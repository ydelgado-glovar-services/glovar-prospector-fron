/**
 * app/page.tsx — Root redirect.
 *
 * The prospecting tool now lives at /dashboard.
 * This page simply redirects there. The middleware will
 * intercept unauthenticated users and send them to /login.
 */

import { redirect } from "next/navigation"

export default function RootPage() {
  redirect("/dashboard")
}
