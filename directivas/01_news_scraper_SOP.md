# DIRECTIVA: COGNITIVE_MULTI_ANGLE_NEWS_SCRAPER_SOP

> **ID:** SOP-NEWS-001
> **Script Asociado:** `scripts/news_scraper.py`
> **Última Actualización:** 2026-06-01
> **Estado:** ACTIVO

## 1. Objetivos y Alcance
- **Objetivo Principal:** Extraer noticias altamente relevantes sobre la empresa objetivo utilizando la intención cognitiva generada en Fase 0 (`extracted_intent`) para construir 3 consultas multi-ángulo quirúrgicas, eliminando por completo la dependencia de diccionarios estáticos, clasificadores de keywords y reglas rígidas de triggers.
- **Arquitectura de Búsqueda — Cognitive Query Planner:**
  1. **Pre-requisito: Manifiesto Cognitivo (Fase 0):** El script lee la clave `"extracted_intent"` del runtime context (`.tmp/active_runtime_context.json`), generada por el Pre-flight Intent Parser en `main.py`. Contiene: `target_industry_core`, `b2b_buying_trigger_context`, `rigorous_pain_framework`, `target_market_region`, `optimized_search_tokens`.
  2. **Generador de Plan de Búsqueda Humana (`generate_human_search_plan`):** Invoca al LLM (`meta-llama/llama-4-scout-17b-16e-instruct`) para que actúe como un investigador humano y diseñe **3 consultas quirúrgicas y no-redundantes** basadas en el ICP (Ideal Customer Profile) del cliente:
     - **EXPANSION** (Ángulo #1): Expansión física/corporativa, nuevas oficinas, contrataciones, inversiones en el mercado objetivo.
     - **PAIN_REGULATORY** (Ángulo #2): Fricción operativa, compliance, regulaciones, dolores sectoriales en el mercado objetivo.
     - **SOCIAL** (Ángulo #3): Relaciones públicas, eventos, webinars, conferencias, anuncios de ejecutivos en el mercado objetivo.
  3. **Ejecución Paralela (asyncio.gather):** Las 3 consultas cognitivas se ejecutan en paralelo con `asyncio.gather`.
  4. **Consolidación y Deduplicación:** Los resultados se consolidan deduplicando por URL. Se priorizan las que mencionan directamente a la empresa objetivo mediante regex robusta (`\bcompany\b`) insensible a acentos.
  5. **Tavily Content Extraction API (`/extract`):** Las URLs seleccionadas se envían a Tavily para limpiar anuncios, menús de navegación y cookies, retornando el texto limpio del artículo.
- **Criterio de Éxito:** Devuelve un JSON cacheado en `.tmp/news_{company_name}.json` con hasta `max_news_articles` objetos (`title`, `url`, `snippet`).

## 2. Especificaciones de Entrada/Salida (I/O)
### Entradas (Inputs)
- **Argumentos Requeridos:** `--company` (string)
- **Contexto del Runtime (`.tmp/active_runtime_context.json`):** El parámetro `max_news_articles` (int) determina el volumen de artículos a retornar (1, 3 ó 5). La clave `extracted_intent` es el manifiesto cognitivo que impulsa la generación de consultas.
- **Variables de Entorno (`.env`):** `TAVILY_API_KEY`, `GROQ_API_KEY_1` ... `GROQ_API_KEY_9`

### Salidas (Outputs)
- **Artefactos:** Archivo temporal `.tmp/news_{company_name}.json` con el arreglo estructurado de noticias.

## 3. Restricciones y Casos Borde
- **Fallback Determinista del Cognitive Planner:** Si la llamada al LLM en `generate_human_search_plan` falla por cualquier motivo (rate limit, error de red), el script cae a 3 queries de fallback pre-construidas usando el `target_market_region` del intent. El pipeline nunca se detiene.
- **Fallo de Tavily Extract:** Si la API `/extract` falla, el script usa automáticamente el snippet resumido de la búsqueda como fallback. El campo `snippet` se trunca a 1500 caracteres máximo.
- **Rotación de Claves Groq:** El rotador `_get_next_groq_key_news()` usa hashing MD5 sobre el nombre de la empresa para selección determinista y sin estado de la clave. Si no hay claves numeradas, recae en `GROQ_API_KEY`.
- **Pacing Delay:** Se impone un `time.sleep(2.0)` antes de cada llamada al LLM para respetar los rate limits de Groq.
- **Frescura Temporal Nativa:** Se usa el parámetro `"time_range": "year"` de Tavily para filtrar por metadatos del índice, sin inyectar strings de año en los queries.