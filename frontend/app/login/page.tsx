"use client"

/**
 * app/login/page.tsx — Minimalist professional login page.
 *
 * Custom email/password form using Supabase Auth.
 * Supports both Sign In and Sign Up modes.
 * Redirects to /dashboard on successful authentication.
 */

import { useState, useEffect, useCallback, Suspense, type FormEvent } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Sparkles, Loader2, Mail, Lock, ArrowRight, UserPlus } from "lucide-react"
import { createClient } from "@/utils/supabase/client"
import { useAuth } from "@/components/auth-provider"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

type AuthMode = "signin" | "signup"

function LoginForm() {
  const { setIsLoading: setGlobalLoading } = useAuth()
  const [mode, setMode] = useState<AuthMode>("signin")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const router = useRouter()
  const searchParams = useSearchParams()
  const supabase = createClient()

  // Handle error params passed by the auth callback (e.g. expired session link)
  const urlError = searchParams.get("error")
  const urlErrorMessage = searchParams.get("message")
  const sessionErrorMessage =
    urlError === "session_expired"
      ? "Tu sesión ha expirado. Por favor inicia sesión nuevamente."
      : urlError === "missing_code"
      ? "El enlace de acceso es inválido o ya fue usado."
      : null

  useEffect(() => {
    setIsLoading(false)
    setGlobalLoading(false)
    // Pre-populate error from URL params (session expiry from callback)
    if (sessionErrorMessage) {
      setError(sessionErrorMessage)
    }

    // Guard silencioso: si el cliente tiene una sesión activa en memoria mientras la página
    // de login está abierta, redirige al dashboard sin emitir eventos globales de autenticación.
    // IMPORTANTE: NO llamar supabase.auth.signOut() aquí porque emite SIGNED_OUT globalmente,
    // lo que dispara router.refresh() en el AuthProvider → re-monta LoginForm → bucle infinito.
    const silentSessionCheck = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (session) {
          console.log("[Login] Active session detected on mount. Redirecting to /dashboard silently.")
          router.push("/dashboard")
        }
      } catch (err) {
        console.warn("[Login] Silent session check failed:", err)
      }
    }
    silentSessionCheck()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setGlobalLoading])

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setIsLoading(true)

    try {
      if (mode === "signin") {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        })

        if (signInError) {
          setError(signInError.message)
          return
        }

        router.push("/dashboard")
        router.refresh()
      } else {
        const { error: signUpError } = await supabase.auth.signUp({
          email,
          password,
        })

        if (signUpError) {
          setError(signUpError.message)
          return
        }

        setSuccess("¡Cuenta creada! Revisa tu correo para confirmar tu registro.")
      }
    } catch (err) {
      setError("Error inesperado. Intenta de nuevo.")
      console.error("[Login]", err)
    } finally {
      setIsLoading(false)
    }
  }

  const toggleMode = () => {
    setMode((prev) => (prev === "signin" ? "signup" : "signin"))
    setError(null)
    setSuccess(null)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4">
      {/* Background decoration */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-[500px] w-[500px] rounded-full bg-primary/5 blur-3xl" />
        <div className="absolute -bottom-40 -right-40 h-[400px] w-[400px] rounded-full bg-primary/3 blur-3xl" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Logo & Brand */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">
              AI Lead Prospector
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Prospección autónoma impulsada por IA
            </p>
          </div>
        </div>

        {/* Auth Card */}
        <Card className="border-border/60 shadow-xl shadow-black/5">
          <CardHeader className="space-y-1 pb-4">
            <CardTitle className="text-lg font-semibold">
              {mode === "signin" ? "Iniciar Sesión" : "Crear Cuenta"}
            </CardTitle>
            <CardDescription className="text-sm">
              {mode === "signin"
                ? "Ingresa tus credenciales para acceder a la plataforma."
                : "Registra una nueva cuenta para comenzar a prospectar."}
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              {/* Email */}
              <div className="flex flex-col gap-2">
                <Label
                  htmlFor="email"
                  className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
                >
                  Correo electrónico
                </Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="tu@empresa.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={isLoading}
                    required
                    className="pl-10"
                    autoComplete="email"
                  />
                </div>
              </div>

              {/* Password */}
              <div className="flex flex-col gap-2">
                <Label
                  htmlFor="password"
                  className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
                >
                  Contraseña
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={isLoading}
                    required
                    minLength={6}
                    className="pl-10"
                    autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  />
                </div>
              </div>

              {/* Error message */}
              {error && (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              {/* Success message */}
              {success && (
                <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400">
                  {success}
                </div>
              )}

              {/* Submit */}
              <Button
                type="submit"
                size="lg"
                className="mt-1 w-full font-medium"
                disabled={isLoading}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Procesando...</span>
                  </>
                ) : mode === "signin" ? (
                  <>
                    <ArrowRight className="h-4 w-4" />
                    <span>Ingresar</span>
                  </>
                ) : (
                  <>
                    <UserPlus className="h-4 w-4" />
                    <span>Crear Cuenta</span>
                  </>
                )}
              </Button>

              {/* Toggle mode */}
              <div className="text-center text-sm text-muted-foreground">
                {mode === "signin" ? (
                  <>
                    ¿No tienes cuenta?{" "}
                    <button
                      type="button"
                      onClick={toggleMode}
                      className="font-medium text-primary underline-offset-4 hover:underline"
                    >
                      Regístrate
                    </button>
                  </>
                ) : (
                  <>
                    ¿Ya tienes cuenta?{" "}
                    <button
                      type="button"
                      onClick={toggleMode}
                      className="font-medium text-primary underline-offset-4 hover:underline"
                    >
                      Inicia Sesión
                    </button>
                  </>
                )}
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-muted-foreground/60">
          Plataforma interna · Acceso restringido
        </p>
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-muted/30">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground font-medium font-mono">Cargando página de acceso...</span>
        </div>
      </div>
    }>
      <LoginForm />
    </Suspense>
  )
}
