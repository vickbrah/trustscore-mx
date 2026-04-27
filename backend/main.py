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

from fastapi import FastAPI, Depends, HTTPException, status, Request
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
from billing import crear_checkout_session, manejar_webhook, TIERS_PRICING

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
#  BILLING — Stripe
# ============================================================

class CheckoutReq(BaseModel):
    item: Literal["paquete_500", "paquete_2000", "paquete_5000",
                  "express", "estandar", "profesional", "enterprise"]


@app.post("/api/v1/billing/checkout")
def billing_checkout(req: CheckoutReq, user: User = Depends(get_current_user)):
    app_url = os.getenv("APP_URL", "http://localhost:8000")
    front_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return crear_checkout_session(
        tier_o_paquete=req.item, user_email=user.email, user_id=user.id,
        success_url=f"{front_url}/dashboard.html?paid=1",
        cancel_url=f"{front_url}/dashboard.html?cancel=1",
    )


@app.post("/api/v1/billing/webhook")
async def billing_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = manejar_webhook(body, sig)
    if not event:
        return JSONResponse({"received": True, "ignored": True})

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        uid = int(s["metadata"]["user_id"])
        item = s["metadata"]["tier"]
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            return JSONResponse({"error": "user not found"}, 404)

        from billing import PAQUETES_CREDITOS
        if item in PAQUETES_CREDITOS:
            user.saldo_creditos += PAQUETES_CREDITOS[item]["creditos"]
        elif item in TIERS_PRICING:
            user.saldo_creditos += TIERS_PRICING[item]["precio"]
        db.commit()

    return JSONResponse({"received": True})
