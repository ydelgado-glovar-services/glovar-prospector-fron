# app.py
import os
import uuid
import json
import sys
import subprocess
import base64
from email.mime.text import MIMEText
from typing import List, Optional
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


def _utc_now_iso() -> str:
    """Timestamp ISO-8601 en UTC para columnas updated_at / last_run_at."""
    return datetime.now(timezone.utc).isoformat()

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    expected_key = os.getenv("GLOVAR_BACKEND_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Backend API Key is not set."
        )
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Backend API Key"
        )

app = FastAPI(
    title="AI Lead Prospector Enterprise API",
    version="3.13.0",
    dependencies=[Depends(verify_api_key)]
)

# ── CORS Hardening ────────────────────────────────────────────────────────────
# La combinación allow_origins=["*"] + allow_credentials=True es inválida (los
# navegadores la rechazan) e insegura. Se resuelve de forma configurable:
#  - Si ALLOWED_ORIGINS está definido (CSV), se restringe a esos orígenes con
#    credenciales habilitadas.
#  - Si no, se permite "*" SIN credenciales (las peticiones legítimas llegan
#    server-side desde el proxy de Next.js con x-api-key, no requieren cookies).
_raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
if _raw_origins:
    _allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    _allow_credentials = True
else:
    _allowed_origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize production Cloud Supabase interaction client safely
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

class ProspectRequest(BaseModel):
    mi_empresa: str
    sector: str
    pais: str
    mercado_objetivo: Optional[str] = ""
    tamano_empresa: str
    cargo_decision: str
    dolor_cliente: str
    propuesta_valor: str
    limite_perfiles: Optional[int] = 10
    max_news_articles: Optional[int] = 3
    triggers_compra: Optional[str] = ""
    casos_exito: Optional[str] = ""
    keywords_industria: Optional[str] = ""
    exclusion_list: Optional[List[str]] = Field(default_factory=list)

# Enforced production schema: target_email is now mandatory and dynamically sent from frontend review modal
class SendEmailRequest(BaseModel):
    lead_id: int
    target_email: str = Field(..., description="The real destination email address captured dynamically from the UI modal.")


class FastProspectRequest(BaseModel):
    """Modo Rápido: una frase en lenguaje natural + filtros opcionales.
    Todos los campos son opcionales; el `prompt` se parsea a filtros ICP."""
    prompt: Optional[str] = ""
    cargo_decision: Optional[str] = ""
    sector: Optional[str] = ""
    pais: Optional[str] = ""
    mercado_objetivo: Optional[str] = ""
    tamano_empresa: Optional[str] = ""
    keywords_industria: Optional[str] = ""
    limite_perfiles: Optional[int] = 15

# Deprecated in-memory database in favor of direct Supabase persistence

def execute_pipeline_subprocess(payload_path: str, user_id: str, job_id: str):
    try:
        supabase.table("jobs_status").update({
            "status": "processing",
            "current_phase": "Phase 0: Discovering targets",
            "progress_percentage": 10
        }).eq("job_id", job_id).execute()
    except Exception as err:
        print(f"[Orchestrator] Failed to update start status: {err}")
    
    # Robust environment resolution logic for execution binary
    venv_python = os.path.join(".venv", "Scripts", "python.exe")
    python_bin = venv_python if os.path.exists(venv_python) else sys.executable
    
    try:
        subprocess.run([
            python_bin, "scripts/main.py",
            "--payload_path", payload_path,
            "--user_id", user_id,
            "--job_id", job_id
        ], check=True)
        
        try:
            supabase.table("jobs_status").update({
                "status": "completed",
                "progress_percentage": 100,
                "current_phase": "Pipeline execution finished successfully"
            }).eq("job_id", job_id).execute()
        except Exception as err:
            print(f"[Orchestrator] Failed to update completed status: {err}")
            
    except subprocess.CalledProcessError as e:
        try:
            supabase.table("jobs_status").update({
                "status": "failed",
                "progress_percentage": 100,
                "error_message": f"Subprocess orchestrator crash: {str(e)}"
            }).eq("job_id", job_id).execute()
        except Exception as err:
            print(f"[Orchestrator] Failed to update failed status: {err}")

@app.get("/health")
async def health_check():
    """Chequeo de salud liviano para monitoreo externo (mismo x-api-key que el resto de la API).

    No toca Supabase ni ninguna dependencia externa: si esto responde, el contenedor
    arrancó y el proceso ASGI está vivo. Úsalo con un cron/UptimeRobot para detectar
    un crash-loop en minutos en vez de descubrirlo por accidente (incidente 2026-08-24).
    """
    return {"status": "ok", "service": "ai-lead-prospector-backend"}


DEFAULT_MONTHLY_CREDIT_LIMIT = 300  # ver db/migrations/003_prospecting_credits.sql y directivas/11


def _check_credit_balance(user_id: str, estimated_cost: int) -> None:
    """Billetera de créditos de prospección (Modo Profundo): 1 crédito = 1 empresa
    procesada. Bloquea con 402 si el saldo del mes no alcanza para el peor caso
    de esta corrida (limite_perfiles). Es un gate FUNCIONAL para contabilizar y
    no reventar la cuota de Tavily/Apify — no hay UI de bloqueo en el frontend
    todavía (fuera de alcance actual, ver directivas/11)."""
    try:
        used_result = supabase.rpc("get_monthly_credits_used", {"p_user_id": user_id}).execute()
        used = used_result.data if isinstance(used_result.data, int) else 0
    except Exception as e:
        # Fail-open deliberado: si la tabla/función de créditos no existe todavía
        # (migración 003 no corrida) o Supabase falla, no se bloquea la prospección
        # por un problema de contabilidad — solo se loggea.
        print(f"[Credits] No se pudo verificar el saldo (¿migración 003 aplicada?): {e}")
        return

    try:
        limit_result = (
            supabase.table("prospecting_credit_limits")
            .select("monthly_credit_limit")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        monthly_limit = (
            limit_result.data["monthly_credit_limit"]
            if limit_result.data else DEFAULT_MONTHLY_CREDIT_LIMIT
        )
    except Exception:
        monthly_limit = DEFAULT_MONTHLY_CREDIT_LIMIT

    if used + estimated_cost > monthly_limit:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Saldo de créditos de prospección insuficiente para este mes. "
                f"Usados: {used}/{monthly_limit}. Esta corrida podría consumir hasta "
                f"{estimated_cost} créditos (1 por empresa a procesar). "
                f"Reduce 'Límite de perfiles a analizar' o espera al próximo mes."
            ),
        )


@app.post("/api/v1/prospect", status_code=status.HTTP_202_ACCEPTED)
async def trigger_prospecting_flow(payload: ProspectRequest, background_tasks: BackgroundTasks, x_user_id: str = Header(...)):
    job_id = str(uuid.uuid4())

    # Gate de créditos ANTES de gastar Tavily/Apify: usa limite_perfiles (el tope
    # que el propio usuario pidió) como estimación de peor caso.
    await run_in_threadpool(_check_credit_balance, x_user_id, payload.limite_perfiles or 10)

    try:
        supabase.table("jobs_status").insert({
            "job_id": job_id,
            "user_id": x_user_id,
            "status": "queued",
            "progress_percentage": 0,
            "current_phase": "Pipeline Queued"
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize job in Supabase: {str(e)}")
    
    os.makedirs(".tmp", exist_ok=True)
    temp_file_path = f".tmp/job_{job_id}_payload.json"
    
    full_dump_data = payload.model_dump()
    full_dump_data["user_id"] = x_user_id
    
    with open(temp_file_path, "w") as f:
        json.dump(full_dump_data, f, indent=2)
        
    background_tasks.add_task(execute_pipeline_subprocess, temp_file_path, x_user_id, job_id)
    return {"status": "queued", "job_id": job_id}


@app.post("/api/v1/prospect/fast", status_code=status.HTTP_200_OK)
async def trigger_fast_prospecting(payload: FastProspectRequest, x_user_id: str = Header(...)):
    """Modo Rápido (Express): prospección SÍNCRONA en segundos.

    No usa subprocess ni el pipeline de noticias. Busca contactos por cargo +
    industria + geografía (Tavily), los puntúa por encaje de cargo y los
    persiste en `leads`. Los emails se verifican con Hunter. Devuelve los
    leads de inmediato.
    """
    job_id = str(uuid.uuid4())
    try:
        await run_in_threadpool(
            lambda: supabase.table("jobs_status").insert({
                "job_id": job_id,
                "user_id": x_user_id,
                "status": "processing",
                "progress_percentage": 20,
                "current_phase": "Modo Rápido: buscando contactos",
            }).execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize fast job: {str(e)}")

    try:
        # Import perezoso: aísla cualquier problema de importación al endpoint rápido.
        from scripts.fast_search import run_fast_prospect
        form = payload.model_dump()
        result = await run_in_threadpool(run_fast_prospect, form, x_user_id, job_id)
        await run_in_threadpool(
            lambda: supabase.table("jobs_status").update({
                "status": "completed",
                "progress_percentage": 100,
                "current_phase": f"Modo Rápido finalizado ({result.get('source')})",
            }).eq("job_id", job_id).execute()
        )
        return {"status": "completed", "job_id": job_id, "source": result.get("source"), "leads": result.get("leads", [])}
    except Exception as e:
        try:
            await run_in_threadpool(
                lambda: supabase.table("jobs_status").update({
                    "status": "failed",
                    "progress_percentage": 100,
                    "error_message": f"Fast mode failure: {str(e)}",
                }).eq("job_id", job_id).execute()
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Fast prospecting failure: {str(e)}")

@app.get("/api/v1/prospect/job/{job_id}")
async def get_job_status(job_id: str, x_user_id: str = Header(..., alias="x-user-id")):
    try:
        response = supabase.table("jobs_status").select("*").eq("job_id", job_id).eq("user_id", x_user_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Job record identifier not found.")
        return response.data[0]
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Database lookup failure: {str(e)}")

@app.get("/api/v1/queries")
async def get_saved_queries(x_user_id: str = Header(...)):
    try:
        response = await run_in_threadpool(
            lambda: supabase.table("saved_queries")
            .select("*")
            .eq("user_id", x_user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloud Supabase lookup failure: {str(e)}")


@app.post("/api/v1/queries", status_code=status.HTTP_201_CREATED)
async def create_saved_query(payload: dict, x_user_id: str = Header(...)):
    """Crea una nueva consulta guardada (versión 1).

    Devuelve un OBJETO único (no una lista) para que el frontend pueda leer
    `data.id` y fijar el `activeQueryId`, habilitando el flujo de versionado.
    """
    try:
        now = _utc_now_iso()
        # search_params puede venir embebido o ser el propio payload (legacy).
        search_params = payload.get("search_params", payload)
        # El proxy inyecta user_id dentro del body; lo descartamos del search_params
        # para no contaminar los parámetros de búsqueda con metadatos de identidad.
        if isinstance(search_params, dict):
            search_params = {k: v for k, v in search_params.items() if k not in ("user_id", "query_name", "search_params", "result_job_id", "tags", "parent_query_id")}

        db_payload = {
            "user_id": x_user_id,
            "query_name": payload.get("query_name", f"Query Run {str(uuid.uuid4())[:8]}"),
            "search_params": search_params,
            "version": 1,
            "tags": payload.get("tags", []),
            "result_job_id": payload.get("result_job_id"),
            "parent_query_id": payload.get("parent_query_id"),
            "last_run_at": now if payload.get("result_job_id") else None,
            "updated_at": now,
        }
        response = await run_in_threadpool(
            lambda: supabase.table("saved_queries").insert(db_payload).execute()
        )
        # Normalización: retornar el primer (y único) registro como objeto.
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloud Supabase insertion failure: {str(e)}")


@app.put("/api/v1/queries/{query_id}")
async def update_saved_query(query_id: str, payload: dict, x_user_id: str = Header(...)):
    """Sobreescribe (nueva versión) una consulta existente.

    Lógica de versionado: incrementa `version`, fusiona etiquetas, actualiza
    `updated_at`/`last_run_at` y re-ancla `result_job_id` para que los resultados
    de la ejecución vigente queden ligados a esta versión de la consulta.
    El aislamiento multi-tenant se aplica SIEMPRE con `.eq("user_id", x_user_id)`.
    """
    try:
        # 1. Verificar propiedad antes de mutar (defensa contra IDOR).
        existing = await run_in_threadpool(
            lambda: supabase.table("saved_queries")
            .select("*")
            .eq("id", query_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Saved query not found for this tenant.")

        current = existing.data[0]
        now = _utc_now_iso()
        new_version = int(current.get("version") or 1) + 1

        # Fusión idempotente de etiquetas (sin duplicados, preservando orden).
        incoming_tags = payload.get("tags")
        merged_tags = list(current.get("tags") or [])
        if incoming_tags:
            for t in incoming_tags:
                if t and t not in merged_tags:
                    merged_tags.append(t)

        update_fields = {
            "version": new_version,
            "tags": merged_tags,
            "updated_at": now,
        }
        if "query_name" in payload and payload["query_name"]:
            update_fields["query_name"] = payload["query_name"]
        if "search_params" in payload and isinstance(payload["search_params"], dict):
            sp = {k: v for k, v in payload["search_params"].items() if k != "user_id"}
            update_fields["search_params"] = sp
        if payload.get("result_job_id"):
            # Re-anclaje de resultados a la nueva versión de la consulta.
            update_fields["result_job_id"] = payload["result_job_id"]
            update_fields["last_run_at"] = now

        response = await run_in_threadpool(
            lambda: supabase.table("saved_queries")
            .update(update_fields)
            .eq("id", query_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        return response.data[0] if response.data else {}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Cloud Supabase update failure: {str(e)}")


@app.delete("/api/v1/queries/{query_id}")
async def delete_saved_query(query_id: str, x_user_id: str = Header(...)):
    """Elimina una consulta guardada con verificación estricta de propiedad."""
    try:
        response = await run_in_threadpool(
            lambda: supabase.table("saved_queries")
            .delete()
            .eq("id", query_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Saved query not found for this tenant.")
        return {"status": "deleted", "id": query_id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Cloud Supabase deletion failure: {str(e)}")

@app.get("/api/v1/leads")
async def get_leads(
    job_id: Optional[str] = None,
    x_user_id: str = Header(..., description="Strict user identification extracted from secure session")
):
    try:
        user_id = x_user_id
        query = supabase.table("leads").select("*").eq("user_id", user_id)
        if job_id and job_id.strip() and job_id not in ("undefined", "null", "None"):
            query = query.eq("job_id", job_id)
        # AUDITORÍA #2: ordenar por match_score desc ("los mejores primero").
        # Empate por created_at desc para estabilidad temporal.
        query = query.order("match_score", desc=True).order("created_at", desc=True).limit(500)
        response = query.execute()
        return {"leads": response.data}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cloud Supabase leads retrieval failure: {str(e)}"
        )

@app.get("/api/v1/auth/google/status")
async def get_google_auth_status(x_user_id: str = Header(..., description="Strict user identification extracted from secure session")):
    # Gmail OAuth bypass: always evaluated as connected to allow direct local copy
    return {"connected": True, "is_connected": True}


@app.patch("/api/v1/internal/update-job/{job_id}")
async def update_job_metrics(job_id: str, data: dict):
    """Webhook interno de telemetría invocado por scripts/main.py.

    HARDENING: se aplica una whitelist estricta de columnas mutables para evitar
    asignación masiva (mass-assignment) sobre la tabla jobs_status. El flujo de
    telemetría de BackgroundTasks queda intacto: solo se filtran campos no permitidos.
    """
    ALLOWED_FIELDS = {
        "status",
        "progress_percentage",
        "current_phase",
        "error_message",
        "processed_leads",
        "total_leads",
    }
    sanitized = {k: v for k, v in (data or {}).items() if k in ALLOWED_FIELDS}
    if not sanitized:
        raise HTTPException(status_code=400, detail="No valid mutable fields supplied for job telemetry.")
    sanitized["updated_at"] = _utc_now_iso()
    try:
        response = await run_in_threadpool(
            lambda: supabase.table("jobs_status").update(sanitized).eq("job_id", job_id).execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Target job not found.")
        return {"status": "ok"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Database update failure: {str(e)}")

async def get_fresh_google_token(user_id: str, token_envelope: dict) -> str:
    """Valida y refresca dinámicamente el token de acceso de Google OAuth utilizando el refresh_token si es necesario."""
    refresh_token = token_envelope.get("refresh_token")
    if not refresh_token:
        return token_envelope.get("access_token")
        
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("[OAuth Refresh] GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not defined in environment. Using existing access_token.")
        return token_envelope.get("access_token")
        
    print(f"[OAuth Refresh] Proactively refreshing Google OAuth2 access token for user {user_id}...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                }
            )
            if resp.status_code == 200:
                new_tokens = resp.json()
                new_access_token = new_tokens.get("access_token")
                if new_access_token:
                    # Actualizar el sobre en la base de datos Supabase para futuras peticiones
                    token_envelope["access_token"] = new_access_token
                    try:
                        supabase.table("user_integrations").update({
                            "token_credentials": token_envelope
                        }).eq("user_id", user_id).eq("provider", "google").execute()
                        print("[OAuth Refresh] Successfully updated fresh access_token in Supabase.")
                    except Exception as db_err:
                        print(f"[OAuth Refresh] Failed to persist refreshed Google token in Supabase: {db_err}")
                        
                    return new_access_token
            else:
                print(f"[OAuth Refresh] Google Token Refresh API rejected with status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[OAuth Refresh] Error during Google OAuth token refresh: {e}")
        
    return token_envelope.get("access_token")

# PRODUCTION READY: Fully dynamic Outreach endpoint without simulation variables
@app.post("/api/v1/outreach/send-email", status_code=status.HTTP_200_OK)
async def send_cold_outreach_email(
    payload: SendEmailRequest,
    x_user_id: str = Header(..., description="Secure UUID passed from Next.js server context")
):
    """Retrieves Gemini's personalized draft from database and fires it live via Gmail API utilizing Supabase OAuth link."""
    try:
        # Step 1: Query the lead data from Supabase
        lead_query = supabase.table("leads").select("nombre_lead, empresa, trigger_noticia, mensaje_generado, es_calificado").eq("id", payload.lead_id).eq("user_id", x_user_id).execute()
        if not lead_query.data:
            raise HTTPException(status_code=404, detail="Target lead record not found under this tenant boundary.")
            
        lead_data = lead_query.data[0]
        if not lead_data.get("es_calificado") or not lead_data.get("mensaje_generado"):
            raise HTTPException(status_code=400, detail="This lead cannot be emailed: missing AI personalized draft composition.")

        # Step 2: Extract REAL User Google OAuth Token from Supabase session layer JSON storage
        integration_query = supabase.table("user_integrations").select("token_credentials").eq("user_id", x_user_id).eq("provider", "google").execute()
        if not integration_query.data:
            raise HTTPException(status_code=412, detail="Google account integration missing. Authentication required.")
            
        # Parse the dynamic OAuth access token from the credentials dictionary structure natively
        token_envelope = integration_query.data[0].get("token_credentials", {})
        access_token = await get_fresh_google_token(x_user_id, token_envelope)
        
        if not access_token:
            raise HTTPException(status_code=412, detail="Active access token token missing inside user integration metadata profile.")

        # Step 3: Package raw RFC 2822 email text mapping Gemini's structured fields and user dynamic target
        message = MIMEText(lead_data["mensaje_generado"])
        message['to'] = payload.target_email  # Dynamically routed target parameter
        message['subject'] = lead_data["trigger_noticia"]
        
        # Base64url encoding required by the raw Gmail send API format standard
        raw_base64 = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

        # Step 4: Execute a direct asynchronous HTTP request to the official Google Rest API endpoint
        async with httpx.AsyncClient() as client:
            gmail_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            google_response = await client.post(gmail_url, json={"raw": raw_base64}, headers=headers)
            
            if google_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY, 
                    detail=f"Google API rejection server-side: {google_response.text}"
                )

        return {
            "status": "success", 
            "delivered_to": payload.target_email, 
            "message_id": google_response.json().get("id")
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Outreach transmission catastrophic failure: {str(e)}")



# ══════════════════════════════════════════════════════════════════════════════
#  MINI-CRM INTEGRADO  ─  Pipeline de leads calificados (tablas crm_leads / crm_lead_notes)
#  SOP asociado: directivas/08_crm_pipeline_SOP.md
#  Seguridad: aislamiento multi-tenant estricto vía .eq("user_id", x_user_id) en
#  TODA operación (el service_role bypassea RLS, por lo que el filtro es obligatorio).
# ══════════════════════════════════════════════════════════════════════════════

CRM_VALID_STAGES = {"nuevo", "contactado", "en_conversacion", "propuesta", "ganado", "perdido"}
CRM_VALID_PRIORITIES = {"baja", "media", "alta"}

# Campos del snapshot del lead que se copian al CRM (desacoplados del lead origen).
_CRM_SNAPSHOT_FIELDS = (
    "nombre_lead", "empresa", "cargo", "email", "telefono",
    "linkedin_url", "trigger_noticia", "mensaje_generado", "url_noticia",
)


@app.get("/api/v1/crm/leads")
async def list_crm_leads(x_user_id: str = Header(...)):
    """Lista las tarjetas del CRM del usuario con sus notas internas embebidas."""
    try:
        leads_resp = await run_in_threadpool(
            lambda: supabase.table("crm_leads")
            .select("*")
            .eq("user_id", x_user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        leads = leads_resp.data or []
        lead_ids = [l["id"] for l in leads]

        notes_by_lead: dict = {}
        if lead_ids:
            notes_resp = await run_in_threadpool(
                lambda: supabase.table("crm_lead_notes")
                .select("*")
                .eq("user_id", x_user_id)
                .in_("crm_lead_id", lead_ids)
                .order("created_at", desc=True)
                .execute()
            )
            for note in (notes_resp.data or []):
                notes_by_lead.setdefault(note["crm_lead_id"], []).append(note)

        for lead in leads:
            lead["notes"] = notes_by_lead.get(lead["id"], [])

        return {"crm_leads": leads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CRM lead retrieval failure: {str(e)}")


@app.post("/api/v1/crm/leads", status_code=status.HTTP_201_CREATED)
async def add_crm_lead(payload: dict, x_user_id: str = Header(...)):
    """Envía un lead calificado al CRM.

    Idempotente: si el lead origen (lead_id) ya está en el CRM del usuario, se
    devuelve el registro existente en lugar de duplicarlo (upsert lógico).
    """
    try:
        now = _utc_now_iso()
        lead_id = payload.get("lead_id")

        # Anti-duplicado cuando proviene de un lead real de la tabla `leads`.
        if lead_id is not None:
            existing = await run_in_threadpool(
                lambda: supabase.table("crm_leads")
                .select("*")
                .eq("user_id", x_user_id)
                .eq("lead_id", lead_id)
                .execute()
            )
            if existing.data:
                return existing.data[0]

        stage = payload.get("stage", "nuevo")
        if stage not in CRM_VALID_STAGES:
            stage = "nuevo"
        priority = payload.get("priority", "media")
        if priority not in CRM_VALID_PRIORITIES:
            priority = "media"

        db_payload = {
            "user_id": x_user_id,
            "lead_id": lead_id,
            "job_id": payload.get("job_id"),
            "stage": stage,
            "priority": priority,
            "tags": payload.get("tags", []),
            "created_at": now,
            "updated_at": now,
        }
        for field in _CRM_SNAPSHOT_FIELDS:
            db_payload[field] = payload.get(field)

        response = await run_in_threadpool(
            lambda: supabase.table("crm_leads").insert(db_payload).execute()
        )
        created = response.data[0] if response.data else {}
        created["notes"] = []
        return created
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CRM lead insertion failure: {str(e)}")


@app.patch("/api/v1/crm/leads/{crm_lead_id}")
async def update_crm_lead(crm_lead_id: str, payload: dict, x_user_id: str = Header(...)):
    """Actualiza etapa (Kanban), prioridad y/o etiquetas de una tarjeta del CRM."""
    update_fields: dict = {}

    if "stage" in payload:
        if payload["stage"] not in CRM_VALID_STAGES:
            raise HTTPException(status_code=422, detail=f"Invalid stage. Allowed: {sorted(CRM_VALID_STAGES)}")
        update_fields["stage"] = payload["stage"]

    if "priority" in payload:
        if payload["priority"] not in CRM_VALID_PRIORITIES:
            raise HTTPException(status_code=422, detail=f"Invalid priority. Allowed: {sorted(CRM_VALID_PRIORITIES)}")
        update_fields["priority"] = payload["priority"]

    if "tags" in payload and isinstance(payload["tags"], list):
        update_fields["tags"] = payload["tags"]

    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid mutable CRM fields supplied.")

    update_fields["updated_at"] = _utc_now_iso()

    try:
        response = await run_in_threadpool(
            lambda: supabase.table("crm_leads")
            .update(update_fields)
            .eq("id", crm_lead_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="CRM lead not found for this tenant.")
        return response.data[0]
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"CRM lead update failure: {str(e)}")


@app.delete("/api/v1/crm/leads/{crm_lead_id}")
async def delete_crm_lead(crm_lead_id: str, x_user_id: str = Header(...)):
    """Elimina una tarjeta del CRM (las notas asociadas caen por ON DELETE CASCADE)."""
    try:
        response = await run_in_threadpool(
            lambda: supabase.table("crm_leads")
            .delete()
            .eq("id", crm_lead_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="CRM lead not found for this tenant.")
        return {"status": "deleted", "id": crm_lead_id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"CRM lead deletion failure: {str(e)}")


@app.post("/api/v1/crm/leads/{crm_lead_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_crm_note(crm_lead_id: str, payload: dict, x_user_id: str = Header(...)):
    """Agrega una nota interna a una tarjeta del CRM, validando la propiedad del lead."""
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Note body cannot be empty.")
    try:
        # Validar que la tarjeta pertenece al tenant antes de anexar la nota.
        owner = await run_in_threadpool(
            lambda: supabase.table("crm_leads")
            .select("id")
            .eq("id", crm_lead_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        if not owner.data:
            raise HTTPException(status_code=404, detail="CRM lead not found for this tenant.")

        now = _utc_now_iso()
        note_payload = {
            "crm_lead_id": crm_lead_id,
            "user_id": x_user_id,
            "body": body,
            "created_at": now,
        }
        response = await run_in_threadpool(
            lambda: supabase.table("crm_lead_notes").insert(note_payload).execute()
        )
        # Tocar updated_at del lead para que ascienda en el ordenamiento del board.
        await run_in_threadpool(
            lambda: supabase.table("crm_leads")
            .update({"updated_at": now})
            .eq("id", crm_lead_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        return response.data[0] if response.data else {}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"CRM note insertion failure: {str(e)}")


@app.delete("/api/v1/crm/notes/{note_id}")
async def delete_crm_note(note_id: str, x_user_id: str = Header(...)):
    """Elimina una nota interna con verificación de propiedad."""
    try:
        response = await run_in_threadpool(
            lambda: supabase.table("crm_lead_notes")
            .delete()
            .eq("id", note_id)
            .eq("user_id", x_user_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="CRM note not found for this tenant.")
        return {"status": "deleted", "id": note_id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"CRM note deletion failure: {str(e)}")
