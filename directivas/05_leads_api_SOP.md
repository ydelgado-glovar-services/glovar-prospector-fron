# DIRECTIVA: LEADS_API_SCHEMA_SOP

> **ID:** SOP-LEADS-API-005
> **Script Asociado:** `app.py`
> **Estado:** ACTIVO

## 1. Objetivos y Alcance
- **Objetivo Principal:** Documentar el contrato de API para la recuperación asíncrona de prospectos (leads) calificados/descalificados por parte del frontend.
- **Alineación con el Frontend:** El frontend de Next.js (`app/dashboard/page.tsx`) espera recuperar los leads estructurados en un formato de envoltorio específico (`leadsData.leads ?? []`). Este SOP garantiza la inmutabilidad y compatibilidad de este contrato para evitar que la interfaz colapse o muestre pantallas vacías.

---

## 2. Contrato de la API (Endpoint Schema)
- **Ruta del Endpoint:** `GET /api/v1/leads`
- **Método HTTP:** `GET`
- **Cabeceras Obligatorias (Headers):**
  - `x-user-id`: Identificación única y segura del usuario (UUID) extraída del contexto de sesión activa del frontend de Next.js.
  - `x-api-key`: Clave API interna (`GLOVAR_BACKEND_API_KEY`) compartida entre el servidor proxy de Next.js y el backend serverless de Modal para mitigar Spoofing (STRIDE).
- **Parámetros Opcionales (Query Params):**
  - `job_id`: Identificador único de ejecución (UUID) para aislar resultados y evitar filtración de datos de otros jobs.

---

## 3. Lógica de Negocio y Formato de Respuesta
- **Consulta a la Base de Datos (Cloud Supabase):**
  - Tabla objetivo: `leads`
  - Filtro base: `user_id == x_user_id` (a través de la cabecera `x-user-id`).
  - Filtro opcional: `job_id == job_id` (si se proporciona el query parameter `job_id` para aislar resultados de dashboard).
  - Ordenación: `created_at` en orden descendente (`desc=True`) para priorizar la visualización de los prospectos calificados más recientemente.
  - Límite estricto: Limitado a 500 registros (`limit(500)`) para asegurar tiempos de respuesta óptimos y estabilidad.
- **Envoltorio JSON de Respuesta (Response Envelope):**
  - La respuesta debe retornar obligatoriamente un objeto JSON que encapsule la lista de registros recuperados bajo la clave `"leads"`:
    ```json
    {
      "leads": [
        {
          "id": 123,
          "nombre_lead": "Esteban Alvarado",
          "empresa": "Example Corp",
          "cargo": "VP Operations",
          "es_calificado": true,
          "mensaje_generado": "Estimado Esteban...",
          "url_noticia": "[{\"title\":\"Hito de Crecimiento\",\"url\":\"https://...\"}]",
          "created_at": "2026-05-24T18:00:00Z"
        }
      ]
    }
    ```
  - **Soporte Dinámico de Noticias (`url_noticia`):** El backend recupera y sirve la columna `url_noticia` sin alterar su formato. Dicha columna puede almacenar tanto un string plano (enlace único histórico) como una lista JSON serializada con múltiples noticias/triggers descubiertos. El frontend se encarga de parsear y renderizar dinámicamente badges interactivos (G1-G3 / L1-L2) con tooltips descriptivos para leads calificados o descalificados según corresponda.
