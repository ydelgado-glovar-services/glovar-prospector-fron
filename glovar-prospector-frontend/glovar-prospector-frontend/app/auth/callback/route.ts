/**
 * app/auth/callback/route.ts — Supabase Auth Callback Handler.
 *
 * Handles the redirect after email confirmation or OAuth login.
 * Supabase sends the user here with a `code` query parameter,
 * which we exchange for a session.
 */

import { NextResponse } from "next/server"
import { createClient } from "@/utils/supabase/server"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const next = searchParams.get("next") ?? "/dashboard"

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)

    if (!error) {
      return NextResponse.redirect(`${origin}${next}`)
    }

    // Code exchange failed (expired code, already used, etc.)
    // Redirect with context so the login page shows a helpful message
    console.error("[Auth Callback] Code exchange failed:", error.message)
    return NextResponse.redirect(
      `${origin}/login?error=session_expired&message=${encodeURIComponent(error.message)}`
    )
  }

  // No code present — likely a direct hit or malformed URL
  return NextResponse.redirect(`${origin}/login?error=missing_code`)
}
