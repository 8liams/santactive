"""Diagnostic national : constats disponibles à l'échelle de la France entière.

Il n'existe pas de « score national » : le score Sant'active classe les
départements entre eux. La vue nationale présente donc ce qui est réellement
mesurable à cette échelle : repères officiels (APL DREES, accès routier Insee,
densités RPPS), répartition des zones par région, départements les moins bien
placés et leurs raisons, et les entrées vers Prioriser, les fiches et la
comparaison.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ..components.aide import aide_methodo
from ..components.nav import NavCrumb, dept_link_html, internal_href, render_breadcrumb
from ..config import APL_MILLESIME
from ..scoring import get_score_breakdown


def _fr(v, fmt=".1f") -> str:
    return format(v, fmt).replace(",", " ").replace(".", ",")


def render(data: dict) -> None:
    master: pd.DataFrame = data["master"]
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Diagnostic national")], key_prefix="diag_nat_bc")
    nb = int(master["score_global"].notna().sum())
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">FRANCE ENTIÈRE</span>'
        f'<span class="dot"></span><span class="region">{nb} départements analysés · Mayotte hors score</span>{aide_methodo("score")}</div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Diagnostic <em>national</em></h1></div>'
        '<p class="fiche-header-lead">Ce qui se mesure à l’échelle de la France : accessibilité potentielle aux généralistes, '
        'éloignement routier, densités, et la répartition des départements selon le score Sant’active. Choisissez un territoire '
        'dans la barre pour obtenir son diagnostic.</p></div>', unsafe_allow_html=True)

    num = lambda c: pd.to_numeric(master[c], errors="coerce") if c in master.columns else pd.Series(dtype=float)
    pop = num("population_num")
    part_apl = num("part_pop_apl_inf_2_5")
    pop_sous = float((part_apl * pop).sum())
    pop_ins = num("acces_mg_pop"); pop15 = float(num("acces_mg_pop_sup_15").sum())
    part15 = pop15 / float(pop_ins.sum()) if pop_ins.sum() > 0 else float("nan")
    apl_med = num("apl_dept").median(); med_med = num("med_gen_pour_100k").median()

    def kpi(label, value, unit, ctx, color="#1A3D8F"):
        return (f'<div class="diagnostic-kpi" style="padding:12px 14px;--sem:{color};">'
                f'<div class="diagnostic-kpi-label">{label}</div>'
                f'<div class="diagnostic-kpi-value" style="font-size:26px;margin-bottom:6px;">{value}<span class="max"> {unit}</span></div>'
                f'<div style="font-size:11px;color:#6B6B68;line-height:1.4;">{ctx}</div></div>')
    c = st.columns(4)
    c[0].markdown(kpi("Sous le repère APL 2,5", f"{pop_sous / 1e6:.1f}".replace(".", ","), "M hab.",
                      f"{_fr(pop_sous / pop.sum() * 100)} % de la population vit dans une commune sous le repère de sous-densité · DREES {APL_MILLESIME}", "#A51C30"), unsafe_allow_html=True)
    c[1].markdown(kpi("APL médiane des départements", _fr(apl_med), "consult./hab.",
                      f"{int((num('apl_dept') < 2.5).sum())} départements sous 2,5 · {int((num('apl_dept') < apl_med).sum())} sous la médiane"), unsafe_allow_html=True)
    c[2].markdown(kpi("À plus de 15 min d’un généraliste", _fr(part15 * 100) if pd.notna(part15) else "N/D", "%",
                      f"{int(pop15):,} habitants · INSEE 2025, carreaux de 200 m · hors Guadeloupe, Guyane, Mayotte".replace(",", " "), "#D9772B"), unsafe_allow_html=True)
    c[3].markdown(kpi("Généralistes", _fr(med_med, ".0f"), "/100 000 hab.",
                      f"densité médiane des départements · RPPS 1ᵉʳ janv. 2026 · de {_fr(num('med_gen_pour_100k').min(), '.0f')} à {_fr(num('med_gen_pour_100k').max(), '.0f')}"), unsafe_allow_html=True)

    # ── Où se concentrent les difficultés ────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:22px;"><div class="section-eyebrow">OÙ</div>'
                '<h2 class="section-title">Où se concentrent <em>les difficultés ?</em></h2>'
                '<p class="section-lead">Le score Sant’active classe les départements entre eux (terciles : 33 critiques, 34 intermédiaires, '
                '33 favorables par construction). Il n’existe pas de score national : la lecture utile est la répartition par région '
                'et les départements les moins bien placés.</p></div>', unsafe_allow_html=True)
    g1, g2 = st.columns([1.15, 1], gap="large")
    with g1:
        st.markdown('<h4 class="subsection-title">Zones critiques par région</h4>', unsafe_allow_html=True)
        regs = (master.groupby(["Code région", "Nom de la région"])
                .agg(n=("dept", "size"), crit=("zone_short", lambda s: int((s == "Critique").sum())),
                     fav=("zone_short", lambda s: int((s == "Favorable").sum())), pop=("population_num", "sum"),
                     part15=("acces_mg_pop_sup_15", "sum"), popins=("acces_mg_pop", "sum")).reset_index()
                .sort_values(["crit", "n"], ascending=[False, True]))
        def _lien_region(r):
            code = str(r["Code région"])
            return internal_href("region", region_code=code, t="r" + code)
        def _ligne(r):
            part = (_fr(r["part15"] / r["popins"] * 100) + "\u202f%") if r["popins"] > 0 else "n.d."
            return (f'<div style="display:grid;grid-template-columns:2fr .7fr .7fr 1fr;padding:6px 10px;border-bottom:1px solid #E8E6DD;font-size:13px;align-items:center;">'
                    f'<span><a href="{_lien_region(r)}" target="_self" class="region-dept-name">{html.escape(str(r["Nom de la région"]))}</a></span>'
                    f'<span style="text-align:right;color:#A51C30;font-weight:700;">{int(r["crit"])}<span style="color:#9C9A92;font-weight:400;"> / {int(r["n"])}</span></span>'
                    f'<span style="text-align:right;color:#1B5E3F;">{int(r["fav"])}</span>'
                    f'<span style="text-align:right;color:#6B6B68;">{part}</span></div>')
        rows = "".join(_ligne(r) for _, r in regs.iterrows())
        st.markdown('<div class="sa-tbl-scroll"><div style="display:grid;grid-template-columns:2fr .7fr .7fr 1fr;padding:6px 10px;background:#F3F2EC;'
                    'font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6B6B68;"><span>Région</span>'
                    '<span style="text-align:right;">Critiques</span><span style="text-align:right;">Favorables</span>'
                    '<span style="text-align:right;">&gt; 15 min (INSEE)</span></div>' + rows + '</div>', unsafe_allow_html=True)
    with g2:
        st.markdown('<h4 class="subsection-title">Les dix départements les moins bien placés</h4>', unsafe_allow_html=True)
        worst = master.dropna(subset=["score_global"]).sort_values("score_global").head(10)
        cards = ""
        for _, r in worst.iterrows():
            bd = [b for b in get_score_breakdown(r) if b["score"] is not None]
            faibles = [b["label"][0].lower() + b["label"][1:] for b in sorted(bd, key=lambda b: b["score"])[:2]]
            cards += (f'<div style="display:flex;justify-content:space-between;gap:10px;padding:7px 10px;border-bottom:1px solid #E8E6DD;font-size:13px;">'
                      f'<span>{dept_link_html(str(r["dept"]), str(r["Nom du département"]), css_class="region-dept-name")} '
                      f'<span style="color:#6B6B68;font-size:12px;">· décroche sur {html.escape(", ".join(faibles))}</span></span>'
                      f'<span style="color:#A51C30;font-weight:700;white-space:nowrap;">{float(r["score_global"]):.0f}<span style="color:#9C9A92;font-weight:400;">/100</span></span></div>')
        st.markdown(cards, unsafe_allow_html=True)

    # ── Éloignement routier : départements les plus concernés ────────────────
    st.markdown('<div class="section-header" style="margin-top:22px;"><div class="section-eyebrow">ÉLOIGNEMENT</div>'
                '<h2 class="section-title">Où vit-on loin <em>d’un généraliste ?</em></h2>'
                '<p class="section-lead">Part des habitants à plus de 15 minutes en voiture du généraliste le plus proche '
                '(INSEE 2025). En France, l’éloignement reste rare (moins de 1 %) et concentré dans quelques départements ruraux ou montagneux ; '
                'ailleurs, les difficultés d’accès relèvent de la capacité (APL, densités), pas de la distance.</p></div>', unsafe_allow_html=True)
    far = master.dropna(subset=["acces_mg_part_sup_15"]).sort_values("acces_mg_part_sup_15", ascending=False).head(8)
    def _tuile(r):
        pct = _fr(float(r["acces_mg_part_sup_15"]) * 100)
        pers = f"{int(float(r['acces_mg_pop_sup_15'])):,}".replace(",", "\u202f")
        return (f'<div class="prio-tile"><div class="prio-tile-lbl">{dept_link_html(str(r["dept"]), str(r["Nom du département"]), css_class="region-dept-name")}</div>'
                f'<div class="prio-tile-txt"><strong>{pct}\u202f%</strong> des habitants à plus de 15 min · {pers} personnes · APL {_fr(float(r["apl_dept"]))}</div></div>')
    tiles = "".join(_tuile(r) for _, r in far.iterrows())
    st.markdown(f'<div class="prio-intro prio-intro--4">{tiles}</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="sa-parcours" style="margin-top:8px;"><a class="primary" href="{internal_href("exploration")}" target="_self">Prioriser les territoires →</a>'
        f'<a href="{internal_href("comparer")}" target="_self">Comparer des territoires →</a>'
        f'<a href="{internal_href("acces")}" target="_self">Simuler une implantation →</a>'
        f'<a href="{internal_href("methodologie")}" target="_self">Méthodologie →</a></div>'
        f'<p class="sa-couverture" style="margin-top:10px;">Sources : DREES (APL {APL_MILLESIME}, RPPS 2026), INSEE (RP 2021 ; accès aux équipements 2025), '
        f'FINESS 2026, CNAM 2023, DVF 2025. Aucun indicateur national ne mesure l’accès effectif aux rendez-vous.</p>',
        unsafe_allow_html=True)
