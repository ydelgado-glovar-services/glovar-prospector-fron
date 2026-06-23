# GLOVAR PROSPECTOR — ARQUITECTURA TÉCNICA Y MANUAL DE OPERACIÓN
**Versión de Producción:** `3.13.0`  
**Autoría:** Glovar Services & Antigravity AI  

> **Changelog 3.13.0 — Dos modos de prospección + UX simplificada**
> - **⚡ Modo Rápido (Express):** lista de contactos en segundos (sin noticias). Proveedor intercambiable Apollo → fallback Tavily+Hunter. Endpoint síncrono `POST /api/v1/prospect/fast`. Ver `directivas/10_fast_mode_SOP.md`.
> - **UX estilo Enginy:** input en lenguaje natural ("Describe tu cliente ideal") + toggle de modo; en Modo Rápido los campos profundos quedan ocultos/opcionales.
> - **🔍 Modo Profundo:** el pipeline de señales/noticias existente, intacto.
> - Nuevo `scripts/fast_search.py` + `compute_fast_match` (scoring sin intent).

> **Changelog 3.12.0 — Motor de Scoring ICP (Fit + Intent)**
> - **Calificación FIT-FIRST:** se deja de descartar empresas por falta de noticias. Se puntúa FIT (ICP) e INTENT (trigger) 0–100; alto fit sin trigger sigue calificado (nurture). Ver `directivas/09_lead_scoring_engine_SOP.md`.
> - **Scoring + ranking:** `match_score` (0–100) + tier A/B/C/D; los leads se ordenan por los mejores primero. Nuevo `scripts/scoring.py`.
> - **Determinismo:** `temperature=0.1` en toda la calificación (resultados reproducibles).
> - **Descubrimiento ampliado:** 3 consultas Tavily multi-ángulo + el slider "Límite de perfiles" ahora controla el cap real de empresas.
> - **Verificación de email:** se distingue email verificado (Apollo/Hunter) vs inferido por patrón (badge "Estimado").
> - **Modelo Groq configurable:** `GROQ_MODEL_REASONING` / `GROQ_MODEL_FAST`.
> - **Migración DB:** `db/migrations/002_lead_scoring_and_email_verification.sql`.

> **Changelog 3.11.0**
> - **Fix crítico de build:** el `.gitignore` raíz (plantilla Python) ignoraba la carpeta `lib/` del frontend; se ancló a `/lib/` y se restauraron `lib/{types,api,utils}.ts`.
> - **Guardado de consultas con versionado:** nuevos endpoints `PUT`/`DELETE /api/v1/queries/{id}`, `POST` devuelve objeto único, anclaje de resultados (`result_job_id`) por versión. Ver `directivas/07_saved_queries_versioning_SOP.md`.
> - **Mini-CRM integrado:** tablas `crm_leads`/`crm_lead_notes`, endpoints `/api/v1/crm/*`, apartado Kanban "Mis Leads / CRM". Ver `directivas/08_crm_pipeline_SOP.md`.
> - **Hardening:** CORS configurable (`ALLOWED_ORIGINS`), whitelist en el webhook interno de telemetría, llamadas Supabase en `run_in_threadpool`.
> - **Migración DB:** `db/migrations/001_saved_queries_versioning_and_crm.sql`.

---

## 1. Introducción al Sistema
**Glovar Prospector** es una plataforma empresarial avanzada de **inteligencia comercial y prospección autónoma B2B**. Diseñada especialmente para el sector logístico y de ciencias de la vida, utiliza un motor RAG (Generación Aumentada por Recuperación) cognitivo y multi-agente para descubrir prospectos corporativos, rastrear hitos de crecimiento recientes en tiempo real, identificar tomadores de decisiones clave en LinkedIn, enriquecer datos de contacto corporativos directos y generar secuencias hiper-personalizadas de correo frío orientadas al dolor operacional del cliente.

---

## 2. Stack Tecnológico de la Arquitectura
El sistema está construido bajo una filosofía **decapitada (headless), serverless y de alta concurrencia**:

```
 ┌────────────────────────────────────────────────────────┐
 │           Frontend UI (Next.js 16 / React 19)          │
 │   - Dashboard ejecutivo con distribución de leads      │
 │   - Gestión en tiempo real del progreso de Jobs        │
 │   - Editor interactivo de copys / Aprobación Manual    │
 └───────────────────────────┬────────────────────────────┘
                             │ (API HTTPS / JSON JWT)
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │            Backend FastAPI (Orquestador Core)          │
 │   - Uvicorn (Puerto 8000), FastAPI Router              │
 │   - BackgroundTasks para subprocesos locales (.venv)   │
 │   - Endpoint interno de telemetría de Jobs             │
 └───────────────────────────┬────────────────────────────┘
                             ├────────────────────────────┐
                             │ (Async Subprocesses)       │ (Serverless Deployment)
                             ▼                            ▼
 ┌────────────────────────────────────────────────────────┐ ┌─────────────────────────┐
 │            Pipeline de Prospección (Python 3)          │ │    Modal Container      │
 │  - scripts/main.py (Orquestador Central)               │ │  (Servidor Backend      │
 │  - scripts/news_scraper.py (Cognitive Search Planner)  │ │  Autónomo de 2GB RAM    │
 │  - scripts/lead_scraper.py (Apify + Hunter.io API)    │ │   y autoescalable)      │
 │  - scripts/validator.py (RAG & Llama-4-Scout Audit)    │ └─────────────┬───────────┘
 └───────────────────────────┬────────────────────────────┘               │
                             │ (Secure SSL Client / RLS Active)           │
                             ▼                                            │
 ┌────────────────────────────────────────────────────────────────────────┴┐
 │                 Data Cluster (Cloud Supabase - PostgreSQL)              │
 │  - Tablas: leads, jobs_status, saved_queries, user_profiles,            │
 │            crm_leads, crm_lead_notes                                     │
 │  - Políticas de Aislamiento de Clientes (Row Level Security - RLS)      │
 └─────────────────────────────────────────────────────────────────────────┘
```

### Componentes Críticos del Stack:
1. **Frontend (Dashboard)**: Next.js `16.2.6` (React 19, Turbopack) + TailwindCSS `v4.0.0` + Radix UI + Recharts para visualización de métricas de embudo.
2. **Backend**: FastAPI `0.115` + Uvicorn. Administra la autenticación del usuario, persistencia de consultas, y expone los webhooks de telemetría interna.
3. **Container Serverless (Modal)**: Modal (`modal_app.py`) empaqueta y despliega la aplicación de FastAPI a la nube serverless de Modal con autoescalado horizontal (hasta 10 contenedores concurrentes), límites de tiempo de ejecución de 15 minutos (`timeout=900`) y asignación de 2GB de RAM para evitar cuellos de botella durante las corridas de concurrencia.
4. **Data Cluster**: Cloud Supabase (PostgreSQL 17.6) provisto de políticas RLS estrictas y esquemas relacionales robustos.
5. **Modelos de Inferencia**: Rotador determinista de claves de API de Groq en base al hash de la empresa para consumir de forma segura **Llama 4 Scout** (`meta-llama/llama-4-scout-17b-16e-instruct`), garantizando consistencia, velocidad lógica y cero "frío" inicial.

---

## 3. Catálogo de Base de Datos (Cloud Supabase)
Supabase actúa como el estado único de la verdad. A continuación se desglosa el diccionario de datos relacionales:

### A. Tipos de Datos (Enums)
*   **`user_role`**: Permite Control de Acceso Basado en Roles (RBAC).  
    *Valores:* `admin`, `client`
*   **`job_state`**: Monitorea el ciclo de vida del pipeline.  
    *Valores:* `queued`, `processing`, `completed`, `failed`

### B. Tabla: `jobs_status`
Almacena el registro de ejecución y el progreso de los procesos de prospección asíncronos.
*   **RLS**: Habilitado.

| Columna | Tipo de Datos | Nulabilidad | Descripción |
| :--- | :--- | :--- | :--- |
| `job_id` | `uuid` | `NOT NULL` | Identificador único de ejecución (Primary Key) |
| `user_id` | `uuid` | `NOT NULL` | ID del usuario propietario de la ejecución |
| `status` | `job_state` | `NOT NULL` | Estado actual (`queued`, `processing`, etc.) |
| `progress_percentage` | `integer` | `NOT NULL` | Progreso porcentual (0 a 100) |
| `current_phase` | `character varying` | `NOT NULL` | Descripción de la fase en tiempo real (Sincronizado vía webhook) |
| `error_message` | `text` | `NULL` | Detalle del error si el estado es `failed` |
| `created_at` | `timestamp with time zone` | `NOT NULL` | Fecha de creación del Job |
| `updated_at` | `timestamp with time zone` | `NOT NULL` | Última actualización |

*Políticas de Seguridad (RLS):*
*   `Users can insert their own jobs`: `auth.uid() = user_id` (INSERT)
*   `Users can only view their own jobs`: `auth.uid() = user_id` (SELECT)
*   `Users can update their own jobs`: `auth.uid() = user_id` (UPDATE)

---

### C. Tabla: `leads`
La tabla nuclear que contiene el output final del enriquecimiento y la auditoría RAG.
*   **RLS**: Habilitado.

| Columna | Tipo de Datos | Nulabilidad | Descripción |
| :--- | :--- | :--- | :--- |
| `id` | `bigint` | `NOT NULL` | Identificador único de lead (Primary Key secuencial) |
| `created_at` | `timestamp with time zone` | `NOT NULL` | Fecha de prospección |
| `nombre_lead` | `text` | `NULL` | Nombre del prospecto (o `Contacto Pendiente` para fallback) |
| `empresa` | `text` | `NULL` | Nombre de la compañía prospectada |
| `cargo` | `text` | `NULL` | Cargo funcional extraído de LinkedIn |
| `linkedin_url` | `text` | `NULL` | Enlace al perfil de LinkedIn |
| `email` | `text` | `NULL` | Correo electrónico directo (Enriquecido por Hunter.io) |
| `telefono` | `text` | `NULL` | Teléfono corporativo |
| `url_noticia` | `text` | `NULL` | Enlace a la noticia/artículo gatillador del trigger |
| `trigger_noticia` | `text` | `NULL` | Resumen conceptual de la noticia |
| `mensaje_generado` | `text` | `NULL` | Cuerpo del correo hiper-personalizado redactado por el LLM |
| `es_calificado` | `boolean` | `NULL` | Bandera de aprobación comercial (`true`/`false`) |
| `razonamiento_filtro` | `text` | `NULL` | Justificación estructurada de 3 puntos (Fase 2) |
| `user_id` | `uuid` | `NULL` | Propietario del lead |
| `job_id` | `uuid` | `NULL` | JobID origen |

*Políticas de Seguridad (RLS):*
*   `client_isolation_policy`: Aislamiento a nivel de cliente (`auth.uid() = user_id` para todas las operaciones).
*   `admin_read_all_policy`: Permite a los administradores (`role = 'admin'`) consultar leads de todos los clientes para propósitos de auditoría comercial.

---

## 4. Detalle y Flujo de los Scripts del Pipeline

El pipeline de prospección asíncrono se compone de cuatro scripts en Python que se ejecutan en cascada dentro del contenedor. Todos implementan **delays preventivos estrictos** (pacing) para eludir límites de tasas de API (Rate Limits) en Groq y Tavily.

```
 ┌────────────────────────────────────────────────────────┐
 │                      scripts/main.py                   │
 │                Orquestador y Hub Central               │
 └───────────────────────────┬────────────────────────────┘
                             ▼ (Pre-flight Parser LLM)
 ┌────────────────────────────────────────────────────────┐
 │                Intento Estratégico (Fase 0)            │
 └───────────────────────────┬────────────────────────────┘
                             ▼ (Tavily Target Search)
 ┌────────────────────────────────────────────────────────┐
 │           Descubrimiento de Empresas (Max 20)          │
 └───────────────────────────┬────────────────────────────┘
                             ▼ (ThreadPoolExecutor Concurrente x3)
 ┌────────────────────────────────────────────────────────┐
 │            Bucle por Empresa Descubierta               │
 ├────────────────────────────────────────────────────────┤
 │                                                        │
 │  1. scripts/news_scraper.py (Fase 1: Cognitive Plan)    │
 │     └─ Escribe: .tmp/news_{company}.json               │
 │                                                        │
 │  2. scripts/lead_scraper.py (LinkedIn + Hunter)        │
 │     └─ Escribe: .tmp/leads_{company}.json              │
 │                                                        │
 │  3. scripts/validator.py (Fase 2: RAG & Persistence)   │
 │     └─ Guarda directo en Supabase DB                   │
 │                                                        │
 └────────────────────────────────────────────────────────┘
```

---

### A. Orquestador Central: `scripts/main.py`
Es el punto de entrada de la ejecución asíncrona. Maneja la orquestación semántica, el procesamiento multihilo por lotes de empresas, y la telemetría progresiva hacia Supabase.

*   **Entradas:**
    *   `--payload_path`: Ruta absoluta al archivo JSON temporal con el onboarding del cliente (bodys de dolor, valor, exclusiones, etc.).
    *   `--user_id`: UUID del cliente.
    *   `--job_id`: UUID único del job creado.
*   **Proceso Interno:**
    1.  **Fase 0: Pre-flight Cognitive Intent Parser:** Lee los campos crudos del formulario y ejecuta a `Llama 4 Scout` para extraer un manifiesto cognitivo de alta precisión:
        *   `optimized_search_tokens`: Los 4 mejores términos en inglés/español para búsquedas orgánicas.
        *   `target_industry_core`: Nicho normalizado en inglés.
        *   `b2b_buying_trigger_context`: Traducciòn explícita del detonante del dolor de compra.
        *   `rigorous_pain_framework`: Marco académico del fallo operacional del prospecto.
        *   `target_market_region`: Normalización geográfica del mercado objetivo.
        *   Este manifiesto se almacena de inmediato en `.tmp/active_runtime_context.json` bajo la clave `"extracted_intent"`.
    2.  **Company Discovery:** Utiliza `Tavily Search API` inyectando los tokens cognitivos calculados para descubrir entre 15 y 20 empresas reales del perfil objetivo en la geografía indicada.
    3.  **Filtro de Lista de Exclusión (Blacklist):** Realiza un filtrado primario cruzando la lista con la propiedad `exclusion_list` provista por el payload del usuario.
    4.  **Ejecución Multihilo Concurrente (`ThreadPoolExecutor`):** Inicializa 3 hilos de trabajo paralelos. Para cada empresa limpia de la lista, ejecuta secuencialmente las llamadas internas de `news_scraper`, `lead_scraper` y `validator`.
    5.  **Control de Idempotencia por Supabase:** Antes de procesar una empresa del lote, consulta la tabla `leads` en Supabase. Si la empresa ya cuenta con registros para ese `job_id`, salta el análisis de inmediato, mitigando el sobreconsumo de créditos de API en caso de reanudaciones tras reinicios inesperados.
    6.  **Piping de Estado:** Invoca el endpoint `/api/v1/internal/update-job/{job_id}` del backend para actualizar la fase actual y el porcentaje de progreso (10% a 100%) visible en el dashboard.
*   **Salidas:**
    *   Archivos de intercambio temporal en `.tmp/` (`news_{company}.json` y `leads_{company}.json`).
    *   Orquestación de la persistencia directa en base de datos.
    *   Limpieza segura de los archivos staging locales al culminar.

---

### B. Cognitive Search & News Scraper: `scripts/news_scraper.py`
Localiza hitos de crecimiento recientes y críticos (2025/2026) que justifiquen una prospección contextualizada.

*   **Entradas:**
    *   Nombre de la empresa objetivo (argumento del módulo).
    *   Contexto del manifiesto estratégico extraído en la Fase 0 (`.tmp/active_runtime_context.json`).
*   **Proceso Interno:**
    1.  **Fase 1: Cognitive Query Planner:** La IA evalúa la intención comercial y genera secuencialmente 3 consultas de búsqueda súper-dirigidas para la empresa:
        *   *Query de Expansión:* Enfoque en aperturas de sedes, contrataciones o nuevos proyectos.
        *   *Query Regulatoria/Dolor:* Enfoque en normativas locales (ej. INVIMA BPM) y retos de suministro.
        *   *Query Social/Comercial:* Enfocado en hitos o disrupciones de mercado.
    2.  **Scraping y Extracción Avanzada:** Dispara las búsquedas mediante `Tavily Search API`. Toma los 3 mejores enlaces de noticias y realiza un raspado profundo mediante `Tavily Extract API` para digerir el contenido HTML crudo a texto limpio.
    3.  **Filtrado Semántico de Noticias por IA:** Evalúa el texto consolidado mediante Llama 4 Scout. Asigna un score de relevancia basado en si la noticia refleja un trigger válido 2025/2026 alineado al mercado del cliente y descarta contenido genérico (blogs, comunicados vagos).
*   **Salidas:**
    *   Escribe `.tmp/news_{company}.json` conteniendo el trigger seleccionado, la noticia líder y su URL origen. Si no se hallan noticias válidas, marca el archivo con un trigger nulo para su descalificación en cascada.

---

### C. Lead Discoverer & Enriched Scraper: `scripts/lead_scraper.py`
Localiza decisores óptimos en LinkedIn y enriquece sus correos y dominios corporativos.

*   **Entradas:**
    *   Nombre de la empresa.
    *   Payload de la consulta (`cargo_decision` y `tamano_empresa`).
*   **Proceso Interno:**
    1.  **LinkedIn Scraping:** Construye consultas dirigidas de LinkedIn en base a los cargos parametrizados en el frontend (ej. `VP Supply Chain LATAM`, `Director Logística`). Invoca a `Apify google-search-scraper` para extraer las URLs de los perfiles públicos que rankean en Google para esos roles.
    2.  **Cortafuegos Determinista (Pre-Validación en Python):** Para cada perfil encontrado, ejecuta validaciones lógicas locales antes de llamar APIs de pago:
        *   **is_valid_human_role:** Elimina perfiles no humanos, robots de indexación o páginas corporativas.
        *   **Mismatch Check:** Compara si el título extraído y el nombre coinciden verdaderamente con la empresa objetivo.
    3.  **Resolución de Dominio y Hunter.io:** Si el perfil es válido, localiza el dominio B2B de la empresa a través de una consulta ligera de Tavily y utiliza `Hunter.io Email Finder API` con el nombre del lead y el dominio corporativo resuelto para obtener el correo electrónico comercial.
    4.  **Fallback de Prospección Manual (Contacto Pendiente):** Si la empresa tiene un trigger comercialmente válido pero no fue posible localizar un decisor por LinkedIn de forma automatizada, crea un registro clasificado como `Contacto Pendiente` con cargo `Prospección Manual Pendiente` e email `None`, permitiendo que el cliente en el frontend asigne el perfil de forma manual en lugar de perder la cuenta.
*   **Salidas:**
    *   Escribe `.tmp/leads_{company}.json` con el listado de leads enriquecidos, estatus de validez y dominios.

---

### D. RAG Auditor & Copywriter: `scripts/validator.py`
Lleva a cabo la auditoría cruzada conceptual definitiva y redacta los correos de conversión en frío.

*   **Entradas:**
    *   Nombre de la empresa.
    *   UUID del usuario y UUID del Job.
    *   Archivos temporales `.tmp/news_{company}.json` y `.tmp/leads_{company}.json`.
*   **Proceso Interno:**
    1.  **Fase 2: Rigorous Pain Framework Integration:** Toma el manifiesto de dolor del runtime context y lo inserta en el prompt de Llama 4 Scout.
    2.  **Cortocircuito de Inferencia:** Si el lead viene marcado como pre-descalificado (por rol inválido o mismatch en `lead_scraper`), escribe directamente en Supabase con `es_calificado = false` en milisegundos, eludiendo la llamada del LLM por completo.
    3.  **Auditoría de Inferencia Cruzada:** Si el lead es apto, el LLM audita la cuenta bajo 3 pilares lógicos:
        *   *Punto 1 (Hecho Noticioso Detonante):* Fáctico, verídico y temporalmente acotado (2025/2026).
        *   *Punto 2 (Impacto Operativo Deductivo):* Mapeo del dolor del prospecto frente a la normativa (ej. INVIMA, rupturas de cadena de frío).
        *   *Punto 3 (Encaje de Rol):* Responsabilidad del decisor en mitigar ese dolor.
    4.  **Redacción de Email Conversivo en Frío:** Si es aprobado, redacta un correo hiper-personalizado en español de un máximo de 150 palabras. Inserta la propuesta de valor del cliente de forma fluida y sin sonar spammer.
    5.  **Persistencia en Supabase:** Realiza la inserción directa de los campos (leads válidos y calificados con `es_calificado = true`, empresas con `Contacto Pendiente`, y descartes con `es_calificado = false`).
*   **Salidas:**
    *   Escritura de registros permanentes en la tabla `leads` de Supabase.

---

## 5. Conexión del Backend con Modal y Cloud Supabase

La conexión serverless y distribuida opera bajo un flujo dinámico y seguro:

### A. Despliegue en Modal (`modal_app.py`)
Modal empaqueta el backend en un entorno Linux Debian Slim. Instala las dependencias declaradas en `requirements.txt`, añade el directorio de `scripts/` y el archivo `app.py` en la raíz `/root` del contenedor virtual.
*   **Cosecha Dinámica de Secretos:** Modal hereda las variables de entorno de producción local (`SUPABASE_URL`, `TAVILY_API_KEY`, `HUNTER_API_KEY`, etc.) y las inyecta como secretos seguros de Modal.
*   **Autoescalado Concurrente:** El contenedor permite hasta 10 instancias paralelas ante ráfagas de peticiones concurrentes del frontend.
*   **Pool Rotativo de Groq:** Inyecta en el contenedor las claves desde `GROQ_API_KEY_1` hasta `GROQ_API_KEY_9` para la rotación stateless en los scripts de ejecución.

### B. Flujo de Telemetría (Piping de Jobs)
Cuando un usuario dispara una prospección en el frontend, FastAPI corre un `BackgroundTasks` que ejecuta el subproceso del orquestador (`main.py`). A medida que `main.py` recorre las empresas del lote, este se comunica de vuelta mediante el endpoint local o en la nube `PATCH /api/v1/internal/update-job/{job_id}` actualizando a Supabase en vivo. Esto permite que el componente de progreso en Next.js muestre la fase real y porcentaje (ej. *"Procesando activo: Syneos Health (40%)"*) de forma fluida y reactiva.

### C. Row Level Security (RLS) en Supabase
El frontend Next.js realiza consultas directas de leads y perfiles de usuario utilizando el cliente `@supabase/supabase-js`. Gracias a las políticas RLS implementadas en Postgres, Supabase valida el JSON Web Token (JWT) de la sesión del usuario contra el campo `user_id` de las tablas `leads` y `jobs_status`, garantizando un aislamiento del 100% de la información comercial entre diferentes clientes (Multi-Tenant).

---

## 6. Comandos de Ejecución y Pruebas locales

### Instalación y Setup:
```bash
# 1. Clonar el repositorio e inicializar el entorno virtual
python -m venv .venv
source .venv/Scripts/activate # En Windows

# 2. Instalar dependencias requeridas
pip install -r requirements.txt

# 3. Configurar variables de entorno (.env) en la raíz
# Ingrese claves para SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TAVILY_API_KEY, HUNTER_API_KEY, etc.
```

### Ejecutar Servidor Backend en Local (FastAPI):
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Probar Pipeline Autónomo de Prospección (Script Directo):
```bash
# Ejecutar una prospección utilizando el payload de formulario cacheado en disco
python scripts/main.py --payload_path .tmp/dynamic_form_payload.json --user_id a7b1d5a9-15c8-45e6-8045-09f03dfae1a0 --job_id ee74bd37-ce5b-4f7c-9f5a-87cc817a663f
```

### Desplegar Backend a la Nube Serverless (Modal):
```bash
# 1. Autenticar cli de Modal
modal setup

# 2. Desplegar aplicación en producción serverless
modal deploy modal_app.py
```
> [!IMPORTANT]
> **Monitoreo de Infraestructura:** El despliegue generará un URL público SSL administrado por Modal. El frontend de Next.js debe apuntar sus endpoints de prospección (`NEXT_PUBLIC_BACKEND_API_URL`) a esta dirección de producción para disparar la computación distribuida.
