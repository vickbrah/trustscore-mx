"""
Bulk CSV upload: cliente sube un CSV con RFCs (y opcionalmente nombres),
backend procesa cada uno, devuelve CSV con scores y categorias.

Formato esperado de entrada (con o sin header):
  rfc,nombre

Formato de salida:
  rfc,nombre,score,categoria,banderas_count,n_criticas,error
"""

import csv
import io
import asyncio
from typing import List, Dict, Any, Tuple

from . import identity, sat, scoring, external


MAX_ROWS_PER_REQUEST = 500
MAX_PARALLEL = 5


def parsear_csv_input(content: bytes) -> List[Dict[str, str]]:
    """Parsea el CSV recibido, soporta header opcional."""
    text = content.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []

    # Detectar header
    header_idx = 0
    if rows[0] and any(h.lower().strip() in ("rfc", "rfc consultado") for h in rows[0]):
        header_idx = 1

    out = []
    for r in rows[header_idx:]:
        if not r or not r[0].strip():
            continue
        out.append({
            "rfc": r[0].strip().upper(),
            "nombre": r[1].strip() if len(r) > 1 else "",
        })
    return out[:MAX_ROWS_PER_REQUEST]


async def _procesar_uno(rfc: str, nombre: str) -> Dict[str, Any]:
    """Corre tier express en un RFC y devuelve resultado simplificado."""
    try:
        rfc_check = identity.validar_rfc(rfc)
        sat_69b = sat.consultar_69b(rfc)
        dof = await sat.consultar_dof_async(rfc, nombre)
        bc = await sat.consultar_boletin_concursal_async(rfc, nombre)
        ofac = await external.consultar_ofac_pep(nombre or rfc, rfc)

        checks = {
            "rfc": rfc_check, "sat_69b": sat_69b, "dof": dof,
            "boletin_concursal": bc, "ofac_pep": ofac,
        }
        s = scoring.calcular_score(checks)
        return {
            "rfc": rfc, "nombre": nombre,
            "score": s["score"], "categoria": s["categoria"],
            "banderas_count": len(s["banderas"]),
            "n_criticas": s["n_banderas_criticas"],
            "error": "",
        }
    except Exception as e:
        return {
            "rfc": rfc, "nombre": nombre,
            "score": "", "categoria": "ERROR",
            "banderas_count": 0, "n_criticas": 0,
            "error": str(e)[:100],
        }


async def procesar_bulk(rows: List[Dict[str, str]]) -> Tuple[bytes, int, int]:
    """Procesa todas las filas en paralelo (con limite). Devuelve CSV + counts."""
    sem = asyncio.Semaphore(MAX_PARALLEL)

    async def bounded(rfc: str, nombre: str):
        async with sem:
            return await _procesar_uno(rfc, nombre)

    tasks = [bounded(r["rfc"], r["nombre"]) for r in rows]
    results = await asyncio.gather(*tasks)

    # Contar criticas
    n_criticas_total = sum(1 for r in results if r["categoria"] == "CRITICO")

    # Generar CSV de salida
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["rfc", "nombre", "score", "categoria", "banderas_count", "n_criticas", "error"])
    for r in results:
        w.writerow([r["rfc"], r["nombre"], r["score"], r["categoria"],
                    r["banderas_count"], r["n_criticas"], r["error"]])

    return out.getvalue().encode("utf-8"), len(results), n_criticas_total
