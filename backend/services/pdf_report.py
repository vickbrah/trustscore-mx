"""
Generador de reportes PDF de TrustScore MX.
Usa reportlab (puro Python, sin deps de sistema).

Cada reporte incluye:
  - Header con marca
  - Datos del evaluado
  - Score con gauge visual
  - Tabla de checks con semaforo
  - Banderas detectadas
  - Recomendacion final
  - Footer con timestamp y consulta_id (auditable)
"""

from io import BytesIO
from datetime import datetime
from typing import Dict, Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.pdfgen import canvas


NAVY = HexColor("#0A2540")
BLUE = HexColor("#0070F3")
GREEN = HexColor("#00A36C")
AMBER = HexColor("#F5A524")
ORANGE = HexColor("#FF7A00")
RED = HexColor("#E5484D")
GRAY = HexColor("#6B7A90")
LIGHT_GRAY = HexColor("#F6F9FC")


def _color_for_category(cat: str):
    cat = (cat or "").upper()
    if cat == "EXCELENTE":
        return GREEN
    if cat == "CONFIABLE":
        return GREEN
    if cat == "ACEPTABLE":
        return AMBER
    if cat == "RIESGOSO":
        return ORANGE
    return RED


def generar_pdf(payload: Dict[str, Any], consulta_id: int) -> bytes:
    """Genera el PDF y devuelve los bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = []

    # === Header ===
    story.append(Paragraph(
        '<font color="#0070F3"><b>TrustScore MX</b></font>'
        '   <font color="#6B7A90" size="9">Reporte de confianza</font>',
        ParagraphStyle("Header", parent=styles["Title"], fontSize=22, leading=26),
    ))
    story.append(Spacer(1, 4 * mm))

    # === Datos del evaluado ===
    score_data = payload.get("score", {})
    rfc = payload.get("rfc", "")
    tier = payload.get("tier", "express").upper()
    fecha = payload.get("fecha_consulta", datetime.utcnow().isoformat())[:19].replace("T", " ")
    score = score_data.get("score", 0)
    cat = score_data.get("categoria", "—")
    color = _color_for_category(cat)
    recom = score_data.get("recomendacion", "")
    banderas = score_data.get("banderas", [])

    info_table = Table([
        ["RFC consultado", rfc],
        ["Tier", tier],
        ["Fecha", fecha],
        ["Consulta ID", str(consulta_id)],
    ], colWidths=[4.5 * cm, 11 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, HexColor("#EEF1F6")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8 * mm))

    # === Score grande ===
    score_table = Table([
        [
            Paragraph(
                f'<font size="48" color="{color.hexval()}"><b>{score}</b></font><br/>'
                f'<font size="11" color="#6B7A90">de 1000</font>',
                styles["Normal"],
            ),
            Paragraph(
                f'<font size="9" color="#6B7A90">CATEGORIA</font><br/>'
                f'<font size="20" color="{color.hexval()}"><b>{cat}</b></font><br/>'
                f'<font size="10" color="#3C4B61">{recom}</font>',
                styles["Normal"],
            ),
        ]
    ], colWidths=[5 * cm, 10.5 * cm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("BOX", (0, 0), (-1, -1), 1, HexColor("#DCE2EC")),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 8 * mm))

    # === Checks ===
    story.append(Paragraph(
        '<font color="#0A2540"><b>Verificaciones realizadas</b></font>',
        ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14),
    ))
    story.append(Spacer(1, 3 * mm))
    checks = payload.get("checks", {})
    rows = [["Fuente", "Resultado", "Estado"]]

    sat = checks.get("sat_69b") or {}
    if sat.get("encontrado"):
        rows.append(["SAT Lista 69-B", f'En lista: {sat.get("situacion")}', "RIESGO"])
    else:
        rows.append(["SAT Lista 69-B", "No aparece en lista", "OK"])

    rfc_c = checks.get("rfc") or {}
    rows.append(["Identidad RFC", "Valido" if rfc_c.get("valido") else "Estructura invalida",
                 "OK" if rfc_c.get("valido") else "ALERTA"])

    pep = checks.get("ofac_pep") or {}
    if pep.get("coincidencias"):
        names = [m.get("name", "") for m in pep.get("matches", [])][:2]
        rows.append(["OFAC SDN / Sanciones", f"COINCIDENCIA: {', '.join(names)[:60]}", "RIESGO"])
    else:
        rows.append(["OFAC SDN / Sanciones", "Sin coincidencias", "OK"])

    bc = checks.get("boletin_concursal") or {}
    rows.append([
        "Boletin Concursal IFECOM",
        "Concurso activo" if bc.get("en_concurso") else "Sin concurso",
        "RIESGO" if bc.get("en_concurso") else "OK",
    ])

    dof = checks.get("dof") or {}
    rows.append([
        "DOF (sanciones, inhabilitaciones)",
        f'{len(dof.get("publicaciones", []))} publicaciones' if dof.get("encontrado") else "Sin publicaciones",
        "ALERTA" if dof.get("encontrado") else "OK",
    ])

    if "ine" in checks and checks["ine"]:
        rows.append([
            "INE / Renapo",
            "Verificado" if checks["ine"].get("verificado") else "No verificable",
            "OK" if checks["ine"].get("verificado") else "ALERTA",
        ])

    if "buro" in checks and checks["buro"]:
        b = checks["buro"]
        rows.append([
            "Buro de Credito",
            f'Score {b.get("score_buro", "—")} · {b.get("creditos_atrasados", 0)} atrasos',
            "OK" if b.get("score_buro", 0) > 700 else "ALERTA",
        ])

    checks_table = Table(rows, colWidths=[6 * cm, 7 * cm, 2.5 * cm])
    checks_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#DCE2EC")),
    ]))
    # Color por estado
    for i, row in enumerate(rows[1:], start=1):
        st = row[2]
        col = GREEN if st == "OK" else AMBER if st == "ALERTA" else RED
        checks_table.setStyle(TableStyle([("TEXTCOLOR", (2, i), (2, i), col)]))
    story.append(checks_table)
    story.append(Spacer(1, 8 * mm))

    # === Banderas ===
    if banderas:
        story.append(Paragraph(
            '<font color="#0A2540"><b>Banderas detectadas</b></font>',
            ParagraphStyle("h2", parent=styles["Heading2"], fontSize=14),
        ))
        story.append(Spacer(1, 3 * mm))
        for b in banderas:
            sev = b.get("severidad", "media").upper()
            sev_col = "#E5484D" if sev == "CRITICA" else "#F5A524" if sev == "MEDIA" else "#6B7A90"
            story.append(Paragraph(
                f'<font color="{sev_col}"><b>[{sev}]</b></font> '
                f'<font color="#3C4B61">{b.get("mensaje", "")}</font>',
                ParagraphStyle("bandera", parent=styles["BodyText"], fontSize=10, leftIndent=6),
            ))
            story.append(Spacer(1, 1 * mm))

    # === Footer ===
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        f'<font color="#6B7A90" size="8">'
        f'Reporte generado por TrustScore MX · trustscoremx.com · '
        f'Consulta {consulta_id} · {fecha} UTC<br/>'
        f'Este reporte es confidencial. Su uso debe limitarse al fin legitimo de negocio que lo origino. '
        f'Cumplimiento LFPDPPP. Para mas informacion: contacto@trustscoremx.com'
        f'</font>',
        styles["Normal"],
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
