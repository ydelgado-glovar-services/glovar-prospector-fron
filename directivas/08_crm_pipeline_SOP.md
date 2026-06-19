# DIRECTIVA: CRM_PIPELINE_SOP

> **ID:** SOP-CRM-008
> **Script Asociado:** `app.py`
> **Migración:** `db/migrations/001_saved_queries_versioning_and_crm.sql`
> **Frontend:** `components/crm-provider.tsx`, `components/crm-board.tsx`, `app/crm/page.tsx`
> **Estado:** ACTIVO

## 1. Objetivo
Documentar el **Mini-CRM integrado**: un pipeline tipo Kanban donde el usuario gestiona los leads calificados que envía desde los resultados de prospección, con etiquetas personalizadas, prioridad y notas internas.

## 2. Esquema de datos

### `crm_leads`
Tarjeta del pipeline. Contiene un **snapshot desacoplado** de los datos del lead (no se pierde si el lead origen cambia).

| Columna | Tipo | Notas |
| :--- | :--- | :--- |
| `id` | `uuid` (PK) | Identificador de la tarjeta. |
| `user_id` | `uuid` (NOT NULL, default `auth.uid()`) | Propietario. |
| `lead_id` | `bigint` | Referencia opcional a `leads.id`. |
| `job_id` | `uuid` | Job de origen. |
| `nombre_lead`, `empresa`, `cargo`, `email`, `telefono`, `linkedin_url`, `trigger_noticia`, `mensaje_generado`, `url_noticia` | `text` | Snapshot del lead. |
| `stage` | `text` (CHECK) | `nuevo`, `contactado`, `en_conversacion`, `propuesta`, `ganado`, `perdido`. |
| `priority` | `text` (CHECK) | `baja`, `media`, `alta`. |
| `tags` | `text[]` | Etiquetas personalizadas (ej. "Contactar el martes"). |
| `created_at`, `updated_at` | `timestamptz` | `updated_at` mantenido por trigger. |

Índice único parcial `uq_crm_leads_user_lead (user_id, lead_id) WHERE lead_id IS NOT NULL` → evita duplicar el mismo lead origen.

### `crm_lead_notes`
Notas internas (timeline por tarjeta). FK `crm_lead_id` con `ON DELETE CASCADE`.

## 3. Contrato de la API

| Método | Ruta | Descripción |
| :--- | :--- | :--- |
| `GET` | `/api/v1/crm/leads` | Lista tarjetas del usuario con sus notas embebidas. |
| `POST` | `/api/v1/crm/leads` | Envía un lead al CRM (idempotente por `lead_id`). |
| `PATCH` | `/api/v1/crm/leads/{id}` | Actualiza `stage` / `priority` / `tags` (whitelist + validación de enums). |
| `DELETE` | `/api/v1/crm/leads/{id}` | Elimina la tarjeta (cascada a notas). |
| `POST` | `/api/v1/crm/leads/{id}/notes` | Agrega una nota interna (valida propiedad del lead). |
| `DELETE` | `/api/v1/crm/notes/{note_id}` | Elimina una nota. |

**Cabeceras obligatorias:** `x-user-id`, `x-api-key`.

## 4. Experiencia de usuario (Frontend)
- **Enviar a CRM:** botón en cada lead calificado de los resultados (`results-panel.tsx`). Si ya está en el CRM, muestra el badge "En CRM".
- **Apartado "Mis Leads / CRM"** (`/crm`): tablero Kanban con columnas por etapa, KPIs (total, en conversación, propuestas, ganados), y tarjetas con prioridad, etiquetas y contador de notas.
- **Mover etapa:** botones ◀ ▶ en la tarjeta (actualización optimista) o selector en el detalle. No se usa drag-and-drop (sin dependencias de DnD instaladas).
- **Detalle del lead:** etapa, prioridad, contacto, trigger/noticia, mensaje IA, editor de etiquetas y timeline de notas internas (agregar/eliminar).

## 5. Seguridad
- RLS habilitado en ambas tablas con políticas `auth.uid() = user_id` (SELECT/INSERT/UPDATE/DELETE).
- El backend (que usa `service_role` y bypassea RLS) refuerza el aislamiento con `.eq("user_id", x_user_id)` en **todas** las operaciones, incluida la verificación de propiedad antes de anexar notas.
- `PATCH` aplica whitelist de campos y validación de los enums `stage`/`priority`.
