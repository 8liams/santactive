"""Génération du rapport PDF départemental avec ReportLab."""

from __future__ import annotations

import io
from datetime import date
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette Sant'active ────────────────────────────────────────────────────────
BLEU_NUIT   = colors.HexColor("#0A1938")
BLEU_ROYAL  = colors.HexColor("#1A3D8F")
ROUGE_CRIT  = colors.HexColor("#A51C30")
AMBRE       = colors.HexColor("#D97706")
VERT_FAV    = colors.HexColor("#1B5E3F")
GRIS_CLAIR  = colors.HexColor("#F3F2EC")
GRIS_BORD   = colors.HexColor("#C9C6BA")
BLANC       = colors.white
NOIR        = colors.HexColor("#0A0A0A")

W, H = A4  # 595 × 842 pts
MARGIN = 20 * mm


def _zone_color(zone: str) -> Any:
    return {
        "Critique":     ROUGE_CRIT,
        "Intermédiaire": AMBRE,
        "Favorable":    VERT_FAV,
    }.get(zone, BLEU_ROYAL)


def _fmt(val, fmt="{:.1f}", fallback="—"):
    try:
        if pd.isna(val):
            return fallback
        return fmt.format(float(val))
    except Exception:
        return fallback


def generate_department_pdf(
    r: pd.Series,
    master: pd.DataFrame,
    recos: list[dict],
) -> bytes:
    """Génère un rapport PDF pour un département et retourne les bytes."""

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"Sant'active — {r.get('Nom du département', '')}",
        author="Sant'active",
    )

    styles = getSampleStyleSheet()
    story: list = []

    dept_name   = str(r.get("Nom du département", "—"))
    region_name = str(r.get("Nom de la région", "—"))
    zone        = str(r.get("zone_short", "—"))
    score       = r.get("score_global")
    zone_col    = _zone_color(zone)

    # ── HEADER BLOC ───────────────────────────────────────────────────────────
    header_data = [[
        Paragraph(
            f'<font color="#{BLEU_NUIT.hexval()[2:]}"><b>{dept_name}</b></font>',
            ParagraphStyle("h_dept", fontName="Helvetica-Bold", fontSize=28,
                           leading=32, textColor=BLEU_NUIT),
        ),
        Paragraph(
            f'<font color="#{zone_col.hexval()[2:]}">● {zone}</font>',
            ParagraphStyle("h_zone", fontName="Helvetica-Bold", fontSize=13,
                           alignment=TA_RIGHT, textColor=zone_col),
        ),
    ]]
    header_tbl = Table(header_data, colWidths=[W - 2*MARGIN - 80, 80])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_tbl)

    story.append(Paragraph(
        f'<font color="#666666">{region_name} · Rapport généré le {date.today().strftime("%d/%m/%Y")}</font>',
        ParagraphStyle("sub", fontName="Helvetica", fontSize=10,
                       textColor=colors.HexColor("#666666"), spaceBefore=2),
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=GRIS_BORD,
                             spaceAfter=12, spaceBefore=8))

    # ── SCORE GLOBAL ──────────────────────────────────────────────────────────
    score_str = _fmt(score, "{:.1f}")
    ranked = master.dropna(subset=["score_global"]).sort_values("score_global")
    rang = int((ranked["dept"] == r["dept"]).cumsum().max()) if score else 0

    score_data = [[
        Paragraph(
            f'<b><font size="32" color="#{zone_col.hexval()[2:]}">{score_str}</font>'
            f'<font size="14" color="#666666">/100</font></b>',
            ParagraphStyle("sc", fontName="Helvetica-Bold", fontSize=32,
                           leading=36, textColor=zone_col),
        ),
        Paragraph(
            f'<font color="#666666">Score global\nRang national : {rang}/{len(ranked)}</font>',
            ParagraphStyle("sc_lbl", fontName="Helvetica", fontSize=11,
                           textColor=colors.HexColor("#666666"), leading=16),
        ),
    ]]
    score_tbl = Table(score_data, colWidths=[100, W - 2*MARGIN - 100])
    score_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLAIR),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 18),
    ]))
    story.append(score_tbl)
    story.append(Spacer(1, 10))

    # ── KPI GRID (4 indicateurs) ──────────────────────────────────────────────
    apl     = r.get("apl_median_dept")
    temps   = r.get("temps_acces_median")
    med_gen = r.get("med_gen_pour_100k")
    prix    = r.get("prix_m2_moyen")

    apl_nat  = master["apl_median_dept"].median() if "apl_median_dept" in master.columns else None
    temp_nat = master["temps_acces_median"].median() if "temps_acces_median" in master.columns else None
    med_nat  = master["med_gen_pour_100k"].median() if "med_gen_pour_100k" in master.columns else None

    def _kpi_cell(label: str, val_str: str, delta_str: str, good: bool | None) -> list:
        col = VERT_FAV if good is True else (ROUGE_CRIT if good is False else AMBRE)
        return [
            Paragraph(f'<font size="9" color="#999999">{label.upper()}</font>',
                      ParagraphStyle("kl", fontName="Helvetica", fontSize=9,
                                     textColor=colors.HexColor("#999999"))),
            Paragraph(f'<b><font size="20" color="#{col.hexval()[2:]}">{val_str}</font></b>',
                      ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=20,
                                     leading=24, textColor=col)),
            Paragraph(f'<font size="9" color="#666666">{delta_str}</font>',
                      ParagraphStyle("kd", fontName="Helvetica", fontSize=9,
                                     textColor=colors.HexColor("#666666"))),
        ]

    def _compare(val, ref):
        if val is None or ref is None or pd.isna(val) or pd.isna(ref):
            return None
        return float(val) >= float(ref)

    kpi_cols = [
        _kpi_cell("APL médecins généralistes",
                  _fmt(apl, "{:.1f}") + " /hab.",
                  f"Médiane nat. {_fmt(apl_nat, '{:.1f}')}",
                  _compare(apl, apl_nat)),
        _kpi_cell("Temps d'accès médical",
                  _fmt(temps, "{:.1f}") + " min",
                  f"Médiane nat. {_fmt(temp_nat, '{:.1f}')} min",
                  _compare(temp_nat, temps)),  # inversé : moins = mieux
        _kpi_cell("Médecins gén. / 100 000 hab.",
                  _fmt(med_gen, "{:.0f}"),
                  f"Médiane nat. {_fmt(med_nat, '{:.0f}')}",
                  _compare(med_gen, med_nat)),
        _kpi_cell("Prix immobilier médian",
                  _fmt(prix, "{:,.0f}") + " €/m²",
                  "Source DVF 2025",
                  None),
    ]

    cw = (W - 2*MARGIN) / 4
    kpi_data = [
        [Paragraph(c[0].text, c[0].style) for c in kpi_cols],
        [Paragraph(c[1].text, c[1].style) for c in kpi_cols],
        [Paragraph(c[2].text, c[2].style) for c in kpi_cols],
    ]
    kpi_tbl = Table(kpi_data, colWidths=[cw]*4)
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BLANC),
        ("BOX",           (0, 0), (-1, -1), 1, GRIS_BORD),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, GRIS_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 14))

    # ── RECOMMANDATIONS ───────────────────────────────────────────────────────
    if recos:
        story.append(Paragraph(
            "Plan d'action recommandé",
            ParagraphStyle("reco_h", fontName="Helvetica-Bold", fontSize=14,
                           textColor=BLEU_NUIT, spaceBefore=4, spaceAfter=8),
        ))

        for i, reco in enumerate(recos[:4], 1):
            badge_col = ROUGE_CRIT if i == 1 else (AMBRE if i == 2 else BLEU_ROYAL)
            reco_data = [[
                Paragraph(
                    f'<b><font color="#{badge_col.hexval()[2:]}">P{i}</font></b>',
                    ParagraphStyle("rb", fontName="Helvetica-Bold", fontSize=16,
                                   alignment=TA_CENTER, textColor=badge_col),
                ),
                [
                    Paragraph(f'<b>{reco.get("title", "")}</b>',
                              ParagraphStyle("rt", fontName="Helvetica-Bold",
                                             fontSize=11, textColor=BLEU_NUIT,
                                             spaceAfter=3)),
                    Paragraph(reco.get("prose", ""),
                              ParagraphStyle("rp", fontName="Helvetica",
                                             fontSize=9, textColor=NOIR,
                                             leading=13)),
                ],
            ]]
            reco_tbl = Table(reco_data, colWidths=[30, W - 2*MARGIN - 30])
            reco_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), GRIS_CLAIR),
                ("TOPPADDING",    (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING",   (0, 0), (-1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.5, GRIS_BORD),
            ]))
            story.append(reco_tbl)
            story.append(Spacer(1, 4))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GRIS_BORD))
    story.append(Paragraph(
        f"Sant'active · Rapport automatisé · {date.today().strftime('%d/%m/%Y')} · "
        "Sources : INSEE 2021, RPPS 2026, FINESS 2026, DVF 2025, DREES",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=8,
                       textColor=colors.HexColor("#999999"),
                       alignment=TA_CENTER, spaceBefore=6),
    ))

    doc.build(story)
    return buf.getvalue()
