"""Fiche région : outil d'aide à la décision ARS."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ..components import render_national_choropleth
from ..components.share_bar import region_share_context, render_fiche_share_bar
from ..pdf_export import generate_region_pdf
from ..region_decision import (
    build_action_prioritaire,
    enrich_leviers_decision,
    enrich_priorities_decision,
)
from ..region_pilotage import (
    compute_dept_priorities,
    compute_leviers_action,
    compute_publics_prioritaires,
    compute_region_summary,
    compute_specialites_tension,
)
from ..components.nav import NavCrumb, dept_link_html, render_breadcrumb
from ..router import navigate

# Affichage uniquement — les calculs internes restent inchangés
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

    priorities_raw = compute_dept_priorities(region_depts, data.get("patho"))
    delais_region = compute_specialites_tension(data.get("delais"), region_code_val)
    publics = compute_publics_prioritaires(
        region_depts, data.get("patho"), priorities_raw
    )
    priorities = enrich_priorities_decision(
        priorities_raw, region_depts, data.get("patho"), master
    )
    summary = compute_region_summary(
        priorities_raw, region_depts, delais_region, publics=publics
    )
    leviers = enrich_leviers_decision(
        compute_leviers_action(
            region_depts, priorities_raw, data.get("patho"), delais_region
        ),
        region_depts,
        priorities,
        data,
        region_name,
    )
    action_prioritaire = build_action_prioritaire(leviers, region_name)

    render_topbar(region_name)
    render_share_section(
        region_name, region_code_val, region_depts, summary, priorities, leviers
    )
    render_hero(
        region_depts, region_name, summary, publics,
        master=master,
        region_code=region_code_val,
        priorities=priorities,
        leviers=leviers,
    )
    render_ou_agir(priorities)
    render_pour_qui(publics)
    render_action_prioritaire(action_prioritaire)
    render_comment_agir(leviers)
    render_donnees_detaillees(
        region_depts, region_name, data, delais_region, priorities_raw
    )


# ── Bloc 1 — Contexte régional ───────────────────────────────────────────────

def render_topbar(region_name: str) -> None:
    render_breadcrumb([
        NavCrumb("Accueil", "home"),
        NavCrumb(region_name),
    ], key_prefix="region_bc")


def render_share_section(
    region_name: str,
    region_code: str,
    region_depts: pd.DataFrame,
    summary: dict,
    priorities: pd.DataFrame,
    leviers: list[dict],
) -> None:
    share = region_share_context(region_name, region_code, region_depts, summary)
    pdf_bytes: bytes | None = None
    pdf_error: str | None = None
    try:
        pdf_bytes = generate_region_pdf(
            region_name, region_code, region_depts, summary, priorities, leviers
        )
    except Exception as exc:
        pdf_error = str(exc)

    slug = (
        region_name.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("'", "")
    )
    render_fiche_share_bar(
        fiche_url=share["fiche_url"],
        email_subject=share["email_subject"],
        email_body=share["email_body"],
        share_title=share["share_title"],
        pdf_bytes=pdf_bytes,
        pdf_filename=f"santactive_region_{slug}.pdf",
        pdf_error=pdf_error,
        key_prefix=f"region_share_{region_code}",
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
    *,
    master: pd.DataFrame,
    region_code: str,
    priorities: pd.DataFrame,
    leviers: list[dict],
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
    apl_str = f"{apl_med:.1f}" if pd.notna(apl_med) else "N/D"

    pop_fmt = f"{int(pop_tot):,}".replace(",", "\u202f") if pd.notna(pop_tot) else "N/D"

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
        f'</div></div>',
        unsafe_allow_html=True,
    )

    synthesis = _generate_region_synthesis(
        region_depts, region_name, summary, publics
    )
    st.markdown(
        f'<div class="diagnostic-prose" style="max-width:900px;margin-bottom:24px;">'
        f'{synthesis}</div>',
        unsafe_allow_html=True,
    )

    from ..audio_diagnostic import (
        build_region_audio_diagnostic_text,
        render_audio_diagnostic_button,
    )

    def _region_audio_text() -> str:
        return build_region_audio_diagnostic_text(
            region_name,
            region_code,
            region_depts,
            master,
            priorities,
            leviers,
            summary,
        )

    render_audio_diagnostic_button(
        scope_key=f"region_{region_code}",
        build_text=_region_audio_text,
    )


# ── Bloc 2 — Où agir ? ───────────────────────────────────────────────────────

def _score_priorite_html(score: int) -> str:
    if score >= 80:
        color = "#A51C30"
    elif score >= 60:
        color = "#B07D00"
    else:
        color = "#0A1938"
    return (
        f'<span style="font-weight:600;color:{color};font-feature-settings:\'tnum\';">'
        f'{int(score)}</span>'
        f'<span style="color:#9C9A92;font-size:12px;">/100</span>'
    )


def _faisabilite_badge(label: str) -> str:
    cls = {"Élevée": "fav", "Moyenne": "inter", "Complexe": "crit"}.get(label, "inter")
    return (
        f'<span class="fiche-zone-badge {cls}" '
        f'style="font-size:10px;padding:3px 8px;">{html.escape(label)}</span>'
    )


def _impact_territoire_html(row: pd.Series) -> str:
    label = str(row.get("impact_label", "Impact moyen"))
    pop = row.get("impact_pop")
    pop_str = (
        f"≈ {int(pop):,}".replace(",", "\u202f") + " habitants concernés"
        if pd.notna(pop) and pop else "Population non estimée"
    )
    return (
        f'<div style="font-size:13px;font-weight:500;color:#0A1938;">'
        f'{html.escape(label)}</div>'
        f'<div style="font-size:11px;color:#6B6B68;margin-top:2px;">{pop_str}</div>'
    )


def render_ou_agir(priorities: pd.DataFrame) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">OÙ AGIR</div>'
        '<h2 class="section-title">Territoires <em>prioritaires.</em></h2>'
        '</div>'
        '<p class="diagnostic-prose" style="font-size:14px;max-width:900px;'
        'margin:-8px 0 24px;line-height:1.6;">'
        'Classement des départements où une action régionale pourrait produire '
        'le plus d\u2019impact au regard des besoins de santé, de la population '
        'concernée et de la faisabilité d\u2019intervention.'
        '</p>',
        unsafe_allow_html=True,
    )

    rows_html: list[str] = []
    for _, row in priorities.iterrows():
        dept_code = str(row["dept"]).zfill(2)
        score = int(row.get("score_priorite", 0))
        bg = "#FEF9F9" if score >= 75 else "white"
        justif = str(row.get("justification_prioritaire", row.get("lecture_rapide", "")))
        rows_html.append(
            f'<div class="region-priority-row" style="background:{bg};">'
            f'<div class="region-priority-dept">'
            f'{dept_link_html(dept_code, str(row["Nom du département"]), css_class="region-dept-name")}'
            f"</div>"
            f'<div class="region-priority-score">{_score_priorite_html(score)}</div>'
            f'<div class="region-priority-impact">{_impact_territoire_html(row)}</div>'
            f'<div class="region-priority-fais">'
            f'{_faisabilite_badge(str(row.get("faisabilite_label", "Moyenne")))}'
            f"</div>"
            f'<div class="region-priority-lecture">'
            f'{html.escape(justif)}</div>'
            f"</div>"
        )

    st.markdown(
        '<div class="region-priority-table sa-tbl-scroll">'
        '<div class="region-priority-header">'
        "<span>Département</span><span>Score de priorité</span>"
        "<span>Impact potentiel estimé</span><span>Faisabilité</span>"
        "<span>Justification</span>"
        "</div>"
        + "".join(rows_html)
        + "</div>",
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
        importance = pub.get("importance", pub.get("priorite", "N/D"))
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


# ── Bloc 4 — Action prioritaire ───────────────────────────────────────────────

def render_action_prioritaire(card: dict[str, str] | None) -> None:
    if not card:
        return

    items = (
        ("Action recommandée", card["action"]),
        ("Population potentiellement concernée", card["population"]),
        ("Territoires prioritaires", card["territoires"]),
        ("Faisabilité", card["faisabilite"]),
        ("Horizon", card["horizon"]),
    )
    grid = "".join(
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">{html.escape(lbl)}</span>'
        f'<span class="reco-impact-val">{html.escape(val)}</span>'
        f"</div>"
        for lbl, val in items
    )
    st.markdown(
        f'<div class="reco-card p1" style="min-height:auto;margin-top:48px;">'
        f'<div class="reco-title">Action régionale prioritaire</div>'
        f'<div class="reco-impact" style="margin-top:16px;">'
        f'<div class="reco-impact-grid">{grid}</div>'
        f"</div>"
        f'<div class="reco-prose" style="font-size:14px;margin-top:18px;">'
        f'<strong>Justification\u202f:</strong> '
        f'<em>{html.escape(card["justification"])}</em>'
        f"</div></div>",
        unsafe_allow_html=True,
    )


# ── Bloc 5 — Comment agir ? ───────────────────────────────────────────────────

def _render_levier_fiche_html(lev: dict, index: int) -> str:
    amplitude = lev.get("amplitude")
    pop = html.escape(str(lev.get("impact_pop_str", "n.d.")))
    horizon = html.escape(
        amplitude.horizon if amplitude else str(lev.get("horizon", "Moyen terme"))
    )
    pourquoi = html.escape(str(lev.get("pourquoi_maintenant", "")))
    impact_niv = html.escape(str(lev.get("impact_niveau", "Impact moyen")))
    fais = html.escape(str(lev.get("faisabilite_label", "Moyenne")))
    depts = html.escape(", ".join(lev.get("depts", [])) or "n.d.")
    public = html.escape(str(lev.get("public_cible", "N/D")))

    return (
        f'<div class="reco-card p{index}" style="min-height:auto;">'
        f'<div class="reco-number">{index}.</div>'
        f'<div class="reco-title">{html.escape(lev["intitule"].capitalize())}</div>'
        f'<div class="reco-prose" style="font-size:13px;margin-top:12px;">'
        f"<strong>Pourquoi maintenant\u202f?</strong><br>{pourquoi}"
        "</div>"
        f'<div class="reco-impact" style="margin-top:16px;">'
        f'<div class="reco-impact-grid">'
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">Impact attendu</span>'
        f'<span class="reco-impact-val">{impact_niv}</span>'
        f"</div>"
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">Population concernée</span>'
        f'<span class="reco-impact-val">{pop}</span>'
        f"</div>"
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">Territoires concernés</span>'
        f'<span class="reco-impact-val">{depts}</span>'
        f"</div>"
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">Public cible</span>'
        f'<span class="reco-impact-val">{public}</span>'
        f"</div>"
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">Faisabilité</span>'
        f'<span class="reco-impact-val">{fais}</span>'
        f"</div>"
        f'<div class="reco-impact-item">'
        f'<span class="reco-impact-lbl">Horizon</span>'
        f'<span class="reco-impact-val">{horizon}</span>'
        f"</div>"
        f"</div></div>"
        f"</div>"
    )


def render_comment_agir(leviers: list[dict]) -> None:
    st.markdown(
        '<div class="section-header" style="margin-top:56px;">'
        '<div class="section-eyebrow">COMMENT AGIR</div>'
        '<h2 class="section-title">Actions régionales <em>recommandées.</em></h2>'
        '</div>'
        '<p class="diagnostic-prose" style="font-size:14px;max-width:900px;'
        'margin:-8px 0 24px;line-height:1.6;">'
        'Actions régionales recommandées à partir des besoins observés, '
        'des publics concernés et du potentiel d\u2019impact estimé.'
        '</p>',
        unsafe_allow_html=True,
    )

    if not leviers:
        st.info("Aucun levier identifié avec les données disponibles.")
        return

    for i, lev in enumerate(leviers[:3], 1):
        st.markdown(_render_levier_fiche_html(lev, i), unsafe_allow_html=True)


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
            f"Écart de {worst['Nom du département']} ({worst['score_global']:.1f}/100) "
            f"à {best['Nom du département']} ({best['score_global']:.1f}/100)."
        )
    else:
        phrase = (
            f"Situation homogène. "
            f"Écart de {worst['Nom du département']} ({worst['score_global']:.1f}/100) "
            f"à {best['Nom du département']} ({best['score_global']:.1f}/100)."
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

    rows_html: list[str] = []
    for i, (_, d) in enumerate(sorted_depts.iterrows(), 1):
        zone = d.get("zone_short", "N/D")
        score = d.get("score_global")
        score_str = f"{score:.1f}" if pd.notna(score) else "N/D"
        pop = d.get("population_num", 0)
        pop_str = f"{int(pop):,}".replace(",", "\u202f") if pd.notna(pop) else "N/D"
        dept_code = str(d["dept"]).zfill(2)
        dept_name = d["Nom du département"]
        badge_cls = {"Critique": "crit", "Intermédiaire": "inter",
                     "Favorable": "fav"}.get(zone, "")
        score_color = (
            "#A51C30" if zone == "Critique"
            else ("#E5B04A" if zone == "Intermédiaire" else "#1B5E3F")
        )
        bg = "#FEF9F9" if zone == "Critique" else "white"
        rows_html.append(
            f'<div class="region-ranking-row" style="background:{bg};">'
            f'<span class="region-ranking-rank">{i:02d}</span>'
            f'<span class="region-ranking-dept">'
            f'{dept_link_html(dept_code, str(dept_name), css_class="region-dept-name")}'
            f"</span>"
            f'<span class="region-ranking-code">{dept_code}</span>'
            f'<span class="region-ranking-zone">'
            f'<span class="fiche-zone-badge {badge_cls}" '
            f'style="font-size:10px;padding:3px 8px;">{zone}</span>'
            f"</span>"
            f'<span class="region-ranking-score" style="color:{score_color};">'
            f"{score_str}</span>"
            f'<span class="region-ranking-pop">{pop_str}</span>'
            f"</div>"
        )

    st.markdown(
        '<div class="region-ranking-table sa-tbl-scroll">'
        '<div class="region-ranking-header">'
        "<span>#</span><span>D\u00e9partement</span><span>Code</span>"
        "<span>Zone</span><span>Score</span><span>Population</span>"
        "</div>"
        + "".join(rows_html)
        + "</div>",
        unsafe_allow_html=True,
    )


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
            f'<span>{srow.get("levier", "N/D")}</span>'
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
