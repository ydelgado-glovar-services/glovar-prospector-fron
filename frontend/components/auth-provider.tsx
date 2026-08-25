"use client"

/**
 * components/auth-provider.tsx — Proveedor de Contexto de Autenticación.
 *
 * Envuelve la aplicación para proveer:
 *   - Estado actual de la sesión y usuario
 *   - Rol del usuario (desde la tabla user_profiles, con degradación a 'client')
 *   - Estado de carga (isLoading) para evitar bloqueos en la hidratación
 *   - Función signOut para cerrar sesión
 *
 * Escucha los cambios de estado de autenticación de Supabase (login, logout, refresco)
 * y mantiene el árbol de React sincronizado de forma resiliente.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react"
import { useRouter } from "next/navigation"
import { createClient, resetClient } from "@/utils/supabase/client"
import type { Session, User, AuthChangeEvent } from "@supabase/supabase-js"

// ── Tipos ──
interface AuthContextValue {
  session: Session | null
  user: User | null
  role: string | null
  isLoading: boolean
  setIsLoading: (isLoading: boolean) => void
  signOut: () => Promise<void>
}

// ── Contexto ──
const AuthContext = createContext<AuthContextValue>({
  session: null,
  user: null,
  role: null,
  isLoading: true,
  setIsLoading: () => { },
  signOut: async () => { },
})

// ── Hook personalizado ──
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth debe usarse dentro de un <AuthProvider>")
  }
  return ctx
}

// ── Proveedor ──
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()
  // Track previous session key to prevent infinite refresh loops on initial mount/no-change
  const prevSessionKey = useRef<string | null>(null)

  // createBrowserClient is naturally a singleton on the client
  const supabase = createClient()

  // Obtener el rol del usuario desde la tabla user_profiles
  const fetchRole = useCallback(
    async (userId: string) => {
      try {
        const { data, error } = await supabase
          .from("user_profiles")
          .select("role")
          .eq("id", userId)
          .single()

        if (error) {
          console.warn("[Auth] No se pudo obtener el rol del usuario, asignando 'client':", error.message)
          setRole("client")
          return
        }

        setRole(data?.role ?? "client")
      } catch (err) {
        console.error("[Auth] Excepción al obtener el rol, asignando 'client':", err)
        setRole("client")
      }
    },
    [supabase]
  )

  useEffect(() => {
    // Bug Fix 1: `initialized` ref ensures the safety timeout only fires on first mount.
    // Without this, every time the tab resumes from sleep, Supabase emits TOKEN_REFRESHED
    // which triggers router.refresh() → remounts the provider → resets the timeout → loop.
    const initialized = { current: false }

    // Safety timeout: if session init hangs >6s on first load (cold start, offline, etc.),
    // force-resolve to unauthenticated to unblock the UI.
    const authTimeout = setTimeout(() => {
      if (!initialized.current) {
        console.warn("[Auth] Initialization timed out (6s). Resolving state to unauthenticated.")
        setIsLoading(false)
        setSession(null)
        setUser(null)
        setRole(null)
      }
    }, 6000)

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event: AuthChangeEvent, currentSession: Session | null) => {
      // Mark as initialized so the safety timeout no longer has any effect
      initialized.current = true
      clearTimeout(authTimeout)

      setSession(currentSession)
      setUser(currentSession?.user ?? null)

      if (currentSession?.user) {
        await fetchRole(currentSession.user.id)
      } else {
        setRole(null)
      }

      setIsLoading(false)

      // Calculate current session key
      const sessionKey = currentSession ? currentSession.access_token : "null"
      const isInitial = prevSessionKey.current === null
      const hasChanged = prevSessionKey.current !== sessionKey

      // Update the reference with the new session key
      prevSessionKey.current = sessionKey

      // Refresh Next.js router cache ONLY on real auth transitions (login / logout / profile update).
      // TOKEN_REFRESHED is a background auto-refresh and must NOT trigger router.refresh()
      // because it causes unnecessary Server Component re-renders and can interfere with
      // in-progress auth state transitions (e.g. the post-logout redirect to /login).
      if (
        !isInitial &&
        hasChanged &&
        (event === "SIGNED_IN" ||
          event === "SIGNED_OUT" ||
          event === "USER_UPDATED")
      ) {
        console.log(`[Auth] Auth transition detected (${event}). Triggering router.refresh() to update cache.`)
        router.refresh()
      }
    })

    return () => {
      clearTimeout(authTimeout)
      subscription.unsubscribe()
    }
  }, [supabase, fetchRole, router])

  const signOut = useCallback(async () => {
    try {
      setIsLoading(true)
      console.log("[Auth] Initiating resilient signOut. Purging Supabase cookies and local state...")

      // 1. Crear un timeout para no quedarse esperando a la red indefinidamente si Supabase.auth.signOut() se cuelga
      const signOutPromise = supabase.auth.signOut()
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Supabase signOut network timeout")), 2000)
      )

      // Intentamos cerrar sesión en la red, pero si tarda más de 2 segundos, continuamos con la limpieza manual
      try {
        await Promise.race([signOutPromise, timeoutPromise])
      } catch (timeoutErr) {
        console.warn("[Auth] Network signOut timed out or failed. Proceeding with manual client-side purge.")
      }

      // 2. Resetear el singleton del cliente Supabase para que el próximo login
      // instancie un cliente limpio sin estado de sesión anterior en memoria.
      resetClient()

      // 3. Limpieza manual y agresiva de cookies locales (por si acaso el SDK falló en borrarlas)
      if (typeof window !== "undefined") {
        // Borrar localStorage y sessionStorage de Supabase
        localStorage.clear()
        sessionStorage.clear()

        // Borrar todas las cookies del documento
        const cookies = document.cookie.split("; ")
        for (const cookie of cookies) {
          const eqPos = cookie.indexOf("=")
          const name = eqPos > -1 ? cookie.substring(0, eqPos) : cookie
          // Si es una cookie de supabase (sb-) o de sesión, la borramos forzando expiración en el pasado
          if (name.startsWith("sb-") || name.includes("auth-token")) {
            document.cookie = `${name}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;`
            document.cookie = `${name}=; Path=/; Domain=${window.location.hostname}; Expires=Thu, 01 Jan 1970 00:00:01 GMT;`
          }
        }
      }

      // 4. Limpiar estado de React inmediatamente
      setSession(null)
      setUser(null)
      setRole(null)

      // 5. Forzar el refresco de Next.js y redirigir
      router.refresh()
      router.push("/login")
    } catch (err) {
      console.error("[Auth] Exception during resilient signOut:", err)
      // Recuperación catastrófica segura
      resetClient()
      setSession(null)
      setUser(null)
      setRole(null)
      router.refresh()
      router.push("/login")
    } finally {
      setIsLoading(false)
    }
  }, [supabase, router])

  return (
    <AuthContext.Provider value={{ session, user, role, isLoading, setIsLoading, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
