"""
Sistema de notificaciones email via Resend.com (gratis hasta 100 emails/dia).

Si RESEND_API_KEY no esta configurada, los emails se LOG pero no se envian
(modo demo). Cuando configures, automaticamente empieza a enviar.

Plantillas incluidas:
  - signup_welcome
  - consulta_critica (alerta cuando cliente consulta RFC con score <400)
  - monitor_alert (RFC monitoreado cambio de status)
  - payment_received
  - payment_failed
  - subscription_renewed
  - weekly_report (a admins)
"""

import os
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
FROM_EMAIL = os.getenv("FROM_EMAIL", "TrustScore MX <noreply@trustscoremx.com>")
ADMIN_EMAILS = [
    e.strip() for e in os.getenv("ADMIN_EMAILS", "suparevilla@gmail.com").split(",") if e.strip()
]


async def enviar_email(
    to: List[str],
    subject: str,
    html: str,
    reply_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Envia email via Resend. Si no hay API key, loggea en lugar de enviar."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        logger.info("[EMAIL DEMO] To: %s | Subject: %s", to, subject)
        return {"sent": False, "reason": "RESEND_API_KEY no configurada", "demo": True}

    payload = {
        "from": FROM_EMAIL,
        "to": to,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if r.status_code in (200, 201):
            return {"sent": True, "id": r.json().get("id")}
        return {"sent": False, "status": r.status_code, "error": r.text[:200]}
    except Exception as e:
        return {"sent": False, "error": str(e)}


# ============================================================
#   PLANTILLAS HTML
# ============================================================

def _layout(content: str, footer: str = "") -> str:
    """Wrapper HTML con marca TrustScore MX."""
    return f"""
<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;background:#F6F9FC;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F6F9FC;padding:30px 0;">
<tr><td align="center">
  <table width="600" cellpadding="0" cellspacing="0" style="background:white;border-radius:14px;box-shadow:0 4px 12px rgba(10,37,64,.06);overflow:hidden;">
    <tr><td style="background:linear-gradient(135deg,#0A2540,#0070F3);padding:24px 32px;color:white;">
      <table width="100%"><tr>
        <td style="font-size:18px;font-weight:800;">TrustScore <span style="opacity:.8;">MX</span></td>
        <td align="right" style="font-size:12px;opacity:.7;">Score de confianza para Mexico</td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:32px;color:#3C4B61;font-size:15px;line-height:1.6;">
      {content}
    </td></tr>
    <tr><td style="background:#F6F9FC;padding:18px 32px;font-size:12px;color:#6B7A90;border-top:1px solid #EEF1F6;">
      {footer or 'TrustScore MX &middot; <a href="https://trustscoremx.com" style="color:#0070F3;">trustscoremx.com</a> &middot; <a href="https://trustscoremx.com/legal/privacidad.html" style="color:#0070F3;">Privacidad</a>'}
    </td></tr>
  </table>
</td></tr></table>
</body></html>
"""


async def email_signup_welcome(email: str, nombre: str) -> Dict[str, Any]:
    content = f"""
    <h2 style="color:#0A2540;margin:0 0 12px;font-size:22px;">Bienvenido, {nombre}.</h2>
    <p>Tu cuenta TrustScore MX esta activa. Tienes <strong>5 consultas Express gratis</strong> para empezar.</p>
    <p style="margin:24px 0;"><a href="https://trustscoremx.com/dashboard.html" style="display:inline-block;background:#0070F3;color:white;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:700;">Ir al dashboard</a></p>
    <p>Cualquier duda, responde a este correo y te ayudamos.</p>
    """
    return await enviar_email([email], "Bienvenido a TrustScore MX", _layout(content), reply_to="contacto@trustscoremx.com")


async def email_consulta_critica(email: str, rfc: str, score: int, motivo: str) -> Dict[str, Any]:
    content = f"""
    <h2 style="color:#E5484D;margin:0 0 12px;font-size:22px;">Alerta: bandera critica detectada</h2>
    <p>La consulta sobre <strong>{rfc}</strong> arrojo un score de <strong>{score}/1000</strong> (CRITICO).</p>
    <p style="background:#FDECEC;border-left:3px solid #E5484D;padding:12px 16px;border-radius:6px;">
      <strong>Motivo principal:</strong> {motivo}
    </p>
    <p>Te recomendamos NO proceder con esta entidad sin verificacion adicional.</p>
    <p><a href="https://trustscoremx.com/dashboard.html" style="color:#0070F3;font-weight:700;">Ver reporte completo &rarr;</a></p>
    """
    return await enviar_email([email], f"Alerta: {rfc} en lista negra", _layout(content))


async def email_monitor_alert(email: str, rfc: str, cambio_anterior: str, cambio_nuevo: str) -> Dict[str, Any]:
    content = f"""
    <h2 style="color:#F5A524;margin:0 0 12px;font-size:22px;">Cambio detectado en RFC monitoreado</h2>
    <p>El RFC <strong>{rfc}</strong> que tienes monitoreado cambio de status.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr><td style="padding:8px 12px;background:#F6F9FC;font-weight:700;width:120px;">Antes:</td><td style="padding:8px 12px;">{cambio_anterior}</td></tr>
      <tr><td style="padding:8px 12px;background:#F6F9FC;font-weight:700;">Ahora:</td><td style="padding:8px 12px;color:#E5484D;font-weight:700;">{cambio_nuevo}</td></tr>
    </table>
    <p><a href="https://trustscoremx.com/dashboard.html" style="color:#0070F3;font-weight:700;">Ver detalles &rarr;</a></p>
    """
    return await enviar_email([email], f"Monitor: cambio en {rfc}", _layout(content))


async def email_payment_received(email: str, monto: float, descripcion: str) -> Dict[str, Any]:
    content = f"""
    <h2 style="color:#00A36C;margin:0 0 12px;font-size:22px;">Pago recibido. Gracias.</h2>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr><td style="padding:10px 12px;background:#F6F9FC;font-weight:700;width:140px;">Monto:</td><td style="padding:10px 12px;font-size:18px;color:#0A2540;font-weight:700;">${monto:.2f} MXN</td></tr>
      <tr><td style="padding:10px 12px;background:#F6F9FC;font-weight:700;">Concepto:</td><td style="padding:10px 12px;">{descripcion}</td></tr>
    </table>
    <p>Tu factura llegara en proximos minutos via Stripe.</p>
    """
    return await enviar_email([email], "Pago confirmado - TrustScore MX", _layout(content))


async def email_payment_failed(email: str, monto: float) -> Dict[str, Any]:
    content = f"""
    <h2 style="color:#E5484D;margin:0 0 12px;font-size:22px;">No pudimos procesar tu pago</h2>
    <p>Intentamos cobrar <strong>${monto:.2f} MXN</strong> pero el cargo fue rechazado.</p>
    <p>Tu cuenta seguira activa durante 7 dias. Si no actualizas tu metodo de pago antes, sera suspendida automaticamente.</p>
    <p style="margin:24px 0;"><a href="https://trustscoremx.com/dashboard.html" style="display:inline-block;background:#E5484D;color:white;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:700;">Actualizar metodo de pago</a></p>
    """
    return await enviar_email([email], "ACCION REQUERIDA: Pago rechazado", _layout(content))


async def email_subscription_renewed(email: str, plan: str, monto: float) -> Dict[str, Any]:
    content = f"""
    <h2 style="color:#0070F3;margin:0 0 12px;font-size:22px;">Tu suscripcion {plan} se renovo</h2>
    <p>Cobramos <strong>${monto:.2f} MXN</strong> por tu plan {plan}. Tu acceso esta activo por 30 dias mas.</p>
    """
    return await enviar_email([email], f"Suscripcion {plan} renovada", _layout(content))


async def email_weekly_report_admin(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Reporte semanal a los admins (Vick + Romi)."""
    content = f"""
    <h2 style="color:#0A2540;margin:0 0 12px;font-size:22px;">Reporte semanal TrustScore MX</h2>
    <p style="color:#6B7A90;font-size:13px;">Periodo: ultimos 7 dias</p>

    <table style="width:100%;border-collapse:collapse;margin:18px 0;">
      <tr><td colspan="2" style="background:#0A2540;color:white;padding:10px 14px;font-weight:700;">INGRESOS</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;width:55%;">Ingresos cobrados (semana)</td><td style="padding:10px 14px;font-weight:700;font-size:18px;color:#00A36C;">${metrics.get('ingresos_semana', 0):,.2f} MXN</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">MRR (recurring)</td><td style="padding:10px 14px;font-weight:700;">${metrics.get('mrr', 0):,.2f} MXN</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">Margen bruto estimado</td><td style="padding:10px 14px;font-weight:700;color:#00A36C;">${metrics.get('margen_semana', 0):,.2f} MXN</td></tr>
    </table>

    <table style="width:100%;border-collapse:collapse;margin:18px 0;">
      <tr><td colspan="2" style="background:#0070F3;color:white;padding:10px 14px;font-weight:700;">USUARIOS</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;width:55%;">Cuentas nuevas</td><td style="padding:10px 14px;font-weight:700;">{metrics.get('cuentas_nuevas', 0)}</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">Cuentas activas (con consultas en semana)</td><td style="padding:10px 14px;font-weight:700;">{metrics.get('cuentas_activas', 0)}</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">Suscripciones activas</td><td style="padding:10px 14px;font-weight:700;">{metrics.get('suscripciones_activas', 0)}</td></tr>
    </table>

    <table style="width:100%;border-collapse:collapse;margin:18px 0;">
      <tr><td colspan="2" style="background:#F5A524;color:white;padding:10px 14px;font-weight:700;">CONSULTAS</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;width:55%;">Total consultas (semana)</td><td style="padding:10px 14px;font-weight:700;">{metrics.get('consultas_semana', 0)}</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">Por tier Express</td><td style="padding:10px 14px;">{metrics.get('por_tier', {}).get('express', 0)}</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">Por tier Estandar</td><td style="padding:10px 14px;">{metrics.get('por_tier', {}).get('estandar', 0)}</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">Por tier Profesional+</td><td style="padding:10px 14px;">{metrics.get('por_tier', {}).get('profesional', 0) + metrics.get('por_tier', {}).get('enterprise', 0)}</td></tr>
      <tr><td style="padding:10px 14px;background:#F6F9FC;">RFCs criticos detectados</td><td style="padding:10px 14px;color:#E5484D;font-weight:700;">{metrics.get('criticos_detectados', 0)}</td></tr>
    </table>

    <p style="margin-top:24px;font-size:13px;color:#6B7A90;">
      Saldo de Stripe disponible para retirar: <a href="https://dashboard.stripe.com/balance" style="color:#0070F3;">verificar en Stripe Dashboard</a>
    </p>
    """
    return await enviar_email(ADMIN_EMAILS, "TrustScore MX semanal", _layout(content))
