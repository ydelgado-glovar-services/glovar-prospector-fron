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


# ── Pydantic Models ──

class CompanyAuditResult(BaseModel):
    """Fase 1: Auditoría a nivel de empresa/cuenta."""
    is_company_approved: bool = Field(description="True if the company has a valid recent growth trigger (2025/2026).")
    company_justification: str = Field(description="Detailed Spanish justification of why the company is approved or rejected.")
    trigger_summary: str = Field(description="Brief summary of the key growth trigger found, in Spanish.")

class BusinessValidationResult(BaseModel):
    """Fase 2: Validación a nivel de lead individual."""
    is_approved: bool = Field(description="True only if company matches active business criteria and parameters provided.")
    justification: str = Field(description="Brutally detailed fundamental analysis referencing target triggers.")
    subject_line: str = Field(description="Email subject line tailored to the discovered buying match.")
    email_body: str = Field(description="Cold message text structure following the 150-word 4-part guide.")

def get_tavily_factual_context(news_data: list) -> str:
    logger.info("Recycling factual context from previously extracted news data to avoid redundant Tavily Search API calls.")
    if not news_data:
        return ""
    snippets: list[str] = [f"Source: {r.get('url')}\nContent: {r.get('snippet')}" for r in news_data]
    return "\n\n".join(snippets)


def _serialize_news(news_data: list, full: bool = False) -> str | None:
    """Serializa la lista de noticias para persistencia en Supabase."""
    if not news_data:
        return None
    subset = news_data if full else news_data[:2]
    return json.dumps([{"title": n.get("title", "Hito de Crecimiento de la Empresa"), "url": n["url"]} for n in subset if n.get("url")])


def _call_groq_with_retry(system_prompt: str, user_prompt: str, max_retries: int = 3, company_name: str = "") -> str | None:
    """Llama a Groq con rotación de claves y reintentos exponenciales."""
    import random
    
    # Pacing Audit: jitter delay
    stagger_delay = 2.0 + random.uniform(0.5, 3.5)
    logger.info(f"Staggering Groq request pacing. Delay: {stagger_delay:.2f} seconds...")
    time.sleep(stagger_delay)
    
    retry_delay: float = 5.0
    response_text = None
    
    for attempt in range(max_retries):
        try:
            api_key = get_next_groq_key(company_name)
            groq_client = Groq(api_key=api_key)
            chat_completion = groq_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            response_text = chat_completion.choices[0].message.content
            break
        except groq.RateLimitError as e:
            logger.warning(f"Groq Rate Limit Error (429) hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries}): {e}")
            time.sleep(retry_delay)
            retry_delay *= 2.0
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e) or "rate limit" in str(e).lower():
                logger.warning(f"Rate limit hit (Exception). Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(retry_delay)
                retry_delay *= 2.0
            else:
                logger.error(f"Non-retryable error during content generation via Groq: {e}")
                break
    
    return response_text


def _run_company_audit(company_name: str, news_data: list, factual_context: str, form_context: dict) -> CompanyAuditResult | None:
    """FASE 1: Auditoría a nivel de empresa — evalúa si la empresa tiene un hito de crecimiento válido."""
    
    # Extraer intención cognitiva del contexto enriquecido (Fase 0)
    extracted_intent = form_context.get("extracted_intent", {})
    pain_framework = extracted_intent.get("rigorous_pain_framework", form_context.get("dolor_cliente", ""))
    buying_trigger_context = extracted_intent.get("b2b_buying_trigger_context", "")
    anti_profile_constraints = extracted_intent.get("anti_profile_constraints", "")
    target_industry_core = extracted_intent.get("target_industry_core", form_context.get("sector", "su sector"))
    
    system_prompt = (
        "You are a highly analytical corporate strategic auditor. "
        "Your task is to evaluate whether the TARGET COMPANY is a qualified prospect for the sending company's services. "
        "CRITICAL ONTOLOGICAL CHECK (ANTI-PROFILES): "
        f"Apply the following constraints strictly: '{anti_profile_constraints}'. "
        "If the target company semantically matches these constraints (i.e. they are a direct competitor, like an operator logistics 3PL/4PL for a logistics client, or an insurance provider for an insurance client), "
        "you MUST REJECT them immediately in Phase 1, explicitly stating in the justification that they belong to the client's Anti-Profile. "
        "HYBRID DEDUCTIVE AUDIT: Use a two-tier evaluation for non-competitors. "
        "TIER 1 (Approval by Trigger): If the news shows recent (2025/2026) global growth (funding, new products, "
        "international expansion, facility expansions), APPROVE because it creates immediate operational stress and demand. "
        "TIER 2 (Approval by Account Exception - Evergreen Targets): If there are NO recent news, BUT the company matches "
        f"the profile of a massive top-tier enterprise within the '{target_industry_core}' sector (based on 500+ employee size), "
        "you MUST APPROVE the account under the criterion of 'Volumen Operacional Continuo'. "
        "Deduce that these massive companies operate continuously and their baseline demand for the client's services is constant. "
        "REJECT ONLY if the company is an anti-profile, or if it is a small/irrelevant company with no recent growth triggers. "
        "RIGOROUS PAIN EVALUATION: When approving, connect the trigger (or the continuous operational volume) to the following "
        f"operational pain framework: '{pain_framework}'. "
        "Output ALL text fields ('company_justification', 'trigger_summary') in professional, fluent Spanish."
    )
    
    user_prompt = f"""
    Evaluate the following company for growth potential as a prospect:
    
    TARGET COMPANY: {company_name}
    
    SENDING COMPANY CONTEXT:
    - Sending Company: '{form_context.get('mi_empresa', '')}'
    - Value Proposition: '{form_context.get('propuesta_valor', '')}'
    - Target Client's Main Pain: '{form_context.get('dolor_cliente', '')}'
    
    COGNITIVE INTENT CONTEXT (Phase 0 Pre-flight Analysis):
    - What triggers a sale for us: '{buying_trigger_context}'
    - Rigorous Pain Framework: '{pain_framework}'
    
    DISCOVERED NEWS CONTEXT:
    {json.dumps(news_data)}
    
    PRISTINE INFRASTRUCTURE CONTEXT (Tavily RAG):
    {factual_context}
    
    Return a JSON object with exactly these keys at the ROOT level:
    - "is_company_approved": (boolean) True if the company has a valid recent (2025/2026) growth trigger.
    - "company_justification": (string) In Spanish. Detailed explanation of why the company is approved or rejected. If approved, cite the specific growth trigger AND explain how it connects to the operational pain framework. If rejected, explain why the news is insufficient.
    - "trigger_summary": (string) In Spanish. Brief 1-2 sentence summary of the key growth trigger found. If rejected, write "Sin trigger válido reciente."
    """
    
    response_text = _call_groq_with_retry(system_prompt, user_prompt, company_name=company_name)
    if not response_text:
        return None
    
    try:
        raw_json = json.loads(response_text)
        just = raw_json.get("company_justification")
        if isinstance(just, list):
            raw_json["company_justification"] = "\n".join(str(item) for item in just)
        return CompanyAuditResult.model_validate(raw_json)
    except Exception as e:
        logger.error(f"Error parsing company audit response: {e}. Raw: {response_text}")
        return None


def validate_and_persist(company_name: str, user_id: str, job_id: str) -> None:
    with open(f".tmp/news_{company_name}.json", "r") as f:
        news_data = json.load(f)
    with open(f".tmp/leads_{company_name}.json", "r") as f:
        leads_data = json.load(f)
        
    with open(".tmp/active_runtime_context.json", "r") as f:
        form_context = json.load(f)

    supabase: Client = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))

    # ══════════════════════════════════════════════════════════════════════
    # PRE-FILTRO: Verificar calidad de noticias antes de llamar al LLM
    # ══════════════════════════════════════════════════════════════════════
    
    longest_snippet = ""
    for news_item in news_data:
        snippet = news_item.get("snippet") or ""
        if len(snippet) > len(longest_snippet):
            longest_snippet = snippet

    longest_snippet_lower = longest_snippet.lower()
    has_error_strings = any(err in longest_snippet_lower for err in ["404", "429", "rate limit", "error", "not found", "access denied", "forbidden"])

    if len(longest_snippet) < 150 or has_error_strings:
        logger.warning(f"Company {company_name} news substance check failed. Longest snippet length: {len(longest_snippet)}, has error strings: {has_error_strings}. Disqualifying company.")
        serialized_news = _serialize_news(news_data)
        
        # Insertar fila de descalificación por falta de noticias sustanciales
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
                "razonamiento_filtro": "Descalificado: No se encontraron noticias sustanciales recientes (2025/2026) sobre la empresa. Los snippets recuperados están vacíos, contienen errores HTTP, o son demasiado cortos para determinar un hito de crecimiento válido.",
                "trigger_noticia": "Falta de Noticias Sustanciales",
                "mensaje_generado": None
            }).execute()
            logger.info(f"Appended news-substance-failure row for company: {company_name}")
        except Exception as e:
            logger.error(f"Error inserting news-substance-failure lead: {e}")
        return

    # ══════════════════════════════════════════════════════════════════════
    # PRE-FILTRO: Verificar que las noticias mencionan a la empresa
    # ══════════════════════════════════════════════════════════════════════
    
    company_lower = company_name.lower()
    company_found_in_news = False
    for news_item in news_data:
        title_text = (news_item.get("title") or "").lower()
        snippet_text = (news_item.get("snippet") or "").lower()
        if company_lower in title_text or company_lower in snippet_text:
            company_found_in_news = True
            break
    
    if not company_found_in_news:
        logger.info(f"Trigger flagged as Generic Sector Noise for {company_name}. Short-circuiting.")
        serialized_news = _serialize_news(news_data)
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
                "razonamiento_filtro": "Descalificado: Las noticias descubiertas son blogs genéricos de la industria y no mencionan directamente a la empresa objetivo.",
                "trigger_noticia": "Ruido Genérico del Sector",
                "mensaje_generado": None
            }).execute()
            logger.info(f"Appended generic noise row for company: {company_name}")
        except Exception as e:
            logger.error(f"Error inserting generic noise lead: {e}")
        return

    # ══════════════════════════════════════════════════════════════════════
    # FASE 1: AUDITORÍA A NIVEL DE EMPRESA (Company-Level Audit)
    # ══════════════════════════════════════════════════════════════════════
    
    factual_context: str = get_tavily_factual_context(news_data)
    
    logger.info(f"═══ FASE 1: Company-Level Audit for '{company_name}' ═══")
    company_audit = _run_company_audit(company_name, news_data, factual_context, form_context)
    
    if company_audit is None:
        logger.error(f"Company audit LLM call failed for {company_name}. Defaulting to disqualified.")
        serialized_news = _serialize_news(news_data)
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
                "razonamiento_filtro": "Descalificado: Error técnico al evaluar la empresa con el LLM. Se requiere reintento manual.",
                "trigger_noticia": "Error en Auditoría LLM",
                "mensaje_generado": None
            }).execute()
        except Exception as e:
            logger.error(f"Error inserting LLM failure lead: {e}")
        return
    
    # ── Empresa RECHAZADA en Fase 1 → Descalificar toda la cuenta ──
    if not company_audit.is_company_approved:
        logger.info(f"Company '{company_name}' REJECTED in Phase 1. Reason: {company_audit.trigger_summary}")
        serialized_news = _serialize_news(news_data)
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
                "razonamiento_filtro": company_audit.company_justification,
                "trigger_noticia": company_audit.trigger_summary,
                "mensaje_generado": None
            }).execute()
            logger.info(f"Appended Phase 1 rejection row for company: {company_name}")
        except Exception as e:
            logger.error(f"Error inserting Phase 1 rejection: {e}")
        return
    
    # ══════════════════════════════════════════════════════════════════════
    # FASE 2: VALIDACIÓN A NIVEL DE LEAD (Lead-Level Audit)
    # La empresa CALIFICÓ en Fase 1. Ahora evaluamos los leads individuales.
    # ══════════════════════════════════════════════════════════════════════
    
    logger.info(f"═══ FASE 2: Lead-Level Audit for '{company_name}' (APPROVED in Phase 1) ═══")
    
    # Verificar si hay leads activos disponibles
    active_leads = [lead for lead in leads_data if not lead.get("is_disqualified")]
    
    if not active_leads:
        # ── EMPRESA APTA (Sin Lead) ──
        # La empresa calificó pero no hay leads activos de LinkedIn
        logger.info(f"Company '{company_name}' APPROVED but NO active leads found. Marking as EMPRESA APTA.")
        serialized_news = _serialize_news(news_data, full=True)
        fallback_reasoning = company_audit.company_justification + "\n\n[FALLBACK MANUAL] Empresa calificada comercialmente por su trigger. No se descubrieron perfiles de LinkedIn decisores activos de forma automatizada. Requiere prospección humana manual."
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
                "es_calificado": True,  # ← EMPRESA APTA
                "razonamiento_filtro": fallback_reasoning,
                "trigger_noticia": company_audit.trigger_summary,
                "mensaje_generado": None
            }).execute()
            logger.info(f"Appended EMPRESA APTA (sin lead) row for company: {company_name}")
        except Exception as e:
            logger.error(f"Error inserting empresa apta lead: {e}")
        
        # También persistir los leads pre-descalificados del scraper (si los hay)
        for lead in leads_data:
            if lead.get("is_disqualified"):
                first_name = lead.get("first_name", "").strip()
                last_name = lead.get("last_name", "").strip()
                full_name = f"{first_name} {last_name}".strip()
                try:
                    supabase.table("leads").insert({
                        "user_id": user_id,
                        "job_id": job_id,
                        "nombre_lead": full_name,
                        "empresa": company_name,
                        "cargo": lead.get("title", ""),
                        "linkedin_url": lead.get("linkedin_url", ""),
                        "email": None,
                        "url_noticia": _serialize_news(news_data),
                        "es_calificado": False,
                        "razonamiento_filtro": lead.get("disqualification_reason"),
                        "trigger_noticia": lead.get("disqualification_trigger"),
                        "mensaje_generado": None
                    }).execute()
                except Exception as e:
                    logger.error(f"Error inserting pre-disqualified lead: {e}")
        return

    # ── Hay leads activos: evaluar todos en un lote único con el LLM ──
    any_lead_approved = False
    
    logger.info(f"Evaluating {len(active_leads)} active leads in a single batch LLM call...")
    
    leads_batch = []
    for lead in active_leads:
        first_name = lead.get("first_name", "").strip()
        last_name = lead.get("last_name", "").strip()
        full_name = f"{first_name} {last_name}".strip()
        leads_batch.append({
            "linkedin_url": lead.get("linkedin_url", ""),
            "full_name": full_name,
            "first_name": first_name,
            "title": lead.get("title", "")
        })

    prompt_context = f"""
    Analyze the recent pre-approved growth trigger for the target company: {company_name}.
    
    COMPANY AUDIT RESULT (Phase 1 — ALREADY APPROVED):
    The company has been pre-approved with the following growth trigger:
    {company_audit.company_justification}
    Trigger Summary: {company_audit.trigger_summary}

    Context from our commercial positioning criteria:
    - Sending Company: '{form_context['mi_empresa']}'
    - Value Proposition: '{form_context['propuesta_valor']}'
    - Target Client's Main Pain: '{form_context['dolor_cliente']}'
    - Success Case/Supporting Success History: '{form_context['casos_exito']}'

    COGNITIVE INTENT CONTEXT (Phase 0 Pre-flight Analysis):
    - What triggers a sale for us: '{form_context.get('extracted_intent', {}).get('b2b_buying_trigger_context', '')}'
    - Rigorous Pain Framework (Academic Operational Failure Analysis): '{form_context.get('extracted_intent', {}).get('rigorous_pain_framework', '')}'

    ACTIVE CANDIDATES TO EVALUATE:
    {json.dumps(leads_batch, indent=2)}

    YOUR TASK IN PHASE 2 IS:
    Evaluate each candidate's role to see if it is relevant to the sending company's value proposition.
    The role should be a decision-maker or influencer related to: {form_context.get('cargo_decision', '')}.
    If the role is relevant:
    1. Set is_approved to true.
    2. Write a highly persuasive cold email (maximum 150 words) structured in 4 parts, starting directly with the news trigger, addressed strictly to the candidate's first_name.
    3. Generate a subject line: 'Hito/Noticia de Crecimiento de [Empresa]: [Acción Preventiva de mitigación del dolor]'.
    4. Write a Spanish justification structured strictly in three numbered points:
       1. EL HECHO NOTICIOSO DETONANTE: Citation of the exact news hito, funding amount, expansion, or clinical trial start.
       2. EL IMPACTO OPERATIVO DEDUCTIVO: In-depth explanation of how this growth milestone will stress their operations, connecting it DIRECTLY to the Rigorous Pain Framework: '{form_context.get('extracted_intent', {}).get('rigorous_pain_framework', form_context['dolor_cliente'])}'.
       3. ENCAJE DEL ROL: Direct relation of the lead's role ('title') with the preventive responsibility to mitigate this operational pain.
    
    If the role is completely irrelevant (e.g., HR, marketing, design, or unrelated department), set is_approved to false.

    LANGUAGE OF THE OUTPUT:
    All justifications, subject lines, and email bodies MUST be written entirely in professional, fluent, and natural Spanish (Español).

    STRICT JSON SCHEMA GUARDRAIL:
    You MUST return a valid JSON object matching this schema exactly:
    {{
      "evaluations": [
        {{
          "linkedin_url": "linkedin_url_of_the_candidate",
          "is_approved": true,
          "justification": "1. ...\\n2. ...\\n3. ...",
          "subject_line": "...",
          "email_body": "..."
        }}
      ]
    }}
    Ensure the array has exactly one entry for each of the provided candidates.
    Do NOT include any preamble, conversational text, or markdown code blocks (like ```json). Respond with pure raw JSON text only.
    """

    system_prompt = (
        "You are a highly analytical, strategic, and non-complacent corporate sales auditor. "
        "The company has ALREADY been approved in Phase 1 of the audit. "
        "Your task in Phase 2 is to evaluate a batch of LinkedIn candidates at a pre-approved company, "
        "determine if their role fits the target profile, and if so write custom Spanish outreach emails. "
        "When writing emails and justifications, you MUST connect the growth trigger directly to the "
        "Rigorous Pain Framework provided in the context to maximize conversion impact. "
        "Ensure natural Spanish language, exact first name greetings, and compliance with the JSON schema."
    )

    response_text = _call_groq_with_retry(system_prompt, prompt_context, company_name=company_name)
    
    eval_map = {}
    if response_text:
        try:
            raw_json = json.loads(response_text)
            evaluations = raw_json.get("evaluations", [])
            for ev in evaluations:
                url = ev.get("linkedin_url")
                if url:
                    eval_map[url] = ev
        except Exception as e:
            logger.error(f"Error parsing batch LLM evaluations: {e}. Raw response: {response_text}")

    # Procesar cada lead mapeando la respuesta del lote
    for lead in leads_data:
        first_name = lead.get("first_name", "").strip()
        last_name = lead.get("last_name", "").strip()
        full_name = f"{first_name} {last_name}".strip()
        title = lead.get("title", "")
        linkedin_url = lead.get("linkedin_url", "")

        # Si ya estaba pre-descalificado por el scraper
        if lead.get("is_disqualified"):
            logger.info(f"Lead '{full_name}' pre-disqualified: {lead.get('disqualification_reason')}. Short-circuiting.")
            serialized_news = _serialize_news(news_data)
            try:
                supabase.table("leads").insert({
                    "user_id": user_id,
                    "job_id": job_id,
                    "nombre_lead": full_name,
                    "empresa": company_name,
                    "cargo": title,
                    "linkedin_url": linkedin_url,
                    "email": None,
                    "url_noticia": serialized_news,
                    "es_calificado": False,
                    "razonamiento_filtro": lead.get("disqualification_reason"),
                    "trigger_noticia": lead.get("disqualification_trigger"),
                    "mensaje_generado": None
                }).execute()
                logger.info(f"Appended pre-disqualified row for lead: {full_name}")
            except Exception as e:
                logger.error(f"Error inserting pre-disqualified lead: {e}")
            continue

        # Validar usando el mapa de respuesta del lote
        lead_eval = eval_map.get(linkedin_url)
        is_approved = False
        reasoning = "Descalificado: El cargo del lead no se alinea con los roles decisores requeridos."
        subject_line = None
        email_body = None

        if lead_eval:
            is_approved = lead_eval.get("is_approved", False)
            reasoning = lead_eval.get("justification") or "Descalificado por rol."
            subject_line = lead_eval.get("subject_line")
            email_body = lead_eval.get("email_body")
        else:
            logger.warning(f"No batch LLM evaluation found for lead: {full_name}. Defaulting to rejected.")

        try:
            if lead.get("is_human_fallback") and is_approved:
                reasoning += "\n\n[FALLBACK MANUAL] Empresa calificada comercialmente por su trigger. No se descubrieron perfiles de LinkedIn decisores activos de forma automatizada. Requiere prospección humana manual."

            serialized_news = _serialize_news(news_data, full=is_approved)

            supabase.table("leads").insert({
                "user_id": user_id,
                "job_id": job_id,
                "nombre_lead": full_name,
                "empresa": company_name,
                "cargo": title,
                "linkedin_url": linkedin_url,
                "email": lead.get("email"),
                "url_noticia": serialized_news,
                "es_calificado": is_approved,
                "razonamiento_filtro": reasoning,
                "trigger_noticia": subject_line if is_approved else None,
                "mensaje_generado": email_body if is_approved else None
            }).execute()

            if is_approved:
                any_lead_approved = True
            
            logger.info(f"Appended row for lead: {full_name} (approved={is_approved})")
        except Exception as e:
            logger.error(f"Error executing processing step and writing to cloud: {e}")

    # ══════════════════════════════════════════════════════════════════════
    # POST-FASE 2: Si NINGÚN lead fue aprobado pero la empresa SÍ calificó,
    # insertar fila EMPRESA APTA para no perder la empresa valiosa.
    # ══════════════════════════════════════════════════════════════════════
    
    if not any_lead_approved and active_leads:
        logger.info(f"Company '{company_name}' APPROVED in Phase 1 but ALL leads rejected by role in Phase 2. Inserting EMPRESA APTA fallback.")
        serialized_news = _serialize_news(news_data, full=True)
        fallback_reasoning = company_audit.company_justification + "\n\n[EMPRESA APTA - SIN LEAD DECISOR] La empresa fue calificada por su hito de crecimiento, pero ninguno de los perfiles de LinkedIn evaluados tiene un rol decisor relevante para nuestra propuesta de valor. Requiere prospección manual para encontrar al contacto adecuado."
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
                "es_calificado": True,  # ← EMPRESA APTA
                "razonamiento_filtro": fallback_reasoning,
                "trigger_noticia": company_audit.trigger_summary,
                "mensaje_generado": None
            }).execute()
            logger.info(f"Appended EMPRESA APTA (all leads rejected by role) row for company: {company_name}")
        except Exception as e:
            logger.error(f"Error inserting empresa apta fallback: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--job_id", required=True)
    args = parser.parse_args()
    
    validate_and_persist(args.company, args.user_id, args.job_id)