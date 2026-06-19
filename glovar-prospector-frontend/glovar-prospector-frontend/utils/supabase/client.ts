import { createBrowserClient } from '@supabase/ssr'

let client: ReturnType<typeof createBrowserClient> | null = null

export function createClient() {
  if (!client) {
    client = createBrowserClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
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
  }
  return client
}

/**
 * resetClient — Anula el singleton del cliente Supabase del browser.
 * Debe llamarse durante el signOut para garantizar que el siguiente login
 * instancie un cliente limpio sin ningún estado de sesión anterior en memoria.
 */
export function resetClient() {
  client = null
}
