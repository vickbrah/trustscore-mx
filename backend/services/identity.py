"""
Validación de identidad mexicana (RFC, CURP, INE).

Implementación REAL del algoritmo de homoclave del SAT y validación
estructural de CURP. La validación contra Renapo (foto + biométrico)
requiere API paga (NubariumIA / Verificamex) y se conecta en external.py.
"""

import re
from datetime import datetime
from typing import Dict, Any

# === RFC ===

RFC_PERSONA_FISICA_RE = re.compile(r"^[A-ZÑ&]{4}[0-9]{6}[A-Z0-9]{3}$")
RFC_PERSONA_MORAL_RE = re.compile(r"^[A-ZÑ&]{3}[0-9]{6}[A-Z0-9]{3}$")
RFC_BLACKLIST_4 = {
    "BUEI", "BUEY", "CACA", "CACO", "CAGA", "CAGO", "CAKA", "CAKO",
    "COGE", "COJA", "COJE", "COJI", "COJO", "CULO", "FETO", "GUEY",
    "JOTO", "KACA", "KACO", "KAGA", "KAGO", "KOGE", "KOJO", "KAKA",
    "KULO", "MAME", "MAMO", "MEAR", "MEAS", "MEON", "MIAR", "MION",
    "MOCO", "MULA", "PEDA", "PEDO", "PENE", "PUTA", "PUTO", "QULO",
    "RATA", "RUIN",
}

# RFC genéricos oficiales (publicados por el SAT, no siguen el algoritmo de homoclave)
RFC_GENERICOS = {
    "XAXX010101000",  # Operaciones con público en general (extranjeros)
    "XEXX010101000",  # Residentes en el extranjero
}

# Tabla de valores para homoclave RFC
_HOMOCLAVE_TABLE = {
    "0": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16, "H": 17,
    "I": 18, "J": 19, "K": 20, "L": 21, "M": 22, "N": 23, "&": 24, "O": 25,
    "P": 26, "Q": 27, "R": 28, "S": 29, "T": 30, "U": 31, "V": 32, "W": 33,
    "X": 34, "Y": 35, "Z": 36, " ": 37, "Ñ": 38,
}


def validar_rfc(rfc: str) -> Dict[str, Any]:
    """
    Valida estructura del RFC mexicano y verifica el dígito verificador (homoclave).
    Retorna dict con los detalles del análisis.
    """
    rfc = (rfc or "").upper().strip().replace("-", "")
    result: Dict[str, Any] = {
        "rfc": rfc,
        "valido": False,
        "tipo": None,
        "fecha_constitucion": None,
        "homoclave_correcta": None,
        "es_palabra_inconveniente": False,
        "errores": [],
    }

    if not rfc:
        result["errores"].append("RFC vacío")
        return result

    # Atajo: RFCs genéricos oficiales del SAT se aceptan sin validar homoclave
    if rfc in RFC_GENERICOS:
        result["valido"] = True
        result["tipo"] = "rfc_generico_sat"
        result["homoclave_correcta"] = True
        return result

    if RFC_PERSONA_MORAL_RE.match(rfc) and len(rfc) == 12:
        result["tipo"] = "persona_moral"
    elif RFC_PERSONA_FISICA_RE.match(rfc) and len(rfc) == 13:
        result["tipo"] = "persona_fisica"
        if rfc[:4] in RFC_BLACKLIST_4:
            result["es_palabra_inconveniente"] = True
            result["errores"].append(
                f"Las primeras 4 letras '{rfc[:4]}' son palabra inconveniente "
                "(el SAT no asigna RFC con estas iniciales)"
            )
    else:
        result["errores"].append("Formato de RFC no válido")
        return result

    # Validar fecha
    fecha_str = rfc[-9:-3] if result["tipo"] == "persona_fisica" else rfc[-9:-3]
    try:
        yy = int(fecha_str[0:2])
        mm = int(fecha_str[2:4])
        dd = int(fecha_str[4:6])
        # Asumimos siglo: 00-29 -> 2000s, 30-99 -> 1900s
        year = 2000 + yy if yy <= 29 else 1900 + yy
        fecha = datetime(year, mm, dd)
        if fecha > datetime.now():
            result["errores"].append("Fecha del RFC en el futuro")
        result["fecha_constitucion"] = fecha.strftime("%Y-%m-%d")
    except ValueError:
        result["errores"].append(f"Fecha inválida en RFC: {fecha_str}")
        return result

    # Validar homoclave (último dígito)
    homoclave_calculada = _calcular_homoclave(rfc)
    homoclave_real = rfc[-1]
    result["homoclave_correcta"] = homoclave_calculada == homoclave_real
    if not result["homoclave_correcta"]:
        result["errores"].append(
            f"Dígito verificador no coincide (esperado {homoclave_calculada}, "
            f"recibido {homoclave_real})"
        )

    result["valido"] = (
        len(result["errores"]) == 0
        and result["homoclave_correcta"]
        and not result["es_palabra_inconveniente"]
    )
    return result


def _calcular_homoclave(rfc: str) -> str:
    """Calcula el dígito verificador del RFC usando el algoritmo oficial del SAT."""
    base = rfc[:-1]
    # Padding para 12 chars en persona moral (3 letras) -> agregar espacio al inicio
    if len(base) == 11:  # persona moral: 3 letras + 6 dígitos + 2 homoclave parciales
        base = " " + base
    suma = 0
    for i, ch in enumerate(base):
        valor = _HOMOCLAVE_TABLE.get(ch, 0)
        suma += valor * (13 - i)
    residuo = suma % 11
    if residuo == 0:
        return "0"
    if residuo == 10:
        return "A"
    return str(11 - residuo)


# === CURP ===

CURP_RE = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])"
    r"[HM](AS|BC|BS|CC|CL|CM|CS|CH|DF|DG|GT|GR|HG|JC|MC|MN|MS|NT|NL|"
    r"OC|PL|QT|QR|SP|SL|SR|TC|TS|TL|VZ|YN|ZS|NE)"
    r"[B-DF-HJ-NP-TV-Z]{3}[0-9A-Z][0-9]$"
)


def validar_curp(curp: str) -> Dict[str, Any]:
    """Valida estructura de la CURP mexicana."""
    curp = (curp or "").upper().strip()
    result: Dict[str, Any] = {
        "curp": curp,
        "valido": False,
        "fecha_nacimiento": None,
        "sexo": None,
        "estado": None,
        "errores": [],
    }
    if not CURP_RE.match(curp):
        result["errores"].append("Formato de CURP no válido")
        return result

    yy = int(curp[4:6])
    mm = int(curp[6:8])
    dd = int(curp[8:10])
    siglo_char = curp[16]
    year = 2000 + yy if siglo_char.isdigit() else 1900 + yy
    try:
        result["fecha_nacimiento"] = datetime(year, mm, dd).strftime("%Y-%m-%d")
    except ValueError:
        result["errores"].append("Fecha inválida en CURP")
        return result

    result["sexo"] = "Hombre" if curp[10] == "H" else "Mujer"
    result["estado"] = curp[11:13]
    result["valido"] = True
    return result


# === INE ===

# Clave de elector: 18 caractere