# DIRECTIVE: MODAL_PRODUCTION_DEPLOYMENT_SOP

> **ID:** SOP-DEPLOY-006
> **Script Asociado:** `modal_app.py`, `app.py`, `scripts/main.py`
> **Estado:** ACTIVO

## 1. Objetivos y Alcance
- **Objetivo Principal:** Documentar el estándar de despliegue en producción serverless del backend FastAPI a la nube de Modal.
- **Eficiencia y Escalabilidad:** Modal opera bajo demanda con escalado automático a cero, absorbiendo hilos concurrentes de scraping a través de contenedores aislados y paralelos, eliminando la necesidad de servidores dedicados (Railway/Render) de costo ocioso fijo.

---

## 2. Contrato de Configuración y Parámetros de Modal
- **Nombre de la Aplicación (ASGI):** `glovar-prospector-backend`
- **Manejador ASGI:** `api` apuntando a `from app import app as fastapi_app`
- **Límites de Concurrencia de Contenedores:**
  - El decorador `@app.function(...)` debe usar **`max_containers=10`** para permitir ejecuciones de prospección paralelas en lotes simultáneos de hasta 10 instancias.
- **Memoria de Contenedor:** **`memory=2048`** (2 GB de RAM declarados explícitamente). Requerido para absorber la carga de 3 workers concurrentes (`ThreadPoolExecutor(max_workers=3)`) con subprocesos Python simultáneos realizando peticiones HTTP paralelas a Tavily, Apify y Groq.
- **Tiempo de Espera Máximo (Timeout):** Configurado a **`900` segundos (15 minutos)** para prevenir interrupciones prematuras en flujos profundos de scraping y enriquecimiento B2B de LinkedIn.

---

## 3. Inyección Dinámica de Secretos (Dynamic Harvesting)
- El contenedor de Modal no almacena llaves en disco de forma estática.
- **Algoritmo de Cosecha Local:** `modal_app.py` debe leer dinámicamente el archivo `.env` del desarrollador en el momento del despliegue para inyectar los secretos en la nube:
  1. Claves de autenticación base: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `TAVILY_API_KEY`, `HUNTER_API_KEY`, `APOLLO_API_KEY`, `APIFY_API_TOKEN`.
  2. Firma de seguridad de red backend-frontend contra Spoofing (STRIDE): `GLOVAR_BACKEND_API_KEY`.
  3. Enlace de telemetría: `INTERNAL_BACKEND_URL` (Debe coincidir con la URL pública HTTPS de Modal).
  4. Pool rotativo de Groq: Un bucle dinámico debe cosechar todas las claves declaradas bajo el patrón `GROQ_API_KEY_X` (del 1 al 9) e inyectarlas al pool en la nube.

---

## 4. Gobernanza del Empaquetado y Limpieza
- **Prohibición de Directivas en la Nube:** El directorio `directivas/` contiene pautas operativas exclusivas para agentes de IA en desarrollo y **debe ser excluido** de la imagen de producción en Modal para mantener el contenedor liviano y veloz.
- **Aislamiento Efímero:** El almacenamiento temporal `.tmp/` se descarta y destruye automáticamente al finalizar cada ejecución de prospección, garantizando el aislamiento absoluto de datos entre inquilinos.

---

## 5. Requerimientos de Seguridad de Supabase (Políticas de Grants)
- A partir del 30 de Mayo de 2026, toda nueva tabla en el esquema público de Supabase requiere un otorgamiento de permisos (`GRANT`) explícito para ser leída por la API de Datos (supabase-js).
- **Lógica Obligatoria:** Habilitar grants para roles públicos y autenticados:
  ```sql
  GRANT ALL ON TABLE public.leads TO anon, authenticated, service_role;
  GRANT ALL ON TABLE public.jobs_status TO anon, authenticated, service_role;
  GRANT ALL ON TABLE public.saved_queries TO anon, authenticated, service_role;
  GRANT ALL ON TABLE public.user_profiles TO anon, authenticated, service_role;
  GRANT ALL ON TABLE public.user_integrations TO anon, authenticated, service_role;
  ```
