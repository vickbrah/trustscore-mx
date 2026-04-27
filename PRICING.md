# TrustScore MX — Análisis de Costos y Pricing

## Filosofía
Cobrar mínimo 3x sobre costo variable (markup 200%). En tiers premium, markup real llega a 5-10x porque mucho dato es público y solo aplicamos infra + lógica de scoring.

---

## Costo por consulta (lo que NOSOTROS pagamos)

| Fuente | Costo unitario | Tipo | Notas |
|---|---|---|---|
| Validador RFC SAT | $0.00 MXN | Público | Servicio web del SAT, gratis |
| Lista 69-B SAT (EFOS/EDOS) | $0.00 MXN | Público | CSV descargable mensual del SAT |
| DOF (sanciones, inhabilitaciones) | $0.00 MXN | Público | Scraping del Diario Oficial |
| Boletín Concursal (quiebras) | $0.00 MXN | Público | Scraping IFECOM |
| CONDUSEF / PROFECO (quejas) | $0.00 MXN | Público | Scraping de portales |
| Validación INE/Renapo | $25.00 MXN | API paga | Vía Verificamex / NubariumIA |
| Validación CURP | $8.00 MXN | API paga | Vía Renapo / proveedor |
| Listas OFAC + PEP global | $8.00 MXN | API paga | Vía Truora / ComplyAdvantage |
| Buró de Crédito completo | $120.00 MXN | API paga + regulación | Requiere SOFOM o partner |
| Círculo de Crédito | $90.00 MXN | API paga | Alternativa a Buró |
| Belvo (open banking, opt-in) | $15.00 MXN | API paga | Solo si el evaluado da consentimiento |
| Registro Público de Comercio | $5.00 MXN | Mixto | Algunas entidades cobran |
| Litigios judiciales (TSJ) | $3.00 MXN | Scraping + infra | Requiere mantenimiento |

**Costo fijo de infraestructura por consulta:** ~$0.50 MXN
(compute + DB + storage del reporte + logs)

---

## Tiers de pricing al cliente

### TIER 1 — EXPRESS · $49 MXN
**Verificación rápida de identidad y status fiscal**

Incluye:
- Validación de formato RFC/CURP (algoritmo)
- Lookup en Lista 69-B del SAT (EFOS/EDOS)
- Consulta DOF (sanciones)
- Boletín Concursal (quiebra activa)

Costo nuestro: **$1.00 MXN** (todo data pública + infra)
Markup: **4,800%**
Margen bruto: $48 MXN por consulta
Tiempo de respuesta: <2 segundos

**Caso de uso:** "Antes de mandarle anticipo a mi proveedor nuevo, ¿está en lista negra?"

---

### TIER 2 — ESTÁNDAR · $149 MXN
**Verificación completa de persona o empresa**

Incluye todo Express PLUS:
- Validación INE/CURP contra Renapo (foto + datos)
- Listas OFAC + PEP internacionales
- Quejas CONDUSEF/PROFECO
- Score TrustScore agregado (0-1000)

Costo nuestro: **$42 MXN** ($25 INE + $8 CURP + $8 PEP + $1 público + $0.50 infra)
Markup: **255%**
Margen bruto: $107 MXN por consulta
Tiempo de respuesta: <8 segundos

**Caso de uso:** "Voy a rentar mi depa o contratar a alguien high-ticket, quiero saber con quién trato."

---

### TIER 3 — PROFESIONAL · $399 MXN
**Reporte exhaustivo + análisis societario**

Incluye todo Estándar PLUS:
- Análisis de red societaria (accionistas en otras empresas)
- Cruce de accionistas con Lista 69-B
- Litigios judiciales activos (estatales)
- Registro Público de Comercio
- Recomendación textual generada (semáforo + razones)

Costo nuestro: **$50 MXN** ($42 anteriores + $5 RPC + $3 litigios)
Markup: **698%**
Margen bruto: $349 MXN por consulta
Tiempo de respuesta: <30 segundos

**Caso de uso:** "Voy a meterle $500K a un partner. Necesito due diligence ligera."

---

### TIER 4 — ENTERPRISE · $799 MXN
**Due diligence con buró de crédito**

Incluye todo Profesional PLUS:
- Buró de Crédito completo
- Belvo open banking (si el evaluado autoriza)
- Análisis de flujo bancario (90 días)
- Reporte PDF firmado digitalmente

Costo nuestro: **$185 MXN** ($50 + $120 Buró + $15 Belvo)
Markup: **332%**
Margen bruto: $614 MXN por consulta
Tiempo de respuesta: <2 minutos

**Caso de uso:** "Voy a darle crédito comercial o entrar en sociedad, full check."

> **Nota:** Tier 4 requiere ser SOFOM o tener contrato con un partner SOFOM. Hasta entonces, este tier va con flag "próximamente" en la landing y se vende en pre-orden.

---

## Suscripciones (recurrente, donde está el negocio real)

| Plan | Precio mensual | Consultas incluidas | Costo nuestro variable | Margen estimado |
|---|---|---|---|---|
| Starter | $499 MXN | 15 Express | $15 | $484 (97%) |
| Growth | $1,999 MXN | 30 Estándar + 50 Express | $1,310 | $689 (34%) |
| Pro | $4,999 MXN | 50 Profesional + 100 Estándar | $6,700 | -$1,701 (¡PIERDE!) |
| Enterprise | Cotización | Custom | — | — |

> **OJO:** Plan Pro está mal calibrado a propósito en este draft — hay que rebalancear los incluidos o subir precio. Marcado para revisión post-MVP.

**Plan Growth recalibrado:** 20 Estándar + 30 Express. Costo: $870. Margen: $1,129 (56%). 

---

## Proyección de revenue (escenario conservador, mes 6)

| Métrica | Valor |
|---|---|
| Clientes pagando | 100 |
| Mix promedio | 60% Starter, 30% Growth, 10% Pro |
| MRR | $115,800 MXN |
| Costo variable mensual | $32,000 MXN |
| **Margen bruto** | **$83,800 MXN/mes** |
| Costos fijos (infra+APIs base+legal) | $25,000 MXN |
| **Profit operativo** | **$58,800 MXN/mes** |

---

## Costos fijos (lo que pagamos pase lo que pase)

| Concepto | Costo mensual MXN |
|---|---|
| Hosting (Railway/Render/AWS) | $1,500 |
| Postgres managed | $800 |
| Stripe fees variables | (3.6% del revenue) |
| Cuentas API base (mínimos) | $5,000 |
| Dominio + SSL + correo | $300 |
| Aviso de privacidad / legal compliance | $3,000 |
| Soporte (tú, hasta cierto MRR) | $0 |
| **Total fijo mensual** | **$10,600 MXN** |

---

## Ruta de inversión inicial

| Etapa | Inversión | Resultado |
|---|---|---|
| **Pre-MVP (mes 0)** | $0-5,000 MXN | Landing + dominio + Stripe activo, captas leads |
| **MVP funcional (mes 1-2)** | $15,000 MXN | Backend desplegado, primeros 3 APIs pagas conectadas |
| **Tracción inicial (mes 3-4)** | $30,000 MXN | Marketing + primeros 20 clientes pagando |
| **Escala (mes 5-12)** | $150,000 MXN | Buró integrado vía partner SOFOM, equipo de 1 dev jr |

**Capital total para llegar a punto de equilibrio:** ~$200,000 MXN ($10K USD aprox)

Punto de equilibrio estimado: ~30 clientes pagando plan Growth = mes 4-5.
