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
- Sin trigger reciente → fit ≥ **60** (umbral más exigente, anti-alucinación).
- Anti-perfiles → fit < 20 → rechazo.

Las filas **descalificadas** usan `disqualified_scores()` → conservan `fit/intent` por transparencia pero `match_score = 0`, tier `D` (quedan al fondo del ranking).

## 4. Cambios en el pipeline
- **`validator.py` — Fase 1:** `_run_company_audit` produce `fit_score`, `intent_score`, `size_match`. Aprueba por fit (no exige noticias). Los pre-filtros de noticias ya **NO descartan**: solo calculan `has_recent_trigger` (si las noticias son sustanciales y mencionan a la empresa). Si no hay trigger, `intent_score = 0` y decide el fit.
- **`validator.py` — Fase 2:** el LLM asigna `role_fit_score` por candidato y, si NO hay trigger reciente, tiene PROHIBIDO inventar noticias (abre el email con contexto operativo/valor).
- **`main.py` — Descubrimiento (Auditoría #4 y #7):** 3 consultas Tavily multi-ángulo (directorio, líderes, intención) fusionadas y deduplicadas por URL; el cap de empresas = **`limite_perfiles`** (slider 5–25), que antes no tenía efecto.
- **`lead_scraper.py` — (Auditoría #6):** mayor recall (`resultsPerPage` 5, tope 3/rol, slice top-8) y registro del **origen del email** (`email_source`: `apollo`/`hunter`/`pattern_inferred`) y `email_verified` (solo true con Apollo/Hunter).
- **Determinismo (Auditoría #3):** `temperature=0.1` en todas las llamadas de calificación.
- **Modelo configurable (Auditoría #8):** `GROQ_MODEL_REASONING` / `GROQ_MODEL_FAST` por entorno.

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
