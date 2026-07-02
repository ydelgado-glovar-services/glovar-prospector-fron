# AI Lead Prospector - Technical Audit & Architecture Report

## 1. Project Overview & Current State
**System Name:** AI Lead Prospector (Agent_Scraping_Linkedin_3)
**Version:** 3.10.0 (Production)
**Status:** Operational and structurally sound. The repository contains a complete pipeline for autonomous B2B intelligence and cold outreach, connecting a Next.js frontend to a FastAPI orchestrator that deploys background jobs on Modal serverless containers.

## 2. Tech Stack Architecture
- **Frontend Layer:** Next.js 16.2.6 (React 19, Turbopack) + TailwindCSS v4.0.0. Located in `glovar-prospector-frontend`.
- **Backend Orchestrator:** FastAPI 0.115 + Uvicorn. Exposes REST endpoints and manages async pipeline triggering via `BackgroundTasks`. Port 8000.
- **Serverless Compute:** Modal (`modal_app.py`) for auto-scaling horizontal deployment (Debian Slim, 2GB RAM, up to 10 instances).
- **Data Cluster:** Cloud Supabase (PostgreSQL 17.6). Project ID: `acoefbmluadzscwushcw`.
- **AI/LLM Engine:** Llama-4-Scout-17b via Groq API (with deterministic state-less API key rotation).
- **External Integrations:** 
  - Tavily Search API & Extract API (Company Discovery & News Scraping)
  - Apify `google-search-scraper` (LinkedIn Decision-Maker Extraction)
  - Hunter.io (Email Resolution)
  - Google OAuth / Gmail API (Direct Email Outreach)

## 3. Core Modules & Subprocesses (`scripts/`)
The background intelligence pipeline runs asynchronously utilizing Python `ThreadPoolExecutor` for concurrency:
1. **`main.py` (Orchestrator):** Serves as the entry point. Parses B2B intent using an LLM, queries Tavily to discover target companies, applies exclusion blacklists, and spawns parallel threads for the scraping phases.
2. **`news_scraper.py`:** Searches for recent operational growth events/triggers (2025/2026) that justify an outreach.
3. **`lead_scraper.py`:** Discovers target decision-makers on LinkedIn via Apify and attempts to resolve their corporate email via Hunter.io. Includes a manual fallback loop if the email isn't found.
4. **`validator.py`:** Performs an aggressive RAG-based cross-audit (fact-checking the trigger, the operational pain mapping, and the lead's role fit). If qualified, it authors the hyper-personalized cold email and commits directly to Supabase.

## 4. Supabase Database Architecture (Consolidated via MCP)
*MCP Telemetry Date: 2026-06-19*
**Project Name:** Agent_Scraping_Linkedin (`acoefbmluadzscwushcw`)
**Region:** us-east-2
**Database:** Postgres 17.6
**Row Level Security (RLS):** Strictly ENABLED across all tables ensuring multi-tenant isolation.

### Relational Tables & Schema
1. **`public.leads` (2,126 rows)**
   - **Purpose:** Core entity for enriched prospect data and LLM-generated cold emails.
   - **Key Fields:** `id` (bigint), `created_at`, `nombre_lead`, `empresa`, `cargo`, `linkedin_url`, `email`, `telefono`, `trigger_noticia`, `mensaje_generado`, `es_calificado`, `user_id` (uuid), `job_id` (uuid).
   - **Connections:** Relates to `user_profiles` (`user_id`) and `jobs_status` (`job_id`).

2. **`public.jobs_status` (92 rows)**
   - **Purpose:** Tracks execution telemetry and live progress of background pipelines for the Next.js UI.
   - **Key Fields:** `job_id` (PK, uuid), `user_id`, `status` (Enum: queued, processing, completed, failed), `progress_percentage`, `current_phase`, `error_message`.

3. **`public.user_profiles` (7 rows)**
   - **Purpose:** Extended user profile metadata.
   - **Key Fields:** Contains a 1:1 reference to Postgres `auth.users` and stores the RBAC role (`admin` or `client`).

4. **`public.saved_queries` (1 row)**
   - **Purpose:** Persists payload configurations for recurrent executions.
   - **Key Fields:** `user_id`, `query_name`, `search_params`.

5. **`public.user_integrations` (0 rows)**
   - **Purpose:** Securely stores third-party OAuth access envelopes (e.g., Google).
   - **Key Fields:** `user_id`, `provider`, `token_credentials` (JSON).

## 5. Security Guardrails & Directives
- **Strict Synchronicity Rule:** Any architectural modification in `scripts/` or `app.py` must be immediately reflected in the Standard Operating Procedures (SOPs) located inside the `directivas/` directory.
- **Pre-flight Check Requirement:** String-matching verification between the codebase and SOP files is required prior to marking any modifications as complete.
- **Gmail OAuth Bypass:** Currently evaluated as `{"connected": True}` in `app.py` for local simulation, though `send_cold_outreach_email` endpoint implements actual token refresh and live API dispatches.

## 6. Local Execution Commands
- **Standard Pipeline Run:** 
  `python scripts/main.py --payload_path <file> --user_id <uuid> --job_id <uuid>`
- **Local Server:**
  `uvicorn app:app --host 0.0.0.0 --port 8000 --reload`



---

## 7. Auditoría 3.11.0 — Hallazgos y Correcciones

### 7.1 Hallazgos críticos (corregidos)
1. **Build roto por `.gitignore`:** la regla `lib/` de la plantilla Python (raíz) ignoraba `glovar-prospector-frontend/glovar-prospector-frontend/lib/`. Los archivos `types.ts`, `api.ts` y `utils.ts` **no estaban versionados**, por lo que el frontend no compilaba tras un clon limpio. _Fix:_ regla anclada a `/lib/` y `/lib64/`, y archivos `lib/*` restaurados.
2. **"Guardar Consulta" inoperante:** el frontend llamaba a `PUT`/`DELETE /api/v1/queries/{id}` inexistentes, y el `POST` devolvía una lista (rompía `data.id` → `activeQueryId`). _Fix:_ endpoints añadidos y `POST` normalizado a objeto único; lógica de versionado completa.

### 7.2 Hallazgos de seguridad (corregidos / mitigados)
3. **`service_role` bypassa RLS:** el aislamiento multi-tenant depende del filtro `.eq("user_id", ...)`. Se reforzó en todos los endpoints nuevos + verificación de propiedad antes de mutar (anti-IDOR). RLS estricto definido también en la migración para accesos directos con anon key.
4. **Webhook interno sin whitelist:** `PATCH /internal/update-job/{job_id}` aceptaba un dict arbitrario (mass-assignment). _Fix:_ whitelist `{status, progress_percentage, current_phase, error_message, processed_leads, total_leads}`. La telemetría de `BackgroundTasks → jobs_status` se preserva intacta.
5. **CORS inválido:** `allow_origins=["*"]` + `allow_credentials=True`. _Fix:_ configurable vía `ALLOWED_ORIGINS` (credenciales solo con orígenes explícitos).

### 7.3 Asincronía / rendimiento
6. **Llamadas Supabase síncronas en endpoints async** bloquean el event loop. _Fix:_ los endpoints nuevos usan `run_in_threadpool`. _Recomendación pendiente:_ migrar los endpoints legados (`get_job_status`, `get_leads`, `trigger_prospecting_flow`) al mismo patrón.

### 7.4 Hallazgos abiertos (pendientes, fuera del alcance de las 3 misiones)
7. **Envío de correo desfasado:** `integrations-provider.tsx` llama `POST /api/v1/auth/google/send-email` con `{lead_id, subject, body}`, pero el backend expone `POST /api/v1/outreach/send-email` con esquema `{lead_id, target_email}`. _Acción recomendada:_ unificar ruta y contrato (el cuerpo del correo se toma de `mensaje_generado`, por lo que el frontend debería enviar `target_email`).
8. **OAuth status simulado:** `/api/v1/auth/google/status` retorna `connected:true` fijo, lo que puede inducir a error si no hay integración real.
9. **`POLL_BUDGET_MS = 9000_000`** (≈150 min) contradice el comentario "5 minutos" en `dashboard/page.tsx`.
