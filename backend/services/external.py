"""
Integraciones con APIs externas pagas.

Cada función está estructurada con:
  1) Stub funcional para el MVP (devuelve respuesta determinística para test)
  2) Comentario con la llamada REAL al provider, lista para descomentar
     cuando se obtenga el API key.

Esto permite que el dashboard, el scoring y los endpoints funcionen
end-to-end mientras se contratan los providers.
"""

import os
import hashlib
from typing import Dict, Any
import httpx


def _is_real_api_configured(env_var: str) -> bool:
    return bool(os.getenv(env_var, "").strip())


# ============================================================
#   NUBARIUM / VERIFICAMEX — Validación INE + Renapo
#   Costo: ~$25 MXN por consulta
# ============================================================

async def verificar_ine_renapo(rfc: str, clave_ine: str = "") -> Dict[str, Any]:
    if not _is_real_api_configured("NUBARIUM_API_KEY"):
        # Stub determinístico para MVP: el último dígito del hash del RFC define el resultado
        h = int(hashlib.md5(rfc.encode()).hexdigest(), 16) % 10
        return {
            "verificado": h != 7,  # ~10% falla, para mostrar la UX de errores
            "fuente": "Nubarium / Renapo (MOCK)",
            "vigencia": "vigente" if h != 7 else "no encontrado",
            "nota_mvp": "Stub — conecta NUBARIUM_API_KEY en .env para datos reales",
        }
    # === Llamada real (cuando tengas la clave) ===
    # async with httpx.AsyncClient(timeout=10.0) as client:
    #     r = await client.post(
    #         f"{os.getenv('NUBARIUM_BASE_URL')}/v1/ine/validate",
    #         headers={"Authorization": f"Bearer {os.getenv('NUBARIUM_API_KEY')}"},
    #         json={"rfc": rfc, "clave_ine": clave_ine},
    #     )
    #     return r.json()
    return {"verificado": False, "fuente": "Nubarium", "error": "no implementado en MVP"}


# ============================================================
#   TRUORA — Listas OFAC + PEP + sanciones internacionales
#   Costo: ~$8 MXN por consulta
# ============================================================

async def consultar_ofac_pep(nombre: str, rfc: str = "") -> Dict[str, Any]:
    if not _is_real_api_configured("TRUORA_API_KEY"):
        # Stub: nombres con "TRUCHO", "FANTASMA", "TIMA" quedan como hit
        hit_keywords = ["TRUCHO", "FANTASMA", "TIMA", "PUTIN", "MARO"]
        is_hit = any(kw in nombre.upper() for kw in hit_keywords)
        return {
            "coincidencias": is_hit,
            "listas": ["OFAC SDN", "ONU"] if is_hit else [],
            "categoria": "PEP" if is_hit else None,
            "fuente": "Truora Background Check (MOCK)",
            "nota_mvp": "Stub — conecta TRUORA_API_KEY para listas reales",
        }
    # === Llamada real ===
    # async with httpx.AsyncClient(timeout=15.0) as client:
    #     r = await client.post(
    #         "https://api.truora.com/v1/checks",
    #         headers={"Truora-API-Key": os.getenv("TRUORA_API_KEY")},
    #         data={"national_id": rfc, "country": "MX", "type": "person"},
    #     )
    #     return r.json()
    return {"coincidencias": False, "fuente": "Truora", "error": "no implementado"}


# ============================================================
#   CONDUSEF / PROFECO — Quejas de consumidores
#   Costo: ~$0.50 MXN (scraping propio)
# ============================================================

async def consultar_quejas(rfc: str, nombre: str = "") -> Dict[str, Any]:
    h = int(hashlib.md5((rfc + nombre).encode()).hexdigest(), 16) % 10
    quejas_count = h if h <= 3 else 0
    return {
        "condusef_quejas": quejas_count,
        "profeco_quejas": max(0, h - 5),
        "severidad": "leve" if quejas_count <= 2 else "moderada" if quejas_count <= 5 else "grave",
        "fuente": "CONDUSEF + PROFECO (scraping propio)",
        "nota_mvp": "Stub determinístico. Activa scraper periódico en producción.",
    }


# ============================================================
#   LITIGIOS judiciales (Tribunales Superiores estatales)
#   Costo: ~$3 MXN (scraping + caché)
# ============================================================

async def consultar_litigios(rfc: str, nombre: str = "") -> Dict[str, Any]:
    h = int(hashlib.md5((rfc + "lit").encode()).hexdigest(), 16) % 10
    return {
        "litigios_activos": h <= 1,  # 20% probabilidad
        "casos": [
            {"juzgado": "Civil 12 CDMX", "expediente": "452/2024", "tipo": "Mercantil"}
        ] if h <= 1 else [],
        "fuente": "Tribunales Superiores estatales (scraping)",
        "nota_mvp": "Stub. Conecta scraper TSJ por estado en producción.",
    }


# ============================================================
#   BURÓ DE CRÉDITO — vía partner SOFOM
#   Costo: ~$120 MXN por consulta
# ============================================================

async def consultar_buro_credito(rfc: str, curp: str = "") -> Dict[str, Any]:
    if not _is_real_api_configured("BURO_API_KEY"):
        h = int(hashlib.md5(rfc.encode()).hexdigest(), 16) % 1000
        score = 400 + (h % 450)  # rango 400-849, similar a Buró real
        return {
            "score_buro": score,
            "creditos_activos": h % 8,
            "creditos_atrasados": h % 3,
            "monto_endeudamiento": (h % 50) * 10000,
            "fuente": "Buró de Crédito (MOCK)",
            "nota_mvp": "Stub. Conexión real requiere SOFOM o partner autorizado por CNBV.",
            "disponible_en_mvp": False,
        }
    return {"error": "implementación real requiere contrato con Buró"}


# ============================================================
#   BELVO — Open banking (consentido)
#   Costo: ~$15 MXN
# ============================================================

async def conectar_belvo(link_id: str) -> Dict[str, Any]:
    return {
        "conectado": False,
        "nota_mvp": "Belvo se conecta en frontend con su widget. Aquí solo procesamos el link_id.",
        "fuente": "Belvo Open Banking",
    }
