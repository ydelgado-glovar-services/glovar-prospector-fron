# DIRECTIVA: PIPELINE_ORCHESTRATOR_EXECUTION_SOP

> **ID:** SOP-ORCHESTRATOR-004
> **Script Asociado:** `app.py`
> **Estado:** ACTIVO

## 1. Objetivos y Alcance
- **Objetivo Principal:** Garantizar que el orquestador backend de FastAPI (`app.py`) invoque el script principal del pipeline (`scripts/main.py`) utilizando el entorno virtual local (`.venv`) si está disponible.
- **Aislamiento de Dependencias:** Al priorizar el ejecutable del entorno virtual local sobre el intérprete global del sistema, se asegura que las dependencias requeridas por el pipeline (como `httpx`, `pydantic`, etc.) estén correctamente aisladas y disponibles durante la ejecución en subprocesos.

---

## 2. Contrato de Resolución de Entorno (Windows)
- **Ruta Objetivo del Intérprete:** `.venv/Scripts/python.exe`
- **Lógica de Decisión Determinista:**
  1. El orquestador debe intentar construir la ruta local utilizando `os.path.join(".venv", "Scripts", "python.exe")`.
  2. Mediante la función `os.path.exists()`, debe evaluar si el archivo ejecutable existe físicamente en el espacio de trabajo.
  3. **Caso de Éxito:** Si el archivo existe en el disco, se debe usar como el binario de ejecución del subproceso para correr `scripts/main.py`.
  4. **Caso Fallback (Seguridad):** Si no existe, debe degradar de forma segura al intérprete del sistema actual utilizando `sys.executable`.

---

## 3. Restricciones y Pautas de Gobernanza
- **Prohibición de Rutas Absolutas:** Bajo ninguna circunstancia se deben codificar rutas absolutas del sistema operativo (`C:\Users\...` o similares) que dependan de la máquina local del desarrollador. Todas las resoluciones deben ser relativas al espacio de trabajo.
- **Estabilidad de Ejecución:** El orquestador no debe lanzar excepciones de enrutamiento si el entorno virtual local no está configurado. Debe realizar la validación de forma tolerante a fallos y asegurar que el fallback mantenga el pipeline operativo.
- **Procesamiento Concurrente de Empresas (ThreadPoolExecutor, Idempotencia & Límite de Lote):** El orquestador principal (`main.py`) procesa el lote de empresas objetivo en paralelo utilizando un pool de hilos (`ThreadPoolExecutor`) con **3 workers concurrentes** para máxima velocidad de prospección. La estabilidad en contenedores de producción (Modal) se garantiza mediante el mecanismo de **Idempotencia Activa** que consulta Supabase antes de procesar cada empresa: si ya fue validada para el `job_id` activo, se salta instantáneamente. Esto convierte cualquier reinicio de contenedor de Modal (preemption) de un evento catastrófico a una molestia menor sin pérdida de créditos de API. El contenedor de Modal dispone de **2048 MB de RAM** declarados explícitamente para absorber la carga de 3 subprocesos Python concurrentes con peticiones HTTP simultáneas. Asimismo, se impone un **tope estricto de máximo 20 empresas limpias por job**.
- **Fase 0: Pre-flight Cognitive Intent Parser:** Antes de cualquier búsqueda o descubrimiento de empresas, el orquestador ejecuta `extract_strategic_intent(form_data)` que utiliza el LLM (`GROQ_MODEL`, default `openai/gpt-oss-120b`) para traducir el formulario crudo del cliente en un **Manifiesto de Búsqueda Estratégico** (`extracted_intent`) con las siguientes claves cognitivas:
  - `optimized_search_tokens`: Los 4 mejores términos de búsqueda optimizados para motores.
  - `target_industry_core`: El nicho de industria normalizado al estándar inglés.
  - `b2b_buying_trigger_context`: Traducción precisa del evento que dispara una venta.
  - `rigorous_pain_framework`: Explicación académica del fallo operativo que sufren los prospectos.
  - `target_market_region`: Región geográfica normalizada.
  Este manifiesto se persiste en `.tmp/active_runtime_context.json` bajo la clave `"extracted_intent"` y alimenta a los scripts downstream (`news_scraper.py`, `validator.py`).
- **Descubrimiento de Empresas Cognitivo:** La función `discover_companies(industry, size, country, extracted_intent)` usa directamente los `optimized_search_tokens` y `target_industry_core` del manifiesto cognitivo para construir queries de Tavily de alta precisión. No acepta ni requiere `advanced_keywords` ni strings de keywords crudos del formulario.





---

## Addendum v3.12 — Descubrimiento ampliado y slider conectado (Auditoría #4, #7, #8)
- **Descubrimiento multi-ángulo:** `discover_companies` lanza 3 consultas Tavily (directorio, líderes del sector, intención/dolor) y fusiona/deduplica por URL para un universo más amplio y menos sesgado.
- **Slider conectado:** el cap de empresas a procesar = `limite_perfiles` (5–25). Antes estaba fijo en 20 y el slider no surtía efecto.
- **Modelo configurable (consolidado):** una sola variable `GROQ_MODEL` por entorno (default `openai/gpt-oss-120b`, activo en capa gratuita de Groq).
- Ver `directivas/09_lead_scoring_engine_SOP.md`.



## Addendum v3.12.2 — Anti-perfil no debe incluir la industria objetivo (fix Fase 0)
- Bug: el Intent Parser (Fase 0) a veces metía la **industria objetivo** dentro de `anti_profile_constraints` (p. ej. "Exclude banks or insurance"), provocando que `validator.py` descartara a todos los clientes válidos (bancos).
- Fix: el `system_prompt` de `extract_strategic_intent` incluye una **CRITICAL RULE** explícita: el anti-perfil es STRICTAMENTE para competidores directos de la empresa remitente (otras consultoras IT, agencias RPA, etc.), **NUNCA** la industria objetivo. Se añade una verificación final que exige no excluir el sector objetivo y devolver string vacío si no hay un competidor claro.



## Addendum v3.13 — Geografía dual: sede vs mercado de expansión (expansion play)
- **Caso de uso:** encontrar empresas con SEDE en un país (ej. EE.UU.) que **se expanden u operan** en otro mercado (ej. Colombia); la entrada a ese mercado es el disparador de compra (típico para un 3PL local).
- **Nuevo campo (opcional):** `mercado_objetivo` en el formulario / `ProspectRequest`. Si se deja vacío, comportamiento idéntico al actual.
- **Fase 0 (`main.py`):** ahora emite dos claves geográficas: `discovery_hq_region` (sede, dónde descubrir) y `target_market_region` (mercado de expansión/servicio = `mercado_objetivo` si se provee).
- **Descubrimiento (`discover_companies`):** si hay "expansion play", las 3 consultas Tavily combinan sede + expansión ("companies headquartered in {HQ} expanding into {mercado}", "with operations/offices in {mercado}", "opening operations in {mercado}").
- **Validador (Fase 1):** el encaje geográfico premia presencia/señales de expansión en `target_market_region` y **NO penaliza** la sede extranjera; una empresa de la sede sin vínculo con el mercado objetivo = fit geográfico débil.
