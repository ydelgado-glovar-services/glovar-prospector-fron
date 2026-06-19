"use client"

/**
 * app/crm/page.tsx — Apartado "Mis Leads / CRM".
 *
 * Vista protegida (el middleware garantiza sesión) que muestra el pipeline
 * Kanban de leads calificados enviados desde los resultados de prospección.
 */

import { useEffect } from "react"
import { useRouter } from "next/navigation"

import { AppHeader } from "@/components/app-header"
import { CrmBoard } from "@/components/crm-board"
import { useAuth } from "@/components/auth-provider"

export default function CrmPage() {
  const { session, isLoading: authLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!authLoading && !session) router.push("/login")
  }, [authLoading, session, router])

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
      <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-4 py-6 md:px-6 md:py-8">
        <div className="mb-5">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">Mis Leads / CRM</h1>
          <p className="text-sm text-muted-foreground">
            Gestiona tu pipeline comercial: mueve leads entre etapas, asigna etiquetas y registra notas internas.
          </p>
        </div>
        <CrmBoard />
      </main>
    </div>
  )
}
