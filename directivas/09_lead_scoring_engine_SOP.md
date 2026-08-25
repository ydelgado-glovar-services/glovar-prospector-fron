# DIRECTIVA: LEAD_SCORING_ENGINE_SOP

> **ID:** SOP-SCORING-009
> **Scripts asociados:** `scripts/scoring.py`, `scripts/validator.py`, `scripts/main.py`, `scripts/lead_scraper.py`
> **Migración:** `db/migrations/002_lead_scoring_and_email_verification.sql`
> **Backend:** `app.py` (`GET /api/v1/leads` ordena por `match_score`)
> **Frontend:** `components/results-panel.tsx`, `lib/types.ts`
> **Estado:** ACTIVO

## 1. Objetivo
Documentar el motor de **scoring ICP (Fit + Intent)** y la calificación **fit-first** que reemplaza la antigua calificación binaria centrada en noticias. El objetivo del sistema deja de ser "¿la empresa tiene noticias?" y pasa a ser **"¿qué tan bien encaja con el ICP del cliente y cómo de caliente está?"**, devolviendo **los mejores leads primero**.

## 2. Fundamento (validado contra el mercado B2B 2026)
- **FIT** = encaje con el Ideal Customer Profile (industria/sub-nicho, tamaño, geografía, dolor). Estable.
- **INTENT** = fuerza y recencia del trigger de compra (noticias). Volátil.
- Regla de oro del mercado: *"Fit sin señales no avanza; señales sin fit es ruido"*. Por eso el FIT **califica** y el INTENT **prioriza**.
- Ruteo: Alto Fit + Alto Intent → Tier A; **Alto Fit + Bajo Intent → sigue calificado (nurture)**; Bajo Fit → descartado.

## 3. Cálculo del score (`scripts/scoring.py`)
Sub-scores (0–100) producidos por el LLM con rúbrica; el compuesto se calcula de forma **determinista** en Python.

| Contexto | Fórmula del `match_score` |
| :--- | :--- |
| Lead con contacto | `0.45·fit + 0.30·intent + 0.25·role_fit` |
| Cuenta (EMPRESA APTA, sin contacto) | `0.60·fit + 0.40·intent` |

**Tiers:** A ≥ 80 · B 60–79 · C 40–59 · D < 40.

**Calificación fit-first (`account_qualifies`):**
- Con trigger reciente → fit ≥ **45**.
- Sin trigger reciente → fit ≥ **60** (umbral más exigente, anti-alucinación) **Y** el `fit_score` ya viene recortado ×`TIMING_PENALTY_NO_TRIGGER` (0.75, ver §4-bis) antes de comparar contra este umbral.
- Anti-perfiles → fit < 20 → rechazo.

Las filas **descalificadas** usan `disqualified_scores()` → conservan `fit/intent` por transparencia pero `match_score = 0`, tier `D` (quedan al fondo del ranking).

## 4. Cambios en el pipeline
- **`validator.py` — Fase 1:** `_run_company_audit` produce `fit_score`, `intent_score`, `size_match`. Aprueba por fit (no exige noticias). Los pre-filtros de noticias ya **NO descartan**: solo calculan `has_recent_trigger` (si las noticias son sustanciales y mencionan a la empresa). Si no hay trigger, `intent_score = 0` y decide el fit.
- **`validator.py` — Fase 2:** el LLM asigna `role_fit_score` por candidato y, si NO hay trigger reciente, tiene PROHIBIDO inventar noticias (abre el email con contexto operativo/valor).
- **`main.py` — Descubrimiento (Auditoría #4 y #7):** 3 consultas Tavily multi-ángulo, cap de empresas = **`limite_perfiles`** (slider 5–25). Ver §4-bis para el rediseño signal-first del 2026-08-25.

## 4-bis. Timing como factor de calificación (decisión de negocio 2026-08-25)
El valor del producto no es listar empresas del sector, es llegar en el **momento exacto**. Cambios:
- **Discovery signal-first (`main.py::discover_companies`):** de los 3 ángulos de búsqueda, 2 ahora exigen señal de compra reciente en el propio texto de la query ("announces expansion", "funding round", "hiring") **y** usan `time_range="month"` de Tavily (filtro de fecha real, server-side). El 3er ángulo se deja sin filtro de fecha como red de recall, para no devolver 0 empresas en meses sin noticias frescas del nicho — es un **híbrido**, no un signal-first puro.
- **`news_scraper.py::generate_human_search_plan`:** las 3 queries de noticias por empresa ahora se piden explícitamente orientadas a un trigger reciente ("announces", "recently", "just opened"), y `_tavily_search` bajó su `time_range` de `"year"` a `"month"`.
- **Penalización determinista de `fit_score` (`scripts/scoring.py::TIMING_PENALTY_NO_TRIGGER = 0.75`):** si `has_recent_trigger=False`, `validator.py::_run_company_audit` recorta el `fit_score` del LLM en 25% ANTES de decidir calificación (no solo exige un umbral más alto como antes — ahora el timing también pesa en el ranking/tier de las cuentas que sí califican). Una cuenta de fit excepcional (≥80) puede seguir calificando sin trigger (nurture real); una de fit mediocre (60-75) ya no.
- **Motivación medida en producción:** una corrida real (2026-08-25) descartó 2/2 empresas descubiertas exactamente por falta de señal reciente, después de ya haber gastado Tavily (discovery + news) y Apify (scraping LinkedIn) en ambas. El rediseño busca reducir ese gasto en cuentas que de todas formas se van a rechazar.
- **`lead_scraper.py` — (Auditoría #6):** mayor recall (`resultsPerPage` 5, tope 3/rol, slice top-8) y registro del **origen del email** (`email_source`: `apollo`/`hunter`/`pattern_inferred`) y `email_verified` (solo true con Apollo/Hunter).
- **Determinismo (Auditoría #3):** `temperature=0.1` en todas las llamadas de calificación.
- **Modelo configurable (Auditoría #8, consolidado):** una sola variable `GROQ_MODEL` por entorno controla TODAS las llamadas LLM del pipeline (antes existían `GROQ_MODEL_REASONING`/`GROQ_MODEL_FAST` por separado; se unificaron porque en la práctica el "modelo fast" solo se usaba en `fast_search.py` y el resto de scripts siempre llamaban al de razonamiento). Default: `openai/gpt-oss-120b` (activo en la capa gratuita de Groq; `meta-llama/llama-4-scout-17b-16e-instruct` quedó descontinuado). Declarado de forma independiente en cada script (`main.py`, `validator.py`, `lead_scraper.py`, `news_scraper.py`, `fast_search.py`); cambiarlo requiere actualizar el default en los 5 archivos o exportar `GROQ_MODEL` en el entorno.

## 5. Persistencia (`leads`)
Columnas nuevas (migración 002): `fit_score`, `intent_score`, `role_fit_score`, `match_score` (indexado, default 0), `score_tier` (CHECK A/B/C/D), `score_breakdown` (jsonb), `email_source`, `email_verified`.

## 6. Experiencia de usuario
- `GET /api/v1/leads` ordena por `match_score DESC` (los mejores primero).
- La tabla de resultados muestra una columna **Match** (score + tier con tooltip de fit/intent/role) y un badge **"Estimado"** en emails no verificados.
- El orden por defecto del panel es **Match Score (mejores primero)**.

## 7. Acción requerida
Ejecutar la migración `db/migrations/002_lead_scoring_and_email_verification.sql` en Supabase antes de la primera corrida con esta versión.



## Addendum v3.12.1 — role_fit determinista (fix)
- `scripts/scoring.py` incorpora `deterministic_role_fit(title, target_roles)`: rúbrica por reglas (acrónimos C-level/VP por palabra completa; frases como Director/Gerente/Head por substring; bono token-a-token por coincidencia con los cargos objetivo; penalización a intern/becario/asistente).
- En la Fase 2 del validador el `role_fit` final = `max(role_fit_LLM, deterministic_role_fit(...))`. Así un cargo decisor reconocido (Director, CIO, CTO) **nunca** queda en 0 por ruido del contexto/noticia, eliminando la inconsistencia (72 vs 0) entre evaluaciones del mismo perfil.
