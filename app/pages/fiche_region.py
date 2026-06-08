"""Fiche région : outil d'aide à la décision ARS."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..action_impact import (
    project_levier_amplitude_region,
    render_amplitude_region_html,
)
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

# Affichage uniquement — les calculs internes restent inchangés
_PRIORITE_DISPLAY: dict[str, tuple[str, str]] = {
    "candidat expérimentation": ("Priorité immédiate", "crit"),
    "très prioritaire": ("Priorité forte", "crit"),
    "prioritaire": ("Priorité secondaire", "inter"),
    "à surveiller": ("Surveillance", "fav"),
}

_PUBLIC_SHORT: dict[str, str] = {
    "Seniors (65 ans et plus)": "Seniors",
    "Maladies cardiovasculaires": "Maladies cardiovasculaires",
    "Maladies psychiatriques": "Santé mentale",
    "Maladies respiratoires chroniques": "Maladies respiratoires",
    "Maladies neurologiques ou dégénératives": "Neurologie",
    "Diabète": "Diabète",
    "Cancers": "Cancers",
}


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
    region_code_val = str(region_depts.iloc[0].get("Code région", ""))

    priorities = compute_dept_priorities(region_depts, data.get("patho"))
    delais_region = compute_specialites_tension(data.get("delais"), region_code_val)
    publics = compute_publics_prioritaires(region_depts, data.get("patho"), priorities)
    summary = compute_region_summary(
        priorities, region_depts, delais_region, publics=publics
    )
    leviers = compute_leviers_action(
        region_depts, priorities, data.get("patho"), delais_region
    )

    render_topbar(region_name)
    render_hero(region_depts, region_name, summary, publics)
    render_ou_agir(priorities, region_depts, data)
    render_pour_qui(publics)
    render_comment_agir(leviers, region_depts, data, region_name)
    render_donnees_detaillees(
        region_depts, region_name, data, delais_region, priorities
    )


# ── Bloc 1 — Contexte régional ───────────────────────────────────────────────

def render_topbar(region_name: str) -> None:
    st.markdown(
        f'<div class="fiche-topbar"><div class="breadcrumb">'
        f'<a href="?view=home">Accueil</a>'
        f'<span class="sep">›</span>'
        f'<span class="current">{region_name}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _generate_region_synthesis(
    region_depts: pd.DataFrame,
    region_name: str,
    summary: dict,
    publics: list[dict],
) -> str:
    """Synthèse dynamique spécifique à la région."""
    nb_depts = len(region_depts)
    pct65_med = pd.to_numeric(region_depts.get("pct_plus_65"), errors="coerce").median()
    ecart = (
        region_depts["score_global"].max() - region_depts["score_global"].min()
    )
    nb_desert = int(
        (pd.to_numeric(region_depts["apl_median_dept"], errors="coerce") < 2.5).sum()
    )
    nb_crit = int((region_depts["zone_short"] == "Critique").sum())

    if pd.notna(pct65_med) and pct65_med > 24:
        lead = (
            f"<strong>{region_name}</strong> est marquée par un "
            f"<strong>vieillissement démographique important</strong>"
            f" ({pct65_med:.0f}\u202f% de seniors en médiane)."
        )
    elif nb_desert >= max(1, nb_depts // 3):
        lead = (
            f"<strong>{region_name}</strong> se caractérise par une "
            f"<strong>faible accessibilité aux soins de ville</strong> "
            f"sur {nb_desert} département{'s' if nb_desert > 1 else ''}."
        )
    elif pd.notna(ecart) and ecart > 18:
        lead = (
            f"<strong>{region_name}</strong> présente "
            f"<strong>de fortes disparités territoriales</strong> "
            f"entre départements (écart de {ecart:.0f} points)."
        )
    elif nb_crit == 0:
        lead = (
            f"<strong>{region_name}</strong> affiche un profil "
            f"<strong>plutôt homogène</strong> à l'échelle régionale."
        )
    else:
        lead = (
            f"<strong>{region_name}</strong> concentre des enjeux sanitaires "
            f"sur <strong>{nb_crit} département{'s' if nb_crit > 1 else ''}</strong> "
            f"en zone critique."
        )

    tension = summary.get("tension_principale", "")
    public = summary.get("public_principal", "n.d.")

    detail = f" {tension.capitalize()}."
    if public != "n.d.":
        detail += f" Public clé\u202f: <em>{public}</em>."

    patho_labels = [
        _PUBLIC_SHORT.get(p["label"], p["label"])
        for p in publics[:2]
        if p.get("type") == "pathologie CNAM"
    ]
    if patho_labels:
        detail += f" Pression sur <em>{' et '.join(patho_labels)}</em>."

    return lead + detail


def render_hero(
    region_depts: pd.DataFrame,
    region_name: str,
    summary: dict,
    publics: list[dict],
) -> None:
    pop_tot = region_depts["population_num"].sum()
    nb_depts = len(region_depts)
    nb_crit = int((region_depts["zone_short"] == "Critique").sum())

    zone_region = (
        "Critique" if nb_crit >= nb_depts / 2
        else ("Intermédiaire" if nb_crit > 0 else "Favorable")
    )
    badge_class = {"Critique": "crit", "Intermédiaire": "inter",
                   "Favorable": "fav"}.get(zone_region, "")

    apl_med = region_depts["apl_median_dept"].median()
    apl_str = f"{apl_med:.1f}" if pd.notna(apl_med) else "—"

    ecart = region_depts["score_global"].max() - region_depts["score_global"].min()
    ecart_str = f"{ecart:.0f}" if pd.notna(ecart) else "—"

    pop_fmt = f"{int(pop_tot):,}".replace(",", "\u202f") if pd.notna(pop_tot) else "—"

    st.markdown(
        f'<div class="fiche-header">'
        f'<div class="fiche-eyebrow">'
        f'<span class="code">RÉGION</span>'
        f'</div>'
        f'<div class="fiche-title-row">'
        f'<h1 class="fiche-title">{region_name}</h1>'
        f'<div class="fiche-zone-badge {badge_class}">'
        f'{nb_crit} dépt{"s" if nb_crit > 1 else ""} '
        f'critique{"s" if nb_crit > 1 else ""}'
        f'</div></div>'
        f'<div class="fiche-meta">'
        f'<div class="fiche-meta-item">'
        f'<span class="label">DÉPARTEMENTS</span>'
        f'<span class="value">{nb_depts}</span>'
        f'</div>'
        f'<div class="fiche-meta-item">'
        f'<span class="label">POPULATION</span>'
        f'<span class="value">{pop_fmt}</span>'
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

    synthesis = _generate_region_synthesis(
        region_depts, region_name, summary, publics
    )
    st.markdown(
        f'<div class="diagnostic-prose" style="max-width:900px;margin-bottom:48px;">'
        f'{synthesis}</div>',
        unsafe_allow_html=True,
    )


# ── Bloc 2 — Où agir ? ───────────────────────────────────────────────────────

def _priorite_badge(internal: str) -> str:
    label, cls = _PRIORITE_DISPLAY.get(internal, ("Surveillance", "fav"))
    return (
        f'<span class="fiche-zone-badge {cls}" '
        f'style="font-size:10px;padding:3px 8px;">{label}</span>'
    )


def _short_raison(text: str) -> str:
    """Raccourcit une raison pour l'affichage."""
    low = text.lower()
    if "désert médical" in low or ("apl" in low and "2" in low):
        return "Désert médical"
    if "communes" in low and "15" in low:
        return "Communes éloignées des soins"
    if "65 ans" in low or "seniors" in low:
        return "Forte part de seniors"
    if "accès aux soins dégradé" in low:
        return "Accès aux soins dégradé"
    if "offre hospitalière" in low or "structures" in low:
        return "Offre hospitalière limitée"
    if "temps d'accès" in low:
        return "Temps d'accès élevé"
    if "prévalence" in low:
        return text.split(" — ")[-1][:50] if " — " in text else text[:50]
    if " — " in text:
        return text.split(" — ")[0][:55]
    return text[:55]


def render_ou_agir(
    priorities: pd.DataFrame,
    region_depts: pd.DataFrame,
    data: dict,
) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">OÙ AGIR</div>'
        '<h2 class="section-title">Territoires <em>prioritaires.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    cols = "40px 1fr 130px 1.4fr"
    table_html = (
        f'<div class="sa-tbl-scroll"><div style="min-width:520px;">'
        f'<div style="display:grid;grid-template-columns:{cols};gap:0 14px;'
        f'padding:10px 16px;background:#F3F2EC;border-radius:4px 4px 0 0;'
        f'font-size:10px;font-weight:700;letter-spacing:0.08em;color:#6B6B68;'
        f'text-transform:uppercase;">'
        f'<span>Rang</span><span>Département</span><span>Priorité</span>'
        f'<span>Lecture rapide</span>'
        f'</div>'
    )

    for _, row in priorities.iterrows():
        dept_code = row["dept"]
        rang = int(row["priorite_rang"])
        internal = row["priorite"]
        label, _ = _PRIORITE_DISPLAY.get(internal, ("Surveillance", "fav"))
        bg = "#FEF9F9" if label in ("Priorité immédiate", "Priorité forte") else "white"

        table_html += (
            f'<a href="?view=dept&dept_code={dept_code}" '
            f'style="display:grid;grid-template-columns:{cols};gap:0 14px;'
            f'padding:12px 16px;background:{bg};border-bottom:1px solid #F0EDE5;'
            f'text-decoration:none;color:inherit;align-items:center;">'
            f'<span style="font-size:12px;font-weight:700;color:#9C9A92;">{rang:02d}</span>'
            f'<span style="font-size:14px;font-weight:500;">{row["Nom du département"]}</span>'
            f'<span>{_priorite_badge(internal)}</span>'
            f'<span style="font-size:12px;color:#6B6B68;line-height:1.45;">'
            f'{row["lecture_rapide"]}</span>'
            f'</a>'
        )

    table_html += "</div></div>"
    st.markdown(table_html, unsafe_allow_html=True)

    # Focus top 3
    top3 = priorities.head(3)
    if top3.empty:
        return

    st.markdown(
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#9C9A92;margin:36px 0 16px;">'
        'Pourquoi ces territoires ressortent</div>',
        unsafe_allow_html=True,
    )

    patho_map = _patho_metrics(
        data.get("patho"),
        region_depts["dept"].astype(str).str.zfill(2).tolist(),
    )

    cols_ui = st.columns(min(3, len(top3)))
    for i, (_, row) in enumerate(top3.iterrows()):
        code = str(row["dept"]).zfill(2)
        profile = build_territoire_card(row, patho_map.get(code), region_depts)
        public = profile["publics"][0] if profile["publics"] else "—"
        raisons = [_short_raison(r) for r in row.get("raisons", [])[:3]]
        raisons_html = "".join(
            f'<li style="margin-bottom:6px;font-size:13px;color:#4A4A4A;">{r}</li>'
            for r in raisons
        )
        synthese = str(row.get("lecture_rapide", ""))

        with cols_ui[i]:
            st.markdown(
                f'<div class="reco-card p{i + 1}">'
                f'<span class="reco-priority p{i + 1}">Rang {int(row["priorite_rang"]):02d}</span>'
                f'<div class="reco-title">{row["Nom du département"]}</div>'
                f'<ul style="padding-left:18px;margin:12px 0;">{raisons_html}</ul>'
                f'<div style="font-size:11px;color:#9C9A92;margin-bottom:8px;">'
                f'PUBLIC\u202f: {public}</div>'
                f'<div class="reco-prose" style="font-size:13px;">{synthese}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Bloc 3 — Pour qui agir ? ──────────────────────────────────────────────────

def render_pour_qui(publics: list[dict]) -> None:
    st.markdown(
        '<div class="section-header" style="margin-top:56px;">'
        '<div class="section-eyebrow">POUR QUI AGIR</div>'
        '<h2 class="section-title">Publics <em>prioritaires.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not publics:
        st.info("Données CNAM ou démographiques insuffisantes.")
        return

    top_publics = publics[:3]
    cols_ui = st.columns(min(3, len(top_publics)))

    for i, pub in enumerate(top_publics):
        label = _PUBLIC_SHORT.get(pub["label"], pub["label"])
        depts_str = ", ".join(pub.get("depts", [])[:3]) or "n.d."
        importance = pub.get("importance", pub.get("priorite", "—"))
        volume = pub.get("volume", "n.d.")

        with cols_ui[i]:
            st.markdown(
                f'<div class="reco-card p{i + 1}">'
                f'<div class="reco-title">{label}</div>'
                f'<div class="reco-stats" style="margin:14px 0;">'
                f'<div class="reco-stat">'
                f'<span class="val">{volume}</span>'
                f'<span class="lbl">Volume concerné</span>'
                f'</div>'
                f'</div>'
                f'<div style="font-size:12px;color:#4A4A4A;margin-bottom:8px;">'
                f'<strong>Départements\u202f:</strong> {depts_str}</div>'
                f'<div style="font-size:12px;color:#6B6B68;">{importance}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Bloc 4 — Comment agir ? ───────────────────────────────────────────────────

def render_comment_agir(
    leviers: list[dict],
    region_depts: pd.DataFrame,
    data: dict,
    region_name: str,
) -> None:
    st.markdown(
        '<div class="section-header" style="margin-top:56px;">'
        '<div class="section-eyebrow">COMMENT AGIR</div>'
        '<h2 class="section-title">Leviers <em>recommandés.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not leviers:
        st.info("Aucun levier identifié avec les données disponibles.")
        return

    for i, lev in enumerate(leviers[:3], 1):
        depts_str = ", ".join(lev.get("depts", [])) or "n.d."
        amplitude = project_levier_amplitude_region(
            lev, region_depts, data, region_name
        )
        st.markdown(
            f'<div class="reco-card p{i}">'
            f'<div class="reco-title">{lev["intitule"].capitalize()}</div>'
            f'<div class="reco-prose" style="font-size:13px;">'
            f'<strong>Problème\u202f:</strong> {lev.get("tension", "—")}<br>'
            f'<strong>Public\u202f:</strong> {lev["public_cible"]}<br>'
            f'<strong>Territoires\u202f:</strong> {depts_str}'
            f'</div>'
            f'{render_amplitude_region_html(amplitude)}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Données détaillées (accordéon) ────────────────────────────────────────────

def _region_ui_css() -> str:
    """Correctifs UI scoped fiche région."""
    return """
<style>
/* Fix icône Material Streamlit affichée en texte (_arrowright) */
div[data-testid="stExpander"] > details > summary {
    list-style: none !important;
}
div[data-testid="stExpander"] > details > summary::-webkit-details-marker {
    display: none !important;
}
div[data-testid="stExpander"] summary [data-testid="stIconMaterial"],
div[data-testid="stExpander"] summary span[data-testid="stIconMaterial"],
div[data-testid="stExpander"] summary > span:first-child,
div[data-testid="stExpander"] summary > div:first-child {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    font-size: 0 !important;
    line-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    position: absolute !important;
    pointer-events: none !important;
}
div[data-testid="stExpander"] summary::before {
    content: '▸  ' !important;
    color: #1A3D8F !important;
    font-weight: 700 !important;
    font-size: 13px !important;
}
div[data-testid="stExpander"] details[open] > summary::before {
    content: '▾  ' !important;
}
</style>
"""


def render_donnees_detaillees(
    region_depts: pd.DataFrame,
    region_name: str,
    data: dict,
    delais_region: pd.DataFrame,
    priorities: pd.DataFrame,
) -> None:
    st.markdown(_region_ui_css(), unsafe_allow_html=True)
    st.markdown(
        '<div class="section-header" style="margin-top:48px;margin-bottom:8px;">'
        '<div class="section-eyebrow">EXPLORATION</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Données détaillées", expanded=False):
        render_diagnostic_region(region_depts, region_name)
        render_region_map(region_depts, data.get("geojson"))
        render_ranking_depts(region_depts)
        render_delais_detail(delais_region, region_name)
        render_priorisation_technique(priorities)
        st.markdown(
            '<div style="margin-top:24px;padding:14px 18px;background:#F3F2EC;'
            'border-radius:4px;font-size:12px;color:#6B6B68;line-height:1.6;">'
            '<strong style="color:#2B2B2B;">Note méthodologique.</strong> '
            'Priorisation basée sur fragilité sanitaire, impact potentiel et '
            'faisabilité de déploiement (données ouvertes). Ne remplace pas '
            'l\'expertise locale d\'une ARS.'
            '</div>',
            unsafe_allow_html=True,
        )


def render_diagnostic_region(region_depts: pd.DataFrame, region_name: str) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">DIAGNOSTIC RÉGIONAL</div>'
        '<h2 class="section-title">Disparités <em>internes.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    valid = region_depts.dropna(subset=["score_global"])
    if valid.empty:
        st.info("Données insuffisantes.")
        return

    worst = valid.sort_values("score_global").iloc[0]
    best = valid.sort_values("score_global", ascending=False).iloc[0]
    nb_crit = int((region_depts["zone_short"] == "Critique").sum())

    if nb_crit > 0:
        phrase = (
            f"{nb_crit} département{'s' if nb_crit > 1 else ''} en zone critique. "
            f"{worst['Nom du département']} ({worst['score_global']:.1f}/100) "
            f"— {best['Nom du département']} ({best['score_global']:.1f}/100)."
        )
    else:
        phrase = (
            f"Situation homogène. "
            f"{worst['Nom du département']} ({worst['score_global']:.1f}/100) "
            f"— {best['Nom du département']} ({best['score_global']:.1f}/100)."
        )

    st.markdown(
        f'<div class="diagnostic-prose" style="max-width:900px;font-size:16px;">'
        f'{phrase}</div>',
        unsafe_allow_html=True,
    )


def render_region_map(region_depts: pd.DataFrame, geojson) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">CARTE</div>'
        '<h2 class="section-title">Départements <em>de la région.</em></h2>'
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
        height=450,
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
        '<div class="section-eyebrow">CLASSEMENT</div>'
        '<h2 class="section-title">Score <em>par département.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    sorted_depts = region_depts.sort_values(
        "score_global", na_position="last"
    ).reset_index(drop=True)

    cols = "36px 1fr 60px 110px 80px 100px 48px"
    table_html = (
        f'<div class="sa-tbl-scroll"><div style="min-width:640px;">'
        f'<div style="display:grid;grid-template-columns:{cols};gap:0 12px;'
        f'padding:8px 16px;background:#F3F2EC;border-radius:4px 4px 0 0;'
        f'font-size:11px;font-weight:700;letter-spacing:0.1em;color:#6B6B68;'
        f'text-transform:uppercase;">'
        f'<span>#</span><span>D\u00e9partement</span><span>Code</span>'
        f'<span>Zone</span>'
        f'<span style="text-align:right;">Score</span>'
        f'<span style="text-align:right;">Population</span>'
        f'<span></span>'
        f'</div>'
    )

    for i, (_, d) in enumerate(sorted_depts.iterrows(), 1):
        zone = d.get("zone_short", "\u2014")
        score = d.get("score_global")
        score_str = f"{score:.1f}" if pd.notna(score) else "\u2014"
        pop = d.get("population_num", 0)
        pop_str = f"{int(pop):,}".replace(",", "\u202f") if pd.notna(pop) else "\u2014"
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
            f'style="display:grid;grid-template-columns:{cols};gap:0 12px;'
            f'padding:10px 16px;background:{bg};border-bottom:1px solid #F0EDE5;'
            f'text-decoration:none;color:inherit;align-items:center;">'
            f'<span style="font-size:12px;font-weight:700;color:#9C9A92;">{i:02d}</span>'
            f'<span style="font-size:14px;font-weight:500;">{dept_name}</span>'
            f'<span style="font-size:12px;color:#9C9A92;">{dept_code}</span>'
            f'<span><span class="fiche-zone-badge {badge_cls}" '
            f'style="font-size:10px;padding:3px 8px;">{zone}</span></span>'
            f'<span style="text-align:right;font-weight:600;color:{score_color};">'
            f'{score_str}</span>'
            f'<span style="text-align:right;font-size:12px;color:#6B6B68;">{pop_str}</span>'
            f'<span style="text-align:right;color:#1A3D8F;">\u2192</span>'
            f'</a>'
        )

    table_html += "</div></div>"
    st.markdown(table_html, unsafe_allow_html=True)


def render_delais_detail(delais_region: pd.DataFrame, region_name: str) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">PARCOURS DE SOINS</div>'
        '<h2 class="section-title">Délais <em>spécialistes</em> (DREES).</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    if delais_region.empty:
        st.info("Données régionales de délais indisponibles.")
        return

    cols = "1.4fr 80px 80px 1fr"
    html = (
        f'<div class="sa-tbl-scroll"><div style="min-width:480px;">'
        f'<div style="display:grid;grid-template-columns:{cols};gap:0 12px;'
        f'padding:8px 16px;background:#F3F2EC;font-size:10px;font-weight:700;'
        f'letter-spacing:0.08em;color:#6B6B68;text-transform:uppercase;">'
        f'<span>Spécialité</span>'
        f'<span style="text-align:right;">Médian</span>'
        f'<span style="text-align:right;">P75</span>'
        f'<span>Levier</span></div>'
    )
    for _, srow in delais_region.iterrows():
        p75 = srow.get("delai_jours_p75")
        p75_str = f"{int(p75)}\u202fj" if pd.notna(p75) else "n.d."
        html += (
            f'<div style="display:grid;grid-template-columns:{cols};gap:0 12px;'
            f'padding:10px 16px;border-bottom:1px solid #F0EDE5;font-size:13px;">'
            f'<span>{srow["specialite"]}</span>'
            f'<span style="text-align:right;font-weight:600;">'
            f'{int(srow["delai_jours_median"])}\u202fj</span>'
            f'<span style="text-align:right;color:#6B6B68;">{p75_str}</span>'
            f'<span>{srow.get("levier", "—")}</span>'
            f'</div>'
        )
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)


def render_priorisation_technique(priorities: pd.DataFrame) -> None:
    """Tableau technique avec dimensions internes (exploration uniquement)."""
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">PRIORISATION</div>'
        '<h2 class="section-title">Dimensions <em>techniques.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    cols = "36px 1fr 88px 88px 88px 110px"
    html = (
        f'<div class="sa-tbl-scroll"><div style="min-width:620px;">'
        f'<div style="display:grid;grid-template-columns:{cols};gap:0 10px;'
        f'padding:8px 16px;background:#F3F2EC;font-size:10px;font-weight:700;'
        f'letter-spacing:0.08em;color:#6B6B68;text-transform:uppercase;">'
        f'<span>Rang</span><span>Département</span>'
        f'<span>Fragilité</span><span>Impact</span><span>Faisabilité</span>'
        f'<span>Priorité (calc.)</span></div>'
    )
    for _, row in priorities.iterrows():
        html += (
            f'<div style="display:grid;grid-template-columns:{cols};gap:0 10px;'
            f'padding:10px 16px;border-bottom:1px solid #F0EDE5;font-size:12px;">'
            f'<span>{int(row["priorite_rang"]):02d}</span>'
            f'<span>{row["Nom du département"]}</span>'
            f'<span>{row["fragilite"]}</span>'
            f'<span>{row["impact"]}</span>'
            f'<span>{row["faisabilite"]}</span>'
            f'<span style="color:#6B6B68;">{row["priorite"]}</span>'
            f'</div>'
        )
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)
