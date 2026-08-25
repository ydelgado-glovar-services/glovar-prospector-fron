# AI LEAD PROSPECTOR WORKSPACE MANIFEST

> Contexto completo, convenciones cruzadas y riesgos conocidos: ver **[AGENTS.md](AGENTS.md)**. Este manifiesto es el mapa rápido de enrutamiento para Gemini CLI / Antigravity.

## 1. Core Architecture Stack
- **Frontend Framework:** Next.js 16 (Turbopack Deployment Line).
- **Backend Worker:** FastAPI (Uvicorn Port 8000 local; en producción corre serverless en Modal vía `modal_app.py` — ver `directivas/06_modal_production_deployment_SOP.md`).
- **Data Cluster:** Cloud Supabase PostgreSQL Engine (Secured via Global MCP Server).
- **LLM Engine:** Groq, modelo único configurable vía `GROQ_MODEL` (default `openai/gpt-oss-120b`) — ver `directivas/09_lead_scoring_engine_SOP.md`.

## 2. Distributed Context Routing
- Contextual Standard Operating Procedures: `directivas/`
- Isolated Subagent Context Blueprints: `.antigravitycli/agents/`
- Automated Hook Interceptors: `.agents/hooks/`
- Shortened Tooling Playbooks: `.agents/skills/`

## 3. Ground Execution Commands
- Core Pipeline Execution: `python scripts/main.py --payload_path <file> --user_id <uuid> --job_id <uuid>`

## 4. Strict Synchronicity & Governance Guardrails
- **Rule of Truth:** No agent or subagent shall modify an execution parameter, model name, or API schema inside `scripts/` or `app.py` without instantly updating the corresponding Markdown file inside `directivas/`.
- **Pre-flight Check Requirement:** Before declaring any task as 'completed' or generating an implementation blueprint, the agent MUST perform a string-matching verification between the active codebase and the SOP files to guarantee 100% architectural alignment.
- **Secrets Guard:** Never run `modal deploy` without confirming the local `.env` has real production values — `modal_app.py` rebuilds secrets from it on every deploy (see AGENTS.md §3 and §6).