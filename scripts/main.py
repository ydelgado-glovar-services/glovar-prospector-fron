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

# ── AUDITORÍA #8: Modelo Groq configurable por entorno ──────────────────────────
# Por defecto mantiene Llama-4-Scout para no alterar la calidad actual.
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
            model=GROQ_MODEL_REASONING,
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

    # ── AUDITORÍA #4: Descubrimiento multi-ángulo ──────────────────────────────
    if is_expansion_play:
        logger.info(f"Expansion-play discovery: HQ='{formatted_country}' expandiendo a '{expansion_market}'.")
        discovery_queries = [
            # Ángulo 1: empresas (sede en HQ) que se EXPANDEN al mercado objetivo
            f"{core_industry} companies headquartered in {formatted_country} expanding into {expansion_market} {cognitive_tokens}",
            # Ángulo 2: empresas con OPERACIONES/sede en el mercado objetivo
            f"{core_industry} companies with operations or offices in {expansion_market} {cognitive_tokens}",
            # Ángulo 3: trigger de entrada/expansión al mercado objetivo
            f"{core_industry} companies opening operations in {expansion_market} {extracted_intent.get('b2b_buying_trigger_context', '')}",
        ]
    else:
        discovery_queries = [
            # Ángulo 1: directorios / listados de empresas del nicho
            f"list of active {core_industry} companies operating in {formatted_country} with {size} employees {cognitive_tokens}",
            # Ángulo 2: líderes / mayores actores del sector (captura cuentas top)
            f"largest and leading {core_industry} companies in {formatted_country} {cognitive_tokens}",
            # Ángulo 3: orientado a la intención/dolor específico del ICP
            f"{core_industry} companies {formatted_country} {cognitive_tokens} {extracted_intent.get('b2b_buying_trigger_context', '')}",
        ]
    logger.info(f"Multi-angle company discovery ({len(discovery_queries)} queries) for '{core_industry}'.")

    tavily_key: str = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.error("Tavily API key not found.")
        return []

    seen_urls: set[str] = set()
    snippets: list[str] = []
    try:
        with httpx.Client(timeout=20.0) as client:
            for q in discovery_queries:
                try:
                    response = client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": tavily_key, "query": q, "search_depth": "advanced", "max_results": 10}
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
                            snippets.append(f"Title: {r.get('title')}\nContent: {r.get('content') or r.get('snippet')}")
                    else:
                        logger.error(f"Tavily discovery query failed with status {response.status_code}")
                except Exception as inner:
                    logger.warning(f"Discovery query skipped due to error: {inner}")
                    continue
    except Exception as e:
        logger.error(f"Error calling Tavily Search API: {e}")
        return []

    raw_context = "\n\n".join(snippets)
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
            api_key = get_next_groq_key(industry)
            groq_client = Groq(api_key=api_key)
            chat_completion = groq_client.chat.completions.create(
                model=GROQ_MODEL_REASONING,
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
    parser = argparse.ArgumentParser(description="Glovar Lead Prospector Engine Main Hub - Discovery First")
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

    country: str = form_data.get("pais") or "Colombia"
    discovered_companies: list[str] = discover_companies(industry, size, country, extracted_intent, limit=limite_perfiles)
    if not discovered_companies:
        logger.info("No companies discovered. Pipeline halting gracefully.")
        sys.exit(0)
        
    exclusion_list: list[str] = [name.strip().lower() for name in form_data.get("exclusion_list", [])]
    clean_companies: list[str] = [c for c in discovered_companies if c.strip().lower() not in exclusion_list][:limite_perfiles]  # Cap dinámico = límite de perfiles solicitado por el usuario (5–25)
    
    if not clean_companies:
        logger.info("All targets matched blacklist exclusion array parameters. Exiting.")
        sys.exit(0)
        
    total_batch: int = len(clean_companies)
    processed_count = 0
    import threading
    lock = threading.Lock()

    from supabase import create_client, Client
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    supabase_client = None
    if supabase_url and supabase_key:
        try:
            supabase_client = create_client(supabase_url, supabase_key)
        except Exception as e:
            logger.warning(f"Could not initialize Supabase client for idempotency check: {e}")

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