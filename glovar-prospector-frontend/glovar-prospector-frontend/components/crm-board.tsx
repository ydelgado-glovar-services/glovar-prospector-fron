"use client"

/**
 * components/crm-board.tsx — Tablero Kanban del Mini-CRM.
 *
 * Vista de pipeline corporativo: columnas por etapa, tarjetas de leads con
 * prioridad, etiquetas personalizadas y notas internas. La tarjeta abre un
 * panel de detalle con toda la información del lead y herramientas de gestión.
 *
 * Nota: no se usa drag-and-drop (sin dependencias de DnD instaladas). El
 * movimiento entre etapas se hace con un selector y botones de avance/retroceso,
 * lo que además resulta más accesible y predecible para usuarios corporativos.
 */

import { useMemo, useState } from "react"
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Inbox,
  Mail,
  Phone,
  Plus,
  StickyNote,
  Tag as TagIcon,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { useToast } from "@/hooks/use-toast"
import { useCrm } from "@/components/crm-provider"
import { CRM_STAGES, type CrmLead, type CrmStage, type CrmPriority } from "@/lib/types"

const PRIORITY_META: Record<CrmPriority, { label: string; className: string }> = {
  alta: { label: "Alta", className: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30" },
  media: { label: "Media", className: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  baja: { label: "Baja", className: "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/30" },
}

function stageIndex(stage: CrmStage) {
  return CRM_STAGES.findIndex((s) => s.id === stage)
}

export function CrmBoard() {
  const { crmLeads, isLoading } = useCrm()
  const [selected, setSelected] = useState<CrmLead | null>(null)

  // Mantener el lead seleccionado sincronizado con el estado más reciente del provider.
  const selectedLive = useMemo(
    () => (selected ? crmLeads.find((c) => c.id === selected.id) ?? null : null),
    [selected, crmLeads],
  )

  const leadsByStage = useMemo(() => {
    const map: Record<string, CrmLead[]> = {}
    for (const stage of CRM_STAGES) map[stage.id] = []
    for (const lead of crmLeads) {
      ;(map[lead.stage] ?? (map[lead.stage] = [])).push(lead)
    }
    return map
  }, [crmLeads])

  const wonCount = leadsByStage["ganado"]?.length ?? 0

  if (isLoading && crmLeads.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center py-24">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    )
  }

  if (crmLeads.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-muted/50">
          <Inbox className="h-7 w-7 text-muted-foreground" />
        </div>
        <div className="max-w-md space-y-1">
          <p className="text-base font-semibold text-foreground">Tu CRM está vacío</p>
          <p className="text-xs text-muted-foreground text-pretty">
            Desde los resultados de prospección, usa el botón <strong>&quot;Enviar a CRM&quot;</strong> en
            un lead calificado para empezar a gestionarlo aquí.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-4">
      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total en CRM" value={crmLeads.length} icon={<Building2 className="h-4 w-4 text-primary" />} />
        <KpiCard label="En conversación" value={leadsByStage["en_conversacion"]?.length ?? 0} icon={<Mail className="h-4 w-4 text-amber-500" />} />
        <KpiCard label="Propuestas" value={leadsByStage["propuesta"]?.length ?? 0} icon={<StickyNote className="h-4 w-4 text-purple-500" />} />
        <KpiCard label="Ganados" value={wonCount} icon={<TrendingUp className="h-4 w-4 text-emerald-500" />} />
      </div>

      {/* Kanban */}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {CRM_STAGES.map((stage) => {
          const items = leadsByStage[stage.id] ?? []
          return (
            <div key={stage.id} className="flex w-[280px] shrink-0 flex-col rounded-lg border border-border/60 bg-muted/30">
              <div className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: stage.color }} />
                  <span className="text-sm font-semibold text-foreground">{stage.label}</span>
                </div>
                <Badge variant="secondary" className="h-5 min-w-[20px] px-1.5 font-mono text-[10px]">
                  {items.length}
                </Badge>
              </div>
              <div className="flex flex-col gap-2 p-2">
                {items.length === 0 ? (
                  <p className="px-2 py-6 text-center text-[11px] text-muted-foreground">Sin leads</p>
                ) : (
                  items.map((lead) => (
                    <KanbanCard key={lead.id} lead={lead} onOpen={() => setSelected(lead)} />
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>

      <LeadDetailDialog lead={selectedLive} open={!!selectedLive} onClose={() => setSelected(null)} />
    </div>
  )
}

function KpiCard({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <Card className="border-border/60 p-3 shadow-none">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
        {icon}
      </div>
      <div className="mt-1.5 text-2xl font-bold">{value}</div>
    </Card>
  )
}

function KanbanCard({ lead, onOpen }: { lead: CrmLead; onOpen: () => void }) {
  const { updateLead } = useCrm()
  const idx = stageIndex(lead.stage)
  const prio = PRIORITY_META[(lead.priority as CrmPriority) ?? "media"]

  const move = (dir: -1 | 1) => {
    const next = CRM_STAGES[idx + dir]
    if (next) updateLead(lead.id, { stage: next.id })
  }

  return (
    <Card className="group cursor-pointer border-border/60 p-2.5 shadow-none transition-colors hover:border-primary/50 hover:bg-card">
      <div onClick={onOpen} className="flex flex-col gap-1.5">
        <div className="flex items-start justify-between gap-2">
          <p className="line-clamp-1 text-sm font-semibold text-foreground" title={lead.nombre_lead ?? ""}>
            {lead.nombre_lead || "Contacto"}
          </p>
          <Badge variant="outline" className={`shrink-0 text-[9px] ${prio.className}`}>{prio.label}</Badge>
        </div>
        <p className="line-clamp-1 text-xs text-muted-foreground" title={lead.empresa ?? ""}>
          {lead.empresa || "—"}
        </p>
        {lead.cargo && <p className="line-clamp-1 text-[11px] text-muted-foreground/80">{lead.cargo}</p>}
        {lead.tags && lead.tags.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1">
            {lead.tags.slice(0, 3).map((t) => (
              <span key={t} className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-medium text-primary">
                {t}
              </span>
            ))}
            {lead.tags.length > 3 && <span className="text-[9px] text-muted-foreground">+{lead.tags.length - 3}</span>}
          </div>
        )}
        {lead.notes && lead.notes.length > 0 && (
          <span className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
            <StickyNote className="h-3 w-3" /> {lead.notes.length} nota{lead.notes.length === 1 ? "" : "s"}
          </span>
        )}
      </div>
      {/* Controles de movimiento entre etapas */}
      <div className="mt-2 flex items-center justify-between border-t border-border/40 pt-1.5">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-1.5 text-muted-foreground disabled:opacity-30"
          disabled={idx <= 0}
          onClick={(e) => { e.stopPropagation(); move(-1) }}
          aria-label="Retroceder etapa"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-1.5 text-muted-foreground disabled:opacity-30"
          disabled={idx >= CRM_STAGES.length - 1}
          onClick={(e) => { e.stopPropagation(); move(1) }}
          aria-label="Avanzar etapa"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </Card>
  )
}

function LeadDetailDialog({ lead, open, onClose }: { lead: CrmLead | null; open: boolean; onClose: () => void }) {
  const { updateLead, removeLead, addNote, deleteNote } = useCrm()
  const { toast } = useToast()
  const [newTag, setNewTag] = useState("")
  const [noteBody, setNoteBody] = useState("")
  const [savingNote, setSavingNote] = useState(false)

  if (!lead) return null

  const tags = lead.tags ?? []

  const handleAddTag = () => {
    const t = newTag.trim()
    if (!t || tags.includes(t)) { setNewTag(""); return }
    updateLead(lead.id, { tags: [...tags, t] })
    setNewTag("")
  }

  const handleRemoveTag = (t: string) => {
    updateLead(lead.id, { tags: tags.filter((x) => x !== t) })
  }

  const handleAddNote = async () => {
    if (!noteBody.trim()) return
    setSavingNote(true)
    const ok = await addNote(lead.id, noteBody.trim())
    setSavingNote(false)
    if (ok) { setNoteBody(""); toast({ title: "Nota agregada" }) }
    else toast({ variant: "destructive", title: "No se pudo agregar la nota" })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {lead.nombre_lead || "Contacto"}
            {lead.linkedin_url && (
              <a href={lead.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                <ExternalLink className="h-4 w-4" />
              </a>
            )}
          </DialogTitle>
          <DialogDescription>
            {[lead.cargo, lead.empresa].filter(Boolean).join(" · ") || "Detalle del lead"}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5 py-2">
          {/* Etapa + Prioridad */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Etapa</Label>
              <Select value={lead.stage} onValueChange={(v) => updateLead(lead.id, { stage: v as CrmStage })}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CRM_STAGES.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Prioridad</Label>
              <Select value={lead.priority ?? "media"} onValueChange={(v) => updateLead(lead.id, { priority: v as CrmPriority })}>
                <SelectTrigger className="h-9 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="alta">Alta</SelectItem>
                  <SelectItem value="media">Media</SelectItem>
                  <SelectItem value="baja">Baja</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Contacto */}
          <div className="grid grid-cols-1 gap-2 rounded-lg border border-border/60 bg-muted/20 p-3 sm:grid-cols-2">
            <InfoRow icon={<Mail className="h-3.5 w-3.5" />} label="Email" value={lead.email} />
            <InfoRow icon={<Phone className="h-3.5 w-3.5" />} label="Teléfono" value={lead.telefono} />
          </div>

          {/* Trigger / Noticia */}
          {lead.trigger_noticia && (
            <div className="flex flex-col gap-1">
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Trigger / Noticia</Label>
              <p className="rounded-md border border-border/60 bg-muted/20 p-2.5 text-xs text-muted-foreground">{lead.trigger_noticia}</p>
            </div>
          )}

          {/* Mensaje generado */}
          {lead.mensaje_generado && (
            <div className="flex flex-col gap-1">
              <Label className="text-[11px] uppercase tracking-wide text-muted-foreground">Mensaje IA</Label>
              <p className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md border border-border/60 bg-muted/20 p-2.5 text-xs text-muted-foreground">{lead.mensaje_generado}</p>
            </div>
          )}

          {/* Etiquetas */}
          <div className="flex flex-col gap-2">
            <Label className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
              <TagIcon className="h-3.5 w-3.5" /> Etiquetas personalizadas
            </Label>
            <div className="flex flex-wrap gap-1.5">
              {tags.length === 0 && <span className="text-xs text-muted-foreground">Sin etiquetas</span>}
              {tags.map((t) => (
                <span key={t} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                  {t}
                  <button type="button" onClick={() => handleRemoveTag(t)} className="hover:text-destructive" aria-label={`Quitar ${t}`}>
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <Input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddTag() } }}
                placeholder="Ej: Contactar el martes, Alta Prioridad"
                className="h-9 text-sm"
              />
              <Button size="sm" variant="outline" onClick={handleAddTag} className="gap-1 shrink-0">
                <Plus className="h-3.5 w-3.5" /> Añadir
              </Button>
            </div>
          </div>

          {/* Notas internas */}
          <div className="flex flex-col gap-2">
            <Label className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
              <StickyNote className="h-3.5 w-3.5" /> Notas internas
            </Label>
            <div className="flex gap-2">
              <Textarea
                value={noteBody}
                onChange={(e) => setNoteBody(e.target.value)}
                placeholder="Ej: Llamé el lunes, pidió propuesta para el viernes…"
                rows={2}
                className="text-sm"
              />
              <Button size="sm" onClick={handleAddNote} disabled={savingNote || !noteBody.trim()} className="shrink-0 self-start gap-1">
                <Plus className="h-3.5 w-3.5" /> Nota
              </Button>
            </div>
            <div className="flex flex-col gap-1.5">
              {(lead.notes ?? []).map((n) => (
                <div key={n.id} className="flex items-start justify-between gap-2 rounded-md border border-border/60 bg-card p-2.5">
                  <div className="flex flex-col gap-0.5">
                    <p className="whitespace-pre-wrap text-xs text-foreground">{n.body}</p>
                    <span className="text-[10px] text-muted-foreground">
                      {new Date(n.created_at).toLocaleString("es-ES", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <button type="button" onClick={() => deleteNote(n.id)} className="text-muted-foreground hover:text-destructive" aria-label="Eliminar nota">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between gap-2 sm:justify-between">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-destructive hover:text-destructive"
            onClick={async () => {
              const ok = await removeLead(lead.id)
              if (ok) { toast({ title: "Lead eliminado del CRM" }); onClose() }
            }}
          >
            <Trash2 className="h-4 w-4" /> Quitar del CRM
          </Button>
          <Button variant="outline" size="sm" onClick={onClose}>Cerrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value?: string | null }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">{icon}</span>
      <span className="font-medium text-muted-foreground">{label}:</span>
      <span className="truncate text-foreground" title={value ?? ""}>{value || "—"}</span>
    </div>
  )
}
