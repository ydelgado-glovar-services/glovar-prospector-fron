"use client"

/**
 * app/admin/page.tsx — Admin Panel (role-gated).
 *
 * Checks if the current user has role === 'admin' from user_profiles.
 * If not, shows "Access Denied". If admin, fetches and displays the
 * user_profiles table in a clean data table.
 */

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Shield, ShieldAlert, Users, Loader2, ArrowLeft } from "lucide-react"

import { useAuth } from "@/components/auth-provider"
import { createClient } from "@/utils/supabase/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"

interface UserProfile {
  id: string
  email: string | null
  role: string
  created_at: string
}

export default function AdminPage() {
  const { user, role, isLoading: authLoading } = useAuth()
  const router = useRouter()
  const supabase = createClient()

  const [users, setUsers] = useState<UserProfile[]>([])
  const [isLoadingUsers, setIsLoadingUsers] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  // Fetch users from user_profiles table (admin only)
  useEffect(() => {
    if (authLoading || role !== "admin") return

    const fetchUsers = async () => {
      setIsLoadingUsers(true)
      setFetchError(null)

      try {
        const { data, error } = await supabase
          .from("user_profiles")
          .select("id, email, role, created_at")
          .order("created_at", { ascending: false })

        if (error) {
          setFetchError(error.message)
          return
        }

        setUsers(data ?? [])
      } catch (err) {
        setFetchError("Error al obtener usuarios.")
        console.error("[Admin]", err)
      } finally {
        setIsLoadingUsers(false)
      }
    }

    fetchUsers()
  }, [authLoading, role, supabase])

  // Auth loading state
  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">Verificando permisos...</span>
        </div>
      </div>
    )
  }

  // ── ACCESS DENIED — not admin ──
  if (role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4">
        <Card className="w-full max-w-md border-destructive/30 shadow-xl">
          <CardHeader className="items-center text-center">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10">
              <ShieldAlert className="h-7 w-7 text-destructive" />
            </div>
            <CardTitle className="text-xl font-bold">Acceso Denegado</CardTitle>
            <CardDescription className="text-sm">
              No tienes permisos de administrador para acceder a esta sección.
              <br />
              Contacta al administrador del sistema si crees que esto es un error.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center">
            <Button variant="outline" onClick={() => router.push("/dashboard")}>
              <ArrowLeft className="h-4 w-4" />
              Volver al Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // ── ADMIN VIEW ──
  return (
    <div className="flex min-h-screen flex-col bg-muted/30">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Shield className="h-4 w-4" />
            </div>
            <div className="flex flex-col leading-tight">
              <h1 className="text-base font-semibold tracking-tight">Admin Panel</h1>
              <span className="text-xs text-muted-foreground">
                Gestión de usuarios · {user?.email}
              </span>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => router.push("/dashboard")}>
            <ArrowLeft className="h-3 w-3" />
            Dashboard
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-6 md:px-6 md:py-8">
        <Card className="border-border/80 shadow-sm">
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <CardTitle className="text-lg font-semibold">Usuarios Registrados</CardTitle>
            </div>
            <CardDescription className="text-sm">
              Lista de todos los usuarios registrados en la plataforma.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoadingUsers ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">Cargando usuarios...</span>
              </div>
            ) : fetchError ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {fetchError}
              </div>
            ) : users.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Users className="mb-2 h-8 w-8" />
                <p className="text-sm">No hay usuarios registrados.</p>
              </div>
            ) : (
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[300px]">Email</TableHead>
                      <TableHead className="w-[120px]">Rol</TableHead>
                      <TableHead className="w-[200px]">Fecha de Registro</TableHead>
                      <TableHead className="w-[280px] font-mono text-xs">ID</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((profile) => (
                      <TableRow key={profile.id}>
                        <TableCell className="font-medium">
                          {profile.email ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={profile.role === "admin" ? "default" : "secondary"}
                            className="text-xs"
                          >
                            {profile.role}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {new Date(profile.created_at).toLocaleDateString("es-CO", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          })}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground/70">
                          {profile.id}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
