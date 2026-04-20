"""Fiche région : vue agrégée + départements qui la composent."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..components import render_national_choropleth, zone_badge_html
from ..config import CMAP, PALETTE
from ..router import navigate


def render(data: dict) -> None:
    region_code = st.session_state.get("region_code", "")
    master: pd.DataFrame = data["master"]

    region_depts = master[master["Code région"].astype(str) == str(region_code)].copy()
    if region_depts.empty:
        st.error(f"Région introuvable ({region_code}).")
        if st.button("← Retour accueil"):
            navigate("home")
        return

    region_name = region_depts.iloc[0]["Nom de la région"]

    # ── TOPBAR ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="fiche-topbar"><div class="breadcrumb">'
        f'<a href="?view=home">Accueil</a>'
        f'<span class="sep">›</span>'
        f'<span class="current">{region_name}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── HEADER ────────────────────────────────────────────────────────────────
    pop_tot = region_depts["population_num"].sum()
    nb_depts = len(region_depts)
    nb_crit = int((region_depts["zone_short"] == "Critique").sum())

    zone_region = (
        "Critique" if nb_crit >= nb_depts / 2
        else ("Intermédiaire" if nb_crit > 0 else "Favorable")
    )
    badge_class = {"Critique": "crit", "Intermédiaire": "inter",
                   "Favorable": "fav"}.get(zone_region, "")

    score_moyen = region_depts["score_global"].mean()
    score_str = f"{score_moyen:.1f}" if pd.notna(score_moyen) else "—"

    apl_med = (
        region_depts["apl_median_dept"].median()
        if "apl_median_dept" in region_depts.columns
        else None
    )
    apl_str = f"{apl_med:.1f}" if apl_med is not None and pd.notna(apl_med) else "—"

    ecart = region_depts["score_global"].max() - region_depts["score_global"].min()
    ecart_str = f"{ecart:.0f}" if pd.notna(ecart) else "—"

    pop_fmt = f"{int(pop_tot):,}".replace(",", "\u202f") if pd.notna(pop_tot) else "—"

    st.markdown(
        f'<div class="fiche-header">'
        f'<div class="fiche-eyebrow">'
        f'<span class="code">RÉGION</span>'
        f'<span class="dot"></span>'
        f'<span class="region">{nb_depts} départements</span>'
        f'<span class="dot"></span>'
        f'<span class="region">{pop_fmt} habitants</span>'
        f'</div>'
        f'<div class="fiche-title-row">'
        f'<h1 class="fiche-title">{region_name}</h1>'
        f'<div class="fiche-zone-badge {badge_class}">'
        f'{nb_crit} dépt{"s" if nb_crit > 1 else ""} '
        f'critique{"s" if nb_crit > 1 else ""}'
        f'</div></div>'
        f'<div class="fiche-meta">'
        f'<div class="fiche-meta-item">'
        f'<span class="label">SCORE MOYEN RÉGION</span>'
        f'<span class="value">{score_str}<span class="small">/100</span></span>'
        f'</div>'
        f'<div class="fiche-meta-item">'
        f'<span class="label">APL MÉDIAN</span>'
        f'<span class="value">{apl_str}<span class="small">/hab.</span></span>'
        f'</div>'
        f'<div class="fiche-meta-item">'
        f'<span class="label">ÉCART INTRA-RÉGIONAL</span>'
        f'<span class="value">{ecart_str}<span class="small">pts</span></span>'
        f'</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── SECTIONS ──────────────────────────────────────────────────────────────
    render_diagnostic_region(region_depts, region_name)
    render_region_map(region_depts, data.get("geojson"))
    render_ranking_depts(region_depts)
    render_reco_ars(region_depts, region_name)


# ──────────────────────────────────────────────────────────────────────────────

def render_diagnostic_region(region_depts: pd.DataFrame, region_name: str) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">DIAGNOSTIC RÉGIONAL</div>'
        '<h2 class="section-title">Disparités <em>internes</em> et leviers d\'action.</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    valid = region_depts.dropna(subset=["score_global"])
    if valid.empty:
        st.info("Données insuffisantes pour ce diagnostic.")
        return

    worst = valid.sort_values("score_global").iloc[0]
    best  = valid.sort_values("score_global", ascending=False).iloc[0]
    nb_crit = int((region_depts["zone_short"] == "Critique").sum())

    if nb_crit > 0:
        phrase = (
            f"La région <strong>{region_name}</strong> compte "
            f"<strong>{nb_crit} département{'s' if nb_crit > 1 else ''} en zone "
            f"critique</strong>, avec <em>{worst['Nom du département']}</em> au plus "
            f"bas ({worst['score_global']:.1f}/100) et "
            f"<em>{best['Nom du département']}</em> au plus haut "
            f"({best['score_global']:.1f}/100)."
        )
    else:
        phrase = (
            f"La région <strong>{region_name}</strong> présente une situation homogène. "
            f"{worst['Nom du département']} reste le plus vulnérable "
            f"({worst['score_global']:.1f}/100), {best['Nom du département']} "
            f"le plus favorable ({best['score_global']:.1f}/100)."
        )

    st.markdown(
        f'<div class="diagnostic-prose" style="max-width:900px;">{phrase}</div>',
        unsafe_allow_html=True,
    )


def render_region_map(region_depts: pd.DataFrame, geojson) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ZOOM RÉGION</div>'
        '<h2 class="section-title">Les départements <em>qui composent la région.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not geojson:
        st.warning("Carte indisponible.")
        return

    dept_codes = set(region_depts["dept"].astype(str).tolist())
    filtered_gj = {
        "type": "FeatureCollection",
        "features": [
            f for f in geojson["features"]
            if f["properties"]["code"] in dept_codes
        ],
    }

    region_code_val = str(region_depts.iloc[0].get("Code région", ""))
    event = render_national_choropleth(
        master=region_depts,
        geojson=filtered_gj,
        metric="score_global",
        colormap_name="score",
        height=500,
        key=f"region_map_{region_code_val}",
    )

    if event and event.get("last_active_drawing"):
        props = event["last_active_drawing"].get("properties", {})
        code = props.get("code")
        if code:
            navigate("dept", dept_code=str(code))


def render_ranking_depts(region_depts: pd.DataFrame) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">CLASSEMENT INTRA-RÉGIONAL</div>'
        '<h2 class="section-title">Du plus <em>critique</em> au plus favorable.</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    sorted_depts = region_depts.sort_values("score_global", na_position="last").reset_index(drop=True)

    # En-tête + lignes : tableau HTML pur, lien <a href> pour la navigation
    table_html = (
        '<div style="display:grid;'
        'grid-template-columns:36px 1fr 60px 110px 80px 100px 48px;'
        'gap:0 12px;padding:8px 16px;background:#F3F2EC;border-radius:4px 4px 0 0;'
        'font-size:11px;font-weight:700;letter-spacing:0.1em;color:#6B6B68;'
        'text-transform:uppercase;">'
        '<span>#</span><span>D\u00e9partement</span><span>Code</span>'
        '<span>Zone</span>'
        '<span style="text-align:right;">Score</span>'
        '<span style="text-align:right;">Population</span>'
        '<span></span>'
        '</div>'
    )

    for i, (_, d) in enumerate(sorted_depts.iterrows(), 1):
        zone      = d.get("zone_short", "\u2014")
        score     = d.get("score_global")
        score_str = f"{score:.1f}" if pd.notna(score) else "\u2014"
        pop       = d.get("population_num", 0)
        pop_str   = f"{int(pop):,}".replace(",", "\u202f") if pd.notna(pop) else "\u2014"
        dept_code = d["dept"]
        dept_name = d["Nom du d\u00e9partement"]

        badge_cls = {"Critique": "crit", "Interm\u00e9diaire": "inter",
                     "Favorable": "fav"}.get(zone, "")
        score_color = (
            "#A51C30" if zone == "Critique"
            else ("#E5B04A" if zone == "Interm\u00e9diaire" else "#1B5E3F")
        )
        bg = "#FEF9F9" if zone == "Critique" else "white"

        table_html += (
            f'<a href="?view=dept&dept_code={dept_code}" '
            f'style="display:grid;text-decoration:none;cursor:pointer;'
            f'grid-template-columns:36px 1fr 60px 110px 80px 100px 48px;'
            f'gap:0 12px;padding:10px 16px;background:{bg};'
            f'border-bottom:1px solid #F0EDE5;align-items:center;">'
            f'<span style="font-size:12px;font-weight:700;color:#9C9A92;">{i:02d}</span>'
            f'<span style="font-size:14px;font-weight:500;color:#0A0A0A;">{dept_name}</span>'
            f'<span style="font-size:12px;color:#9C9A92;">{dept_code}</span>'
            f'<span><span class="fiche-zone-badge {badge_cls}" '
            f'style="font-size:10px;padding:3px 8px;">{zone}</span></span>'
            f'<span style="text-align:right;font-size:14px;font-weight:600;color:{score_color};">'
            f'{score_str}<span style="font-size:10px;color:#9C9A92;font-weight:400;">/100</span></span>'
            f'<span style="text-align:right;font-size:12px;color:#6B6B68;">{pop_str}</span>'
            f'<span style="text-align:right;font-size:13px;color:#1A3D8F;font-weight:500;">\u2192</span>'
            f'</a>'
        )

    st.markdown(table_html, unsafe_allow_html=True)


def render_reco_ars(region_depts: pd.DataFrame, region_name: str) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">PILOTAGE ARS</div>'
        '<h2 class="section-title">Priorités d\'allocation <em>FIR</em>.</h2>'
        '<p class="section-lead">Recommandations politiques pour l\'Agence Régionale '
        'de Santé, classées par levier budgétaire.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    recos: list[dict] = []

    # P1 — Concentration FIR sur les zones critiques
    top_crit = (
        region_depts[region_depts["zone_short"] == "Critique"]
        .sort_values("score_global")
        .head(3)
    )
    if not top_crit.empty:
        names = ", ".join(top_crit["Nom du département"].tolist())
        nc = len(top_crit)
        recos.append({
            "priority": "P1",
            "title": (
                f"Concentrer l'enveloppe FIR 2026 sur {nc} territoire"
                f"{'s' if nc > 1 else ''} critique{'s' if nc > 1 else ''}."
            ),
            "prose": (
                f"{names} présentent les scores les plus dégradés. "
                "Prioriser les subventions à l'installation, les maisons de santé "
                "pluridisciplinaires et les dispositifs de télémédecine."
            ),
            "stats": [
                (str(nc), "Dépt. prioritaires"),
                ("FIR", "Enveloppe cible"),
                ("12-24 mois", "Horizon"),
            ],
        })

    # P2 — Plan gériatrique si département avec forte part 65+
    if "pct_plus_65" in region_depts.columns:
        top65 = region_depts.sort_values("pct_plus_65", ascending=False).iloc[0]
        if pd.notna(top65.get("pct_plus_65")) and top65["pct_plus_65"] > 22:
            recos.append({
                "priority": "P2",
                "title": f"Plan gériatrique spécifique pour {top65['Nom du département']}.",
                "prose": (
                    f"{top65['pct_plus_65']:.1f}% de +65 ans. "
                    "Conventionnement EHPAD + HAD, parcours de soins gériatriques, "
                    "dépistage des fragilités."
                ),
                "stats": [
                    (f"{top65['pct_plus_65']:.0f}\u202f%", "Part des 65+"),
                    ("EHPAD+HAD", "Dispositif"),
                ],
            })

    # P2 — Délais RDV spécialistes
    recos.append({
        "priority": "P2",
        "title": "Plan régional de réduction des délais RDV spécialistes.",
        "prose": (
            "Cibler ophtalmologie et psychiatrie, les deux spécialités avec les "
            "délais les plus dégradés. Téléconsultation + centres de santé ARS."
        ),
        "stats": [
            ("Ophta + Psy", "Spé. ciblées"),
            ("-30\u202f%", "Objectif délais"),
            ("24 mois", "Horizon"),
        ],
    })

    for i in range(0, len(recos), 2):
        c1, c2 = st.columns(2)
        for j, col in enumerate([c1, c2]):
            if i + j >= len(recos):
                break
            reco = recos[i + j]
            with col:
                stats_html = "".join(
                    f'<div class="reco-stat">'
                    f'<span class="val">{v}</span>'
                    f'<span class="lbl">{lbl}</span>'
                    f'</div>'
                    for v, lbl in reco.get("stats", [])
                )
                st.markdown(
                    f'<div class="reco-card">'
                    f'<span class="reco-priority {reco["priority"].lower()}">'
                    f'Priorité {reco["priority"][1]}'
                    f'</span>'
                    f'<div class="reco-number">{i + j + 1:02d} —</div>'
                    f'<div class="reco-title">{reco["title"]}</div>'
                    f'<div class="reco-prose">{reco["prose"]}</div>'
                    f'<div class="reco-stats">{stats_html}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
