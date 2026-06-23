/**
 * lib/types.ts — Contratos de tipos compartidos del frontend Glovar Prospector.
 *
 * NOTA DE AUDITORÍA: Este archivo fue restaurado. La carpeta `lib/` estaba siendo
 * excluida del repositorio por la regla `lib/` heredada de la plantilla `.gitignore`
 * de Python, lo que impedía compilar el frontend tras un clon limpio.
 */

/* ------------------------------------------------------------------ */
/*  Formulario de prospección                                          */
/* ------------------------------------------------------------------ */

export type CompanySize = "1-50" | "51-200" | "201-500" | "500+"

export interface ProspectRequest {
  /** Descripción en lenguaje natural del cliente ideal (UX simplificada). */
  prompt?: string
  mi_empresa: string
  sector: string
  pais: string
  /** Mercado objetivo de expansión (opcional). Si la empresa tiene sede en `pais`
   *  pero buscas las que se expanden/operan en otro mercado, indícalo aquí
   *  (ej. pais="Estados Unidos", mercado_objetivo="Colombia"). */
  mercado_objetivo?: string
  /** Vacío en el estado inicial; se valida como obligatorio antes de enviar. */
  tamano_empresa: CompanySize | ""
  cargo_decision: string
  dolor_cliente: string
  propuesta_valor: string
  limite_perfiles?: number
  max_news_articles?: number
  triggers_compra?: string
  casos_exito?: string
  keywords_industria?: string
  /** Siempre presente como array para que FastAPI reciba una lista válida. */
  exclusion_list?: string[]
}

/* ------------------------------------------------------------------ */
/*  Resultado de prospección (tabla `leads`)                           */
/* ------------------------------------------------------------------ */

export interface ProspectResult {
  id?: number
  created_at?: string
  nombre_lead?: string | null
  empresa?: string | null
  cargo?: string | null
  linkedin_url?: string | null
  email?: string | null
  telefono?: string | null
  url_noticia?: string | null
  trigger_noticia?: string | null
  mensaje_generado?: string | null
  es_calificado?: boolean | null
  razonamiento_filtro?: string | null
  user_id?: string | null
  job_id?: string | null

  // ── Scoring ICP (fit + intent) — migración 002 ──────────────────────────────
  /** Encaje con el ICP (0-100). */
  fit_score?: number | null
  /** Fuerza/recencia del trigger de compra (0-100). */
  intent_score?: number | null
  /** Encaje del cargo del contacto (0-100). */
  role_fit_score?: number | null
  /** Score compuesto final (0-100) usado para ranking. */
  match_score?: number | null
  /** Tier comercial derivado del score: 'A' | 'B' | 'C' | 'D'. */
  score_tier?: "A" | "B" | "C" | "D" | null
  /** Desglose auditable del cálculo del score. */
  score_breakdown?: Record<string, unknown> | null

  // ── Verificación de email ───────────────────────────────────────────────────
  /** Origen del email: 'apollo' | 'hunter' | 'pattern_inferred'. */
  email_source?: "apollo" | "hunter" | "pattern_inferred" | null
  /** true solo si proviene de una fuente verificada (Apollo/Hunter). */
  email_verified?: boolean | null
}

/* ------------------------------------------------------------------ */
/*  Consultas guardadas (tabla `saved_queries`) con versionado         */
/* ------------------------------------------------------------------ */

export interface SavedQuery {
  id: string
  user_id?: string
  query_name: string
  search_params: ProspectRequest
  created_at: string
  updated_at?: string

  // ── Extensiones de versionado ──────────────────────────────────────
  /** Número de versión incremental. La v1 es la consulta base. */
  version?: number
  /** Etiquetas libres para distinguir versiones (ej. "Q3", "ajuste-cargo"). */
  tags?: string[]
  /** job_id de la ejecución cuyos resultados quedan anclados a esta versión. */
  result_job_id?: string | null
  /** Si es una versión derivada, apunta a la consulta raíz. */
  parent_query_id?: string | null
  /** Marca temporal de la última ejecución asociada. */
  last_run_at?: string | null
}

/* ------------------------------------------------------------------ */
/*  Telemetría de progreso del Job (tabla `jobs_status`)               */
/* ------------------------------------------------------------------ */

export interface JobProgress {
  phase: string
  processed: number
  total: number
  progress_percentage: number
}

/* ------------------------------------------------------------------ */
/*  Mini-CRM (tablas `crm_leads` y `crm_lead_notes`)                   */
/* ------------------------------------------------------------------ */

/** Etapas del pipeline visual tipo Kanban. */
export type CrmStage =
  | "nuevo"
  | "contactado"
  | "en_conversacion"
  | "propuesta"
  | "ganado"
  | "perdido"

export type CrmPriority = "baja" | "media" | "alta"

export interface CrmNote {
  id: string
  crm_lead_id: string
  user_id?: string
  body: string
  created_at: string
}

export interface CrmLead {
  id: string
  user_id?: string
  /** Referencia al lead original de la tabla `leads` (si proviene de ahí). */
  lead_id?: number | null
  job_id?: string | null

  // Snapshot de datos del lead (desacoplado para no perder info si el lead origen cambia)
  nombre_lead?: string | null
  empresa?: string | null
  cargo?: string | null
  email?: string | null
  telefono?: string | null
  linkedin_url?: string | null
  trigger_noticia?: string | null
  mensaje_generado?: string | null
  url_noticia?: string | null

  // Campos propios del CRM
  stage: CrmStage
  priority?: CrmPriority
  tags?: string[]
  created_at: string
  updated_at?: string

  /** Notas internas embebidas (cuando se solicitan con el detalle). */
  notes?: CrmNote[]
}

/** Etiquetas de visualización para cada etapa del Kanban. */
export const CRM_STAGES: { id: CrmStage; label: string; color: string }[] = [
  { id: "nuevo", label: "Nuevo", color: "#6366f1" },
  { id: "contactado", label: "Contactado", color: "#0ea5e9" },
  { id: "en_conversacion", label: "En conversación", color: "#f59e0b" },
  { id: "propuesta", label: "Propuesta enviada", color: "#a855f7" },
  { id: "ganado", label: "Ganado", color: "#10b981" },
  { id: "perdido", label: "Perdido", color: "#ef4444" },
]
