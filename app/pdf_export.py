"""Rapports territoriaux PDF (département, région) — ReportLab.

Structure du rapport départemental (3 à 5 pages A4) :
  1. Synthèse exécutive : identité, score Sant'active (offre et accès aux soins), indicateurs clés,
     trois constats, priorités d'action, lien vers la fiche en ligne.
  2. Diagnostic : les six dimensions du score, comparaison aux médianes nationales (temps INSEE 2025),
     pathologies.
  3. Recommandations : pour chaque levier, problème, public, communes concernées, action, données,
     conditions de mise en œuvre.
  4. Approfondissement (si disponible) : capacité théorique en ETP, estimation indicative des délais.
  5. Sources, méthode et limites.

Règles éditoriales : chiffres au format français, millésimes nommés, estimation distinguée de
l'observé, pas de « score global de santé territoriale » (le score mesure l'offre et l'accès aux
soins de premier recours), rangs affichés 1er = le mieux placé.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as _xml_escape

import pandas as pd
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .config import APL_MILLESIME, TEMPS_LABEL_COURT
from .scoring import DIMENSIONS, fmt_classement_national

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
GRIS_SEC   = colors.HexColor("#777777")
BLEU_PALE  = colors.HexColor("#EEF2FA")

W, H = A4
MARGIN    = 18 * mm
CONTENT_W = W - 2 * MARGIN
NBSP = " "
BASE_URL = "https://santactive.streamlit.app"


# ─── Polices : Marianne (charte) avec repli Helvetica ─────────────────────────
def _register_fonts() -> tuple[str, str, str]:
    try:
        base = Path(__file__).resolve().parent.parent / "static" / "fonts" / "marianne"
        if "Marianne" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Marianne", str(base / "Marianne-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("Marianne-Bold", str(base / "Marianne-Bold.ttf")))
            pdfmetrics.registerFont(TTFont("Marianne-Medium", str(base / "Marianne-Medium.ttf")))
            pdfmetrics.registerFontFamily("Marianne", normal="Marianne", bold="Marianne-Bold",
                                          italic="Marianne", boldItalic="Marianne-Bold")
        return "Marianne", "Marianne-Bold", "Marianne-Medium"
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Helvetica"


FONT, FONT_B, FONT_M = _register_fonts()


# ─── Helpers de format ────────────────────────────────────────────────────────
_MOIS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
            "août", "septembre", "octobre", "novembre", "décembre")


def _date_fr(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.day} {_MOIS_FR[d.month - 1]} {d.year}"


def _num(val, dec: int = 1, fallback: str = "N/D") -> str:
    """Nombre au format français (virgule décimale, espace insécable pour les milliers)."""
    try:
        if val is None or pd.isna(val):
            return fallback
        s = f"{float(val):,.{dec}f}"
        return s.replace(",", "§").replace(".", ",").replace("§", NBSP)
    except Exception:
        return fallback


def _pct(val, dec: int = 1, fallback: str = "N/D") -> str:
    """Part (0-1) en pourcentage français."""
    try:
        if val is None or pd.isna(val):
            return fallback
        return _num(float(val) * 100, dec) + NBSP + "%"
    except Exception:
        return fallback


def _f(val) -> float | None:
    try:
        if val is None or pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


_GLYPH_MAP = str.maketrans({" ": NBSP, " ": NBSP, "ᵉ": "e", "✓": "+", "✗": "–",
                            "′": "'", "″": '"'})


def _esc(x: Any) -> str:
    """Échappement XML pour Paragraph + remplacement des caractères absents de la police (Marianne)."""
    return _xml_escape(str(x if x is not None else "").translate(_GLYPH_MAP))


def _hex(c: Any) -> str:
    return c.hexval()[2:]


def _s(name: str, **kwargs) -> ParagraphStyle:
    defaults = {"fontName": FONT, "fontSize": 9.5, "textColor": NOIR, "leading": 13.5}
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


ST_BODY  = _s("body")
ST_SMALL = _s("small", fontSize=8, leading=11, textColor=GRIS_TXT)
ST_NOTE  = _s("note", fontSize=7.5, leading=10.5, textColor=GRIS_SEC)
ST_LABEL = _s("label", fontSize=7.5, leading=10, textColor=GRIS_SEC)
ST_H1    = _s("h1", fontName=FONT_B, fontSize=24, leading=28, textColor=BLEU_NUIT)
ST_H2    = _s("h2", fontName=FONT_B, fontSize=12.5, leading=16, textColor=BLEU_NUIT)
ST_H3    = _s("h3", fontName=FONT_B, fontSize=10.5, leading=14, textColor=BLEU_NUIT)
ST_TH    = _s("th", fontName=FONT_B, fontSize=8, leading=10, textColor=BLANC)
ST_TD    = _s("td", fontSize=8.5, leading=11)
ST_TDC   = _s("tdc", fontSize=8.5, leading=11, alignment=TA_CENTER)
ST_TDR   = _s("tdr", fontSize=8.5, leading=11, alignment=TA_RIGHT)


def _zone_color(zone: str) -> Any:
    return {"Critique": ROUGE_CRIT, "Intermédiaire": AMBRE, "Favorable": VERT_FAV}.get(zone, BLEU_ROYAL)


def _zone_soft(zone: str) -> Any:
    return {"Critique": colors.HexColor("#FBEEF0"), "Intermédiaire": colors.HexColor("#FEF4DC"),
            "Favorable": colors.HexColor("#E3EFE8")}.get(zone, GRIS_CLAIR)


def _zone_lecture(zone: str) -> str:
    return {"Critique": "tiers des départements les moins bien placés",
            "Intermédiaire": "tiers médian des départements",
            "Favorable": "tiers des départements les mieux placés"}.get(zone, "sans classement")


def _typologie(densite) -> str:
    d = _f(densite)
    if d is None:
        return "N/D"
    return "rural" if d < 80 else "péri-urbain" if d < 250 else "urbain" if d < 1000 else "urbain dense"


# ─── Composants ───────────────────────────────────────────────────────────────
def _heading(title: str, story: list, sub: str | None = None) -> None:
    story.append(Spacer(1, 10))
    rows = [[Paragraph(_esc(title).upper(), _s("hd", fontName=FONT_B, fontSize=10.5, leading=13, textColor=BLEU_NUIT))]]
    tbl = Table(rows, colWidths=[CONTENT_W])
    tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, BLEU_ROYAL),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ROUGE_CRIT),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    if sub:
        story.append(Spacer(1, 3))
        story.append(Paragraph(_esc(sub), ST_SMALL))
    story.append(Spacer(1, 7))


def _box(flowables: list, bg=GRIS_CLAIR, border=GRIS_BORD, width: float = CONTENT_W, pad: int = 9,
         left_bar: Any = None) -> Table:
    t = Table([[flowables]], colWidths=[width])
    style = [("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.5, border),
             ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
             ("LEFTPADDING", (0, 0), (-1, -1), pad + 2), ("RIGHTPADDING", (0, 0), (-1, -1), pad + 2),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if left_bar is not None:
        style.append(("LINEBEFORE", (0, 0), (0, -1), 3, left_bar))
    t.setStyle(TableStyle(style))
    return t


def _bar(value: float | None, color: Any, width: float = 50 * mm, height: float = 5.5) -> Drawing:
    """Barre 0-100 avec repère médian (50)."""
    d = Drawing(width, height + 3)
    d.add(Rect(0, 1.5, width, height, fillColor=GRIS_CLAIR, strokeColor=None))
    if value is not None:
        d.add(Rect(0, 1.5, width * max(0.0, min(100.0, value)) / 100.0, height, fillColor=color, strokeColor=None))
    d.add(Rect(width / 2 - 0.4, 0, 0.8, height + 3, fillColor=GRIS_SEC, strokeColor=None))
    return d


def _table(rows: list, col_widths: list, header: bool = True, zebra: bool = True, font_size: float = 8.5) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.3, GRIS_BORD), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), BLEU_NUIT))
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [BLANC, GRIS_CLAIR]))
    t.setStyle(TableStyle(style))
    return t


def _th(txt: str, align=TA_LEFT) -> Paragraph:
    return Paragraph(_esc(txt), _s("thx", fontName=FONT_B, fontSize=8, leading=10, textColor=BLANC, alignment=align))


def _td(txt: str, align=TA_LEFT, bold: bool = False, color: Any = NOIR, size: float = 8.5) -> Paragraph:
    return Paragraph(txt, _s("tdx", fontName=FONT_B if bold else FONT, fontSize=size, leading=size + 2.5,
                             textColor=color, alignment=align))


def _link(url: str, label: str | None = None) -> str:
    return f'<a href="{_esc(url)}" color="#{_hex(BLEU_ROYAL)}"><u>{_esc(label or url)}</u></a>'


# ─── Pagination : en-tête, pied de page, « Page x / n » ───────────────────────
class _NumberedCanvas(_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self.setFont(FONT, 7.5)
            self.setFillColor(GRIS_SEC)
            self.drawRightString(W - MARGIN, 10 * mm, f"Page {self._pageNumber} / {total}")
            _canvas.Canvas.showPage(self)
        _canvas.Canvas.save(self)


def _page_cb(running_title: str, sources_line: str):
    def _cb(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BLEU_NUIT)
        canvas.rect(0, H - 9 * mm, W, 9 * mm, fill=1, stroke=0)
        canvas.setFillColor(ROUGE_CRIT)
        canvas.rect(0, H - 9 * mm, 4 * mm, 9 * mm, fill=1, stroke=0)
        canvas.setFont(FONT_B, 7.5)
        canvas.setFillColor(BLANC)
        canvas.drawString(MARGIN, H - 6 * mm, "SANT'ACTIVE  ·  " + running_title.upper())
        canvas.setFont(FONT, 7.5)
        canvas.drawRightString(W - MARGIN, H - 6 * mm, f"Rapport territorial · {_date_fr()}")
        canvas.setStrokeColor(GRIS_BORD)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 14 * mm, W - MARGIN, 14 * mm)
        canvas.setFont(FONT, 7)
        canvas.setFillColor(GRIS_SEC)
        canvas.drawString(MARGIN, 10 * mm, f"Sant'active · {running_title} · document de travail, données publiques")
        canvas.drawString(MARGIN, 7 * mm, sources_line)
        canvas.restoreState()
    return _cb


def _doc(buf: io.BytesIO, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                             topMargin=MARGIN + 3 * mm, bottomMargin=19 * mm, title=title, author="Sant'active",
                             subject="Offre et accès aux soins de premier recours")


_SOURCES_LINE = (f"Sources : DREES APL {APL_MILLESIME} · INSEE accès aux équipements 2025 · DREES RPPS 2026 · "
                 "FINESS 2026 · INSEE RP 2021 · CNAM 2023 · DVF 2025")


# ─── Pages communes : sources, méthode, limites ───────────────────────────────
_SOURCES_ROWS = [
    ("Accessibilité potentielle localisée (APL)", f"DREES, APL aux médecins généralistes, millésime {APL_MILLESIME}",
     "Consultations accessibles par an et par habitant ; repère de sous-densité 2,5. Valeur départementale : moyenne des APL communaux pondérée par la population standardisée."),
    ("Temps d'accès à un généraliste", "INSEE, accès aux équipements 2025 (BPE 2025, distancier Metric-OSRM)",
     "Trajet en voiture, par carreau habité de 200 m, vers le cabinet le plus proche. Guadeloupe, Guyane, Mayotte hors champ."),
    ("Médecins généralistes", "DREES, répertoire RPPS au 1er janvier 2026 · INSEE RP 2021",
     "Personnes en activité, tous modes d'exercice, rapportées à la population municipale."),
    ("Structures de soins", "FINESS (ministère chargé de la Santé, diffusion DREES), mars 2026",
     "Centres hospitaliers, centres hospitaliers régionaux, établissements privés de soins de suite et de réadaptation : des sites, pas des capacités. Les cliniques privées de court séjour ne sont pas comptées ; l'indicateur ne décrit pas toute l'offre hospitalière."),
    ("Population, âge, densité", "INSEE, recensement de la population 2021", "Population municipale, part des 65 ans et plus, densité."),
    ("Pathologies", "CNAM, cartographie des pathologies et des dépenses, 2023", "Patients pris en charge ; prévalences brutes ou standardisées sur l'âge selon l'usage."),
    ("Prix immobilier", "DVF (DGFiP), 2025", "Prix médian des transactions, indicateur de contexte (5 % du score)."),
]


def _sources_pages(story: list, *, lien_methodo: str, niveau: str) -> None:
    # Nouvelle page seulement s'il reste moins de la moitié d'une page : évite une page à moitié vide.
    story.append(Spacer(1, 8))
    story.append(CondPageBreak(130 * mm))
    _heading("Sources, méthode et limites", story)
    rows = [[_th("Donnée"), _th("Source et millésime"), _th("Lecture")]]
    for a, b, c in _SOURCES_ROWS:
        rows.append([_td(_esc(a), bold=True, size=8), _td(_esc(b), size=8), _td(_esc(c), size=7.5, color=GRIS_TXT)])
    story.append(_table(rows, [CONTENT_W * 0.24, CONTENT_W * 0.32, CONTENT_W * 0.44]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Méthode", ST_H3))
    story.append(Spacer(1, 3))
    meth = [
        "<b>Score Sant'active</b> : indice sur 100 construit à partir de six indicateurs publics, chacun converti en rang "
        "parmi les 100 départements analysés (50 = médiane), puis moyenne pondérée : APL 30 %, temps d'accès à un "
        "généraliste 20 %, densité de généralistes 20 %, structures hospitalières 15 %, part des 65 ans et plus 10 %, "
        "prix immobilier 5 %. Les pondérations sont un choix méthodologique du projet, pas des pondérations officielles. "
        "Lorsqu'un indicateur manque, son poids est redistribué (au moins trois dimensions).",
        "<b>Zones et classement</b> : les départements sont répartis en trois groupes de taille égale (critique, "
        "intermédiaire, favorable). Le classement affiche 1er = le mieux placé ; les rangs sont uniques.",
        "<b>Leviers d'action</b> : catalogue d'une vingtaine de dispositifs existants, chacun assorti de conditions "
        "chiffrées (obligatoires, contributives, exclusions). Un levier est retenu si ses conditions obligatoires sont "
        "remplies et qu'au moins un tiers de ses conditions pondérées le sont ; au plus quatre leviers, deux par famille. "
        "Règles explicites, sans intelligence artificielle générative.",
    ]
    if niveau == "region":
        meth.append(
            "<b>Priorités régionales</b> : le score de priorité (0-100) est la moyenne du besoin (fragilité et score "
            "Sant'active) et du volume de population concernée ; il n'intègre pas la faisabilité. La lecture "
            "« fragilité × impact × faisabilité » est une qualification complémentaire qui identifie les candidats à "
            "une expérimentation ; ce n'est pas un second score.")
    for m in meth:
        story.append(Paragraph(m, ST_SMALL))
        story.append(Spacer(1, 3))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Limites", ST_H3))
    story.append(Spacer(1, 3))
    for lim in [
        "Les indicateurs décrivent l'offre et l'accessibilité géographique des soins de premier recours ; ils ne mesurent "
        "ni la disponibilité réelle des rendez-vous, ni la qualité des soins, ni l'état de santé de la population.",
        "Le score situe un département parmi les autres à une date donnée ; il ne mesure pas une évolution.",
        "Les leviers sont des pistes fondées sur des règles explicites, à instruire avec les acteurs locaux (ARS, CPTS, "
        "collectivités, professionnels) ; ils ne constituent ni une prescription ni une évaluation de politique publique.",
        "Les estimations (équivalents temps plein théoriques) sont signalées comme telles et ne remplacent pas une donnée observée.",
    ]:
        story.append(Paragraph("– " + lim, ST_SMALL))
        story.append(Spacer(1, 2))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Méthodologie complète et historique des changements : {_link(lien_methodo)}. "
        f"Rapport généré le {_date_fr()} à partir de l'application Sant'active ({_link(BASE_URL)}).", ST_NOTE))


# ═════════════════════════════════════════════════════════════════════════════
# RAPPORT DÉPARTEMENTAL
# ═════════════════════════════════════════════════════════════════════════════
_DIM_META = {
    "apl":      ("Accessibilité potentielle (APL)", lambda v: _num(v, 2) + " consult./hab.", f"DREES {APL_MILLESIME}"),
    "temps":    ("Temps médian vers un généraliste", lambda v: _num(v, 0) + " min", TEMPS_LABEL_COURT),
    "medecins": ("Généralistes pour 100 000 hab.", lambda v: _num(v, 0), "RPPS 2026"),
    "etabs":    ("Sites hospitaliers pour 100 000 hab.", lambda v: _num(v, 1), "FINESS 2026"),
    "seniors":  ("Part des 65 ans et plus", lambda v: _num(v, 1) + NBSP + "%", "INSEE RP 2021"),
    "foncier":  ("Prix médian au m²", lambda v: _num(v, 0) + " €/m²", "DVF 2025"),
}


def _constats(r: pd.Series, master: pd.DataFrame) -> list[tuple[str, bool]]:
    """Trois constats chiffrés, du plus marquant au moins marquant ; True = point de vigilance."""
    med = lambda c: _f(pd.to_numeric(master[c], errors="coerce").median()) if c in master.columns else None
    out: list[tuple[float, str, bool]] = []

    apl, apl_m = _f(r.get("apl_dept")), med("apl_dept")
    if apl is not None and apl_m:
        part, pop = _f(r.get("part_pop_apl_inf_2_5")), _f(r.get("population_num"))
        sous = apl < apl_m
        s = (f"APL de {_num(apl, 2)} consultations par habitant et par an, {'sous' if sous else 'au-dessus de'} la "
             f"médiane des départements ({_num(apl_m, 2)}).")
        if part is not None and pop is not None:
            s += (f" {_num(part * pop, 0)} habitants ({_pct(part, 0)}) vivent dans une commune sous le repère 2,5."
                  if part > 0 else " Aucune commune sous le repère de sous-densité 2,5.")
        out.append(((apl - apl_m) / apl_m, s, sous))

    p15, p15_m = _f(r.get("acces_mg_part_sup_15")), med("acces_mg_part_sup_15")
    if p15 is not None and p15_m is not None:
        n15, nc = _f(r.get("acces_mg_pop_sup_15")), _f(r.get("acces_mg_nb_communes_sup_15"))
        pire = p15 > p15_m
        s = (f"{_pct(p15)} des habitants sont à plus de 15 minutes en voiture d'un généraliste "
             f"(médiane des départements : {_pct(p15_m)})")
        if n15 is not None:
            s += f", soit {_num(n15, 0)} personnes"
        if nc is not None and nc > 0:
            s += f" dans {_num(nc, 0)} communes"
        s += " (INSEE 2025)."
        out.append((-(p15 - p15_m) / max(p15_m, 0.005), s, pire))
    elif _f(r.get("temps_acces_interne_median")) is not None:
        t = _f(r.get("temps_acces_interne_median"))
        out.append((-0.3, f"Temps d'accès INSEE 2025 non disponible (territoire hors champ) ; l'indicateur interne "
                          f"donne {_num(t, 0)} minutes médianes vers un généraliste, à lire avec prudence.", True))

    mg, mg_m = _f(r.get("med_gen_pour_100k")), med("med_gen_pour_100k")
    if mg is not None and mg_m:
        sous = mg < mg_m
        out.append(((mg - mg_m) / mg_m,
                    f"{_num(mg, 0)} médecins généralistes pour 100 000 habitants (RPPS 2026), {'sous' if sous else 'au-dessus de'} "
                    f"la médiane ({_num(mg_m, 0)}) ; un effectif de personnes, à lire avec l'APL qui tient compte de l'activité réelle.",
                    sous))

    p65, p65_m = _f(r.get("pct_plus_65")), med("pct_plus_65")
    if p65 is not None and p65_m:
        plus = p65 > p65_m
        out.append((-(p65 - p65_m) / p65_m,
                    f"{_num(p65)} % de la population a 65 ans ou plus (médiane {_num(p65_m)} %) : "
                    f"{'pression accrue' if plus else 'pression moindre'} sur la demande de soins et les parcours gériatriques.",
                    plus))

    et, et_m = _f(r.get("structures_pour_100k")), med("structures_pour_100k")
    if et is not None and et_m:
        sous = et < et_m
        out.append(((et - et_m) / et_m,
                    f"{_num(et, 1)} sites hospitaliers pour 100 000 habitants (FINESS 2026), {'sous' if sous else 'au-dessus de'} "
                    f"la médiane ({_num(et_m, 1)}).", sous))

    out.sort(key=lambda x: (not x[2], -abs(x[0])))  # vigilances d'abord, puis écart le plus marquant
    return [(s, vig) for _, s, vig in out[:3]]


def _reco_card(i: int, reco: dict, r: pd.Series, data: dict | None) -> Table:
    esc = _esc
    famille = str(reco.get("famille", "") or "")
    horizon = str(reco.get("horizon", "") or "")
    head = f'<font color="#{_hex(GRIS_SEC)}" size="7.5">{esc(famille).upper()}'
    if horizon:
        head += f"  ·  {esc(horizon)}"
    head += "</font>"
    parts: list = [
        Paragraph(head, ST_LABEL),
        Paragraph(f"{i}. {esc(reco.get('title', ''))}", ST_H3),
        Spacer(1, 4),
    ]

    def block(label: str, text: str) -> None:
        if text and str(text).strip():
            parts.append(Paragraph(f'<font color="#{_hex(BLEU_ROYAL)}"><b>{esc(label)}</b></font>  {esc(text)}',
                                   _s("rb", fontSize=8.5, leading=12)))
            parts.append(Spacer(1, 3))

    block("Problème", reco.get("probleme", ""))
    pop_obs = ""
    try:
        if data is not None:
            from .action_impact import project_levier_impact
            imp = project_levier_impact(reco, r, data)
            pop_obs = str(getattr(imp, "population", "") or "")
            if pop_obs.strip().lower() in ("n.d.", "n/d"):
                pop_obs = ""
    except Exception:
        pop_obs = ""
    public = str(reco.get("public", "") or "").strip()
    if public or pop_obs:
        block("Public", public + (f" · population observée : {pop_obs}" if pop_obs else ""))
    block("Communes et secteurs concernés", str(reco.get("secteurs", "") or "").strip())
    block("Action", reco.get("action", ""))
    indic = [str(x) for x in (reco.get("indicateurs") or [])[:4]]
    if indic:
        block("Données", " · ".join(indic))
    block("Pourquoi ici", reco.get("pourquoi", ""))
    disp = ", ".join(str(x) for x in (reco.get("dispositifs") or []))
    if disp:
        block("Dispositifs existants", disp)
    block("Mise en œuvre", reco.get("mise_en_oeuvre", ""))
    conds = reco.get("conditions") or []
    if conds:
        ok = [str(lab) for lab, k in conds if k]
        ko = [str(lab) for lab, k in conds if not k]
        txt = ""
        if ok:
            txt += f'<font color="#{_hex(VERT_FAV)}">Conditions remplies :</font> ' + esc(" ; ".join(ok)) + ". "
        if ko:
            txt += f'<font color="#{_hex(GRIS_SEC)}">Non remplies :</font> ' + esc(" ; ".join(ko)) + "."
        parts.append(Paragraph(txt, ST_NOTE))
    return _box(parts, bg=BLANC, left_bar=BLEU_ROYAL, pad=8)


def generate_department_pdf(r: pd.Series, master: pd.DataFrame, recos: list[dict], data: dict | None = None) -> bytes:
    """Rapport territorial départemental (3 à 5 pages)."""
    buf = io.BytesIO()
    dept_name = str(r.get("Nom du département", "N/D"))
    dept_code = str(r.get("dept", "")).zfill(2)
    region = str(r.get("Nom de la région", "N/D"))
    zone = str(r.get("zone_short", "N/D"))
    score = _f(r.get("score_global"))
    nb_dims = _f(r.get("nb_dimensions_ok"))
    total = int(master["score_global"].notna().sum())
    rang = r.get("rang_national")
    rang_str = fmt_classement_national(rang, total) if rang is not None and pd.notna(rang) else "N/D"
    zone_col, zone_bg = _zone_color(zone), _zone_soft(zone)
    med = lambda c: _f(pd.to_numeric(master[c], errors="coerce").median()) if c in master.columns else None
    lien_fiche = f"{BASE_URL}/?view=dept&dept_code={dept_code}"
    lien_methodo = f"{BASE_URL}/?view=methodologie"
    recos = [x for x in (recos or []) if isinstance(x, dict)]
    maintien = bool(recos) and all(str(x.get("id", "")) == "maintien" for x in recos)

    doc = _doc(buf, f"Sant'active · {dept_name} ({dept_code}) · rapport territorial")
    story: list = []

    # ── PAGE 1 · SYNTHÈSE ────────────────────────────────────────────────────
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"{_esc(dept_name)} <font size='13' color='#{_hex(GRIS_SEC)}'>({dept_code})</font>", ST_H1))
    pop, dens = _f(r.get("population_num")), _f(r.get("densite"))
    ident = f"{_esc(region)}"
    if pop is not None:
        ident += f" · {_num(pop, 0)} habitants"
    if dens is not None:
        ident += f" · {_num(dens, 0)} hab./km² ({_typologie(dens)})"
    story.append(Paragraph(ident, _s("ident", fontSize=10, textColor=GRIS_TXT)))
    story.append(Paragraph(f"Rapport territorial · offre et accès aux soins de premier recours · {_date_fr()}", ST_SMALL))
    story.append(Spacer(1, 10))

    score_cell = [
        Paragraph(f'<font size="34" color="#{_hex(zone_col)}"><b>{_num(score, 1)}</b></font>'
                  f'<font size="11" color="#{_hex(GRIS_SEC)}"> /100</font>',
                  _s("sc", fontName=FONT_B, fontSize=34, leading=38)),
        Paragraph("Score Sant'active · offre et accès aux soins", _s("scl", fontSize=8.5, textColor=GRIS_TXT)),
    ]
    right = [
        Paragraph(f'<font color="#{_hex(zone_col)}"><b>Zone {_esc(zone.lower())}</b></font> · {_zone_lecture(zone)}',
                  _s("zb", fontSize=11, leading=14)),
        Spacer(1, 3),
        Paragraph(f"Classement : <b>{_esc(rang_str)}</b> sur {total} départements (1er = le mieux placé).", ST_BODY),
        Paragraph("Le score situe le département parmi les autres sur six indicateurs publics d'offre et d'accès "
                  "aux soins de premier recours ; ce n'est ni une note de santé, ni une évolution.", ST_SMALL),
    ]
    if nb_dims is not None and nb_dims < 6:
        right.append(Paragraph(f'<font color="#{_hex(ROUGE_CRIT)}">Score calculé sur {int(nb_dims)} dimensions sur 6 '
                               f'(temps d\'accès INSEE 2025 hors champ) ; les poids manquants sont redistribués.</font>', ST_SMALL))
    sb = Table([[score_cell, right]], colWidths=[CONTENT_W * 0.36, CONTENT_W * 0.64])
    sb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), zone_bg), ("LINEBELOW", (0, 0), (-1, -1), 2.5, zone_col),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 10),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LEFTPADDING", (0, 0), (-1, -1), 14),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))
    story.append(sb)
    story.append(Spacer(1, 12))

    # Indicateurs clés (4)
    apl, apl_m = _f(r.get("apl_dept")), med("apl_dept")
    p15, p15_m = _f(r.get("acces_mg_part_sup_15")), med("acces_mg_part_sup_15")
    mg, mg_m = _f(r.get("med_gen_pour_100k")), med("med_gen_pour_100k")
    p65, p65_m = _f(r.get("pct_plus_65")), med("pct_plus_65")
    part_apl = _f(r.get("part_pop_apl_inf_2_5"))

    def kpi(label, value, ctx, bad: bool | None):
        col = ROUGE_CRIT if bad else (VERT_FAV if bad is False else BLEU_NUIT)
        return [Paragraph(_esc(label).upper(), ST_LABEL),
                Paragraph(f'<font size="17" color="#{_hex(col)}"><b>{value}</b></font>', _s("kv", fontName=FONT_B, fontSize=17, leading=21)),
                Paragraph(_esc(ctx), ST_NOTE)]

    k = [
        kpi(f"APL · DREES {APL_MILLESIME}", _num(apl, 2) + " c./hab.",
            f"médiane {_num(apl_m, 2)} · " + (f"{_pct(part_apl, 0)} des habitants sous le repère 2,5" if part_apl is not None else ""),
            None if apl is None or apl_m is None else apl < apl_m),
        (kpi("Habitants à plus de 15 min · INSEE 2025", _pct(p15), f"médiane des départements {_pct(p15_m)}",
             None if p15 is None or p15_m is None else p15 > p15_m)
         if p15 is not None else
         kpi("Temps d'accès (indicateur interne)", _num(r.get("temps_acces_interne_median"), 0) + " min",
             "INSEE 2025 hors champ pour ce territoire", None)),
        kpi("Généralistes /100 000 hab. · RPPS 2026", _num(mg, 0), f"médiane {_num(mg_m, 0)}",
            None if mg is None or mg_m is None else mg < mg_m * 0.9),
        kpi("65 ans et plus · INSEE 2021", _num(p65) + NBSP + "%", f"médiane {_num(p65_m)} %",
            None if p65 is None or p65_m is None else p65 > p65_m + 2),
    ]
    kt = Table([k], colWidths=[CONTENT_W / 4] * 4)
    kt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, GRIS_BORD), ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS_BORD),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(kt)
    story.append(Spacer(1, 12))

    # Trois constats
    _heading("Trois constats", story)
    for s, vig in _constats(r, master):
        tag = (f'<font color="#{_hex(ROUGE_CRIT)}"><b>Vigilance</b></font>' if vig
               else f'<font color="#{_hex(VERT_FAV)}"><b>Point d\'appui</b></font>')
        story.append(Paragraph(f"{tag} — {_esc(s)}", ST_BODY))
        story.append(Spacer(1, 4))

    # Priorités d'action
    _heading("Priorités d'action", story, "Leviers retenus par les règles du catalogue Sant'active ; détail en page 3.")
    if maintien or not recos:
        story.append(Paragraph("Aucun levier du catalogue n'est déclenché par les indicateurs observés : veille et maintien "
                               "de l'offre existante, surveillance des départs de généralistes.", ST_BODY))
    else:
        for i, reco in enumerate(recos[:4], 1):
            pub = str(reco.get("public", "") or "").strip()
            story.append(Paragraph(f"<b>{i}. {_esc(reco.get('title', ''))}</b>" + (f" — public : {_esc(pub)}" if pub else ""), ST_BODY))
            story.append(Spacer(1, 2))
    story.append(Spacer(1, 8))
    story.append(_box([Paragraph(f"<b>Fiche en ligne</b> (carte, communes prioritaires, comparaison, simulateur) : {_link(lien_fiche)}", ST_SMALL)],
                      bg=BLEU_PALE, border=BLEU_PALE))

    # ── PAGE 2 · DIAGNOSTIC ──────────────────────────────────────────────────
    story.append(PageBreak())
    _heading("Diagnostic · les six dimensions du score", story,
             "Position du département sur chaque indicateur : 0 = le moins bien placé, 100 = le mieux placé, 50 = médiane (repère vertical).")
    rows = [[_th("Dimension"), _th("Valeur"), _th("Médiane nat.", TA_CENTER), _th("Position /100", TA_CENTER), _th("Poids", TA_CENTER)]]
    for key, cfg in DIMENSIONS.items():
        label, fmt, src = _DIM_META[key]
        sc = _f(r.get(f"score_{key}"))
        raw = _f(r.get(cfg["col"]))
        m = med(cfg["col"])
        col = ROUGE_CRIT if (sc is not None and sc < 33.3) else (AMBRE if (sc is not None and sc < 66.7) else VERT_FAV)
        rows.append([
            _td(f"<b>{_esc(label)}</b><br/><font size='7' color='#{_hex(GRIS_SEC)}'>{_esc(src)}</font>"),
            _td(fmt(raw) if raw is not None else "N/D", bold=True),
            _td(fmt(m) if m is not None else "N/D", TA_CENTER, color=GRIS_TXT),
            [_bar(sc, col), Paragraph(_num(sc, 0) if sc is not None else "non disponible", _s("bv", fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=GRIS_TXT))],
            _td(f"{int(round(cfg['weight'] * 100))} %", TA_CENTER),
        ])
    story.append(_table(rows, [CONTENT_W * 0.32, CONTENT_W * 0.17, CONTENT_W * 0.14, CONTENT_W * 0.27, CONTENT_W * 0.10]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Les dimensions temps d'accès, 65 ans et plus et prix immobilier sont lues en sens inverse : une "
                           "valeur plus faible donne une meilleure position.", ST_NOTE))

    # Accès, offre, besoins : comparaison détaillée
    _heading("Accès, offre et besoins · comparaison nationale", story)
    t_med, t_med_m = _f(r.get("temps_acces_median")), med("temps_acces_median")
    n15 = _f(r.get("acces_mg_pop_sup_15")); nc15 = _f(r.get("acces_mg_nb_communes_sup_15"))
    comp = [[_th("Indicateur"), _th("Ce département", TA_CENTER), _th("Médiane des départements", TA_CENTER), _th("Lecture")]]

    def crow(label, v, m, lecture, src):
        comp.append([_td(f"{_esc(label)}<br/><font size='7' color='#{_hex(GRIS_SEC)}'>{_esc(src)}</font>"),
                     _td(v, TA_CENTER, bold=True), _td(m, TA_CENTER, color=GRIS_TXT), _td(_esc(lecture), size=7.5, color=GRIS_TXT)])

    crow("APL (consultations/hab./an)", _num(apl, 2), _num(apl_m, 2), "repère de sous-densité : 2,5", f"DREES {APL_MILLESIME}")
    crow("Habitants sous le repère APL 2,5", _pct(part_apl, 0), _pct(med("part_pop_apl_inf_2_5"), 0),
         (f"{_num(part_apl * pop, 0)} personnes" if part_apl > 0 else "aucune commune sous le repère") if part_apl is not None and pop else "", f"DREES {APL_MILLESIME}")
    if p15 is not None:
        crow("Temps médian vers un généraliste", _num(t_med, 0) + " min", _num(t_med_m, 0) + " min", "médiane pondérée par la population", "INSEE 2025")
        crow("Habitants à plus de 15 min", _pct(p15), _pct(p15_m),
             (f"{_num(n15, 0)} personnes" if n15 is not None else "") + (f" · {_num(nc15, 0)} communes" if nc15 else ""), "INSEE 2025")
    else:
        crow("Temps médian (indicateur interne)", _num(r.get("temps_acces_interne_median"), 0) + " min",
             _num(med("temps_acces_interne_median"), 0) + " min", "INSEE 2025 hors champ : indicateur interne de repli", "interne")
    crow("Généralistes pour 100 000 hab.", _num(mg, 0), _num(mg_m, 0), "personnes en activité, tous modes d'exercice", "RPPS 2026")
    crow("Sites hospitaliers pour 100 000 hab.", _num(r.get("structures_pour_100k"), 1), _num(med("structures_pour_100k"), 1),
         "CH, CHR, SSR privés ; cliniques privées de court séjour exclues", "FINESS 2026")
    crow("Part des 65 ans et plus", _num(p65) + NBSP + "%", _num(p65_m) + NBSP + "%", "pression sur la demande de soins", "INSEE RP 2021")
    crow("Prix médian au m²", _num(r.get("prix_m2_moyen"), 0) + " €", _num(med("prix_m2_moyen"), 0) + " €", "contexte d'installation (5 % du score)", "DVF 2025")
    story.append(_table(comp, [CONTENT_W * 0.34, CONTENT_W * 0.17, CONTENT_W * 0.21, CONTENT_W * 0.28]))

    # ── PAGE 3 · RECOMMANDATIONS ─────────────────────────────────────────────
    story.append(PageBreak())
    _heading("Recommandations opérationnelles", story,
             "Leviers issus d'un catalogue de dispositifs existants, retenus par des règles explicites sur les indicateurs "
             "observés (au plus quatre, deux par famille). Pistes à instruire avec les acteurs locaux, pas des prescriptions.")
    if maintien and recos and (recos[0].get("action") or recos[0].get("probleme")):
        story.append(KeepTogether(_reco_card(1, recos[0], r, data)))
    elif maintien or not recos:
        story.append(_box([Paragraph("<b>Maintien et veille.</b> Aucun levier du catalogue n'est déclenché : les conditions "
                                     "obligatoires (part d'habitants éloignés, sous-densité, besoins spécifiques) ne sont pas réunies. "
                                     "Recommandation : suivre les départs de généralistes et l'APL communal, et réexaminer à la "
                                     "prochaine mise à jour des données.", ST_BODY)], left_bar=VERT_FAV, bg=BLANC))
    else:
        for i, reco in enumerate(recos[:4], 1):
            story.append(KeepTogether(_reco_card(i, reco, r, data)))
            story.append(Spacer(1, 8))

    # ── PAGE 4 · APPROFONDISSEMENT (si disponible) ───────────────────────────
    deep: list = []
    try:
        from .simulation_capacite import simuler
        sim = simuler(dept_code)
    except Exception:
        sim = None
    if sim and _f(sim.get("deficit_2,5")) is not None and float(sim["deficit_2,5"]) <= 0:
        deep.append(Paragraph("Capacité théorique en équivalents temps plein (ETP)", ST_H3))
        deep.append(Spacer(1, 3))
        deep.append(Paragraph(f"APL moyen pondéré : <b>{_num(sim['apl_moyen_pondere'], 2)}</b> consultations par an et par habitant ; "
                              "aucune commune sous le repère 2,5 : pas de déficit théorique de capacité à combler "
                              f"(source : DREES, APL {APL_MILLESIME}).", ST_BODY))
        deep.append(Spacer(1, 10))
    elif sim:
        lo, mid, hi = sim["etp_2,5"]
        deep.append(Paragraph("Capacité théorique en équivalents temps plein (ETP)", ST_H3))
        deep.append(Spacer(1, 3))
        deep.append(Paragraph(
            f"APL moyen pondéré : <b>{_num(sim['apl_moyen_pondere'], 2)}</b> consultations par an et par habitant ; "
            f"<b>{_pct(sim['part_pop_apl_inf_2_5'], 0)}</b> de la population vit sous le repère 2,5 "
            f"({_num(sim['nb_communes_inf_2_5'], 0)} communes sur {_num(sim['nb_communes'], 0)}). Pour amener chaque commune "
            f"sous le seuil au niveau du seuil, il manquerait environ <b>{_num(sim['deficit_2,5'], 0)}</b> consultations accessibles "
            f"par an, soit <b>environ {_num(mid, 0)} ETP</b> de médecine générale (fourchette {_num(lo, 0)} à {_num(hi, 0)} ETP "
            f"pour 6 000 à 3 600 actes par an ; convention : 1 ETP = 5 400 actes).", ST_BODY))
        deep.append(Spacer(1, 3))
        deep.append(Paragraph("Estimation statique, pas un effectif officiel de médecins manquants : offre existante supposée "
                              "inchangée, déficit calculé commune par commune (effets de voisinage ignorés, tendance à surestimer), "
                              f"ETP différents des médecins physiques. Source : DREES, APL {APL_MILLESIME}.", ST_NOTE))
        deep.append(Spacer(1, 10))
    # Délais DREES 2016-2017 : retirés des rapports (décision du 28 octobre 2026) ; historique dans la Méthodologie.
    # Pathologies (prévalence brute) en approfondissement
    if data and isinstance(data.get("patho"), pd.DataFrame):
        try:
            from .config import PATHOS_EXCLUDED
            pdf_ = data["patho"]
            if not pdf_.empty and "_error" not in pdf_.columns:
                dp = pdf_[(pdf_["dept"] == dept_code) & (~pdf_["patho_niv1"].isin(PATHOS_EXCLUDED))]
                if not dp.empty:
                    dg = dp.groupby("patho_niv1")[["Ntop", "Npop"]].sum(min_count=1).reset_index()
                    dg["prev"] = dg["Ntop"] / dg["Npop"].where(dg["Npop"] > 0) * 100
                    top5 = dg.dropna(subset=["prev"]).sort_values("prev", ascending=False).head(5)
                    if not top5.empty:
                        deep.append(Paragraph("Pathologies les plus fréquentes", ST_H3)); deep.append(Spacer(1, 3)); deep.append(Paragraph(
                                 "Prévalence brute (part des assurés pris en charge), non standardisée sur l'âge · CNAM 2023.", ST_SMALL)); deep.append(Spacer(1, 5))
                        prow = [[_th("Pathologie"), _th("Prévalence", TA_CENTER), _th("Patients", TA_CENTER), _th("")]]
                        mx = float(top5["prev"].max())
                        for _, p in top5.iterrows():
                            prow.append([_td(_esc(str(p["patho_niv1"])[:70])), _td(_num(p["prev"], 2) + NBSP + "%", TA_CENTER, bold=True),
                                         _td(_num(p["Ntop"], 0), TA_CENTER, color=GRIS_TXT), _bar(float(p["prev"]) / mx * 100, BLEU_ROYAL, 26 * mm)])
                        deep.append(_table(prow, [CONTENT_W * 0.50, CONTENT_W * 0.15, CONTENT_W * 0.15, CONTENT_W * 0.20])); deep.append(Spacer(1, 10))
        except Exception:
            pass

    if deep:
        story.append(Spacer(1, 8))
        story.append(CondPageBreak(120 * mm))
        _heading("Approfondissement", story, "Pathologies observées (CNAM) et calculs Sant'active signalés comme estimations ; ils complètent le diagnostic sans s'y substituer.")
        story.extend(deep)

    _sources_pages(story, lien_methodo=lien_methodo, niveau="dept")

    doc.build(story, onFirstPage=_page_cb(f"{dept_name} ({dept_code})", _SOURCES_LINE),
              onLaterPages=_page_cb(f"{dept_name} ({dept_code})", _SOURCES_LINE), canvasmaker=_NumberedCanvas)
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════════
# RAPPORT RÉGIONAL
# ═════════════════════════════════════════════════════════════════════════════
def generate_region_pdf(region_name: str, region_code: str, region_depts: pd.DataFrame, summary: dict,
                        priorities: pd.DataFrame, leviers: list[dict], master: pd.DataFrame | None = None) -> bytes:
    """Rapport territorial régional (3 à 4 pages) : synthèse, tableau des départements, leviers, sources."""
    buf = io.BytesIO()
    rd = region_depts.copy()
    num = lambda c: pd.to_numeric(rd[c], errors="coerce") if c in rd.columns else pd.Series(dtype=float)
    nb = len(rd)
    nb_crit = int((rd["zone_short"] == "Critique").sum()) if "zone_short" in rd.columns else 0
    pop = num("population_num"); apl = num("apl_dept"); part_apl = num("part_pop_apl_inf_2_5")
    pop_tot = float(pop.sum()) if len(pop) else None
    pop_sous = float((part_apl * pop).sum()) if len(pop) else None
    part_sous = pop_sous / pop_tot if pop_tot else None
    pop15 = float(num("acces_mg_pop_sup_15").sum()); popins = float(num("acces_mg_pop").sum())
    part15 = pop15 / popins if popins > 0 else None
    sc = num("score_global")
    nat = master if isinstance(master, pd.DataFrame) and not master.empty else None
    natm = lambda c: _f(pd.to_numeric(nat[c], errors="coerce").median()) if nat is not None and c in nat.columns else None
    part_sous_nat = (float((pd.to_numeric(nat["part_pop_apl_inf_2_5"], errors="coerce") * pd.to_numeric(nat["population_num"], errors="coerce")).sum()
                           / pd.to_numeric(nat["population_num"], errors="coerce").sum()) if nat is not None else None)
    lien_fiche = f"{BASE_URL}/?view=region&region_code={region_code}"
    lien_methodo = f"{BASE_URL}/?view=methodologie"
    prio = priorities.copy() if isinstance(priorities, pd.DataFrame) else pd.DataFrame()
    if "priorite_rang" in prio.columns:
        prio = prio.sort_values("priorite_rang")

    doc = _doc(buf, f"Sant'active · {region_name} · rapport régional")
    story: list = []

    # ── PAGE 1 · SYNTHÈSE ────────────────────────────────────────────────────
    story.append(Spacer(1, 4))
    story.append(Paragraph(_esc(region_name), ST_H1))
    story.append(Paragraph(f"Région {region_code} · {nb} département{'s' if nb > 1 else ''}"
                           + (f" · {_num(pop_tot, 0)} habitants" if pop_tot else ""), _s("ident", fontSize=10, textColor=GRIS_TXT)))
    story.append(Paragraph(f"Rapport territorial · disparités d'accès aux soins et départements à examiner · {_date_fr()}", ST_SMALL))
    story.append(Spacer(1, 10))

    tension = str(summary.get("tension_principale", "") or "")
    story.append(_box([Paragraph(f"<b>Tension principale :</b> {_esc(tension)}", _s("tp", fontSize=10.5, leading=14))],
                      bg=BLEU_PALE, border=BLEU_PALE, left_bar=BLEU_ROYAL))
    story.append(Spacer(1, 10))

    def kpi(label, value, ctx, bad: bool | None):
        col = ROUGE_CRIT if bad else (VERT_FAV if bad is False else BLEU_NUIT)
        return [Paragraph(_esc(label).upper(), ST_LABEL),
                Paragraph(f'<font size="17" color="#{_hex(col)}"><b>{value}</b></font>', _s("kv", fontName=FONT_B, fontSize=17, leading=21)),
                Paragraph(_esc(ctx), ST_NOTE)]

    k = [
        kpi("Habitants sous le repère APL 2,5", _num(pop_sous, 0) if pop_sous is not None else "N/D",
            (f"{_pct(part_sous)} de la population régionale" + (f" · France : {_pct(part_sous_nat)}" if part_sous_nat is not None else "")),
            None if part_sous is None or part_sous_nat is None else part_sous > part_sous_nat),
        kpi(f"APL médian · DREES {APL_MILLESIME}", _num(apl.median(), 2) + " c./hab.",
            f"de {_num(apl.min(), 2)} à {_num(apl.max(), 2)} selon le département" + (f" · médiane nat. {_num(natm('apl_dept'), 2)}" if natm("apl_dept") else ""),
            None),
        kpi("Départements en zone critique", f"{nb_crit} / {nb}", "tiers des départements les moins bien placés au score", nb_crit > 0),
        kpi("Habitants à plus de 15 min · INSEE 2025", _pct(part15) if part15 is not None else "N/D",
            f"{_num(pop15, 0)} personnes" if part15 is not None else "temps INSEE non disponible", None),
    ]
    kt = Table([k], colWidths=[CONTENT_W / 4] * 4)
    kt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, GRIS_BORD), ("INNERGRID", (0, 0), (-1, -1), 0.3, GRIS_BORD),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(kt)

    # Constats régionaux
    _heading("Trois constats", story)
    constats: list[str] = []
    if len(apl.dropna()) >= 2:
        lo, hi = rd.loc[apl.idxmin()], rd.loc[apl.idxmax()]
        constats.append(f"Disparités d'accessibilité : l'APL va de {_num(apl.min(), 2)} ({_esc(lo['Nom du département'])}) à "
                        f"{_num(apl.max(), 2)} ({_esc(hi['Nom du département'])}) consultations par habitant et par an ; "
                        f"scores Sant'active de {_num(sc.min(), 0)} à {_num(sc.max(), 0)} sur 100.")
    if pop_sous is not None and part_sous is not None:
        constats.append(f"{_num(pop_sous, 0)} habitants ({_pct(part_sous)}) vivent dans une commune sous le repère de sous-densité 2,5"
                        + (f", contre {_pct(part_sous_nat)} en France" if part_sous_nat is not None else "") + ".")
    crit_names = rd.loc[rd["zone_short"] == "Critique", "Nom du département"].tolist() if "zone_short" in rd.columns else []
    if crit_names:
        constats.append(f"{len(crit_names)} département{'s' if len(crit_names) > 1 else ''} en zone critique : "
                        f"{_esc(', '.join(str(x) for x in crit_names))}.")
    elif part15 is not None:
        constats.append(f"Aucun département en zone critique ; {_pct(part15)} des habitants sont à plus de 15 minutes d'un généraliste "
                        f"({_num(pop15, 0)} personnes, INSEE 2025).")
    for c in constats[:3]:
        story.append(Paragraph("– " + c, ST_BODY))
        story.append(Spacer(1, 4))

    # Départements à examiner
    _heading("Départements à examiner en priorité", story,
             "Score de priorité (0-100) : moyenne du besoin et du volume de population concernée, hors faisabilité.")
    if not prio.empty:
        for _, p in prio.head(3).iterrows():
            story.append(Paragraph(f"<b>{int(p.get('priorite_rang', 0))}. {_esc(p.get('Nom du département', ''))}</b> · "
                                   f"score de priorité {_num(p.get('score_priorite'), 0)}/100 · lecture : {_esc(p.get('priorite', ''))}", ST_BODY))
            lr = str(p.get("lecture_rapide", "") or "")
            if lr:
                story.append(Paragraph(_esc(lr[:260]), ST_SMALL))
            story.append(Spacer(1, 3))
    story.append(Spacer(1, 6))
    story.append(_box([Paragraph(f"<b>Fiche régionale en ligne</b> (carte, tableau technique, leviers par département) : {_link(lien_fiche)}", ST_SMALL)],
                      bg=BLEU_PALE, border=BLEU_PALE))

    # ── PAGE 2 · TABLEAU DES DÉPARTEMENTS ────────────────────────────────────
    story.append(PageBreak())
    _heading("Diagnostic · les départements de la région", story,
             "Score Sant'active (offre et accès aux soins, 1er = le mieux placé) et indicateurs d'accès ; score de priorité et lecture "
             "« fragilité × impact × faisabilité » (qualification complémentaire, pas un second score).")
    pcols = {}
    if not prio.empty and "Nom du département" in prio.columns:
        for _, p in prio.iterrows():
            pcols[str(p["Nom du département"])] = p
    total_nat = int(nat["score_global"].notna().sum()) if nat is not None else None
    rows = [[_th("Département"), _th("Score", TA_CENTER), _th("Zone", TA_CENTER), _th("APL", TA_CENTER),
             _th("> 15 min", TA_CENTER), _th("65 ans +", TA_CENTER), _th("Priorité /100", TA_CENTER), _th("Lecture")]]
    for _, d in rd.sort_values("score_global", na_position="last").iterrows():
        nom = str(d.get("Nom du département", ""))
        p = pcols.get(nom)
        z = str(d.get("zone_short", ""))
        rang_txt = ""
        if total_nat and pd.notna(d.get("rang_national")):
            rang_txt = f"<br/><font size='7' color='#{_hex(GRIS_SEC)}'>{_esc(fmt_classement_national(d.get('rang_national'), total_nat))} sur {total_nat}</font>"
        rows.append([
            _td(f"<b>{_esc(nom)}</b> <font size='7' color='#{_hex(GRIS_SEC)}'>({_esc(str(d.get('dept', '')).zfill(2))})</font>{rang_txt}"),
            _td(_num(d.get("score_global"), 1), TA_CENTER, bold=True),
            _td(_esc(z), TA_CENTER, color=_zone_color(z), bold=True, size=8),
            _td(_num(d.get("apl_dept"), 2), TA_CENTER),
            _td(_pct(d.get("acces_mg_part_sup_15")), TA_CENTER),
            _td(_num(d.get("pct_plus_65")) + NBSP + "%", TA_CENTER),
            _td(_num(p.get("score_priorite"), 0) if p is not None else "N/D", TA_CENTER, bold=True),
            _td(_esc(p.get("priorite", "")) if p is not None else "", size=7.5),
        ])
    story.append(_table(rows, [CONTENT_W * 0.21, CONTENT_W * 0.08, CONTENT_W * 0.15, CONTENT_W * 0.08,
                               CONTENT_W * 0.09, CONTENT_W * 0.09, CONTENT_W * 0.10, CONTENT_W * 0.20]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Score : score Sant'active sur 100 et classement national. APL : consultations par habitant et par an (DREES {APL_MILLESIME}). "
                           "> 15 min : part des habitants à plus de 15 minutes en voiture d'un généraliste (INSEE 2025). "
                           "Priorité : score de priorité régional (besoin et volume, hors faisabilité). Lecture : qualification croisant "
                           "fragilité, impact et faisabilité.", ST_NOTE))

    # ── LEVIERS (à la suite du tableau) ──────────────────────────────────────
    story.append(Spacer(1, 6))
    _heading("Leviers d'action régionaux", story,
             "Leviers retenus pour les départements de la région par les règles du catalogue ; chaque département a son propre rapport détaillé.")
    levs = [l for l in (leviers or []) if isinstance(l, dict)]
    if not levs:
        story.append(Paragraph("Aucun levier régional déclenché : maintien et veille de l'offre existante.", ST_BODY))
    for i, lev in enumerate(levs[:6], 1):
        titre = str(lev.get("intitule") or lev.get("titre") or lev.get("title") or "")
        parts = [Paragraph(f"<font size='7.5' color='#{_hex(GRIS_SEC)}'>{_esc(str(lev.get('famille', '') or '')).upper()}"
                           + (f"  ·  {_esc(lev.get('horizon'))}" if lev.get("horizon") else "") + "</font>", ST_LABEL),
                 Paragraph(f"{i}. {_esc(titre)}", ST_H3), Spacer(1, 4)]
        depts_lev = [str(x) for x in (lev.get("depts") or [])]
        if depts_lev:
            parts.append(Paragraph(f"<font color='#{_hex(BLEU_ROYAL)}'><b>Départements concernés</b></font>  {_esc(', '.join(depts_lev))}", _s("rb", fontSize=8.5, leading=12)))
            parts.append(Spacer(1, 3))
        pub = str(lev.get("public_cible") or lev.get("public") or "").strip()
        if pub:
            parts.append(Paragraph(f"<font color='#{_hex(BLEU_ROYAL)}'><b>Public</b></font>  {_esc(pub)}", _s("rb", fontSize=8.5, leading=12)))
            parts.append(Spacer(1, 3))
        why = str(lev.get("pourquoi_maintenant") or lev.get("justification") or lev.get("description") or "").strip()
        if why:
            parts.append(Paragraph(f"<font color='#{_hex(BLEU_ROYAL)}'><b>Pourquoi maintenant</b></font>  {_esc(why[:700])}", _s("rb", fontSize=8.5, leading=12)))
            parts.append(Spacer(1, 3))
        disp = ", ".join(str(x) for x in (lev.get("dispositifs") or []))
        if disp:
            parts.append(Paragraph(f"<font color='#{_hex(BLEU_ROYAL)}'><b>Dispositifs existants</b></font>  {_esc(disp)}", _s("rb", fontSize=8.5, leading=12)))
        story.append(KeepTogether(_box(parts, bg=BLANC, left_bar=BLEU_ROYAL, pad=8)))
        story.append(Spacer(1, 8))

    _sources_pages(story, lien_methodo=lien_methodo, niveau="region")
    doc.build(story, onFirstPage=_page_cb(region_name, _SOURCES_LINE), onLaterPages=_page_cb(region_name, _SOURCES_LINE),
              canvasmaker=_NumberedCanvas)
    return buf.getvalue()
