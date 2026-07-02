# AI LEAD PROSPECTOR WORKSPACE MANIFEST

## 1. Core Architecture Stack
- **Frontend Framework:** Next.js 16 (Turbopack Deployment Line).
- **Backend Worker:** FastAPI Stateful Local Core (Uvicorn Port 8000).
- **Data Cluster:** Cloud Supabase PostgreSQL Engine (Secured via Global MCP Server).

## 2. Distributed Context Routing
- Contextual Standard Operating Procedures: `directivas/`
- Isolated Subagent Context Blueprints: `.antigravitycli/agents/`
- Automated Hook Interceptors: `.antigravitycli/hooks/`
- Shortened Tooling Playbooks: `.antigravitycli/skills/`

## 3. Ground Execution Commands
- Core Pipeline Execution: `python scripts/main.py --payload_path <file> --user_id <uuid> --job_id <uuid>`

## 4. Strict Synchronicity & Governance Guardrails
- **Rule of Truth:** No agent or subagent shall modify an execution parameter, model name (e.g., 'gemini-3.5-flash'), or API schema inside `scripts/` or `app.py` without instantly updating the corresponding Markdown file inside `directivas/`.
- **Pre-flight Check Requirement:** Before declaring any task as 'completed' or generating an implementation blueprint, the agent MUST perform a string-matching verification between the active codebase and the SOP files to guarantee 100% architectural alignment.