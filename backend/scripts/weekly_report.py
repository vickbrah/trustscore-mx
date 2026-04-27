"""
Cron semanal: calcula metricas de la ultima semana y envia email a admins.
Se ejecuta cada lunes 09:00 UTC (3am CDMX).

Uso:
    python scripts/weekly_report.py
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Asegurar que el dir backend este en el path
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))


async def main() -> int:
    from sqlalchemy import func
    from db import SessionLocal, User, Consulta
    from services.notifications import email_weekly_report_admin
    from billing import PLANES_SUSCRIPCION

    desde = datetime.utcnow() - timedelta(days=7)
    db = SessionLocal()
    try:
        ingresos_semana = db.query(func.coalesce(func.sum(Consulta.costo_cobrado), 0)).filter(
            Consulta.creada >= desde
        ).scalar() or 0

        margen_semana = db.query(
            func.coalesce(func.sum(Consulta.costo_cobrado - Consulta.costo_real), 0)
        ).filter(Consulta.creada >= desde).scalar() or 0

        cuentas_nuevas = db.query(func.count(User.id)).filter(
            User.creado >= desde
        ).scalar() or 0

        cuentas_activas = db.query(func.count(func.distinct(Consulta.user_id))).filter(
            Consulta.creada >= desde
        ).scalar() or 0

        suscripciones_activas = db.query(func.count(User.id)).filter(
            User.suscripcion_activa.isnot(None)
        ).scalar() or 0

        # MRR estimado
        mrr = 0
        for plan_name in ["starter", "growth", "pro"]:
            n = db.query(func.count(User.id)).filter(
                User.suscripcion_activa == plan_name
            ).scalar() or 0
            mrr += n * PLANES_SUSCRIPCION[plan_name]["precio_mensual"]

        consultas_semana = db.query(func.count(Consulta.id)).filter(
            Consulta.creada >= desde
        ).scalar() or 0

        por_tier_rows = db.query(Consulta.tier, func.count(Consulta.id)).filter(
            Consulta.creada >= desde
        ).group_by(Consulta.tier).all()
        por_tier = {tier: int(n) for tier, n in por_tier_rows}

        criticos = db.query(func.count(Consulta.id)).filter(
            Consulta.creada >= desde, Consulta.categoria == "CRITICO"
        ).scalar() or 0

        metrics = {
            "ingresos_semana": float(ingresos_semana),
            "mrr": float(mrr),
            "margen_semana": float(margen_semana),
            "cuentas_nuevas": int(cuentas_nuevas),
            "cuentas_activas": int(cuentas_activas),
            "suscripciones_activas": int(suscripciones_activas),
            "consultas_semana": int(consultas_semana),
            "por_tier": por_tier,
            "criticos_detectados": int(criticos),
        }
        print("Metrics:", metrics)
        result = await email_weekly_report_admin(metrics)
        print("Email result:", result)
        return 0 if result.get("sent") or result.get("demo") else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
