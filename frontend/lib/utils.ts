import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * cn — Utilidad estándar (shadcn/ui) para componer clases de Tailwind.
 * Combina clsx (condicionales) con tailwind-merge (resolución de conflictos
 * de utilidades), garantizando que la última clase gane de forma determinista.
 *
 * NOTA DE AUDITORÍA: Este archivo vivía bajo `lib/`, que estaba siendo ignorado
 * por la plantilla `.gitignore` de Python (regla `lib/`). Se restauró y la regla
 * se ancló a la raíz (`/lib/`) para no volver a excluir el código del frontend.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
