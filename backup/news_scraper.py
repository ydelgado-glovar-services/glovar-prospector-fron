# scripts/news_scraper.py
import argparse
import os
import sys
import json
import logging
from typing import List, Dict, Any
import httpx
import asyncio
from dotenv import load_dotenv

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

async def fetch_targeted_news(company_name: str) -> list[dict[str, Any]]:
    api_key: str = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        logger.error("Tavily API key not found.")
        return []
        
    with open(".tmp/active_runtime_context.json", "r") as f:
        context = json.load(f)
        
    import datetime
    current_year = datetime.datetime.now().year
        
    country = context.get("pais") or "Colombia"
    
    # ── Resolución dinámica de límites y velocidad ──
    max_articles = int(context.get("max_news_articles", 3))
    if max_articles <= 1:
        max_news = 1
        max_social = 0
    elif max_articles <= 3:
        max_news = 2
        max_social = 1
    else:
        max_news = 3
        max_social = 2
    
    # Construcción dinámica de términos de búsqueda basada en el formulario del usuario
    triggers_raw = context.get("triggers_compra") or ""
    keywords_raw = context.get("keywords_industria") or ""
    
    triggers_list = [t.strip() for t in triggers_raw.split(",") if t.strip()]
    keywords_list = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    
    search_subqueries = []
    if triggers_list:
        # Agrupar triggers con OR booleano
        search_subqueries.append(f"({' OR '.join(triggers_list)})")
    if keywords_list:
        # Agrupar palabras clave con OR booleano
        search_subqueries.append(f"({' OR '.join(keywords_list)})")
        
    if search_subqueries:
        dynamic_terms = " ".join(search_subqueries)
    else:
        # Fallback genérico dinámico en inglés y español solo en caso extremo de formulario vacío
        dynamic_terms = "(growth OR expansion OR funding OR clinical trials OR expansión OR financiamiento OR operaciones)"
        
    query = f"{company_name} {country} {dynamic_terms} {current_year}"
    logger.info(f"Targeted news discovery query (max_articles={max_articles}): '{query}'")
    
    results = []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "search_depth": "advanced", "max_results": 8 if max_articles > 1 else 3}
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
            else:
                logger.error(f"Tavily search failed with status {response.status_code}")
    except Exception as e:
        logger.error(f"Error during Tavily news discovery: {e}")

    # Filtrar noticias de prensa inmediatamente
    company_lower = company_name.lower()
    selected_news = []
    for r in results:
        title = r.get("title") or ""
        content = r.get("content") or r.get("snippet") or ""
        url = r.get("url") or ""
        if not url:
            continue
        if company_lower in title.lower() or company_lower in content.lower():
            selected_news.append(r)
            if len(selected_news) == max_news:
                break
                
    if len(selected_news) < max_news:
        for r in results:
            url = r.get("url") or ""
            if not url or r in selected_news:
                continue
            selected_news.append(r)
            if len(selected_news) == max_news:
                break
    selected_news = selected_news[:max_news]

    # 2. Búsqueda secundaria dinámica (LinkedIn Posts y Eventos)
    sec_results = []
    # Cortocircuito: si max_articles es 1 y ya tenemos 1 noticia, saltamos la búsqueda social
    if max_articles > 1 or not selected_news:
        secondary_query = f'"{company_name}" (site:linkedin.com/posts OR site:linkedin.com/events OR "webinar" OR "conferencia" OR "evento" OR "exposición") {dynamic_terms} {current_year}'
        logger.info(f"Secondary social/LinkedIn search query: '{secondary_query}'")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                sec_response = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": secondary_query, "search_depth": "advanced", "max_results": 5}
                )
                if sec_response.status_code == 200:
                    sec_results = sec_response.json().get("results", [])
                else:
                    logger.error(f"Secondary Tavily search failed with status {sec_response.status_code}")
        except Exception as e:
            logger.error(f"Error during secondary Tavily search: {e}")

    # Seleccionar posts/eventos de LinkedIn si se realizaron
    selected_social = []
    if sec_results and max_social > 0:
        for r in sec_results:
            title = r.get("title") or ""
            content = r.get("content") or r.get("snippet") or ""
            url = r.get("url") or ""
            if not url:
                continue
            if company_lower in title.lower() or company_lower in content.lower():
                selected_social.append(r)
                if len(selected_social) == max_social:
                    break
                    
        if len(selected_social) < max_social:
            for r in sec_results:
                url = r.get("url") or ""
                if not url or r in selected_social:
                    continue
                selected_social.append(r)
                if len(selected_social) == max_social:
                    break
        selected_social = selected_social[:max_social]

    # Combinamos ambas listas para análisis cruzado en el LLM y limitamos al máximo especificado por el usuario
    selected_items = selected_news + selected_social
    selected_items = selected_items[:max_articles]
    urls: list[str] = [r.get("url") for r in selected_items]
    logger.info(f"Programmatically selected relevant URLs for extraction (News & Social Cross): {urls}")
    
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
    logger.info(f"Successfully cached news context matching form intent elements for {args.company}")