"use client"

import { useState, useEffect, Component, type ReactNode } from "react"
import { Settings, Mail, CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { GoogleOAuthProvider, useGoogleLogin } from "@react-oauth/google"
import { useAuth } from "@/components/auth-provider"
import { useIntegrations } from "@/components/integrations-provider"
import { useToast } from "@/components/ui/use-toast"
import { apiFetch } from "@/lib/api"

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ""

if (!GOOGLE_CLIENT_ID) {
  console.warn("[Google Identity] process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID is missing or undefined. Skipping initialization silently.");
}

// Error Boundary to gracefully absorb Google Identity Services initialization exceptions
class SafeGoogleOAuthBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError(error: any) {
    return { hasError: true }
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error("[Google Identity Boundary] Caught initialization exception:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-lg border p-4 text-center text-sm text-amber-600 bg-amber-50 dark:bg-amber-950/20">
          Servicio de autenticación de Google no disponible temporalmente.
        </div>
      )
    }
    return this.props.children
  }
}

function GmailConnectButton() {
  const { session } = useAuth()
  const { isConnected, checkStatus } = useIntegrations()
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)

  const login = useGoogleLogin({
    flow: 'auth-code',
    scope: 'https://www.googleapis.com/auth/gmail.send',
    onSuccess: async (codeResponse) => {
      try {
        setIsLoading(true)
        const res = await apiFetch("/api/v1/auth/google/callback", {
          method: "POST",
          token: session?.access_token,
          body: JSON.stringify({ code: codeResponse.code }),
        })

        if (!res.ok) {
          throw new Error("Error al conectar con Gmail")
        }

        await checkStatus()
        toast({
          title: "Gmail conectado",
          description: "La integración se ha configurado correctamente.",
        })
      } catch (error) {
        console.error(error)
        toast({
          title: "Error",
          description: "No se pudo conectar la cuenta de Gmail.",
          variant: "destructive",
        })
      } finally {
        setIsLoading(false)
      }
    },
    onError: errorResponse => {
      console.error(errorResponse)
      toast({
        title: "Error de autenticación",
        description: "Se canceló o falló el inicio de sesión con Google.",
        variant: "destructive",
      })
    },
  })

  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-900/20">
          <Mail className="h-5 w-5" />
        </div>
        <div>
          <h4 className="text-sm font-medium">Integración con Gmail</h4>
          <p className="text-xs text-muted-foreground">
            Permite a la IA enviar correos en tu nombre
          </p>
        </div>
      </div>
      {isConnected ? (
        <div className="flex items-center gap-2 text-sm text-emerald-600 font-medium">
          <CheckCircle2 className="h-4 w-4" />
          Conectado
        </div>
      ) : (
        <Button
          variant="outline"
          onClick={() => login()}
          disabled={isLoading}
        >
          {isLoading ? "Conectando..." : "Conectar Gmail"}
        </Button>
      )}
    </div>
  )
}

export function SettingsDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground">
          <Settings className="h-4 w-4" />
          <span className="sr-only">Configuración</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Configuración</DialogTitle>
          <DialogDescription>
            Gestiona tus integraciones y preferencias de la cuenta.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {GOOGLE_CLIENT_ID ? (
            <SafeGoogleOAuthBoundary>
              <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
                <GmailConnectButton />
              </GoogleOAuthProvider>
            </SafeGoogleOAuthBoundary>
          ) : (
            <div className="rounded-lg border p-4 text-center text-sm text-amber-600 bg-amber-50 dark:bg-amber-950/20">
              Servicio de autenticación de Google no configurado (client_id no disponible).
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
