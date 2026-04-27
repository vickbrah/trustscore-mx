"""
Descarga la OFAC SDN list (Specially Designated Nationals) del Departamento del
Tesoro de USA y la guarda en backend/data/ofac_sdn.csv.

URL publica oficial:
  https://www.treasury.gov/ofac/downloads/sdn.csv

Formato del CSV (sin header):
  ID, NAME, TITLE, COUNTRY, SDN_TYPE, PROGRAM, ALIAS, ADDRESS, CITY,
  COUNTRY_ADDR, REMARKS, COMMENTS

Uso:
    python scripts/update_ofac.py
"""

import csv
import io
import sys
from pathlib import Path
import httpx

URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
TARGET = Path(__file__).parent.parent / "data" / "ofac_sdn.csv"

HEADERS = [
    "id", "name", "title", "country", "sdn_type", "program",
    "alias", "address", "city", "country_addr", "remarks", "comments",
]


def main() -> int:
    print(f"[OFAC] descargando {URL} ...")
    try:
        r = httpx.get(URL, timeout=60.0, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        print(f"[OFAC] ERROR descargando: {e}", file=sys.stderr)
        return 1
    print(f"[OFAC] {len(r.content):,} bytes recibidos")

    text = r.content.decode("latin-1", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    print(f"[OFAC] {len(rows):,} entries en SDN list")

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([h.upper() for h in HEADERS])
    for row in rows:
        if len(row) >= 2:
            padded = row + [""] * (len(HEADERS) - len(row))
            w.writerow(padded[: len(HEADERS)])

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(out.getvalue(), encoding="utf-8")
    print(f"[OFAC] guardado en {TARGET} ({TARGET.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
