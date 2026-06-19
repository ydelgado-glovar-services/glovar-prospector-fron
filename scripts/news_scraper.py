# scripts/news_scraper.py
import argparse
import os
import sys
import json
import logging
import re
from typing import Any
import httpx
import asyncio
import time
import hashlib
from dotenv import load_dotenv
from groq import Groq

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("prospector_news")

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()


async def _tavily_search(api_key: str, query: str, max_results: int = 5, label: str = "search") -> list[dict]:
    """Ejecuta una búsqueda individual en Tavily y retorna los resultados."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "time_range": "year"
                }
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                logger.info(f"[{label}] Query: '{query[:120]}...' → {len(results)} results")
                return results
            else:
                logger.error(f"[{label}] Tavily search failed with status {response.status_code}")
                return []
    except Exception as e:
        logger.error(f"[{label}] Error during Tavily search: {e}")
        return []


def _is_company_mentioned(company_name: str, text: str) -> bool:
    """Verifica si el nombre de la empresa está mencionado en el texto de manera robusta.
    Usa límites de palabra para evitar falsos positivos por substrings (ej. 'alianza' en 'alianzas').
    """
    if not company_name or not text:
        return False

    def normalize(t: str) -> str:
        t = t.lower()
        t = re.sub(r'[áäâà]', 'a', t)
        t = re.sub(r'[éëêè]', 'e', t)
        t = re.sub(r'[íïîì]', 'i', t)
        t = re.sub(r'[óöôò]', 'o', t)
        t = re.sub(r'[úüûù]', 'u', t)
        t = re.sub(r'[ñ]', 'n', t)
        return t

    comp_norm = normalize(company_name)
    text_norm = normalize(text)

    pattern_str = rf"\b{re.escape(comp_norm)}\b"
    try:
        return bool(re.search(pattern_str, text_norm))
    except Exception:
        return comp_norm in text_norm

def _get_next_groq_key_news(company_name: str = "") -> str:
    """Rotador determinista y sin estado de claves Groq para news_scraper."""
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
        raise ValueError("No Groq API keys found in environment variables.")
    if not company_name:
        current_index = int(time.time() / 60)
    else:
        current_index = int(hashlib.md5(company_name.encode('utf-8')).hexdigest(), 16)
    return keys[current_index % len(keys)]


async def generate_human_search_plan(company_name: str, extracted_intent: dict) -> dict:
    """
    Cognitive Query Planner: Simula a un investigador humano que planifica
    3 consultas quirúrgicas y totalmente diferentes para Tavily basadas en
    el ICP (Ideal Customer Profile) del cliente.

    Los 3 ángulos humanos:
    1. Expansión física/corporativa (nuevas oficinas, contrataciones, inversiones)
    2. Fricción operativa/Dolores sectoriales (regulación, compliance, cadena de suministro)
    3. Relaciones Públicas/Social (eventos, webinars, conferencias, LinkedIn)
    """
    target_market = extracted_intent.get("target_market_region", "Colombia and LATAM")

    system_prompt = (
        "You are a human corporate intelligence researcher.\n"
        "Your goal is to find buying triggers and news for a target company.\n"
        "Instead of writing one giant search query, you must generate exactly 3 distinct, "
        "highly targeted, non-redundant search queries optimized for search engines.\n\n"
        "CRITICAL RULES:\n"
        "- Query 1 (Expansion): Focus on the company's regional expansion, new branches, hiring, "
        "investments, or new local operations in the target market.\n"
        "- Query 2 (Pain/Regulatory): Focus on the industry problems, compliance challenges, "
        "or operational stressors they face in the target market.\n"
        "- Query 3 (Social/PR): Focus on their local events, key executive announcements, "
        "webinars, or conference participations in the target region.\n"
        "- Each query MUST include the company name in double quotes.\n"
        "- Do NOT use date strings like '2025' or '2026'. Keep them clean.\n"
        "- Keep queries concise (under 120 characters each).\n\n"
        "You MUST respond with a strict JSON object matching this schema directly at the root level:\n"
        "{\n"
        "  \"expansion_query\": \"string\",\n"
        "  \"pain_query\": \"string\",\n"
        "  \"social_query\": \"string\"\n"
        "}"
    )

    user_prompt = f"""
    Target Company to investigate: "{company_name}"
    Target Market Region: {target_market}

    Our Strategic Search Intent Context:
    - Core Industry Focus: {extracted_intent.get('target_industry_core', 'General')}
    - What triggers a sale for us: {extracted_intent.get('b2b_buying_trigger_context', 'Expansion or operational shift')}
    - The exact pain we track: {extracted_intent.get('rigorous_pain_framework', 'Operational inefficiency')}
    """

    try:
        api_key = _get_next_groq_key_news(company_name)
        client = Groq(api_key=api_key)

        time.sleep(2.0)  # Pacing delay

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )
        plan = json.loads(response.choices[0].message.content)
        logger.info(f"Cognitive Search Plan generated for '{company_name}': {json.dumps(plan, indent=2)}")
        return plan
    except Exception as e:
        logger.warning(f"Cognitive Query Planner failed for '{company_name}' ({e}). Using deterministic fallback.")
        return {
            "expansion_query": f'"{company_name}" ({target_market}) expansion operations',
            "pain_query": f'"{company_name}" compliance regulatory challenges',
            "social_query": f'"{company_name}" (webinar OR evento OR conferencia)'
        }


async def fetch_targeted_news(company_name: str) -> list[dict[str, Any]]:
    api_key: str = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.error("Tavily API key not found.")
        return []

    with open(".tmp/active_runtime_context.json", "r") as f:
        context = json.load(f)

    # ── Resolución dinámica de límites de artículos ──
    max_articles = int(context.get("max_news_articles", 3))

    # ══════════════════════════════════════════════════════════════════════
    # COGNITIVE QUERY PLANNER: Genera 3 consultas multi-ángulo con el LLM
    # Ángulo #1: Expansión corporativa en el mercado objetivo
    # Ángulo #2: Dolor operativo / fricción regulatoria
    # Ángulo #3: Social/PR (eventos, webinars, LinkedIn)
    # ══════════════════════════════════════════════════════════════════════
    extracted_intent = context.get("extracted_intent", {})

    search_tasks: dict = {}

    search_plan = await generate_human_search_plan(company_name, extracted_intent)
    logger.info(f"Cognitive Search Plan activated for '{company_name}'")

    search_tasks["EXPANSION"] = _tavily_search(
        api_key, search_plan["expansion_query"],
        max_results=5, label="EXPANSION"
    )
    search_tasks["PAIN_REGULATORY"] = _tavily_search(
        api_key, search_plan["pain_query"],
        max_results=5, label="PAIN_REGULATORY"
    )
    search_tasks["SOCIAL"] = _tavily_search(
        api_key, search_plan["social_query"],
        max_results=4, label="SOCIAL"
    )

    # ── Ejecutar TODAS las consultas en paralelo ──
    logger.info(f"Launching {len(search_tasks)} parallel cognitive search queries for '{company_name}'...")
    task_keys = list(search_tasks.keys())
    task_outputs = await asyncio.gather(*search_tasks.values())
    results_map = dict(zip(task_keys, task_outputs))

    # ── Consolidar y deduplicar por URL ──
    seen_urls: set[str] = set()
    all_results: list[dict] = []
    for result_list in results_map.values():
        for r in result_list:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    logger.info(f"Total deduplicated results across all cognitive search layers: {len(all_results)}")

    # ── Seleccionar los mejores resultados priorizando menciones directas de la empresa ──
    selected_items: list[dict] = []

    for r in all_results:
        title = r.get("title") or ""
        content = r.get("content") or r.get("snippet") or ""
        url = r.get("url") or ""
        if not url:
            continue
        if _is_company_mentioned(company_name, title) or _is_company_mentioned(company_name, content):
            selected_items.append(r)
            if len(selected_items) == max_articles:
                break

    # Completar con resultados restantes si no se alcanzó el máximo
    if len(selected_items) < max_articles:
        for r in all_results:
            url = r.get("url") or ""
            if not url or r in selected_items:
                continue
            selected_items.append(r)
            if len(selected_items) == max_articles:
                break

    selected_items = selected_items[:max_articles]

    urls: list[str] = [r.get("url") for r in selected_items]
    logger.info(f"Selected URLs for Tavily extraction: {urls}")

    extracted_content_map: dict[str, str] = {}
    if api_key and urls:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                extract_response = await client.post(
                    "https://api.tavily.com/extract",
                    json={"api_key": api_key, "urls": urls}
                )
                if extract_response.status_code == 200:
                    extract_data = extract_response.json()
                    results_extract = extract_data.get("results", [])
                    for res in results_extract:
                        extracted_content_map[res.get("url", "")] = res.get("content", "")
                    logger.info(f"Successfully extracted {len(extracted_content_map)} articles using Tavily Extract.")
                else:
                    logger.warning(f"Tavily Extract API returned bad status code: {extract_response.status_code}")
        except Exception as e:
            logger.error(f"Error calling Tavily Extract API: {e}")

    final_news: list[dict[str, Any]] = []
    for r in selected_items:
        url = r.get("url")
        title = r.get("title") or "Hito de Crecimiento de la Empresa"
        fallback_snippet = r.get("content") or r.get("snippet") or ""
        snippet: str = extracted_content_map.get(url) or fallback_snippet
        snippet = snippet[:1500] if snippet else ""
        final_news.append({
            "title": title,
            "url": url,
            "snippet": snippet
        })

    return final_news

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    args = parser.parse_args()

    news = asyncio.run(fetch_targeted_news(args.company))
    os.makedirs(".tmp", exist_ok=True)
    with open(f".tmp/news_{args.company}.json", "w") as f:
        json.dump(news, f, indent=2)
    logger.info(f"Successfully cached cognitive news context for {args.company}")