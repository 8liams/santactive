"""Fiche région : vue agrégée + départements qui la composent."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..components import render_national_choropleth
from ..region_pilotage import (
    _patho_metrics,
    build_territoire_card,
    compute_dept_priorities,
    compute_leviers_action,
    compute_publics_prioritaires,
    compute_region_summary,
    compute_specialites_tension,
)
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
    render_priorites_action(region_depts, region_name, data)
    render_diagnostic_region(region_depts, region_name)
    render_region_map(region_depts, data.get("geojson"))
    render_ranking_depts(region_depts)


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


# ── Badges niveaux (pilotage ARS) ────────────────────────────────────────────

_LEVEL_BADGE: dict[str, str] = {
    "faible": "fav",
    "modérée": "inter",
    "forte": "crit",
    "très forte": "crit",
    "limité": "fav",
    "moyen": "inter",
    "élevé": "inter",
    "majeur": "crit",
    "difficile": "crit",
    "à consolider": "inter",
    "correcte": "inter",
    "favorable": "fav",
    "à surveiller": "fav",
    "prioritaire": "inter",
    "très prioritaire": "crit",
    "candidat expérimentation": "crit",
    "élevée": "inter",
    "majeure": "crit",
    "à étudier": "fav",
    "pertinent": "inter",
    "très pertinent": "inter",
}


def _region_pilotage_css() -> str:
    """Styles V2 — pilotage ARS, lecture rapide, responsive."""
    return """
<style>
.region-v2-summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
    gap: 20px;
    margin-bottom: 40px;
}
.region-v2-kpi {
    padding: 20px;
    background: #FAFAF8;
    border: 1px solid #E8E6DD;
    border-radius: 8px;
    min-width: 0;
}
.region-v2-kpi .label {
    display: block;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #9C9A92;
    margin-bottom: 10px;
    line-height: 1.4;
}
.region-v2-kpi .value {
    display: block;
    font-size: 20px;
    font-weight: 500;
    color: #0A1938;
    line-height: 1.3;
    word-wrap: break-word;
    overflow-wrap: anywhere;
}
.region-v2-kpi .value.text {
    font-size: 14px;
    font-weight: 400;
    line-height: 1.45;
}
.region-prio-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 8px; }
.region-prio-table-v2 { min-width: 480px; }
.region-prio-head-v2,
.region-prio-row-v2 {
    display: grid;
    grid-template-columns: 40px minmax(120px, 1fr) minmax(110px, 0.9fr) minmax(160px, 1.5fr);
    gap: 16px;
    padding: 14px 18px;
    align-items: center;
}
.region-prio-head-v2 {
    background: #F3F2EC;
    border-radius: 6px 6px 0 0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #6B6B68;
    text-transform: uppercase;
}
.region-prio-row-v2 {
    border-bottom: 1px solid #F0EDE5;
    text-decoration: none;
    color: inherit;
}
.region-prio-row-v2:hover { background: #FAFAF8; }
.region-prio-dept {
    font-size: 15px;
    font-weight: 500;
    color: #0A0A0A;
    word-wrap: break-word;
}
.region-prio-lecture {
    font-size: 13px;
    color: #6B6B68;
    line-height: 1.5;
}
.region-territoire-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr));
    gap: 20px;
    margin-top: 8px;
}
.region-territoire-card {
    background: white;
    border: 1px solid #E8E6DD;
    border-radius: 8px;
    padding: 20px;
    min-width: 0;
}
.region-territoire-card .card-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 18px;
    padding-bottom: 14px;
    border-bottom: 1px solid #F0EDE5;
}
.region-territoire-card .card-title {
    font-size: 17px;
    font-weight: 600;
    color: #0A1938;
}
.region-territoire-card .card-rang {
    font-size: 11px;
    font-weight: 700;
    color: #9C9A92;
    letter-spacing: 0.06em;
}
.region-card-block { margin-bottom: 16px; }
.region-card-block:last-child { margin-bottom: 0; }
.region-card-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #9C9A92;
    margin-bottom: 8px;
}
.region-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.region-tag {
    display: inline-block;
    font-size: 12px;
    line-height: 1.35;
    padding: 5px 10px;
    border-radius: 4px;
    background: #F3F2EC;
    color: #4A4A4A;
    word-break: break-word;
}
.region-tag.frag { background: #FEF3F3; color: #8B2635; }
.region-tag.atout { background: #F0F7F3; color: #1B5E3F; }
.region-tag.public { background: #EEF2FA; color: #1A3D8F; }
.region-tag.muted { background: #F3F2EC; color: #9C9A92; font-style: italic; }
.region-level-badge,
.region-badge-cell .fiche-zone-badge {
    display: inline-block;
    max-width: 100%;
    white-space: normal !important;
    line-height: 1.35;
    word-break: break-word;
}
.region-public-table-wrap { overflow-x: auto; margin-top: 8px; }
.region-public-table-v2 { min-width: 600px; }
.region-public-row-v2 {
    display: grid;
    grid-template-columns: minmax(140px, 1.2fr) minmax(90px, 0.8fr) minmax(120px, 1fr) minmax(90px, 0.7fr) minmax(100px, 0.9fr);
    gap: 14px;
    padding: 16px 18px;
    border-bottom: 1px solid #F0EDE5;
    align-items: start;
    font-size: 13px;
    line-height: 1.5;
}
.region-public-head-v2 {
    background: #F3F2EC;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #6B6B68;
    text-transform: uppercase;
    border-radius: 6px 6px 0 0;
}
.region-lever-list { display: flex; flex-direction: column; gap: 16px; margin-top: 8px; }
.region-lever-item {
    background: white;
    border: 1px solid #E8E6DD;
    border-radius: 8px;
    padding: 20px 22px;
}
.region-lever-flow {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
    gap: 12px;
    align-items: center;
    margin-bottom: 14px;
}
.region-lever-step {
    font-size: 12px;
    line-height: 1.45;
    padding: 10px 12px;
    border-radius: 6px;
    background: #FAFAF8;
    min-width: 0;
    word-wrap: break-word;
}
.region-lever-step.tension { border-left: 3px solid #A51C30; }
.region-lever-step.public { border-left: 3px solid #1A3D8F; }
.region-lever-step.action { border-left: 3px solid #1B5E3F; background: #F0F7F3; font-weight: 500; }
.region-lever-arrow { color: #C4C2B8; font-size: 16px; text-align: center; }
.region-lever-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 20px;
    font-size: 12px;
    color: #6B6B68;
    padding-top: 12px;
    border-top: 1px solid #F0EDE5;
}
.region-spec-table { min-width: 480px; }
.region-spec-head,
.region-spec-row {
    display: grid;
    grid-template-columns: minmax(120px, 1.3fr) 70px 70px minmax(100px, 1fr);
    gap: 12px;
    padding: 14px 18px;
    align-items: center;
}
.region-spec-head {
    background: #F3F2EC;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #6B6B68;
    text-transform: uppercase;
    border-radius: 6px 6px 0 0;
}
.region-spec-row { border-bottom: 1px solid #F0EDE5; font-size: 13px; }
@media screen and (max-width: 900px) {
    .region-lever-flow {
        grid-template-columns: 1fr;
    }
    .region-lever-arrow { display: none; }
}
@media screen and (max-width: 768px) {
    .region-prio-table-v2 { min-width: 100%; }
    .region-public-table-v2 { min-width: 520px; }
}
</style>
"""


def _level_badge(label: str) -> str:
    cls = _LEVEL_BADGE.get(label, "inter")
    return (
        f'<span class="fiche-zone-badge {cls} region-level-badge" '
        f'style="font-size:10px;padding:3px 8px;">{label}</span>'
    )


def _tags_html(items: list[str], css_class: str = "") -> str:
    if not items:
        return '<span class="region-tag muted">n.d.</span>'
    cls = f" {css_class}" if css_class else ""
    return "".join(f'<span class="region-tag{cls}">{x}</span>' for x in items)


def _fmt_pop(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")


def render_priorites_action(
    region_depts: pd.DataFrame,
    region_name: str,
    data: dict,
) -> None:
    """Pilotage ARS V2 : territoires → publics → problèmes → leviers."""
    region_code = str(region_depts.iloc[0].get("Code région", ""))

    st.markdown(_region_pilotage_css(), unsafe_allow_html=True)

    priorities = compute_dept_priorities(region_depts, data.get("patho"))
    delais_region = compute_specialites_tension(data.get("delais"), region_code)
    publics = compute_publics_prioritaires(region_depts, data.get("patho"), priorities)
    summary = compute_region_summary(
        priorities, region_depts, delais_region, publics=publics
    )
    leviers = compute_leviers_action(
        region_depts, priorities, data.get("patho"), delais_region
    )

    # ── En-tête pilotage ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">PILOTAGE TERRITORIAL</div>'
        '<h2 class="section-title">Où agir, pour qui, <em>comment.</em></h2>'
        '<p class="section-lead">Aide à la décision pour déployer une action publique, '
        'philanthropique ou une expérimentation de santé dans la région.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    pop_prio = summary.get("pop_territoires_prioritaires", 0)
    pop_prio_str = _fmt_pop(pop_prio) if pop_prio > 0 else "n.d."

    st.markdown(
        f'<div class="region-v2-summary">'
        f'<div class="region-v2-kpi">'
        f'<span class="label">Population en territoires prioritaires</span>'
        f'<span class="value">{pop_prio_str}</span>'
        f'</div>'
        f'<div class="region-v2-kpi">'
        f'<span class="label">Départements prioritaires</span>'
        f'<span class="value">{summary.get("nb_depts_prioritaires", 0)}</span>'
        f'</div>'
        f'<div class="region-v2-kpi">'
        f'<span class="label">Tension régionale principale</span>'
        f'<span class="value text">{summary["tension_principale"].capitalize()}.</span>'
        f'</div>'
        f'<div class="region-v2-kpi">'
        f'<span class="label">Public principal concerné</span>'
        f'<span class="value text">{summary.get("public_principal", "n.d.")}</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 1. Territoires prioritaires — tableau simplifié ───────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:8px;">'
        '<div class="section-eyebrow">ÉTAPE 1 — TERRITOIRES</div>'
        '<h2 class="section-title">Territoires <em>prioritaires.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    table_html = (
        '<div class="region-prio-table-wrap"><div class="region-prio-table-v2">'
        '<div class="region-prio-head-v2">'
        '<span>Rang</span><span>Département</span><span>Priorité</span>'
        '<span>Lecture rapide</span>'
        '</div>'
    )
    for _, row in priorities.iterrows():
        dept_code = row["dept"]
        rang = int(row["priorite_rang"])
        bg = (
            "#FEF9F9"
            if row["priorite"] in ("très prioritaire", "candidat expérimentation")
            else "white"
        )
        table_html += (
            f'<a href="?view=dept&dept_code={dept_code}" class="region-prio-row-v2" '
            f'style="background:{bg};">'
            f'<span style="font-size:13px;font-weight:700;color:#9C9A92;">{rang:02d}</span>'
            f'<span class="region-prio-dept">{row["Nom du département"]}</span>'
            f'<span>{_level_badge(row["priorite"])}</span>'
            f'<span class="region-prio-lecture">{row["lecture_rapide"]}</span>'
            f'</a>'
        )
    table_html += "</div></div>"
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Cartes territoires (top 3) ────────────────────────────────────────────
    top3 = priorities.head(3)
    if not top3.empty:
        st.markdown(
            '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
            'text-transform:uppercase;color:#9C9A92;margin:32px 0 16px;">'
            'Territoires à cibler en priorité</div>',
            unsafe_allow_html=True,
        )
        cards_html = '<div class="region-territoire-grid">'
        patho_map = _patho_metrics(
            data.get("patho"),
            region_depts["dept"].astype(str).str.zfill(2).tolist(),
        )

        for _, row in top3.iterrows():
            code = str(row["dept"]).zfill(2)
            profile = build_territoire_card(
                row, patho_map.get(code), region_depts
            )
            cards_html += (
                f'<div class="region-territoire-card">'
                f'<div class="card-head">'
                f'<span class="card-title">{row["Nom du département"]}</span>'
                f'<span class="card-rang">Rang {int(row["priorite_rang"]):02d}</span>'
                f'</div>'
                f'<div style="margin-bottom:16px;">{_level_badge(row["priorite"])}</div>'
                f'<div class="region-card-block">'
                f'<div class="region-card-label">Fragilités principales</div>'
                f'<div class="region-tags">{_tags_html(profile["fragilites"], "frag")}</div>'
                f'</div>'
                f'<div class="region-card-block">'
                f'<div class="region-card-label">Atouts mobilisables</div>'
                f'<div class="region-tags">{_tags_html(profile["atouts"], "atout")}</div>'
                f'</div>'
                f'<div class="region-card-block">'
                f'<div class="region-card-label">Public principal concerné</div>'
                f'<div class="region-tags">{_tags_html(profile["publics"], "public")}</div>'
                f'</div>'
                f'</div>'
            )
        cards_html += "</div>"
        st.markdown(cards_html, unsafe_allow_html=True)

    # ── 2. Publics prioritaires ───────────────────────────────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:56px;">'
        '<div class="section-eyebrow">ÉTAPE 2 — POPULATIONS</div>'
        '<h2 class="section-title">Publics <em>prioritaires.</em></h2>'
        '<p class="section-lead">Populations et pathologies qui justifient une intervention '
        '— données CNAM et INSEE.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not publics:
        st.info("Données CNAM ou démographiques insuffisantes pour identifier les publics prioritaires.")
    else:
        pub_html = (
            '<div class="region-public-table-wrap"><div class="region-public-table-v2">'
            '<div class="region-public-row-v2 region-public-head-v2">'
            '<span>Public / pathologie</span><span>Importance</span>'
            '<span>Départements concernés</span><span>Prévalence</span><span>Volume</span>'
            '</div>'
        )
        for pub in publics[:7]:
            depts_str = ", ".join(pub.get("depts", [])) or "n.d."
            pub_html += (
                f'<div class="region-public-row-v2">'
                f'<span style="font-weight:500;color:#0A1938;">{pub["label"]}</span>'
                f'<span style="color:#4A4A4A;">{pub.get("importance", pub.get("priorite", "n.d."))}</span>'
                f'<span style="color:#4A4A4A;">{depts_str}</span>'
                f'<span style="color:#6B6B68;">{pub.get("prev", "n.d.")}</span>'
                f'<span style="color:#6B6B68;">{pub.get("volume", "n.d.")}</span>'
                f'</div>'
            )
        pub_html += "</div></div>"
        st.markdown(pub_html, unsafe_allow_html=True)

    # ── 3. Problématiques majeures — spécialités sous tension ─────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:56px;">'
        '<div class="section-eyebrow">ÉTAPE 3 — PROBLÉMATIQUES</div>'
        '<h2 class="section-title">Parcours de soins <em>sous tension.</em></h2>'
        '<p class="section-lead">Délais régionaux DREES — {region_name}.</p>'
        '</div>'.format(region_name=region_name),
        unsafe_allow_html=True,
    )

    if delais_region.empty:
        st.info("Données régionales de délais indisponibles pour cette région.")
    else:
        spec_html = (
            '<div class="region-prio-table-wrap"><div class="region-spec-table">'
            '<div class="region-spec-head">'
            '<span>Spécialité</span>'
            '<span style="text-align:right;">Délai médian</span>'
            '<span style="text-align:right;">P75</span>'
            '<span>Levier recommandé</span>'
            '</div>'
        )
        for _, srow in delais_region.head(8).iterrows():
            p75 = srow.get("delai_jours_p75")
            p75_str = f"{int(p75)}\u202fj" if pd.notna(p75) else "n.d."
            spec_html += (
                f'<div class="region-spec-row">'
                f'<span style="font-weight:500;">{srow["specialite"]}</span>'
                f'<span style="text-align:right;font-weight:600;">'
                f'{int(srow["delai_jours_median"])}\u202fj</span>'
                f'<span style="text-align:right;color:#6B6B68;">{p75_str}</span>'
                f'<span style="color:#1B5E3F;font-weight:500;">'
                f'{srow.get("levier", "parcours coordonné")}</span>'
                f'</div>'
            )
        spec_html += "</div></div>"
        st.markdown(spec_html, unsafe_allow_html=True)

    # ── 4. Leviers d'action — problème → action ───────────────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:56px;">'
        '<div class="section-eyebrow">ÉTAPE 4 — ACTIONS</div>'
        '<h2 class="section-title">Leviers <em>recommandés.</em></h2>'
        '<p class="section-lead">De la tension observée à l\'action proposée — '
        'générés à partir du profil territorial de la région.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not leviers:
        st.info("Aucun levier identifié avec les données disponibles pour cette région.")
    else:
        lever_html = '<div class="region-lever-list">'
        for lev in leviers:
            depts_str = ", ".join(lev.get("depts", [])) or "n.d."
            lever_html += (
                f'<div class="region-lever-item">'
                f'<div class="region-lever-flow">'
                f'<div class="region-lever-step tension">'
                f'<strong style="display:block;font-size:9px;letter-spacing:0.08em;'
                f'text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">'
                f'Tension observée</strong>{lev.get("tension", "—")}'
                f'</div>'
                f'<div class="region-lever-arrow">→</div>'
                f'<div class="region-lever-step public">'
                f'<strong style="display:block;font-size:9px;letter-spacing:0.08em;'
                f'text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">'
                f'Public concerné</strong>{lev["public_cible"]}'
                f'</div>'
                f'<div class="region-lever-arrow">→</div>'
                f'<div class="region-lever-step action">'
                f'<strong style="display:block;font-size:9px;letter-spacing:0.08em;'
                f'text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">'
                f'Levier recommandé</strong>{lev["intitule"].capitalize()}'
                f'</div>'
                f'</div>'
                f'<div class="region-lever-meta">'
                f'<span><strong>Famille\u202f:</strong> {lev["famille"]}</span>'
                f'<span><strong>Territoires\u202f:</strong> {depts_str}</span>'
                f'<span>{_level_badge(lev["pertinence"])}</span>'
                f'</div>'
                f'</div>'
            )
        lever_html += "</div>"
        st.markdown(lever_html, unsafe_allow_html=True)

    # ── Note méthodologique ───────────────────────────────────────────────────
    st.markdown(
        '<div style="margin-top:40px;padding:16px 20px;background:#F3F2EC;'
        'border-radius:6px;font-size:12px;color:#6B6B68;line-height:1.6;">'
        '<strong style="color:#2B2B2B;">Note méthodologique.</strong> '
        'Cette priorisation est un outil d\'aide à la décision. Elle ne remplace pas '
        'l\'expertise locale d\'une ARS. Elle croise la fragilité sanitaire, le volume '
        'de population concernée et la faisabilité de déploiement à partir de données ouvertes.'
        '</div>',
        unsafe_allow_html=True,
    )
