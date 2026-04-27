"""
Generador de carta de consentimiento ARCO en PDF.

El cliente B2B genera esta carta, se la manda al Evaluado, el Evaluado la firma,
y queda como evidencia de la base legitima de tratamiento conforme a LFPDPPP.
"""

from io import BytesIO
from datetime import datetime, date

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


NAVY = HexColor("#0A2540")
BLUE = HexColor("#0070F3")
GRAY = HexColor("#6B7A90")


def generar_carta_arco(
    nombre_evaluado: str,
    rfc_evaluado: str,
    nombre_empresa_solicitante: str,
    rfc_empresa: str = "",
    motivo: str = "evaluacion comercial previa a establecer relacion contractual",
) -> bytes:
    """Genera carta de consentimiento ARCO firmable."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.2 * cm, bottomMargin=2.2 * cm,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"],
                          fontSize=11, leading=16, alignment=4,
                          textColor=HexColor("#3C4B61"))
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18,
                        textColor=NAVY, alignment=1, spaceAfter=12)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=9,
                           textColor=GRAY)

    story = []

    # Header
    story.append(Paragraph(
        '<font color="#0070F3"><b>TrustScore MX</b></font>',
        ParagraphStyle("brand", parent=styles["Title"], fontSize=14, alignment=2, textColor=BLUE),
    ))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("CARTA DE CONSENTIMIENTO PARA EL TRATAMIENTO DE DATOS PERSONALES", h1))
    story.append(Spacer(1, 4 * mm))

    # Lugar y fecha
    fecha = date.today().strftime("%d de %B de %Y")
    story.append(Paragraph(
        f'<para alignment="right">Ciudad de Mexico, a {fecha}</para>',
        body,
    ))
    story.append(Spacer(1, 8 * mm))

    # Cuerpo
    story.append(Paragraph(
        f'Por medio del presente documento, yo <b>{nombre_evaluado}</b>, '
        f'identificado con RFC <b>{rfc_evaluado}</b> (en lo sucesivo, "el Titular"), '
        f'manifiesto bajo protesta de decir verdad lo siguiente:',
        body,
    ))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        f'<b>PRIMERO.</b> Otorgo mi <b>CONSENTIMIENTO LIBRE, ESPECIFICO E INFORMADO</b> '
        f'a la empresa <b>{nombre_empresa_solicitante}</b>'
        + (f' (RFC {rfc_empresa})' if rfc_empresa else '')
        + f' (en lo sucesivo, "el Solicitante") '
        f'para que, a traves de la plataforma TrustScore MX, recabe, consulte, integre, '
        f'verifique y trate mis datos personales con la finalidad de '
        f'<b>{motivo}</b>.',
        body,
    ))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        '<b>SEGUNDO.</b> Reconozco que el Solicitante podra cruzar mi informacion con las '
        'siguientes fuentes publicas y privadas: Lista 69-B del SAT, Diario Oficial de la '
        'Federacion (DOF), Boletin Concursal del IFECOM, listas internacionales de sanciones '
        '(OFAC SDN, ONU), CONDUSEF, PROFECO, Registro Publico de Comercio, y -con mi consentimiento '
        'adicional documentado- Buro de Credito.',
        body,
    ))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        '<b>TERCERO.</b> He sido informado que puedo ejercer mis derechos de Acceso, Rectificacion, '
        'Cancelacion y Oposicion (ARCO), asi como revocar este consentimiento, conforme al Articulo '
        '32 de la Ley Federal de Proteccion de Datos Personales en Posesion de los Particulares '
        '(LFPDPPP), enviando un correo a <b>arco@trustscoremx.com</b>.',
        body,
    ))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        '<b>CUARTO.</b> Declaro haber leido y aceptado el Aviso de Privacidad de TrustScore MX, '
        'disponible en <b>trustscoremx.com/legal/privacidad.html</b>.',
        body,
    ))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(
        '<b>QUINTO.</b> El presente consentimiento tendra una vigencia de <b>doce (12) meses</b> '
        'contados a partir de la fecha de firma, salvo revocacion previa por escrito.',
        body,
    ))
    story.append(Spacer(1, 18 * mm))

    # Firma
    sign_table = Table([
        ["", ""],
        ["_______________________________", "_______________________________"],
        [Paragraph(f'<para alignment="center"><b>{nombre_evaluado}</b><br/>'
                   f'<font size="9">RFC: {rfc_evaluado}</font><br/>'
                   f'<font size="9" color="#6B7A90">Firma del Titular</font></para>',
                   styles["Normal"]),
         Paragraph('<para alignment="center"><b>Testigo</b><br/>'
                   '<font size="9">Nombre y firma</font></para>',
                   styles["Normal"])],
    ], colWidths=[8 * cm, 8 * cm])
    sign_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 20 * mm))

    # Footer legal
    story.append(Paragraph(
        '<font size="8" color="#6B7A90">Este documento constituye prueba de la base legitima '
        'para el tratamiento de datos personales conforme al Articulo 10 LFPDPPP. Conserve copia '
        'tanto el Titular como el Solicitante. Generado por TrustScore MX en colaboracion con su cliente.</font>',
        styles["Normal"],
    ))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf
