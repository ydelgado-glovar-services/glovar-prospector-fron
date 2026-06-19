/**
 * middleware.ts — Next.js Edge Middleware (Route Guard).
 *
 * Runs on EVERY matched request BEFORE the page renders.
 * Delegates session refresh and route protection to supabase-middleware.ts.
 *
 * Protected routes: everything EXCEPT /login, static assets, and Next internals.
 */

import { type NextRequest } from "next/server"
import { updateSession } from "@/utils/supabase/middleware"

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico (browser icon)
     * - public folder assets (SVGs, images, etc.)
     * - /auth/ routes (Supabase callback must run before session validation)
     */
    "/((?!_next/static|_next/image|favicon.ico|auth/|api/|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
}
