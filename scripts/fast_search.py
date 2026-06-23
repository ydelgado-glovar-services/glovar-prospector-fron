# scripts/fast_search.py
"""
Modo Rápido ("Express") — Glovar Prospector.

Prospección casi instantánea: NO busca noticias ni hace auditoría multi-fase.
Encuentra contactos por cargo + industria + geografía usando un proveedor de datos,
los puntúa por encaje de cargo (role_fit determinista) y persiste en `leads`.

Arquitectura de proveedor intercambiable (resiliente al plan de Apollo):
  1) Apollo People Search (mixed_people/search)  → preferido, emails verificados.
  2) Tavily LinkedIn search                       → fallback siempre disponible.

Se ejecuta DENTRO del proceso FastAPI (sin subprocess ni jobs_status): responde
en segundos. Reutiliza el enriquecimiento, dedup y scoring del pipeline existente.
"""

import os
import sys
import json
import logging
import time
import hashlib

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import httpx
from groq import Groq
from supabase import create_client, Client

from scripts.scoring import deterministic_role_fit, compute_fast_match
from scripts.lead_scraper import (
    get_company_domain,
    enrich_lead_with_hunter,
    execute_deterministic_pattern_fallback,
    deduplicate_leads,
)

logger = logging.getLogger("prospector_fast")

GROQ_MODEL_FAST = os.getenv("GROQ_MODEL_FAST", "meta-llama/llama-4-scout-17b-16e-instruct")

# Mapa tamaño de empresa → mínimo de empleados (las bandas "N+" son un piso).
_SIZE_MIN = {"1-50": 1, "51-200": 51, "201-500": 201, "500+": 500}


def _get_groq_key() -> str | None:
    keys = [os.getenv(f"GROQ_API_KEY_{i}") for i in range(1, 10)]
    keys = [k for k in keys if k]
    if not keys:
        std = os.getenv("GROQ_API_KEY")
        if std:
            keys = [std]
    if not keys:
        return None
    idx = int(time.time() / 60)
    return keys[idx % len(keys)]


def _csv(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def parse_icp_prompt(prompt: str, overrides: dict) -> dict:
    """Convierte la frase en lenguaje natural + campos explícitos en filtros ICP.

    Los campos explícitos del formulario tienen prioridad; la frase los enriquece.
    Si no hay frase, se construye solo con los campos (sin llamar al LLM → instantáneo).
    """
    filters = {"titles": [], "industries": [], "locations": [], "employee_min": None, "keywords": ""}

    # 1) Campos explícitos (prioridad).
    filters["titles"] += _csv(overrides.get("cargo_decision"))
    filters["industries"] += _csv(overrides.get("sector"))
    loc = (overrides.get("mercado_objetivo") or "").strip() or (overrides.get("pais") or "").strip()
    if loc:
        filters["locations"].append(loc)
    size = (overrides.get("tamano_empresa") or "").strip()
    if size in _SIZE_MIN:
        filters["employee_min"] = _SIZE_MIN[size]
    filters["keywords"] = (overrides.get("keywords_industria") or "").strip()

    # 2) Enriquecer con la frase en lenguaje natural (si existe).
    prompt = (prompt or "").strip()
    if prompt:
        key = _get_groq_key()
        if key:
            try:
                client = Groq(api_key=key)
                system = (
                    "You extract B2B Ideal Customer Profile filters from a short natural-language description. "
                    "Return STRICT JSON with keys: titles (array of job titles/roles), industries (array), "
                    "locations (array of countries/cities), employee_min (integer or null), keywords (string). "
                    "Be concise; only include what is clearly stated or strongly implied."
                )
                resp = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                data = json.loads(resp.choices[0].message.content)
                filters["titles"] += _csv(data.get("titles"))
                filters["industries"] += _csv(data.get("industries"))
                filters["locations"] += _csv(data.get("locations"))
                if not filters["employee_min"] and isinstance(data.get("employee_min"), int):
                    filters["employee_min"] = data["employee_min"]
                if data.get("keywords"):
                    filters["keywords"] = (filters["keywords"] + " " + str(data["keywords"])).strip()
            except Exception as e:
                logger.warning(f"[Fast] NL prompt parse failed ({e}); usando solo campos explícitos.")

    # Dedupe preservando orden.
    for k in ("titles", "industries", "locations"):
        seen, out = set(), []
        for v in filters[k]:
            if v.lower() not in seen:
                seen.add(v.lower())
                out.append(v)
        filters[k] = out
    return filters


def apollo_people_search(filters: dict, limit: int) -> list[dict] | None:
    """Busca personas en la base global de Apollo. Devuelve None si el plan no
    permite el endpoint de búsqueda (403/422) o no hay API key."""
    key = os.getenv("APOLLO_API_KEY", "")
    if not key:
        return None

    payload: dict = {"page": 1, "per_page": min(max(limit, 1), 25)}
    if filters["titles"]:
        payload["person_titles"] = filters["titles"]
    if filters["locations"]:
        payload["person_locations"] = filters["locations"]
    if filters["employee_min"]:
        payload["organization_num_employees_ranges"] = [f"{filters['employee_min']},1000000"]
    kw = " ".join([filters.get("keywords", "")] + filters.get("industries", [])).strip()
    if kw:
        payload["q_keywords"] = kw

    headers = {"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": key}
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post("https://api.apollo.io/v1/mixed_people/search", json=payload, headers=headers)
            if resp.status_code in (401, 403, 422):
                logger.warning(f"[Fast] Apollo search no disponible (status {resp.status_code}); usando fallback Tavily.")
                return None
            if resp.status_code != 200:
                logger.warning(f"[Fast] Apollo search status {resp.status_code}; fallback Tavily.")
                return None
            people = resp.json().get("people", []) or []
    except Exception as e:
        logger.warning(f"[Fast] Apollo search error ({e}); fallback Tavily.")
        return None

    leads: list[dict] = []
    for p in people:
        org = p.get("organization") or {}
        email = p.get("email")
        # Apollo enmascara emails no desbloqueados con placeholders.
        if email and ("not_unlocked" in email or "domain.com" in email):
            email = None
        verified = bool(email) and p.get("email_status") in ("verified", "likely to engage")
        leads.append({
            "first_name": p.get("first_name", "") or "",
            "last_name": p.get("last_name", "") or "",
            "title": p.get("title", "") or "",
            "linkedin_url": p.get("linkedin_url", "") or "",
            "company_name": org.get("name", "") or "",
            "email": email,
            "email_source": "apollo" if email else None,
            "email_verified": verified,
        })
    logger.info(f"[Fast] Apollo devolvió {len(leads)} contactos.")
    return leads


def tavily_people_search(filters: dict, limit: int) -> list[dict]:
    """Fallback: busca perfiles de LinkedIn por cargo + ubicación vía Tavily."""
    import re
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.error("[Fast] TAVILY_API_KEY no encontrada.")
        return []

    titles = filters["titles"] or ["decision maker"]
    location = filters["locations"][0] if filters["locations"] else ""
    loc_str = f' "{location}"' if location else ""
    sector = filters["industries"][0] if filters["industries"] else ""

    leads: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(timeout=20.0) as client:
        for title in titles[:4]:
            query = f'site:linkedin.com/in/ "{title}"{loc_str} {sector}'.strip()
            try:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": tavily_key, "query": query, "search_depth": "advanced", "max_results": 8},
                )
                if resp.status_code != 200:
                    continue
                results = resp.json().get("results", [])
            except Exception as e:
                logger.debug(f"[Fast] Tavily query error: {e}")
                continue

            per_title = 0
            for item in results:
                if per_title >= max(2, limit // max(len(titles), 1)):
                    break
                url = (item.get("url") or "").split("?")[0].rstrip("/")
                if "linkedin.com/in/" not in url or url in seen:
                    continue
                seen.add(url)
                raw = item.get("title") or ""
                raw = re.sub(r"\s*[|-]\s*LinkedIn.*$", "", raw, flags=re.IGNORECASE)
                parts = [p.strip() for p in raw.split("-") if p.strip()]
                if not parts:
                    continue
                full_name = parts[0]
                name_parts = full_name.split(" ", 1)
                # Heurística: el último segmento suele ser la empresa.
                company = parts[-1] if len(parts) >= 3 else ""
                role = parts[1] if len(parts) >= 2 else title
                leads.append({
                    "first_name": name_parts[0] or "",
                    "last_name": name_parts[1] if len(name_parts) > 1 else "",
                    "title": role,
                    "linkedin_url": url,
                    "company_name": company,
                    "email": None,
                    "email_source": None,
                    "email_verified": False,
                })
                per_title += 1
    logger.info(f"[Fast] Tavily devolvió {len(leads)} perfiles.")
    return leads


def _enrich_email(lead: dict) -> None:
    """Completa el email del lead (si falta) priorizando Hunter (verificado) y
    cayendo a patrón determinista (no verificado). Solo si hay empresa resoluble."""
    if lead.get("email"):
        return
    company = lead.get("company_name", "")
    if not company:
        return
    full_name = f"{lead.get('first_name','')} {lead.get('last_name','')}".strip()
    if not full_name:
        return
    try:
        domain = get_company_domain(company)
        email = enrich_lead_with_hunter(full_name, domain)
        if email:
            lead["email"] = email
            lead["email_source"] = "hunter"
            lead["email_verified"] = True
            return
        email = execute_deterministic_pattern_fallback(full_name, domain)
        lead["email"] = email
        lead["email_source"] = "pattern_inferred"
        lead["email_verified"] = False
    except Exception as e:
        logger.debug(f"[Fast] Email enrichment skip para {full_name}: {e}")


def run_fast_prospect(form: dict, user_id: str, job_id: str) -> dict:
    """Orquesta el Modo Rápido y persiste en `leads`. Devuelve {source, leads}."""
    supabase: Client = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))

    try:
        limit = int(form.get("limite_perfiles", 15))
    except (TypeError, ValueError):
        limit = 15
    limit = max(5, min(25, limit))

    filters = parse_icp_prompt(form.get("prompt", ""), form)
    target_roles = filters["titles"] or _csv(form.get("cargo_decision"))
    logger.info(f"[Fast] Filtros ICP: {json.dumps(filters, ensure_ascii=False)}")

    # Proveedor intercambiable: Apollo → Tavily.
    leads = apollo_people_search(filters, limit)
    source = "apollo"
    if leads is None:
        leads = tavily_people_search(filters, limit)
        source = "tavily"

    leads = deduplicate_leads(leads)[:limit]

    # Fit firmográfico base: la fuente ya filtró por cargo/industria/geo.
    base_fit = 75 if (filters["industries"] or filters["locations"]) else 60

    persisted: list[dict] = []
    for lead in leads:
        title = lead.get("title", "")
        role_fit = deterministic_role_fit(title, target_roles)
        is_cal = role_fit >= 50
        if is_cal:
            _enrich_email(lead)  # solo enriquecemos a los calificados para mantener la velocidad

        scores = compute_fast_match(base_fit, role_fit, reasons={"mode": "fast", "source": source, "role_title": title})
        full_name = f"{lead.get('first_name','')} {lead.get('last_name','')}".strip() or "Contacto"
        reasoning = (
            f"Modo Rápido ({source}): contacto encontrado por cargo '{title}'. "
            f"Encaje de cargo {role_fit}/100. Sin análisis de señales/noticias (use Modo Profundo para triggers)."
        )
        row = {
            "user_id": user_id,
            "job_id": job_id,
            "nombre_lead": full_name,
            "empresa": lead.get("company_name") or "—",
            "cargo": title,
            "linkedin_url": lead.get("linkedin_url", ""),
            "email": lead.get("email"),
            "email_source": lead.get("email_source"),
            "email_verified": bool(lead.get("email_verified")),
            "url_noticia": None,
            "es_calificado": is_cal,
            "razonamiento_filtro": reasoning,
            "trigger_noticia": None,
            "mensaje_generado": None,
            **scores,
        }
        try:
            resp = supabase.table("leads").insert(row).execute()
            if resp.data:
                persisted.append(resp.data[0])
        except Exception as e:
            logger.error(f"[Fast] Error insertando lead {full_name}: {e}")

    logger.info(f"[Fast] Persistidos {len(persisted)} leads (source={source}).")
    return {"source": source, "leads": persisted}
