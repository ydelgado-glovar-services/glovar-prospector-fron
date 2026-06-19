# app.py
import os
import uuid
import json
import sys
import subprocess
import base64
from email.mime.text import MIMEText
from typing import List, Optional
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    expected_key = os.getenv("GLOVAR_BACKEND_API_KEY")
    if not expected_key:
        return
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Glovar Backend API Key"
        )

app = FastAPI(
    title="Glovar Lead Prospector Enterprise API",
    version="3.9.0",
    dependencies=[Depends(verify_api_key)]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

@app.post("/api/v1/prospect", status_code=status.HTTP_202_ACCEPTED)
async def trigger_prospecting_flow(payload: ProspectRequest, background_tasks: BackgroundTasks, x_user_id: str = Header(...)):
    job_id = str(uuid.uuid4())
    
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
        response = supabase.table("saved_queries").select("*").eq("user_id", x_user_id).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloud Supabase lookup failure: {str(e)}")

@app.post("/api/v1/queries", status_code=status.HTTP_201_CREATED)
async def create_saved_query(payload: dict, x_user_id: str = Header(...)):
    try:
        db_payload = {
            "user_id": x_user_id,
            "query_name": payload.get("query_name", f"Query Run {str(uuid.uuid4())[:8]}"),
            "search_params": payload.get("search_params", payload)
        }
        response = supabase.table("saved_queries").insert(db_payload).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloud Supabase insertion failure: {str(e)}")

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
        query = query.order("created_at", desc=True).limit(500)
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
    try:
        response = supabase.table("jobs_status").update(data).eq("job_id", job_id).execute()
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