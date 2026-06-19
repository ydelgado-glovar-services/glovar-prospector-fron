import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({
            request,
          })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
      global: {
        fetch: (url, init) => {
          const controller = new AbortController()
          const timeoutId = setTimeout(() => controller.abort(), 8000)
          return fetch(url, {
            ...init,
            signal: controller.signal,
          }).finally(() => clearTimeout(timeoutId))
        },
      },
    }
  )

  // IMPORTANT: Avoid writing any logic between createServerClient and
  // supabase.auth.getUser(). A simple mistake could make it very hard to debug
  // issues with users being randomly logged out.

  const {
    data: { user },
  } = await supabase.auth.getUser()

  const pathname = request.nextUrl.pathname

  // Protected routes: root `/` redirects to dashboard, `/dashboard`, and `/admin`
  const isProtectedRoute =
    pathname === '/' ||
    pathname.startsWith('/dashboard') ||
    pathname.startsWith('/admin')

  // Auth routes: `/login`
  const isAuthRoute = pathname.startsWith('/login')

  if (!user && isProtectedRoute) {
    console.log(`[Middleware] Unauthenticated access to protected route: ${pathname}. Redirecting to /login.`)
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    
    const redirectResponse = NextResponse.redirect(url)
    
    // Propagate all cookies (including cleared/refreshed tokens) to the client on redirect
    supabaseResponse.cookies.getAll().forEach((cookie) => {
      redirectResponse.cookies.set(cookie.name, cookie.value, {
        domain: cookie.domain,
        path: cookie.path,
        maxAge: cookie.maxAge,
        secure: cookie.secure,
        sameSite: cookie.sameSite,
        expires: cookie.expires,
        httpOnly: cookie.httpOnly,
      })
    })
    
    return redirectResponse
  }

  if (user && isAuthRoute) {
    console.log(`[Middleware] Authenticated user on auth route: ${pathname}. Redirecting to /dashboard.`)
    const url = request.nextUrl.clone()
    url.pathname = '/dashboard'
    
    const redirectResponse = NextResponse.redirect(url)
    
    supabaseResponse.cookies.getAll().forEach((cookie) => {
      redirectResponse.cookies.set(cookie.name, cookie.value, {
        domain: cookie.domain,
        path: cookie.path,
        maxAge: cookie.maxAge,
        secure: cookie.secure,
        sameSite: cookie.sameSite,
        expires: cookie.expires,
        httpOnly: cookie.httpOnly,
      })
    })
    
    return redirectResponse
  }


  return supabaseResponse
}

