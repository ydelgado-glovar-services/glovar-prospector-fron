# scripts/validator.py
import argparse
import os
import sys
import json
import logging
import time
from pydantic import BaseModel, Field
import httpx
from groq import Groq
import groq
from supabase import create_client, Client
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("prospector_validator")

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

def get_next_groq_key() -> str:
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
    import random
    # Self-healing cross-process file-access rotator logic
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


class BusinessValidationResult(BaseModel):
    is_approved: bool = Field(description="True only if company matches active business criteria and parameters provided.")
    justification: str = Field(description="Brutally detailed fundamental analysis referencing target triggers.")
    subject_line: str = Field(description="Email subject line tailored to the discovered buying match.")
    email_body: str = Field(description="Cold message text structure following the 150-word 4-part guide.")

def get_tavily_factual_context(company_name: str) -> str:
    api_key: str = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.warning("Tavily API key not found. Skipping factual context lookup.")
        return ""
        
    query: str = f'"{company_name}" IT infrastructure software technical challenges systems stack'
    logger.info(f"Retrieving pristine factual context for {company_name} using Tavily Search API...")
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "search_depth": "advanced", "max_results": 5}
            )
            if response.status_code == 200:
                results: list[dict[str, Any]] = response.json().get("results", [])
                snippets: list[str] = [f"Source: {r.get('url')}\nContent: {r.get('content') or r.get('snippet')}" for r in results]
                return "\n\n".join(snippets)
            else:
                logger.error(f"Tavily search failed with status {response.status_code}")
    except Exception as e:
        logger.error(f"Error during Tavily factual search: {e}")
    return ""

def validate_and_persist(company_name: str, user_id: str, job_id: str) -> None:
    with open(f".tmp/news_{company_name}.json", "r") as f:
        news_data = json.load(f)
    with open(f".tmp/leads_{company_name}.json", "r") as f:
        leads_data = json.load(f)
        
    with open(".tmp/active_runtime_context.json", "r") as f:
        form_context = json.load(f)

    supabase: Client = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))

    # Determinar si todos los perfiles extraídos están descalificados o no hay leads
    all_disqualified = True
    if leads_data:
        for lead in leads_data:
            if not lead.get("is_disqualified"):
                all_disqualified = False
                break
    else:
        all_disqualified = True

    if all_disqualified:
        logger.info(f"No active target leads resolved for {company_name}. Disqualifying company by default to maintain clean dashboard.")
        serialized_news = None
        if news_data:
            news_subset = news_data[:2]
            serialized_news = json.dumps([{"title": n.get("title", "Hito de Crecimiento de la Empresa"), "url": n["url"]} for n in news_subset if n.get("url")])
        try:
            supabase.table("leads").insert({
                "user_id": user_id,
                "job_id": job_id,
                "nombre_lead": "Contacto Pendiente",
                "empresa": company_name,
                "cargo": "Prospección Manual Pendiente",
                "linkedin_url": "",
                "email": None,
                "url_noticia": serialized_news,
                "es_calificado": False,
                "razonamiento_filtro": "Descalificado: No se encontraron perfiles decisores de LinkedIn activos de forma automatizada para evaluar preventivamente la cuenta.",
                "trigger_noticia": "Falta de Leads Decisores",
                "mensaje_generado": None
            }).execute()
            logger.info(f"Appended no-leads fallback row successfully for company: {company_name}")
        except Exception as e:
            logger.error(f"Error inserting no-leads fallback lead to Supabase: {e}")
        return

    # Stale 404 snippets or empty news content substance check
    longest_snippet = ""
    for news_item in news_data:
        snippet = news_item.get("snippet") or ""
        if len(snippet) > len(longest_snippet):
            longest_snippet = snippet

    longest_snippet_lower = longest_snippet.lower()
    has_error_strings = any(err in longest_snippet_lower for err in ["404", "429", "rate limit", "error", "not found", "access denied", "forbidden"])

    has_news_trigger = True
    if len(longest_snippet) < 150 or has_error_strings:
        logger.warning(f"Company {company_name} news substance check failed. Longest snippet length: {len(longest_snippet)}, has error strings: {has_error_strings}. Degrading to General Operational Fit Fallback mode.")
        has_news_trigger = False

    factual_context: str = get_tavily_factual_context(company_name)

    for lead in leads_data:
        first_name: str = lead.get("first_name", "").strip()
        last_name: str = lead.get("last_name", "").strip()
        full_name: str = f"{first_name} {last_name}".strip()
        title: str = lead.get("title", "")
        linkedin_url: str = lead.get("linkedin_url", "")

        # Check if lead was pre-disqualified during scraping phase
        if lead.get("is_disqualified"):
            logger.info(f"Lead '{full_name}' pre-disqualified: {lead.get('disqualification_reason')}. Short-circuiting.")
            serialized_news = None
            if news_data:
                news_subset = news_data[:2]
                serialized_news = json.dumps([{"title": n.get("title", "Hito de Crecimiento de la Empresa"), "url": n["url"]} for n in news_subset if n.get("url")])
            try:
                supabase.table("leads").insert({
                    "user_id": user_id,
                    "job_id": job_id,
                    "nombre_lead": full_name,
                    "empresa": company_name,
                    "cargo": title,
                    "linkedin_url": linkedin_url,
                    "email": None, # No contaminar con emails falsos
                    "url_noticia": serialized_news,
                    "es_calificado": False,
                    "razonamiento_filtro": lead.get("disqualification_reason"),
                    "trigger_noticia": lead.get("disqualification_trigger"),
                    "mensaje_generado": None
                }).execute()
                logger.info(f"Appended pre-disqualified row successfully for lead: {full_name}")
            except Exception as e:
                logger.error(f"Error inserting pre-disqualified lead to Supabase: {e}")
            continue

        # Defensive Python validation statement before calling Groq API
        if has_news_trigger:
            company_lower = company_name.lower()
            company_found = False
            for news_item in news_data:
                title_text = (news_item.get("title") or "").lower()
                snippet_text = (news_item.get("snippet") or "").lower()
                if company_lower in title_text or company_lower in snippet_text:
                    company_found = True
                    break
                    
            if not company_found:
                logger.info(f"Trigger flagged as Generic Sector Noise. Short-circuiting Groq call for {company_name}.")
                serialized_news = None
                if news_data:
                    news_subset = news_data[:2]
                    serialized_news = json.dumps([{"title": n.get("title", "Hito de Crecimiento de la Empresa"), "url": n["url"]} for n in news_subset if n.get("url")])
                try:
                    supabase.table("leads").insert({
                        "user_id": user_id,
                        "job_id": job_id,
                        "nombre_lead": full_name,
                        "empresa": company_name,
                        "cargo": title,
                        "linkedin_url": linkedin_url,
                        "email": lead.get("email"),
                        "url_noticia": serialized_news,
                        "es_calificado": False,
                        "razonamiento_filtro": "Descalificado: Las noticias descubiertas son blogs genéricos de la industria y no mencionan directamente a la empresa objetivo",
                        "trigger_noticia": "Ruido Genérico del Sector",
                        "mensaje_generado": None
                    }).execute()
                    logger.info(f"Appended generic noise row successfully for lead: {full_name}")
                except Exception as e:
                    logger.error(f"Error inserting generic noise lead to Supabase: {e}")
                continue
        # scripts/validator.py - Prompts Dinámicos (Con Trigger vs Alineación General Fa        if has_news_trigger:
            prompt_context = f"""
            Analyze the recent news context and technical infrastructure data for the target company: {company_name}.

            ABSOLUTE IDENTITY OF THE LEAD UNDER ANALYSIS:
            - Full Name: '{full_name}'
            - First Name: '{first_name}'
            - Job Title: '{title}'

            You are strictly forbidden from confusing or hallucinating the identity or role of '{full_name}' with third-party executives mentioned in the news snippets.

            Context from our positioning criteria (can be in Spanish, English, or mixed):
            - Sending Company: '{form_context['mi_empresa']}'
            - Value Proposition: '{form_context['propuesta_valor']}'
            - Target Client's Main Pain: '{form_context['dolor_cliente']}'
            - Success Case/Supporting Success History: '{form_context['casos_exito']}'

            Discovered News Context:
            {json.dumps(news_data)}

            Pristine Infrastructure Context (Tavily RAG):
            {factual_context}

            Evaluate if there is an operational technical match or a deductive growth trigger (e.g., funding secured, operations expansion, clinical trial phase II/III start, product launches, automated alliances or high scaling that overburdens critical processes) between this target company and our value proposition.

            TEMPORAL CRITERIA: Reject the company ('is_approved': false) if the news snippets provided describe events, FDA approvals, expansions, or funding rounds that occurred in years prior to 2025. We only target recent 2025 or 2026 milestones. For example, if a snippet cites a 2017 FDA approval or a 2021/2022 series C, reject the lead and explain in the Spanish justification that the news trigger is historical/outdated.

            If approved, write a highly persuasive cold email (maximum 150 words) aligned with our commercial profile.

            GREETING DIRECTIVE:
            The email greeting MUST address the lead using their specific first name: '{first_name}' (e.g., 'Hola {first_name},' or 'Estimado {first_name},'). NEVER introduce names of third-party executives.

            LANGUAGE OF THE OUTPUT:
            The 'justification', 'subject_line', and 'email_body' MUST be generated entirely in professional, fluent, and natural Spanish (Español).

            STRICT ROOT-LEVEL JSON SCHEMA GUARDRAIL:
            You MUST return a raw JSON object containing exactly the following keys directly at the ROOT level. Do NOT wrap the output in container keys like "analysis", "evaluation", or "match". The structure must be completely flat:
            - "is_approved": (boolean) True only if the company matches active sales criteria.
            - "justification": (string) Fundamental analysis structured strictly in three numbered points in Spanish:
              1. EL HECHO NOTICIOSO DETONANTE: Citation of the exact news hito, funding amount, expansion, or clinical trial start.
              2. EL IMPACTO OPERATIVO DEDUCTIVO: In-depth engineering or process explanation of how this growth milestone will stress their operations and exacerbate client pains related to '{form_context['dolor_cliente']}'.
              3. ENCAJE DEL ROL: Direct relation of the lead's role ('{title}') with the preventive responsibility to mitigate this operational pain.
            - "subject_line": (string) Cold email subject line in Spanish. Format: 'Hito/Noticia de Crecimiento de [Empresa Objetivo]: [Acción Preventiva de mitigación del dolor]'.
            - "email_body": (string) Cold email body in Spanish, maximum 150 words, structured in 4 parts. Must start directly with the specific news trigger without conversational filler.
            """

            system_prompt = (
                "You are a highly analytical, strategic, and non-complacent corporate sales auditor. "
                "Your absolute mandate is to default 'is_approved: false' unless there is an explicit technical operational match OR a clear deductive growth synergy based on the target company's hito/scale trigger. "
                "TEMPORAL RELEVANCE REQUIREMENT: The news trigger or growth milestone MUST be recent and strictly belong to the current timeframe (years 2025 or 2026). Check references and dates. If the snippets only describe historical achievements or milestones from previous years (such as FDA approvals in 2017, expansions in 2021, or investments in 2022/2024), you MUST reject the lead by setting 'is_approved': false. Under 'justification', write a polite explanation in Spanish indicating that the news trigger is outdated or obsolete and does not warrant immediate outreach. "
                f"GROWTH DEDUCTION TRAINING: Companies never publish press releases openly declaring their internal operational problems or system failures (e.g., cold chain failures, latency in databases, regulatory non-compliance like INVIMA, technical bottlenecks). Therefore, you must apply professional deductive reasoning: if the news context shows the target company is experiencing rapid growth, expanding operations to new countries/markets (such as Colombia), launching new products, securing funding rounds/credit lines, starting clinical trials, or opening new offices, this will mathematically place immediate pressure on their corresponding critical processes and infrastructure. If you identify such growth milestones and the candidate's role is a valid decision-maker ({form_context.get('cargo_decision', '')}), you MUST approve the lead ('is_approved': true) and write the cold email presenting our value proposition ({form_context.get('propuesta_valor', '')}) as the indispensable preventive solution to support that growth milestone without degrading operations or risking client pains ({form_context.get('dolor_cliente', '')}). "
                f"ELIMINATE GENERICS: The subject line ('subject_line') must NEVER be generic, marketing-heavy, or salesy. It must reference the exact growth trigger milestone. The justification ('justification') MUST be structured in exactly 3 numbered points written in Spanish. The cold email ('email_body') must be peer-to-peer, highly professional, starting directly with the news trigger, and presenting the value proposition in a quantitative way. "
                f"IDENTITY ABSOLUTE DIRECTIVE & ANTI-HALLUCINATION: The professional under analysis is strictly '{full_name}' with the job title '{title}'. You are STRICTLY FORBIDDEN from assuming this professional is the founder, CEO, or anyone else mentioned in the news snippets (e.g. do not confuse Nubank's 'David Vélez' with a different lead under analysis). In the justification and email body, evaluate and address strictly '{full_name}' using their specific first name '{first_name}'. "
                "No flattery, no false matches, and ensure the entire generated output ('justification', 'subject_line', 'email_body') is in perfect, natural, and fluent Spanish."
            )
        else:
            prompt_context = f"""
            Analyze the General Operational Alignment for the target company: {company_name}.

            ABSOLUTE IDENTITY OF THE LEAD UNDER ANALYSIS:
            - Full Name: '{full_name}'
            - First Name: '{first_name}'
            - Job Title: '{title}'

            Context from our positioning criteria (can be in Spanish, English, or mixed):
            - Sending Company: '{form_context['mi_empresa']}'
            - Value Proposition: '{form_context['propuesta_valor']}'
            - Target Client's Main Pain: '{form_context['dolor_cliente']}'
            - Success Case/Supporting Success History: '{form_context['casos_exito']}'

            Pristine Infrastructure Context (Tavily RAG):
            {factual_context}

            Evaluate if the lead's title '{title}' at {company_name} has direct responsibility to mitigate recurring pains of '{form_context['dolor_cliente']}', and if our value proposition '{form_context['propuesta_valor']}' fits their business priorities.

            If approved, write a highly persuasive cold email (maximum 150 words) aligned with our commercial profile.

            GREETING DIRECTIVE:
            The email greeting MUST address the lead using their specific first name: '{first_name}' (e.g., 'Hola {first_name},' or 'Estimado {first_name},').

            LANGUAGE OF THE OUTPUT:
            The 'justification', 'subject_line', and 'email_body' MUST be generated entirely in professional, fluent, and natural Spanish (Español).

            STRICT ROOT-LEVEL JSON SCHEMA GUARDRAIL:
            You MUST return a raw JSON object containing exactly the following keys directly at the ROOT level. The structure must be completely flat:
            - "is_approved": (boolean) True only if the company matches active sales criteria.
            - "justification": (string) Fundamental analysis structured strictly in three numbered points in Spanish:
              1. DOLOR CRÍTICO DE OPERACIÓN: Typical recurring operational pains faced by the role '{title}' at {company_name} regarding '{form_context['dolor_cliente']}'.
              2. IMPACTO OPERATIVO DEDUCTIVO: Technical explanation of how this recurring pain degrades efficiency, safety, scale, or operational costs.
              3. ENCAJE DEL ROL: Why '{full_name}' as '{title}' is the ideal person to preventively solve this pain with our value proposition.
            - "subject_line": (string) Cold email subject line in Spanish. Format: 'Mitigación preventiva de [Dolor Principal] para la operación de [Empresa Objetivo]'.
            - "email_body": (string) Cold email body in Spanish, maximum 150 words, structured in 4 parts. Must start directly with a mention to their role responsibilities without conversational filler.
            """

            system_prompt = (
                "You are a highly analytical, strategic, and non-complacent corporate sales auditor. "
                "Your absolute mandate is to default 'is_approved: false' unless there is a very strong operational role synergy between the lead's job title and our value proposition regarding target pains. "
                f"GENERAL OPERATIONAL FIT TRAINING: In this scenario, we do not have recent news triggers. Therefore, you must evaluate the General Operational Fit: whether the lead's role ({title}) and the target company's business nature ({company_name}) have a direct, mathematical relation with the specific pains we solve ({form_context.get('dolor_cliente', '')}). For example, a CTO, VP of Engineering, Clinical Operations Manager, or Director of Logistics always has the intrinsic responsibility to prevent infrastructure failures, delays, regulatory non-compliance, or system bottlenecks. If the lead's role belongs to the authorized decision-maker roles ({form_context.get('cargo_decision', '')}), you MUST approve the lead ('is_approved': true) and write the cold email presenting our value proposition ({form_context.get('propuesta_valor', '')}) as the ideal preventive pilar to alleviate that recurring pain ({form_context.get('dolor_cliente', '')}). "
                f"ELIMINATE GENERICS: The subject line ('subject_line') must NEVER be generic, marketing-heavy, or salesy. It must focus directly on the specific role pain mitigation. The justification ('justification') MUST be structured in exactly 3 numbered points written in Spanish. The cold email ('email_body') must be peer-to-peer, highly professional, starting directly with the lead's role operational responsibility, and presenting the value proposition in a quantitative way. "
                f"IDENTITY ABSOLUTE DIRECTIVE & ANTI-HALLUCINATION: The professional under analysis is strictly '{full_name}' with the job title '{title}'. Address strictly '{first_name}' in the email using their specific first name. "
                "No flattery, no false matches, and ensure the entire generated output ('justification', 'subject_line', 'email_body') is in perfect, natural, and fluent Spanish."
            )

        # Pacing Audit: Stagger requests dynamically using a random jitter delay to prevent Groq RPM rate limits
        import random
        stagger_delay = 2.0 + random.uniform(0.5, 3.5)
        logger.info(f"Staggering Groq request pacing. Delay: {stagger_delay:.2f} seconds...")
        time.sleep(stagger_delay)

        max_retries: int = 3
        retry_delay: float = 5.0
        response_text = None
        
        for attempt in range(max_retries):
            try:
                api_key = get_next_groq_key()
                groq_client = Groq(api_key=api_key)
                chat_completion = groq_client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": prompt_context
                        }
                    ],
                    response_format={"type": "json_object"}
                )
                response_text = chat_completion.choices[0].message.content
                break
            except groq.RateLimitError as e:
                logger.warning(f"Groq Rate Limit Error (429) hit. Retrying lead {full_name} in {retry_delay}s... (Attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(retry_delay)
                retry_delay *= 2.0
            except Exception as e:
                if "429" in str(e) or "rate_limit" in str(e) or "rate limit" in str(e).lower():
                    logger.warning(f"Rate limit hit (Exception). Retrying lead {full_name} in {retry_delay}s... (Attempt {attempt+1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2.0
                else:
                    logger.error(f"Non-retryable error during content generation via Groq: {e}")
                    break
                    
        if not response_text:
            logger.error(f"Failed to generate evaluation for lead: {full_name} due to rate limits. Skipping.")
            continue

        try:
            raw_json = json.loads(response_text)
            just = raw_json.get("justification")
            if isinstance(just, list):
                raw_json["justification"] = "\n".join(str(item) for item in just)
            
            result = BusinessValidationResult.model_validate(raw_json)

            reasoning = result.justification
            if lead.get("is_human_fallback") and result.is_approved:
                reasoning += "\n\n[FALLBACK MANUAL] Empresa calificada comercialmente por su trigger. No se descubrieron perfiles de LinkedIn decisores activos de forma automatizada. Requiere prospección humana manual."

            serialized_news = None
            if news_data:
                news_subset = news_data if result.is_approved else news_data[:2]
                serialized_news = json.dumps([{"title": n.get("title", "Hito de Crecimiento de la Empresa"), "url": n["url"]} for n in news_subset if n.get("url")])

            supabase.table("leads").insert({
                "user_id": user_id,
                "job_id": job_id,
                "nombre_lead": full_name,
                "empresa": company_name,
                "cargo": title,
                "linkedin_url": linkedin_url,
                "email": lead.get("email"),
                "url_noticia": serialized_news,
                "es_calificado": result.is_approved,
                "razonamiento_filtro": reasoning,
                "trigger_noticia": result.subject_line if result.is_approved else None,
                "mensaje_generado": result.email_body if result.is_approved else None
            }).execute()

            logger.info(f"Appended row successfully for lead: {full_name}")
        except Exception as e:
            logger.error(f"Error executing processing step and writing to cloud: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--job_id", required=True)
    args = parser.parse_args()
    
    validate_and_persist(args.company, args.user_id, args.job_id)