"""Integración con Stripe — checkout sessions + webhooks."""

import os
from typing import Optional
import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Catálogo de productos. En producción se mapea a price IDs reales de Stripe.
TIERS_PRICING = {
    "express":     {"precio": 49,  "nombre": "Consulta Express"},
    "estandar":    {"precio": 149, "nombre": "Consulta Estándar"},
    "profesional": {"precio": 399, "nombre": "Consulta Profesional"},
    "enterprise":  {"precio": 799, "nombre": "Consulta Enterprise"},
}

PAQUETES_CREDITOS = {
    "paquete_500":   {"precio": 500,   "creditos": 600,   "bonus_pct": 20},
    "paquete_2000":  {"precio": 2000,  "creditos": 2600,  "bonus_pct": 30},
    "paquete_5000":  {"precio": 5000,  "creditos": 7000,  "bonus_pct": 40},
}


def crear_checkout_session(
    *,
    tier_o_paquete: str,
    user_email: str,
    user_id: int,
    success_url: str,
    cancel_url: str,
) -> dict:
    """Crea una sesión de checkout en Stripe y devuelve la URL para redirigir."""
    if not stripe.api_key:
        # Modo demo: regresa una URL falsa para que el flujo del frontend siga vivo
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
        item = {"precio": p["precio"], "nombre": f"Paquete de {p['creditos']} créditos"}
    else:
        raise ValueError(f"Tier desconocido: {tier_o_paquete}")

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "mxn",
                "product_data": {"name": item["nombre"]},
                "unit_amount": int(item["precio"] * 100),  # cents
            },
            "quantity": 1,
        }],
        customer_email=user_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user_id), "tier": tier_o_paquete},
    )
    return {"url": session.url, "session_id": session.id}


def manejar_webhook(payload: bytes, sig: str) -> Optional[dict]:
    """Verifica firma del webhook y devuelve el evento parseado."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        return None
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
        return event
    except Exception:
        return None
