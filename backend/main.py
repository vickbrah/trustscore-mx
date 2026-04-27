"""
TrustScore MX — API REST.

Endpoints clave:
  POST /api/v1/auth/signup            - crea cuenta
  POST /api/v1/auth/login             - devuelve JWT
  POST /api/v1/auth/api-key           - genera API key
  POST /api/v1/check/express          - tier $49
  POST /api/v1/check/estandar         - tier $149
  POST /api/v1/check/profesional      - tier $399
  POST /api/v1/check/enterprise       - tier $799 (mock buró)
  POST /api/v1/billing/checkout       - inicia compra Stripe
  POST /api/v1/billing/webhook        - webhook Stripe
  GET  /api/v1/me                     - perfil + saldo
  GET  /api/v1/me/consultas           - histórico

Para correr:
  cd backend
  pip install -r requirements.txt
  cp .env.example .env
  uvicorn main:app --reload
"""

import os
import asyncio
from datetime import datetime
from typing import Optional, Literal

from fastapi import FastAPI, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from db import init_db, get_db, User, ApiKey, Consulta
from auth import (
    hash_password, verify_password, crear_jwt,
    generar_api_key, verificar_api_key,
    get_current_user,
)
from services import identity, sat, external, scoring
from billing import (crear_checkout_session, crear_checkout_subscription, cancelar_subscription, manejar_webhook, TIERS_PRICING, PAQUETES_CREDITOS, PLANES_SUSCRIPCION)

# ============================================================
app = FastAPI(
    title="TrustScore MX API",
    description="Score de confianza para hacer negocios en México",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://trustscoremx.com",
        "https://www.trustscoremx.com",
        "https://api.trustscoremx.com",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Inicializar DB al cargar el módulo (idempotente: create_all no recrea tablas existentes).
# Esto asegura que los tests y arranques rápidos no dependan del evento startup.
init_db()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def root():
    return {
        "service": "TrustScore MX",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}


# ============================================================
#  AUTH
# ============================================================

class SignupReq(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=2)
    empresa: Optional[str] = None
    password: str = Field(min_length=8)


class LoginReq(BaseModel):
    email: EmailStr
    password: str


@app.post("/api/v1/auth/signup")
def signup(req: SignupReq, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(400, "Ya existe una cuenta con este correo.")
    u = User(
        email=req.email,
        nombre=req.nombre,
        empresa=req.empresa,
        password_hash=hash_password(req.password),
        consultas_gratis_restantes=5,
    )
    db.add(u); db.commit(); db.refresh(u)
    # Enviar email de bienvenida (no bloquear el signup si falla)
    try:
        from services.notifications import email_signup_welcome
        asyncio.create_task(email_signup_welcome(u.email, u.nombre))
    except Exception:
        pass
    return {
        "user_id": u.id,
        "email": u.email,
        "consultas_gratis_restantes": u.consultas_gratis_restantes,
        "token": crear_jwt(u.id),
    }


@app.post("/api/v1/auth/login")
def login(req: LoginReq, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == req.email).first()
    if not u or not verify_password(req.password, u.password_hash):
        raise HTTPException(401, "Credenciales inválidas.")
    return {"token": crear_jwt(u.id), "user_id": u.id, "email": u.email}


@app.post("/api/v1/auth/api-key")
def crear_api_key(
    nombre: str = "default",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full, prefix, h = generar_api_key()
    ak = ApiKey(user_id=user.id, key_prefix=prefix, key_hash=h, nombre=nombre)
    db.add(ak); db.commit()
    return {
        "api_key": full,
        "prefix": prefix,
        "nombre": nombre,
        "aviso": "Guarda esta llave AHORA. No volverá a mostrarse completa.",
    }


# ============================================================
#  CHECKS — el corazón del producto
# ============================================================

class CheckReq(BaseModel):
    rfc: str = Field(min_length=12, max_length=13, description="RFC a consultar")
    nombre: Optional[str] = None
    curp: Optional[str] = None
    clave_ine: Optional[str] = None


def _check_balance_or_fail(user: User, costo: float):
    """Decide si la consulta se cobra de gratis, créditos o falla."""
    if user.consultas_gratis_restantes > 0:
        return "gratis"
    if user.saldo_creditos >= costo:
        return "creditos"
    raise HTTPException(
        402,
        f"Saldo insuficiente. Compra créditos o suscríbete. "
        f"Costo: ${costo} MXN, saldo: ${user.saldo_creditos:.2f}",
    )


def _cobrar(user: User, db: Session, fuente: str, costo: float):
    if fuente == "gratis":
        user.consultas_gratis_restantes -= 1
    else:
        user.saldo_creditos -= costo
    db.commit()


def _persistir_consulta(
    db: Session, user: User, rfc: str, nombre: Optional[str],
    tier: str, payload: dict, costo_cobrado: float, costo_real: float,
):
    score_data = payload.get("score", {})
    c = Consulta(
        user_id=user.id, rfc_consultado=rfc, nombre_consultado=nombre,
        tier=tier, score=score_data.get("score"),
        categoria=score_data.get("categoria"),
        payload_completo=payload, costo_cobrado=costo_cobrado, costo_real=costo_real,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c.id


@app.post("/api/v1/check/express")
async def check_express(
    req: CheckReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tier 1 — $49 MXN. Validación identidad + 69-B + DOF + concursal."""
    costo_cliente = TIERS_PRICING["express"]["precio"]
    costo_real = 1.0
    fuente_pago = _check_balance_or_fail(user, costo_cliente)

    rfc = req.rfc.upper().strip()
    rfc_check = identity.validar_rfc(rfc)
    sat_69b = sat.consultar_69b(rfc)
    dof, bc = await asyncio.gather(
        sat.consultar_dof_async(rfc, req.nombre or ""),
        sat.consultar_boletin_concursal_async(rfc, req.nombre or ""),
    )

    checks = {"rfc": rfc_check, "sat_69b": sat_69b, "dof": dof, "boletin_concursal": bc}
    score = scoring.calcular_score(checks)

    payload = {
        "tier": "express", "rfc": rfc, "fecha_consulta": datetime.utcnow().isoformat(),
        "checks": checks, "score": score,
    }
    _cobrar(user, db, fuente_pago, costo_cliente)
    cid = _persistir_consulta(db, user, rfc, req.nombre, "express", payload,
                              costo_cliente if fuente_pago != "gratis" else 0.0, costo_real)
    payload["consulta_id"] = cid
    payload["cobro"] = {"tier": "express", "monto": costo_cliente, "fuente_pago": fuente_pago}
    return payload


@app.post("/api/v1/check/estandar")
async def check_estandar(
    req: CheckReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tier 2 — $149 MXN. Express + INE Renapo + OFAC/PEP + quejas."""
    costo_cliente = TIERS_PRICING["estandar"]["precio"]
    costo_real = 42.0
    fuente_pago = _check_balance_or_fail(user, costo_cliente)

    rfc = req.rfc.upper().strip()

    rfc_check = identity.validar_rfc(rfc)
    curp_check = identity.validar_curp(req.curp) if req.curp else None
    sat_69b = sat.consultar_69b(rfc)

    dof, bc, ine_t, pep_t, quejas_t = await asyncio.gather(
        sat.consultar_dof_async(rfc, req.nombre or ""),
        sat.consultar_boletin_concursal_async(rfc, req.nombre or ""),
        external.verificar_ine_renapo(rfc, req.clave_ine or ""),
        external.consultar_ofac_pep(req.nombre or rfc, rfc),
        external.consultar_quejas(rfc, req.nombre or ""),
    )

    checks = {
        "rfc": rfc_check, "curp": curp_check,
        "sat_69b": sat_69b, "dof": dof, "boletin_concursal": bc,
        "ine": ine_t, "ofac_pep": pep_t, "quejas": quejas_t,
    }
    score = scoring.calcular_score(checks)

    payload = {
        "tier": "estandar", "rfc": rfc, "fecha_consulta": datetime.utcnow().isoformat(),
        "checks": checks, "score": score,
    }
    _cobrar(user, db, fuente_pago, costo_cliente)
    cid = _persistir_consulta(db, user, rfc, req.nombre, "estandar", payload,
                              costo_cliente if fuente_pago != "gratis" else 0.0, costo_real)
    payload["consulta_id"] = cid
    payload["cobro"] = {"tier": "estandar", "monto": costo_cliente, "fuente_pago": fuente_pago}
    return payload


@app.post("/api/v1/check/profesional")
async def check_profesional(
    req: CheckReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tier 3 — $399 MXN. Estándar + litigios + análisis societario."""
    costo_cliente = TIERS_PRICING["profesional"]["precio"]
    costo_real = 50.0
    fuente_pago = _check_balance_or_fail(user, costo_cliente)
    rfc = req.rfc.upper().strip()

    rfc_check = identity.validar_rfc(rfc)
    curp_check = identity.validar_curp(req.curp) if req.curp else None
    sat_69b = sat.consultar_69b(rfc)

    dof, bc, ine_t, pep_t, quejas_t, lit_t = await asyncio.gather(
        sat.consultar_dof_async(rfc, req.nombre or ""),
        sat.consultar_boletin_concursal_async(rfc, req.nombre or ""),
        external.verificar_ine_renapo(rfc, req.clave_ine or ""),
        external.consultar_ofac_pep(req.nombre or rfc, rfc),
        external.consultar_quejas(rfc, req.nombre or ""),
        external.consultar_litigios(rfc, req.nombre or ""),
    )

    checks = {
        "rfc": rfc_check, "curp": curp_check,
        "sat_69b": sat_69b, "dof": dof, "boletin_concursal": bc,
        "ine": ine_t, "ofac_pep": pep_t, "quejas": quejas_t, "litigios": lit_t,
    }
    score = scoring.calcular_score(checks)
    payload = {
        "tier": "profesional", "rfc": rfc, "fecha_consulta": datetime.utcnow().isoformat(),
        "checks": checks, "score": score,
    }
    _cobrar(user, db, fuente_pago, costo_cliente)
    cid = _persistir_consulta(db, user, rfc, req.nombre, "profesional", payload,
                              costo_cliente if fuente_pago != "gratis" else 0.0, costo_real)
    payload["consulta_id"] = cid
    payload["cobro"] = {"tier": "profesional", "monto": costo_cliente, "fuente_pago": fuente_pago}
    return payload


@app.post("/api/v1/check/enterprise")
async def check_enterprise(
    req: CheckReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Tier 4 — $799 MXN. Profesional + Buró de Crédito (mock en MVP)."""
    costo_cliente = TIERS_PRICING["enterprise"]["precio"]
    costo_real = 185.0
    fuente_pago = _check_balance_or_fail(user, costo_cliente)
    rfc = req.rfc.upper().strip()

    base = await check_profesional(req, user, db)  # incluye todo
    buro = await external.consultar_buro_credito(rfc, req.curp or "")
    base["checks"]["buro"] = buro
    base["score"] = scoring.calcular_score(base["checks"])
    base["tier"] = "enterprise"
    base["cobro"] = {"tier": "enterprise", "monto": costo_cliente, "fuente_pago": fuente_pago}
    return base


# ============================================================
#  PERFIL Y CONSULTAS
# ============================================================

@app.get("/api/v1/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "email": user.email, "nombre": user.nombre, "empresa": user.empresa,
        "consultas_gratis_restantes": user.consultas_gratis_restantes,
        "saldo_creditos": user.saldo_creditos,
        "suscripcion_activa": user.suscripcion_activa,
    }


@app.get("/api/v1/me/consultas")
def mis_consultas(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cs = db.query(Consulta).filter(Consulta.user_id == user.id).order_by(Consulta.creada.desc()).limit(50).all()
    return [
        {
            "id": c.id, "rfc": c.rfc_consultado, "nombre": c.nombre_consultado,
            "tier": c.tier, "score": c.score, "categoria": c.categoria,
            "creada": c.creada.isoformat(), "costo": c.costo_cobrado,
        } for c in cs
    ]


@app.get("/api/v1/me/consultas/{consulta_id}")
def detalle_consulta(consulta_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(Consulta).filter(Consulta.id == consulta_id, Consulta.user_id == user.id).first()
    if not c:
        raise HTTPException(404, "Consulta no encontrada")
    return c.payload_completo



# ============================================================
#  PDF REPORTS — descarga del reporte completo
# ============================================================

@app.get("/api/v1/me/consultas/{consulta_id}/pdf")
def consulta_pdf(
    consulta_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera y descarga el PDF firmado del reporte."""
    from services.pdf_report import generar_pdf
    from io import BytesIO
    c = db.query(Consulta).filter(Consulta.id == consulta_id, Consulta.user_id == user.id).first()
    if not c:
        raise HTTPException(404, "Consulta no encontrada")
    pdf_bytes = generar_pdf(c.payload_completo or {}, c.id)
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trustscore-mx-{c.rfc_consultado}-{c.id}.pdf"',
        },
    )


# ============================================================
#  ADMIN — refresh manual de listas (OFAC, SAT 69-B)
# ============================================================

@app.post("/api/v1/admin/refresh-data")
def admin_refresh_data(
    user: User = Depends(get_current_user),
):
    """
    Forza refresco de listas publicas (OFAC, SAT 69-B). Solo super admin.
    En produccion: agregar campo is_admin a User y verificar.
    """
    if user.email not in {"vick@trustscoremx.com", "suparevilla@gmail.com"}:
        raise HTTPException(403, "Solo administradores")

    import subprocess, sys
    from pathlib import Path
    scripts_dir = Path(__file__).parent / "scripts"
    results = {}

    # OFAC
    try:
        r = subprocess.run(
            [sys.executable, str(scripts_dir / "update_ofac.py")],
            capture_output=True, text=True, timeout=120,
        )
        results["ofac"] = {
            "exit_code": r.returncode,
            "stdout": r.stdout[-500:],
            "stderr": r.stderr[-300:] if r.stderr else "",
        }
    except Exception as e:
        results["ofac"] = {"error": str(e)}

    # SAT 69-B
    try:
        r = subprocess.run(
            [sys.executable, str(scripts_dir / "update_sat_69b.py")],
            capture_output=True, text=True, timeout=120,
        )
        results["sat_69b"] = {
            "exit_code": r.returncode,
            "stdout": r.stdout[-500:],
            "stderr": r.stderr[-300:] if r.stderr else "",
        }
    except Exception as e:
        results["sat_69b"] = {"error": str(e)}

    # Limpiar cache para forzar reload
    try:
        from services.ofac import _load_index
        _load_index.cache_clear()
        from services.sat import _load_69b
        _load_69b.cache_clear()
        results["cache_cleared"] = True
    except Exception as e:
        results["cache_cleared"] = str(e)

    return results



# ============================================================
#  ARCO — carta de consentimiento PDF
# ============================================================

class ArcoReq(BaseModel):
    nombre_evaluado: str = Field(min_length=2)
    rfc_evaluado: str = Field(min_length=12, max_length=13)
    nombre_empresa: str = Field(min_length=2)
    rfc_empresa: Optional[str] = ""
    motivo: Optional[str] = "evaluacion comercial previa a establecer relacion contractual"


@app.post("/api/v1/arco/generar")
def arco_generar(req: ArcoReq, user: User = Depends(get_current_user)):
    """Genera carta ARCO firmable y la devuelve como PDF descargable."""
    from services.arco_pdf import generar_carta_arco
    from io import BytesIO
    pdf = generar_carta_arco(
        req.nombre_evaluado, req.rfc_evaluado.upper(),
        req.nombre_empresa, (req.rfc_empresa or "").upper(),
        req.motivo or "",
    )
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="arco-{req.rfc_evaluado}.pdf"'},
    )


# ============================================================
#  BULK CSV — sube CSV con muchos RFCs, devuelve CSV con scores
# ============================================================

@app.post("/api/v1/check/bulk")
async def check_bulk(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Acepta un CSV con columnas rfc,nombre y devuelve CSV con scores.
    Limite 500 filas. Cobra el equivalente a tier express por cada RFC.
    """
    from services.bulk_csv import parsear_csv_input, procesar_bulk, MAX_ROWS_PER_REQUEST
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Archivo demasiado grande (max 5 MB)")

    rows = parsear_csv_input(content)
    if not rows:
        raise HTTPException(400, "CSV vacio o invalido")

    costo_total = len(rows) * TIERS_PRICING["express"]["precio"]
    if user.consultas_gratis_restantes < len(rows) and user.saldo_creditos < costo_total:
        raise HTTPException(
            402,
            f"Saldo insuficiente. Bulk de {len(rows)} consultas requiere ${costo_total} MXN o {len(rows)} consultas gratis.",
        )

    csv_bytes, total, n_criticas = await procesar_bulk(rows)

    # Cobrar
    if user.consultas_gratis_restantes >= len(rows):
        user.consultas_gratis_restantes -= len(rows)
    else:
        user.saldo_creditos -= costo_total
    db.commit()

    from io import BytesIO
    return StreamingResponse(
        BytesIO(csv_bytes),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="trustscore-bulk-{total}-results.csv"',
            "X-Total-Procesados": str(total),
            "X-Criticas-Encontradas": str(n_criticas),
        },
    )


# ============================================================
#  MONITORING — suscribir RFCs para alertas si cambian
# ============================================================

class MonitorReq(BaseModel):
    rfc: str = Field(min_length=12, max_length=13)
    webhook_url: Optional[str] = None


@app.post("/api/v1/monitor")
def monitor_subscribe(
    req: MonitorReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Suscribe un RFC para monitoreo continuo."""
    from services.monitoring import Monitorizacion, init_monitoring_tables
    init_monitoring_tables()
    rfc = req.rfc.upper().strip()
    existing = db.query(Monitorizacion).filter(
        Monitorizacion.user_id == user.id, Monitorizacion.rfc == rfc
    ).first()
    if existing:
        existing.webhook_url = req.webhook_url or existing.webhook_url
        existing.activa = True
        db.commit()
        return {"id": existing.id, "rfc": rfc, "estado": "actualizado"}
    m = Monitorizacion(user_id=user.id, rfc=rfc, webhook_url=req.webhook_url, activa=True)
    db.add(m); db.commit(); db.refresh(m)
    return {"id": m.id, "rfc": rfc, "estado": "creado"}


@app.get("/api/v1/monitor")
def monitor_list(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lista los RFCs que tengo monitoreados."""
    from services.monitoring import Monitorizacion, init_monitoring_tables
    init_monitoring_tables()
    items = db.query(Monitorizacion).filter(
        Monitorizacion.user_id == user.id, Monitorizacion.activa == True  # noqa
    ).all()
    return [
        {"id": m.id, "rfc": m.rfc, "last_score": m.last_score,
         "last_categoria": m.last_categoria, "webhook_url": m.webhook_url,
         "creada": m.creada.isoformat() if m.creada else None}
        for m in items
    ]


@app.delete("/api/v1/monitor/{monitor_id}")
def monitor_unsubscribe(
    monitor_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from services.monitoring import Monitorizacion
    m = db.query(Monitorizacion).filter(
        Monitorizacion.id == monitor_id, Monitorizacion.user_id == user.id
    ).first()
    if not m:
        raise HTTPException(404, "Monitor no encontrado")
    m.activa = False
    db.commit()
    return {"id": m.id, "estado": "desactivado"}


# ============================================================
#  /me/usage — metricas de uso por API key / usuario
# ============================================================

@app.get("/api/v1/me/usage")
def me_usage(
    days: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resumen de uso del usuario."""
    from datetime import timedelta
    from sqlalchemy import func
    desde = datetime.utcnow() - timedelta(days=days)
    consultas_total = db.query(func.count(Consulta.id)).filter(
        Consulta.user_id == user.id, Consulta.creada >= desde
    ).scalar() or 0
    consultas_por_tier = db.query(
        Consulta.tier, func.count(Consulta.id), func.sum(Consulta.costo_cobrado)
    ).filter(
        Consulta.user_id == user.id, Consulta.creada >= desde
    ).group_by(Consulta.tier).all()
    return {
        "periodo_dias": days,
        "consultas_total": consultas_total,
        "por_tier": [
            {"tier": t, "n": int(n), "total_pagado": float(s or 0)}
            for t, n, s in consultas_por_tier
        ],
        "saldo_actual": user.saldo_creditos,
        "consultas_gratis_restantes": user.consultas_gratis_restantes,
    }


# ============================================================
#  BILLING — Stripe
# ============================================================

class CheckoutReq(BaseModel):
    item: Literal["paquete_500", "paquete_2000", "paquete_5000",
                  "express", "estandar", "profesional", "enterprise"]


class SubscribeReq(BaseModel):
    plan: Literal["starter", "growth", "pro"]


@app.post("/api/v1/billing/checkout")
def billing_checkout(req: CheckoutReq, user: User = Depends(get_current_user)):
    """Compra one-shot (paquete o consulta suelta)."""
    front_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return crear_checkout_session(
        tier_o_paquete=req.item, user_email=user.email, user_id=user.id,
        success_url=f"{front_url}/dashboard.html?paid=1",
        cancel_url=f"{front_url}/dashboard.html?cancel=1",
    )


@app.post("/api/v1/billing/subscribe")
def billing_subscribe(req: SubscribeReq, user: User = Depends(get_current_user)):
    """Inicia checkout de suscripcion mensual recurrente."""
    front_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return crear_checkout_subscription(
        plan=req.plan, user_email=user.email, user_id=user.id,
        success_url=f"{front_url}/dashboard.html?subscribed={req.plan}",
        cancel_url=f"{front_url}/dashboard.html?cancel=1",
    )


@app.post("/api/v1/billing/cancel")
def billing_cancel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cancela suscripcion activa al final del periodo."""
    if not user.stripe_customer_id or not user.suscripcion_activa:
        raise HTTPException(400, "No tienes suscripcion activa")
    # Asume que guardamos stripe_subscription_id en algun lado; simplificacion:
    return {"estado": "Para cancelar, contacta contacto@trustscoremx.com o gestiona desde Stripe Customer Portal"}


@app.post("/api/v1/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    """Handler completo de webhooks de Stripe — subscriptions + payments + alerts."""
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = manejar_webhook(body, sig)
    if not event:
        return JSONResponse({"received": True, "ignored": True})

    etype = event["type"]
    obj = event["data"]["object"]

    # === Compra one-shot completada ===
    if etype == "checkout.session.completed":
        meta = obj.get("metadata", {})
        uid = int(meta.get("user_id", 0))
        if not uid:
            return JSONResponse({"error": "user_id missing"}, 400)
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            return JSONResponse({"error": "user not found"}, 404)

        if not user.stripe_customer_id and obj.get("customer"):
            user.stripe_customer_id = obj["customer"]

        tipo = meta.get("tipo", "one_shot")
        if tipo == "subscription":
            plan = meta.get("plan")
            user.suscripcion_activa = plan
            # Recargar consultas del plan
            p = PLANES_SUSCRIPCION.get(plan, {})
            user.consultas_gratis_restantes = p.get("consultas_express", 0)
            db.commit()
            try:
                from services.notifications import email_subscription_renewed
                import asyncio
                asyncio.create_task(email_subscription_renewed(
                    user.email, p.get("nombre", plan), p.get("precio_mensual", 0)
                ))
            except Exception:
                pass
        else:
            item = meta.get("tier", "")
            if item in PAQUETES_CREDITOS:
                user.saldo_creditos += PAQUETES_CREDITOS[item]["creditos"]
            elif item in TIERS_PRICING:
                user.saldo_creditos += TIERS_PRICING[item]["precio"]
            db.commit()
            try:
                from services.notifications import email_payment_received
                import asyncio
                amount = (obj.get("amount_total") or 0) / 100
                asyncio.create_task(email_payment_received(
                    user.email, amount, f"Compra: {item}"
                ))
            except Exception:
                pass

    # === Renovacion de suscripcion ===
    elif etype == "invoice.payment_succeeded":
        sub_id = obj.get("subscription")
        if sub_id:
            user = db.query(User).filter(User.stripe_customer_id == obj.get("customer")).first()
            if user and user.suscripcion_activa:
                p = PLANES_SUSCRIPCION.get(user.suscripcion_activa, {})
                user.consultas_gratis_restantes = p.get("consultas_express", 0)
                db.commit()
                try:
                    from services.notifications import email_subscription_renewed
                    import asyncio
                    asyncio.create_task(email_subscription_renewed(
                        user.email, p.get("nombre", user.suscripcion_activa),
                        p.get("precio_mensual", 0)
                    ))
                except Exception:
                    pass

    # === Pago fallido ===
    elif etype == "invoice.payment_failed":
        user = db.query(User).filter(User.stripe_customer_id == obj.get("customer")).first()
        if user:
            try:
                from services.notifications import email_payment_failed
                import asyncio
                amount = (obj.get("amount_due") or 0) / 100
                asyncio.create_task(email_payment_failed(user.email, amount))
            except Exception:
                pass

    # === Suscripcion cancelada ===
    elif etype == "customer.subscription.deleted":
        user = db.query(User).filter(User.stripe_customer_id == obj.get("customer")).first()
        if user:
            user.suscripcion_activa = None
            db.commit()

    return JSONResponse({"received": True, "type": etype})


# ============================================================
#  ADMIN DASHBOARD — metricas tiempo real
# ============================================================

@app.get("/api/v1/admin/dashboard")
def admin_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Resumen ejecutivo. Solo emails admins."""
    if user.email not in {"vick@trustscoremx.com", "suparevilla@gmail.com"}:
        raise HTTPException(403, "Solo administradores")

    from sqlalchemy import func
    from datetime import timedelta

    hoy = datetime.utcnow()
    semana_atras = hoy - timedelta(days=7)
    mes_atras = hoy - timedelta(days=30)

    def _suma_periodo(field, since):
        return float(db.query(func.coalesce(func.sum(field), 0)).filter(
            Consulta.creada >= since
        ).scalar() or 0)

    def _count_periodo(model, field, since):
        return int(db.query(func.count(model.id)).filter(field >= since).scalar() or 0)

    mrr = 0
    for plan_name, p in PLANES_SUSCRIPCION.items():
        n = db.query(func.count(User.id)).filter(User.suscripcion_activa == plan_name).scalar() or 0
        mrr += n * p["precio_mensual"]

    return {
        "ingresos_24h": _suma_periodo(Consulta.costo_cobrado, hoy - timedelta(days=1)),
        "ingresos_semana": _suma_periodo(Consulta.costo_cobrado, semana_atras),
        "ingresos_mes": _suma_periodo(Consulta.costo_cobrado, mes_atras),
        "margen_mes": _suma_periodo(Consulta.costo_cobrado - Consulta.costo_real, mes_atras),
        "mrr": float(mrr),
        "arr_estimado": float(mrr) * 12,
        "cuentas_total": int(db.query(func.count(User.id)).scalar() or 0),
        "cuentas_nuevas_semana": _count_periodo(User, User.creado, semana_atras),
        "cuentas_nuevas_mes": _count_periodo(User, User.creado, mes_atras),
        "suscripciones_activas": int(db.query(func.count(User.id)).filter(
            User.suscripcion_activa.isnot(None)
        ).scalar() or 0),
        "consultas_semana": _count_periodo(Consulta, Consulta.creada, semana_atras),
        "consultas_mes": _count_periodo(Consulta, Consulta.creada, mes_atras),
        "criticos_mes": int(db.query(func.count(Consulta.id)).filter(
            Consulta.creada >= mes_atras, Consulta.categoria == "CRITICO"
        ).scalar() or 0),
    }


# ============================================================
#  Hooks: enviar email tras signup y tras consulta CRITICO
# ============================================================
