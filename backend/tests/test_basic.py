"""
Tests basicos de smoke para evitar regresiones.
Correr con: pytest backend/tests/
"""

import os
import sys

# Asegurar que importa desde backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Setear DATABASE_URL para no romper si el .env no existe
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-secret")


def test_imports_all_modules():
    """Smoke test: que todos los modulos compilen e importen."""
    from services import identity, sat, scoring, external, ofac
    from services import scrapers, pdf_report, arco_pdf, bulk_csv, monitoring
    assert identity is not None
    assert sat is not None
    assert scoring is not None
    assert ofac is not None


def test_validar_rfc_persona_moral():
    from services.identity import validar_rfc
    r = validar_rfc("XAXX010101000")
    assert r["valido"] is True
    assert r["tipo"] == "rfc_generico_sat"


def test_validar_rfc_invalido():
    from services.identity import validar_rfc
    r = validar_rfc("INVALID")
    assert r["valido"] is False


def test_validar_curp():
    from services.identity import validar_curp
    r = validar_curp("GOMA800101HDFMRR04")
    # Puede ser valido o invalido segun el algoritmo, pero la funcion debe correr
    assert "valido" in r


def test_consultar_69b_sample():
    """Lookup en lista 69-B de muestra."""
    from services.sat import consultar_69b
    r = consultar_69b("EJE850101A11")
    assert r["encontrado"] is True
    assert r["situacion"] == "DEFINITIVO"


def test_consultar_69b_no_match():
    from services.sat import consultar_69b
    r = consultar_69b("XAXX010101000")
    assert r["encontrado"] is False


def test_scoring_critico_69b():
    """RFC en 69-B DEFINITIVO debe dar score CRITICO."""
    from services.scoring import calcular_score
    checks = {
        "rfc": {"valido": True},
        "sat_69b": {"encontrado": True, "situacion": "DEFINITIVO"},
    }
    s = calcular_score(checks)
    assert s["categoria"] == "CRITICO"
    assert s["score"] < 500


def test_scoring_excelente_limpio():
    from services.scoring import calcular_score
    checks = {
        "rfc": {"valido": True},
        "sat_69b": {"encontrado": False},
    }
    s = calcular_score(checks)
    assert s["score"] >= 900
    assert s["categoria"] == "EXCELENTE"


def test_pdf_report_genera_bytes():
    from services.pdf_report import generar_pdf
    payload = {
        "tier": "express", "rfc": "TEST",
        "checks": {"rfc": {"valido": True}, "sat_69b": {"encontrado": False}},
        "score": {"score": 950, "categoria": "EXCELENTE", "color": "green",
                  "recomendacion": "Procede.", "banderas": []},
    }
    pdf = generar_pdf(payload, 1)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_arco_pdf_genera_bytes():
    from services.arco_pdf import generar_carta_arco
    pdf = generar_carta_arco("Test User", "TES800101A11", "Empresa SA")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


def test_ofac_buscar_no_match_corto():
    """Query muy corta no debe matchear."""
    from services.ofac import buscar_ofac
    r = buscar_ofac("xx")
    assert r["coincidencias"] is False


def test_app_loads():
    """La app FastAPI debe cargar sin errores."""
    from main import app
    assert app is not None
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    # endpoints clave deben existir
    assert "/health" in routes
    assert "/api/v1/auth/signup" in routes
    assert "/api/v1/check/express" in routes
