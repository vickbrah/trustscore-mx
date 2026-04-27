"""
Lookup en la lista OFAC SDN (Specially Designated Nationals).

Descarga gratis y oficial del Departamento del Tesoro de USA. Si el archivo
local existe, se usa (~5MB indexado en memoria). Si no, devuelve resultado
vacio sin fallar el endpoint.

Para refrescarlo correr: python scripts/update_ofac.py
"""

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, List

DATA_PATH = Path(__file__).parent.parent / "data" / "ofac_sdn.csv"


def _normalize(s: str) -> str:
    """Quita acentos, lowercase, deja solo letras y espacios."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@lru_cache(maxsize=1)
def _load_index() -> List[Dict[str, str]]:
    """Carga la lista en memoria."""
    if not DATA_PATH.exists():
        return []
    out = []
    with open(DATA_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append({
                "id": row.get("ID", "").strip(),
                "name": row.get("NAME", "").strip().strip('"'),
                "name_norm": _normalize(row.get("NAME", "").strip().strip('"')),
                "country": row.get("COUNTRY", "").strip().strip('"'),
                "sdn_type": row.get("SDN_TYPE", "").strip(),
                "program": row.get("PROGRAM", "").strip(),
                "alias": row.get("ALIAS", "").strip().strip('"'),
                "remarks": row.get("REMARKS", "").strip().strip('"'),
            })
    return out


def buscar_ofac(nombre: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Busca por nombre en la lista OFAC SDN. Retorna coincidencias.
    Hace match por contencion (todas las palabras del query aparecen en el target).
    """
    if not nombre or len(nombre.strip()) < 3:
        return {"coincidencias": False, "matches": [], "fuente": "OFAC SDN"}

    q = _normalize(nombre)
    q_words = [w for w in q.split() if len(w) >= 3]
    if not q_words:
        return {"coincidencias": False, "matches": [], "fuente": "OFAC SDN"}

    index = _load_index()
    if not index:
        return {
            "coincidencias": False,
            "matches": [],
            "fuente": "OFAC SDN",
            "nota": "Lista local no descargada. Correr scripts/update_ofac.py",
        }

    matches = []
    for entry in index:
        target = entry["name_norm"]
        if all(w in target for w in q_words):
            matches.append({
                "id": entry["id"],
                "name": entry["name"],
                "country": entry["country"],
                "sdn_type": entry["sdn_type"],
                "program": entry["program"],
                "alias": entry["alias"][:120] if entry["alias"] else "",
            })
            if len(matches) >= max_results:
                break

    return {
        "coincidencias": bool(matches),
        "matches": matches,
        "total_index": len(index),
        "fuente": "OFAC SDN List (US Treasury)",
        "url_oficial": "https://www.treasury.gov/ofac/downloads/sdn.csv",
    }
