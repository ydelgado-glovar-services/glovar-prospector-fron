# DIRECTIVE: LAZY_OAUTH_INTEGRATION_SOP

> **ID:** SOP-LAZY-OAUTH-2026
> **Status:** ACTIVE
> **Scope:** Architecture guidelines for frontend third-party integrations handling.

## 1. Core Constraint Rules
- **Rule 1 (Conversion Rate Protection):** Under no circumstances shall the application prevent a logged-in user from accessing the main prospecting dashboard due to unlinked third-party software credentials.
- **Rule 2 (State Isolation):** The global auth loader state variable `authLoading` must evaluate exclusively local database parameters (PostgreSQL profiles schemas). Third-party APIs integration response flags must be kept fully decoupled.

## 2. Dynamic Outreach Flow Implementation Contract
- When the user pushes the 'Review and Send' element for a qualified lead row:
  - The UI triggers `GET /api/v1/auth/google/status`.
  - IF `connected == true` or `is_connected == true`: Render text editor modal populated with the AI generated message copy.
  - IF `connected == false` or `is_connected == false`: Dynamically switch modal interface layout to render a secure authorization button pointing to the Google OAuth Grant URI gateway endpoint.
  - **[SUSPENSIÓN TEMPORAL DE PRODUCCIÓN - BYPASS DE GMAIL OAUTH]**: Las restricciones del flujo de envío de correos han sido suspendidas. El endpoint `/api/v1/auth/google/status` retorna de forma fija `{"connected": true, "is_connected": true}`. La interfaz de usuario ha sido rediseñada para omitir el botón de envío automático por Gmail, permitiendo al usuario visualizar el Asunto y el Cuerpo del correo directamente y copiarlos con un solo clic al portapapeles a través del modal "Ver Mensaje".


## 3. Resilient Non-blocking Operations Guard
- **Lazy Check Initialization**: The integrations loading state (`isLoading`) must initialize to `false` so it never blocks page mounts.
- **Abort Timeout Ceiling**: All check status fetches must enforce a strict `5000ms` timeout ceiling using an `AbortController` (to smoothly absorb database cold start connection spikes). If a timeout or network error occurs, fallback gracefully to `connected: false` without impeding page interactivity.
- **Dual-Key Reconciliation**: The backend must return both `connected` and `is_connected` keys in `/api/v1/auth/google/status`. The frontend must validate both properties to absorb formatting variations.
- **Google Identity SDK Initialization Guardrail**: Wrap the Google OAuth Provider setup in a dedicated React Error Boundary (`SafeGoogleOAuthBoundary`). If `process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID` is missing, undefined, or invalid on mount, write a silent warning to the console and present a safe fallback banner inside the dialog, bypassing SDK crashes completely.