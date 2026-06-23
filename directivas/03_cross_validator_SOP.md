# DIRECTIVA: TRIGGER_CROSS_VALIDATOR_SOP

> **ID:** SOP-VALIDATOR-003
> **Última Actualización:** 2026-05-29
> **Estado:** ACTIVO

## 1. Objetivos y Alcance
- **Objetivo Principal:** Evaluar de forma determinista y altamente parametrizada si las empresas descubiertas cumplen los criterios ingresados en el formulario web por el usuario y persistir los leads calificados/descalificados de forma directa en Supabase, utilizando una arquitectura de **Auditoría en 2 Fases** y un sistema de **3 Estados de Calificación**.
- **Enfoque Factual RAG:** Reutilizar de manera inteligente el contexto de texto plano extraído y guardado previamente por `news_scraper.py` en `.tmp/news_{company_name}.json` para la validación factual RAG, eliminando por completo llamadas de búsqueda redundantes a Tavily Search API para un ahorro neto de 100% en esta fase.
- **Integración de Intención Cognitiva (Fase 0):** El validador lee la clave `"extracted_intent"` del runtime context enriquecido en `.tmp/active_runtime_context.json`. El `rigorous_pain_framework` y `b2b_buying_trigger_context` se inyectan directamente en los prompts del LLM para que la auditoría corporativa (Fase 1) y la redacción de emails (Fase 2) estén alineadas con el dolor operativo profundo del prospecto en lugar de una evaluación genérica.
- **Meta de Precisión:** Minimizar alucinaciones y falsos positivos para alcanzar un nivel de precisión de respuesta del **93.3%** mediante prompts altamente contextualizados en el framework Groq utilizando el modelo **Llama 4 Scout** (`meta-llama/llama-4-scout-17b-16e-instruct`).

## 2. Sistema de 3 Estados de Calificación

La calificación de leads opera bajo un modelo de tres estados, implementado de forma 100% retrocompatible sin necesidad de nuevas columnas en Supabase:

| Estado Conceptual | `es_calificado` | `nombre_lead` | Frontend | Acción |
| :--- | :---: | :--- | :--- | :--- |
| **CALIFICADO (Con Lead)** | `true` | Nombre real | Badge Verde | Email frío vía dashboard |
| **EMPRESA APTA (Sin Lead)** | `true` | `"Contacto Pendiente"` | Badge Ámbar | Prospección Manual |
| **DESCALIFICADO** | `false` | Cualquier nombre | Badge Gris | Ninguna |

## 3. Arquitectura de Auditoría en 2 Fases

### Fase 1: Auditoría a Nivel de Empresa (Company-Level Audit)
- **Entrada:** Noticias descubiertas, contexto del formulario (propuesta de valor, dolor del cliente), contexto RAG de Tavily.
- **Proceso:** Se realiza un **único llamado al LLM** que evalúa si la empresa tiene un hito de crecimiento válido reciente (2025/2026) bajo los criterios de Tier 1 o Tier 2.
- **Pydantic Model:** `CompanyAuditResult` con campos `is_company_approved`, `company_justification`, `trigger_summary`.
- **Si RECHAZADA:** Se inserta un único registro con `es_calificado = False`, `nombre_lead = "Contacto Pendiente"`, y la justificación de rechazo. Se cortocircuita el proceso completo (0 llamadas adicionales al LLM para los leads), ahorrando hasta un **60% de cuota de API**.
- **Si APROBADA:** Se procede a la Fase 2.

### Fase 2: Validación a Nivel de Lead (Lead-Level Audit)
- **Entrada:** Resultado de la Fase 1 (pre-aprobación de empresa), datos de leads de LinkedIn, contexto del formulario.
- **Proceso:** Para cada lead activo, se evalúa si su ROL es relevante para la propuesta de valor mediante un llamado individual al LLM.
- **Pydantic Model:** `BusinessValidationResult` con campos `is_approved`, `justification`, `subject_line`, `email_body`.
- **Escenarios de Salida:**
  - **Lead aprobado:** `es_calificado = True`, nombre real, email redactado → **CALIFICADO (Con Lead)**
  - **Lead rechazado por rol:** `es_calificado = False`, nombre real, sin email.
  - **Todos los leads rechazados por rol:** Se persiste adicionalmente una fila `"Contacto Pendiente"` con `es_calificado = True` → **EMPRESA APTA (Sin Lead)**
  - **Sin leads activos (todos pre-descalificados o lista vacía):** Se inserta directamente `"Contacto Pendiente"` con `es_calificado = True` → **EMPRESA APTA (Sin Lead)**

## 4. Pre-Filtros Deterministas (Antes de la Fase 1)

1. **Comprobación de Calidad de Noticias:** Si las noticias extraídas están vacías, son menores a 150 caracteres o contienen errores (404, 429, etc.), se descalifica inmediatamente sin llamar al LLM.
2. **Validación Antiruido (Generic Sector Noise Guard):** Si el nombre de la empresa no aparece en ningún título o snippet, se descalifica por "Ruido Genérico del Sector".

## 5. Especificaciones de Entrada/Salida (I/O)
### Entradas (Formulario Plano Completo)
- Archivo JSON unificado en `.tmp/active_runtime_context.json` que contiene el formulario unificado del cliente activo (`mi_empresa`, `propuesta_valor`, `dolor_cliente`, `cargo_decision`, `casos_exito`, `triggers_compra`, `max_news_articles`).
- Archivos temporales de noticias `.tmp/news_{company_name}.json` y leads `.tmp/leads_{company_name}.json` (con correos enriquecidos vía Hunter.io).

### Salidas (Outputs)
- **Persistencia en Base de Datos:** Registra directamente cada lead evaluado en la tabla `leads` de Supabase, incluyendo el correo electrónico corporativo enriquecido (`email`), el razonamiento detallado del filtro, el trigger de la noticia (`subject_line`), el cuerpo del email personalizado (en caso de ser calificado), y la columna obligatoria `job_id` de ejecución.
- **Persistencia Dinámica de Múltiples Noticias:** Almacena la lista de noticias en la columna `url_noticia` serializada en formato JSON string `[{"title": "...", "url": "..."}]`. Si el lead es calificado (`es_calificado = True`) o es empresa apta, se guarda la lista completa; si es descalificado, se limita a 2 noticias (`news_subset = news_data[:2]`).

## 6. Restricciones y Pautas de Correlación RAG
- **Redacción de Email Personalizado (Afinamiento de Precisión y Multi-Cliente):**
  - **Instrucción de Idiomas (English Prompts with Spanish Output):** Todos los System Prompts se escriben en **inglés**. El payload JSON de salida (`justification`, `subject_line`, `email_body`) se genera en **español** fluido y profesional.
  - **Soporte Multilingüe Nativo:** El pipeline acepta entradas del formulario en español, inglés o mezclados.
  - **Con Trigger Noticioso Requerido:** La justificación (`justification`) DEBE estructurarse en 3 puntos numerados (1. EL HECHO NOTICIOSO DETONANTE, 2. EL IMPACTO OPERATIVO DEDUCTIVO, 3. ENCAJE DEL ROL).
- **Guardia de Saludos de Lead:** Saludar únicamente usando el nombre de pila (`first_name`) del lead.
- **Auditoría Híbrida Deductiva (Dos Tiers):**
  - **TIER 1 (Match Directo LATAM):** Si la noticia muestra explícitamente oficinas en Colombia, planes de expansión en LATAM, o licitaciones en portales colombianos, aprobar inmediatamente.
  - **TIER 2 (Deducción de Crecimiento Global):** Si la noticia muestra crecimiento global significativo, aprobar porque este crecimiento inevitablemente estresará su cadena de suministro y operaciones 3PL.
  - **Rechazar SOLO si:** la noticia es meramente asistencia a conferencias sin anuncios concretos, blogs genéricos, o eventos históricos anteriores a 2025.
- **Filtro de Empresa en Título (Title Company Mismatch Gate):** Si el cargo del lead contiene "at " o "en " seguido de una empresa que no sea la objetivo, se descarta automáticamente sin llamar al LLM.
- **Inyección de Leads Fantasma y Purificación del Dashboard (Human Fallback Gate):** Si la empresa califica en Fase 1 pero no hay leads activos o todos son rechazados por rol, se inyecta `"Contacto Pendiente"` con `es_calificado = True` (EMPRESA APTA) para no perder la empresa valiosa.
- **Guardarraíl Estricto de Relevancia Temporal:** El LLM audita estrictamente el año del hito. Hitos anteriores a **2025** son rechazados obligatoriamente.
- **Rotación de Claves Groq (Round-Robin API Key Rotator):** Rotación dinámica entre claves configuradas (`GROQ_API_KEY_1`, `GROQ_API_KEY_2`, etc.) con jitter delays.
- **Función Centralizada `_call_groq_with_retry`:** Todas las llamadas al LLM usan una función utilitaria centralizada que encapsula la rotación de claves, pacing con jitter, y reintentos exponenciales (máx. 3 intentos).
- **Función Centralizada `_serialize_news`:** Serialización de noticias para Supabase encapsulada en una función utilitaria que acepta un flag `full` para controlar si se guarda la lista completa o solo un subconjunto.



---

## Addendum v3.12 — Scoring ICP y calificación FIT-FIRST (Auditoría #1, #2, #3, #5)
- La calificación deja de ser binaria y centrada en noticias. Ahora se puntúa **FIT (ICP)** e **INTENT (trigger)** 0–100 y se calcula un `match_score` compuesto + tier (A/B/C/D).
- **Fit-first:** los pre-filtros de noticias ya NO descartan empresas; solo determinan `has_recent_trigger`. Una empresa de alto fit **sin** noticias sigue calificada (nurture, intent=0). Los anti-perfiles se rechazan.
- Fase 2 asigna `role_fit_score` por contacto y no inventa noticias cuando la calificación es por fit.
- **Determinismo:** `temperature=0.1` en todas las llamadas de calificación (Fase 1 y 2).
- Detalle completo y fórmulas en `directivas/09_lead_scoring_engine_SOP.md`.



## Addendum v3.12.3 — Anti-perfil no debe descartar la industria objetivo + tamaño "N+" (fix de calibración)
- **Bug observado (Elite Logística):** el validador descartaba CROs (Parexel, IQVIA, ICON…) como "competidor/anti-perfil" mientras aprobaba otro CRO idéntico (PPD) → inconsistencia. Causa: la Fase 0 contaminaba `target_industry_core` con el servicio del remitente ("...Logistics") y la Fase 1 sobre-aplicaba el anti-perfil.
- **Fix Fase 1 (anti-perfil):** una empresa es anti-perfil SOLO si su negocio CENTRAL es el mismo servicio que vende el remitente (competidor directo real). Operar en la industria objetivo = CLIENTE, nunca competidor; prohibido inferir competencia por tener operaciones internas (un CRO con logística interna sigue siendo cliente).
- **Fix Fase 1 (tamaño):** las bandas "N+" (ej. "500+") son un PISO; una empresa de 10.000 empleados cumple "500+". Solo se penaliza si está claramente POR DEBAJO del piso.
- **Fix Fase 0 (`main.py`):** `target_industry_core` describe la industria del CLIENTE, nunca el servicio del remitente (usar "Clinical Research & Biopharma", no "Biopharma Logistics").
