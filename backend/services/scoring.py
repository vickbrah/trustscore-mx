"""
Algoritmo de scoring TrustScore MX (0-1000).

Empezamos en 1000 y restamos puntos por cada bandera roja, ponderada
por severidad. La idea: un score auditable, explicable y defendible.

Categorias:
  900-1000 -> EXCELENTE  (verde fuerte)
  750-899  -> CONFIABLE  (verde)
  600-749  -> ACEPTABLE  (amarillo)
  400-599  -> RIESGOSO   (naranja)
  0-399    -> CRITICO    (rojo)
"""

from typing import Dict, Any, List


PESOS = {
    "rfc_invalido": 200,
    "homoclave_incorrecta": 100,
    "ine_no_verificable": 80,
    "sat_69b_definitivo": 600,
    "sat_69b_presunto": 350,
    "sat_69b_desvirtuado": 50,
    "ofac_pep_hit": 400,
    "boletin_concursal_activo": 250,
    "litigio_activo": 80,
    "queja_condusef_grave": 100,
    "queja_condusef_moderada": 40,
    "queja_condusef_leve": 10,
    "buro_score_bajo": 100,
    "buro_atrasos": 50,
}


def calcular_score(checks: Dict[str, Any]) -> Dict[str, Any]:
    """Recibe el dict de checks y devuelve score, categoria, banderas y recomendacion."""
    score = 1000
    banderas: List[Dict[str, str]] = []

    rfc_check = checks.get("rfc", {})
    if not rfc_check.get("valido"):
        score -= PESOS["rfc_invalido"]
        banderas.append({
            "tipo": "identidad", "severidad": "alta",
            "mensaje": "RFC no valido estructuralmente",
        })
    elif rfc_check.get("homoclave_correcta") is False:
        score -= PESOS["homoclave_incorrecta"]
        banderas.append({
            "tipo": "identidad", "severidad": "media",
            "mensaje": "Digito verificador del RFC no coincide",
        })

    ine_check = checks.get("ine", {})
    if ine_check.get("verificado") is False:
        score -= PESOS["ine_no_verificable"]
        banderas.append({
            "tipo": "identidad", "severidad": "media",
            "mensaje": "Identidad INE no verificable contra Renapo",
        })

    sat_69b = checks.get("sat_69b", {})
    if sat_69b.get("encontrado"):
        situacion = (sat_69b.get("situacion") or "").upper()
        if situacion == "DEFINITIVO":
            score -= PESOS["sat_69b_definitivo"]
            banderas.append({
                "tipo": "fiscal", "severidad": "critica",
                "mensaje": "RFC en Lista 69-B SAT con situacion DEFINITIVO (facturas falsas confirmadas)",
            })
        elif situacion == "PRESUNTO":
            score -= PESOS["sat_69b_presunto"]
            banderas.append({
                "tipo": "fiscal", "severidad": "alta",
                "mensaje": "RFC en Lista 69-B SAT como PRESUNTO (investigacion abierta)",
            })
        elif situacion == "DESVIRTUADO":
            score -= PESOS["sat_69b_desvirtuado"]
            banderas.append({
                "tipo": "fiscal", "severidad": "baja",
                "mensaje": "RFC aparecio en 69-B pero situacion DESVIRTUADO (se aclaro)",
            })

    pep = checks.get("ofac_pep", {})
    if pep.get("coincidencias"):
        score -= PESOS["ofac_pep_hit"]
        banderas.append({
            "tipo": "compliance", "severidad": "critica",
            "mensaje": "Coincidencia en listas " + ", ".join(pep.get("listas", [])),
        })

    bc = checks.get("boletin_concursal", {})
    if bc.get("en_concurso"):
        score -= PESOS["boletin_concursal_activo"]
        banderas.append({
            "tipo": "financiero", "severidad": "alta",
            "mensaje": "Concurso mercantil activo en IFECOM",
        })

    lit = checks.get("litigios", {})
    casos = lit.get("casos", [])
    if lit.get("litigios_activos") and casos:
        score -= min(PESOS["litigio_activo"] * len(casos), 200)
        banderas.append({
            "tipo": "legal", "severidad": "media",
            "mensaje": str(len(casos)) + " litigio(s) judicial(es) activo(s)",
        })

    quejas = checks.get("quejas", {})
    sev = (quejas.get("severidad") or "").lower()
    n_q = quejas.get("condusef_quejas", 0) + quejas.get("profeco_quejas", 0)
    if sev == "grave":
        score -= PESOS["queja_condusef_grave"]
        banderas.append({"tipo": "reputacional", "severidad": "alta",
                         "mensaje": str(n_q) + " quejas graves CONDUSEF/PROFECO"})
    elif sev == "moderada":
        score -= PESOS["queja_condusef_moderada"]
        banderas.append({"tipo": "reputacional", "severidad": "media",
                         "mensaje": str(n_q) + " quejas moderadas"})
    elif sev == "leve" and n_q > 0:
        score -= PESOS["queja_condusef_leve"]

    # Buro: aplicamos si hay datos en el reporte (mock o real)
    buro = checks.get("buro") or {}
    if "score_buro" in buro:
        score_buro = buro.get("score_buro", 800)
        if score_buro < 600:
            score -= PESOS["buro_score_bajo"]
            banderas.append({"tipo": "financiero", "severidad": "alta",
                             "mensaje": "Score Buro bajo (" + str(score_buro) + ")"})
        atrasos = buro.get("creditos_atrasados", 0)
        if atrasos > 0:
            score -= min(PESOS["buro_atrasos"] * atrasos, 150)
            banderas.append({"tipo": "financiero", "severidad": "media",
                             "mensaje": str(atrasos) + " credito(s) en atraso"})

    score = max(0, min(1000, score))
    categoria, color, recomendacion = _categorizar(score, banderas)

    return {
        "score": score,
        "categoria": categoria,
        "color": color,
        "recomendacion": recomendacion,
        "banderas": banderas,
        "n_banderas_criticas": sum(1 for b in banderas if b["severidad"] == "critica"),
        "n_banderas_altas": sum(1 for b in banderas if b["severidad"] == "alta"),
    }


def _categorizar(score: int, banderas: list) -> tuple:
    tiene_critica = any(b["severidad"] == "critica" for b in banderas)
    if tiene_critica:
        return ("CRITICO", "red",
                "NO PROCEDER. Hay banderas criticas (lista negra/sanciones). "
                "Operar con esta entidad expone a sanciones legales y fiscales.")
    if score >= 900:
        return ("EXCELENTE", "green",
                "Procede con tranquilidad. Perfil limpio y verificable.")
    if score >= 750:
        return ("CONFIABLE", "green",
                "Procede con confianza. Sin banderas relevantes; vigilancia rutinaria.")
    if score >= 600:
        return ("ACEPTABLE", "amber",
                "Procede con cautela. Hay senales menores; pide referencias adicionales o limita exposicion.")
    if score >= 400:
        return ("RIESGOSO", "orange",
                "Alto riesgo. Solicita garantias, anticipo reducido o pago contra entrega.")
    return ("CRITICO", "red",
            "NO PROCEDER. Score muy bajo con multiples banderas. Buscar otro proveedor o contraparte.")
