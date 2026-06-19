# DIRECTIVA: SAVED_QUERIES_VERSIONING_SOP

> **ID:** SOP-QUERIES-007
> **Script Asociado:** `app.py`
> **Migración:** `db/migrations/001_saved_queries_versioning_and_crm.sql`
> **Frontend:** `app/dashboard/page.tsx`, `components/results-panel.tsx`
> **Estado:** ACTIVO

## 1. Objetivo
Documentar el contrato y la lógica de **guardado y versionado de consultas de prospección** (tabla `saved_queries`), incluyendo el anclaje de resultados de una ejecución (`job_id`) a una versión concreta de la consulta.

## 2. Antecedente (Bug corregido)
El frontend invocaba `PUT` y `DELETE` sobre `/api/v1/queries/{id}`, endpoints que **no existían** en `app.py` (solo había `GET` y `POST`). Además, el `POST` devolvía una **lista**, por lo que el frontend leía `data.id` como `undefined` y nunca fijaba `activeQueryId`, dejando inoperante el flujo de versionado. Ambos defectos quedan resueltos en esta directiva.

## 3. Esquema de datos (`saved_queries`)
Columnas añadidas por la migración 001:

| Columna | Tipo | Descripción |
| :--- | :--- | :--- |
| `version` | `integer` (NOT NULL, default 1) | Versión incremental de la consulta. |
| `tags` | `text[]` (default `{}`) | Etiquetas libres para distinguir versiones (ej. fecha, `ajuste-cargo`). |
| `result_job_id` | `uuid` | Job cuyos resultados quedan **anclados** a esta versión. |
| `parent_query_id` | `uuid` (FK a `saved_queries.id`) | Linaje: consulta raíz cuando se deriva una copia. |
| `last_run_at` | `timestamptz` | Última ejecución asociada. |
| `updated_at` | `timestamptz` (default `now()`) | Mantenido por trigger `set_updated_at`. |

## 4. Contrato de la API

| Método | Ruta | Descripción |
| :--- | :--- | :--- |
| `GET` | `/api/v1/queries` | Lista las consultas del usuario, ordenadas por `updated_at desc`. |
| `POST` | `/api/v1/queries` | Crea una consulta nueva (versión 1). **Devuelve un objeto único** (no lista). |
| `PUT` | `/api/v1/queries/{query_id}` | Sobreescribe creando **nueva versión** (incrementa `version`, fusiona `tags`, re-ancla `result_job_id`). |
| `DELETE` | `/api/v1/queries/{query_id}` | Elimina con verificación estricta de propiedad. |

**Cabeceras obligatorias:** `x-user-id` (inyectada por el proxy Next.js) y `x-api-key`.

**Cuerpo (POST/PUT):** `{ query_name, search_params, tags?, result_job_id?, parent_query_id? }`.

## 5. Lógica de versionado (UX)
1. El usuario ejecuta una prospección → obtiene `job_id` + resultados.
2. Al pulsar **"Guardar Consulta"**:
   - **Sin consulta activa** → guardar como nueva (pide nombre + etiquetas opcionales).
   - **Con consulta activa cargada** → modal de decisión:
     - **Sobreescribir (nueva versión):** `PUT`. Sube a `v(n+1)`, anexa etiquetas/fecha y re-ancla `result_job_id` para que **los resultados queden ligados a la nueva versión**.
     - **Guardar como consulta nueva:** `POST` con `parent_query_id` apuntando a la consulta de origen (linaje preservado).
3. El frontend compara los parámetros del formulario contra los de la consulta activa (`paramsChanged`) para resaltar que hubo ajustes.

## 6. Seguridad
- Aislamiento multi-tenant **obligatorio** con `.eq("user_id", x_user_id)` en `GET/PUT/DELETE` (el `service_role` bypassea RLS; ver SOP de seguridad).
- El `PUT`/`DELETE` verifican propiedad antes de mutar (defensa contra IDOR).
- En `POST`/`PUT` se descarta `user_id` inyectado en el cuerpo para no contaminar `search_params`.
