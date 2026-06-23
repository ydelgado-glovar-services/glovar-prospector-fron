# scripts/validator.py
import argparse
import os
import sys

# Asegurar que la raíz del workspace esté en sys.path para importar scripts.* tanto
# cuando se ejecuta nativamente desde main.py como en modo standalone.
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import json
import logging
import time
from pydantic import BaseModel, Field
import httpx
from groq import Groq
import groq
from supabase import create_client, Client
from dotenv import load_dotenv

from scripts.scoring import compute_composite, account_qualifies, disqualified_scores, deterministic_role_fit

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

# ── AUDITORÍA #8: Modelo configurable por entorno ───────────────────────────────
# Permite afinar throughput/costo sin tocar código. Por defecto se mantiene el
# modelo actual (Llama-4-Scout) para no alterar la calidad existente.
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


class CompanyAuditResult(BaseModel):
    """Fase 1: Auditoría a nivel de empresa/cuenta (scoring ICP fit + intent)."""
    is_company_approved: bool = Field(description="True if the account qualifies (driven by ICP fit, not only by news).")
    fit_score: int = Field(default=0, description="0-100. How well the company matches the ICP: industry/sub-niche, size band, geography, and relevance to the client's pain.")
    intent_score: int = Field(default=0, description="0-100. Strength and recency of the buying trigger found in the news. 0 if there is no real recent trigger.")
    size_match: bool = Field(default=True, description="True if the company plausibly fits the requested employee-size band.")
    company_justification: str = Field(description="Detailed Spanish justification of why the company qualifies or not, citing fit and (if any) the trigger.")
    trigger_summary: str = Field(description="Brief summary of the key growth trigger found, in Spanish. If none, state it qualifies by ICP fit.")

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


def _call_groq_with_retry(system_prompt: str, user_prompt: str, max_retries: int = 3, company_name: str = "", temperature: float = 0.1) -> str | None:
    """Llama a Groq con rotación de claves y reintentos exponenciales.

    AUDITORÍA #3 (Determinismo): se fija `temperature` (default 0.1) en TODAS las
    llamadas de calificación (Fase 1 y Fase 2). Antes se omitía y el modelo usaba
    el default alto (~1.0), provocando que la misma empresa se aprobara/rechazara
    de forma distinta entre corridas. Con 0.1 los resultados son reproducibles.
    """
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
                model=GROQ_MODEL_REASONING,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=temperature
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


def _run_company_audit(company_name: str, news_data: list, factual_context: str, form_context: dict, has_recent_trigger: bool = True) -> CompanyAuditResult | None:
    """FASE 1: Auditoría de cuenta con scoring ICP (FIT-FIRST).

    Cambio clave (Auditoría #1, #2, #5): ya NO se exige un trigger de noticias para
    calificar. Se puntúa el FIT con el ICP (industria/sub-nicho, tamaño, geografía,
    dolor) y el INTENT (fuerza/recencia del trigger). Una empresa de alto fit SIN
    noticias recientes sigue calificando (nurture); los anti-perfiles se rechazan.
    """
    
    # Extraer intención cognitiva del contexto enriquecido (Fase 0)
    extracted_intent = form_context.get("extracted_intent", {})
    pain_framework = extracted_intent.get("rigorous_pain_framework", form_context.get("dolor_cliente", ""))
    buying_trigger_context = extracted_intent.get("b2b_buying_trigger_context", "")
    anti_profile_constraints = extracted_intent.get("anti_profile_constraints", "")
    target_industry_core = extracted_intent.get("target_industry_core", form_context.get("sector", "su sector"))
    requested_size = form_context.get("tamano_empresa", "")
    target_region = extracted_intent.get("target_market_region", form_context.get("pais", ""))
    hq_region = extracted_intent.get("discovery_hq_region", form_context.get("pais", ""))
    is_expansion_play = bool((target_region or "").strip()) and (target_region or "").strip().lower() != (hq_region or "").strip().lower()

    # Directiva geográfica: en un "expansion play" (sede en un país, expansión a otro)
    # el fit geográfico NO depende de la sede sino de tener/abrir presencia en el
    # mercado de expansión; la sede extranjera es esperada y NO debe penalizarse.
    if is_expansion_play:
        geo_directive = (
            f"GEOGRAPHIC FIT (expansion play): the company is expected to be headquartered in '{hq_region}'. "
            f"What matters is whether it HAS, or shows concrete signals of OPENING/EXPANDING, operations in the "
            f"target market '{target_region}'. Reward real presence/expansion signals in '{target_region}'; "
            f"do NOT penalize the foreign HQ. A company in '{hq_region}' with NO link to '{target_region}' is a WEAK "
            f"geographic fit for this client."
        )
    else:
        geo_directive = (
            f"GEOGRAPHIC FIT (strict): the company MUST have real, active operations in '{target_region}' "
            f"(a local subsidiary, offices, or a clearly national operation). A foreign/global brand with "
            f"the SAME name but whose operation lives in ANOTHER country (e.g. a Spain- or Bulgaria-based bank, "
            f"or a '.es'/'.bg' entity) is a WEAK/INVALID geographic fit unless it demonstrably operates in "
            f"'{target_region}'. If the target is clearly a foreign entity without local presence in "
            f"'{target_region}', set size_match irrelevant, lower fit_score below 30 and is_company_approved=false."
        )

    trigger_state = (
        "There IS candidate recent news in the context below; evaluate its real strength."
        if has_recent_trigger else
        "There is NO substantial recent news mentioning the company. Set intent_score = 0 and "
        "judge the account ONLY by its ICP FIT using your knowledge of the company's profile."
    )

    system_prompt = (
        "You are a rigorous B2B account-fit auditor producing a numeric ICP score. "
        "You DO NOT require recent news to qualify an account; news only affects the INTENT score. "
        "Score two independent dimensions from 0 to 100:\n"
        "1) fit_score: how well the TARGET COMPANY matches the client's Ideal Customer Profile — "
        f"industry/sub-niche ('{target_industry_core}'), requested employee size band ('{requested_size}'), "
        "geography (per the directive below), and relevance to the client's operational pain. "
        f"{geo_directive} "
        "SIZE RULE: size bands written as 'N+' (e.g. '500+') are a MINIMUM (N or more): a company with 5,000 or "
        "50,000 employees FULLY satisfies '500+'. NEVER penalize a company for being LARGER than the floor. "
        "Set size_match=false (and lower fit_score) ONLY if the company is clearly BELOW the requested floor.\n"
        "2) intent_score: strength and recency of a real buying trigger (funding, expansion, new products, "
        "regulatory shifts, hiring) found in the provided news. If there is no real recent trigger, set it to 0.\n\n"
        f"TRIGGER STATE: {trigger_state}\n\n"
        "CRITICAL ANTI-PROFILE CHECK (do NOT over-apply): "
        f"Apply this anti-profile strictly but narrowly: '{anti_profile_constraints}'. "
        "A target is an Anti-Profile ONLY if its PRIMARY/core business is the SAME service the sending company sells "
        "(i.e. a true direct competitor). "
        f"Operating in the target client industry ('{target_industry_core}') makes a company a CLIENT, NOT a competitor — "
        "you MUST NOT reject it as anti-profile for that reason, and you MUST NOT infer competitor status merely because "
        "it might run internal operations (e.g. a CRO that handles some of its own logistics is still a CLIENT, not a "
        "logistics competitor). Only when a company is a genuine direct competitor, set fit_score below 20 and "
        "is_company_approved=false, stating it belongs to the client's Anti-Profile.\n\n"
        "APPROVAL RULE (fit-first): set is_company_approved=true if the account is a genuine ICP match "
        "(strong fit), EVEN IF intent_score is low. Reject only anti-profiles or low-fit/irrelevant companies. "
        f"When approving, connect the reasoning to the client's pain framework: '{pain_framework}'. "
        "Output 'company_justification' and 'trigger_summary' in professional, fluent Spanish. "
        "If there is no recent trigger but the fit is strong, 'trigger_summary' must state that it qualifies by "
        "ICP fit (sin trigger reciente)."
    )
    
    user_prompt = f"""
    Evaluate the following company as a prospect and produce ICP scores:
    
    TARGET COMPANY: {company_name}
    
    SENDING COMPANY CONTEXT:
    - Sending Company: '{form_context.get('mi_empresa', '')}'
    - Value Proposition: '{form_context.get('propuesta_valor', '')}'
    - Target Client's Main Pain: '{form_context.get('dolor_cliente', '')}'
    - Requested Industry: '{target_industry_core}'
    - Requested Company Size Band: '{requested_size}'
    - Target Region: '{target_region}'
    
    COGNITIVE INTENT CONTEXT (Phase 0 Pre-flight Analysis):
    - What triggers a sale for us: '{buying_trigger_context}'
    - Rigorous Pain Framework: '{pain_framework}'
    
    DISCOVERED NEWS CONTEXT:
    {json.dumps(news_data)}
    
    PRISTINE INFRASTRUCTURE CONTEXT (Tavily RAG):
    {factual_context}
    
    Return a JSON object with exactly these keys at the ROOT level:
    - "is_company_approved": (boolean) True if the account is a genuine ICP match (fit-first; news not required).
    - "fit_score": (integer 0-100) ICP fit as defined above.
    - "intent_score": (integer 0-100) strength/recency of the real buying trigger; 0 if none.
    - "size_match": (boolean) True if the company plausibly fits the requested employee-size band.
    - "company_justification": (string, Spanish) Why it qualifies or not. Cite fit factors and, if any, the trigger and how it connects to the pain framework.
    - "trigger_summary": (string, Spanish) 1-2 sentences on the key trigger; if none, say it qualifies by ICP fit (sin trigger reciente).
    """
    
    response_text = _call_groq_with_retry(system_prompt, user_prompt, company_name=company_name)
    if not response_text:
        return None
    
    try:
        raw_json = json.loads(response_text)
        just = raw_json.get("company_justification")
        if isinstance(just, list):
            raw_json["company_justification"] = "\n".join(str(item) for item in just)
        # Si no hay trigger reciente, forzar intent_score = 0 (consistencia determinista).
        if not has_recent_trigger:
            raw_json["intent_score"] = 0
        audit = CompanyAuditResult.model_validate(raw_json)
        # Recalcular la aprobación con la regla fit-first determinista (no confiar
        # ciegamente en el booleano del LLM): aprueba por fit, rechaza anti-perfiles.
        audit.is_company_approved = account_qualifies(audit.fit_score, has_recent_trigger)
        return audit
    except Exception as e:
        logger.error(f"Error parsing company audit response: {e}. Raw: {response_text}")
        return None


def validate_and_persist(company_name: str, user_id: str, job_id: str) -> None:
    from scripts.runtime_paths import context_path, news_path, leads_path
    with open(news_path(job_id, company_name), "r") as f:
        news_data = json.load(f)
    with open(leads_path(job_id, company_name), "r") as f:
        leads_data = json.load(f)

    with open(context_path(job_id), "r") as f:
        form_context = json.load(f)

    supabase: Client = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))

    # ══════════════════════════════════════════════════════════════════════
    # PRE-FILTRO (NO bloqueante) — Auditoría #1: FIT-FIRST
    # Antes esto descartaba la empresa por falta de noticias. Ahora SOLO determina
    # si existe un trigger reciente real (intent). La calificación la decide el FIT
    # en la Fase 1, de modo que un buen prospecto sin prensa NO se pierde.
    # ══════════════════════════════════════════════════════════════════════

    longest_snippet = ""
    for news_item in news_data:
        snippet = news_item.get("snippet") or ""
        if len(snippet) > len(longest_snippet):
            longest_snippet = snippet

    longest_snippet_lower = longest_snippet.lower()
    has_error_strings = any(err in longest_snippet_lower for err in ["404", "429", "rate limit", "error", "not found", "access denied", "forbidden"])
    news_substance_ok = len(longest_snippet) >= 150 and not has_error_strings

    # ¿Las noticias mencionan realmente a la empresa? (evita ruido genérico del sector)
    company_lower = company_name.lower()
    company_found_in_news = False
    for news_item in news_data:
        title_text = (news_item.get("title") or "").lower()
        snippet_text = (news_item.get("snippet") or "").lower()
        if company_lower in title_text or company_lower in snippet_text:
            company_found_in_news = True
            break

    # Hay trigger reciente SOLO si las noticias son sustanciales Y mencionan a la empresa.
    has_recent_trigger = news_substance_ok and company_found_in_news
    if not has_recent_trigger:
        logger.info(
            f"No substantial recent trigger for '{company_name}' "
            f"(substance_ok={news_substance_ok}, mentioned={company_found_in_news}). "
            f"Proceeding FIT-FIRST: ICP fit will decide qualification (intent=0)."
        )

    # ══════════════════════════════════════════════════════════════════════
    # FASE 1: AUDITORÍA A NIVEL DE EMPRESA (Company-Level Audit)
    # ══════════════════════════════════════════════════════════════════════
    
    factual_context: str = get_tavily_factual_context(news_data)
    
    logger.info(f"═══ FASE 1: Company-Level Audit for '{company_name}' (trigger_reciente={has_recent_trigger}) ═══")
    company_audit = _run_company_audit(company_name, news_data, factual_context, form_context, has_recent_trigger=has_recent_trigger)
    
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

    # Scoring de cuenta (Fase 1): fit + intent → se reutiliza en todos los inserts.
    account_fit = company_audit.fit_score
    account_intent = company_audit.intent_score
    account_reasons = {
        "trigger_summary": company_audit.trigger_summary,
        "size_match": company_audit.size_match,
        "has_recent_trigger": has_recent_trigger,
    }

    # ── Empresa RECHAZADA en Fase 1 (bajo fit / anti-perfil) → Descalificar cuenta ──
    if not company_audit.is_company_approved:
        logger.info(f"Company '{company_name}' REJECTED in Phase 1 (fit={account_fit}). Reason: {company_audit.trigger_summary}")
        serialized_news = _serialize_news(news_data)
        account_scores = disqualified_scores(account_fit, account_intent, reasons=account_reasons)
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
                "mensaje_generado": None,
                **account_scores,
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
                "mensaje_generado": None,
                **compute_composite(account_fit, account_intent, role_fit=None, reasons=account_reasons),
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

    trigger_directive = (
        "The company has a REAL recent buying trigger. Start the email directly with that news trigger."
        if has_recent_trigger else
        "There is NO recent news trigger; the account qualifies by ICP FIT. Do NOT invent or fabricate any news. "
        "Open the email with the prospect's operational context/pain and the value proposition instead of a fake news hito."
    )

    prompt_context = f"""
    Analyze the pre-approved target company: {company_name}.
    
    COMPANY AUDIT RESULT (Phase 1 — ALREADY APPROVED, fit-first):
    {company_audit.company_justification}
    Trigger Summary: {company_audit.trigger_summary}
    Account ICP fit_score: {company_audit.fit_score}/100 · intent_score: {company_audit.intent_score}/100
    TRIGGER DIRECTIVE: {trigger_directive}

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
    Evaluate each candidate's role relevance to the sending company's value proposition.
    The role should be a decision-maker or influencer related to: {form_context.get('cargo_decision', '')}.
    For EACH candidate, also assign a "role_fit_score" (integer 0-100) reflecting how well their seniority and
    decision power match the target role (a perfect C-level/VP decision-maker ≈ 90-100; tangential influencer ≈ 50-70;
    irrelevant ≈ 0-30).
    If the role is relevant (role_fit_score >= 50):
    1. Set is_approved to true.
    2. Write a highly persuasive cold email (maximum 150 words) structured in 4 parts, following the TRIGGER DIRECTIVE above, addressed strictly to the candidate's first_name.
    3. Generate a subject line tailored to the buying match (use the growth hito if it exists; otherwise focus on the operational pain/value).
    4. Write a Spanish justification structured strictly in three numbered points:
       1. EL DETONANTE: the news hito if it exists; otherwise the ICP fit reason (operational context).
       2. EL IMPACTO OPERATIVO DEDUCTIVO: how this stresses their operations, connecting DIRECTLY to the Rigorous Pain Framework: '{form_context.get('extracted_intent', {}).get('rigorous_pain_framework', form_context['dolor_cliente'])}'.
       3. ENCAJE DEL ROL: relation of the lead's role ('title') with the responsibility to mitigate this operational pain.
    
    If the role is irrelevant (e.g., HR, marketing, design, unrelated department), set is_approved to false and role_fit_score below 40.

    LANGUAGE OF THE OUTPUT:
    All justifications, subject lines, and email bodies MUST be written entirely in professional, fluent, and natural Spanish (Español).

    STRICT JSON SCHEMA GUARDRAIL:
    You MUST return a valid JSON object matching this schema exactly:
    {{
      "evaluations": [
        {{
          "linkedin_url": "linkedin_url_of_the_candidate",
          "is_approved": true,
          "role_fit_score": 85,
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
        role_fit = 0

        if lead_eval:
            is_approved = lead_eval.get("is_approved", False)
            reasoning = lead_eval.get("justification") or "Descalificado por rol."
            subject_line = lead_eval.get("subject_line")
            email_body = lead_eval.get("email_body")
            role_fit = lead_eval.get("role_fit_score", 70 if is_approved else 0)
        else:
            logger.warning(f"No batch LLM evaluation found for lead: {full_name}. Defaulting to rejected.")

        # PISO DETERMINISTA de role_fit (Issue 2): un cargo decisor reconocido
        # (Director, CIO/CTO/CxO, VP, Gerente, Head...) nunca queda por debajo de su
        # piso por reglas, sin importar el ruido del contexto o de la noticia.
        target_roles_ctx = [r.strip() for r in (form_context.get("cargo_decision", "") or "").split(",") if r.strip()]
        rule_role_fit = deterministic_role_fit(title, target_roles_ctx)
        role_fit = max(int(role_fit or 0), rule_role_fit)

        try:
            if lead.get("is_human_fallback") and is_approved:
                reasoning += "\n\n[FALLBACK MANUAL] Empresa calificada comercialmente por su trigger. No se descubrieron perfiles de LinkedIn decisores activos de forma automatizada. Requiere prospección humana manual."

            serialized_news = _serialize_news(news_data, full=is_approved)

            # Scoring compuesto del lead (fit + intent de cuenta + role_fit del contacto).
            # Solo se puntúan los leads aprobados; los rechazados quedan con match_score=0 (default).
            if is_approved:
                lead_scores = compute_composite(
                    account_fit, account_intent, role_fit=role_fit,
                    reasons={**account_reasons, "role_title": title},
                )
            else:
                lead_scores = {}

            supabase.table("leads").insert({
                "user_id": user_id,
                "job_id": job_id,
                "nombre_lead": full_name,
                "empresa": company_name,
                "cargo": title,
                "linkedin_url": linkedin_url,
                "email": lead.get("email"),
                "email_source": lead.get("email_source"),
                "email_verified": lead.get("email_verified", False),
                "url_noticia": serialized_news,
                "es_calificado": is_approved,
                "razonamiento_filtro": reasoning,
                "trigger_noticia": subject_line if is_approved else None,
                "mensaje_generado": email_body if is_approved else None,
                **lead_scores,
            }).execute()

            if is_approved:
                any_lead_approved = True
            
            logger.info(f"Appended row for lead: {full_name} (approved={is_approved}, match={lead_scores.get('match_score', 0)})")
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
                "mensaje_generado": None,
                **compute_composite(account_fit, account_intent, role_fit=None, reasons=account_reasons),
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