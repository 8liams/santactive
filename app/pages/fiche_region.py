"""Fiche région : vue agrégée + départements qui la composent."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..components import render_national_choropleth
from ..region_pilotage import (
    compute_dept_priorities,
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
    render_diagnostic_region(region_depts, region_name)
    render_priorites_action(region_depts, region_name, data)
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
}


def _level_badge(label: str) -> str:
    cls = _LEVEL_BADGE.get(label, "inter")
    return (
        f'<span class="fiche-zone-badge {cls}" '
        f'style="font-size:10px;padding:3px 8px;white-space:nowrap;">{label}</span>'
    )


def render_priorites_action(
    region_depts: pd.DataFrame,
    region_name: str,
    data: dict,
) -> None:
    """Bloc pilotage ARS : fragilité, impact, faisabilité, priorité."""
    region_code = str(region_depts.iloc[0].get("Code région", ""))

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">PILOTAGE ARS</div>'
        '<h2 class="section-title">Priorités d\'action <em>régionales.</em></h2>'
        '<p class="section-lead">Repérer les territoires où une action publique ou '
        'philanthropique peut être utile, ciblée et déployable.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    priorities = compute_dept_priorities(region_depts, data.get("patho"))
    delais_region = compute_specialites_tension(data.get("delais"), region_code)
    summary = compute_region_summary(priorities, region_depts, delais_region)

    # ── Résumé régional ───────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));'
        f'gap:16px;margin-bottom:32px;">'
        f'<div class="fiche-meta-item" style="padding:16px;background:#FAFAF8;'
        f'border:1px solid #E8E6DD;border-radius:6px;">'
        f'<span class="label">DÉPARTEMENT LE PLUS PRIORITAIRE</span>'
        f'<span class="value" style="font-size:18px;">{summary["dept_top"]}</span>'
        f'</div>'
        f'<div class="fiche-meta-item" style="padding:16px;background:#FAFAF8;'
        f'border:1px solid #E8E6DD;border-radius:6px;">'
        f'<span class="label">DÉPARTEMENTS PRIORITAIRES</span>'
        f'<span class="value">{summary["nb_prioritaires"]}</span>'
        f'</div>'
        f'<div class="fiche-meta-item" style="padding:16px;background:#FAFAF8;'
        f'border:1px solid #E8E6DD;border-radius:6px;">'
        f'<span class="label">CANDIDATS EXPÉRIMENTATION</span>'
        f'<span class="value">{summary["nb_experimentation"]}</span>'
        f'</div>'
        f'<div class="fiche-meta-item" style="padding:16px;background:#FAFAF8;'
        f'border:1px solid #E8E6DD;border-radius:6px;">'
        f'<span class="label">TENSION RÉGIONALE PRINCIPALE</span>'
        f'<span class="value" style="font-size:14px;line-height:1.4;">'
        f'{summary["tension_principale"].capitalize()}.</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Tableau de priorisation ───────────────────────────────────────────────
    st.markdown(
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#9C9A92;margin:0 0 12px;">'
        'TABLEAU DE PRIORISATION</div>',
        unsafe_allow_html=True,
    )

    cols = (
        "40px 1.2fr 90px 88px 88px 88px 110px 1.4fr"
    )
    table_html = (
        f'<div class="sa-tbl-scroll"><div style="min-width:920px;">'
        f'<div style="display:grid;grid-template-columns:{cols};'
        f'gap:0 10px;padding:8px 16px;background:#F3F2EC;border-radius:4px 4px 0 0;'
        f'font-size:10px;font-weight:700;letter-spacing:0.08em;color:#6B6B68;'
        f'text-transform:uppercase;align-items:center;">'
        f'<span>Rang</span><span>Département</span><span>Zone</span>'
        f'<span>Fragilité</span><span>Impact</span><span>Faisabilité</span>'
        f'<span>Priorité</span><span>Lecture rapide</span>'
        f'</div>'
    )

    for _, row in priorities.iterrows():
        dept_code = row["dept"]
        dept_name = row["Nom du département"]
        zone = str(row.get("zone_short", "—"))
        zone_cls = {"Critique": "crit", "Intermédiaire": "inter", "Favorable": "fav"}.get(zone, "")
        rang = int(row["priorite_rang"])
        bg = "#FEF9F9" if row["priorite"] in ("très prioritaire", "candidat expérimentation") else "white"

        table_html += (
            f'<a href="?view=dept&dept_code={dept_code}" '
            f'style="display:grid;grid-template-columns:{cols};gap:0 10px;'
            f'padding:10px 16px;background:{bg};border-bottom:1px solid #F0EDE5;'
            f'text-decoration:none;color:inherit;align-items:center;">'
            f'<span style="font-size:12px;font-weight:700;color:#9C9A92;">{rang:02d}</span>'
            f'<span style="font-size:14px;font-weight:500;color:#0A0A0A;">{dept_name}</span>'
            f'<span><span class="fiche-zone-badge {zone_cls}" '
            f'style="font-size:10px;padding:3px 8px;">{zone}</span></span>'
            f'<span>{_level_badge(row["fragilite"])}</span>'
            f'<span>{_level_badge(row["impact"])}</span>'
            f'<span>{_level_badge(row["faisabilite"])}</span>'
            f'<span>{_level_badge(row["priorite"])}</span>'
            f'<span style="font-size:12px;color:#6B6B68;line-height:1.4;">'
            f'{row["lecture_rapide"]}</span>'
            f'</a>'
        )

    table_html += "</div></div>"
    st.markdown(table_html, unsafe_allow_html=True)

    # ── Focus top 3 ─────────────────────────────────────────────────────────
    top3 = priorities.head(3)
    if not top3.empty:
        st.markdown(
            '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
            'text-transform:uppercase;color:#9C9A92;margin:40px 0 16px;">'
            'FOCUS — TROIS TERRITOIRES À TRAITER EN PRIORITÉ</div>',
            unsafe_allow_html=True,
        )
        cols_ui = st.columns(min(3, len(top3)))
        for i, (_, row) in enumerate(top3.iterrows()):
            with cols_ui[i]:
                raisons_html = "".join(
                    f'<li style="margin-bottom:6px;">{r}</li>'
                    for r in row.get("raisons", [])
                )
                st.markdown(
                    f'<div class="reco-card">'
                    f'<span class="reco-priority p1">Rang {int(row["priorite_rang"]):02d}</span>'
                    f'<div class="reco-title">{row["Nom du département"]}</div>'
                    f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin:12px 0;">'
                    f'{_level_badge(row["priorite"])}'
                    f'{_level_badge(row["fragilite"])}'
                    f'{_level_badge(row["impact"])}'
                    f'{_level_badge(row["faisabilite"])}'
                    f'</div>'
                    f'<ul style="font-size:12px;color:#4A4A4A;line-height:1.55;'
                    f'padding-left:18px;margin:0 0 14px;">{raisons_html}</ul>'
                    f'<div class="reco-prose">{row["synthese"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Spécialités sous tension ──────────────────────────────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:48px;">'
        '<div class="section-eyebrow">PARCOURS DE SOINS</div>'
        '<h2 class="section-title">Spécialités <em>sous tension</em> dans la région.</h2>'
        '<p class="section-lead">Délais médians DREES par spécialité — données régionales '
        f'{region_name}.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    if delais_region.empty:
        st.info(
            "Données régionales de délais non disponibles pour cette région. "
            "Les estimations départementales restent accessibles via chaque fiche département."
        )
    else:
        spec_cols = (
            "1.4fr 80px 80px 100px"
        )
        spec_html = (
            f'<div class="sa-tbl-scroll"><div style="min-width:480px;">'
            f'<div style="display:grid;grid-template-columns:{spec_cols};'
            f'gap:0 12px;padding:8px 16px;background:#F3F2EC;border-radius:4px 4px 0 0;'
            f'font-size:10px;font-weight:700;letter-spacing:0.08em;color:#6B6B68;'
            f'text-transform:uppercase;">'
            f'<span>Spécialité</span>'
            f'<span style="text-align:right;">Médian</span>'
            f'<span style="text-align:right;">P75</span>'
            f'<span>Tension</span>'
            f'</div>'
        )
        for _, srow in delais_region.iterrows():
            p75 = srow.get("delai_jours_p75")
            p75_str = f"{int(p75)}\u202fj" if pd.notna(p75) else "—"
            spec_html += (
                f'<div style="display:grid;grid-template-columns:{spec_cols};'
                f'gap:0 12px;padding:10px 16px;background:white;'
                f'border-bottom:1px solid #F0EDE5;align-items:center;">'
                f'<span style="font-size:14px;font-weight:500;">{srow["specialite"]}</span>'
                f'<span style="text-align:right;font-size:14px;font-weight:600;">'
                f'{int(srow["delai_jours_median"])}\u202fj</span>'
                f'<span style="text-align:right;font-size:12px;color:#6B6B68;">{p75_str}</span>'
                f'<span>{_level_badge(srow["tension"])}</span>'
                f'</div>'
            )
        spec_html += "</div></div>"
        st.markdown(spec_html, unsafe_allow_html=True)

    # ── Note méthodologique ───────────────────────────────────────────────────
    st.markdown(
        '<div style="margin-top:24px;padding:14px 18px;background:#F3F2EC;'
        'border-radius:4px;font-size:12px;color:#6B6B68;line-height:1.6;">'
        '<strong style="color:#2B2B2B;">Note méthodologique.</strong> '
        'Cette priorisation est un outil d\'aide à la décision. Elle ne remplace pas '
        'l\'expertise locale d\'une ARS. Elle croise la fragilité sanitaire, le volume '
        'de population concernée et la faisabilité de déploiement à partir de données ouvertes.'
        '</div>',
        unsafe_allow_html=True,
    )
