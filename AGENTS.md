# AI Lead Prospector — Contexto para agentes de IA

Este archivo es la **fuente canónica de contexto** para cualquier agente de IA (Claude Code, Gemini CLI, Antigravity, Cursor, etc.) que trabaje en este repositorio. `CLAUDE.md` y `GEMINI.md` apuntan aquí para lo compartido y solo agregan notas específicas de su propia herramienta.

No repitas aquí el detalle operativo de cada componente — eso vive en `directivas/*.md` (11 SOPs numerados, uno por componente). Este archivo da la vista de conjunto, las convenciones que cruzan todo el repo, y los riesgos conocidos que cualquier agente debe tener presentes antes de tocar código.

## 1. Qué es esto

Plataforma B2B de prospección comercial con IA (sector logística / ciencias de la vida). Tres capas:

- **Frontend** — Next.js 16 / React 19, en `frontend/` (desde 2026-08 ya no está anidado; desplegado en Vercel). Proxy inverso server-side en `app/api/v1/[...slug]/route.ts` inyecta `X-User-Id` + `GLOVAR_BACKEND_API_KEY`; el navegador nunca ve esa key.
- **Backend** — FastAPI (`app.py`), local vía Uvicorn o desplegado serverless en Modal (`modal_app.py`). Modo Profundo lanza `scripts/main.py` como subproceso (pipeline noticias → leads → validación); Modo Rápido (`scripts/fast_search.py`) corre síncrono dentro del propio proceso FastAPI.
- **Datos** — Supabase (PostgreSQL), con `SUPABASE_SERVICE_ROLE_KEY` server-side y RLS como defensa en profundidad.

Para el detalle de cada pieza: `directivas/01` a `11` + `lazy_oauth_integration_SOP.md`. Empieza por `directivas/04_pipeline_orchestrator_SOP.md` si necesitas entender el flujo end-to-end.

## Costos (Tavily / Apify / Hunter) — verificado 2026-08-25

Los únicos 3 servicios de pago: **Tavily** ($30/mes, 4.000 créditos), **Apify** (~$30/mes de cómputo, Modo Profundo únicamente), **Hunter** (verificación de email). Groq, Modal, Supabase y Vercel operan en capa gratuita.

- **Hunter es el cuello de botella real, no Tavily/Apify.** El plan actual es el **free tier: 50 créditos/mes** (1 crédito ≈ 1 búsqueda de email; 0.5 crédito por verificación) — con eso el techo real de contactos con correo verificado es **~50/mes**, muy por debajo de cualquier cifra de "1000 leads/mes" a menos que se suba a un plan pago (el `informe_costos_definitivo.md` en `docs/comercial/` asumía el plan Starter de Hunter, $49/mes/2.000 créditos — ya no es el plan activo, ese doc quedó desactualizado tras el pivote a cliente único). Además, la `HUNTER_API_KEY` en `.env` está **inválida (401)** a fecha 2026-08-25 — ver `AGENTS.md`/reporte de la prueba de fuego.
- **Tavily/Apify tienen holgura amplia** para un solo cliente: consumo real medido en una sesión de pruebas (3 intentos de Modo Profundo, uno exitoso con 2 empresas auditadas) = ~75 créditos Tavily de 4.000 (~2%) y ~$0.12 de Apify de $30 (~0.4%).
- **Sistema de créditos de prospección:** ver `directivas/11_prospecting_credits_SOP.md` — 1 crédito = 1 empresa procesada en Modo Profundo, techo default 300/mes, gate en `app.py` + registro real en `scripts/main.py`.
- **Si el negocio quiere de verdad ~1.000 leads/mes con correo verificado**, el paso obligatorio es subir el plan de Hunter (no Tavily/Apify) — son los que sobran, no los que faltan.

## 2. Convenciones que cruzan todo el repo

### Modelo Groq — una sola variable
Todas las llamadas LLM del pipeline (intent parsing, discovery, scoring de cuenta, validación de rol, redacción de email, query planning, parseo ICP del Modo Rápido) usan **una sola variable de entorno: `GROQ_MODEL`** (default `openai/gpt-oss-120b`, activo en la capa gratuita de Groq).

- Antes existían `GROQ_MODEL_REASONING` / `GROQ_MODEL_FAST` por separado; se consolidaron (2026-08) porque en la práctica solo `fast_search.py` usaba el modelo "fast", y el resto del pipeline siempre llamaba al de razonamiento — dos variables para un solo comportamiento real.
- Groq rota su catálogo de modelos gratuitos con frecuencia real, no solo teórica: `llama-4-scout-17b-16e-instruct` quedó descontinuado (2026-08-14), y días después `llama-3.3-70b-versatile` —su reemplazo— también dejó de estar disponible (404 `model_not_found`, detectado 2026-08-25 en una prueba en vivo). **La documentación de Groq puede ir por detrás de lo que tus keys realmente pueden usar.** Antes de fijar un nuevo default, verifica contra la API real, no solo contra `https://console.groq.com/docs/models`:
  ```bash
  curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY_1"
  ```
  y confirma con una llamada real de `chat/completions` antes de darlo por bueno (un modelo puede aparecer listado y aun así fallar). Default actual verificado así: `openai/gpt-oss-120b` (2026-08-25).
- **`GROQ_MODEL` está declarado de forma independiente en 5 archivos** (`scripts/main.py`, `validator.py`, `lead_scraper.py`, `news_scraper.py`, `fast_search.py`), cada uno con su propio `os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")`. No hay un único punto de verdad en código — si cambias el default, cámbialo en los 5 archivos (o simplemente exporta `GROQ_MODEL` en el entorno, que tiene prioridad).

### Rotación de API keys de Groq
**Decisión de negocio fija (no se elimina el pool):** el sistema opera exclusivamente con llaves gratuitas rotadas — no con un plan de pago. Cualquier fix a esta lógica debe preservar la rotación, no reemplazarla por una sola llave.

Pool de hasta 9 keys (`GROQ_API_KEY_1`...`9`, fallback a `GROQ_API_KEY`; el tamaño real del pool depende de cuántas estén seteadas — verifica con `.env`, no asumas 9), rotación determinista por hash MD5 del nombre de la empresa (o aleatoria si no hay nombre de empresa). Es **obligatorio** usarla para cualquier llamada LLM nueva — así lo exige `.antigravitycli/agents/agent_onboarding.md`.

⚠️ Esta lógica está **copiada casi idéntica en 5 archivos** (`main.py`, `validator.py`, `lead_scraper.py`, `news_scraper.py`, `fast_search.py`). No existe un módulo compartido pese a que el onboarding lo da por hecho ("debes importar `get_next_groq_key()`"). Si tocas esta lógica, revisa los 5 lugares — no asumas que hay una sola función.

⚠️ **Bug de reintentos corregido (2026-08-25):** en `validator.py` (`_call_groq_with_retry`) y `main.py` (`discover_companies`), el loop de reintentos volvía a pedir la llave con `get_next_groq_key(company_name)` — determinista por `company_name`, así que un 429 se reintentaba contra la MISMA llave que acababa de rate-limitear, sin aprovechar el pool. Fix: la semilla de selección ahora incluye el número de intento (`f"{company_name}::retry{attempt}"`) para que cada reintento rote a otra llave. Si agregas un nuevo loop de reintentos con Groq, replica este patrón.

⚠️ **Bug de concentración de carga corregido (2026-08-25):** `fast_search.py` rotaba con `int(time.time() / 60)` — bajo Modal (hasta `max_containers=10` concurrentes), todas las peticiones del mismo minuto, en cualquier contenedor, caían en la misma llave. Se cambió a `random.choice(keys)` para repartir la carga concurrente sobre todo el pool.

### Modelo/parámetros y gobernanza ("Regla de Verdad")
`GEMINI.md` establece que ningún agente puede cambiar un nombre de modelo, parámetro de ejecución o schema de API sin actualizar el SOP correspondiente en `directivas/`. Se aplicó ese criterio al consolidar `GROQ_MODEL` (ver `directivas/09_lead_scoring_engine_SOP.md` y las referencias cruzadas en 01, 02, 03, 04). Sigue esa disciplina: si tocas `scripts/` o `app.py` de forma que cambie comportamiento observable, actualiza el SOP en el mismo cambio.

## 3. Riesgos conocidos — lee esto antes de tocar estas áreas

- **`modal_app.py` reconstruye los secretos de producción desde el `.env` LOCAL en cada `modal deploy`** (no usa un secreto nombrado/persistente en Modal). Ya se corrigió el bug más grave (línea ~36: antes escribía `""` para cualquier variable ausente del `.env` local, pisando con blancos los secretos reales de producción — causó un incidente real el 2026-08-14). Ahora solo inyecta una variable si tiene valor local, así que un deploy sin `.env` completo ya no borra secretos existentes, **pero tampoco los actualiza** ni gestiona rollback: sigue sin haber un mecanismo de versionado de secretos. Antes de cualquier `modal deploy`, confirma que el `.env` local tiene los valores reales o usa un secreto nombrado de Modal (`modal secret create` / `modal.Secret.from_name(...)`) — recomendado como mejora futura, no implementado todavía.
- **Fail-open en autenticación:** `app.py` (`verify_api_key`) retorna sin validar si `GLOVAR_BACKEND_API_KEY` no está seteada en el entorno — deja la API completamente abierta en vez de rechazar. Si tocas ese endpoint, considera invertir a fail-closed.
- **`/api/v1/auth/google/status` siempre responde `{"connected": true}`** — bypass intencional documentado en `directivas/lazy_oauth_integration_SOP.md`, no un bug, pero no asumas que refleja el estado real de OAuth.
- **`backup/` está trackeado en git** (no en `.gitignore`) y contiene copias completas y desactualizadas de `main.py`, `validator.py`, `lead_scraper.py`, `news_scraper.py`. Verifica siempre que estás editando `scripts/`, no `backup/`.
- **Llamadas síncronas a Supabase dentro de handlers `async def`** en varios endpoints de `app.py` (bloquean el event loop). Los endpoints más nuevos ya usan `run_in_threadpool`; si agregas uno nuevo, síguelo también.
- **Sin suite de tests automatizada.** La única verificación es compilación + type-check (sección 4). Si cambias lógica de scoring/validación, prueba manualmente con el skill `test_run` antes de dar por completado.
- `requirements.txt` está codificado en UTF-16LE — es frágil ante herramientas que no toleren ese encoding; no lo reescribas a mano sin verificar el encoding resultante.
- **`GLOVAR_BACKEND_API_KEY` vive en DOS lugares independientes que deben coincidir exactamente:** el `.env` local usado por `modal deploy` (backend) y las variables de entorno del proyecto en Vercel (`frontend/app/api/v1/[...slug]/route.ts:41`, leída server-side). Si en Vercel falta o no coincide, el proxy **silenciosamente** no manda el header `x-api-key` (`if (backendApiKey) { headers.set(...) }` — sin error, sin log) y el backend rechaza todo con 401/500, aunque Modal esté perfectamente sano. Si algo "no funciona" desde el frontend pero `curl` directo a Modal sí funciona, sospecha primero de esto antes de tocar el backend. Lo mismo aplica a `PYTHON_BACKEND_URL`/`NEXT_PUBLIC_API_URL` (deben apuntar a la URL real de Modal, no a `http://127.0.0.1:8000`).

## 4. Verificación antes de dar algo por completado

```bash
# Backend
python -m py_compile app.py scripts/main.py scripts/news_scraper.py scripts/lead_scraper.py scripts/validator.py scripts/fast_search.py

# Frontend (desde frontend/)
npx tsc --noEmit
```

Health check en producción (mismo `x-api-key` que el resto de la API, no requiere `x-user-id`): `curl https://<workspace>--ai-lead-prospector-backend-api.modal.run/health -H "x-api-key: $GLOVAR_BACKEND_API_KEY"`. Añadido 2026-08-25 específicamente para detectar un crash-loop en minutos en vez de por accidente.

(El SOP y el onboarding usan `.venv\Scripts\python.exe` porque el desarrollo local ocurre en WSL/Windows con un venv de Windows — usa el intérprete que tengas activo, el `py_compile` es lo que importa.)

Correr el pipeline completo localmente: ver skill `.agents/skills/test_run/SKILL.md` (usa el payload cacheado en `.tmp/dynamic_form_payload.json`).

## 5. Dónde vive cada tipo de contexto

| Qué necesitas | Dónde está |
|---|---|
| Detalle operativo de un componente (contrato I/O, reglas de negocio) | `directivas/NN_*_SOP.md` |
| Arquitectura de despliegue, mitigaciones de seguridad activas | `.antigravitycli/agents/agent_onboarding.md` |
| Comandos rápidos (correr pipeline, verificar salud, consultar leads) | `.agents/skills/*/SKILL.md` |
| Variables de entorno requeridas antes de ejecutar localmente | `.agents/hooks/PreInvocation.json`, `.env.example` |
| Historial de qué se corrigió y cuándo (por versión) | `README.md` (changelog al inicio), `technical_audit_report.md` (snapshot de auditoría, no se actualiza retroactivamente) |

## 6. Despliegue a Modal — checklist mínimo

1. Confirmar que `ia_lead_prospector/.env` local tiene los valores reales (Supabase, Tavily, Hunter, Apify, `GLOVAR_BACKEND_API_KEY`, `GROQ_API_KEY_1..N`). Sin esto, `modal_app.py` no podrá inyectar esos secretos (ver sección 3).
2. `modal deploy modal_app.py` desde `ia_lead_prospector/`.
3. Verificar salud: `curl .../health -H "x-api-key: ..."` (o revisar `modal app logs ai-lead-prospector-backend`) antes de dar el deploy por exitoso — un deploy "exitoso" en la CLI no garantiza que el contenedor arranque sin errores en runtime (import-time failures, como `SupabaseException`, no se ven hasta la primera invocación).
4. Si tocaste el backend, confirma también que Vercel tiene `GLOVAR_BACKEND_API_KEY` con el MISMO valor y `PYTHON_BACKEND_URL`/`NEXT_PUBLIC_API_URL` apuntando a la URL de Modal — ver el riesgo en sección 3. Un backend sano en Modal no implica que el frontend pueda hablarle.
