# DIRECTIVA: FAST_MODE_SOP

> **ID:** SOP-FAST-010
> **Scripts:** `scripts/fast_search.py`, `scripts/scoring.py` (compute_fast_match)
> **Backend:** `app.py` (`POST /api/v1/prospect/fast`)
> **Frontend:** `components/search-form.tsx`, `app/dashboard/page.tsx`, `lib/types.ts`
> **Estado:** ACTIVO

## 1. Objetivo
Ofrecer **dos modos de prospección** y una UX simplificada (estilo Enginy):
- **⚡ Modo Rápido (Express):** lista de contactos en **segundos**, sin noticias ni auditoría multi-fase. Para list-building (ej. vendedor de software de RRHH que busca "Directores de RRHH").
- **🔍 Modo Profundo (Señales):** el pipeline completo (noticias + triggers + scoring fit/intent + emails personalizados, ~5-6 min). Para ABM y jugadas de timing/expansión.

## 2. UX
- **Toggle de modo** en la cabecera del formulario.
- **Input en lenguaje natural** ("Describe tu cliente ideal") que el backend parsea a filtros ICP. En Modo Rápido basta esa frase (o un cargo); los demás campos son opcionales para afinar.
- En Modo Rápido se ocultan los campos profundos (dolor, propuesta, opciones avanzadas, velocidad). El modo por defecto es **Rápido**.

## 3. Arquitectura del Modo Rápido (`scripts/fast_search.py`)
Síncrono, dentro del proceso FastAPI (sin subprocess ni polling). Proveedor **intercambiable**:
1. **Apollo People Search** (`mixed_people/search`) — preferido; emails verificados. **Requiere plan de pago de Apollo con API access**; si el plan no lo permite (401/403/422) se cae automáticamente al fallback.
2. **Tavily LinkedIn search** — fallback siempre disponible; email vía Hunter → patrón.

Flujo: `parse_icp_prompt` (campos explícitos + LLM rápido sobre la frase) → búsqueda por proveedor → `deduplicate_leads` → enriquecimiento de email (solo calificados, para mantener la velocidad) → `deterministic_role_fit` → `compute_fast_match` → persistencia en `leads`.

## 4. Scoring del Modo Rápido
Sin intent (no hay noticias): `match_score = 0.55·fit + 0.45·role_fit` (`compute_fast_match`). `fit` base = 75 (la fuente ya filtró por cargo/industria/geo). `es_calificado = role_fit >= 50`. Reutiliza tiers A/B/C/D y el ranking del panel.

## 5. Contrato de la API
`POST /api/v1/prospect/fast` (cabeceras `x-user-id`, `x-api-key`).
Body: `{ prompt?, cargo_decision?, sector?, pais?, mercado_objetivo?, tamano_empresa?, keywords_industria?, limite_perfiles? }`.
Respuesta: `{ status, job_id, source, leads[] }` (los leads ya vienen con scoring y se renderizan directo, sin polling).

## 6. Limitaciones / futuro
- El Modo Rápido NO genera emails personalizados (eso es lo que hace lento al Modo Profundo). Se puede añadir generación batch opcional.
- Calidad de email del fallback Tavily depende de poder resolver el dominio de la empresa.
- **Fase 3 (futuro):** export/sync del CRM a HubSpot/Salesforce.
