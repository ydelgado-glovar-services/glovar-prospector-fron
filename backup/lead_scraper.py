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

def get_next_groq_key() -> str:
    """Rotador Round-Robin auto-recuperable de claves de API de Groq en multihilo."""
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
        
    state_file = ".tmp/groq_rotator_state.json"
    os.makedirs(".tmp", exist_ok=True)
    
    current_index = 0
    # Evitar bloqueos mediante jitter random backoff en accesos concurrentes
    for attempt in range(5):
        try:
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    state = json.load(f)
                    current_index = state.get("current_index", 0)
            break
        except (IOError, json.JSONDecodeError, ValueError):
            time.sleep(0.02 + random.uniform(0.01, 0.03))
            
    selected_key = keys[current_index % len(keys)]
    next_index = (current_index + 1) % len(keys)
    
    for attempt in range(5):
        try:
            with open(state_file, "w") as f:
                json.dump({"current_index": next_index}, f)
            break
        except IOError:
            time.sleep(0.02 + random.uniform(0.01, 0.03))
        
    masked_key = selected_key[:7] + "..." + selected_key[-4:] if len(selected_key) > 10 else "..."
    logger.info(f"Rotating Groq API Key: selected key index {current_index % len(keys)} ({masked_key})")
    return selected_key

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
    
    candidates_list = []
    for idx, lead in enumerate(leads):
        raw_title = lead.get("title", "")
        # Fix B: El título de Google incluye la empresa actual del perfil al final ("Role - Company").
        # Enviamos SOLO la parte del cargo al LLM para evitar que confunda la empresa
        # del título HTML con la empresa que se está prospectando.
        title_for_llm = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
        candidates_list.append({
            "index": idx,
            "name": f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            "profile_headline_or_title": title_for_llm
        })
        
    system_prompt = (
        "You are an expert B2B data cleaning assistant specializing in verifying LinkedIn profile candidates.\n"
        "Your task is to analyze a list of candidates and determine if they match the requested target decision-maker roles.\n\n"
        
        # Fix C: Regla is_active_employee relajada. Los perfiles llegaron via búsqueda
        # site:linkedin.com/in/ + nombre de empresa, así que ya tienen relación con la empresa target.
        # El único disqualificador real es que el CARGO no sea un rol decisor.
        "IMPORTANT CONTEXT: These candidates were found via a Google search specifically targeting "
        "the company name inside LinkedIn profiles. Therefore, assume they have a connection to the "
        "target company unless their title EXPLICITLY uses words like 'former', 'ex-', 'past', 'previo', 'anterior', or 'ex '.\n\n"
        
        "RULES:\n"
        "1. Active Employment (LENIENT):\n"
        "   - Set is_active_employee to TRUE by default for all candidates.\n"
        "   - Only set is_active_employee to FALSE if the title/headline EXPLICITLY contains words like \"former\", \"ex-\", \"past\", \"previo\", \"anterior\".\n"
        "   - Do NOT mark as inactive just because the title shows a company name that differs from the target — the profile_headline_or_title field has already been cleaned and shows only the job role.\n"
        "2. Role Match (PRIMARY FILTER):\n"
        "   - This is the MAIN decision criterion. Does the candidate's title fit the target roles conceptually or contextually?\n"
        "   - For example, if target roles are 'VP Supply Chain, Clinical Operations', a 'Clinical Operations Specialist', 'Director of Clinical Trial Operations', or 'Supply Chain Director' IS a match.\n"
        "   - A generic 'Project Manager', 'Software Developer', 'Doctor', 'HR Manager', or 'Nurse' is NOT a match.\n"
        "   - Disqualify empty, garbage, or invalid titles (e.g. if the title is just the company name itself like 'Kashio Inc' or just initials).\n\n"
        
        "OUTPUT FORMAT:\n"
        "You MUST respond with a valid JSON object matching this schema exactly:\n"
        "{\n"
        "  \"results\": [\n"
        "    {\n"
        "      \"index\": 0,\n"
        "      \"is_active_employee\": true,\n"
        "      \"is_role_match\": true,\n"
        "      \"disqualification_reason\": \"\" (brief explanation written in Spanish of why it was disqualified, leave empty if both are true)\n"
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
        api_key = get_next_groq_key()
        client = Groq(api_key=api_key)
        
        # We use Llama 3.1 8B instant for lightning-fast and low-cost execution
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content or ""
        logger.info(f"LLM pre-flight validation response received: {content.strip()}")
        
        data = json.loads(content)
        results = data.get("results", [])
        
        for res in results:
            idx = res.get("index")
            if idx is not None and 0 <= idx < len(leads):
                lead = leads[idx]
                is_active = res.get("is_active_employee", True)
                is_match = res.get("is_role_match", True)
                
                # Fix D: El único criterio de descalificación real es el cargo (is_role_match).
                # is_active_employee solo descalifica si el perfil es EXPLÍCITAMENTE un ex-empleado.
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


def get_company_domain(company_name: str) -> str:
    """Dynamically finds the official company homepage domain using Tavily Search API or fallback heuristic."""
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        fallback = f"{company_name.lower().replace(' ', '')}.com"
        logger.info(f"TAVILY_API_KEY not found. Fallback domain heuristic: {fallback}")
        return fallback
        
    query = f"{company_name} official website domain homepage"
    logger.info(f"Searching Tavily to resolve official domain for {company_name}...")
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "max_results": 3}
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                blacklist_domains = ["instagram.com", "facebook.com", "linkedin.com", "twitter.com", "youtube.com", "wikipedia.org", "pinterest.com", "tiktok.com", "github.com", "medium.com"]
                for r in results:
                    url = r.get("url") or ""
                    domain = urlparse(url).netloc
                    if domain.startswith("www."):
                        domain = domain[4:]
                    
                    # Ignorar si pertenece a una plataforma social
                    if any(bad in domain.lower() for bad in blacklist_domains):
                        logger.info(f"Ignoring public social profile domain resolved: {domain}")
                        continue
                    
                    logger.info(f"Resolved official domain from search: {domain}")
                    return domain
    except Exception as e:
        logger.error(f"Error querying Tavily for domain resolution: {e}")
        
    fallback = f"{company_name.lower().replace(' ', '')}.com"
    logger.info(f"Using fallback domain heuristic: {fallback}")
    return fallback

def execute_deterministic_pattern_fallback(full_name: str, domain: str) -> str:
    """Infiere de manera determinista el correo electrónico corporativo basándose en patrones estándar B2B."""
    name_parts = [p.strip().lower() for p in full_name.strip().split(" ") if p.strip()]
    if not name_parts:
        return f"contact@{domain}"
        
    first_name = name_parts[0]
    import unicodedata
    def clean_string(s: str) -> str:
        return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        
    first_clean = clean_string(first_name)
    
    if len(name_parts) > 1:
        last_clean = clean_string(name_parts[1])
        # Patrón estándar B2B mayoritario: nombre.apellido@dominio
        return f"{first_clean}.{last_clean}@{domain}"
        
    return f"{first_clean}@{domain}"

def enrich_lead_with_hunter(full_name: str, company_domain: str) -> str | None:
    """Enriches the lead's email by calling Hunter.io Email Finder API, with deterministic fallback guards."""
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
                logger.warning("[RATE LIMIT GUARD] Hunter.io quota exceeded (429). Deflecting to Apollo.io...")
                return None
                
            if response.status_code == 200:
                data = response.json().get("data", {})
                email = data.get("email")
                if email:
                    # Validar que el email no use un dominio de lista negra
                    if any(bad in email.lower() for bad in blacklist_domains):
                        logger.warning(f"Discarding enriched email from public or social platform: {email}")
                        return None
                    logger.info(f"✅ Hunter.io enriched: {email} (confidence {data.get('score', 0)}%)")
                    return email
                else:
                    logger.info(f"❌ Hunter.io could not find email for {full_name}")
            else:
                logger.error(f"Hunter.io API rejected with status {response.status_code}: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error querying Hunter.io Email Finder API: {e}")
        return None
    return None

def enrich_lead_with_apollo(full_name: str, company_domain: str) -> str | None:
    """Fallback B2B enrichment utilizing Apollo.io contacts/search API."""
    apollo_key = os.getenv("APOLLO_API_KEY", "")
    if not apollo_key:
        logger.debug("APOLLO_API_KEY is not defined in the environment. Skipping Apollo enrichment.")
        return None

    # DNS Guard: verify domain resolves to an IP address before querying Apollo.io API
    import socket
    try:
        socket.gethostbyname(company_domain)
    except socket.gaierror:
        logger.warning(f"[Security] DNS Tampering Guard: Domain '{company_domain}' failed DNS resolution. Aborting Apollo enrichment.")
        return None
        
    url = "https://api.apollo.io/api/v1/contacts/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": apollo_key
    }
    payload = {
        "q_keywords": full_name,
        "q_organization_domains_list": [company_domain]
    }
    
    logger.info(f"Querying Apollo.io Search API fallback for '{full_name}' at domain '{company_domain}'...")
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                contacts = response.json().get("contacts", [])
                if contacts:
                    for contact in contacts:
                        email = contact.get("email")
                        if email and "@" in email:
                            # Validar que no use un dominio de lista negra
                            blacklist_domains = ["instagram.com", "facebook.com", "linkedin.com", "twitter.com", "youtube.com", "wikipedia.org", "pinterest.com", "tiktok.com", "github.com", "medium.com", "gmail.com", "hotmail.com", "yahoo.com", "outlook.com"]
                            if any(bad in email.lower() for bad in blacklist_domains):
                                continue
                            logger.info(f"✅ Apollo.io fallback enriched: {email}")
                            return email
                    logger.info(f"❌ Apollo.io could not find any valid verified emails for {full_name}")
            else:
                logger.error(f"Apollo.io API rejected with status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Error querying Apollo.io Search API: {e}")
    return None

async def fallback_tavily_search(company_name: str, target_roles: list[str], original_company_name: str = None) -> list[dict]:
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
        for role in target_roles:
            queries.append((role, f'site:linkedin.com/in/ "{company_name}" {role}'))
            words = role.split()
            if len(words) > 2:
                queries.append((role, f'site:linkedin.com/in/ "{company_name}" {" ".join(words[:2])}'))
                
        for role, query in queries:
            try:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": query, "search_depth": "advanced", "max_results": 3}
                )
                results = response.json().get("results", [])
                role_count = 0
                for item in results:
                    if role_count >= 2:
                        break
                    url = item.get("url") or ""
                    if "linkedin.com/in/" not in url:
                        continue
                        
                    clean_url = url.split("?")[0].rstrip("/")
                    if clean_url in seen_urls:
                        continue
                    seen_urls.add(clean_url)
                    
                    title_clean = item.get("title") or ""
                    for suffix in [" | LinkedIn", " - LinkedIn", " | linkedin", " - linkedin"]:
                        if suffix in title_clean:
                            title_clean = title_clean.split(suffix)[0]
                            
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

async def scrape_linkedin_targets(company_name: str) -> list[dict]:
    apify_token = os.getenv("APIFY_API_TOKEN", "")
    if not apify_token:
        logger.error("APIFY_API_TOKEN is not defined in the environment.")
        return []
        
    # Clean company name to prevent search query failures
    search_company = clean_company_name_for_search(company_name)
        
    try:
        with open(".tmp/active_runtime_context.json", "r") as f:
            context = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read runtime context: {e}")
        return []
        
    cargo_decision = context.get("cargo_decision") or "Executive"
    target_roles = [r.strip() for r in cargo_decision.split(",") if r.strip()]
    if not target_roles:
        target_roles = ["Executive"]
        
    queries = []
    for role in target_roles:
        # Query primaria: comillas estrictas (mayor precisión)
        queries.append(f'site:linkedin.com/in/ "{search_company}" {role}')
        words = role.split()
        if len(words) > 2:
            # Fix A: Variante con solo las 2 primeras palabras del cargo (mayor cobertura)
            queries.append(f'site:linkedin.com/in/ "{search_company}" {" ".join(words[:2])}')
        # Fix A: Variante sin comillas en el nombre de empresa (para empresas pequeñas/nicho
        # donde las comillas estrictas reducen demasiado los resultados)
        queries.append(f'site:linkedin.com/in/ {search_company} {" ".join(words[:2]) if len(words) > 1 else role}')
    payload = {
        "queries": "\n".join(queries),
        "resultsPerPage": 3,
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
                output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)
            else:
                run_data = response.json().get("data", {})
                run_id = run_data.get("id", "")
                dataset_id = run_data.get("defaultDatasetId", "")
                
                if not run_id or not dataset_id:
                    output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)
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
                                output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)
                                break
                        except Exception:
                            output_leads = await fallback_tavily_search(search_company, target_roles, original_company_name=company_name)
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
                                        if role_count >= 2:
                                            break
                                        url = item.get("url") or ""
                                        if "linkedin.com/in/" not in url:
                                            continue
                                        clean_url = url.split("?")[0].rstrip("/")
                                        if clean_url in seen_urls:
                                            continue
                                        seen_urls.add(clean_url)
                                        
                                        title_clean = item.get("title") or ""
                                        for suffix in [" | LinkedIn", " - LinkedIn", " | linkedin", " - linkedin"]:
                                            if suffix in title_clean:
                                                title_clean = title_clean.split(suffix)[0]
                                                
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

    # relevance slice to top 6 to ensure role diversity is validated
    final_leads = output_leads[:6]
    
    # Run adaptive, industry-agnostic LLM pre-flight validation on the candidates
    final_leads = await validate_leads_with_llm(search_company, target_roles, final_leads)

    # Cascade B2B Enrichment (only for non-disqualified leads)
    if final_leads:
        domain = get_company_domain(search_company)
        for lead in final_leads:
            if lead.get("is_disqualified"):
                lead["email"] = None # No contaminar con email de otra empresa
                continue
            full_name = f"{lead['first_name']} {lead['last_name']}".strip()
            
            # 1. Intentar enriquecer prioritariamente con Apollo.io
            email = enrich_lead_with_apollo(full_name, domain)
            
            # 2. Si Apollo no encuentra o falla, intentar con Hunter.io (con Quota Guard)
            if not email:
                email = enrich_lead_with_hunter(full_name, domain)
                
            # 3. Si ambos fallan, usar la heurística determinista como fallback final de la cascada
            if not email:
                email = execute_deterministic_pattern_fallback(full_name, domain)
                logger.info(f"Using B2B deterministic pattern fallback for {full_name}: {email}")
                
            lead["email"] = email
            
    return final_leads

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    args = parser.parse_args()
    
    leads = asyncio.run(scrape_linkedin_targets(args.company))
    os.makedirs(".tmp", exist_ok=True)
    with open(f".tmp/leads_{args.company}.json", "w") as f:
        json.dump(leads, f, indent=2)
    logger.info(f"Extracted dynamic and enriched Hunter.io decision-makers list context for {args.company}")