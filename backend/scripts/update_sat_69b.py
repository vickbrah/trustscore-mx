"""
Descarga la Lista 69-B oficial del SAT y la guarda en backend/data/sat_69b_real.csv

URL pública del SAT (verificada):
  https://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv

El archivo se actualiza periódicamente (quincenal/mensual). Correr este script
como cron job en Render (1 vez al día es suficiente).

Uso:
    python scripts/update_sat_69b.py
"""

import csv
import io
import sys
import os
from pathlib import Path
import httpx

URL_SAT = "https://omawww.sat.gob.mx/cifras_sat/Documents/Listado_Completo_69-B.csv"
TARGET = Path(__file__).parent.parent / "data" / "sat_69b_real.csv"


def descargar() -> bytes:
    print(f"[SAT] descargando {URL_SAT} ...")
    r = httpx.get(URL_SAT, timeout=60.0, follow_redirects=True)
    r.raise_for_status()
    print(f"[SAT] {len(r.content):,} bytes recibidos")
    return r.content


def normalizar(raw: bytes) -> str:
    """El SAT publica con encoding latino; lo pasamos a UTF-8 con headers limpios."""
    text = raw.decode("latin-1", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))

    # Saltar líneas de cabecera del SAT (suelen ser 4-5 líneas de metadata antes del header real)
    header_idx = 0
    for i, row in enumerate(rows[:10]):
        joined = " ".join(row).upper()
        if "RFC" in joined and ("CONTRIBUYENTE" in joined or "NOMBRE" in joined or "RAZON" in joined):
            header_idx = i
            break

    rows = rows[header_idx:]
    print(f"[SAT] header detectado en linea {header_idx}, {len(rows)-1:,} contribuyentes en lista")

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["RFC", "RAZON_SOCIAL", "SITUACION", "FECHA_PUBLICACION", "OFICIO_GLOBAL"])

    for row in rows[1:]:
        if len(row) < 2:
            continue
        rfc = (row[0] or "").strip().upper()
        if not rfc or len(rfc) not in (12, 13):
            continue
        razon = (row[1] if len(row) > 1 else "").strip()
        situacion = (row[2] if len(row) > 2 else "").strip().upper()
        fecha = (row[3] if len(row) > 3 else "").strip()
        oficio = (row[4] if len(row) > 4 else "").strip()
        w.writerow([rfc, razon, situacion, fecha, oficio])

    return out.getvalue()


def main() -> int:
    try:
        raw = descargar()
        clean = normalizar(raw)
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(clean, encoding="utf-8")
        print(f"[SAT] guardado en {TARGET} ({TARGET.stat().st_size:,} bytes)")
        return 0
    except Exception as e:
        print(f"[SAT] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
