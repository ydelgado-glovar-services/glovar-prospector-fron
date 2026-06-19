"use client"

import { useState } from "react"
import { Sparkles, LogOut, Shield, Loader2, Search, KanbanSquare } from "lucide-react"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { SettingsDialog } from "@/components/settings-dialog"

export function AppHeader() {
  const { user, role, signOut } = useAuth()
  const pathname = usePathname()
  const [isSigningOut, setIsSigningOut] = useState(false)

  const handleSignOut = async () => {
    if (isSigningOut) return
    setIsSigningOut(true)
    try {
      await signOut()
    } finally {
      // Reset in case signOut fails or navigation is slow
      setIsSigningOut(false)
    }
  }

  const navItems = [
    { href: "/dashboard", label: "Prospección", icon: Search },
    { href: "/crm", label: "Mis Leads / CRM", icon: KanbanSquare },
  ]

  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="flex flex-col leading-tight">
              <h1 className="text-base font-semibold tracking-tight text-foreground">AI Lead Prospector</h1>
              <span className="text-xs text-muted-foreground">Prospección autónoma impulsada por IA</span>
            </div>
          </div>

          {/* Navegación principal */}
          <nav className="hidden items-center gap-1 md:flex">
            {navItems.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || (href === "/dashboard" && pathname === "/")
              return (
                <Link key={href} href={href}>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </span>
                </Link>
              )
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {/* Admin link (only visible to admins) */}
          {role === "admin" && (
            <Link href="/admin">
              <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                <Shield className="h-3 w-3" />
                Admin
              </Button>
            </Link>
          )}

          {/* User info & sign out */}
          <div className="hidden items-center gap-2 text-xs text-muted-foreground md:flex">
            <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true" />
            <span className="max-w-[180px] truncate">{user?.email ?? "Conectado"}</span>
          </div>

          <SettingsDialog />

          <Button
            variant="ghost"
            size="sm"
            onClick={handleSignOut}
            disabled={isSigningOut}
            className="gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            {isSigningOut ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <LogOut className="h-3 w-3" />
            )}
            <span className="hidden sm:inline">{isSigningOut ? "Saliendo..." : "Salir"}</span>
          </Button>
        </div>
      </div>
    </header>
  )
}
