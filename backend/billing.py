"""Integracion Stripe — subscriptions recurrentes + payments + webhooks."""

import os
from typing import Optional, Dict, Any
import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Productos one-shot (consulta suelta)
TIERS_PRICING = {
    "express":     {"precio": 49,  "nombre": "Consulta Express"},
    "estandar":    {"precio": 149, "nombre": "Consulta Estandar"},
    "profesional": {"precio": 399, "nombre": "Consulta Profesional"},
    "enterprise":  {"precio": 799, "nombre": "Consulta Enterprise"},
}

# Paquetes prepagados de creditos
PAQUETES_CREDITOS = {
    "paquete_500":   {"precio": 500,   "creditos": 600,   "bonus_pct": 20},
    "paquete_2000":  {"precio": 2000,  "creditos": 2600,  "bonus_pct": 30},
    "paquete_5000":  {"precio": 5000,  "creditos": 7000,  "bonus_pct": 40},
}

# Suscripciones recurrentes (esto es donde esta el negocio real)
PLANES_SUSCRIPCION = {
    "starter": {
        "precio_mensual": 499,
        "nombre": "Plan Starter",
        "consultas_express": 15,
        "descripcion": "15 consultas Express al mes",
    },
    "growth": {
        "precio_mensual": 1999,
        "nombre": "Plan Growth",
        "consultas_express": 30,
        "consultas_estandar": 20,
        "descripcion": "30 Express + 20 Estandar al mes",
    },
    "pro": {
        "precio_mensual": 4999,
        "nombre": "Plan Pro",
        "consultas_express": 100,
        "consultas_estandar": 50,
        "consultas_profesional": 20,
        "descripcion": "100 Express + 50 Estandar + 20 Profesional al mes",
    },
}


def crear_checkout_session(
    *,
    tier_o_paquete: str,
    user_email: str,
    user_id: int,
    success_url: str,
    cancel_url: str,
) -> dict:
    """Checkout one-shot (paquete o consulta suelta)."""
    if not stripe.api_key:
        return {
            "demo_mode": True,
            "url": f"{success_url}?demo=1&tier={tier_o_paquete}",
            "session_id": "cs_demo_" + tier_o_paquete,
            "nota": "Stripe no configurado. Configura STRIPE_SECRET_KEY en .env.",
        }

    if tier_o_paquete in TIERS_PRICING:
        item = TIERS_PRICING[tier_o_paquete]
    elif tier_o_paquete in PAQUETES_CREDITOS:
        p = PAQUETES_CREDITOS[tier_o_paquete]
        item = {"precio": p["precio"], "nombre": f"Paquete de {p['creditos']} creditos"}
    else:
        raise ValueError(f"Tier desconocido: {tier_o_paquete}")

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "mxn",
                "product_data": {"name": item["nombre"]},
                "unit_amount": int(item["precio"] * 100),
            },
            "quantity": 1,
        }],
        customer_email=user_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user_id), "tier": tier_o_paquete, "tipo": "one_shot"},
    )
    return {"url": session.url, "session_id": session.id}


def crear_checkout_subscription(
    *,
    plan: str,
    user_email: str,
    user_id: int,
    success_url: str,
    cancel_url: str,
) -> dict:
    """Checkout recurrente (suscripcion mensual)."""
    if plan not in PLANES_SUSCRIPCION:
        raise ValueError(f"Plan desconocido: {plan}")

    p = PLANES_SUSCRIPCION[plan]

    if not stripe.api_key:
        return {
            "demo_mode": True,
            "url": f"{success_url}?demo=1&plan={plan}",
            "session_id": "sub_demo_" + plan,
            "nota": "Stripe no configurado.",
        }

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{
            "price_data": {
                "currency": "mxn",
                "product_data": {"name": p["nombre"], "description": p["descripcion"]},
                "unit_amount": int(p["precio_mensual"] * 100),
                "recurring": {"interval": "month"},
            },
            "quantity": 1,
        }],
        customer_email=user_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user_id), "plan": plan, "tipo": "subscription"},
        subscription_data={"metadata": {"user_id": str(user_id), "plan": plan}},
    )
    return {"url": session.url, "session_id": session.id}


def cancelar_subscription(stripe_subscription_id: str) -> dict:
    """Cancela al final del periodo actual (no inmediato)."""
    if not stripe.api_key:
        return {"demo": True, "estado": "cancelada (demo)"}
    s = stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)
    return {"id": s.id, "cancelara_el": s.current_period_end, "estado": "se cancelara al final del periodo"}


def manejar_webhook(payload: bytes, sig: str) -> Optional[Dict[str, Any]]:
    """Verifica firma del webhook y devuelve el evento parseado."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        return None
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
        return event
    except Exception:
        return None
