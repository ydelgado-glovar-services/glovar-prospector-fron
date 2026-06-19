/**
 * lib/api.ts — Cliente HTTP ligero para hablar con el proxy de Next.js
 * (`app/api/v1/[...slug]/route.ts`), que a su vez reenvía al backend FastAPI
 * inyectando el `X-User-Id` derivado del JWT validado en el servidor.
 *
 * NOTA DE AUDITORÍA: Este archivo fue restaurado. La carpeta `lib/` estaba siendo
 * excluida del repositorio por la regla `lib/` de la plantilla `.gitignore` de Python.
 *
 * Diseño:
 *  - Las rutas son relativas (`/api/v1/...`) para resolverse contra el mismo origen,
 *    de modo que el proxy server-side valide la sesión y propague la identidad.
 *  - El token (JWT de Supabase) se envía como `Authorization: Bearer` para que el
 *    proxy lo reenvíe; el backend confía en `X-User-Id` que el proxy inyecta.
 *  - Devuelve el `Response` nativo para que el llamador controle `.ok`, `.status`,
 *    `.json()` y `.text()` sin acoplarse a un envoltorio propietario.
 */

export interface ApiFetchOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
  /** JWT de acceso de la sesión Supabase. */
  token?: string
  /** Cuerpo ya serializado (string) o un objeto que se serializará a JSON. */
  body?: BodyInit | Record<string, unknown> | null
  /** AbortSignal para cancelación / timeouts. */
  signal?: AbortSignal
  /** Cabeceras adicionales opcionales. */
  headers?: Record<string, string>
}

export async function apiFetch(
  path: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const { method = "GET", token, body, signal, headers: extraHeaders } = options

  const headers: Record<string, string> = {
    ...(extraHeaders ?? {}),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const requestInit: RequestInit = {
    method,
    headers,
    signal,
    // Mismo origen: garantiza que las cookies de sesión viajen al proxy.
    credentials: "same-origin",
    cache: "no-store",
  }

  if (body !== undefined && body !== null && method !== "GET") {
    if (typeof body === "string" || body instanceof FormData || body instanceof Blob) {
      requestInit.body = body as BodyInit
      if (typeof body === "string") {
        headers["Content-Type"] = "application/json"
      }
    } else {
      headers["Content-Type"] = "application/json"
      requestInit.body = JSON.stringify(body)
    }
  }

  return fetch(path, requestInit)
}
