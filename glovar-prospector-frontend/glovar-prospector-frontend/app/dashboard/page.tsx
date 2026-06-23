"use client"

/**
 * app/dashboard/page.tsx — Protected prospecting dashboard.
 *
 * This is the main application view (previously at /).
 * The auth guard (middleware) ensures only authenticated users reach this page.
 * The fetch call to the backend now includes the JWT Authorization header.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import { useRouter } from "next/navigation"

import { AppHeader } from "@/components/app-header"
import { ResultsPanel } from "@/components/results-panel"
import { SearchForm } from "@/components/search-form"
import { useAuth } from "@/components/auth-provider"
import { createClient } from "@/utils/supabase/client"
import type { ProspectRequest, ProspectResult, SavedQuery, JobProgress } from "@/lib/types"
import { apiFetch } from "@/lib/api"
import { useToast } from "@/hooks/use-toast"

const INITIAL_FORM: ProspectRequest = {
  prompt: "",
  mi_empresa: "",
  sector: "",
  pais: "",
  mercado_objetivo: "",
  tamano_empresa: "",
  cargo_decision: "",
  dolor_cliente: "",
  propuesta_valor: "",
  limite_perfiles: 25,
  max_news_articles: 3,
  triggers_compra: "",
  casos_exito: "",
  keywords_industria: "",
  exclusion_list: [], // [Spec-Driven] Always present so FastAPI receives a valid list
}

const LS_KEYS = {
  form: "prospect_form_state",
  results: "prospect_results_state",
  jobId: "prospect_active_job_id",
} as const

// ── ISOLATED FETCH LOGIC ─────────────────────────────────────────────────────────
// This is strictly outside the React component scope to prevent Promise cancellation
// and closure trapping during rapid re-renders.
const executeProspectRequest = async (
  accessToken: string,
  formPayload: string,
  router: any,
  toast: any,
  pollJob: (jobId: string, accessToken: string) => void,
  setResults: (results: any[]) => void,
  setHasSearched: (val: boolean) => void
) => {
  if (!accessToken) {
    console.error("[Frontend] No access token available. Redirecting to login.")
    router.push("/login")
    return { jobStarted: false }
  }

  console.log("[Frontend] Checkpoint: Immediately before apiFetch")
  console.log("[Frontend] Enviando solicitud de prospección (autenticada):", formPayload)

  const response = await apiFetch("/api/v1/prospect", {
    method: "POST",
    token: accessToken,
    body: formPayload,
  })

  if (response.status === 401) {
    console.error("[Frontend] Token inválido o expirado en el backend. Redirigiendo a login.")
    router.push("/login")
    return { jobStarted: false }
  }

  if (!response.ok) {
    const errorBody = await response.text()
    console.error(`[Frontend] Error HTTP ${response.status}:`, errorBody)
    throw new Error(`Error del servidor: ${response.status} - ${errorBody}`)
  }

  const data = await response.json()

  if (data.job_id) {
    console.log(`[Frontend] Job iniciado con ID: ${data.job_id}. Iniciando polling...`)
    try {
      toast({
        title: "Prospección en curso",
        description: "Buscando y evaluando perfiles. Este proceso puede tomar varios minutos...",
      })
    } catch (e) {
      console.error("[Frontend] Error showing running job toast:", e)
    }
    pollJob(data.job_id, accessToken)
    return { jobStarted: true }
  } else {
    // Fallback para ejecución síncrona
    const leads: ProspectResult[] = data.leads ?? []
    console.log(`[Frontend] Prospección síncrona completada.`)
    setResults(leads)
    setHasSearched(true)
    return { jobStarted: false }
  }
}

// ── Polling config ──────────────────────────────────────────────────────────
// Exponential backoff: starts at POLL_MIN_MS, doubles each attempt, caps at POLL_MAX_MS.
// Total budget: ~300 s (5 minutes) before the soft-timeout fires.
const POLL_MIN_MS = 2_000   // 2 s  – initial interval
const POLL_MAX_MS = 10_000  // 10 s – maximum interval
const POLL_BUDGET_MS = 9000_000 // 5 min total

export default function DashboardPage() {
  const { session, isLoading: authLoading } = useAuth()
  const router = useRouter()
  const { toast } = useToast()

  const isSessionReady = !authLoading && !!session

  const [form, setForm] = useState<ProspectRequest>(INITIAL_FORM)
  const [prospectMode, setProspectMode] = useState<"fast" | "deep">("fast")
  const [results, setResults] = useState<ProspectResult[]>([])
  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [isInitialized, setIsInitialized] = useState(false)
  const [activeQueryId, setActiveQueryId] = useState<string | null>(null)
  const [searchTimestamp, setSearchTimestamp] = useState<number>(Date.now())

  // Timeout-fallback state — shown when polling exhausts its budget
  const [isTimedOut, setIsTimedOut] = useState(false)
  const [timedOutJobId, setTimedOutJobId] = useState<string | null>(null)

  // Granular progress for the progress bar
  const [jobProgress, setJobProgress] = useState<JobProgress>({ phase: "", processed: 0, total: 0, progress_percentage: 0 })

  const isFetchingRef = useRef<boolean>(false) // Mutex lock
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null)
  const pollStartRef = useRef<number>(0)       // wall-clock start of the current poll
  const pollIntervalRef = useRef<number>(POLL_MIN_MS) // current backoff interval
  const lastProgressHash = useRef<string>("") // prevent re-render loops

  // Clean up polling timer on unmount
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current)
      }
    }
  }, [])

  // Redirect to login if no session (client-side fallback, middleware handles SSR)
  useEffect(() => {
    if (!authLoading && !session) {
      router.push("/login")
    }
  }, [authLoading, session, router])

  // (Client-side timeout is now handled natively within AuthProvider)

  // Cargar estado inicial desde localStorage en el cliente al montar
  // Si había un job activo antes de que el usuario recargara la página, lo retomamos.
  useEffect(() => {
    try {
      const savedForm = localStorage.getItem(LS_KEYS.form)
      if (savedForm) setForm(JSON.parse(savedForm))

      const savedResults = localStorage.getItem(LS_KEYS.results)
      if (savedResults) {
        const parsedResults = JSON.parse(savedResults)
        setResults(parsedResults)
        if (parsedResults.length > 0) setHasSearched(true)
      }
    } catch (err) {
      console.error("[Frontend] Error cargando estado desde localStorage:", err)
    } finally {
      setIsInitialized(true)
    }
  }, [])

  // [State Recovery] — After auth is ready, check for an in-progress job from before a page refresh.
  useEffect(() => {
    if (!session || !isInitialized) return
    const savedJobId = localStorage.getItem(LS_KEYS.jobId)
    if (!savedJobId) return

    console.log(`[Frontend] Recuperando job en curso desde localStorage: ${savedJobId}`)
    toast({
      title: "Retomando prospección",
      description: "Se detectó una búsqueda en curso. Reconectando...",
    })
    setIsLoading(true)
    setIsTimedOut(false)
    setTimedOutJobId(null)
    pollJob(savedJobId, session.access_token)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.access_token, isInitialized])

  const fetchQueries = async () => {
    // [Sec-Driven] AbortController: hard 12 s ceiling to prevent indefinite hangs
    // when the FastAPI backend or Ngrok tunnel is unreachable on hard refresh.
    const controller = new AbortController()
    const timeoutId = setTimeout(() => {
      controller.abort()
      console.warn("[Frontend] fetchQueries AbortController fired (12s timeout).")
    }, 12_000)

    try {
      if (!session?.access_token) {
        console.error("[Frontend] No valid session for fetching queries.")
        router.push("/login")
        return
      }

      const response = await apiFetch("/api/v1/queries", {
        token: session.access_token,
        signal: controller.signal,
      })

      if (response.status === 401) {
        console.error("[Frontend] Token expirado al obtener consultas. Redirigiendo...")
        toast({
          variant: "destructive",
          title: "Sesión expirada",
          description: "Tu sesión ha expirado, por favor inicia sesión nuevamente.",
        })
        router.push("/login")
        return
      }

      if (response.ok) {
        const data = await response.json()
        setSavedQueries(data)
      } else {
        console.error(`[Frontend] Error HTTP ${response.status} al obtener consultas`)
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        // AbortController timed out — backend unreachable or too slow
        console.error("[Frontend] fetchQueries timed out (AbortError).")
        toast({
          variant: "destructive",
          title: "Error de conexión con el servidor",
          description: "No se pudo conectar al servidor en 12 segundos. Verifica que el backend esté corriendo.",
        })
      } else {
        console.error("[Frontend] Error fetching queries:", err)
      }
    } finally {
      clearTimeout(timeoutId) // Always clear the abort timer
    }
  }

  // Effect to fetch queries when session is ready
  useEffect(() => {
    if (session) {
      fetchQueries()
    }
  }, [session?.access_token])

  // Guardar estado del formulario cuando cambie, solo después de inicializar
  useEffect(() => {
    if (!isInitialized) return
    try {
      localStorage.setItem(LS_KEYS.form, JSON.stringify(form))
    } catch (err) {
      console.error("[Frontend] Error guardando form en localStorage:", err)
    }
  }, [form, isInitialized])

  // Guardar resultados cuando cambien, solo después de inicializar
  useEffect(() => {
    if (!isInitialized) return
    try {
      localStorage.setItem(LS_KEYS.results, JSON.stringify(results))
    } catch (err) {
      console.error("[Frontend] Error guardando resultados en localStorage:", err)
    }
  }, [results, isInitialized])

  const handleChange = (patch: Partial<ProspectRequest>) => {
    setForm((prev) => ({ ...prev, ...patch }))
  }

  const handleClear = () => {
    resetSystemState()
    setForm(INITIAL_FORM)
  }

  const resetSystemState = () => {
    console.log("[Frontend] Executing Hard Reset of system state.")
    try {
      localStorage.removeItem(LS_KEYS.form)
      localStorage.removeItem(LS_KEYS.results)
      localStorage.removeItem(LS_KEYS.jobId)
    } catch (err) {
      console.error("[Frontend] Error clearing localStorage on hard reset:", err)
    }

    if (pollingTimerRef.current) {
      clearTimeout(pollingTimerRef.current)
      pollingTimerRef.current = null
    }

    setResults([])
    setIsLoading(false)
    setJobProgress({ phase: "", processed: 0, total: 0, progress_percentage: 0 })
    setIsTimedOut(false)
    setTimedOutJobId(null)
    setHasSearched(false)
    setActiveQueryId(null)
    setSearchTimestamp(Date.now())
  }

  // ── MODO RÁPIDO: prospección síncrona (sin polling) ──────────────────────────
  const handleFastSubmit = async () => {
    if (isFetchingRef.current) return
    isFetchingRef.current = true
    try {
      const accessToken = session?.access_token
      if (!accessToken) {
        router.push("/login")
        return
      }
      // Validación ligera: basta una frase o un cargo.
      if (!form.prompt?.trim() && !form.cargo_decision?.trim()) {
        toast({
          variant: "destructive",
          title: "Falta información",
          description: "Describe tu cliente ideal o indica al menos un cargo objetivo.",
        })
        return
      }

      setIsLoading(true)
      setIsTimedOut(false)
      setResults([])
      setHasSearched(true)
      setSearchTimestamp(Date.now())

      const res = await apiFetch("/api/v1/prospect/fast", {
        method: "POST",
        token: accessToken,
        body: JSON.stringify({
          prompt: form.prompt || "",
          cargo_decision: form.cargo_decision || "",
          sector: form.sector || "",
          pais: form.pais || "",
          mercado_objetivo: form.mercado_objetivo || "",
          tamano_empresa: form.tamano_empresa || "",
          keywords_industria: form.keywords_industria || "",
          limite_perfiles: form.limite_perfiles ?? 15,
        }),
      })

      if (res.status === 401) {
        router.push("/login")
        return
      }
      if (!res.ok) {
        const t = await res.text()
        throw new Error(t)
      }
      const data = await res.json()
      const leads: ProspectResult[] = data.leads ?? []
      setResults(leads)
      toast({
        title: "Modo Rápido completado",
        description: `Se encontraron ${leads.length} contactos (fuente: ${data.source}).`,
      })
    } catch (err) {
      console.error("[Frontend] Error en Modo Rápido:", err)
      toast({
        variant: "destructive",
        title: "Error en Modo Rápido",
        description: "No se pudo completar la búsqueda rápida. Intenta de nuevo.",
      })
    } finally {
      setIsLoading(false)
      isFetchingRef.current = false
    }
  }

  // ── UPDATED: fetch explícitamente refresca y verifica la sesión y el token ──
  const handleSubmit = async () => {
    // STRICT MUTEX LOCK
    if (isFetchingRef.current) {
      console.warn("[Frontend] Mutex Locked: Previendo ejecución duplicada de handleSubmit")
      return
    }
    isFetchingRef.current = true

    let jobStarted = false

    try {
      // [DEBUG] Hard Reset disabled to expose silent failures
      // resetSystemState()

      const { sector, pais, tamano_empresa, cargo_decision, dolor_cliente, propuesta_valor } = form

      // Validate ONLY the required fields.
      if (!sector?.trim() || !pais?.trim() || !tamano_empresa?.trim() || !cargo_decision?.trim() || !dolor_cliente?.trim() || !propuesta_valor?.trim()) {
        try {
          toast({
            variant: "destructive",
            title: "Campos incompletos",
            description: "Por favor, completa todos los campos requeridos del formulario.",
          })
        } catch (e) {
          console.error("[Frontend] Error showing incomplete fields toast:", e)
        }
        return // finally block will reset mutex
      }

      // ── Guardrail: limite_perfiles must be between 5 and 25 ──────────────────
      // Mirrors: z.number().min(5).max(25, "El límite máximo por búsqueda es 25 para proteger créditos.")
      const limite = form.limite_perfiles ?? 25
      if (limite < 5 || limite > 25) {
        try {
          toast({
            variant: "destructive",
            title: "Límite de perfiles inválido",
            description: "El límite máximo por búsqueda es 25 para proteger créditos.",
          })
        } catch (e) {
          console.error("[Frontend] Error showing limite_perfiles toast:", e)
        }
        return // finally block will reset mutex
      }

      setIsLoading(true)
      setJobProgress({ phase: "Iniciando prospección", processed: 0, total: 0, progress_percentage: 0 })

      // ── Synchronization buffer ───────────────────────────────────────────────
      await new Promise((resolve) => setTimeout(resolve, 100))

      // [Error Boundary]: Pre-flight serialization check
      let bodyPayload;
      try {
        bodyPayload = JSON.stringify(form);
      } catch (err) {
        console.error("[Frontend] Error de serialización pre-flight:", err);
        throw err;
      }

      // Retrieve token instantaneously from the pre-warmed Auth Context (RAM)
      const accessToken = session?.access_token;
      if (!accessToken) {
        console.error("[Frontend] CRITICAL: handleSubmit fired without an active token in context.");
        router.push("/login");
        return; // finally block will unlock mutex
      }

      // Execute the isolated fetch logic
      const result = await executeProspectRequest(
        accessToken,
        bodyPayload,
        router,
        toast,
        pollJob,
        setResults,
        setHasSearched
      )

      if (result) {
        jobStarted = result.jobStarted
      }

    } catch (criticalError: any) {
      console.error("[Frontend] Uncaught error in handleSubmit. Error Object:", criticalError)
      console.error("[Frontend] Error Stack:", criticalError?.stack)
      try {
        toast({
          variant: "destructive",
          title: "Error inesperado",
          description: "Ocurrió un error crítico al iniciar la prospección.",
        })
      } catch (e) {
        console.error("[Frontend] Error showing critical error toast:", e)
      }
    } finally {
      // Ensure the UI never hangs indefinitely if the API errors before job starts
      if (!jobStarted) {
        setIsLoading(false)
      }
      isFetchingRef.current = false // Unlock mutex
    }
  }

  /**
   * pollJob — Resilient job polling with exponential backoff and 5-minute budget.
   *
   * • Backoff: starts at POLL_MIN_MS (2 s), doubles each attempt, caps at POLL_MAX_MS (10 s).
   * • Budget:  300 s total. On soft-timeout it surfaces a manual-retry UI instead of
   *            hard-failing, so users can keep waiting or manually trigger one final check.
   * • Recovery: job_id is persisted in localStorage so a page refresh can resume polling.
   */
  const pollJob = useCallback(async (jobId: string, accessToken: string) => {
    // Persist job id for state recovery across page refreshes
    try { localStorage.setItem(LS_KEYS.jobId, jobId) } catch { /* ignore */ }

    // Reset backoff counters for this poll session
    pollStartRef.current = Date.now()
    pollIntervalRef.current = POLL_MIN_MS

    const checkStatus = async () => {
      try {
        const response = await apiFetch(`/api/v1/prospect/job/${jobId}`, {
          token: accessToken,
        })

        if (response.status === 401) {
          console.error("[Frontend] Token inválido durante el polling.")
          try { localStorage.removeItem(LS_KEYS.jobId) } catch { /* ignore */ }
          router.push("/login")
          return
        }

        if (!response.ok) {
          throw new Error(`Error polling job: ${response.status}`)
        }

        const data = await response.json()
        const elapsed = Date.now() - pollStartRef.current

        if (data.status === "completed") {
          console.log(`[Frontend] ✅ Job completado (${Math.round(elapsed / 1000)} s): ${jobId}`)
          try { localStorage.removeItem(LS_KEYS.jobId) } catch { /* ignore */ }

          // ── Fetch the leads that were saved to Supabase during the job ──────────────
          // The job status endpoint does NOT embed leads in its response (stateless design).
          // We must call GET /api/v1/leads to retrieve them from the database.
          let leads: ProspectResult[] = []
          try {
            console.log(`[Frontend] Fetching leads from /api/v1/leads for job ${jobId}...`)
            const leadsResponse = await apiFetch(`/api/v1/leads?job_id=${jobId}`, { token: accessToken })
            if (leadsResponse.ok) {
              const leadsData = await leadsResponse.json()
              leads = leadsData.leads ?? []
              console.log(`[Frontend] ✅ ${leads.length} leads recuperados de Supabase.`)
            } else {
              console.error(`[Frontend] ❌ Error al recuperar leads: HTTP ${leadsResponse.status}`)
            }
          } catch (fetchErr) {
            console.error("[Frontend] ❌ Error en la petición de leads:", fetchErr)
          }

          // ── Safety net: job completed but 0 leads found ─────────────────────────────
          if (leads.length === 0) {
            setResults([])
            setHasSearched(true)
            setIsLoading(false)
            setIsTimedOut(false)
            setTimedOutJobId(null)
            setJobProgress({ phase: "", processed: 0, total: 0, progress_percentage: 0 })
            if (pollingTimerRef.current) {
              clearTimeout(pollingTimerRef.current)
              pollingTimerRef.current = null
            }
            toast({
              variant: "destructive",
              title: "⚠️ No se encontraron leads",
              description: "No se encontraron leads. Intenta ampliar tus criterios de búsqueda o verifica el scraper.",
            })
            return
          }

          setResults(leads)
          setHasSearched(true)
          setIsLoading(false)
          setIsTimedOut(false)
          setTimedOutJobId(null)
          setJobProgress({
            phase: "Completado",
            processed: data.processed_leads ?? leads.length,
            total: data.total_leads ?? leads.length,
            progress_percentage: 100,
          })
          if (pollingTimerRef.current) {
            clearTimeout(pollingTimerRef.current)
            pollingTimerRef.current = null
          }
          toast({
            title: "✅ Prospección completada",
            description: `Se encontraron ${leads.length} leads.`,
          })
          return
        }

        if (data.status === "error") {
          // ── Explicit zero-profile termination from the backend ──
          console.warn(`[Frontend] ⚠️ Job terminó con 0 perfiles (cookie/match): ${jobId}`, data.error)
          try { localStorage.removeItem(LS_KEYS.jobId) } catch { /* ignore */ }
          toast({
            variant: "destructive",
            title: "⚠️ No se encontraron leads",
            description: data.error ?? "No se encontraron leads. Intenta ampliar tus criterios de búsqueda o verifica el scraper.",
          })
          setResults([])
          setHasSearched(true)
          setIsLoading(false)
          setIsTimedOut(false)
          setTimedOutJobId(null)
          setJobProgress({ phase: "", processed: 0, total: 0, progress_percentage: 0 })
          if (pollingTimerRef.current) {
            clearTimeout(pollingTimerRef.current)
            pollingTimerRef.current = null
          }
          return
        }

        if (data.status === "failed") {
          console.error(`[Frontend] ❌ Job fallido: ${jobId}`, data.error)
          try { localStorage.removeItem(LS_KEYS.jobId) } catch { /* ignore */ }
          toast({
            variant: "destructive",
            title: "Error en la prospección",
            description: data.error || "Ocurrió un error procesando los perfiles.",
          })
          setResults([])
          setHasSearched(true)
          setIsLoading(false)
          setIsTimedOut(false)
          setTimedOutJobId(null)
          setJobProgress({ phase: "", processed: 0, total: 0, progress_percentage: 0 })
          if (pollingTimerRef.current) {
            clearTimeout(pollingTimerRef.current)
            pollingTimerRef.current = null
          }
          return
        }

        // ── Still pending / processing ────────────────────────────────────────────
        // Update granular progress in a Main-Thread-Safe way
        const newPhase = data.current_phase ?? ""
        const newProcessed = data.processed_leads ?? 0
        const newTotal = data.total_leads ?? 0
        const newProgressPercentage = data.progress_percentage ?? 0
        const currentProgressKey = `${newPhase}-${newProcessed}-${newTotal}-${newProgressPercentage}`

        if (lastProgressHash.current !== currentProgressKey) {
          lastProgressHash.current = currentProgressKey
          setJobProgress({
            phase: newPhase,
            processed: newProcessed,
            total: newTotal,
            progress_percentage: newProgressPercentage,
          })
        }
        // Check if we've exhausted the total 5-minute budget
        if (elapsed >= POLL_BUDGET_MS) {
          console.warn(`[Frontend] ⏳ Budget agotado (${Math.round(elapsed / 1000)} s). Job: ${jobId}`)
          // Soft-timeout: surface manual-retry UI, keep job_id in localStorage
          setIsLoading(false)
          setIsTimedOut(true)
          setTimedOutJobId(jobId)
          if (pollingTimerRef.current) {
            clearTimeout(pollingTimerRef.current)
            pollingTimerRef.current = null
          }
          toast({
            title: "⏳ El backend sigue trabajando",
            description: "Puedes seguir esperando o cargar los resultados manualmente.",
          })
          return
        }

        // Exponential backoff — double interval, cap at POLL_MAX_MS
        const nextInterval = Math.min(pollIntervalRef.current * 2, POLL_MAX_MS)
        pollIntervalRef.current = nextInterval
        console.log(
          `[Frontend] Polling job ${jobId} — elapsed: ${Math.round(elapsed / 1000)} s, ` +
          `next check in: ${nextInterval / 1000} s`
        )
        pollingTimerRef.current = setTimeout(checkStatus, nextInterval)

      } catch (error) {
        console.error("[Frontend] Error al consultar estado del job:", error)
        toast({
          variant: "destructive",
          title: "Error de conexión",
          description: "Perdimos la conexión con el servidor. Puedes intentar cargar los resultados manualmente.",
        })
        // Don't remove jobId so the user can still retry
        setIsLoading(false)
        setIsTimedOut(true)
        setTimedOutJobId(jobId)
      }
    }

    checkStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, toast])

  /**
   * handleManualCheck — triggered by the "Seguir esperando" / "Cargar resultados" button.
   * Performs a single immediate status check on the timed-out job.
   */
  const handleManualCheck = useCallback(async () => {
    if (!timedOutJobId || !session?.access_token) return

    setIsTimedOut(false)
    setIsLoading(true)
    toast({ title: "Consultando resultados...", description: "Revisando el estado del job en el backend." })

    try {
      const response = await apiFetch(`/api/v1/prospect/job/${timedOutJobId}`, {
        token: session.access_token,
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      if (data.status === "completed") {
        let leads: ProspectResult[] = []
        try {
          const leadsResponse = await apiFetch(`/api/v1/leads?job_id=${timedOutJobId}`, { token: session.access_token })
          if (leadsResponse.ok) {
            const leadsData = await leadsResponse.json()
            leads = leadsData.leads ?? []
          }
        } catch (fetchErr) {
          console.error("[Frontend] Error al recuperar leads en manual check:", fetchErr)
        }
        try { localStorage.removeItem(LS_KEYS.jobId) } catch { /* ignore */ }
        setResults(leads)
        setHasSearched(true)
        setIsLoading(false)
        setTimedOutJobId(null)
        toast({ title: "✅ Resultados listos", description: `${leads.length} leads encontrados.` })
      } else if (data.status === "failed") {
        try { localStorage.removeItem(LS_KEYS.jobId) } catch { /* ignore */ }
        setIsLoading(false)
        setTimedOutJobId(null)
        setHasSearched(true)
        toast({ variant: "destructive", title: "Job fallido", description: data.error || "Error procesando la búsqueda." })
      } else {
        // Still running — resume backoff polling from current position
        pollJob(timedOutJobId, session.access_token)
      }
    } catch (err) {
      console.error("[Frontend] Error en comprobación manual:", err)
      setIsLoading(false)
      setIsTimedOut(true)
      toast({ variant: "destructive", title: "Error de conexión", description: "No se pudo conectar al servidor." })
    }
  }, [timedOutJobId, session, pollJob, toast])

  // --- Handlers de Historial ---

  const handleSaveQuery = async (
    name: string,
    isOverwrite: boolean = false,
    existingId?: string,
    extra?: { tags?: string[]; result_job_id?: string | null; parent_query_id?: string | null },
  ) => {
    if (!session) return

    // Ancla de resultados: el job_id de la ejecución vigente (todos los leads del
    // run comparten el mismo job_id) queda ligado a esta versión de la consulta.
    const anchoredJobId =
      extra?.result_job_id ?? results.find((r) => r.job_id)?.job_id ?? null

    try {
      let response
      if (isOverwrite && existingId) {
        response = await apiFetch(`/api/v1/queries/${existingId}`, {
          method: "PUT",
          token: session.access_token,
          body: JSON.stringify({
            query_name: name,
            search_params: form,
            tags: extra?.tags ?? [],
            result_job_id: anchoredJobId,
          }),
        })
      } else {
        response = await apiFetch("/api/v1/queries", {
          method: "POST",
          token: session.access_token,
          body: JSON.stringify({
            query_name: name,
            search_params: form,
            tags: extra?.tags ?? [],
            result_job_id: anchoredJobId,
            parent_query_id: extra?.parent_query_id ?? null,
          }),
        })
      }

      if (response.ok) {
        const data = await response.json()
        // El backend ahora devuelve un OBJETO único, por lo que data.id es válido
        // y permite fijar el activeQueryId para habilitar el versionado posterior.
        if (data?.id) {
          setActiveQueryId(data.id)
        }
        toast({
          title: isOverwrite ? "Consulta actualizada (nueva versión)" : "Consulta guardada",
          description: isOverwrite
            ? "Se creó una nueva versión y los resultados quedaron anclados a ella."
            : "Tu consulta ha sido guardada en la nube.",
        })
        fetchQueries()
      } else {
        const errData = await response.text()
        console.error("[Frontend] Error guardando consulta:", errData)
        toast({
          variant: "destructive",
          title: "Error",
          description: "No se pudo guardar la consulta.",
        })
      }
    } catch (err) {
      console.error("[Frontend] Error en la petición de guardar consulta:", err)
    }
  }

  const handleLoadQuery = async (query: SavedQuery) => {
    // [Safety Mechanism]: Clean history loading without triggering side effects
    setForm(query.search_params)
    setActiveQueryId(query.id)
    
    if (query.result_job_id && session?.access_token) {
      setIsLoading(true)
      try {
        const leadsResponse = await apiFetch(`/api/v1/leads?job_id=${query.result_job_id}`, { token: session.access_token })
        if (leadsResponse.ok) {
          const leadsData = await leadsResponse.json()
          setResults(leadsData.leads ?? [])
          setHasSearched(true)
        } else {
          setResults([])
          setHasSearched(false)
        }
      } catch (err) {
        console.error("Error fetching leads for saved query", err)
        setResults([])
        setHasSearched(false)
      } finally {
        setIsLoading(false)
      }
    } else {
      setResults([])
      setHasSearched(false)
    }
  }

  const handleDeleteQuery = async (id: string) => {
    if (!session) return
    try {
      const response = await apiFetch(`/api/v1/queries/${id}`, {
        method: "DELETE",
        token: session.access_token,
      })
      if (response.ok) {
        toast({
          title: "Consulta eliminada",
          description: "La consulta fue eliminada correctamente.",
        })
        fetchQueries()
      } else {
        toast({
          variant: "destructive",
          title: "Error al eliminar",
          description: "No se pudo eliminar la consulta.",
        })
      }
    } catch (err) {
      console.error("[Frontend] Error al eliminar consulta:", err)
    }
  }

  // Show nothing while auth is loading (resilient loading state handled by AuthProvider)
  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm text-muted-foreground">Cargando sesión...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col bg-muted/30">
      <AppHeader />
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 md:px-6 md:py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,440px)_minmax(0,1fr)]">
          <SearchForm
            values={form}
            isLoading={isLoading}
            isSessionReady={isSessionReady}
            mode={prospectMode}
            onModeChange={setProspectMode}
            onChange={handleChange}
            onSubmit={prospectMode === "fast" ? handleFastSubmit : handleSubmit}
            onClear={handleClear}
          />
          <ResultsPanel
            key={searchTimestamp}
            results={results}
            isLoading={isLoading}
            hasSearched={hasSearched}
            formData={form}
            savedQueries={savedQueries}
            activeQueryId={activeQueryId}
            onSaveQuery={handleSaveQuery}
            onLoadQuery={handleLoadQuery}
            onDeleteQuery={handleDeleteQuery}
            isTimedOut={isTimedOut}
            onManualCheck={handleManualCheck}
            jobProgress={jobProgress}
          />
        </div>
      </main>
    </div>
  )
}
