# Informe de Costos y Planes — AI Lead Prospector (DEFINITIVO)

> Modelo de costos verificado sobre facturación real. Facturación **mensual** (sin compromisos anuales). Referencia: **TRM $4.000 COP/USD**.

---

## 1. Tabla de costos — solo pagamos 3 plataformas

| Plataforma | Plan (mensual) | Costo/mes | Para qué se usa |
|---|---|---|---|
| **Tavily** | Project | **$30** (~$120.000 COP) | Descubrir empresas, noticias/triggers y buscar contactos |
| **Apify** | Starter | **$29** (~$116.000 COP) | Scraping de LinkedIn (**solo modo profundo/empresas**) |
| **Hunter** | Starter | **$49** (~$196.000 COP) | Correos verificados |
| **STACK COMPLETO (empresas)** | | **$108/mes (~$432.000 COP)** | Los 3 servicios |
| **Stack solo personas (sin Apify)** | | **$79/mes (~$316.000 COP)** | Tavily + Hunter |

> Vercel, Supabase, Modal y Groq operan en **capa gratuita** → **no se suman** al costo.

---

## 2. Límites de cada plataforma

| Plataforma | Cupo/mes | Capacidad real |
|---|---|---|
| **Hunter** | 2.000 créditos | **~1.500 contactos con correo verificado** → **LÍMITE MAESTRO** |
| Tavily | 4.000 créditos | ~950 empresas profundas · o ~5.000 búsquedas rápidas |
| Apify | ~$29 de uso | ~1.300 empresas (solo profundo) |

**Conclusión:** el tope de todo el sistema lo pone **Hunter: ~1.500 contactos verificados al mes.** Tavily y Apify tienen holgura de sobra.

---

## 3. Qué usa cada modalidad

| Modalidad | Qué recibe el cliente | APIs que consume |
|---|---|---|
| **Persona natural (Rápido)** | Contactos (nombre, cargo, LinkedIn, **correo verificado**) + workspace (CRM, dashboard, calendario, notas). Sin noticias. | **Tavily + Hunter** (NO Apify) |
| **Empresa (Profundo)** | Todo lo anterior **+ noticia/trigger + email personalizado + auditoría de encaje**, con varios contactos por empresa (~3–4). | **Tavily + Apify + Hunter** |

---

## 4. Costo por lead (lo que te cuesta a ti)

**Costo marginal** = lo que consume cada lead de los cupos que ya pagaste.

| Tipo de lead | Consumo | Costo marginal | En COP |
|---|---|---|---|
| **Contacto rápido (persona)** | 0,8 cr Tavily + 1,3 cr Hunter | **~$0,04** | **~$155 COP** |
| **Contacto profundo (empresa)** | 1,2 cr Tavily + Apify + 1,3 cr Hunter | **~$0,05** | **~$190 COP** |
| **Empresa completa (~3,5 contactos)** | 4,2 cr Tavily + $0,022 Apify + ~4 cr Hunter | **~$0,16** | **~$625 COP** |

**Fórmula del costo real por lead:**
```
Costo por lead = Stack mensual ($432.000 COP) ÷ total de contactos del mes
```
- A media capacidad (750 contactos): ~$576 COP/lead
- A plena capacidad (1.500 contactos): ~$290 COP/lead

> Cuanto más llenas el stack, más barato sale cada lead. Un cliente solo = caro; 3+ clientes = costo por lead se desploma.

---

## 5. Planes de venta

| Plan | Modalidad | Precio/mes | Cupo | Costo/lead (tú) |
|---|---|---|---|---|
| **Natural** | Persona (rápido) | **$149.000 COP** (~$37) | 150 contactos | ~$155 COP |
| **Negocio** | Empresa (profundo) | **$390.000 COP** (~$98) | 150 leads | ~$190 COP |
| **Growth** ⭐ | Empresa (profundo) | **$790.000 COP** (~$198) | 450 leads | ~$190 COP |
| **Business** | Empresa (profundo) | **$1.900.000 COP** (~$475) | 1.200 leads | ~$190 COP |

*Referencia de mercado: Enginy (plataforma casi idéntica) cobra desde €799/mes (~$3,4M COP).*

---

## 6. Planes iniciales que podemos soportar (con el stack actual)

Cada combinación cabe **sin pagar excedentes** (respeta el límite maestro de ~1.500 contactos verificados).

| Combinación | Contactos | Stack | Ingreso/mes | Ganancia | Margen |
|---|---|---|---|---|---|
| **8 Naturales** (sin Apify) | 1.200 | $316.000 | $1.192.000 | $876.000 | **~73%** |
| **1 Growth + 3 Negocios** | 900 | $432.000 | $1.960.000 | $1.528.000 | **~78%** |
| **1 Growth + 4 Negocios + 2 Naturales** | 1.350 | $432.000 | $2.648.000 | $2.216.000 | **~84%** |
| **1 Business** | 1.200 | $432.000 | $1.900.000 | $1.468.000 | **~77%** |

**Regla de arranque:** nunca sostengas el stack con **un solo cliente** (sale caro). Arranca con personas naturales ($79/mes, sin Apify) o cierra 2–3 empresas antes de encender Apify.

---

## 7. Conclusiones claras

1. **Solo pagas 3 plataformas:** Tavily $30 + Apify $29 + Hunter $49 = **$108/mes**. Todo lo demás es gratis.
2. **Tu tope es Hunter: ~1.500 contactos verificados/mes.**
3. **Cada lead te cuesta ~$155–190 COP** (marginal); diluido, baja hasta ~$290 COP a plena capacidad.
4. **El stack actual sostiene ~8 clientes pequeños o 3–4 Growth**, con margen **73–84%**.
5. **Persona natural no usa Apify** → arranca con stack de solo **$79/mes**.
6. **Palanca de margen:** enriquecer solo al decisor principal por empresa (1 contacto en vez de 3–4) triplica la capacidad de Hunter.

> Para cálculos rápidos usa la **calculadora** (`calculadora_costos.html`): metes cuántos clientes de cada plan y te dice si cabe, tu costo/lead y tu margen.
