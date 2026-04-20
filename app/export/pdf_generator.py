"""Génère un rapport PDF A4 d'un département.

Deux backends supportés, dans l'ordre :
    1. WeasyPrint (HTML → PDF, rendu le plus fidèle au design).
       Nécessite Pango/Cairo (`brew install pango cairo libffi` sur macOS).
    2. ReportLab (fallback pur-Python, toujours disponible).
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd

from ..config import PALETTE


# ─── Utilitaires ──────────────────────────────────────────────────────────────
def _fig_to_png(fig, width: int = 700, height: int = 400) -> bytes:
    """Rend une figure Plotly en PNG via kaleido."""
    return fig.to_image(format="png", width=width, height=height, scale=2)


def _safe(v, spec: str = ".1f", suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        return format(v, spec) + suffix
    except Exception:
        return f"{v}{suffix}"


# ─── Backend WeasyPrint (si dispo) ────────────────────────────────────────────
def _generate_weasyprint(dept_row, gauge_fig, radar_fig) -> bytes:
    import base64
    from weasyprint import HTML

    gauge_b64 = base64.b64encode(_fig_to_png(gauge_fig, 600, 300)).decode()
    radar_b64 = base64.b64encode(_fig_to_png(radar_fig, 700, 400)).decode()
    today = date.today().strftime("%d/%m/%Y")

    html = f"""
    <html><head><meta charset="utf-8"><style>
        @page {{ size: A4; margin: 2cm; }}
        body {{ font-family: 'Helvetica', sans-serif; color: {PALETTE['gris_texte']}; }}
        .header {{ background: {PALETTE['bleu_regalien']}; color: white;
                   padding: 1.5rem; border-bottom: 4px solid {PALETTE['ambre_alerte']}; }}
        h1 {{ margin: 0; font-size: 20pt; font-weight: 700; }}
        .meta {{ font-size: 9pt; color: {PALETTE['gris_secondaire']};
                 margin: 0.5rem 0 1.5rem; }}
        .section {{ margin: 1rem 0; page-break-inside: avoid; }}
        .section h2 {{ font-size: 13pt; border-bottom: 2px solid {PALETTE['bleu_regalien']};
                       padding-bottom: 4px; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
        .kpi {{ border: 1px solid {PALETTE['gris_bordure']};
                padding: 12px; border-radius: 4px; }}
        .kpi-label {{ font-size: 8pt; color: {PALETTE['gris_secondaire']};
                      text-transform: uppercase; }}
        .kpi-value {{ font-size: 18pt; font-weight: 300; color: {PALETTE['bleu_regalien']}; }}
        .badge {{ display: inline-block; padding: 2px 10px; border-radius: 4px;
                  font-size: 10pt; font-weight: 500; }}
        img {{ max-width: 100%; }}
        .footer {{ position: fixed; bottom: 0; font-size: 8pt;
                   color: {PALETTE['gris_secondaire']}; width: 100%; text-align: center; }}
    </style></head><body>
        <div class="header">
            <h1>Rapport Santé &amp; Territoires</h1>
            <div>{dept_row.get('Nom du département', '')} ({dept_row.get('dept', '')})
                — {dept_row.get('Nom de la région', '')}</div>
        </div>
        <div class="meta">Rapport généré le {today}</div>

        <div class="section">
            <h2>Synthèse</h2>
            <p>Score global : <b>{_safe(dept_row.get('score_global'))}/100</b>
               — Zone <b>{dept_row.get('zone_short', '—')}</b></p>
            <img src="data:image/png;base64,{gauge_b64}" />
        </div>

        <div class="section">
            <h2>Indicateurs clés</h2>
            <div class="kpi-grid">
                <div class="kpi"><div class="kpi-label">Médecins gén. / 100k</div>
                     <div class="kpi-value">{_safe(dept_row.get('med_gen_pour_100k'), '.0f')}</div></div>
                <div class="kpi"><div class="kpi-label">Temps d'accès médian</div>
                     <div class="kpi-value">{_safe(dept_row.get('temps_acces_median'))} min</div></div>
                <div class="kpi"><div class="kpi-label">Prix médian m²</div>
                     <div class="kpi-value">{_safe(dept_row.get('prix_m2_moyen'), '.0f')} €</div></div>
                <div class="kpi"><div class="kpi-label">Structures / 100k</div>
                     <div class="kpi-value">{_safe(dept_row.get('structures_pour_100k'))}</div></div>
                <div class="kpi"><div class="kpi-label">Part des 65+</div>
                     <div class="kpi-value">{_safe(dept_row.get('pct_plus_65'))}%</div></div>
                <div class="kpi"><div class="kpi-label">Score environnemental</div>
                     <div class="kpi-value">{_safe(dept_row.get('enviro_score'))}/20</div></div>
            </div>
        </div>

        <div class="section">
            <h2>Profil détaillé</h2>
            <img src="data:image/png;base64,{radar_b64}" />
        </div>

        <div class="footer">
            Dashboard Santé &amp; Territoires · Sources : INSEE 2021 · RPPS janv. 2026 ·
            FINESS mars 2026 · DVF 2025 · ANSM · CNAM 2023
        </div>
    </body></html>
    """
    return HTML(string=html).write_pdf()


# ─── Backend ReportLab (fallback pur-Python) ──────────────────────────────────
def _generate_reportlab(dept_row, gauge_fig, radar_fig) -> bytes:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    COL_REGALIEN = HexColor(PALETTE["bleu_regalien"])
    COL_AMBRE    = HexColor(PALETTE["ambre_alerte"])
    COL_GRIS_TXT = HexColor(PALETTE["gris_texte"])
    COL_GRIS_SEC = HexColor(PALETTE["gris_secondaire"])
    COL_GRIS_BOR = HexColor(PALETTE["gris_bordure"])
    COL_GRIS_FND = HexColor(PALETTE["gris_fond"])
    COL_BLANC    = HexColor(PALETTE["blanc"])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.5 * cm, bottomMargin=2 * cm,
        title="Rapport Santé & Territoires",
    )

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle("t", parent=styles["Heading1"],
                             fontSize=18, leading=22, textColor=COL_BLANC,
                             fontName="Helvetica-Bold")
    s_sub   = ParagraphStyle("sub", parent=styles["Normal"],
                             fontSize=10, textColor=COL_BLANC,
                             fontName="Helvetica")
    s_h2    = ParagraphStyle("h2", parent=styles["Heading2"],
                             fontSize=13, leading=16, textColor=COL_GRIS_TXT,
                             spaceBefore=12, spaceAfter=6,
                             fontName="Helvetica-Bold")
    s_body  = ParagraphStyle("b", parent=styles["Normal"],
                             fontSize=10, leading=14, textColor=COL_GRIS_TXT,
                             fontName="Helvetica")
    s_meta  = ParagraphStyle("m", parent=styles["Normal"],
                             fontSize=8, textColor=COL_GRIS_SEC,
                             fontName="Helvetica")
    s_kpi_lbl = ParagraphStyle("kl", parent=styles["Normal"],
                               fontSize=7, leading=9, textColor=COL_GRIS_SEC,
                               fontName="Helvetica-Bold")
    s_kpi_val = ParagraphStyle("kv", parent=styles["Normal"],
                               fontSize=16, leading=19, textColor=COL_REGALIEN,
                               fontName="Helvetica")

    story: list = []

    # Header block (badge + sous-titre)
    header_data = [[
        Paragraph("Rapport Santé &amp; Territoires", s_title),
    ], [
        Paragraph(
            f"{dept_row.get('Nom du département', '')} "
            f"({dept_row.get('dept', '')}) — "
            f"{dept_row.get('Nom de la région', '')}",
            s_sub),
    ]]
    header = Table(header_data, colWidths=[doc.width])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COL_REGALIEN),
        ("LINEBELOW",  (0, -1), (-1, -1), 3, COL_AMBRE),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"Rapport généré le {date.today().strftime('%d/%m/%Y')}",
                           s_meta))
    story.append(Spacer(1, 12))

    # Synthèse
    story.append(Paragraph("Synthèse", s_h2))
    score_val = _safe(dept_row.get("score_global"))
    zone_val  = dept_row.get("zone_short", "—")
    story.append(Paragraph(
        f"Score global : <b>{score_val}/100</b> — Zone <b>{zone_val}</b>", s_body))
    story.append(Spacer(1, 6))
    try:
        gauge_png = _fig_to_png(gauge_fig, 600, 280)
        story.append(Image(io.BytesIO(gauge_png), width=doc.width, height=9 * cm))
    except Exception:
        story.append(Paragraph("<i>(Jauge non disponible)</i>", s_meta))
    story.append(Spacer(1, 12))

    # KPI grid (3 colonnes × 2 lignes)
    story.append(Paragraph("Indicateurs clés", s_h2))
    kpis = [
        ("Médecins gén. / 100k",      _safe(dept_row.get("med_gen_pour_100k"), ".0f")),
        ("Temps d'accès médian",      _safe(dept_row.get("temps_acces_median")) + " min"),
        ("Prix médian m²",            _safe(dept_row.get("prix_m2_moyen"), ".0f") + " €"),
        ("Structures / 100k",         _safe(dept_row.get("structures_pour_100k"))),
        ("Part des 65+",              _safe(dept_row.get("pct_plus_65")) + " %"),
        ("Score environnemental",     _safe(dept_row.get("enviro_score")) + "/20"),
    ]
    kpi_cells = []
    row = []
    for i, (lbl, val) in enumerate(kpis):
        cell = [Paragraph(lbl.upper(), s_kpi_lbl),
                Spacer(1, 3),
                Paragraph(val, s_kpi_val)]
        row.append(cell)
        if (i + 1) % 3 == 0:
            kpi_cells.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append("")
        kpi_cells.append(row)

    col_w = (doc.width - 12) / 3
    kpi_tbl = Table(kpi_cells, colWidths=[col_w] * 3)
    kpi_tbl.setStyle(TableStyle([
        ("BOX",        (0, 0), (-1, -1), 0.5, COL_GRIS_BOR),
        ("INNERGRID",  (0, 0), (-1, -1), 0.5, COL_GRIS_BOR),
        ("BACKGROUND", (0, 0), (-1, -1), COL_BLANC),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 12))

    # Profil détaillé (radar)
    story.append(Paragraph("Profil détaillé", s_h2))
    try:
        radar_png = _fig_to_png(radar_fig, 700, 400)
        story.append(Image(io.BytesIO(radar_png), width=doc.width, height=11 * cm))
    except Exception:
        story.append(Paragraph("<i>(Radar non disponible)</i>", s_meta))

    # Footer sur chaque page
    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(COL_GRIS_SEC)
        canvas.drawCentredString(
            A4[0] / 2, 1 * cm,
            "Dashboard Santé & Territoires · Sources : INSEE 2021 · "
            "RPPS janv. 2026 · FINESS mars 2026 · DVF 2025 · ANSM · CNAM 2023",
        )
        canvas.drawRightString(A4[0] - 2 * cm, 0.6 * cm,
                               f"Page {_doc.page}")
        canvas.setFillColor(COL_GRIS_FND)  # évite un warning reportlab unused
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ─── API publique ─────────────────────────────────────────────────────────────
def generate_dept_report(dept_row, master, patho, pros, gauge_fig, radar_fig) -> bytes:
    """Génère un PDF A4 pour le département donné.

    Tente WeasyPrint, tombe sur ReportLab si les libs système (pango/cairo)
    ne sont pas présentes.
    """
    try:
        return _generate_weasyprint(dept_row, gauge_fig, radar_fig)
    except Exception:
        return _generate_reportlab(dept_row, gauge_fig, radar_fig)
