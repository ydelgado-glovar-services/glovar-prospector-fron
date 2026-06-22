# DIRECTIVA: HUNTER_B2B_LEAD_ENRICHMENT_SOP

> **ID:** SOP-LEADS-002
> **Script Asociado:** `scripts/lead_scraper.py`
> **Estado:** ACTIVO

## 1. Objetivos y Alcance
- **Objetivo Principal:** Extraer prospectos de LinkedIn a través de Apify e identificar sus correos corporativos utilizando el API de Hunter.io.
- **Criterio de Éxito:** Genera un archivo `.tmp/leads_{company_name}.json` con nombres, cargos, enlaces de LinkedIn y correos corporativos válidos de forma segura, eludiendo bloqueos directos mediante la API oficial de Hunter.io.

## 2. Especificaciones de Entrada/Salida (I/O)
### Entradas (Inputs)
- **Argumentos Requeridos:** `--company` (string)
- **Variables de Entorno (.env):** `APIFY_API_TOKEN`, `HUNTER_API_KEY`, `TAVILY_API_KEY`

### Salidas (Outputs)
- **Artefactos:** Archivo temporal `.tmp/leads_{company_name}.json` conteniendo un arreglo JSON de leads con `first_name`, `last_name`, `title`, `linkedin_url`, `email` y `company_name`.

## 3. Restricciones y Casos Borde
- **Búsqueda en LinkedIn (Apify + Tavily Fallback):**
  - **Limpieza y Sanitización de Nombre de Empresa (`clean_company_name_for_search`):** Para evitar fallos de búsqueda en Apify/Tavily por nombres excesivamente largos o ruidosos (ej. oraciones explicativas enteras recuperadas por Tavily RAG), se limpia y sanitiza el nombre de la empresa antes de componer las queries de búsqueda de Google y LinkedIn, recortando a partir de verbos y términos descriptivos comunes (ej. `mantiene`, `maneja`, `cobertura`, `visitas`, etc.) y removiendo patrones de correos y paréntesis para quedarse con el núcleo del nombre (ej. `H Clinical`).
  - **Queries de Apify — Triple variante por cargo (Fix A):** Para cada cargo objetivo se generan hasta 3 queries complementarias:
    1. Query estricta con comillas dobles en nombre de empresa y cargo completo: `site:linkedin.com/in/ "COMPANY" Full Role Title`
    2. Si el cargo tiene >2 palabras, variante simplificada con las 2 primeras palabras del cargo: `site:linkedin.com/in/ "COMPANY" First Two Words`
    3. Query sin comillas estrictas en el nombre de empresa (para empresas pequeñas/nicho donde las comillas reducen drásticamente los resultados): `site:linkedin.com/in/ COMPANY First Two Words`
  - Si Apify falla, se utiliza una búsqueda alternativa por cargo mediante Tavily (`fallback_tavily_search`) con las mismas variantes de query.
- **Resolución de Dominio Corporativo:**
  - **Capa 1 (Clearbit Autocomplete):** Se realiza una consulta inicial gratuita a `https://autocomplete.clearbit.com/v1/companies/suggest?query=COMPANY` para extraer instantáneamente el dominio web oficial real mapeado.
  - **Capa 2 (Tavily Search Fallback):** Si Clearbit falla, se utiliza Tavily Search con una lista negra estrictamente extendida que descarta directorios, redes sociales y portales de noticias (ej. `portafolio.co`, `larepublica.co`, `techcrunch.com`) para evitar capturar dominios falsos.
- **Enriquecimiento de Correo (Hunter.io API):**
  - Endpoint: `GET https://api.hunter.io/v2/email-finder`
  - Cabeceras/Parametros: `domain`, `first_name`, `last_name`, `api_key` (HUNTER_API_KEY).
- **Cascada de Enriquecimiento B2B (Apollo.io ──► Hunter.io ──► Heurística):**
  - El lead_scraper ejecuta una cascada determinista de enriquecimiento de tres capas:
    1. **Capa Principal (Apollo.io):** Busca al lead por nombre y dominio utilizando el endpoint `POST https://api.apollo.io/api/v1/contacts/search` con la cabecera de autenticación `X-Api-Key`, cabecera `Content-Type: application/json` y los parámetros `q_keywords` y `q_organization_domains_list`.
    2. **Capa Secundaria (Hunter.io):** Si Apollo no encuentra al contacto en su base de datos o falla, desvía la consulta a Hunter.io Email Finder usando `GET https://api.hunter.io/v2/email-finder`. Si Hunter devuelve un error de tasa de límite (429), la función retorna `None` de forma limpia.
    3. **Capa Heurística Final (Deterministic Fallback - LATAM Heuristic):** Si ambas APIs retornan `None`, se genera de forma matemática el patrón corporativo más probable (ej. `{first}.{last}@{domain}`). Esta capa incorpora un filtro de nombres en español (ej. *Carlos*, *Maria*, *Jose*) para identificar si la segunda parte del nombre es un segundo nombre o un apellido, evitando desvíos y rebotes en LATAM.
- **Pre-validación Inteligente y Adaptativa por LLM (LLM Pre-flight Validation Gate):**
  - Antes de realizar cualquier consulta a APIs externas de enriquecimiento B2B (Apollo/Hunter), el scraper realiza una pre-evaluación adaptativa, agnóstica del sector y libre de heurísticas estáticas de palabras clave.
  - **Mecanismo Anti-Desincronización (State Desync Guard):** Envía de forma concurrente todos los candidatos extraídos utilizando su `linkedin_url` como identificador único estable en el JSON de entrada y salida, asegurando que el LLM nunca altere el mapeo físico de los leads.
  - **Limpieza Dinámica de Nombre y Título (Fix B):** En lugar de recortar linealmente el título HTML por guiones en Python, se envía el título completo al LLM `meta-llama/llama-4-scout-17b-16e-instruct` para que extraiga de forma semántica el primer nombre, el apellido y el cargo limpio, resolviendo dinámicamente las variaciones de SEO y geografía de Google.
  - **Criterios de Evaluación del LLM (Reglas Actualizadas):**
    1. **Relación Laboral Activa — LENIENTE (Fix C):** Se asume que TODOS los candidatos son empleados activos de la empresa target por defecto (`is_active_employee: true`), ya que fueron encontrados mediante búsqueda directa `site:linkedin.com/in/ + nombre de empresa`. Solo se marca `is_active_employee: false` si el título contiene EXPLÍCITAMENTE palabras como `former`, `ex-`, `past`, `previo`, `anterior`.
    2. **Alineación de Cargo (Role Fit — FILTRO PRINCIPAL):** El criterio de descalificación principal es `is_role_match`. Mapea semántica y conceptualmente si el cargo del lead se alinea con los roles decisores autorizados por el usuario (`cargo_decision`), descartando cargos basura o genéricos sin importar el sector.
  - **Lógica de Descalificación (Fix D):** Un lead se descalifica SOLO si `is_role_match = false` o si `is_active_employee = false` (ex-empleado explícito). La presencia de una empresa diferente en el título HTML ya NO es criterio de descalificación por sí sola.
  - **Acción:** Si el LLM descalifica al candidato, se le marca como `is_disqualified = True`, se le asigna `email = None`, y se omite el 100% de las consultas de enriquecimiento B2B. En caso contrario, se sobrescriben los campos `first_name`, `last_name` y `title` con las entidades limpias extraídas por el LLM.



---

## Addendum v3.12 — Recall y verificación de email (Auditoría #6)
- Mayor recall de decisores: `resultsPerPage` subido a 5, tope por rol a 3, y slice a los top-8 candidatos.
- Cada lead persiste el **origen del email**: `email_source` ∈ {`apollo`, `hunter`, `pattern_inferred`} y `email_verified` (true solo con Apollo/Hunter). El patrón determinista `nombre.apellido@dominio` queda marcado como **no verificado** para evitar rebotes.
- Modelo Groq configurable por entorno (`GROQ_MODEL_REASONING`). Ver `directivas/09_lead_scoring_engine_SOP.md`.



## Addendum v3.12.1 — Deduplicación estricta pre-scoring (fix)
- `deduplicate_leads()` unifica clones por **(nombre normalizado + empresa)** ANTES de la validación LLM (ahorra tokens) y de nuevo antes de enriquecer/persistir.
- Cubre: clones idénticos (`Esteban Sánchez`), apellido parcial vs completo (`Fidel Vargas` ⊆ `Fidel Vargas Londoño`, se conserva el más completo y se fusiona el email) y basura de parsing (`Carlos Alberto Alberto` → `Carlos Alberto` vía `_clean_name`).
- El prompt de validación de roles ahora reconoce explícitamente cargos decisores (Director, CIO/CTO/CxO, VP, Gerente, Head) y solo descarta roles claramente no decisores, evitando el falso "Nombre de Cargo Inválido".
