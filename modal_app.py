# modal_app.py
import os
import modal
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local para la cosecha de secretos en el despliegue
load_dotenv()

# 1. Definir la imagen y dependencias del contenedor
# Copiaremos los directorios necesarios y la app FastAPI principal para su ejecución en la nube.
image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements("requirements.txt")
    .pip_install("fastapi", "uvicorn")
    .add_local_dir("scripts", "/root/scripts")
    .add_local_file("app.py", "/root/app.py")
)

# 2. Definir la aplicación en Modal
app = modal.App("glovar-prospector-backend")

# 3. Registrar secretos de entorno dinámicos heredados del entorno local de producción
secret_keys = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "TAVILY_API_KEY",
    "HUNTER_API_KEY",
    "APOLLO_API_KEY",
    "APIFY_API_TOKEN",
    "GLOVAR_BACKEND_API_KEY",
    "INTERNAL_BACKEND_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET"
]

secrets_dict = {}
for key in secret_keys:
    secrets_dict[key] = os.getenv(key, "")

# Inyectar dinámicamente todo el pool rotativo de Groq (GROQ_API_KEY, GROQ_API_KEY_1...9)
if os.getenv("GROQ_API_KEY"):
    secrets_dict["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
for i in range(1, 10):
    var_name = f"GROQ_API_KEY_{i}"
    if os.getenv(var_name):
        secrets_dict[var_name] = os.getenv(var_name)

secrets = [modal.Secret.from_dict(secrets_dict)]

# 4. Envolver FastAPI como una aplicación ASGI Serverless
@app.function(
    image=image,
    secrets=secrets,
    max_containers=10, # Horizontal scaling for concurrent commercial prospecting jobs
    timeout=900,         # 15 minutes to handle deep scraping + enrichment flows
    memory=2048,         # 2 GB RAM — required for 3 concurrent worker subprocesses (news + leads + validator per company)
)
@modal.asgi_app()
def api():
    # Importación interna y ajuste de path para evitar fallas durante la construcción local de la imagen
    import sys
    sys.path.append("/root")
    from app import app as fastapi_app
    return fastapi_app
