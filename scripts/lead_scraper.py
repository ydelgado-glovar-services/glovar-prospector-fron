# scripts/lead_scraper.py
import argparse
import os
import sys
import json
import logging
import asyncio
import httpx
import time
import random
from dotenv import load_dotenv
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("prospector_leads")

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

# ── AUDITORÍA #8: Modelo Groq configurable por entorno ──────────────────────────
GROQ_MODEL_REASONING = os.getenv("GROQ_MODEL_REASONING", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "meta-llama/llama-4-scout-17b-16e-instruct")


def get_next_groq_key(company_name: str = "") -> str:
    """Rotador determinista y sin estado (Stateless Hashing) de claves de API de Groq."""
    keys = []
    for i in range(1, 10):
        key = os.getenv(f"GROQ_API_KEY_{i}")
        if key:
            keys.append(key)
    if not keys:
        standard_key = os.getenv("GROQ_API_KEY")
        if standard_key:
            keys.append(standard_key)
            
    if not keys:
        logger.error("No Groq API keys found in environment variables.")
        raise ValueError("No Groq API keys found in environment variables.")
        
    import hashlib
    # Si no se provee un nombre de empresa, se rota usando la marca de tiempo (minuto actual)
    if not company_name:
        import time
        current_index = int(time.time() / 60)
    else:
        current_index = int(hashlib.md5(company_name.encode('utf-8')).hexdigest(), 16)
        
    selected_key = keys[current_index % len(keys)]
    masked_key = selected_key[:7] + "..." + selected_key[-4:] if len(selected_key) > 10 else "..."
    logger.info(f"Rotating Groq API Key (Stateless): selected key index {current_index % len(keys)} ({masked_key})")
    return selected_key

def _dedupe_key(lead: dict):
    """Genera (tokens_de_nombre_normalizados, empresa_normalizada) para deduplicar.
    Colapsa tokens consecutivos repetidos (corrige basura tipo 'Alberto Alberto')."""
    import unicodedata
    def strip_accents(s: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    name = f"{lead.get('first_name','')} {lead.get('last_name','')}"
    tokens = [strip_accents(t).lower() for t in name.split() if t.strip()]
    collapsed: list[str] = []
    for t in tokens:
        if not collapsed or collapsed[-1] != t:
            collapsed.append(t)
    company = strip_accents(lead.get("company_name", "")).lower().strip()
    return collapsed, company


def _same_person(a: list[str], b: list[str]) -> bool:
    """Misma persona si comparten el primer nombre y el conjunto más corto está
    contenido en el más largo (cubre 'Fidel Vargas' vs 'Fidel Vargas Londoño')."""
    if not a or not b or a[0] != b[0]:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return all(tok in longer for tok in shorter)


def _lead_completeness(lead: dict):
    """Prioridad para elegir el representante del cluster de duplicados."""
    tokens, _ = _dedupe_key(lead)
    return (
        0 if lead.get("is_disqualified") else 1,  # preferir NO descalificado
        len(tokens),                               # preferir nombre más completo
        1 if lead.get("email") else 0,             # preferir con email
        1 if lead.get("linkedin_url") else 0,      # preferir con URL
    )


def _merge_leads(primary: dict, secondary: dict) -> dict:
    """Rellena en `primary` los campos faltantes a partir de `secondary`."""
    for field in ("email", "linkedin_url", "title", "first_name", "last_name", "company_name"):
        if not primary.get(field) and secondary.get(field):
            primary[field] = secondary[field]
    return primary


def _clean_name(first: str, last: str):
    """Corrige nombres con apellido duplicado por parsing ruidoso
    (ej. first='Carlos Alberto', last='Alberto' -> 'Carlos Alberto', '')."""
    ft = (first or "").split()
    lt = (last or "").split()
    # Quitar tokens iniciales del apellido que repiten el final del nombre.
    while lt and ft and lt[0].lower() == ft[-1].lower():
        lt.pop(0)
    # Colapsar duplicados consecutivos dentro de cada parte.
    def _collapse(seq):
        out = []
        for tok in seq:
            if not out or out[-1].lower() != tok.lower():
                out.append(tok)
        return out
    return " ".join(_collapse(ft)), " ".join(_collapse(lt))


def deduplicate_leads(leads: list[dict]) -> list[dict]:
    """Deduplicación ESTRICTA por (nombre normalizado + empresa) ANTES de gastar
    tokens del LLM y de persistir. Conserva el representante más completo y fusiona
    los campos útiles del resto del cluster."""
    # Limpieza previa de nombres (corrige apellidos duplicados tipo 'Alberto Alberto').
    for lead in leads:
        cf, cl = _clean_name(lead.get("first_name", ""), lead.get("last_name", ""))
        lead["first_name"], lead["last_name"] = cf, cl

    kept: list[dict] = []
    for lead in leads:
        tokens, company = _dedupe_key(lead)
        if not tokens:
            continue  # descartar entradas sin un nombre real (páginas, posts, ruido)
        match = None
        for entry in kept:
            if entry["company"] == company and _same_person(tokens, entry["tokens"]):
                match = entry
                break
        if match is None:
            kept.append({"tokens": tokens, "company": company, "lead": lead})
        else:
            if _lead_completeness(lead) > _lead_completeness(match["lead"]):
                match["lead"] = _merge_leads(lead, match["lead"])
                match["tokens"] = tokens
            else:
                match["lead"] = _merge_leads(match["lead"], lead)
    deduped = [e["lead"] for e in kept]
    if len(deduped) < len(leads):
        logger.info(f"[Dedup] Leads unificados: {len(leads)} -> {len(deduped)} (se removieron {len(leads) - len(deduped)} clones).")
    return deduped


async def validate_leads_with_llm(company_name: str, target_roles: list[str], leads: list[dict]) -> list[dict]:
    """
    Utiliza un LLM (Llama 3.1 8B en Groq) rápido, económico y adaptativo para validar si
    los perfiles de LinkedIn corresponden a empleados activos y coinciden semánticamente
    con los cargos decisores autorizados. Esto es 100% agnóstico de la industria/sector.
    """
    if not leads:
        return []
        
    try:
        from groq import Groq
    except ImportError:
        logger.error("Groq library is not installed. Skipping LLM pre-validation.")
        for lead in leads:
            lead["is_disqualified"] = False
        return leads
        
    logger.info(f"Running adaptive LLM pre-flight validation for {len(leads)} candidates at {company_name}...")
    
    # Preparamos los candidatos usando su linkedin_url como ID único estable para prevenir State Desync
    candidates_list = []
    for lead in leads:
        raw_title = lead.get("title", "")
        candidates_list.append({
            "id": lead.get("linkedin_url"),
            "raw_title": raw_title
        })
        
    system_prompt = (
        "You are an expert B2B data cleaning assistant specializing in verifying LinkedIn profile candidates from search engine titles.\n"
        "Your task is to analyze a list of candidates and determine if they match the requested target decision-maker roles.\n\n"
        
        "Since Google changes search title formatting dynamically (e.g. sometimes putting job titles or company names first), you must "
        "intelligently extract the candidate's real First Name, Last Name, and Cleaned Job Title from the raw title string.\n"
        "If a candidate has a compound middle name or double surname common in LATAM, split them correctly so that first_name has their names (e.g. 'Juan Carlos') and last_name has their surname(s) (e.g. 'Pérez').\n"
        "If the raw title does not contain a real person's name (e.g., it is a company page or a post), mark is_role_match as FALSE.\n\n"
        
        "IMPORTANT CONTEXT: These candidates were found via a Google search specifically targeting "
        "the company name inside LinkedIn profiles. Therefore, assume they have a connection to the "
        "target company unless their title EXPLICITLY uses words like 'former', 'ex-', 'past', 'previo', 'anterior', or 'ex '.\n\n"
        
        "RULES:\n"
        "1. Active Employment (LENIENT):\n"
        "   - Set is_active_employee to TRUE by default for all candidates.\n"
        "   - Only set is_active_employee to FALSE if the title/headline EXPLICITLY contains words like \"former\", \"ex-\", \"past\", \"previo\", \"anterior\".\n"
        "2. Role Match (PRIMARY FILTER) — be deterministic and robust to noise:\n"
        "   - Judge ONLY the candidate's JOB TITLE/headline against the target roles. IGNORE any unrelated news, company description, or context noise.\n"
        "   - ALWAYS set is_role_match=TRUE for clear decision-maker/executive titles even if the wording is noisy, e.g.: "
        "Director/Directora, CIO, CTO, CEO, CFO, COO, CMO, CISO, Chief (any C-level), VP/Vicepresidente, Head of, Gerente, Manager, Jefe, "
        "Líder/Lead, Presidente, Founder/Fundador, Owner/Socio, and any title containing the requested target roles.\n"
        "   - Set is_role_match=FALSE ONLY if the title is empty/garbage, is clearly a non-decision role (intern, becario, pasante, asistente, auxiliar, estudiante), "
        "or belongs to an unrelated department (HR/RRHH, marketing, design) that does not match the target roles.\n"
        "   - When in doubt about a senior-sounding title, set is_role_match=TRUE.\n\n"
        
        "OUTPUT FORMAT:\n"
        "You MUST respond with a valid JSON object matching this schema exactly:\n"
        "{\n"
        "  \"results\": [\n"
        "    {\n"
        "      \"id\": \"linkedin_url_of_the_lead\",\n"
        "      \"first_name\": \"Extracted First Name\",\n"
        "      \"last_name\": \"Extracted Last Name\",\n"
        "      \"cleaned_job_title\": \"Extracted Job Title\",\n"
        "      \"is_active_employee\": true,\n"
        "      \"is_role_match\": true,\n"
        "      \"disqualification_reason\": \"\" (brief explanation written in Spanish, leave empty if both are true)\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Do NOT include any preamble, conversational text, or markdown code blocks (like ```json). Respond with pure raw JSON text only."
    )
    
    user_prompt = (
        f"Target Company: {company_name}\n"
        f"Requested Target Roles: {', '.join(target_roles)}\n\n"
        f"Candidates to analyze:\n{json.dumps(candidates_list, indent=2)}"
    )
    
    try:
        api_key = get_next_groq_key(company_name)
        client = Groq(api_key=api_key)
        
        # We use Llama 4 Scout for high cognitive precision role matching
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=GROQ_MODEL_REASONING,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content or ""
        logger.info(f"LLM pre-flight validation response received: {content.strip()}")
        
        data = json.loads(content)
        results = data.get("results", [])
        
        # Mapeo usando la URL de LinkedIn como llave única estable
        leads_map = {lead.get("linkedin_url"): lead for lead in leads if lead.get("linkedin_url")}
        
        for res in results:
            lid = res.get("id")
            if lid and lid in leads_map:
                lead = leads_map[lid]
                is_active = res.get("is_active_employee", True)
                is_match = res.get("is_role_match", True)
                
                # Sobrescribir nombres y cargos si el LLM los extrajo con éxito
                if res.get("first_name") and res.get("first_name") != "Extracted First Name":
                    lead["first_name"] = res.get("first_name")
                if res.get("last_name") and res.get("last_name") != "Extracted Last Name":
                    lead["last_name"] = res.get("last_name")
                if res.get("cleaned_job_title") and res.get("cleaned_job_title") != "Extracted Job Title":
                    lead["title"] = res.get("cleaned_job_title")
                
                if not is_active:
                    lead["is_disqualified"] = True
                    lead["disqualification_reason"] = res.get("disqualification_reason") or "Descalificado: El perfil indica explícitamente ser ex-empleado."
                    lead["disqualification_trigger"] = "Ex-Empleado Confirmado"
                elif not is_match:
                    lead["is_disqualified"] = True
                    lead["disqualification_reason"] = res.get("disqualification_reason") or "Descalificado: El cargo del lead no se alinea con los roles decisores requeridos."
                    lead["disqualification_trigger"] = "Nombre de Cargo Inválido"
                else:
                    lead["is_disqualified"] = False
                    
        # Garantizar que todos los leads tengan la llave
        for lead in leads:
            if "is_disqualified" not in lead:
                lead["is_disqualified"] = False
                
    except Exception as e:
        logger.error(f"Error during LLM pre-flight validation: {e}. Falling back to default safety state.")
        for lead in leads:
            lead["is_disqualified"] = False
            
    return leads


# ── Resolución de dominio corporativo (hardening anti-emails basura) ─────────────
# Data-brokers, directorios, redes y portales que NO son el sitio oficial de una
# empresa. Si la resolución cae en uno de estos, el email inferido rebota seguro
# (ej. leadiq.com, zoominfo.com, emis.com vistos en las pruebas).
_DOMAIN_BLACKLIST = [
    # Redes sociales y plataformas
    "instagram.com", "facebook.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "wikipedia.org", "pinterest.com", "tiktok.com", "github.com",
    "medium.com", "glassdoor.com", "indeed.com", "computrabajo.com",
    # Data-brokers / agregadores B2B (origen de los emails basura en las pruebas)
    "zoominfo.com", "leadiq.com", "rocketreach.co", "rocketreach.com", "lusha.com",
    "signalhire.com", "contactout.com", "apollo.io", "hunter.io", "clearbit.com",
    "crunchbase.com", "emis.com", "kompass.com", "dnb.com", "owler.com",
    "b2bmarketplace.procolombia.co", "procolombia.co", "einforma.com", "infoempresa.com",
    "universidadperu.com", "datacreditos.com", "griinstitute.org",
    # Prensa / portales de noticias
    "portafolio.co", "larepublica.co", "techcrunch.com", "dinero.com",
    "informacolombia.com", "elremate.com", "las2orillas.co", "valoraanalitik.com",
    "bloomberg.com", "elespectador.com", "eltiempo.com", "semana.com",
    "apify.com", "tavily.com",
    # Emails personales/públicos (nunca son dominio corporativo)
    "gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "icloud.com", "live.com",
]

# Sufijos legales y palabras genéricas que NO ayudan a identificar el dominio.
_LEGAL_STOPWORDS = {
    "sas", "sa", "sac", "ltda", "ltd", "llc", "inc", "corp", "corporation", "co",
    "company", "group", "grupo", "holding", "holdings", "plc", "gmbh", "srl",
    "the", "de", "del", "la", "el", "los", "las", "y", "and", "of", "services",
    "servicios", "solutions", "soluciones", "global", "international", "internacional",
}


def _norm_alnum(s: str) -> str:
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _company_tokens(name: str) -> list[str]:
    """Tokens significativos del nombre (sin sufijos legales ni palabras genéricas)."""
    import unicodedata, re as _re
    s = "".join(c for c in unicodedata.normalize("NFD", name or "") if unicodedata.category(c) != "Mn")
    toks = [t.lower() for t in _re.findall(r"[A-Za-z0-9]+", s)]
    return [t for t in toks if t not in _LEGAL_STOPWORDS and len(t) >= 2]


def _domain_root(domain: str) -> str:
    """Etiqueta registrable aproximada del dominio, normalizada a alfanumérico.
    'www.bancodebogota.com.co' -> 'bancodebogota'; 'tp-link.com' -> 'tplink'."""
    d = (domain or "").lower().strip()
    if d.startswith("www."):
        d = d[4:]
    labels = [l for l in d.split(".") if l]
    if not labels:
        return ""
    # TLDs compuestos comunes (com.co, gob.cl, com.mx, co.uk...).
    multi_tld = {"com", "co", "org", "net", "gob", "gov", "edu", "ac"}
    if len(labels) >= 3 and labels[-2] in multi_tld:
        root = labels[-3]
    elif len(labels) >= 2:
        root = labels[-2]
    else:
        root = labels[0]
    return _norm_alnum(root)


def _domain_matches_company(domain: str, company_name: str) -> bool:
    """Verifica que el dominio resuelto pertenezca PLAUSIBLEMENTE a la empresa.
    Evita los falsos positivos del autocompletado difuso (p. ej. 'TP' -> tp-link.com,
    'X' -> x.com) sin descartar acrónimos legítimos cortos ('SLB' -> slb.com)."""
    root = _domain_root(domain)
    if not root:
        return False
    tokens = _company_tokens(company_name)
    if not tokens:
        return False
    concat = "".join(tokens)
    # 1) Coincidencia exacta de la raíz con la concatenación (cubre acrónimos cortos
    #    legítimos como 'SLB' -> slb.com, 'IQVIA' -> iqvia.com).
    if root == concat:
        return True
    # 2) Un token relevante (>=4) contenido en la raíz del dominio.
    for t in tokens:
        if len(t) >= 4 and t in root:
            return True
    # 3) Substring en cualquier dirección, exigiendo longitud >=4 en AMBOS lados
    #    (evita que 'tp' haga match con 'tplink').
    if len(root) >= 4 and len(concat) >= 4 and (root in concat or concat in root):
        return True
    # 4) Acrónimo de las iniciales (>=2 tokens) == raíz del dominio.
    if len(tokens) >= 2:
        acronym = "".join(t[0] for t in tokens)
        if len(acronym) >= 2 and acronym == root:
            return True
    return False


def get_company_domain(company_name: str) -> str:
    """Resuelve el dominio corporativo oficial (Clearbit → Tavily → heurística),
    VERIFICANDO que el dominio realmente pertenezca a la empresa antes de aceptarlo.
    Devuelve "" si no se puede resolver con confianza (mejor sin email que con uno
    que rebota a un data-broker)."""
    # 1. Clearbit Autocomplete (rápido y preciso) — con verificación de pertenencia.
    logger.info(f"Trying Clearbit Autocomplete domain lookup for: {company_name}...")
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(
                "https://autocomplete.clearbit.com/v1/companies/suggest",
                params={"query": company_name}
            )
            if response.status_code == 200:
                suggestions = response.json()
                if suggestions and isinstance(suggestions, list):
                    for best_match in suggestions[:3]:
                        domain = (best_match.get("domain") or "").lower()
                        if not domain:
                            continue
                        if any(bad in domain for bad in _DOMAIN_BLACKLIST):
                            continue
                        if _domain_matches_company(domain, company_name):
                            logger.info(f"✅ Clearbit resolved & verified domain: {domain}")
                            return domain
                        else:
                            logger.info(f"Clearbit suggestion '{domain}' rejected (no coincide con '{company_name}').")
    except Exception as e:
        logger.debug(f"Clearbit Autocomplete lookup failed/skipped: {e}")

    # 2. Fallback a Tavily Search con sanitización + verificación de pertenencia.
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.info(f"TAVILY_API_KEY not found and Clearbit unverified for '{company_name}'. No domain resolved.")
        return ""

    query = f"{company_name} official website domain homepage"
    logger.info(f"Searching Tavily to resolve official domain for {company_name}...")
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": 5}
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                first_verified = None
                for r in results:
                    url = r.get("url") or ""
                    domain = urlparse(url).netloc
                    if domain.startswith("www."):
                        domain = domain[4:]
                    domain = domain.lower()
                    if not domain or any(bad in domain for bad in _DOMAIN_BLACKLIST):
                        continue
                    if _domain_matches_company(domain, company_name):
                        logger.info(f"✅ Tavily resolved & verified domain: {domain}")
                        return domain
                    if first_verified is None:
                        first_verified = domain  # candidato no verificado, último recurso
                if first_verified:
                    logger.info(f"Tavily domain '{first_verified}' no verificado contra el nombre; se descarta para no inferir email basura.")
    except Exception as e:
        logger.error(f"Error querying Tavily for domain resolution: {e}")

    # 3. Sin resolución confiable: devolver "" (el llamador NO inferirá email).
    logger.info(f"No reliable corporate domain resolved for '{company_name}'.")
    return ""


def execute_deterministic_pattern_fallback(full_name: str, domain: str) -> str:
    """Infiere de manera determinista el correo electrónico corporativo basándose en patrones estándar B2B, con soporte LATAM."""
    name_parts = [p.strip().lower() for p in full_name.strip().split(" ") if p.strip()]
    if not name_parts:
        return f"contact@{domain}"
        
    first_name = name_parts[0]
    import unicodedata
    def clean_string(s: str) -> str:
        return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        
    first_clean = clean_string(first_name)
    
    if len(name_parts) > 1:
        # Heurística LATAM: Identificar segundos nombres comunes para evitar usarlos como apellido
        SEGUNDOS_NOMBRES = [
            "carlos", "maria", "jose", "antonio", "luis", "fernando", "andres", 
            "camilo", "felipe", "alejandro", "eduardo", "manuel", "francisco", 
            "david", "sebastian", "javier", "alberto", "diego", "daniel", "carmenza",
            "patricia", "beatriz", "helena", "isabel", "cristina", "alexandra"
        ]
        
        # Si tiene 3 o más partes y el segundo elemento es un segundo nombre común, saltamos al apellido real
        if len(name_parts) >= 3 and name_parts[1] in SEGUNDOS_NOMBRES:
            last_clean = clean_string(name_parts[2])
        else:
            last_clean = clean_string(name_parts[1])
            
        # Patrón estándar B2B mayoritario: nombre.apellido@dominio
        return f"{first_clean}.{last_clean}@{domain}"
        
    return f"{first_clean}@{domain}"

def verify_email_with_hunter(email: str, hunter_key: str) -> bool:
    """Confirma la entregabilidad real de un email vía Hunter Email Verifier
    (GET /v2/email-verifier). Devuelve True solo si el veredicto es entregable
    (data.status == 'valid' o data.result == 'deliverable')."""
    if not email or not hunter_key:
        return False
    url = "https://api.hunter.io/v2/email-verifier"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params={"email": email, "api_key": hunter_key})
            if response.status_code == 200:
                data = response.json().get("data", {})
                status = (data.get("status") or "").lower()
                result = (data.get("result") or "").lower()
                return status == "valid" or result == "deliverable"
            logger.warning(f"Hunter Email Verifier status {response.status_code} para '{email}'.")
    except Exception as e:
        logger.error(f"Error querying Hunter.io Email Verifier API: {e}")
    return False


def enrich_lead_with_hunter(full_name: str, company_domain: str) -> str | None:
    """Busca y VERIFICA el email profesional de la persona vía Hunter.io.

    Usa el Email Finder (/v2/email-finder) y devuelve el email SOLO si Hunter
    confirma que es válido/entregable (política "solo correos verídicos"). Si no
    hay un email verificado, devuelve None (no se infieren correos por patrón)."""
    hunter_key = os.getenv("HUNTER_API_KEY", "")
    if not hunter_key:
        logger.warning("HUNTER_API_KEY is not defined in the environment. Skipping enrichment.")
        return None
        
    blacklist_domains = ["instagram.com", "facebook.com", "linkedin.com", "twitter.com", "youtube.com", "wikipedia.org", "pinterest.com", "tiktok.com", "github.com", "medium.com", "gmail.com", "hotmail.com", "yahoo.com", "outlook.com"]
    if any(bad in company_domain.lower() for bad in blacklist_domains):
        logger.warning(f"Aborting Hunter.io lookup: Domain '{company_domain}' belongs to public platforms or social networks list.")
        return None

    # DNS Guard: verify domain resolves to an IP address before querying paid Hunter.io API
    import socket
    try:
        socket.gethostbyname(company_domain)
    except socket.gaierror:
        logger.warning(f"[Security] DNS Tampering Guard: Domain '{company_domain}' failed DNS resolution. Aborting Hunter enrichment.")
        return None
        
    name_parts = full_name.strip().split(" ", 1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""
    
    url = "https://api.hunter.io/v2/email-finder"
    params = {
        "domain": company_domain,
        "first_name": first_name,
        "last_name": last_name,
        "api_key": hunter_key
    }
    
    logger.info(f"Querying Hunter.io for lead '{full_name}' at domain '{company_domain}'...")
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params=params)
            
            # Hunter.io Quota Exceeded Rate Limit Guard (HTTP 429)
            if response.status_code == 429:
                logger.warning("[RATE LIMIT GUARD] Hunter.io quota exceeded (429). Skipping enrichment.")
                return None
                
            if response.status_code == 200:
                data = response.json().get("data", {})
                email = data.get("email")
                if not email:
                    logger.info(f"❌ Hunter.io could not find email for {full_name}")
                    return None
                # Descarta dominios públicos / redes sociales.
                if any(bad in email.lower() for bad in blacklist_domains):
                    logger.warning(f"Discarding enriched email from public or social platform: {email}")
                    return None
                # ── Gate "solo correo verídico" ──
                # Hunter reporta la validez en data.verification.status. Aceptamos el
                # email SOLO si está verificado como 'valid'. Si el Finder no trae un
                # veredicto pero la confianza es alta y el dominio no es catch-all, lo
                # confirmamos con el Email Verifier antes de aceptarlo.
                score = data.get("score", 0) or 0
                finder_status = ((data.get("verification") or {}).get("status") or "").lower()
                accept_all = bool(data.get("accept_all"))
                is_valid = finder_status == "valid"
                if not is_valid and not accept_all and score >= 80:
                    is_valid = verify_email_with_hunter(email, hunter_key)
                if is_valid:
                    logger.info(f"✅ Hunter verificado: {email} (score {score}%, status '{finder_status or 'checked'}')")
                    return email
                logger.info(
                    f"⚠️ Hunter halló {email} pero no es verídico "
                    f"(score {score}, status '{finder_status or 'n/a'}', accept_all={accept_all}); se descarta."
                )
                return None
            else:
                logger.error(f"Hunter.io API rejected with status {response.status_code}: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error querying Hunter.io Email Finder API: {e}")
        return None
    return None

async def fallback_tavily_search(company_name: str, target_roles: list[str], original_company_name: str = None, country: str = "") -> list[dict]:
    """Graceful Tavily fallback to search and extract LinkedIn profile candidates."""
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    output_leads = []
    seen_urls = set()
    
    if not tavily_key:
        logger.warning("Tavily API key not found. Skipping fallback LinkedIn search.")
        return []
        
    logger.info("Triggering fallback Tavily search for LinkedIn profiles...")
    async with httpx.AsyncClient(timeout=20.0) as client:
        queries = []
        country_str = f' "{country}"' if country else ""
        for role in target_roles:
            queries.append((role, f'site:linkedin.com/in/ "{company_name}" {role}{country_str}'))
            words = role.split()
            if len(words) > 2:
                queries.append((role, f'site:linkedin.com/in/ "{company_name}" {" ".join(words[:2])}{country_str}'))
                
        for role, query in queries:
            try:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": query, "search_depth": "advanced", "max_results": 5}
                )
                results = response.json().get("results", [])
                role_count = 0
                for item in results:
                    if role_count >= 3:
                        break
                    url = item.get("url") or ""
                    if "linkedin.com/in/" not in url:
                        continue
                        
                    clean_url = url.split("?")[0].rstrip("/")
                    if clean_url in seen_urls:
                        continue
                    seen_urls.add(clean_url)
                    
                    title_clean = item.get("title") or ""
                    import re
                    title_clean = re.sub(r'\s*\|\s*LinkedIn.*$', '', title_clean, flags=re.IGNORECASE)
                    title_clean = re.sub(r'\s*-\s*LinkedIn.*$', '', title_clean, flags=re.IGNORECASE)
                            
                    parts = [p.strip() for p in title_clean.split("-") if p.strip()]
                    if not parts:
                        continue
                        
                    full_name = parts[0]
                    name_parts = full_name.split(" ", 1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ""
                    
                    output_leads.append({
                        "first_name": first_name or "Target",
                        "last_name": last_name or "",
                        "title": " - ".join(parts[1:]) if len(parts) > 1 else f"{role} Professional",
                        "linkedin_url": clean_url,
                        "company_name": original_company_name or company_name
                    })
                    role_count += 1
            except Exception as err:
                logger.debug(f"Silent skip on Tavily single-role fallback: {err}")
                continue
                
    return output_leads

def clean_company_name_for_search(name: str) -> str:
    """
    Cleans long, noisy, or explanatory company descriptions returned by Tavily/RAG
    to prevent search query failure in LinkedIn search engines.
    """
    if not name:
        return ""
    
    clean = name.strip()
    
    # 1. Handle common email pattern suffixes or parenthetical text
    # e.g., "NCIinfo@nih.gov (Institutos Nacionales de la Salud)" -> "Institutos Nacionales de la Salud"
    if "@" in clean and "(" in clean and ")" in clean:
        import re
        match = re.search(r'\(([^)]+)\)', clean)
        if match:
            clean = match.group(1).strip()
            
    # Remove email addresses if they are still present
    if "@" in clean:
        clean = " ".join([w for w in clean.split() if "@" not in w])
        
    # Remove trailing parenthetical phrases like "(FDA)" at the very end of the string
    import re
    clean = re.sub(r'\s*\([^)]*\)\s*$', '', clean).strip()
        
    # 2. Split by common descriptive action verbs or noise terms
    words = clean.split()
    noise_verbs = [
        "mantiene", "maneja", "cobertura", "visitas", "depósitos", 
        "proveedores", "couriers", "coordinadores", "transporte", 
        "enfermeras", "ofrece", "ofrecen", "brinda", "brindan", 
        "presenta", "cuenta"
    ]
    
    cut_index = len(words)
    for i, word in enumerate(words):
        # We only cut if it's after the first word
        if word.lower().strip(".,:-_()") in noise_verbs and i > 0:
            cut_index = i
            break
            
    if cut_index < len(words):
        clean = " ".join(words[:cut_index])
    
    # Clean up common trailing punctuation but avoid leaving unbalanced parenthesis
    clean = clean.strip(".,:-_\"'[]{}")
    
    logger.info(f"[Company Name Clean] Original: '{name}' -> Cleaned: '{clean}'")
    return clean

async def scrape_linkedin_targets(company_name: str, job_id: str | None = None) -> list[dict]:
    apify_token = os.getenv("APIFY_API_TOKEN", "")
    if not apify_token:
        logger.error("APIFY_API_TOKEN is not defined in the environment.")
        return []
        
    # Clean company name to prevent search query failures
    search_company = clean_company_name_for_search(company_name)
        
    try:
        # Contexto aislado por job_id (evita leer el contexto de OTRA corrida).
        # Fallback al archivo legacy global solo si no se provee job_id (modo standalone).
        if job_id:
            from scripts.runtime_paths import context_path
            ctx_file = context_path(job_id)
        else:
            ctx_file = ".tmp/active_runtime_context.json"
        with open(ctx_file, "r") as f:
            context = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read runtime context: {e}")
        return []
        
    cargo_decision = context.get("cargo_decision") or "Executive"
    country_target = context.get("target_market_region") or context.get("pais") or ""
    target_roles = [r.strip() for r in cargo_decision.split(",") if r.strip()]
    if not target_roles:
        target_roles = ["Executive"]
        
    queries = []
    country_str = f' "{country_target}"' if country_target else ""
    for role in target_roles:
        # Query primaria: comillas estrictas (mayor precisión)
        queries.append(f'site:linkedin.com/in/ "{search_company}" {role}{country_str}')
        words = role.split()
        if len(words) > 2:
            # Fix A: Variante con solo las 2 primeras palabras del cargo (mayor cobertura)
            queries.append(f'site:linkedin.com/in/ "{search_company}" {" ".join(words[:2])}{country_str}')
        # Fix A: Variante sin comillas en el nombre de empresa (para empresas pequeñas/nicho
        # donde las comillas estrictas reducen demasiado los resultados)
        queries.append(f'site:linkedin.com/in/ {search_company} {" ".join(words[:2]) if len(words) > 1 else role}{country_str}')
    payload = {
        "queries": "\n".join(queries),
        "resultsPerPage": 5,
        "maxPagesPerQuery": 1,
        "mobileResults": False,
        "aiMode": "aiModeOff"
    }
    
    start_url = f"https://api.apify.com/v2/acts/apify~google-search-scraper/runs?token={apify_token}"
    logger.info(f"Initiating Apify LinkedIn search actor for {search_company}...")
    
    output_leads = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(start_url, json=payload)
            if response.status_code not in [200, 201]:
                logger.error(f"Apify returned status code {response.status_code}. Using Tavily fallback.")
                output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name, country=country_target)
            else:
                run_data = response.json().get("data", {})
                run_id = run_data.get("id", "")
                dataset_id = run_data.get("defaultDatasetId", "")
                
                if not run_id or not dataset_id:
                    output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name, country=country_target)
                else:
                    poll_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={apify_token}"
                    logger.info("Polling Apify search actor run status...")
                    while True:
                        await asyncio.sleep(4)
                        try:
                            poll_resp = await client.get(poll_url)
                            if poll_resp.status_code != 200:
                                continue
                            status = poll_resp.json().get("data", {}).get("status", "")
                            if status == "SUCCEEDED":
                                break
                            elif status in ["FAILED", "TIMED-OUT", "ABORTED"]:
                                logger.error(f"Apify run finished with status: {status}. Using Tavily fallback.")
                                output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name, country=country_target)
                                break
                        except Exception:
                            output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name, country=country_target)
                            break
                            
                    if not output_leads:
                        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={apify_token}"
                        try:
                            items_resp = await client.get(dataset_url)
                            if items_resp.status_code == 200:
                                items = items_resp.json()
                                seen_urls = set()
                                for query_result in items:
                                    role_count = 0
                                    for item in query_result.get("organicResults", []):
                                        if role_count >= 3:
                                            break
                                        url = item.get("url") or ""
                                        if "linkedin.com/in/" not in url:
                                            continue
                                        clean_url = url.split("?")[0].rstrip("/")
                                        if clean_url in seen_urls:
                                            continue
                                        seen_urls.add(clean_url)
                                        
                                        title_clean = item.get("title") or ""
                                        import re
                                        title_clean = re.sub(r'\s*\|\s*LinkedIn.*$', '', title_clean, flags=re.IGNORECASE)
                                        title_clean = re.sub(r'\s*-\s*LinkedIn.*$', '', title_clean, flags=re.IGNORECASE)
                                                
                                        parts = [p.strip() for p in title_clean.split("-") if p.strip()]
                                        if not parts:
                                            continue
                                        full_name = parts[0]
                                        name_parts = full_name.split(" ", 1)
                                        
                                        output_leads.append({
                                            "first_name": name_parts[0] or "Target",
                                            "last_name": name_parts[1] if len(name_parts) > 1 else "",
                                            "title": " - ".join(parts[1:]) if len(parts) > 1 else "Target Professional",
                                            "linkedin_url": clean_url,
                                            "company_name": company_name
                                        })
                                        role_count += 1
                            else:
                                output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)
                        except Exception:
                            output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)
        except Exception as e:
            logger.error(f"Apify execution failure, using fallback: {e}")
            output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)

    # AUDITORÍA (dedup): unificar clones por (nombre + empresa) ANTES de gastar
    # tokens del LLM. Corrige duplicados tipo 'Fidel Vargas' vs 'Fidel Vargas Londoño'
    # y basura de parsing tipo 'Carlos Alberto Alberto'.
    output_leads = deduplicate_leads(output_leads)

    # relevance slice to top 8 to improve decision-maker recall while keeping enrichment cost bounded
    final_leads = output_leads[:8]
    
    # Run adaptive, industry-agnostic LLM pre-flight validation on the candidates
    final_leads = await validate_leads_with_llm(search_company, target_roles, final_leads)

    # Segunda pasada de dedup: tras la limpieza de nombres del LLM pueden quedar
    # clones idénticos; los unificamos antes de enriquecer y persistir.
    final_leads = deduplicate_leads(final_leads)

    # Cascade B2B Enrichment (only for non-disqualified leads)
    # AUDITORÍA #6: se registra el ORIGEN del email y si está verificado, para no
    # contactar a ciegas direcciones inferidas por patrón (riesgo de rebote).
    if final_leads:
        domain = get_company_domain(search_company)
        for lead in final_leads:
            if lead.get("is_disqualified"):
                lead["email"] = None  # No contaminar con email de otra empresa
                lead["email_source"] = None
                lead["email_verified"] = False
                continue
            full_name = f"{lead['first_name']} {lead['last_name']}".strip()

            email = None
            email_source = None
            email_verified = False

            # Si NO se resolvió un dominio corporativo confiable, NO inferimos email
            # (mejor sin email que con uno que rebota a un data-broker).
            if not domain:
                lead["email"] = None
                lead["email_source"] = None
                lead["email_verified"] = False
                logger.info(f"Sin dominio confiable para '{search_company}'; se omite email de {full_name}.")
                continue

            # Única fuente de email: Hunter.io (Finder + Verifier). Política
            # "solo correos verídicos": si Hunter no confirma un email válido,
            # se deja vacío (no se infieren correos por patrón).
            email = enrich_lead_with_hunter(full_name, domain)
            if email:
                email_source = "hunter"
                email_verified = True
            else:
                logger.info(f"Sin email verídico de Hunter para {full_name}; se deja vacío.")

            lead["email"] = email
            lead["email_source"] = email_source
            lead["email_verified"] = email_verified

    return final_leads

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--job_id", required=False, default=None)
    args = parser.parse_args()
    
    leads = asyncio.run(scrape_linkedin_targets(args.company, args.job_id))
    from scripts.runtime_paths import leads_path
    if args.job_id:
        out_path = leads_path(args.job_id, args.company)
    else:
        os.makedirs(".tmp", exist_ok=True)
        out_path = f".tmp/leads_{args.company}.json"
    with open(out_path, "w") as f:
        json.dump(leads, f, indent=2)
    logger.info(f"Extracted dynamic and enriched Hunter.io decision-makers list context for {args.company}")