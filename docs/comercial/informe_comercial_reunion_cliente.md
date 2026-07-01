# Informe Comercial y Calculadora de Costos — Glovar Prospector
### Documento de trabajo para reunión con cliente

> **Uso:** guía interna + material de demo. Referencia de moneda: **TRM $4.000 COP/USD** (ajustar al día). Modelo de costos: **bootstrap** (solo se paga Hunter.io; el resto opera en capas gratuitas).
> **Producto:** Glovar Prospector — plataforma SaaS de prospección B2B autónoma + espacio de trabajo comercial (CRM).

---

## Índice
1. [Valor del sistema](#1-valor-del-sistema)
2. [Cómo hacer la demo](#2-como-hacer-la-demo)
3. [Preguntas para el cliente](#3-preguntas-para-el-cliente)
4. [Feedback y aclaraciones (en blanco)](#4-feedback-y-aclaraciones)
5. [Presupuesto, calculadora y roadmap](#5-presupuesto-calculadora-y-roadmap)

---

## 1. Valor del sistema

### 1.1 Qué hace
Glovar Prospector automatiza el trabajo de **encontrar clientes potenciales, investigarlos y preparar el primer contacto**. Opera en dos modos:

- **Modo Rápido (persona):** entrega una lista de contactos calificados por cargo + industria + geografía en **segundos**. Ideal para llenar el pipeline rápido.
- **Modo Profundo (empresa):** además de encontrar al decisor, **detecta señales de compra recientes (noticias, movimientos, expansiones)**, evalúa el encaje real de cada empresa y **redacta un correo de contacto personalizado** listo para enviar. Tarda de 3 a 10 minutos por lote.

### 1.2 Qué recibe el cliente (entregables concretos)
- Lista de leads con **nombre, cargo, empresa, LinkedIn y correo verificado**.
- **Puntaje de encaje (match score)** que prioriza los mejores primero.
- En Modo Profundo: **la señal/noticia que justifica el contacto** + **borrador de correo personalizado**.
- **Mini-CRM tipo Kanban** para gestionar cada lead por etapas (nuevo → contactado → en conversación → propuesta → ganado/perdido), con **prioridades y notas internas**.
- **Envío de correo integrado** (vía su propia cuenta de Gmail).
- **Búsquedas guardadas y versionadas** para repetir prospecciones ganadoras.

### 1.3 Para qué más sirve (más allá de prospectar)
El sistema no es solo un buscador de leads: es el **centro de operación comercial del día a día**.
- Organiza y prioriza toda la cartera de oportunidades en un solo lugar.
- Reemplaza el Excel + LinkedIn + herramientas de correo dispersas.
- Conserva la **memoria comercial** (histórico, notas, motivos de cierre) que normalmente se pierde cuando un vendedor renuncia.

### 1.4 Los 3 beneficios que se venden
| Beneficio | Traducción para el cliente |
|---|---|
| **Gana más dinero** | Más reuniones con empresas que *justo ahora* tienen la necesidad |
| **Ahorra tiempo** | Lo que a una persona le toma días, aquí toma minutos |
| **Ahorra dinero** | Hace el trabajo de varias personas y reemplaza 3–4 herramientas |

### 1.5 Manejo de objeciones

**Objeción A — "Para eso contrato a una persona."**
> Un prospectador en Colombia cuesta, cargado con prestaciones, **~$2,6–3,4 millones al mes**, trabaja 8 horas, produce ~300–500 leads decentes, se cansa, se enferma, se va y se lleva el conocimiento. Y **de todos modos** necesitaría pagar aparte las herramientas de datos. El sistema hace ese volumen en 1–2 días, 24/7, con calidad constante, por una fracción de ese costo.

**Objeción B — "Prefiero contratar a alguien para ser aún más eficiente."**
> No es *o el sistema o la persona*: es **el sistema + la persona**. Estudios de la industria muestran que un vendedor dedica cerca de **dos tercios de su día a tareas que no venden** (investigar, armar listas, digitar, redactar). El sistema le quita esa carga y le devuelve esas horas para lo único que cierra ventas: **llamar, conversar y negociar**. Un vendedor apoyado por el sistema rinde como tres. Es la forma más barata de hacer más eficiente a quien contrate.

**Objeción C — "El humano hace más: llama, hace seguimiento, cierra."**
> Cierto, y por eso el sistema **no reemplaza al cerrador**: lo potencia. Hoy cubre investigación, datos, redacción, organización (CRM) y recordatorios. La llamada telefónica es **integrable en el roadmap** (marcador, registro de llamadas, WhatsApp). El sistema amplifica al vendedor, no lo elimina.

**Objeción D — "¿Por qué pago todos los meses?"**
> Porque no es un archivo, es un **motor encendido**: los datos calientes caducan, y las APIs, el hosting y la IA que lo alimentan son servicios mensuales. Como la luz: se paga por tenerla encendida todos los días.

---

## 2. Cómo hacer la demo

> **Objetivo de la demo:** que el cliente *vea* leads reales de SU sector aparecer y entienda que puede operar todo desde un solo lugar. Idealmente, prospectar en vivo con los datos de su propia empresa.

### 2.1 Flujo de la demo (guion sugerido)
1. **Contexto (2 min):** "Vamos a buscar clientes potenciales para *tu* empresa, en vivo."
2. **Modo Rápido primero (impacto inmediato):** llenar solo la frase o el cargo → mostrar contactos en segundos. Genera el "wow".
3. **Modo Profundo (el diferenciador):** llenar el formulario completo → mostrar cómo detecta la noticia/señal y redacta el correo.
4. **Resultados:** mostrar el ranking por puntaje, abrir un lead, mostrar el correo generado.
5. **CRM + envío:** enviar un lead al tablero Kanban, agregar una nota, mostrar el envío de correo.
6. **Cierre:** "Todo esto lo tendrías corriendo 24/7 por menos de lo que cuesta medio salario."

### 2.2 Los campos del sistema, explicados (qué espera para funcionar bien)

**Selector de modo (arriba):** *Rápido* (lista de contactos en segundos) vs *Profundo* (con señales/noticias, ~5 min).

**Campo en lenguaje natural — "Describe tu cliente ideal":**
- En **Modo Rápido** es lo único obligatorio (eso o un cargo). Ej.: *"Directores de Recursos Humanos en empresas de software de 200+ empleados en Colombia".*
- En **Modo Profundo** es opcional: si se escribe, autocompleta los campos de abajo.

**Campos del Modo Profundo (obligatorios salvo indicación):**

| Campo | Qué es | Qué poner (ejemplo) | Por qué importa |
|---|---|---|---|
| **Mi Empresa (Remitente)** | Nombre de la empresa del cliente | *Elite Logística* | Personaliza el correo y el contexto |
| **Sector Objetivo** | Industria a la que se le vende (máx. 3 términos) | *Salud, Finanzas* | Enfoca la búsqueda de empresas |
| **País** | País donde están las empresas objetivo | *Colombia* / *Estados Unidos* | Filtro geográfico principal |
| **Mercado objetivo / expansión** *(opcional)* | Mercado al que se expanden | País: EE.UU. → Mercado: *Colombia* | Encuentra empresas que operan/expanden a otra región |
| **Tamaño de empresa** | Rango de empleados | *201–500* (opciones: 1–50, 51–200, 201–500, 500+) | Ajusta el perfil firmográfico |
| **Cargo del tomador de decisión** | A quién contactar (máx. 3 términos) | *CEO, CTO, VP Ventas* | Define a quién se busca dentro de la empresa |
| **Dolor del cliente a resolver** | Problema que el cliente resuelve | *"Empresas extranjeras pierden cadena de frío al entrar a Colombia..."* | Alimenta el análisis de encaje y el correo |
| **Propuesta de valor / Resultado** | Qué ofrece y qué resultado da | *"Operador 3PL en salud con INVIMA y entregas < 24h"* | Da el argumento del mensaje |

**Opciones Comerciales Avanzadas (opcionales, acordeón):**

| Campo | Qué es | Ejemplo |
|---|---|---|
| **Triggers de Compra** (máx. 150 car.) | Señal que se busca en noticias | *Expansión a Colombia* |
| **Casos de Éxito / Diferenciadores** | Pruebas de valor para el correo | *reducción de tiempo 60%* |
| **Keywords de Industria** | Términos técnicos para afinar | *cold chain, INVIMA compliance* |
| **Empresas a excluir (Lista Negra)** | Empresas a NO prospectar (separadas por coma) | *Competidor ABC, Cliente actual X* |

**Controles finales:**
- **Límite de perfiles a analizar** (deslizador 5–25): cuántas empresas/contactos procesar.
- **Velocidad de Prospección** (solo Profundo): ⚡ Rápido (1 art./empresa, ~3 min) · 🚀 Estándar (3 art., ~6 min) · 🔍 Profundo (5 art., ~10 min).

> **Regla técnica a respetar en la demo:** en *Sector* y *Cargo*, usar **máximo 3 términos separados por coma** (el sistema lo advierte). Más términos degradan la búsqueda.

### 2.3 Estrategias de iteración (para mostrar dominio en vivo)
1. **Empezar amplio, luego afinar:** primera corrida general; si trae ruido, agregar *Keywords* y *Lista Negra*.
2. **Validar con Rápido, profundizar con Profundo:** usar Modo Rápido para confirmar que el ICP trae buenos cargos, y luego Modo Profundo sobre el mejor segmento.
3. **Usar Triggers para el *timing*:** si el cliente vende algo ligado a un evento (expansión, ronda de inversión, nueva regulación), ponerlo en *Triggers de Compra*.
4. **Ajustar cargo/tamaño si la calidad baja:** cambiar de "CEO" a "Director de Operaciones", o subir el tamaño de empresa.
5. **Guardar la búsqueda ganadora:** dejar la consulta guardada para repetirla cada semana (mostrar que es un motor recurrente, no una consulta única).

---

## 3. Preguntas para el cliente

### 3.1 Descubrimiento (antes de la demo)
- ¿A qué se dedica la empresa y cuál es el producto/servicio estrella?
- ¿Quién es su cliente ideal hoy? (sector, tamaño, país, cargo que decide)
- ¿Cómo consiguen clientes actualmente? ¿Cuántos leads/reuniones generan al mes?
- ¿Tienen a alguien dedicado a prospectar? ¿Cuánto tiempo le dedica?
- ¿Qué herramientas usan hoy (Excel, LinkedIn, CRM, correo)?
- ¿Cuánto vale, en promedio, cerrar un cliente nuevo? (para calcular ROI)

### 3.2 Verificación de comprensión (durante/después de la demo)
- ¿Le quedó claro qué hace el sistema y qué recibe?
- ¿Ve la diferencia entre el Modo Rápido y el Profundo?
- ¿Los contactos que aparecieron se parecen a sus clientes reales?
- ¿Qué parte le generó más valor? ¿Qué parte no le quedó clara?
- ¿Cómo imagina usándolo en su día a día?

### 3.3 Cierre / compromiso
- ¿Cuántos leads al mes necesitaría para que esto le sirva?
- ¿Quiénes en su equipo lo usarían?
- ¿Qué necesitaría ver para tomar la decisión hoy?

---

## 4. Feedback y aclaraciones
> *Sección en blanco para diligenciar durante y después de la reunión.*

**Datos del cliente / empresa:**
- Empresa:
- Sector:
- Cliente ideal (cargo / tamaño / país):
- Valor promedio de un cierre:

**Lo que más le gustó:**
-

**Dudas / objeciones planteadas:**
-

**Funcionalidades que pidió (que no tenemos):**
-

**Preguntas que YO puedo hacer para avanzar la venta:**
- ¿Qué volumen de leads justificaría la inversión?
- ¿Prefiere pagar mensual o anual (con descuento)?
- ¿Le interesa un piloto de 15 días?
- ¿Quién más debe aprobar la compra?

**Compromisos / próximos pasos:**
-

---

## 5. Presupuesto, calculadora y roadmap

### 5.1 Presupuesto inicial para dejar el sistema operativo (modelo bootstrap)

| Componente | Configuración | Costo de bolsillo |
|---|---|---|
| Vercel | Hobby (gratis) | $0 |
| Supabase | Free (500 MB) | $0 |
| Modal | 2 cuentas × $30 crédito/mes | $0 (renovable) |
| Groq | 6 llaves rotadas (capa gratuita) | $0 |
| Tavily | Free (1.000 créditos/mes) | $0 |
| Apify | Free (~$5 crédito/mes) | $0 |
| **Hunter.io** | **Starter (500 correos/mes)** | **$34 (≈ $136.000 COP)** |
| **TOTAL PISO OPERATIVO** | | **≈ $34/mes (≈ $136.000 COP)** |

> Para los **primeros clientes**, el único gasto real es **Hunter ($34/mes)**. Todo lo demás opera en capa gratuita.

### 5.2 Calculadora de costo por lead (fórmula)

**Costos unitarios (medidos):**
- Hunter: **$0,068 / correo verificado**
- Tavily: **$0** hasta 1.000 cr/mes; luego $0,0075/cr (~4,2 cr por empresa profunda)
- Apify: **$0** hasta $5/mes; luego ~$0,018 por empresa profunda
- Groq / Modal / Vercel / Supabase: **$0** (capa gratuita)

**Variables:**
- `L` = leads generados en el mes
- `e` = tasa de enriquecimiento (proporción de leads que consumen un correo Hunter). Recomendado: **0,7**
- `PISO` = suma de suscripciones activas ese mes (arranque = $34)

**Fórmulas:**

```
Costo_marginal_por_lead  =  (Tavily_por_lead) + (Apify_por_lead) + e × $0,068
      → dentro de capas gratuitas:  ≈ 0,7 × $0,068 ≈ $0,048 por lead

Costo_efectivo_por_lead  =  (PISO / L)  +  Costo_marginal_por_lead

Precio_venta_por_lead    =  Costo_efectivo_por_lead × Markup   (o precio por VALOR)
```

**Escenarios (arranque, solo Hunter salvo indicación):**

| Leads/mes | ¿Dentro de gratis? | Piso mensual | Costo efectivo por lead |
|---|---|---|---|
| 50 | Sí | $34 | **$0,73** (≈ $2.900 COP) |
| 150 | Sí | $34 | **$0,28** (≈ $1.120 COP) |
| 230 | Límite Tavily/Apify | $34 | **$0,20** (≈ $800 COP) |
| 500 | No (+ Tavily $30 + Apify ~$4) | $68 | **$0,19** (≈ $760 COP) |

> **Conclusión de la calculadora:** incluso en el peor caso (50 leads/mes), el costo por lead es de **centavos de dólar**. Un lead calificado tiene un valor de mercado muy superior, lo que sostiene márgenes del 80–90%.

### 5.3 ¿Para cuántos clientes alcanza el arranque? (fórmula de capacidad)

```
N_clientes ≈ mínimo entre:
   Tavily:  1.000 cr ÷ (4,2 cr × leads_por_cliente)
   Apify:   ~230 empresas ÷ leads_por_cliente
   Hunter:  500 correos ÷ (e × leads_por_cliente)
```

| Stack | Costo/mes | Capacidad | Clientes (uso ~40 leads c/u) |
|---|---|---|---|
| **Free + Hunter** | ~$34 | ~200–230 leads profundos/mes | **3–5 clientes** |
| **+ Tavily $30** | ~$64 | ~900 leads/mes (limita Hunter 500 correos) | **10–15 clientes** |

> El límite **no es el tiempo** (los créditos se renuevan cada mes), sino el **volumen de leads**. El arranque sostiene los primeros 3–5 clientes de forma indefinida y casi sin costo.

### 5.4 Precios de venta sugeridos (lanzamiento)

| Plan | Segmento | Precio/mes | Leads profundos/mes | Funcionalidades |
|---|---|---|---|---|
| **Free / Prueba** | Captación | $0 | 5 (total) | Modo Rápido (3/día), CRM básico |
| **Individual** | Persona natural | **$199.000 COP** (~$50) | 50 | Modo Rápido *fair-use*, CRM, notas, envío Gmail, 1 usuario |
| **Growth / PyME** ⭐ | Empresa pequeña | **$790.000 COP** (~$200) | 500 | Ambos modos, CRM completo, scoring, envío, 3 usuarios |
| **Business** | Equipo comercial | **$1.900.000 COP** (~$475) | 2.000+ | Todo + 8 usuarios, secuencias, dashboards, prioridad |
| **Enterprise** | Corporativo | A la medida | Ilimitado | Usuarios ilimitados, integraciones, SLA |

**Referencia de mercado:** Enginy (antes Genesy), plataforma casi idéntica, cobra desde **€799/mes (~$3,4M COP)**. Los precios propuestos están muy por debajo, adaptados al mercado local, con margen del 80–90%.

**Táctica de lanzamiento:** ofrecer a los primeros 5–10 clientes un **precio de fundador** (30–50% de descuento) a cambio de testimonio y feedback, sin bajar el precio de lista visible.

### 5.5 Roadmap de funcionalidades (dependencia del cliente)

**✅ Lo que YA tiene:**
- Prospección Modo Rápido y Modo Profundo
- Detección de señales/noticias + redacción de correo con IA
- Scoring y ranking de leads
- Mini-CRM Kanban (etapas, prioridades)
- Notas internas por lead
- Envío de correo integrado (Gmail)
- Búsquedas guardadas con versionado

**🔧 Lo que se mejora (corto plazo):**
- Enriquecimiento de correo más robusto (más cobertura verificada)
- Filtros geográficos más precisos en Modo Rápido
- Panel de resultados con más contexto por lead

**🚀 Lo que falta para volver al cliente DEPENDIENTE (prioridad):**
| Feature | Efecto en dependencia |
|---|---|
| **Tareas y recordatorios con vencimiento** | Da una razón para entrar cada mañana |
| **Reuniones + sincronización con calendario** | Convierte el CRM en su agenda diaria |
| **Resumen/briefing diario (correo o WhatsApp)** | Gancho de re-entrada: *"hoy tienes 4 leads nuevos y 3 seguimientos"* |
| **Secuencias de seguimiento automáticas** | El sistema trabaja solo; apagarlo cuesta pipeline |
| **Bandeja unificada (detección de respuestas)** | Si contestan dentro de la app, viven en la app |
| **Dashboard de métricas y conversión** | El gerente entra a reportar → decisor que no cancela |
| **Marcador telefónico / WhatsApp / registro de llamadas** | Cierra la objeción "el humano también llama" |
| **Colaboración de equipo (asignar, mencionar)** | Todo el equipo se conecta → cancelar afecta a varios |

> **Estrategia de fondo:** convertir el sistema de un "generador de leads" a un **"sistema operativo comercial diario"**. Mientras más datos meta el cliente (notas, reuniones, correos, resultados), **más doloroso es abandonarlo** — esa es la ventaja competitiva sostenible y la que asegura la mensualidad.

---

*Documento vivo — actualizar tras cada reunión con feedback real de clientes.*
