"""Génération du rapport PDF départemental avec ReportLab — v2."""

from __future__ import annotations

import io
from datetime import date
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette Sant'active ────────────────────────────────────────────────────────
BLEU_NUIT  = colors.HexColor("#0A1938")
BLEU_ROYAL = colors.HexColor("#1A3D8F")
ROUGE_CRIT = colors.HexColor("#A51C30")
AMBRE      = colors.HexColor("#D97706")
VERT_FAV   = colors.HexColor("#1B5E3F")
GRIS_CLAIR = colors.HexColor("#F3F2EC")
GRIS_BORD  = colors.HexColor("#C9C6BA")
BLANC      = colors.white
NOIR       = colors.HexColor("#0A0A0A")
GRIS_TXT   = colors.HexColor("#4A4A4A")
GRIS_SEC   = colors.HexColor("#999999")

W, H = A4
MARGIN    = 20 * mm
CONTENT_W = W - 2 * MARGIN


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _zone_color(zone: str) -> Any:
    return {"Critique": ROUGE_CRIT, "Intermédiaire": AMBRE, "Favorable": VERT_FAV}.get(zone, BLEU_ROYAL)


def _zone_soft(zone: str) -> Any:
    return {
        "Critique":      colors.HexColor("#FBEEF0"),
        "Intermédiaire": colors.HexColor("#FEF4DC"),
        "Favorable":     colors.HexColor("#E3EFE8"),
    }.get(zone, GRIS_CLAIR)


def _fmt(val, fmt="{:.1f}", fallback="—"):
    try:
        if pd.isna(val):
            return fallback
        return fmt.format(float(val))
    except Exception:
        return fallback


def _compare(val, ref) -> bool | None:
    try:
        if pd.isna(val) or pd.isna(ref):
            return None
        return float(val) >= float(ref)
    except Exception:
        return None


def _s(name: str, **kwargs) -> ParagraphStyle:
    defaults = {"fontName": "Helvetica", "fontSize": 10, "textColor": NOIR, "leading": 14}
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


def _hex(c: Any) -> str:
    return c.hexval()[2:]


# ─── Section heading ──────────────────────────────────────────────────────────
def _section_heading(title: str, story: list) -> None:
    story.append(Spacer(1, 12))
    tbl = Table([[
        Paragraph(
            f'<font color="#{_hex(ROUGE_CRIT)}" size="11">▌</font>'
            f'  <b><font size="11" color="#{_hex(BLEU_NUIT)}">{title.upper()}</font></b>',
            _s("sh", fontName="Helvetica-Bold", fontSize=11, textColor=BLEU_NUIT, leading=14),
        )
    ]], colWidths=[CONTENT_W])
    tbl.setStyle(TableStyle([
        ("LINEBELOW",     (0, 0), (-1, -1), 1,  GRIS_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8))


# ─── Footer/header callbacks ──────────────────────────────────────────────────
def _page_cb(dept_name: str):
    def _cb(canvas, doc):
        canvas.saveState()

        # ── Running header (pages 2+) ─────────────────────────────────────────
        if doc.page > 1:
            canvas.setFillColor(BLEU_NUIT)
            canvas.rect(0, H - 8 * mm, W, 8 * mm, fill=1, stroke=0)
            canvas.setFont("Helvetica-Bold", 7.5)
            canvas.setFillColor(BLANC)
            canvas.drawString(MARGIN, H - 5.5 * mm, f"SANT'ACTIVE  ·  {dept_name.upper()}")
            canvas.drawRightString(W - MARGIN, H - 5.5 * mm, date.today().strftime("%d/%m/%Y"))

        # ── Footer ────────────────────────────────────────────────────────────
        canvas.setStrokeColor(GRIS_BORD)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 14 * mm, W - MARGIN, 14 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GRIS_SEC)
        canvas.drawString(MARGIN, 11 * mm, f"Sant'active · Rapport confidentiel · {dept_name}")
        canvas.drawCentredString(
            W / 2, 8 * mm,
            "Sources : INSEE 2021 · RPPS 2026 · FINESS 2026 · DVF 2025 · DREES · ANCT 2023",
        )
        canvas.drawRightString(W - MARGIN, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return _cb


# ─── Main ─────────────────────────────────────────────────────────────────────
def generate_department_pdf(
    r: pd.Series,
    master: pd.DataFrame,
    recos: list[dict],
    data: dict | None = None,
) -> bytes:
    """Génère un rapport PDF A4 complet pour un département."""

    buf        = io.BytesIO()
    dept_name  = str(r.get("Nom du département", "—"))
    dept_code  = str(r.get("dept", "")).zfill(2)
    region     = str(r.get("Nom de la région", "—"))
    zone       = str(r.get("zone_short", "—"))
    score      = r.get("score_global")
    zone_col   = _zone_color(zone)
    zone_bg    = _zone_soft(zone)

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 4 * mm,
        bottomMargin=18 * mm,
        title=f"Sant'active — {dept_name}",
        author="Sant'active",
    )

    story: list = []

    # ── ① BANDEAU COUVERTURE ──────────────────────────────────────────────────
    cov = Table([[
        Paragraph(
            '<font color="white" size="9"><b>SANT\'ACTIVE</b></font>'
            '<font color="white" size="8">  ·  Observatoire Santé Territorial</font>',
            _s("cov_l", fontName="Helvetica-Bold", fontSize=9, textColor=BLANC),
        ),
        Paragraph(
            f'<font color="white" size="8">Rapport confidentiel · {date.today().strftime("%d %B %Y")}</font>',
            _s("cov_r", fontName="Helvetica", fontSize=8, alignment=TA_RIGHT, textColor=BLANC),
        ),
    ]], colWidths=[CONTENT_W * 0.65, CONTENT_W * 0.35])
    cov.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BLEU_NUIT),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(cov)
    story.append(Spacer(1, 16))

    # ── ② TITRE DÉPARTEMENT ───────────────────────────────────────────────────
    story.append(Paragraph(
        f'<b><font size="30" color="#{_hex(BLEU_NUIT)}">{dept_name}</font></b>'
        f'<font size="16" color="#999999">  ·  {dept_code}</font>',
        _s("dept_title", fontName="Helvetica-Bold", fontSize=30, textColor=BLEU_NUIT, leading=34),
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f'<font size="11" color="#666666">{region}</font>',
        _s("sub", fontName="Helvetica", fontSize=11, textColor=colors.HexColor("#666666")),
    ))
    story.append(Spacer(1, 12))

    # ── ③ SCORE GLOBAL + ZONE ─────────────────────────────────────────────────
    ranked    = master.dropna(subset=["score_global"]).sort_values("score_global")
    rang      = int((ranked["dept"] == r["dept"]).cumsum().max()) if score else 0
    score_str = _fmt(score, "{:.1f}")
    total     = len(ranked)

    score_block = Table([[
        Paragraph(
            f'<b><font size="40" color="#{_hex(zone_col)}">{score_str}</font>'
            f'<font size="14" color="#999999">/100</font></b>',
            _s("sc_big", fontName="Helvetica-Bold", fontSize=40, textColor=zone_col, leading=44),
        ),
        [
            Paragraph(
                f'<b><font size="13" color="#{_hex(zone_col)}">● {zone}</font></b>',
                _s("zb", fontName="Helvetica-Bold", fontSize=13, alignment=TA_RIGHT, textColor=zone_col),
            ),
            Spacer(1, 6),
            Paragraph(
                '<font size="10" color="#444444">Score global de santé territoriale</font>',
                _s("zl", fontName="Helvetica", fontSize=10, alignment=TA_RIGHT,
                   textColor=colors.HexColor("#444444")),
            ),
            Paragraph(
                f'<font size="9" color="#999999">Rang national : {rang} / {total}</font>',
                _s("rang", fontName="Helvetica", fontSize=9, alignment=TA_RIGHT, textColor=GRIS_SEC),
            ),
        ],
    ]], colWidths=[CONTENT_W * 0.42, CONTENT_W * 0.58])
    score_block.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), zone_bg),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (0, -1), 20),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 16),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW",     (0, 0), (-1, -1), 3, zone_col),
    ]))
    story.append(score_block)
    story.append(Spacer(1, 18))

    # ── ④ KPI GRID (6 indicateurs 3×2) ───────────────────────────────────────
    _section_heading("Indicateurs clés", story)

    apl     = r.get("apl_median_dept")
    temps   = r.get("temps_acces_median")
    med_gen = r.get("med_gen_pour_100k")
    prix    = r.get("prix_m2_moyen")
    pct65   = r.get("pct_plus_65")
    pop     = r.get("population_num")
    score_acces = r.get("score_acces")
    score_etabs = r.get("score_etabs")

    apl_nat   = master["apl_median_dept"].median()   if "apl_median_dept"   in master.columns else None
    temp_nat  = master["temps_acces_median"].median() if "temps_acces_median" in master.columns else None
    med_nat   = master["med_gen_pour_100k"].median()  if "med_gen_pour_100k"  in master.columns else None
    pct65_nat = master["pct_plus_65"].median()        if "pct_plus_65"        in master.columns else None

    def _arrow(good: bool | None) -> str:
        if good is True:  return f'<font color="#{_hex(VERT_FAV)}">▲</font>'
        if good is False: return f'<font color="#{_hex(ROUGE_CRIT)}">▼</font>'
        return '<font color="#999999">—</font>'

    def _kpi(label, val_str, cmp_str, good):
        col = VERT_FAV if good is True else (ROUGE_CRIT if good is False else AMBRE)
        return [
            Paragraph(f'<font size="8" color="#999999">{label.upper()}</font>',
                      _s(f"kl_{label[:4]}", fontSize=8, textColor=GRIS_SEC)),
            Paragraph(f'<b><font size="20" color="#{_hex(col)}">{val_str}</font></b>',
                      _s(f"kv_{label[:4]}", fontName="Helvetica-Bold", fontSize=20,
                         textColor=col, leading=24)),
            Paragraph(f'{_arrow(good)} <font size="8" color="#666666">{cmp_str}</font>',
                      _s(f"kd_{label[:4]}", fontSize=8, textColor=colors.HexColor("#666666"))),
        ]

    kpis = [
        _kpi("APL médecins gén.",
             _fmt(apl, "{:.2f}") + " /hab.",
             f"Méd. nat. {_fmt(apl_nat, '{:.2f}')}",
             _compare(apl, apl_nat)),
        _kpi("Temps d'accès médial",
             _fmt(temps, "{:.0f}") + " min",
             f"Méd. nat. {_fmt(temp_nat, '{:.0f}')} min",
             _compare(temp_nat, temps)),  # inversé : moins = mieux
        _kpi("Médecins gén. / 100k",
             _fmt(med_gen, "{:.0f}"),
             f"Méd. nat. {_fmt(med_nat, '{:.0f}')}",
             _compare(med_gen, med_nat)),
        _kpi("Prix immobilier médian",
             _fmt(prix, "{:,.0f}").replace(",", "\u202f") + " €/m²",
             "Source DVF 2025",
             None),
        _kpi("Part des 65 ans et +",
             _fmt(pct65, "{:.1f}") + " %",
             f"Méd. nat. {_fmt(pct65_nat, '{:.1f}')} %",
             None),
        _kpi("Population",
             _fmt(pop, "{:,.0f}").replace(",", "\u202f") if pop and not pd.isna(pop) else "—",
             "Source INSEE 2021",
             None),
    ]

    cw3 = CONTENT_W / 3
    kpi_tbl = Table(
        [[kpis[0], kpis[1], kpis[2]], [kpis[3], kpis[4], kpis[5]]],
        colWidths=[cw3, cw3, cw3],
    )
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BLANC),
        ("BOX",           (0, 0), (-1, -1), 0.8, GRIS_BORD),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, GRIS_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",    (0, 0), (2, 0), GRIS_CLAIR),  # first row slightly shaded
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 18))

    # ── ⑤ DÉLAIS DE RDV ESTIMÉS ──────────────────────────────────────────────
    try:
        from .components.delais import compute_delais_proxy
        apl_val = float(apl) if apl is not None and not pd.isna(apl) else None
        if apl_val:
            delais_df = compute_delais_proxy(dept_code, apl_val)
            if not delais_df.empty and "delai_estime_jours" in delais_df.columns:
                _section_heading("Délais de rendez-vous estimés", story)

                story.append(Paragraph(
                    f'<i><font size="8" color="#666666">Estimation proxy : délai national DREES '
                    f'× (APL nationale 2,9 / APL département {apl_val:.2f}). '
                    f'Facteur plafonné à 3,0 pour éviter les aberrations.</font></i>',
                    _s("dmeta", fontSize=8, textColor=colors.HexColor("#666666"),
                       fontName="Helvetica", leading=11),
                ))
                story.append(Spacer(1, 6))

                d_rows = [[
                    Paragraph('<b><font size="9" color="white">Spécialité</font></b>',
                              _s("dh0", fontSize=9, textColor=BLANC, fontName="Helvetica-Bold")),
                    Paragraph('<b><font size="9" color="white">Nat. (j)</font></b>',
                              _s("dh1", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                                 fontName="Helvetica-Bold")),
                    Paragraph('<b><font size="9" color="white">Estimé (j)</font></b>',
                              _s("dh2", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                                 fontName="Helvetica-Bold")),
                    Paragraph('<b><font size="9" color="white">Interprétation</font></b>',
                              _s("dh3", fontSize=9, textColor=BLANC, fontName="Helvetica-Bold")),
                ]]
                for _, drow in delais_df.iterrows():
                    nat_j  = int(drow.get("delai_median_jours", 0))
                    est_j  = int(drow.get("delai_estime_jours", 0))
                    interp = str(drow.get("interpretation", ""))
                    diff   = est_j - nat_j
                    vc = ROUGE_CRIT if diff > 3 else (VERT_FAV if diff < -3 else AMBRE)
                    d_rows.append([
                        Paragraph(f'<font size="9">{drow.get("specialite", "")}</font>',
                                  _s(f"dc_{nat_j}", fontSize=9, textColor=NOIR)),
                        Paragraph(f'<font size="9">{nat_j}\u202fj</font>',
                                  _s(f"dn_{nat_j}", fontSize=9, alignment=TA_CENTER, textColor=GRIS_TXT)),
                        Paragraph(f'<b><font size="9" color="#{_hex(vc)}">{est_j}\u202fj</font></b>',
                                  _s(f"de_{est_j}", fontSize=9, alignment=TA_CENTER,
                                     textColor=vc, fontName="Helvetica-Bold")),
                        Paragraph(f'<font size="8" color="#666666">{interp}</font>',
                                  _s(f"di_{nat_j}", fontSize=8, textColor=colors.HexColor("#666666"))),
                    ])

                d_tbl = Table(
                    d_rows,
                    colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.14, CONTENT_W * 0.17, CONTENT_W * 0.34],
                )
                d_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, 0), BLEU_NUIT),
                    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BLANC, GRIS_CLAIR]),
                    ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_BORD),
                    ("TOPPADDING",    (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(d_tbl)
                story.append(Spacer(1, 18))
    except Exception:
        pass

    # ── ⑥ PATHOLOGIES PRIORITAIRES ────────────────────────────────────────────
    if data and "patho" in data:
        try:
            from .config import PATHOS_EXCLUDED
            patho_df = data["patho"]
            if not patho_df.empty and "_error" not in patho_df.columns:
                dp = patho_df[patho_df["dept"] == dept_code].copy()
                dp = dp[~dp["patho_niv1"].isin(PATHOS_EXCLUDED)]
                if not dp.empty and "patho_niv1" in dp.columns:
                    dg = (
                        dp.groupby("patho_niv1")[["Ntop", "Npop"]]
                        .sum()
                        .reset_index()
                    )
                    dg["prev"] = (dg["Ntop"] / dg["Npop"] * 100).round(2)
                    top5 = dg.sort_values("prev", ascending=False).head(5)
                    if not top5.empty:
                        _section_heading("Pathologies chroniques · prévalence territoriale", story)

                        p_rows = [[
                            Paragraph('<b><font size="9" color="white">Pathologie</font></b>',
                                      _s("ph0", fontSize=9, textColor=BLANC, fontName="Helvetica-Bold")),
                            Paragraph('<b><font size="9" color="white">Prévalence</font></b>',
                                      _s("ph1", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                                         fontName="Helvetica-Bold")),
                            Paragraph('<b><font size="9" color="white">Patients</font></b>',
                                      _s("ph2", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                                         fontName="Helvetica-Bold")),
                            Paragraph('<b><font size="9" color="white">Rang (dept)</font></b>',
                                      _s("ph3", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                                         fontName="Helvetica-Bold")),
                        ]]
                        for rank_i, (_, prow) in enumerate(top5.iterrows(), 1):
                            ntop_s = f"{int(prow['Ntop']):,}".replace(",", "\u202f")
                            bar_w  = int(float(prow["prev"]) / float(top5["prev"].max()) * 10)
                            bar    = "█" * bar_w + "░" * (10 - bar_w)
                            p_rows.append([
                                Paragraph(
                                    f'<font size="9">{str(prow["patho_niv1"])[:55]}</font>',
                                    _s(f"pn{rank_i}", fontSize=9, textColor=NOIR),
                                ),
                                Paragraph(
                                    f'<b><font size="9" color="#{_hex(BLEU_ROYAL)}">'
                                    f'{prow["prev"]:.2f}\u202f%</font></b>',
                                    _s(f"pv{rank_i}", fontSize=9, alignment=TA_CENTER,
                                       textColor=BLEU_ROYAL, fontName="Helvetica-Bold"),
                                ),
                                Paragraph(
                                    f'<font size="9">{ntop_s}</font>',
                                    _s(f"pp{rank_i}", fontSize=9, alignment=TA_CENTER, textColor=GRIS_TXT),
                                ),
                                Paragraph(
                                    f'<font size="8" color="#{_hex(BLEU_NUIT)}">{bar}</font>',
                                    _s(f"pb{rank_i}", fontSize=8, alignment=TA_CENTER, textColor=BLEU_NUIT),
                                ),
                            ])
                        p_tbl = Table(
                            p_rows,
                            colWidths=[CONTENT_W * 0.48, CONTENT_W * 0.18, CONTENT_W * 0.17, CONTENT_W * 0.17],
                        )
                        p_tbl.setStyle(TableStyle([
                            ("BACKGROUND",    (0, 0), (-1, 0), BLEU_NUIT),
                            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BLANC, GRIS_CLAIR]),
                            ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_BORD),
                            ("TOPPADDING",    (0, 0), (-1, -1), 7),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                        ]))
                        story.append(p_tbl)
                        story.append(Spacer(1, 18))
        except Exception:
            pass

    # ── ⑦ RECOMMANDATIONS ─────────────────────────────────────────────────────
    if recos:
        _section_heading("Plan d'action recommandé", story)

        _prio_col_map = {
            1: ROUGE_CRIT, "P1": ROUGE_CRIT,
            2: AMBRE,      "P2": AMBRE,
            3: BLEU_ROYAL, "P3": BLEU_ROYAL,
        }

        for i, reco in enumerate(recos[:4], 1):
            prio_raw  = reco.get("priority", i)
            prio_lbl  = f"P{prio_raw}" if isinstance(prio_raw, int) else str(prio_raw)
            badge_col = _prio_col_map.get(prio_raw, BLEU_ROYAL)
            stats     = reco.get("stats", [])

            content = [
                Paragraph(
                    f'<b><font size="11" color="#{_hex(BLEU_NUIT)}">{reco.get("title", "")}</font></b>',
                    _s(f"rt{i}", fontName="Helvetica-Bold", fontSize=11,
                       textColor=BLEU_NUIT, spaceAfter=4),
                ),
                Paragraph(
                    reco.get("prose", ""),
                    _s(f"rp{i}", fontSize=9, textColor=GRIS_TXT, leading=13),
                ),
            ]

            if stats:
                stat_items = []
                for val, lbl in stats[:3]:
                    stat_items.append(Paragraph(
                        f'<b><font size="14" color="#{_hex(badge_col)}">{val}</font></b>'
                        f'<br/><font size="8" color="#666666">{lbl}</font>',
                        _s(f"rs{i}{val[:2]}", fontName="Helvetica-Bold", fontSize=14,
                           textColor=badge_col, alignment=TA_CENTER, leading=18),
                    ))
                while len(stat_items) < 3:
                    stat_items.append(Paragraph("", _s("rse", fontSize=8)))

                stat_cw = (CONTENT_W - 36) / 3
                st_tbl = Table([stat_items], colWidths=[stat_cw] * 3)
                st_tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, -1), GRIS_CLAIR),
                    ("GRID",          (0, 0), (-1, -1), 0.3, GRIS_BORD),
                    ("TOPPADDING",    (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ]))
                content.append(Spacer(1, 5))
                content.append(st_tbl)

            reco_tbl = Table([[
                Paragraph(
                    f'<b><font size="12" color="#{_hex(badge_col)}">{prio_lbl}</font></b>',
                    _s(f"rb{i}", fontName="Helvetica-Bold", fontSize=12,
                       alignment=TA_CENTER, textColor=badge_col),
                ),
                content,
            ]], colWidths=[36, CONTENT_W - 36])
            reco_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), BLANC),
                ("TOPPADDING",    (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING",   (0, 0), (0, -1), 10),
                ("LEFTPADDING",   (1, 0), (1, -1), 12),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW",     (0, 0), (-1, -1), 0.5, GRIS_BORD),
                ("LINEBEFORE",    (0, 0), (0, -1), 3, badge_col),
            ]))
            story.append(KeepTogether(reco_tbl))
            story.append(Spacer(1, 6))

    # ── ⑧ TABLEAU COMPARATIF NATIONAL ────────────────────────────────────────
    _section_heading("Comparaison nationale", story)

    def _ecart(val, ref, higher=True) -> str:
        try:
            v, r2 = float(val), float(ref)
            diff   = v - r2
            symbol = "▲" if diff > 0 else ("▼" if diff < 0 else "=")
            good   = (diff > 0) == higher
            c      = f"#{_hex(VERT_FAV)}" if good else f"#{_hex(ROUGE_CRIT)}"
            return f'<font color="{c}"><b>{symbol} {abs(diff):.1f}</b></font>'
        except Exception:
            return "—"

    score_med = ranked["score_global"].median() if not ranked.empty else None

    comp_rows = [[
        Paragraph('<b><font size="9" color="white">Indicateur</font></b>',
                  _s("ch0", fontSize=9, textColor=BLANC, fontName="Helvetica-Bold")),
        Paragraph('<b><font size="9" color="white">Ce département</font></b>',
                  _s("ch1", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                     fontName="Helvetica-Bold")),
        Paragraph('<b><font size="9" color="white">Médiane nationale</font></b>',
                  _s("ch2", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                     fontName="Helvetica-Bold")),
        Paragraph('<b><font size="9" color="white">Écart</font></b>',
                  _s("ch3", fontSize=9, alignment=TA_CENTER, textColor=BLANC,
                     fontName="Helvetica-Bold")),
    ]]

    for ind, dept_v, nat_v, higher in [
        ("APL médecins gén.",      _fmt(apl, "{:.2f}"),    _fmt(apl_nat, "{:.2f}"),    True),
        ("Temps d'accès (min)",    _fmt(temps, "{:.0f}"),   _fmt(temp_nat, "{:.0f}"),   False),
        ("Médecins gén. / 100k",   _fmt(med_gen, "{:.0f}"), _fmt(med_nat, "{:.0f}"),    True),
        ("Score global / 100",     _fmt(score, "{:.1f}"),   _fmt(score_med, "{:.1f}"),  True),
    ]:
        try:
            ecart_str = _ecart(dept_v, nat_v, higher)
        except Exception:
            ecart_str = "—"
        comp_rows.append([
            Paragraph(f'<font size="9">{ind}</font>',    _s(f"ci{ind[:3]}", fontSize=9, textColor=NOIR)),
            Paragraph(f'<b><font size="9">{dept_v}</font></b>',
                      _s(f"cv{ind[:3]}", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER)),
            Paragraph(f'<font size="9">{nat_v}</font>', _s(f"cn{ind[:3]}", fontSize=9,
                                                            alignment=TA_CENTER, textColor=GRIS_TXT)),
            Paragraph(ecart_str,                        _s(f"ce{ind[:3]}", fontSize=9, alignment=TA_CENTER)),
        ])

    c_tbl = Table(comp_rows, colWidths=[CONTENT_W * 0.40, CONTENT_W * 0.20,
                                        CONTENT_W * 0.20, CONTENT_W * 0.20])
    c_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), BLEU_NUIT),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [BLANC, GRIS_CLAIR]),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(c_tbl)
    story.append(Spacer(1, 24))

    # ── BUILD ─────────────────────────────────────────────────────────────────
    cb = _page_cb(dept_name)
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()
