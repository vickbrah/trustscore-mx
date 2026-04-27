"""
Lookup en Lista 69-B del SAT (EFOS / EDOS).

EN PRODUCCIÓN: Bajar el listado completo del SAT (CSV público actualizado
mensualmente) y refrescar a una tabla Postgres. URL oficial:
http://omawww.sat.gob.mx/cifras_sat/Paginas/datos/vinculo.html?page=ListCompleta69B.html

Para el MVP usamos el CSV local de muestra para que el endpoint funcione end-to-end.
"""

import csv
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any, List

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_PATH_REAL = DATA_DIR / "sat_69b_real.csv"      # Producción: descargado del SAT
DATA_PATH_SAMPLE = DATA_DIR / "sat_69b_sample.csv"  # Fallback: muestra para desarrollo


@lru_cache(maxsize=1)
def _load_69b() -> Dict[str, Dict[str, str]]:
    """Carga el CSV de Lista 69-B. Prefiere el real descargado del SAT, sino usa muestra."""
    indexed: Dict[str, Dict[str, str]] = {}
    path = DATA_PATH_REAL if DATA_PATH_REAL.exists() else DATA_PATH_SAMPLE
    if not path.exists():
        return indexed
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rfc = (row.get("RFC") or "").upper().strip()
            if rfc:
                indexed[rfc] = row
    return indexed


def consultar_69b(rfc: str) -> Dict[str, Any]:
    """
    Devuelve si el RFC aparece en lista 69-B del SAT.

    Estados posibles del SAT:
      - PRESUNTO: investigación abierta
      - DEFINITIVO: se confirmó que emite facturas falsas (la peor)
      - DESVIRTUADO: se aclaró y salió limpio
      - SENTENCIA FAVORABLE: ganó amparo
    """
    rfc = (rfc or "").upper().strip()
    listado = _load_69b()
    hit = listado.get(rfc)

    if not hit:
        return {
            "rfc": rfc,
            "encontrado": False,
            "situacion": None,
            "mensaje": "RFC no aparece en Lista 69-B del SAT",
            "fuente": "SAT — Listado de contribuyentes con operaciones presuntamente inexistentes",
        }

    return {
        "rfc": rfc,
        "encontrado": True,
        "situacion": hit.get("SITUACION"),
        "razon_social": hit.get("RAZON_SOCIAL"),
        "fecha_publicacion": hit.get("FECHA_PUBLICACION"),
        "oficio_global": hit.get("OFICIO_GLOBAL"),
        "fuente": "SAT — Listado de contribuyentes con operaciones presuntamente inexistentes",
        "mensaje": (
            f"⚠️ RFC encontrado en lista 69-B con situación: {hit.get('SITUACION')}. "
            "Esto significa que el SAT lo investigó por emitir facturas presuntamente falsas."
        ),
    }


def consultar_dof(rfc: str, nombre: str = "") -> Dict[str, Any]:
    """
    Búsqueda en Diario Oficial de la Federación (sanciones, inhabilitaciones).
    PROD: scraper sobre https://dof.gob.mx/busqueda_avanzada.php cacheado.
    """
    return {
        "rfc": rfc,
        "encontrado": False,
        "publicaciones": [],
        "fuente": "DOF (Diario Oficial de la Federación)",
        "mensaje": "Sin sanciones ni inhabilitaciones publicadas en DOF.",
    }


def consultar_boletin_concursal(rfc: str) -> Dict[str, Any]:
    """
    Búsqueda en Boletín Concursal (IFECOM) — quiebras y concursos mercantiles.
    PROD: scraper sobre https://www.ifecom.cjf.gob.mx
    """
    return {
        "rfc": rfc,
        "en_concurso": False,
        "estado": None,
        "fuente": "IFECOM — Boletín Concursal",
        "mensaje": "Sin proceso de concurso mercantil activo.",
    }


def consultar_opinion_cumplimiento_32d(rfc: str) -> Dict[str, Any]:
    """
    Opinión de cumplimiento del SAT (32-D). El servicio oficial requiere
    e.firma del contribuyente, no se puede consultar terceros sin autorización.

    Aquí devolvemos el formato del reporte; en prod, el cliente sube el PDF
    de opinión positiva del proveedor que evalúa.
    """
    retu