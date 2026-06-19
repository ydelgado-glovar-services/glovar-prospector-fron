"use client"

import { useState, useMemo } from "react"
import {
  ExternalLink,
  Inbox,
  Loader2,
  Search,
  Copy,
  Users,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Info,
  Save,
  Trash2,
  Eye,
  Clock,
  ArrowDownUp,
  Mail,
  Phone,
  Send,
  RefreshCw,
  AlertCircle,
} from "lucide-react"
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, LabelList,
} from "recharts"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useToast } from "@/components/ui/use-toast"
import { useIntegrations } from "@/components/integrations-provider"
import type { ProspectRequest, ProspectResult, SavedQuery, JobProgress } from "@/lib/types"

interface ResultsPanelProps {
  results: ProspectResult[]
  isLoading: boolean
  hasSearched: boolean
  formData: ProspectRequest
  savedQueries: SavedQuery[]
  activeQueryId: string | null
  onSaveQuery: (name: string, isOverwrite?: boolean, existingId?: string) => void
  onLoadQuery: (query: SavedQuery) => void
  onDeleteQuery: (id: string) => void
  /** True when the polling budget has been exhausted (soft-timeout) */
  isTimedOut?: boolean
  /** Called when the user clicks "Seguir esperando" or "Cargar resultados" */
  onManualCheck?: () => void
  /** Granular progress data from the backend job */
  jobProgress?: JobProgress
}

export function ResultsPanel({
  results,
  isLoading,
  hasSearched,
  formData,
  savedQueries,
  activeQueryId,
  onSaveQuery,
  onLoadQuery,
  onDeleteQuery,
  isTimedOut = false,
  onManualCheck,
  jobProgress,
}: ResultsPanelProps) {
  const [activeTab, setActiveTab] = useState("actual")

  return (
    <Card className="flex h-full flex-col border-border/80 shadow-sm overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-4 bg-card/50 backdrop-blur-sm">
        <div className="space-y-1">
          <CardTitle className="text-lg font-semibold">Resultados de prospección</CardTitle>
          <CardDescription className="text-sm">
            Panel analítico y listado de leads enriquecidos por IA.
          </CardDescription>
        </div>
        {results.length > 0 && !isLoading && activeTab === "actual" && (
          <Badge variant="secondary" className="shrink-0 font-mono text-xs py-1 px-2.5">
            {results.length} {results.length === 1 ? "lead" : "leads"}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col p-0 overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-1 flex-col overflow-hidden">
          <div className="px-4 pt-3 pb-0">
            <TabsList className="w-full">
              <TabsTrigger value="actual" className="flex-1 gap-1.5">
                <Search className="h-3.5 w-3.5" />
                Búsqueda Actual
              </TabsTrigger>
              <TabsTrigger value="historial" className="flex-1 gap-1.5">
                <Clock className="h-3.5 w-3.5" />
                Historial
                {savedQueries.length > 0 && (
                  <Badge variant="secondary" className="ml-1 h-5 min-w-[20px] px-1.5 text-[10px] font-mono">
                    {savedQueries.length}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Tab: Búsqueda Actual */}
          <TabsContent value="actual" className="flex flex-1 flex-col overflow-hidden mt-0">
            {isTimedOut ? (
              <TimeoutState onManualCheck={onManualCheck} />
            ) : isLoading ? (
              <LoadingState jobProgress={jobProgress} />
            ) : results.length === 0 ? (
              <EmptyState hasSearched={hasSearched} />
            ) : (
              <DashboardContent
                results={results}
                formData={formData}
                savedQueries={savedQueries}
                activeQueryId={activeQueryId}
                onSaveQuery={onSaveQuery}
              />
            )}
          </TabsContent>

          {/* Tab: Historial */}
          <TabsContent value="historial" className="flex flex-1 flex-col overflow-hidden mt-0">
            <HistoryPanel
              savedQueries={savedQueries}
              onLoadQuery={(query) => {
                onLoadQuery(query)
                setActiveTab("actual")
              }}
              onDeleteQuery={onDeleteQuery}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------------ */
/*  Sub-componentes internos                                          */
/* ------------------------------------------------------------------ */

function LoadingState({ jobProgress }: { jobProgress?: JobProgress }) {
  const processed = jobProgress?.processed ?? 0
  const total = jobProgress?.total ?? 0
  const phase = jobProgress?.phase || "Iniciando..."

  const percent: number = jobProgress?.progress_percentage ?? 0

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-20 text-center"
    >
      {/* Spinner */}
      <div className="relative flex h-16 w-16 items-center justify-center">
        <div className="absolute inset-0 animate-ping rounded-full bg-primary/20" aria-hidden="true" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-border bg-card shadow-md">
          <Loader2 className="h-7 w-7 animate-spin text-primary" aria-hidden="true" />
        </div>
      </div>

      {/* Text */}
      <div className="max-w-sm space-y-1 w-full">
        <p className="text-base font-medium text-foreground">{phase}</p>
        {total > 0 && (
          <p className="text-xs text-muted-foreground">
            {processed} / {total} leads procesados
          </p>
        )}
        {!total && (
          <p className="text-xs text-muted-foreground text-pretty">
            Extrayendo perfiles, analizando triggers de noticias y redactando mensajes personalizados.
          </p>
        )}
      </div>

      {/* Progress bar */}
      <div className="w-full max-w-sm space-y-2">
        <div className="flex items-center justify-between text-sm font-medium w-full gap-2">
          <span className="text-muted-foreground truncate" title={phase}>{phase}</span>
          <span className="text-primary shrink-0">{percent}%</span>
        </div>
        <div
          className="relative w-full h-4 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          {percent > 0 ? (
            <div
              className="absolute top-0 left-0 h-full rounded-full bg-primary transition-all duration-500 ease-out"
              style={{ width: `${percent}%` }}
            />
          ) : (
            // Indeterminate shimmer before any phase signal
            <div className="absolute top-0 left-0 h-full w-1/3 rounded-full bg-primary animate-[shimmer_1.5s_ease-in-out_infinite]" />
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * TimeoutState — Shown when the 5-minute polling budget is exhausted.
 * The backend may still be working; this gives the user two clear options.
 */
function TimeoutState({ onManualCheck }: { onManualCheck?: () => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-1 flex-col items-center justify-center gap-5 px-6 py-20 text-center"
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full border border-amber-300 bg-amber-50 dark:bg-amber-950/40 dark:border-amber-700">
        <AlertCircle className="h-7 w-7 text-amber-600 dark:text-amber-400" aria-hidden="true" />
      </div>
      <div className="max-w-md space-y-2">
        <p className="text-base font-semibold text-foreground">
          El backend sigue procesando los leads
        </p>
        <p className="text-xs text-muted-foreground text-pretty">
          Batches grandes (15+ perfiles) pueden tardar más de 5 minutos. El proceso{" "}
          <strong>no se ha cancelado</strong>. Puedes esperar y volver a verificar, o intentar
          cargar los resultados en este momento.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <button
          type="button"
          onClick={onManualCheck}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Seguir esperando
        </button>
        <button
          type="button"
          onClick={onManualCheck}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Search className="h-4 w-4" aria-hidden="true" />
          Cargar resultados manualmente
        </button>
      </div>
    </div>
  )
}

function EmptyState({ hasSearched }: { hasSearched: boolean }) {
  if (hasSearched) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center animate-in fade-in-50 duration-300">
        <div className="flex h-16 w-16 items-center justify-center rounded-full border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900 shadow-sm">
          <AlertCircle className="h-7 w-7 text-amber-600 dark:text-amber-400" aria-hidden="true" />
        </div>
        <div className="max-w-md space-y-3">
          <p className="text-base font-semibold text-foreground">Sin resultados calificados</p>
          <div className="rounded-lg border border-amber-200/50 bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-800 dark:text-amber-300 dark:border-amber-800/30 shadow-inner">
            No companies or targets discovered matching the active search parameters.
          </div>
        </div>
      </div>
    )
  }

  // Premium idle state — communicates the 3-step AI workflow
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 px-8 py-16 text-center">
      <div className="space-y-2">
        <div className="flex h-14 w-14 mx-auto items-center justify-center rounded-2xl border border-primary/20 bg-primary/5 shadow-sm">
          <Search className="h-6 w-6 text-primary" aria-hidden="true" />
        </div>
        <p className="text-base font-semibold text-foreground">Panel listo para prospectar</p>
        <p className="text-xs text-muted-foreground max-w-xs">
          Configura los criterios en el formulario e inicia la búsqueda automática de leads.
        </p>
      </div>

      {/* 3-step workflow illustration */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-sm">
        {[
          { icon: Users, label: "LinkedIn", desc: "Extrae perfiles calificados" },
          { icon: Loader2, label: "Análisis IA", desc: "Evalua y enriquece con Groq" },
          { icon: Mail, label: "Mensajes", desc: "Redacta outreach personalizado" },
        ].map(({ icon: Icon, label, desc }) => (
          <div
            key={label}
            className="flex flex-col items-center gap-2 rounded-xl border border-border/60 bg-card/60 p-3"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
            </div>
            <p className="text-xs font-semibold text-foreground">{label}</p>
            <p className="text-[10px] text-muted-foreground leading-tight">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function safeRender(val: unknown): string {
  if (val === null || val === undefined) return "—"
  if (typeof val === "object") {
    const obj = val as Record<string, unknown>
    const str = obj.name || obj.title || obj.text || obj.companyName || obj.fullName
    if (str && typeof str === "string") return str
    try {
      return JSON.stringify(val)
    } catch {
      return String(val)
    }
  }
  return String(val)
}

function safeUrl(val: unknown): string {
  if (!val) return ""
  if (typeof val === "string") {
    const trimmed = val.trim()
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return trimmed
    }
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(trimmed)
        return safeUrl(parsed)
      } catch {
        // Fall through
      }
    }
    return trimmed
  }
  if (typeof val === "object") {
    const obj = val as Record<string, unknown>
    const keys = ["linkedin_url", "linkedInUrl", "url", "link", "linkedin"]
    for (const key of keys) {
      if (typeof obj[key] === "string" && obj[key]) {
        return obj[key] as string
      }
    }
    if (Array.isArray(val) && val.length > 0) {
      return safeUrl(val[0])
    }
  }
  return ""
}

/* ------------------------------------------------------------------ */
/*  Dashboard con gráfico + KPIs + botón Guardar                      */
/* ------------------------------------------------------------------ */

interface DashboardContentProps {
  results: ProspectResult[]
  formData: ProspectRequest
  savedQueries: SavedQuery[]
  activeQueryId: string | null
  onSaveQuery: (name: string, isOverwrite?: boolean, existingId?: string) => void
}

function DashboardContent({ results, formData, savedQueries, activeQueryId, onSaveQuery }: DashboardContentProps) {
  const [saveDialogOpen, setSaveDialogOpen] = useState(false)
  const [queryName, setQueryName] = useState("")
  const [conflictingQuery, setConflictingQuery] = useState<SavedQuery | null>(null)
  const [isUpdateMode, setIsUpdateMode] = useState(false)

  // Clasificación de leads en 3 estados: Calificado (con lead), Empresa Apta (sin lead), Descalificado
  const calificadosConLead = results.filter((r) => r.es_calificado && r.nombre_lead && r.nombre_lead !== "Contacto Pendiente")
  const empresasAptas = results.filter((r) => r.es_calificado && r.nombre_lead === "Contacto Pendiente")
  const calificados = results.filter((r) => r.es_calificado) // Total calificados (incluye empresa apta)
  const desconocidos = results.filter(
    (r) => !r.es_calificado && (!r.nombre_lead || r.nombre_lead === "Desconocido" || r.nombre_lead === "—")
  )
  const descartados = results.filter(
    (r) => !r.es_calificado && r.nombre_lead && r.nombre_lead !== "Desconocido" && r.nombre_lead !== "—"
  )

  const chartData = [
    { name: "Calificados", value: calificadosConLead.length, color: "#10b981" },
    { name: "Empresa Apta", value: empresasAptas.length, color: "#f59e0b" },
    { name: "Descartados", value: descartados.length, color: "#4b5563" },
    { name: "Desconocidos", value: desconocidos.length, color: "#9ca3af" },
  ].filter((item) => item.value > 0) // Ocultar segmentos sin valores

  const handleSaveClick = () => {
    // [Safety Mechanism]: Modal State Safety
    // Safely reads activeQueryId to switch between Update vs Create modes
    if (activeQueryId) {
      const activeQuery = savedQueries.find(q => q.id === activeQueryId)
      if (activeQuery) {
        setQueryName(activeQuery.query_name)
        setIsUpdateMode(true)
      } else {
        setIsUpdateMode(false)
        setQueryName("")
      }
    } else {
      setIsUpdateMode(false)
      setQueryName("")
    }
    setSaveDialogOpen(true)
  }

  const handleSave = () => {
    const name = queryName.trim()
    if (!name) return

    if (isUpdateMode && activeQueryId) {
      // Direct update of the active query
      onSaveQuery(name, true, activeQueryId)
      setQueryName("")
      setSaveDialogOpen(false)
      setIsUpdateMode(false)
      return
    }

    const existing = savedQueries.find(
      (q) => q.query_name.trim().toLowerCase() === name.toLowerCase()
    )

    if (existing) {
      setConflictingQuery(existing)
    } else {
      onSaveQuery(name)
      setQueryName("")
      setSaveDialogOpen(false)
    }
  }

  const handleConfirmOverwrite = () => {
    if (conflictingQuery) {
      onSaveQuery(queryName.trim(), true, conflictingQuery.id)
      setQueryName("")
      setConflictingQuery(null)
      setSaveDialogOpen(false)
    }
  }

  // Nombre sugerido basado en datos del formulario
  const suggestedName = [formData.sector, formData.pais, formData.cargo_decision]
    .filter(Boolean)
    .join(" — ")

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Botón Guardar Consulta */}
      <div className="flex items-center justify-end px-4 pt-3 pb-1">
        <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
          <Button variant="outline" size="sm" className="gap-1.5 text-xs" onClick={handleSaveClick}>
            <Save className="h-3.5 w-3.5" />
            Guardar Consulta
          </Button>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Guardar consulta en historial</DialogTitle>
              <DialogDescription>
                Asigna un nombre descriptivo para identificarla fácilmente después.
              </DialogDescription>
            </DialogHeader>
            {isUpdateMode ? (
              <div className="flex flex-col gap-3 py-2">
                <div className="p-3 bg-blue-50 text-blue-900 border border-blue-200 rounded-md text-sm">
                  Estás editando la consulta <strong>{queryName}</strong>.
                </div>
                <div className="flex flex-col gap-2 mt-2">
                  <Label htmlFor="query-update-name" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Actualizar nombre (opcional)
                  </Label>
                  <Input
                    id="query-update-name"
                    value={queryName}
                    onChange={(e) => setQueryName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave()
                    }}
                    autoFocus
                  />
                </div>
                <DialogFooter className="mt-4">
                  <Button variant="outline" size="sm" onClick={() => { setSaveDialogOpen(false); setQueryName(""); setIsUpdateMode(false); }}>
                    Cancelar
                  </Button>
                  <Button variant="default" size="sm" onClick={handleSave} className="bg-blue-600 hover:bg-blue-700">
                    Actualizar
                  </Button>
                </DialogFooter>
              </div>
            ) : conflictingQuery ? (
              <div className="flex flex-col gap-3 py-2">
                <div className="p-3 bg-amber-50 text-amber-900 border border-amber-200 rounded-md text-sm">
                  Ya existe una consulta llamada <strong>{conflictingQuery.query_name}</strong>. ¿Deseas sobrescribirla?
                </div>
                <div className="flex justify-end gap-2 mt-2">
                  <Button variant="outline" size="sm" onClick={() => setConflictingQuery(null)}>
                    Volver y cambiar nombre
                  </Button>
                  <Button variant="default" size="sm" onClick={handleConfirmOverwrite} className="bg-amber-600 hover:bg-amber-700">
                    Sobrescribir
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-3 py-2">
                  <Label htmlFor="query-name" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Nombre de la consulta
                  </Label>
                  <Input
                    id="query-name"
                    placeholder={suggestedName || "Ej: Campaña Real Estate Q3"}
                    value={queryName}
                    onChange={(e) => setQueryName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave()
                    }}
                    autoFocus
                  />
                </div>
                <DialogFooter>
                  <Button variant="outline" size="sm" onClick={() => { setSaveDialogOpen(false); setQueryName(""); setConflictingQuery(null); }}>
                    Cancelar
                  </Button>
                  <Button size="sm" onClick={handleSave} disabled={!queryName.trim()} className="gap-1.5">
                    <Save className="h-3.5 w-3.5" />
                    Guardar
                  </Button>
                </DialogFooter>
              </>
            )}
          </DialogContent>
        </Dialog>
      </div>

      {/* Sección superior: Dashboard Visual */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 bg-muted/20 border-b border-border/60 items-stretch">
        {/* KPIs Stat Cards */}
        <div className="flex flex-col justify-between gap-3 md:col-span-1 h-full">
          <Card className="bg-card shadow-none border-border/60 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Total Extraídos
              </span>
              <Users className="h-4 w-4 text-primary" />
            </div>
            <div className="mt-1.5 flex items-baseline gap-1">
              <span className="text-2xl font-bold">{results.length}</span>
              <span className="text-xs text-muted-foreground">leads</span>
            </div>
          </Card>

          <Card className="bg-card shadow-none border-border/60 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Calificados
              </span>
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            </div>
            <div className="mt-1.5 flex items-baseline gap-1">
              <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {calificados.length}
              </span>
              <span className="text-xs text-muted-foreground">
                ({((calificados.length / results.length) * 100).toFixed(0)}%)
              </span>
            </div>
          </Card>

          <div className="grid grid-cols-2 gap-2">
            <Card className="bg-card shadow-none border-border/60 p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium text-muted-foreground uppercase">
                  Descart.
                </span>
                <XCircle className="h-3 w-3 text-amber-500" />
              </div>
              <div className="mt-1 text-base font-bold text-amber-600 dark:text-amber-400">
                {descartados.length}
              </div>
            </Card>
            <Card className="bg-card shadow-none border-border/60 p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-medium text-muted-foreground uppercase">
                  Descon.
                </span>
                <HelpCircle className="h-3 w-3 text-slate-500" />
              </div>
              <div className="mt-1 text-base font-bold text-slate-600 dark:text-slate-400">
                {desconocidos.length}
              </div>
            </Card>
          </div>
        </div>

        {/* Gráfico Torta — sin tooltip en hover */}
        <div className="md:col-span-1 flex flex-col bg-card rounded-lg border border-border/60 p-2 h-full min-h-[220px]">
          <span className="text-xs font-medium text-muted-foreground px-2 pt-1">
            Distribución de Leads
          </span>
          <div className="w-full flex-1 min-h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartData}
                  cx="50%"
                  cy="50%"
                  innerRadius={35}
                  outerRadius={65}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} stroke="hsl(var(--card))" strokeWidth={2} />
                  ))}
                </Pie>
                {/* Tooltip removed intentionally — no hover info on donut slices */}
                <Legend verticalAlign="bottom" height={28} iconType="circle" iconSize={8} wrapperStyle={{ fontSize: "10px" }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Embudo de Prospección — BarChart sin tooltip */}
        <div className="md:col-span-1 flex flex-col bg-card rounded-lg border border-border/60 p-2 h-full min-h-[220px]">
          <span className="text-xs font-medium text-muted-foreground px-2 pt-1">
            Embudo de Prospección
          </span>
          <div className="w-full flex-1 min-h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[
                  { name: "Extraídos", value: results.length, fill: "#000000" },
                  { name: "Analizados", value: results.length - desconocidos.length, fill: "#4b5563" },
                  { name: "Calificados", value: calificadosConLead.length, fill: "#10b981" },
                  { name: "Empresa Apta", value: empresasAptas.length, fill: "#f59e0b" },
                ]}
                margin={{ top: 20, right: 10, left: -10, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
                {/* Tooltip removed intentionally — values visible via LabelList */}
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {[
                    { fill: "#000000" },
                    { fill: "#4b5563" },
                    { fill: "#9ca3af" },
                  ].map((entry, index) => (
                    <Cell key={`bar-${index}`} fill={entry.fill} />
                  ))}
                  <LabelList dataKey="value" position="top" className="text-[11px] font-bold fill-foreground" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Listado en Tabla Optimizada con Sorting */}
      <ResultsTable results={results} />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Tabla con sorting                                                  */
/* ------------------------------------------------------------------ */

type SortOrder = "relevancia" | "nombre-asc"
type TableFilter = "todos" | "calificados" | "descartados"

function ReviewEmailDialog({
  result,
  onCopy
}: {
  result: ProspectResult
  onCopy: (body: string) => void
}) {
  const [subject, setSubject] = useState(`Explorando sinergias con ${result.empresa || 'tu empresa'}`)
  const [body, setBody] = useState(result.mensaje_generado || "")
  const [isOpen, setIsOpen] = useState(false)
  const { toast } = useToast()

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button
          variant="default"
          size="sm"
          className="h-7 text-[10px] w-full bg-blue-600 hover:bg-blue-700 text-white gap-1"
        >
          <Eye className="h-3.5 w-3.5" />
          Ver Mensaje
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Mensaje de Prospección Generado</DialogTitle>
          <DialogDescription>Revisa y copia el asunto y el cuerpo del correo personalizado por IA.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4 py-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor={`subject-${result.id}`} className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Asunto</Label>
            <Input id={`subject-${result.id}`} value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`body-${result.id}`} className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Mensaje</Label>
            <Textarea id={`body-${result.id}`} rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
        </div>
        <DialogFooter className="flex justify-end gap-2 mt-4">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              navigator.clipboard.writeText(subject)
              toast({
                title: "Asunto copiado",
                description: "El asunto del correo ha sido copiado al portapapeles.",
              })
            }}
            className="gap-1.5"
          >
            <Copy className="h-4 w-4" />
            Copiar Asunto
          </Button>
          <Button
            size="sm"
            onClick={() => {
              onCopy(body)
              setIsOpen(false)
            }}
            className="gap-1.5 bg-blue-600 hover:bg-blue-700 text-white"
          >
            <Copy className="h-4 w-4" />
            Copiar Cuerpo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ResultsTable({ results }: { results: ProspectResult[] }) {
  const { toast } = useToast()
  const { isConnected, sendEmail } = useIntegrations()
  const [sortOrder, setSortOrder] = useState<SortOrder>("relevancia")
  const [tableFilter, setTableFilter] = useState<TableFilter>("todos")
  const [sendingEmailId, setSendingEmailId] = useState<string | null>(null)

  const handleSendEmail = async (lead: ProspectResult, subject: string, body: string) => {
    if (!lead.email) return

    setSendingEmailId(lead.nombre_lead || "unknown")
    
    try {
      const success = await sendEmail({
        leadId: lead.id!,
        subject: subject,
        body: body
      })

      if (success) {
        toast({
          title: "Correo enviado exitosamente",
          description: `El correo a ${lead.nombre_lead || 'el prospecto'} ha sido enviado.`,
        })
      } else {
        toast({
          variant: "destructive",
          title: "Error al enviar correo",
          description: `No se pudo enviar el correo a ${lead.nombre_lead || 'el prospecto'}. Verifica la conexión con Google.`,
        })
      }
    } catch (err) {
      console.error("[Frontend] Error enviando correo:", err)
      toast({
        variant: "destructive",
        title: "Error de red",
        description: "Ocurrió un error inesperado al intentar enviar el correo.",
      })
    } finally {
      setSendingEmailId(null)
    }
  }

  const filteredResults = useMemo(() => {
    switch (tableFilter) {
      case "calificados":
        return results.filter((r) => r.es_calificado)
      case "descartados":
        return results.filter((r) => !r.es_calificado)
      default:
        return results
    }
  }, [results, tableFilter])

  const sortedResults = useMemo(() => {
    const copy = [...filteredResults]
    switch (sortOrder) {
      case "relevancia":
        return copy.sort((a, b) => {
          if (a.es_calificado === b.es_calificado) return 0
          return a.es_calificado ? -1 : 1
        })
      case "nombre-asc":
        return copy.sort((a, b) => {
          const nameA = (a.nombre_lead || "").toLowerCase()
          const nameB = (b.nombre_lead || "").toLowerCase()
          return nameA.localeCompare(nameB, "es")
        })
      default:
        return copy
    }
  }, [filteredResults, sortOrder])

  const calCount = results.filter((r) => r.es_calificado).length
  const descCount = results.filter((r) => !r.es_calificado).length

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Filter tabs + Sorting control */}
      <div className="flex flex-col gap-0 border-b border-border/60 bg-card/50">
        {/* Quick filter tabs */}
        <div className="px-4 pt-3 pb-2">
          <Tabs value={tableFilter} onValueChange={(v) => setTableFilter(v as TableFilter)} className="w-full">
            <TabsList className="w-full max-w-md">
              <TabsTrigger value="todos" className="flex-1 text-xs gap-1">
                Todos
                <Badge variant="secondary" className="ml-1 h-4 min-w-[18px] px-1 text-[9px] font-mono">{results.length}</Badge>
              </TabsTrigger>
              <TabsTrigger value="calificados" className="flex-1 text-xs gap-1">
                Calificados
                <Badge variant="secondary" className="ml-1 h-4 min-w-[18px] px-1 text-[9px] font-mono">{calCount}</Badge>
              </TabsTrigger>
              <TabsTrigger value="descartados" className="flex-1 text-xs gap-1">
                Descartados
                <Badge variant="secondary" className="ml-1 h-4 min-w-[18px] px-1 text-[9px] font-mono">{descCount}</Badge>
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        {/* Sorting */}
        <div className="flex items-center gap-2 px-4 pb-2.5">
          <Label className="text-xs font-medium text-muted-foreground whitespace-nowrap">Ordenar por:</Label>
          <Select value={sortOrder} onValueChange={(v) => setSortOrder(v as SortOrder)}>
            <SelectTrigger className="h-8 w-[260px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="relevancia">Relevancia (Calificados primero)</SelectItem>
              <SelectItem value="nombre-asc">Nombre (A-Z)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Tabla */}
      <div className="flex-1 overflow-x-auto">
        {/* Implementación de table-fixed w-full y anchos de columna estrictos */}
        <Table className="table-fixed w-full min-w-[1300px]">
          <TableHeader className="sticky top-0 z-10 bg-card border-b border-border/80 shadow-2xs">
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[150px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Nombre
              </TableHead>
              <TableHead className="w-[150px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Empresa
              </TableHead>
              <TableHead className="w-[150px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Cargo
              </TableHead>
              <TableHead className="w-[110px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Estado
              </TableHead>
              <TableHead className="w-[90px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Link
              </TableHead>
              <TableHead className="w-[90px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Fuente
              </TableHead>
              <TableHead className="w-[160px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Contacto
              </TableHead>
              <TableHead className="w-[250px] text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Noticia / Trigger encontrado
              </TableHead>
              <TableHead className="w-[150px] text-xs font-semibold uppercase tracking-wide text-muted-foreground text-center">
                Mensaje / Acción
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedResults.map((result, index) => {
              const nombre = safeRender(result.nombre_lead)
              const empresa = safeRender(result.empresa)
              const cargo = safeRender(result.cargo)
              const trigger = safeRender(result.trigger_noticia)
              const mensaje = safeRender(result.mensaje_generado)
              const url = safeUrl(result.linkedin_url)
              const email = result.email || ""
              const telefono = result.telefono || ""

              return (
                <TableRow key={`${nombre}-${index}`} className="align-middle hover:bg-muted/30 transition-colors">
                  <TableCell className="font-medium text-foreground">
                    <div className="truncate" title={nombre}>
                      {nombre}
                    </div>
                  </TableCell>
                  <TableCell className="text-foreground">
                    <div className="truncate" title={empresa}>
                      {empresa}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    <div className="truncate" title={cargo}>
                      {cargo}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col items-start gap-1.5">
                      {result.es_calificado && result.nombre_lead !== "Contacto Pendiente" ? (
                        <Badge variant="default" className="text-xs bg-emerald-500 hover:bg-emerald-600">
                          Calificado
                        </Badge>
                      ) : result.es_calificado && result.nombre_lead === "Contacto Pendiente" ? (
                        <Badge variant="default" className="text-xs bg-amber-500 hover:bg-amber-600">
                          Empresa Apta
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-xs">
                          No calificado
                        </Badge>
                      )}
                      {result.razonamiento_filtro && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors cursor-help max-w-full"
                              aria-label="Ver razonamiento del filtro IA"
                            >
                              <Info className="h-3 w-3 shrink-0" aria-hidden="true" />
                              <span className="truncate">
                                {safeRender(result.razonamiento_filtro)}
                              </span>
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="bottom" className="max-w-xs text-xs leading-relaxed">
                            <p className="font-medium mb-0.5">Razonamiento IA</p>
                            <p>{safeRender(result.razonamiento_filtro)}</p>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    {url ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-semibold text-primary underline-offset-4 hover:underline"
                      >
                        <span>Perfil</span>
                        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                      </a>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {(() => {
                      if (!result.url_noticia) return <span className="text-xs text-muted-foreground">—</span>;
                      
                      let parsedNews: { title: string; url: string }[] = [];
                      let isJsonNews = false;
                      try {
                        let rawStr = result.url_noticia.trim();
                        if (rawStr) {
                          // Absorber strings JSON con doble serialización (comillas externas adicionales y caracteres escapados)
                          if (rawStr.startsWith('"') && rawStr.endsWith('"') && rawStr.length > 2) {
                            try {
                              const parsedStr = JSON.parse(rawStr);
                              if (typeof parsedStr === "string") {
                                rawStr = parsedStr.trim();
                              } else if (Array.isArray(parsedStr)) {
                                parsedNews = parsedStr;
                                isJsonNews = true;
                              }
                            } catch (e) {}
                          }
                          
                          if (!isJsonNews && (rawStr.startsWith("[") || rawStr.startsWith("{"))) {
                            const parsed = JSON.parse(rawStr);
                            if (Array.isArray(parsed)) {
                              parsedNews = parsed;
                              isJsonNews = true;
                            }
                          }
                        }
                      } catch (e) {
                        // Fallback automatically
                      }

                      if (isJsonNews && parsedNews.length > 0) {
                        let linkedinCount = 0;
                        let googleCount = 0;
                        return (
                          <div className="flex flex-wrap gap-1 items-center max-w-[120px]">
                            {parsedNews.map((newsItem, idx) => {
                              const isLI = newsItem.url && newsItem.url.includes("linkedin.com");
                              let label = "";
                              let badgeClass = "";
                              
                              if (isLI) {
                                linkedinCount++;
                                label = `L${linkedinCount}`;
                                badgeClass = "bg-blue-600/10 hover:bg-blue-600/20 text-blue-600 dark:text-blue-400 border border-blue-600/20 hover:border-blue-600/40 cursor-pointer font-mono font-bold text-[10px] px-1.5 py-0.5 rounded transition-all hover:scale-105";
                              } else {
                                googleCount++;
                                label = `G${googleCount}`;
                                badgeClass = "bg-amber-600/10 hover:bg-amber-600/20 text-amber-600 dark:text-amber-400 border border-amber-600/20 hover:border-amber-600/40 cursor-pointer font-mono font-bold text-[10px] px-1.5 py-0.5 rounded transition-all hover:scale-105";
                              }

                              return (
                                <Tooltip key={idx}>
                                  <TooltipTrigger asChild>
                                    <a
                                      href={newsItem.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className={badgeClass}
                                    >
                                      {label}
                                    </a>
                                  </TooltipTrigger>
                                  <TooltipContent side="bottom" className="max-w-xs text-xs leading-relaxed">
                                    <p className="font-semibold mb-0.5">{isLI ? "LinkedIn Post / Evento" : "Noticia de Prensa / Google"}</p>
                                    <p className="line-clamp-3 text-pretty">{newsItem.title}</p>
                                    <p className="text-[10px] text-muted-foreground truncate mt-1">{newsItem.url}</p>
                                  </TooltipContent>
                                </Tooltip>
                              );
                            })}
                          </div>
                        );
                      }

                      // Verificar si la URL es absoluta para evitar links relativos rotos en Vercel
                      const isAbsoluteUrl = result.url_noticia && (result.url_noticia.startsWith("http://") || result.url_noticia.startsWith("https://"));
                      
                      if (isAbsoluteUrl) {
                        return (
                          <a
                            href={result.url_noticia}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={result.url_noticia}
                            className="inline-flex items-center gap-1 text-xs font-semibold text-amber-500 hover:text-amber-400 underline-offset-4 hover:underline transition-colors"
                          >
                            <span>Noticia</span>
                            <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                          </a>
                        );
                      } else {
                        // Si falló el parseo y no es URL absoluta, renderizar como texto plano para no romper la interfaz
                        return (
                          <span className="text-xs text-muted-foreground block truncate max-w-[120px]" title={result.url_noticia}>
                            {result.url_noticia}
                          </span>
                        );
                      }
                    })()}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1.5 text-xs text-muted-foreground">
                      {email ? (
                        <span className="flex items-center gap-1 truncate" title={email}>
                          <Mail className="h-3 w-3 shrink-0" />
                          <span className="truncate">{email}</span>
                        </span>
                      ) : result.es_calificado ? (
                        <span className="flex items-center gap-1 text-[10px] italic">Sin email</span>
                      ) : null}
                      {telefono && (
                        <span className="flex items-center gap-1 truncate" title={telefono}>
                          <Phone className="h-3 w-3 shrink-0" />
                          <span className="truncate">{telefono}</span>
                        </span>
                      )}
                      {!email && !telefono && !result.es_calificado && (
                        <span>—</span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    <div className="line-clamp-2 text-pretty" title={trigger}>
                      {trigger}
                    </div>
                  </TableCell>
                  <TableCell className="text-center">
                    {result.es_calificado && result.nombre_lead !== "Contacto Pendiente" ? (
                      <div className="flex flex-col gap-1.5 items-center w-full max-w-[120px] mx-auto">
                        <ReviewEmailDialog
                          result={result}
                          onCopy={(body) => {
                            navigator.clipboard.writeText(body)
                            toast({
                              title: "Copiado al portapapeles",
                              description: "El mensaje ha sido copiado exitosamente.",
                            })
                          }}
                        />
                      </div>
                    ) : result.es_calificado && result.nombre_lead === "Contacto Pendiente" ? (
                      <Badge variant="outline" className="text-[11px] text-amber-600 dark:text-amber-400 border-amber-500/40 font-medium">
                        Prospección Manual
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[11px] text-muted-foreground font-normal">
                        Descartado
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Panel de Historial                                                 */
/* ------------------------------------------------------------------ */

type HistorySortOrder = "modificacion-desc" | "creacion-desc" | "nombre-asc"

function HistoryPanel({
  savedQueries,
  onLoadQuery,
  onDeleteQuery,
}: {
  savedQueries: SavedQuery[]
  onLoadQuery: (query: SavedQuery) => void
  onDeleteQuery: (id: string) => void
}) {
  const [historySortOrder, setHistorySortOrder] = useState<HistorySortOrder>("modificacion-desc")

  if (savedQueries.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-muted/50">
          <Clock className="h-7 w-7 text-muted-foreground" aria-hidden="true" />
        </div>
        <div className="max-w-md space-y-1">
          <p className="text-base font-medium text-foreground">Sin consultas guardadas</p>
          <p className="text-xs text-muted-foreground text-pretty">
            Ejecuta una prospección y guárdala usando el botón &quot;Guardar Consulta&quot; para verla aquí.
          </p>
        </div>
      </div>
    )
  }

  const sorted = [...savedQueries].sort((a, b) => {
    switch (historySortOrder) {
      case "modificacion-desc":
        return new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime()
      case "creacion-desc":
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      case "nombre-asc":
        return a.query_name.localeCompare(b.query_name, "es")
      default:
        return 0
    }
  })

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString("es-ES", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Sorting control */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60 bg-card/50">
        <ArrowDownUp className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <Label className="text-xs font-medium text-muted-foreground whitespace-nowrap">Ordenar:</Label>
        <Select value={historySortOrder} onValueChange={(v) => setHistorySortOrder(v as HistorySortOrder)}>
          <SelectTrigger className="h-8 w-[280px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="modificacion-desc">Fecha de modificación (Más recientes)</SelectItem>
            <SelectItem value="creacion-desc">Fecha de creación (Más recientes)</SelectItem>
            <SelectItem value="nombre-asc">Nombre (A-Z)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-2 p-4">
          {sorted.map((query) => {
            const params = query.search_params;
            const contextStr = [params.sector, params.pais, params.cargo_decision].filter(Boolean).join(", ")

            return (
              <Card key={query.id} className="bg-card shadow-none border-border/60 p-0 overflow-hidden">
                <div className="flex items-center justify-between gap-3 p-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate" title={query.query_name}>
                      {query.query_name}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1" title="Última modificación">
                        <Clock className="h-3 w-3" />
                        {formatDate(query.updated_at || query.created_at)}
                      </span>
                      <span className="flex items-center gap-1 truncate max-w-[200px]" title={contextStr}>
                        <Search className="h-3 w-3" />
                        {contextStr || "Sin filtros específicos"}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 gap-1.5 text-xs"
                      onClick={() => onLoadQuery(query)}
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Ver
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                      onClick={() => onDeleteQuery(query.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span className="sr-only">Eliminar consulta</span>
                    </Button>
                  </div>
                </div>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
