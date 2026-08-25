"use client"

/**
 * components/crm-provider.tsx — Contexto del Mini-CRM integrado.
 *
 * Centraliza el estado y las operaciones del pipeline de leads calificados:
 *  - Cargar tarjetas del usuario (GET /api/v1/crm/leads)
 *  - Enviar un lead calificado al CRM (POST)
 *  - Mover etapa / cambiar prioridad / etiquetas (PATCH)
 *  - Eliminar tarjeta (DELETE)
 *  - Notas internas (POST/DELETE)
 *
 * Todas las peticiones pasan por el proxy de Next.js, que valida la sesión y
 * propaga la identidad (X-User-Id). El aislamiento multi-tenant se garantiza en
 * el backend con `.eq("user_id", ...)` sobre cada operación.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"
import { useAuth } from "@/components/auth-provider"
import { apiFetch } from "@/lib/api"
import type { CrmLead, CrmStage, CrmPriority, ProspectResult } from "@/lib/types"

interface CrmContextValue {
  crmLeads: CrmLead[]
  isLoading: boolean
  refresh: () => Promise<void>
  isInCrm: (leadId?: number | null) => boolean
  addToCrm: (lead: ProspectResult) => Promise<boolean>
  updateLead: (
    id: string,
    patch: { stage?: CrmStage; priority?: CrmPriority; tags?: string[] },
  ) => Promise<boolean>
  removeLead: (id: string) => Promise<boolean>
  addNote: (crmLeadId: string, body: string) => Promise<boolean>
  deleteNote: (noteId: string) => Promise<boolean>
}

const CrmContext = createContext<CrmContextValue | null>(null)

export function useCrm() {
  const ctx = useContext(CrmContext)
  if (!ctx) throw new Error("useCrm debe usarse dentro de un <CrmProvider>")
  return ctx
}

export function CrmProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const [crmLeads, setCrmLeads] = useState<CrmLead[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const token = session?.access_token

  const refresh = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    try {
      const res = await apiFetch("/api/v1/crm/leads", { token })
      if (res.ok) {
        const data = await res.json()
        setCrmLeads(data.crm_leads ?? [])
      }
    } catch (err) {
      console.error("[CRM] Error cargando leads del CRM:", err)
    } finally {
      setIsLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (token) refresh()
  }, [token, refresh])

  const isInCrm = useCallback(
    (leadId?: number | null) =>
      leadId != null && crmLeads.some((c) => c.lead_id === leadId),
    [crmLeads],
  )

  const addToCrm = useCallback(
    async (lead: ProspectResult) => {
      if (!token) return false
      try {
        const res = await apiFetch("/api/v1/crm/leads", {
          method: "POST",
          token,
          body: JSON.stringify({
            lead_id: lead.id ?? null,
            job_id: lead.job_id ?? null,
            nombre_lead: lead.nombre_lead ?? null,
            empresa: lead.empresa ?? null,
            cargo: lead.cargo ?? null,
            email: lead.email ?? null,
            telefono: lead.telefono ?? null,
            linkedin_url: lead.linkedin_url ?? null,
            trigger_noticia: lead.trigger_noticia ?? null,
            mensaje_generado: lead.mensaje_generado ?? null,
            url_noticia: lead.url_noticia ?? null,
            stage: "nuevo",
            priority: "media",
          }),
        })
        if (res.ok) {
          await refresh()
          return true
        }
        return false
      } catch (err) {
        console.error("[CRM] Error agregando lead al CRM:", err)
        return false
      }
    },
    [token, refresh],
  )

  const updateLead = useCallback(
    async (id: string, patch: { stage?: CrmStage; priority?: CrmPriority; tags?: string[] }) => {
      if (!token) return false
      // Actualización optimista para una UI fluida (Kanban responsivo).
      setCrmLeads((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)))
      try {
        const res = await apiFetch(`/api/v1/crm/leads/${id}`, {
          method: "PATCH",
          token,
          body: JSON.stringify(patch),
        })
        if (!res.ok) {
          await refresh() // revertir si falla
          return false
        }
        return true
      } catch (err) {
        console.error("[CRM] Error actualizando lead:", err)
        await refresh()
        return false
      }
    },
    [token, refresh],
  )

  const removeLead = useCallback(
    async (id: string) => {
      if (!token) return false
      setCrmLeads((prev) => prev.filter((c) => c.id !== id))
      try {
        const res = await apiFetch(`/api/v1/crm/leads/${id}`, { method: "DELETE", token })
        if (!res.ok) {
          await refresh()
          return false
        }
        return true
      } catch (err) {
        console.error("[CRM] Error eliminando lead:", err)
        await refresh()
        return false
      }
    },
    [token, refresh],
  )

  const addNote = useCallback(
    async (crmLeadId: string, body: string) => {
      if (!token || !body.trim()) return false
      try {
        const res = await apiFetch(`/api/v1/crm/leads/${crmLeadId}/notes`, {
          method: "POST",
          token,
          body: JSON.stringify({ body }),
        })
        if (res.ok) {
          await refresh()
          return true
        }
        return false
      } catch (err) {
        console.error("[CRM] Error agregando nota:", err)
        return false
      }
    },
    [token, refresh],
  )

  const deleteNote = useCallback(
    async (noteId: string) => {
      if (!token) return false
      try {
        const res = await apiFetch(`/api/v1/crm/notes/${noteId}`, { method: "DELETE", token })
        if (res.ok) {
          await refresh()
          return true
        }
        return false
      } catch (err) {
        console.error("[CRM] Error eliminando nota:", err)
        return false
      }
    },
    [token, refresh],
  )

  return (
    <CrmContext.Provider
      value={{ crmLeads, isLoading, refresh, isInCrm, addToCrm, updateLead, removeLead, addNote, deleteNote }}
    >
      {children}
    </CrmContext.Provider>
  )
}
