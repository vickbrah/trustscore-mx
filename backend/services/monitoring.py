"""
Monitoreo de RFCs: el cliente "suscribe" un RFC y recibe webhook
si su estado cambia (entra a 69-B, aparece en DOF, etc.).

Tabla `monitorizaciones`:
  id, user_id, rfc, last_score, last_categoria, webhook_url, activa, creada

Cron diario (Render) corre check_all_monitorizaciones() y dispara webhooks
cuando hay cambios.
"""

from typing import Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from datetime import datetime
import httpx

from db import Base, SessionLocal, engine


class Monitorizacion(Base):
    __tablename__ = "monitorizaciones"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rfc = Column(String, index=True, nullable=False)
    last_score = Column(Integer, nullable=True)
    last_categoria = Column(String, nullable=True)
    webhook_url = Column(String, nullable=True)
    activa = Column(Boolean, default=True)
    creada = Column(DateTime, default=datetime.utcnow)
    ultima_revision = Column(DateTime, nullable=True)


async def disparar_webhook(url: str, payload: Dict[str, Any]) -> bool:
    """Envia POST con el payload al webhook del cliente."""
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(url, json=payload, headers={"User-Agent": "TrustScoreMX-Webhook/1.0"})
            return 200 <= r.status_code < 300
    except Exception:
        return False


class UsageLog(Base):
    __tablename__ = "usage_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True)
    endpoint = Column(String, nullable=False)
    rfc = Column(String, nullable=True)
    tier = Column(String, nullable=True)
    status_code = Column(Integer, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow, index=True)


def init_monitoring_tables() -> None:
    """Crea las tablas nuevas (idempotente)."""
    Base.metadata.create_all(bind=engine)
