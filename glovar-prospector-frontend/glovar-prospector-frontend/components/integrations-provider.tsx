"use client"

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react"
import { useAuth } from "@/components/auth-provider"
import { useToast } from "@/components/ui/use-toast"
import { apiFetch } from "@/lib/api"
import { usePathname } from "next/navigation"

interface IntegrationsContextValue {
  isConnected: boolean
  isLoading: boolean
  checkStatus: () => Promise<void>
  sendEmail: (params: { leadId: string; subject: string; body: string }) => Promise<boolean>
}

const IntegrationsContext = createContext<IntegrationsContextValue>({
  isConnected: false,
  isLoading: true,
  checkStatus: async () => { },
  sendEmail: async () => false,
})

export function useIntegrations() {
  const ctx = useContext(IntegrationsContext)
  if (!ctx) {
    throw new Error("useIntegrations debe usarse dentro de un <IntegrationsProvider>")
  }
  return ctx
}

export function IntegrationsProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const { toast } = useToast()
  const pathname = usePathname()
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false) // Lazy, non-blocking check starts as false

  const checkStatus = useCallback(async () => {
    if (pathname === "/login" || pathname === "/register") {
      setIsConnected(false)
      setIsLoading(false)
      return
    }

    if (!session?.access_token) {
      setIsConnected(false)
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)

    try {
      const res = await apiFetch("/api/v1/auth/google/status", {
        token: session.access_token,
        signal: controller.signal,
      } as any)
      
      clearTimeout(timeoutId)
      if (res.ok) {
        const data = await res.json()
        setIsConnected(data.is_connected || data.connected || false)
      } else {
        setIsConnected(false)
      }
    } catch (error: any) {
      clearTimeout(timeoutId)
      if (error.name === "AbortError") {
        console.warn("[Integrations] Connection check aborted due to 5s timeout ceiling.")
      } else {
        console.error("[Integrations] Error checking connection status:", error)
      }
      setIsConnected(false)
    } finally {
      setIsLoading(false)
    }
  }, [session?.access_token, pathname])

  useEffect(() => {
    checkStatus()
  }, [checkStatus])

  const sendEmail = useCallback(async ({ leadId, subject, body }: { leadId: string; subject: string; body: string }) => {
    if (!session?.access_token) {
      toast({
        title: "Sesión expirada",
        description: "Por favor, inicia sesión de nuevo.",
        variant: "destructive",
      })
      return false
    }

    if (!isConnected) {
      toast({
        title: "Gmail no conectado",
        description: "Debes conectar tu cuenta de Gmail en Configuración para enviar correos.",
        variant: "destructive",
      })
      return false
    }

    try {
      const res = await apiFetch("/api/v1/auth/google/send-email", {
        method: "POST",
        token: session.access_token,
        body: JSON.stringify({ lead_id: leadId, subject, body }),
      })

      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.detail || "Error al enviar el correo")
      }

      toast({
        title: "Correo enviado",
        description: `Se ha enviado el correo correctamente.`,
      })
      return true
    } catch (error: any) {
      console.error("[Integrations] Error sending email:", error)
      toast({
        title: "Error al enviar",
        description: error.message || "Hubo un problema al conectar con el servidor de Gmail.",
        variant: "destructive",
      })
      return false
    }
  }, [session, isConnected, toast])

  return (
    <IntegrationsContext.Provider value={{ isConnected, isLoading, checkStatus, sendEmail }}>
      {children}
    </IntegrationsContext.Provider>
  )
}
