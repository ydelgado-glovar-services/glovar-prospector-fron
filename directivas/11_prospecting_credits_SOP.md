# DIRECTIVA: PROSPECTING_CREDITS_SOP

> **ID:** SOP-CREDITS-011
> **Scripts asociados:** `app.py` (`_check_credit_balance`), `scripts/main.py` (registro del consumo real)
> **Migración:** `db/migrations/003_prospecting_credits.sql`
> **Estado:** ACTIVO (2026-08-25)

## 1. Objetivo

Control de costo del Modo Profundo (los únicos servicios de pago que consume: Tavily y Apify). No es un sistema de facturación multi-cliente — es **single-tenant**: toda la cuenta compartida de Élite Logística consume contra un único techo mensual. El objetivo explícito (decisión de negocio) es **contabilizar** el consumo real y dejar un límite claro, no construir UI de bloqueo sofisticada todavía.

## 2. Unidad de crédito

**1 crédito = 1 empresa procesada en Modo Profundo** (discovery compartido + 3 búsquedas de noticias + auditoría LLM + scraping Apify por empresa). Se eligió "empresa" y no "job" porque el costo real de Tavily/Apify escala con empresas procesadas, no con clics de botón — un job de 5 empresas y uno de 25 no deberían costar lo mismo en la contabilidad.

El Modo Rápido (`/api/v1/prospect/fast`) NO gasta Apify y usa Tavily de forma marginal (1 búsqueda por corrida) — no se contabiliza contra el mismo techo por ahora.

## 3. Mecanismo (dos partes)

1. **Gate previo (`app.py::_check_credit_balance`, antes de `POST /api/v1/prospect`):** compara `créditos usados este mes` (RPC `get_monthly_credits_used`) + `limite_perfiles` de la petición (peor caso) contra `monthly_credit_limit` (tabla `prospecting_credit_limits`, default 300). Si se excede, responde **HTTP 402** con un mensaje claro. Es una estimación de peor caso (usa el límite solicitado, no el número real de empresas que discovery vaya a encontrar).
2. **Registro real (`scripts/main.py`, justo después de `discover_companies` + filtro de exclusiones):** inserta una fila en `prospecting_credits_usage` con el número REAL de empresas que van a procesarse (`total_batch`), que normalmente es ≤ el estimado del gate. Esto es lo que queda para reportes/contabilidad exacta.

**Fail-open deliberado:** si la migración 003 no está aplicada o Supabase falla al verificar el saldo, `_check_credit_balance` deja pasar la petición (solo loggea) — un problema de contabilidad no debe tumbar la prospección real. Igual con el registro en `main.py`: si falla, solo se loggea una advertencia.

## 4. Límite recomendado (fundamento)

Con el stack actual (Tavily Project $30/mes = 4.000 créditos Tavily; Apify ~$29-30/mes de cómputo; Hunter free = 50 créditos/mes) y consumo real medido en producción el 2026-08-25 (~75 créditos Tavily / ~$0.12 Apify para 3 intentos de Modo Profundo, uno exitoso con 2 empresas auditadas): **`monthly_credit_limit` default = 300 empresas/mes**, con amplio margen dentro del cupo de Tavily y Apify. El verdadero cuello de botella para ENTREGAR valor (correo verificado) es Hunter, no Tavily/Apify — ver AGENTS.md §"Costos" para el detalle completo. Ajustar este número es una fila en `prospecting_credit_limits`, no un cambio de código.

## 4-bis. Revisión de seguridad del commit inicial (2026-08-25) — 3 hallazgos

Una revisión automática sobre el primer commit de este sistema encontró 3 problemas. Estado tras la corrección:

1. **TOCTOU race condition (corregido):** la versión inicial chequeaba saldo en `app.py` (SELECT) y registraba el consumo real mucho después en `scripts/main.py` (subproceso separado) — dos peticiones concurrentes de la cuenta compartida (4 usuarios de Élite lanzando Modo Profundo casi a la vez) podían leer el mismo saldo disponible y ambas pasar, superando el techo real. Fix: función Postgres `reserve_prospecting_credits` (§3-bis de la migración) hace check+reserva **atómicos** con `pg_advisory_xact_lock` por usuario — serializa a los concurrentes. `scripts/main.py` ya no inserta una fila nueva, hace `UPDATE` de la reserva (`_settle_credits_reservation`) con el conteo real, incluyendo en las salidas tempranas (0 empresas descubiertas/excluidas) para no dejar créditos reservados de más.
2. **Fail-open state drift (aceptado y documentado, no revertido):** si Supabase falla o la migración no está aplicada, `_reserve_credits` deja pasar la petición en vez de bloquear. Es una decisión consciente: el control de créditos es un límite de costo interno de bajo riesgo (unos pocos dólares de Tavily/Apify en el peor caso), no un límite de seguridad — bloquear la prospección real por un problema transitorio de contabilidad sería peor para el negocio (prioridad "que no se trabe", ver AGENTS.md). Se mejoró la visibilidad: el log ahora es `[Credits][ERROR]` explícito (antes un `print()` fácil de perder), buscable en `modal app logs`.
3. **Missing authorization (evaluado, no es un gap nuevo):** el gate usa `x_user_id` del header `X-User-Id`, que en TODA la app (no solo créditos) es confiable porque solo lo setea el proxy de Next.js después de validar la sesión de Supabase — protegido además por el `x-api-key` global (`verify_api_key`, `app.py`). Se verificó en vivo que ningún endpoint (incluido `/health` y `/api/v1/prospect`) responde sin `x-api-key` válido. Es el mismo patrón de "header confiable" que ya usan `jobs_status`/`leads` desde antes de este sistema — no una autorización nueva y más débil introducida por los créditos. Si el modelo deja de ser una sola cuenta compartida, este patrón sí necesitará revisarse a fondo.

## 5. Pendiente (fuera de alcance actual, por decisión explícita del negocio)

- UI de bloqueo en el frontend cuando se acerca al límite (hoy el usuario solo ve un 402 si lo alcanza).
- Alertas/notificación cuando el consumo mensual supera un % del techo.
- Registrar créditos también para Modo Rápido si su volumen crece lo suficiente para importar.
