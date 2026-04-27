# TrustScore MX — MVP One-Man Army

API + dashboard para evaluar la confianza de hacer negocios con cualquier persona o empresa en México. Cruza SAT, INE, listas negras, demandas y buró → devuelve un score 0–1000 con recomendación.

## Estructura del proyecto

```
trustscore-mx/
├── PRICING.md                 # Análisis de costos y markup 200%
├── README.md                  # Este archivo
├── frontend/
│   ├── index.html             # Landing page profesional
│   └── dashboard.html         # Dashboard del cliente (login + consultas + saldo + API key)
└── backend/
    ├── main.py                # FastAPI app (todos los endpoints)
    ├── db.py                  # Modelos SQLAlchemy (User, ApiKey, Consulta)
    ├── auth.py                # JWT + API keys + bcrypt
    ├── billing.py             # Stripe checkout + webhooks
    ├── requirements.txt
    ├── .env.example
    ├── data/
    │   └── sat_69b_sample.csv # Lista 69-B (muestra; en prod descargas el real del SAT)
    └── services/
        ├── identity.py        # Validación REAL de RFC (con homoclave) + CURP + INE
        ├── sat.py             # Lookup en Lista 69-B + DOF + Boletín Concursal
        ├── external.py        # APIs pagas (stubs determinísticos hasta tener llaves)
        └── scoring.py         # Algoritmo TrustScore (0-1000) auditable
```

---

## Cómo correr en local (10 minutos)

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # edita los valores opcionales después
uvicorn main:app --reload --port 8000
```

Verifica que arrancó: abre `http://localhost:8000/docs` y verás Swagger con todos los endpoints. La base de datos SQLite se crea automáticamente la primera vez.

### 2. Frontend

No requiere build. Abre `frontend/index.html` y `frontend/dashboard.html` directamente con un servidor estático:

```bash
cd frontend
python -m http.server 5173
# luego abre http://localhost:5173/index.html
```

(O usa la extensión "Live Server" de VS Code, o `npx serve .`)

### 3. Probar end-to-end

1. Abre `http://localhost:5173/dashboard.html`
2. Crea cuenta (te llegan 5 consultas Express gratis)
3. En el formulario, prueba con `EJE850101A11` — está en la lista 69-B muestra (situación DEFINITIVO). Verás el score caer a zona roja con bandera crítica.
4. Prueba con `XAXX010101000` (RFC genérico válido) — score alto, verde.
5. Revisa el histórico, genera una API key, prueba un curl como el del dashboard.

---

## Qué es REAL y qué es MOCK en el MVP

| Componente | Estado MVP | Cómo activar real |
|---|---|---|
| Validación RFC con algoritmo homoclave | ✅ **REAL** | Ya funciona |
| Validación CURP estructural | ✅ **REAL** | Ya funciona |
| Lista 69-B SAT | ✅ **REAL** (con CSV muestra) | Reemplaza `data/sat_69b_sample.csv` con el descargado del SAT, o automatiza la actualización mensual |
| Sanciones DOF | 🟡 Stub | Implementa scraper de `dof.gob.mx/busqueda_avanzada.php` |
| Boletín Concursal IFECOM | 🟡 Stub | Scraper de `ifecom.cjf.gob.mx` |
| Validación INE/Renapo | 🟡 Stub determinístico | Contrata Nubarium/Verificamex y configura `NUBARIUM_API_KEY` |
| OFAC / PEP | 🟡 Stub determinístico | Contrata Truora y configura `TRUORA_API_KEY` |
| CONDUSEF/PROFECO quejas | 🟡 Stub | Scraper propio o manual review |
| Litigios judiciales | 🟡 Stub | Scrapers por TSJ estatal (CDMX, EdoMex, Jalisco, NL son los más urgentes) |
| Buró de Crédito | 🟡 Stub | Requiere SOFOM o partner. Hasta entonces, este tier va con flag "próximamente" |
| Stripe checkout | 🟡 Demo mode | Configura `STRIPE_SECRET_KEY` y `STRIPE_WEBHOOK_SECRET` |

> **Crítico:** los stubs son **determinísticos**, no aleatorios. Devuelven el mismo resultado para el mismo RFC. Eso significa que puedes demostrar el flujo a un cliente sin que se note y sin pagar APIs todavía.

---

## Roadmap de activación (orden recomendado)

1. **Semana 1 — Lista 69-B real automatizada**: cron que descarga el CSV del SAT mensual y reindexa Postgres. Es la fuente con mayor poder de fuego y es 100% gratis.
2. **Semana 2 — Stripe en vivo**: crea productos en el dashboard, pega `STRIPE_SECRET_KEY` y configura el webhook en Stripe Dashboard apuntando a `/api/v1/billing/webhook`. Pasa de modo demo a producción.
3. **Semana 3 — Truora (OFAC + PEP)**: el más fácil de las APIs pagas, valor enorme. ~$8 MXN/consulta, cobramos $149.
4. **Semana 4 — Nubarium (INE/Renapo)**: convierte el tier Estándar en producto serio.
5. **Mes 2 — Scrapers DOF + Boletín Concursal + CONDUSEF**: trabajo de devops, costo cero variable.
6. **Mes 3 — Despacho legal**: aviso de privacidad, contrato B2B, plantillas ARCO.
7. **Mes 4-6 — Buró**: vía partner SOFOM (Konfio Partners, Apoyo Económico, etc.) o SOFOM propia si hay capital.

---

## Despliegue a producción

**Opción más rápida: Railway o Render**

Backend:
```
1. Crea proyecto en Railway, conecta el repo, root = backend/
2. Variables de entorno: las del .env.example
3. Comando: uvicorn main:app --host 0.0.0.0 --port $PORT
4. Agrega Postgres como addon, copia DATABASE_URL al servicio
```

Frontend (Cloudflare Pages o Vercel):
```
1. Sube la carpeta frontend/ como sitio estático
2. En dashboard.html, cambia API base si quieres dominio fijo (línea ~340)
3. Configura dominio: trustscore.mx → Cloudflare → Pages
```

DNS:
- `trustscore.mx` → frontend
- `api.trustscore.mx` → backend
- Stripe webhook → `https://api.trustscore.mx/api/v1/billing/webhook`

---

## Cumplimiento legal mínimo antes de cobrar

1. **Aviso de privacidad** publicado en el sitio (LFPDPPP). Hay generadores en INAI; un despacho lo deja bien por $3-8K MXN.
2. **Términos y condiciones** que limitan uso de los reportes a fines legítimos B2B.
3. **Cláusula de consentimiento ARCO** que el cliente debe aceptar antes de consultar a un tercero.
4. **No publicar** scores ni reportes (esto sería tratamiento sensible). Solo se entregan al cliente que paga.
5. **No tocar Buró sin SOFOM o partner** — eso es regulado por CNBV.

---

## Próximas iteraciones obvias

- PDF firmado digitalmente del reporte (uso pdfkit/weasyprint + cert)
- Webhook hacia el cliente cuando un score consultado cambia (monitoreo)
- Bulk upload de CSVs (verificar 200 RFCs de un jalón)
- SDK Python y JS publicados en PyPI/npm
- Branding del PDF al cliente (white label, +$$$)
- Score de tendencia: detectar cuando un proveedor empieza a "manchar" su perfil
- Integración con marketplace mexicanos (Mercado Libre seller, Kavak, etc.)

---

**Construido en una sentada. Modifica, despliega, vende.**
