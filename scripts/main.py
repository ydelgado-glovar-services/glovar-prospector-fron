# scripts/main.py 1
import argparse
import os
import sys

# Ensure the workspace root is in sys.path so scripts can be imported as packages
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
import json
import logging
import subprocess
import time
from typing import List
import httpx
from dotenv import load_dotenv
from groq import Groq
import groq
from pydantic import BaseModel, Field
import concurrent.futures

# Configure basic logging architecture for system visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("prospector_main")

# Reconfigure stdout/stderr to support UTF-8 natively on Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

# ── Modelo Groq único, configurable por entorno (ver directivas/09_lead_scoring_engine_SOP.md) ──
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


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


def extract_strategic_intent(form_data: dict) -> dict:
    """
    FASE 0: Pre-flight Intent Parser Cognitivo.
    Toma el formulario crudo del cliente y lo convierte en un mapa cognitivo
    de intenciones de búsqueda y dolores corporativos optimizados para el pipeline RAG.
    Elimina la dependencia de diccionarios estáticos y reglas rígidas.
    """
    logger.info("═══ FASE 0: Extracting Strategic Intent from raw form payload ═══")
    
    api_key = get_next_groq_key("intent_parser")
    client = Groq(api_key=api_key)
    
    system_prompt = (
        "You are an expert B2B Commercial Strategy Intent Parser.\n"
        "Your job is to analyze a raw client onboarding form and extract the deep commercial intent, "
        "generating optimized search tokens and conceptual constraints for an automated RAG pipeline.\n\n"
        "CRITICAL ONTOLOGICAL ANALYSIS:\n"
        "You must semantically analyze the 'Value Proposition' (propuesta_valor) to autonomously identify the sending company's business model. "
        "Deduce which profiles or industries act as their DIRECT COMPETITORS (Anti-Profiles) rather than clients. "
        "Generate explicit business constraints to exclude these competitors.\n"
        "FUNDAMENTAL DISTINCTION: A company that OPERATES IN the target industry is a CLIENT, never a competitor — "
        "even if it runs internal operations similar to the sender's service. Example: if the sender is a 3PL/logistics "
        "operator and the target industry is CRO/biopharma, then CROs are CLIENTS (they NEED logistics); the competitors "
        "(Anti-Profile) are OTHER logistics/3PL/courier/freight operators, NOT the CROs. Do NOT confuse the client's "
        "industry with the sender's own service category.\n\n"
        "You must output a strict JSON object with the following keys:\n"
        "1. 'optimized_search_tokens': An array of the 4 best, high-relevance search terms in English/Spanish "
        "for search engines. CRITICAL: These tokens MUST ONLY describe the TARGET company's business, assets, or projects. "
        "NEVER include the sending company's own solution, service, or product (e.g. do NOT include 'seguros', 'pólizas', 'consultoría' if the sender sells insurance) because doing so will return your own competitors instead of your clients.\n"
        "2. 'target_industry_core': The absolute core niche of the TARGET CLIENTS, normalized to a clean English label "
        "(e.g., 'Biotech', 'Fintech Infrastructure', 'Clinical Research Organizations'). "
        "CRITICAL: This describes the CLIENT'S industry, NEVER the sending company's own service category. "
        "If the sender sells logistics/3PL/consulting, do NOT append that service to the core "
        "(use 'Clinical Research & Biopharma', NOT 'Biopharma Logistics').\n"
        "3. 'b2b_buying_trigger_context': A precise translation of what event triggers a sale for the sending company "
        "(e.g., 'A foreign company establishing a local branch', 'A pharma company initiating clinical trials'). "
        "This must be a clear, actionable sentence.\n"
        "4. 'rigorous_pain_framework': A deeply academic explanation of the operational failure the client's targets "
        "suffer from. This is used downstream to evaluate leads and write conversion emails. "
        "Be specific about the business impact (financial, regulatory, operational).\n"
        "5. 'discovery_hq_region': The country/region where the TARGET companies are headquartered (taken from 'País Objetivo'). "
        "This is WHERE to discover the companies.\n"
        "6. 'target_market_region': The EXPANSION/SERVICE market where the buying trigger occurs and where the sending company "
        "delivers its service. If an 'Expansion Target Market' (Mercado Objetivo de Expansión) is provided in the form, USE IT here; "
        "otherwise set it equal to discovery_hq_region. Example: companies headquartered in 'United States' that are expanding into "
        "'Colombia' -> discovery_hq_region='United States', target_market_region='Colombia'.\n"
        "7. 'anti_profile_constraints': A string containing specific exclusion directives based on your ontological analysis "
        "(e.g., 'EXCLUDE any company that provides transportation, logistics, 3PL, 4PL, or freight forwarding services').\n"
        "CRITICAL RULE: The Anti-Profile MUST NEVER include the target industry. If the target industry is Banks and Insurance, "
        "DO NOT exclude banks. The Anti-Profile is STRICTLY for direct competitors of the sending company "
        "(e.g. other IT consultants, RPA agencies), not the target clients. "
        "8. 'dynamic_tavily_queries': An array of EXACTLY 3 highly optimized search strings for Tavily web search. "
        "CRITICAL: Do NOT use generic terms like 'funding round' if the user provides specific 'Triggers de Compra' or 'Keywords de Industria' (e.g., 'licitacion proveedor logistico', 'INVIMA approval', 'supplier RFP'). Use the user's exact triggers. "
        "Angle 1: Focus on the target company's expansion, regulatory approvals (e.g. INVIMA), or new projects in the target market. "
        "Angle 2: Focus on public/private tenders (licitaciones, RFPs) or the specific buying triggers provided. "
        "Angle 3: Focus on operational scaling (hiring, new facilities, supply chain needs) in the target market. "
        "Ensure each query includes the target industry and the relevant geographic market.\n"
        f"Before finalizing, verify that 'anti_profile_constraints' does NOT exclude the target industry ('{form_data.get('sector', '')}'); "
        "if it does, remove that exclusion. When no clear competitor profile exists, return an empty string."
    )
    
    user_prompt = f"""
    Analyze this raw form payload from our B2B prospecting web app:
    - Mi Empresa (Sending Company): {form_data.get('mi_empresa', '')}
    - Sector Objetivo (Target Industry): {form_data.get('sector', '')}
    - País Objetivo (Target Country / HQ): {form_data.get('pais', '')}
    - Mercado Objetivo de Expansión (Expansion Target Market): {form_data.get('mercado_objetivo', '')}
    - Tamaño de Empresa (Company Size): {form_data.get('tamano_empresa', '')}
    - Dolor del Cliente (Client Pain): {form_data.get('dolor_cliente', '')}
    - Propuesta de Valor (Value Proposition): {form_data.get('propuesta_valor', '')}
    - Triggers de Compra (Buying Triggers): {form_data.get('triggers_compra', '')}
    - Keywords de Industria (Industry Keywords): {form_data.get('keywords_industria', '')}
    - Cargo Decisor (Decision-Maker Role): {form_data.get('cargo_decision', '')}
    - Casos de Éxito (Success Cases): {form_data.get('casos_exito', '')}
    """
    
    try:
        # Enforce pacing delay before Groq call
        time.sleep(2.0)
        
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )
        intent = json.loads(response.choices[0].message.content)
        logger.info(f"Strategic Intent extracted successfully: {json.dumps(intent, indent=2, ensure_ascii=False)}")
        return intent
    except Exception as e:
        logger.warning(f"Phase 0 Intent Parser failed ({e}). Using defensive raw fallback.")
        # Fallback defensivo: construye un manifiesto mínimo a partir de los campos crudos
        return {
            "optimized_search_tokens": [
                form_data.get("sector", ""),
                form_data.get("triggers_compra", ""),
                form_data.get("keywords_industria", ""),
                form_data.get("dolor_cliente", "")
            ],
            "target_industry_core": form_data.get("sector", ""),
            "b2b_buying_trigger_context": form_data.get("triggers_compra", "") or "Expansion or operational shift",
            "rigorous_pain_framework": form_data.get("dolor_cliente", ""),
            "discovery_hq_region": form_data.get("pais", "") or "Colombia",
            "target_market_region": (form_data.get("mercado_objetivo") or form_data.get("pais") or "Colombia"),
            "anti_profile_constraints": " ".join(form_data.get("exclusion_list", []))
        }


class CompanyDiscoveryResult(BaseModel):
    companies: list[str] = Field(description="List of real companies fitting the requested criteria parameters (up to the requested limit).")

def discover_companies(industry: str, size: str, country: str, extracted_intent: dict, limit: int = 15) -> list[str]:
    # Grammatical Country Syntax Query Helper
    formatted_country = country.strip()
    country_lower = formatted_country.lower()
    if country_lower in ["global", "world", "internacional", "todos", "any"]:
        formatted_country = "the world operating internationally"
    elif country_lower in ["estados unidos", "usa", "us", "united states"]:
        formatted_country = "the United States"
    elif country_lower in ["colombia", "co"]:
        formatted_country = "Colombia"
    elif country_lower in ["europa", "europe", "eu"]:
        formatted_country = "Europe"

    # Cognitive Query: use Phase 0 intent tokens for precision company discovery
    cognitive_tokens = " ".join([t for t in extracted_intent.get("optimized_search_tokens", []) if t])
    core_industry = extracted_intent.get("target_industry_core", industry)

    # ── Geografía dual: sede (dónde descubrir) vs mercado de expansión (trigger) ──
    # Si el cliente busca empresas con sede en `formatted_country` que se expanden
    # a otro mercado, las consultas combinan ambas geos (caso Elite: sede EE.UU.
    # + expansión a Colombia). Si no hay mercado de expansión distinto, es el flujo normal.
    expansion_market = (extracted_intent.get("target_market_region") or "").strip()
    is_expansion_play = bool(expansion_market) and expansion_market.lower() not in (
        formatted_country.lower(), (country or "").strip().lower(), "", "global",
    )

    # ── FASE 0 Dynamic Queries (2026-08-25) ─────────────────────────────────────
    # Phase 0 (extract_strategic_intent) now produces 'dynamic_tavily_queries':
    # 3 custom search strings built from the user's exact triggers (licitaciones,
    # INVIMA approvals, RFPs, supplier selection, etc.). If present, we use them
    # directly — they are far more precise than the generic hardcoded templates.
    # The fallback (generic signal-first queries) only runs when Phase 0 didn't
    # produce them (e.g. model returned malformed JSON or field is missing).
    dynamic_queries_raw: list = extracted_intent.get("dynamic_tavily_queries", [])
    dynamic_queries_raw = [q for q in dynamic_queries_raw if isinstance(q, str) and q.strip()]

    if dynamic_queries_raw:
        logger.info(
            f"Using {len(dynamic_queries_raw)} DYNAMIC queries from Phase 0 "
            f"(licitaciones/triggers-aware) for '{core_industry}'."
        )
        # Ángulos 1 y 2 con time_range=month (señal reciente exigida).
        # Ángulo 3 sin filtro de fecha como red de recall (evita feast-or-famine).
        discovery_queries = []
        for idx, q in enumerate(dynamic_queries_raw[:3]):
            time_range = "month" if idx < 2 else None
            discovery_queries.append((q, time_range))
    else:
        # ── Fallback: Signal-First hardcoded (conservado de AUDITORÍA #4) ──────
        logger.warning(
            "Phase 0 did not return dynamic_tavily_queries. "
            "Falling back to generic signal-first templates."
        )
        if is_expansion_play:
            logger.info(
                f"Expansion-play discovery (signal-first): "
                f"HQ='{formatted_country}' expandiendo a '{expansion_market}'."
            )
            discovery_queries = [
                (
                    f"{core_industry} company announces expansion OR new office "
                    f"OR new facility in {expansion_market} 2026 {cognitive_tokens}",
                    "month",
                ),
                (
                    f"{core_industry} company funding round OR Series A OR Series B "
                    f"OR Series C 2026 international expansion {cognitive_tokens}",
                    "month",
                ),
                (
                    f"{core_industry} company hiring OR job openings in "
                    f"{expansion_market} {extracted_intent.get('b2b_buying_trigger_context', '')}",
                    None,
                ),
            ]
        else:
            discovery_queries = [
                (
                    f"{core_industry} company announces expansion OR growth OR new investment "
                    f"in {formatted_country} 2026 {cognitive_tokens}",
                    "month",
                ),
                (
                    f"{core_industry} companies news {formatted_country} "
                    f"hiring OR expanding OR funding {cognitive_tokens}",
                    "month",
                ),
                (
                    f"{core_industry} companies {formatted_country} {cognitive_tokens} "
                    f"{extracted_intent.get('b2b_buying_trigger_context', '')}",
                    None,
                ),
            ]
    logger.info(
        f"Discovery queries resolved ({len(discovery_queries)} angles) "
        f"for '{core_industry}'."
    )

    tavily_key: str = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.error("Tavily API key not found.")
        return []

    seen_urls: set[str] = set()
    snippets: list[str] = []
    try:
        with httpx.Client(timeout=20.0) as client:
            for q, time_range in discovery_queries:
                try:
                    search_payload = {"api_key": tavily_key, "query": q, "search_depth": "advanced", "max_results": 10}
                    if time_range:
                        # Tavily filtra server-side por fecha real, más confiable que
                        # pedirle "reciente" solo en el texto de la query.
                        search_payload["time_range"] = time_range
                    response = client.post(
                        "https://api.tavily.com/search",
                        json=search_payload
                    )
                    if response.status_code == 200:
                        results = response.json().get("results", [])
                        for r in results:
                            url = r.get("url") or ""
                            # Deduplicar por URL para no repetir las mismas fuentes entre ángulos
                            if url and url in seen_urls:
                                continue
                            if url:
                                seen_urls.add(url)
                            # Cap por snippet: search_depth="advanced" trae contenido largo;
                            # sin truncar, agregar 3 queries x 10 resultados puede exceder el
                            # límite de payload de Groq (413) — detectado en prueba de fuego 2026-08-25.
                            content = (r.get('content') or r.get('snippet') or "")[:600]
                            snippets.append(f"Title: {r.get('title')}\nContent: {content}")
                    else:
                        logger.error(f"Tavily discovery query failed with status {response.status_code}")
                except Exception as inner:
                    logger.warning(f"Discovery query skipped due to error: {inner}")
                    continue
    except Exception as e:
        logger.error(f"Error calling Tavily Search API: {e}")
        return []

    raw_context = "\n\n".join(snippets)[:16000]  # tope duro adicional de seguridad
    if not raw_context:
        logger.error("No raw context retrieved from Tavily across all discovery angles.")
        return []
    logger.info(f"Discovery aggregated {len(snippets)} unique snippets across {len(discovery_queries)} angles.")

    # Enforce strict pacing delay of 3.0 seconds before Groq call
    logger.info("Enforcing strict 3.0s pacing delay before querying Groq...")
    time.sleep(3.0)

    anti_profile_constraints = extracted_intent.get("anti_profile_constraints", "")
    
    prompt = f"""
    Analyze the following web search results and extract real active company names in {formatted_country} matching:
    - Industry: {core_industry}
    - Size: {size} employees
    - Target Intent/Profile: {cognitive_tokens}
    
    CRITICAL ANTI-PROFILE EXCLUSION:
    {anti_profile_constraints}
    DO NOT extract or list any company that matches this anti-profile.

    Search Results:
    {raw_context}
    
    EXTRACT CRITERIA:
    Prioritize extracting real, active, and verified company names listed or referenced inside the search results snippets that match the requested criteria.
    Extract UP TO {limit} distinct company names (return as many genuine matches as you can find, but never exceed {limit}).
    Prioritize companies that plausibly fall within the requested employee-size band ({size}).
    Do NOT invent, placeholder, or hallucinate company names. Only return company names that actually exist in the search snippets or are highly verified matching targets. Never list fictional companies.

    Return a structured JSON array under the key 'companies'.
    Matches must match the format: {{"companies": ["Company A", "Company B"]}}
    """

    max_retries = 3
    retry_delay = 5.0
    extraction_response = None
    
    for attempt in range(max_retries):
        try:
            # Semilla por intento: un reintento tras 429 debe rotar a OTRA llave del
            # pool, no volver a pedir la misma que acaba de rate-limitear.
            key_seed = industry if attempt == 0 else f"{industry}::retry{attempt}"
            api_key = get_next_groq_key(key_seed)
            groq_client = Groq(api_key=api_key)
            chat_completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional business development validator. You MUST respond with a valid JSON object matching the requested schema."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            extraction_response = chat_completion.choices[0].message.content
            break
        except Exception as e:
            # 413/"too large" no es un rate limit real: reintentar con otra llave no lo
            # arregla (el problema es el tamaño del payload, no la cuota). Detectado en
            # prueba de fuego 2026-08-25 — el SDK de Groq incluye "rate_limit" en el
            # mensaje incluso para errores de tamaño, así que se filtra aparte primero.
            if "413" in str(e) or "too large" in str(e).lower():
                logger.error(f"Payload too large for Groq (no reintentable, revisar tope de contexto): {e}")
                break
            if "429" in str(e) or "rate_limit" in str(e) or "rate limit" in str(e).lower():
                logger.warning(f"Groq Rate Limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2.0
            else:
                logger.error(f"Non-retryable Groq generation error: {e}")
                break

    if not extraction_response:
        logger.error("Failed to extract company names due to Groq rate limits or generation failures.")
        return []

    try:
        # First attempt: strict Pydantic validation
        result = CompanyDiscoveryResult.model_validate_json(extraction_response)
        return result.companies
    except Exception as e:
        logger.warning(f"Standard Pydantic validation failed, executing tolerant dictionary parser fallback: {e}")
        try:
            raw_json = json.loads(extraction_response)
            companies_list = raw_json.get("companies", [])
            extracted_names = []
            for item in companies_list:
                if isinstance(item, dict):
                    # Seek standard company name naming keys
                    name = item.get("name") or item.get("company_name") or item.get("company")
                    if name:
                        extracted_names.append(str(name))
                elif isinstance(item, str):
                    extracted_names.append(item)
            if extracted_names:
                logger.info(f"Tolerant parser successfully recovered {len(extracted_names)} company names: {extracted_names}")
                return extracted_names
        except Exception as inner_err:
            logger.error(f"Tolerant parser failed to parse Groq response JSON: {inner_err}")
            
        logger.error(f"Error validating company name JSON: {e}. Raw response: {extraction_response}")
        return []


def update_server_status(job_id: str, phase: str, percentage: int) -> None:
    """Pipes execution progress status back into the active FastAPI instance state registry dynamically."""
    internal_url: str = os.getenv("INTERNAL_BACKEND_URL", "http://localhost:8000")
    headers = {}
    api_key = os.getenv("GLOVAR_BACKEND_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    try:
         httpx.patch(f"{internal_url}/api/v1/internal/update-job/{job_id}", json={
            "current_phase": phase,
            "progress_percentage": percentage
        }, headers=headers, timeout=2.0)
    except Exception as e:
        logger.debug(f"Failed to pipe status telemetry update to dashboard app: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(description="AI Lead Prospector Engine Main Hub - Discovery First")
    parser.add_argument("--payload_path", required=True)
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--job_id", required=True)
    args = parser.parse_args()

    with open(args.payload_path, "r") as f:
        form_data = json.load(f)

    industry: str = form_data["sector"]
    size: str = form_data["tamano_empresa"]

    # ── AUDITORÍA #7: conectar el slider "Límite de perfiles" (5–25) al cap real ──
    # Antes el descubrimiento estaba fijo en 15–20 y capado a 20 sin importar el slider.
    try:
        limite_perfiles = int(form_data.get("limite_perfiles", 15))
    except (TypeError, ValueError):
        limite_perfiles = 15
    limite_perfiles = max(5, min(25, limite_perfiles))

    # ══════════════════════════════════════════════════════════════════════
    # FASE 0: Pre-flight Cognitive Intent Parser
    # Traduce el formulario crudo en un manifiesto de búsqueda estratégico
    # ══════════════════════════════════════════════════════════════════════
    extracted_intent = extract_strategic_intent(form_data)

    # Enriquecer el runtime context con la intención cognitiva digerida
    enriched_context = dict(form_data)
    enriched_context["extracted_intent"] = extracted_intent

    # Aislamiento por job_id: el contexto de runtime vive bajo .tmp/job_{job_id}/
    # para que corridas concurrentes/sucesivas NO se pisen entre sí (root cause de
    # la contaminación que hacía que una búsqueda heredara el ICP de otra corrida).
    from scripts.runtime_paths import context_path, news_path, leads_path
    with open(context_path(args.job_id), "w") as f:
        json.dump(enriched_context, f, indent=2, ensure_ascii=False)
    logger.info(f"Runtime context (job-isolated) written for job_id={args.job_id}.")

    from supabase import create_client, Client
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    supabase_client = None
    if supabase_url and supabase_key:
        try:
            supabase_client = create_client(supabase_url, supabase_key)
        except Exception as e:
            logger.warning(f"Could not initialize Supabase client for idempotency check: {e}")

    def _settle_credits_reservation(companies_processed: int) -> None:
        """Ajusta la reserva de créditos (creada atómicamente por app.py vía
        reserve_prospecting_credits) al conteo REAL de empresas. Es un UPDATE
        sobre la fila reservada por job_id, NUNCA un INSERT nuevo — evitar
        duplicar el gasto ya reservado. Se llama tanto en las salidas
        tempranas (0 empresas) como al final del descubrimiento."""
        if not supabase_client:
            return
        try:
            supabase_client.table("prospecting_credits_usage").update({
                "companies_processed": companies_processed,
                "credits_consumed": companies_processed,
            }).eq("job_id", args.job_id).execute()
        except Exception as e:
            logger.warning(f"No se pudo ajustar la reserva de créditos (¿migración 003 aplicada?): {e}")

    country: str = form_data.get("pais") or "Colombia"
    discovered_companies: list[str] = discover_companies(industry, size, country, extracted_intent, limit=limite_perfiles)
    if not discovered_companies:
        logger.info("No companies discovered. Pipeline halting gracefully.")
        _settle_credits_reservation(0)  # libera la reserva: no se gastó nada real
        sys.exit(0)

    exclusion_list: list[str] = [name.strip().lower() for name in form_data.get("exclusion_list", [])]
    clean_companies: list[str] = [c for c in discovered_companies if c.strip().lower() not in exclusion_list][:limite_perfiles]  # Cap dinámico = límite de perfiles solicitado por el usuario (5–25)

    if not clean_companies:
        logger.info("All targets matched blacklist exclusion array parameters. Exiting.")
        _settle_credits_reservation(0)  # libera la reserva: no se gastó nada real
        sys.exit(0)

    total_batch: int = len(clean_companies)
    processed_count = 0
    import threading
    lock = threading.Lock()

    # ── Billetera de créditos (ver db/migrations/003_prospecting_credits.sql) ──
    # Ajusta la reserva atómica (creada en app.py) al conteo REAL de empresas
    # que sí van a procesarse — normalmente ≤ el estimado (limite_perfiles) que
    # se usó para reservar, nunca mayor (clean_companies ya está capado).
    _settle_credits_reservation(total_batch)

    def process_company(company: str):
        nonlocal processed_count
        
        # Idempotency Check: Skip processing if the company already has validated leads for this job_id in Supabase
        if supabase_client:
            try:
                res = supabase_client.table("leads").select("id").eq("job_id", args.job_id).eq("empresa", company).execute()
                if res.data:
                    logger.info(f"Idempotency Check: Company '{company}' has already been processed for job_id '{args.job_id}' in Supabase. Skipping.")
                    with lock:
                        processed_count += 1
                        end_weight = int(10 + ((processed_count / total_batch) * 85))
                    update_server_status(args.job_id, f"Skipped target asset (Cached): {company}", end_weight)
                    return
            except Exception as e:
                logger.warning(f"Error checking idempotency for '{company}' via Supabase: {e}. Running normal flow.")

        with lock:
            start_weight = int(10 + ((processed_count / total_batch) * 85))
        update_server_status(args.job_id, f"Processing target asset: {company}", start_weight)
        
        try:
            # Native imports to avoid spawning subprocesses and reloading RAM
            from scripts.news_scraper import fetch_targeted_news
            from scripts.lead_scraper import scrape_linkedin_targets
            from scripts.validator import validate_and_persist
            import asyncio
            
            # 1. News Scraper (Async)
            logger.info(f"Running news scraper natively for company: '{company}'")
            loop_news = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_news)
            news_results = loop_news.run_until_complete(fetch_targeted_news(company, args.job_id))
            loop_news.close()
            
            with open(news_path(args.job_id, company), "w") as f:
                json.dump(news_results, f, indent=2)

            # 2. Lead Scraper (Async) — recibe job_id para leer el contexto aislado
            logger.info(f"Running lead scraper natively for company: '{company}'")
            loop_leads = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_leads)
            leads_results = loop_leads.run_until_complete(scrape_linkedin_targets(company, args.job_id))
            loop_leads.close()
            
            with open(leads_path(args.job_id, company), "w") as f:
                json.dump(leads_results, f, indent=2)

            # 3. Validator (Sync)
            logger.info(f"Running validator and persister natively for company: '{company}'")
            validate_and_persist(company, args.user_id, args.job_id)
            
            # Safe automated staging file cleanup routine (job-isolated paths)
            cleanup_files = [news_path(args.job_id, company), leads_path(args.job_id, company)]
            for file_path in cleanup_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up staging asset: {file_path}")
        except Exception as err:
            logger.error(f"Native module execution failure on company asset pipeline loop ({company}): {err}")
        finally:
            with lock:
                processed_count += 1
                end_weight = int(10 + ((processed_count / total_batch) * 85))
            update_server_status(args.job_id, f"Completed target asset: {company}", end_weight)

    # Parallel Execution: 3 concurrent workers for maximum throughput.
    # Preemption risk is now mitigated by the Supabase idempotency checkpoint above:
    # if Modal restarts the container mid-run, already-processed companies are skipped
    # instantly on resume, preventing duplicate API credit consumption.
    logger.info(f"Initiating concurrent local processing for {total_batch} companies with 3 workers.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(process_company, clean_companies)

if __name__ == "__main__":
    main()