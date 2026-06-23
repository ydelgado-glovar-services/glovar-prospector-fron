"use client"

import { FormEvent, useState } from "react"
import { Loader2, Play, AlertCircle, Zap, Search } from "lucide-react"

import { useToast } from "@/hooks/use-toast"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Textarea } from "@/components/ui/textarea"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"

import type { CompanySize, ProspectRequest } from "@/lib/types"

interface SearchFormProps {
  values: ProspectRequest
  isLoading: boolean
  isSessionReady?: boolean
  mode?: "fast" | "deep"
  onModeChange?: (mode: "fast" | "deep") => void
  onChange: (patch: Partial<ProspectRequest>) => void
  onSubmit: () => void
  onClear?: () => void
}

export function SearchForm({ values, isLoading, isSessionReady = true, mode = "deep", onModeChange, onChange, onSubmit, onClear }: SearchFormProps) {
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})
  // [Spec-Driven] Local raw string for exclusion list — parsed to string[] on submit
  const [exclusionInput, setExclusionInput] = useState<string>("")
  const { toast } = useToast()

  /** Cuenta términos separados por coma (ignora espacios vacíos). */
  const _countTerms = (value: string | undefined): number => {
    if (!value) return 0
    return value.split(",").filter((t) => t.trim()).length
  }

  const MAX_CSV_TERMS = 3
  const CSV_WARNING = "Máximo 3 términos recomendados para evitar errores de búsqueda"

  const handleFieldChange = (patch: Partial<ProspectRequest>) => {
    onChange(patch)
    const key = Object.keys(patch)[0]
    if (key && formErrors[key]) {
      setFormErrors((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    // ── MODO RÁPIDO: validación ligera (basta una frase o un cargo) ──
    if (mode === "fast") {
      if (!isSessionReady) {
        toast({
          variant: "destructive",
          title: "Sesión no válida",
          description: "La sesión aún no se ha cargado. Espera un momento o vuelve a iniciar sesión.",
        })
        return
      }
      if (!values.prompt?.trim() && !values.cargo_decision?.trim()) {
        setFormErrors({ prompt: "Describe tu cliente ideal o indica al menos un cargo objetivo." })
        return
      }
      setFormErrors({})
      onSubmit()
      return
    }

    // [Spec-Driven] Parse the raw comma-separated string into a clean string[] before submission.
    // Filter out empty tokens from double-commas or trailing commas.
    const parsedExclusionList: string[] = exclusionInput
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)

    // Inject the parsed array into the form values so page.tsx serializes it correctly.
    onChange({ exclusion_list: parsedExclusionList })
    
    try {
      if (!isSessionReady) {
        console.error("[Frontend] handleSubmit triggered without a valid session.")
        toast({
          variant: "destructive",
          title: "Sesión no válida",
          description: "La sesión aún no se ha cargado. Por favor, espera un momento o vuelve a iniciar sesión.",
        })
        return
      }

      const newErrors: Record<string, string> = {}
      
      if (!values.mi_empresa?.trim()) newErrors.mi_empresa = "Campo obligatorio"
      if (!values.sector?.trim()) newErrors.sector = "Campo obligatorio"
      if (!values.pais?.trim()) newErrors.pais = "Campo obligatorio"
      if (!values.tamano_empresa?.trim()) newErrors.tamano_empresa = "Campo obligatorio"
      if (!values.cargo_decision?.trim()) newErrors.cargo_decision = "Campo obligatorio"
      if (!values.dolor_cliente?.trim()) newErrors.dolor_cliente = "Campo obligatorio"
      if (!values.propuesta_valor?.trim()) newErrors.propuesta_valor = "Campo obligatorio"

      // ── Guardrail: máx 3 términos separados por coma en Cargo y Sector ──
      const cargoCount = _countTerms(values.cargo_decision)
      const sectorCount = _countTerms(values.sector)

      if (cargoCount > MAX_CSV_TERMS) {
        newErrors.cargo_decision = CSV_WARNING
      }
      if (sectorCount > MAX_CSV_TERMS) {
        newErrors.sector = CSV_WARNING
      }

      if (Object.keys(newErrors).length > 0) {
        setFormErrors(newErrors)

        // ── Scroll to the first invalid field (safe, non-blocking) ──
        const firstErrorKey = Object.keys(newErrors)[0]
        setTimeout(() => {
          try {
            const errorElement = document.getElementById(firstErrorKey)
            if (errorElement) {
              errorElement?.scrollIntoView?.({ behavior: "smooth", block: "center" })
              errorElement?.focus?.({ preventScroll: true })
            }
          } catch {
            // Silently ignore if the DOM element is not found
          }
        }, 50)

        return
      }
      
      setFormErrors({})
      onSubmit()
    } catch (err) {
      console.error("[Frontend] Error crítico en la validación del formulario:", err)
    }
  }

  return (
    <Card className="h-full border-border/80 shadow-sm">
      <CardHeader className="space-y-3 pb-4">
        <div className="space-y-1">
          <CardTitle className="text-lg font-semibold">Criterios de búsqueda</CardTitle>
          <CardDescription className="text-sm">
            Describe tu cliente ideal. La IA orquesta la búsqueda y el enriquecimiento.
          </CardDescription>
        </div>
        {/* Toggle de modo de prospección */}
        <div className="grid grid-cols-2 gap-1.5 rounded-lg border border-border/70 bg-muted/40 p-1">
          <button
            type="button"
            onClick={() => onModeChange?.("fast")}
            disabled={isLoading}
            className={`flex flex-col items-start gap-0.5 rounded-md px-3 py-2 text-left transition-colors ${
              mode === "fast" ? "bg-card shadow-sm ring-1 ring-primary/30" : "hover:bg-card/60"
            }`}
          >
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              <Zap className={`h-3.5 w-3.5 ${mode === "fast" ? "text-primary" : "text-muted-foreground"}`} /> Rápido
            </span>
            <span className="text-[10px] leading-tight text-muted-foreground">Lista de contactos en segundos</span>
          </button>
          <button
            type="button"
            onClick={() => onModeChange?.("deep")}
            disabled={isLoading}
            className={`flex flex-col items-start gap-0.5 rounded-md px-3 py-2 text-left transition-colors ${
              mode === "deep" ? "bg-card shadow-sm ring-1 ring-primary/30" : "hover:bg-card/60"
            }`}
          >
            <span className="flex items-center gap-1.5 text-sm font-semibold">
              <Search className={`h-3.5 w-3.5 ${mode === "deep" ? "text-primary" : "text-muted-foreground"}`} /> Profundo
            </span>
            <span className="text-[10px] leading-tight text-muted-foreground">Con señales/noticias (~5 min)</span>
          </button>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          {/* Input en lenguaje natural (UX simplificada estilo Enginy) */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="prompt" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Describe tu cliente ideal {mode === "fast" ? "" : "(opcional)"}
            </Label>
            <Textarea
              id="prompt"
              name="prompt"
              placeholder={mode === "fast"
                ? "Ej: Directores de Recursos Humanos en empresas de software de 200+ empleados en Colombia"
                : "Ej: Bancos en Colombia que estén lanzando banca digital y necesiten modernizar su core"}
              value={values.prompt || ""}
              onChange={(event) => handleFieldChange({ prompt: event.target.value })}
              disabled={isLoading}
              rows={2}
              className={formErrors.prompt ? "border-red-500 focus-visible:ring-red-500" : ""}
            />
            {formErrors.prompt ? (
              <span className="text-xs text-red-500 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" /> {formErrors.prompt}
              </span>
            ) : (
              <span className="text-[10px] text-muted-foreground">
                {mode === "fast"
                  ? "Modo Rápido: solo necesitas esto (o un cargo). Los campos de abajo son opcionales para afinar."
                  : "Opcional: si la escribes, autocompleta los campos. El Modo Profundo requiere los campos marcados."}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            {mode === "deep" && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="mi_empresa" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Mi Empresa (Remitente)
              </Label>
              <Input
                id="mi_empresa"
                name="mi_empresa"
                placeholder="Ej: Glovar Services"
                value={values.mi_empresa || ""}
                onChange={(event) => handleFieldChange({ mi_empresa: event.target.value })}
                disabled={isLoading}
                className={formErrors.mi_empresa ? "border-red-500 focus-visible:ring-red-500" : ""}
              />
              {formErrors.mi_empresa && (
                <span className="text-xs text-red-500 flex items-center gap-1 mt-1">
                  <AlertCircle className="w-3 h-3" /> {formErrors.mi_empresa}
                </span>
              )}
            </div>
            )}

            <div className="flex flex-col gap-2">
              <Label htmlFor="sector" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Sector Objetivo
              </Label>
              <Input
                id="sector"
                name="sector"
                placeholder="Ej: Salud, Finanzas, Tecnología"
                value={values.sector}
                onChange={(event) => handleFieldChange({ sector: event.target.value })}
                disabled={isLoading}
                className={formErrors.sector ? "border-red-500 focus-visible:ring-red-500" : ""}
              />
              {formErrors.sector && (
                <span className={`text-xs flex items-center gap-1 mt-1 ${
                  formErrors.sector === CSV_WARNING ? "text-amber-500" : "text-red-500"
                }`}>
                  <AlertCircle className="w-3 h-3" /> {formErrors.sector}
                </span>
              )}
              {!formErrors.sector && _countTerms(values.sector) > 0 && (
                <span className="text-[10px] text-muted-foreground mt-0.5">
                  {_countTerms(values.sector)}/{MAX_CSV_TERMS} términos
                </span>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="pais" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                País
              </Label>
              <Input
                id="pais"
                name="pais"
                placeholder="Ej: Estados Unidos"
                value={values.pais}
                onChange={(event) => handleFieldChange({ pais: event.target.value })}
                disabled={isLoading}
                className={formErrors.pais ? "border-red-500 focus-visible:ring-red-500" : ""}
              />
              {formErrors.pais && (
                <span className="text-xs text-red-500 flex items-center gap-1 mt-1">
                  <AlertCircle className="w-3 h-3" /> {formErrors.pais}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="mercado_objetivo" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Mercado objetivo / expansión (opcional)
              </Label>
              <Input
                id="mercado_objetivo"
                name="mercado_objetivo"
                placeholder="Ej: Colombia"
                value={values.mercado_objetivo || ""}
                onChange={(event) => handleFieldChange({ mercado_objetivo: event.target.value })}
                disabled={isLoading}
              />
              <span className="text-[10px] text-muted-foreground mt-0.5">
                Úsalo para buscar empresas con sede en el <strong>País</strong> que se expanden u operan en este mercado (ej. País: Estados Unidos → Mercado: Colombia).
              </span>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="tamano_empresa" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Tamaño de empresa
              </Label>
              <Select
                name="tamano_empresa"
                value={values.tamano_empresa || undefined}
                onValueChange={(value) => handleFieldChange({ tamano_empresa: value as CompanySize })}
                disabled={isLoading}
              >
                <SelectTrigger 
                  id="tamano_empresa" 
                  className={`w-full ${formErrors.tamano_empresa ? "border-red-500 focus:ring-red-500" : ""}`}
                >
                  <SelectValue placeholder="Selecciona un rango" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1-50">1-50 empleados</SelectItem>
                  <SelectItem value="51-200">51-200 empleados</SelectItem>
                  <SelectItem value="201-500">201-500 empleados</SelectItem>
                  <SelectItem value="500+">500+ empleados</SelectItem>
                </SelectContent>
              </Select>
              {formErrors.tamano_empresa && (
                <span className="text-xs text-red-500 flex items-center gap-1 mt-1">
                  <AlertCircle className="w-3 h-3" /> {formErrors.tamano_empresa}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="cargo_decision" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Cargo del tomador de decisión
              </Label>
              <Input
                id="cargo_decision"
                name="cargo_decision"
                placeholder="Ej: CEO, CTO, VP Ventas"
                value={values.cargo_decision}
                onChange={(event) => handleFieldChange({ cargo_decision: event.target.value })}
                disabled={isLoading}
                className={formErrors.cargo_decision ? "border-red-500 focus-visible:ring-red-500" : ""}
              />
              {formErrors.cargo_decision && (
                <span className={`text-xs flex items-center gap-1 mt-1 ${
                  formErrors.cargo_decision === CSV_WARNING ? "text-amber-500" : "text-red-500"
                }`}>
                  <AlertCircle className="w-3 h-3" /> {formErrors.cargo_decision}
                </span>
              )}
              {!formErrors.cargo_decision && _countTerms(values.cargo_decision) > 0 && (
                <span className="text-[10px] text-muted-foreground mt-0.5">
                  {_countTerms(values.cargo_decision)}/{MAX_CSV_TERMS} términos
                </span>
              )}
            </div>
          </div>

          {mode === "deep" && (
          <>
          <div className="flex flex-col gap-2">
            <Label htmlFor="dolor_cliente" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Dolor del cliente a resolver
            </Label>
            <Textarea
              id="dolor_cliente"
              name="dolor_cliente"
              placeholder="Ej: Empresas extranjeras pierden cadena de frío al entrar a Colombia sin un partner especializado."
              value={values.dolor_cliente}
              onChange={(event) => handleFieldChange({ dolor_cliente: event.target.value })}
              disabled={isLoading}
              rows={4}
              className={formErrors.dolor_cliente ? "border-red-500 focus-visible:ring-red-500" : ""}
            />
            {formErrors.dolor_cliente && (
              <span className="text-xs text-red-500 flex items-center gap-1 mt-1">
                <AlertCircle className="w-3 h-3" /> {formErrors.dolor_cliente}
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="propuesta_valor" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Propuesta de valor / Resultado
            </Label>
            <Textarea
              id="propuesta_valor"
              name="propuesta_valor"
              placeholder="Ej: Operador 3PL exclusivo en salud con certificaciones INVIMA y entregas < 24h."
              value={values.propuesta_valor}
              onChange={(event) => handleFieldChange({ propuesta_valor: event.target.value })}
              disabled={isLoading}
              rows={4}
              className={formErrors.propuesta_valor ? "border-red-500 focus-visible:ring-red-500" : ""}
            />
            {formErrors.propuesta_valor && (
              <span className="text-xs text-red-500 flex items-center gap-1 mt-1">
                <AlertCircle className="w-3 h-3" /> {formErrors.propuesta_valor}
              </span>
            )}
          </div>
          </>
          )}

          {mode === "deep" && (
          <Accordion type="single" collapsible className="w-full border rounded-md px-4 py-1 bg-card">
            <AccordionItem value="opciones-comerciales" className="border-none">
              <AccordionTrigger className="text-sm font-semibold hover:no-underline py-3">
                Opciones Comerciales Avanzadas (Opcional)
              </AccordionTrigger>
              <AccordionContent className="flex flex-col gap-5 pt-1 pb-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="triggers_compra" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Triggers de Compra
                  </Label>
                  <Textarea
                    id="triggers_compra"
                    name="triggers_compra"
                    placeholder="Ej: Expansión a Colombia"
                    value={values.triggers_compra || ""}
                    onChange={(event) => handleFieldChange({ triggers_compra: event.target.value })}
                    disabled={isLoading}
                    rows={2}
                    maxLength={150}
                  />
                  <span className="text-[10px] text-muted-foreground mt-0.5">
                    Breve. Se usará para buscar noticias. (Máx. 150 caracteres — {(values.triggers_compra || "").length}/150)
                  </span>
                </div>
                
                <div className="flex flex-col gap-2">
                  <Label htmlFor="casos_exito" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Casos de Éxito / Diferenciadores
                  </Label>
                  <Textarea
                    id="casos_exito"
                    name="casos_exito"
                    placeholder="Ej: reducción de tiempo 60%, entregables en 2 semanas"
                    value={values.casos_exito || ""}
                    onChange={(event) => handleFieldChange({ casos_exito: event.target.value })}
                    disabled={isLoading}
                    rows={2}
                  />
                </div>
                
                <div className="flex flex-col gap-2">
                  <Label htmlFor="keywords_industria" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Keywords de Industria
                  </Label>
                  <Textarea
                    id="keywords_industria"
                    name="keywords_industria"
                    placeholder="Ej: cold chain excursion, INVIMA compliance..."
                    value={values.keywords_industria || ""}
                    onChange={(event) => handleFieldChange({ keywords_industria: event.target.value })}
                    disabled={isLoading}
                    rows={2}
                  />
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="exclusion_list" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Empresas a excluir (Lista Negra)
                  </Label>
                  <Textarea
                    id="exclusion_list"
                    name="exclusion_list"
                    placeholder="Ej: Epiliquid, Retail N1, Competidor ABC"
                    value={exclusionInput}
                    onChange={(event) => setExclusionInput(event.target.value)}
                    disabled={isLoading}
                    rows={2}
                  />
                  <span className="text-[10px] text-muted-foreground mt-0.5">
                    Ingresa los nombres de empresas que no deseas prospectar, separados por comas.
                  </span>
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="limite_perfiles" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Límite de perfiles a analizar
              </Label>
              <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-0.5 text-sm font-bold font-mono text-primary">
                {values.limite_perfiles ?? 25}
              </span>
            </div>
            <Slider
              id="limite_perfiles"
              name="limite_perfiles"
              min={5}
              max={25}
              step={1}
              value={[values.limite_perfiles ?? 25]}
              onValueChange={(val) => handleFieldChange({ limite_perfiles: val[0] })}
              disabled={isLoading}
              className="w-full"
            />
            <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
              <span>5</span>
              <span>25</span>
            </div>
          </div>

          {mode === "deep" && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="max_news_articles" className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Velocidad de Prospección
            </Label>
            <Select
              name="max_news_articles"
              value={String(values.max_news_articles ?? 3)}
              onValueChange={(val) => handleFieldChange({ max_news_articles: Number(val) })}
              disabled={isLoading}
            >
              <SelectTrigger 
                id="max_news_articles"
                className="w-full border-border/80 shadow-sm"
              >
                <SelectValue placeholder="Selecciona la velocidad" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">⚡ Rápido (1 art. / empresa · ~3 min)</SelectItem>
                <SelectItem value="3">🚀 Estándar (3 art. / empresa · ~6 min)</SelectItem>
                <SelectItem value="5">🔍 Profundo (5 art. / empresa · ~10 min)</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-[10px] text-muted-foreground mt-0.5">
              Controla cuántas noticias y publicaciones de LinkedIn extrae el sistema por empresa para optimizar tiempos.
            </span>
          </div>
          )}

          <div className="mt-2 flex flex-col gap-2">
            <Button
              type="submit"
              size="lg"
              className="w-full font-medium"
              disabled={isLoading || !isSessionReady}
              aria-busy={isLoading}
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  <span>{mode === "fast" ? "Buscando contactos..." : "Ejecutando prospección..."}</span>
                </>
              ) : mode === "fast" ? (
                <>
                  <Zap className="h-4 w-4" aria-hidden="true" />
                  <span>Buscar contactos (Rápido)</span>
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" aria-hidden="true" />
                  <span>Ejecutar Prospección Autónoma</span>
                </>
              )}
            </Button>
            {onClear && (
              <Button
                type="button"
                variant="outline"
                size="lg"
                className="w-full font-medium text-muted-foreground hover:text-foreground"
                onClick={onClear}
                disabled={isLoading}
              >
                Limpiar Búsqueda
              </Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
