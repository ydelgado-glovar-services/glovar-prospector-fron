# AGENT ONBOARDING BLUEPRINT: GLOVAR PROSPECTING CORE

> **ID:** BLUEPRINT-AI-001
> **Workspace:** Glovar Agency - B2B Whitelabel SaaS (Elite Logística context)
> **Estado:** ACTIVO

Este documento sirve para alinear instantáneamente a cualquier agente de Inteligencia Artificial que tome el control de este espacio de trabajo en el futuro. Léelo atentamente antes de modificar código o realizar planes.

---

## 1. Arquitectura de Producción y Despliegue

El sistema está completamente desacoplado en tres capas elásticas:
1. **Frontend (Vercel):** Aplicación Next.js 16. Usa un **Proxy Inverso Seguro** en `app/api/v1/[...slug]/route.ts` para redirigir peticiones al backend e inyectar cabeceras de identificación de forma encriptada en el servidor.
2. **Backend Serverless (Modal):** FastAPI ASGI corriendo en la nube asíncronamente bajo demanda. 
   - *Decorador crítico:* `@app.function(max_containers=10, timeout=900)`.
   - *Comando de despliegue:* `.venv\Scripts\modal deploy modal_app.py`.
3. **Persistencia (Cloud Supabase):** Base de datos PostgreSQL. **IMPORTANTE:** Requiere SQL `GRANT` explícitos para toda tabla del esquema público accedida por la API de Datos (PostgREST).

---

## 2. Mitigaciones de Seguridad STRIDE Activas

Bajo ninguna circunstancia debes debilitar las siguientes salvaguardas implementadas:

* **Spoofing Guard (API Keys):** Los endpoints en `app.py` están validados globalmente por la cabecera `x-api-key`. El proxy de Next.js lee la variable de entorno del servidor `GLOVAR_BACKEND_API_KEY` y la inyecta al redirigir llamadas. **Nunca expongas esta clave al navegador del cliente.**
* **Tampering Guard (DNS Guards):** `scripts/lead_scraper.py` implementa `socket.gethostbyname` pre-flight antes de disparar llamadas a las APIs externas pagas de Hunter o Apollo. Si el dominio corporativo del lead no tiene registros DNS activos, la petición se aborta de inmediato para evitar la fuga y el desperdicio de créditos.
* **Information Disclosure (RLS):** Las políticas de seguridad Row Level Security (RLS) en Supabase están enforzadas estrictamente a través de `user_id = auth.uid()`.

---

## 3. Pool de Groq Rotativo (MANDATORY EXCLUSIVE)
Debido al bloqueo de actualización del plan de pago en la plataforma de Groq en 2026, el sistema opera obligatoriamente a través de un pool rotativo Round-Robin de múltiples llaves gratuitas (`GROQ_API_KEY_1`...`9`).
- La función de rotación está programada de forma resiliente contra colisiones multihilo y jitter backoff en `main.py`, `lead_scraper.py` y `validator.py`.
- Si añades lógica que use LLM en otro script, **debes importar e invocar obligatoriamente `get_next_groq_key()`** en lugar de leer una única llave estática.

---

## 4. Flujo Obligatorio de Verificación de Salud
Antes de declarar cualquier tarea como completada o confirmar blueprints, debes ejecutar la siguiente secuencia de sanidad en la terminal para garantizar 100% de alineación sintáctica:

```bash
# 1. Validación de compilación del backend
.venv\Scripts\python.exe -m py_compile app.py scripts/main.py scripts/news_scraper.py scripts/lead_scraper.py scripts/validator.py

# 2. Validación de tipos del frontend
npx tsc --noEmit --prefix glovar-prospector-frontend/glovar-prospector-frontend
```
 Ambos deben compilar con **cero errores** antes de subir a producción.
