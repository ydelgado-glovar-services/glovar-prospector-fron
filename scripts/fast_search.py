# scripts/fast_search.py
"""
Modo Rápido ("Express") — AI Lead Prospector.

Prospección casi instantánea: NO busca noticias ni hace auditoría multi-fase.
Encuentra contactos por cargo + industria + geografía usando un proveedor de datos,
los puntúa por encaje de cargo (role_fit determinista) y persiste en `leads`.

Proveedor de datos:
  - Tavily LinkedIn search → descubre contactos por cargo + industria + geografía.
Los emails se enriquecen y verifican vía Hunter.io (política "solo correos verídicos").

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


# Variantes de país para el filtro geográfico del Modo Rápido (Tavily no filtra
# duro por país, así que post-filtramos por estas señales en el texto del resultado).
_COUNTRY_HINTS = {
    "colombia": ["colombia", "colombian", "colombiana", "bogota", "bogotá", "medellin",
                 "medellín", "cali", "barranquilla", "cartagena"],
    "mexico": ["mexico", "méxico", "mexican", "mexicana", "cdmx", "guadalajara", "monterrey"],
    "estados unidos": ["united states", "usa", "u.s.", "estados unidos", "american"],
    "united states": ["united states", "usa", "u.s.", "estados unidos", "american"],
    "españa": ["spain", "españa", "espana", "spanish", "madrid", "barcelona"],
    "argentina": ["argentina", "argentinian", "buenos aires"],
    "chile": ["chile", "chilean", "santiago de chile"],
    "peru": ["peru", "perú", "peruvian", "lima"],
}


def _location_hints(location: str) -> list[str]:
    loc = (location or "").strip().lower()
    if not loc:
        return []
    return _COUNTRY_HINTS.get(loc, [loc])


def _location_ok(text: str, hints: list[str]) -> bool:
    if not hints:
        return True
    t = (text or "").lower()
    return any(h in t for h in hints)


def _fast_clean_title(role: str, fallback: str = "") -> str:
    """Normaliza un cargo ruidoso de LinkedIn a un título conciso.
    Toma el primer segmento con sentido (corta en '|'), quita símbolos/emojis
    iniciales y trunca para no guardar headlines de marketing completos."""
    import re
    r = (role or "").strip()
    if not r:
        return fallback
    # Cortar headlines separados por pipes/•/· → quedarnos con el primer bloque.
    r = re.split(r"[|•·]", r)[0].strip()
    # Quitar símbolos/emojis/estrellas al inicio y final.
    r = re.sub(r"^[^A-Za-zÁÉÍÓÚÑáéíóúñ]+", "", r)
    r = r.strip(" -–—·.,").strip()
    if len(r) > 70:
        r = r[:70].rsplit(" ", 1)[0].strip()
    return r or fallback


# Palabras que delatan el inicio de un CARGO pegado al nombre (sin guion separador).
_ROLE_KEYWORDS = [
    "director", "directora", "gerente", "head", "chief", "ceo", "cto", "cfo", "coo",
    "cio", "vp", "vicepresident", "vicepresidente", "jefe", "jefa", "lider", "líder",
    "manager", "responsable", "especialista", "coordinador", "coordinadora",
    "recursos humanos", "gestion humana", "gestión humana", "talento humano",
    "people", "human resources", "hr ",
]


def _fast_split_name_role(raw: str, fallback_title: str = ""):
    """Separa nombre y cargo de un título de LinkedIn ruidoso.
    Maneja el caso sin guion donde el cargo viene pegado (p. ej.
    'Giovanna García Especialista en Recursos Humanos')."""
    import re
    txt = re.sub(r"\s*[|-]\s*LinkedIn.*$", "", raw or "", flags=re.IGNORECASE).strip()
    # Quitar emojis/símbolos decorativos sueltos.
    txt = txt.replace("★", " ").replace("•", " - ").strip()

    parts = [p.strip() for p in txt.split("-") if p.strip()]
    if parts:
        name_candidate = parts[0]
        # Formato típico 'Nombre - Cargo - Empresa': el cargo es el SEGUNDO bloque
        # (no concatenamos el resto para no arrastrar la empresa al cargo).
        role_candidate = parts[1] if len(parts) > 1 else fallback_title
    else:
        name_candidate, role_candidate = txt, fallback_title

    # Si el "nombre" trae un cargo pegado (sin guion), cortarlo en la keyword.
    low = name_candidate.lower()
    cut = None
    for kw in _ROLE_KEYWORDS:
        idx = low.find(kw)
        # Solo si la keyword no está al inicio (debe haber un nombre antes).
        if idx > 2:
            cut = idx if cut is None else min(cut, idx)
    if cut is not None:
        glued_role = name_candidate[cut:].strip()
        name_candidate = name_candidate[:cut].strip(" -·.,")
        if not role_candidate or role_candidate == fallback_title:
            role_candidate = glued_role

    name_parts = name_candidate.split(" ", 1)
    first = name_parts[0] if name_parts else ""
    last = name_parts[1] if len(name_parts) > 1 else ""
    return first, last, _fast_clean_title(role_candidate, fallback_title)


def tavily_people_search(filters: dict, limit: int) -> list[dict]:
    """Fallback: busca perfiles de LinkedIn por cargo + ubicación vía Tavily,
    con post-filtro geográfico (Tavily no filtra duro por país) y limpieza de
    nombre/cargo."""
    import re
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        logger.error("[Fast] TAVILY_API_KEY no encontrada.")
        return []

    titles = filters["titles"] or ["decision maker"]
    location = filters["locations"][0] if filters["locations"] else ""
    loc_str = f' "{location}"' if location else ""
    sector = filters["industries"][0] if filters["industries"] else ""
    geo_hints = _location_hints(location)

    leads: list[dict] = []
    dropped_geo: list[dict] = []
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
                # Heurística empresa: último segmento si el título trae 3+ bloques.
                parts_for_company = [p.strip() for p in re.sub(r"\s*[|-]\s*LinkedIn.*$", "", raw, flags=re.IGNORECASE).split("-") if p.strip()]
                company = parts_for_company[-1] if len(parts_for_company) >= 3 else ""
                first, last, role = _fast_split_name_role(raw, fallback_title=title)
                if not first:
                    continue

                # Post-filtro geográfico: el resultado debe mencionar el país objetivo
                # en el texto (título/contenido/empresa). Tavily no lo garantiza.
                geo_text = f"{raw} {item.get('content','')} {company}"
                lead_row = {
                    "first_name": first,
                    "last_name": last,
                    "title": role,
                    "linkedin_url": url,
                    "company_name": company,
                    "email": None,
                    "email_source": None,
                    "email_verified": False,
                }
                if geo_hints and not _location_ok(geo_text, geo_hints):
                    dropped_geo.append(lead_row)
                    continue
                leads.append(lead_row)
                per_title += 1

    # Si el filtro geográfico dejó la lista vacía (LinkedIn no siempre expone país),
    # usamos los descartados como respaldo para no devolver cero resultados.
    if not leads and dropped_geo:
        logger.info(f"[Fast] Filtro geográfico sin coincidencias explícitas; usando {len(dropped_geo)} resultados de respaldo.")
        leads = dropped_geo[:limit]
    elif dropped_geo:
        logger.info(f"[Fast] Filtro geográfico descartó {len(dropped_geo)} perfiles fuera de '{location}'.")

    logger.info(f"[Fast] Tavily devolvió {len(leads)} perfiles.")
    return leads


def _enrich_email(lead: dict) -> None:
    """Completa el email del lead (si falta) SOLO con un correo verificado por
    Hunter (política "solo correos verídicos"). Si Hunter no lo confirma, el lead
    se deja sin email (no se infieren correos por patrón)."""
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
        if not domain:
            logger.info(f"[Fast] Sin dominio confiable para '{company}'; se omite email de {full_name}.")
            return
        email = enrich_lead_with_hunter(full_name, domain)
        if email:
            lead["email"] = email
            lead["email_source"] = "hunter"
            lead["email_verified"] = True
        else:
            logger.info(f"[Fast] Sin email verídico de Hunter para {full_name}; se deja vacío.")
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

    # Proveedor de datos: Tavily LinkedIn search.
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
