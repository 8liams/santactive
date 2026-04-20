"""Écran d'accueil : recherche live + carte France + KPIs nationaux."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_searchbox import st_searchbox

from ..config import PALETTE
from ..router import navigate
from ..search import SearchResult, search_territory
from ..components.tooltip import info_tooltip

# Caches module-level (appelés hors contexte render par le callback searchbox)
_MASTER_CACHE: pd.DataFrame | None = None
_DATA_CACHE: dict | None = None
_COMMUNES_CACHE: pd.DataFrame | None = None


def _get_communes_for_search() -> pd.DataFrame:
    """Construit un DataFrame {commune, code_departement} dédupliqué."""
    global _COMMUNES_CACHE, _DATA_CACHE
    if _COMMUNES_CACHE is not None:
        return _COMMUNES_CACHE
    if _DATA_CACHE is None:
        _COMMUNES_CACHE = pd.DataFrame(columns=["commune", "code_departement"])
        return _COMMUNES_CACHE

    temps = _DATA_CACHE.get("temps")
    if temps is None or temps.empty:
        _COMMUNES_CACHE = pd.DataFrame(columns=["commune", "code_departement"])
    else:
        _COMMUNES_CACHE = (
            temps[["commune", "code_departement"]]
            .dropna()
            .drop_duplicates(subset=["commune", "code_departement"])
            .reset_index(drop=True)
        )
    return _COMMUNES_CACHE


# ──────────────────────────────────────────────────────────────────────────────
# CALLBACK SEARCHBOX
# ──────────────────────────────────────────────────────────────────────────────

def _search_callback(query: str) -> list:
    """Appelé à chaque frappe — retourne (label_affiché, valeur_stockée)."""
    if not query or len(query) < 2 or _MASTER_CACHE is None:
        return []
    communes_df = _get_communes_for_search()
    results = search_territory(
        query, _MASTER_CACHE, communes=communes_df, limit=10
    )
    return [(_fmt_label(r), {"level": r.level, "code": r.code}) for r in results]


def _fmt_label(r: SearchResult) -> str:
    icon = {"region": "⬢", "departement": "▮", "commune": "●"}.get(r.level, "·")
    level_label = {"region": "Région", "departement": "Département",
                   "commune": "Commune"}.get(r.level, r.level)
    if r.parent_name:
        return f"{icon}  {r.name}   ·   {level_label} · {r.parent_name}"
    return f"{icon}  {r.name}   ·   {level_label}"


# ──────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def render(data: dict) -> None:
    global _MASTER_CACHE, _DATA_CACHE, _COMMUNES_CACHE
    master: pd.DataFrame = data["master"]
    _MASTER_CACHE = master
    _DATA_CACHE = data
    _COMMUNES_CACHE = None  # reset à chaque render pour forcer recalcul si données changent
    geojson = data.get("geojson")

    # ── HERO ──────────────────────────────────────────────────────────────────
    st.markdown("""
<div class="home-hero">
    <div class="hero-eyebrow">Observatoire · 101 départements · 35 000 communes</div>
    <h1 class="hero-title">
        Cartographier la santé,<br><em>territoire par territoire.</em>
    </h1>
    <p class="hero-lead">
        Diagnostics, accès aux soins, démographie, pathologies et immobilier —
        croisés en une seule fiche par territoire, destinée aux ARS, aux élus et
        aux professionnels de santé.
    </p>
</div>
""", unsafe_allow_html=True)

    # ── LABEL + SEARCHBOX LIVE ────────────────────────────────────────────────
    st.markdown(
        '<div style="margin:48px 0 6px;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.12em;'
        'text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">'
        'EXPLORER UN TERRITOIRE'
        '</div>'
        '<div style="font-size:22px;font-weight:300;color:#0A1938;'
        'letter-spacing:-0.01em;margin-bottom:14px;line-height:1.2;">'
        'Recherchez un <em style="font-style:italic;color:#1A3D8F;">département</em>, '
        'une r\u00e9gion ou une commune.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    selection = st_searchbox(
        _search_callback,
        placeholder="Ex\u202f: Cher, Bretagne, Rennes\u2026",
        label="",
        key="home_searchbox",
        clear_on_submit=False,
        rerun_on_update=True,
    )

    if selection and isinstance(selection, dict):
        level = selection.get("level")
        code = selection.get("code")
        if level == "departement":
            navigate("dept", dept_code=code)
        elif level == "region":
            navigate("region", region_code=code)
        elif level == "commune":
            navigate("commune", commune_code=code)

    # ── SUGGESTIONS + CARTE + KPIs ───────────────────────────────────────────
    _render_quick_suggestions(master)

    col_map, col_kpi = st.columns([1.6, 1], gap="large")
    with col_map:
        _render_national_map(master, geojson)
    with col_kpi:
        _render_national_kpis(data)


# ──────────────────────────────────────────────────────────────────────────────
# SUGGESTIONS RAPIDES
# ──────────────────────────────────────────────────────────────────────────────

def _render_quick_suggestions(master: pd.DataFrame) -> None:
    if "score_global" not in master.columns:
        return

    st.markdown(
        '<div class="suggestions-label">Suggestions — zones critiques</div>',
        unsafe_allow_html=True,
    )

    top_crit = (
        master.dropna(subset=["score_global", "Nom du département"])
        .sort_values("score_global")
        .head(4)
    )

    cols = st.columns(min(4, len(top_crit)))
    for i, (_, row) in enumerate(top_crit.iterrows()):
        with cols[i]:
            score_val = row.get("score_global", 0)
            dept_name = row.get("Nom du département", "")
            dept_code = row.get("dept", "")
            if st.button(
                f"⚠ {dept_name}",
                key=f"sugg_{dept_code}",
                help=f"Zone critique · Score {score_val:.0f}/100",
                use_container_width=True,
            ):
                navigate("dept", dept_code=dept_code)


# ──────────────────────────────────────────────────────────────────────────────
# CARTE NATIONALE (Folium/Leaflet)
# ──────────────────────────────────────────────────────────────────────────────

def _render_national_map(master: pd.DataFrame, geojson) -> None:
    from ..components import render_national_choropleth

    st.markdown(
        '<div class="map-header">'
        '<div class="map-title">Accessibilité aux soins en France</div>'
        f'<div class="map-sub">Score global · 101 départements · 2021–2026 '
        f'{info_tooltip("score_global")}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not geojson:
        st.warning("Carte indisponible — vérifiez la connexion.")
        return

    # Sélecteur d'indicateur — pills arrondis
    INDICATORS = [
        ("score_global",       "Score global",   "score", False),
        ("apl_median_dept",    "APL",            "score", False),
        ("temps_acces_median", "Temps d'accès",  "temps", True),
        ("med_gen_pour_100k",  "Médecins /100k", "score", False),
        ("prix_m2_moyen",      "Prix immo",      "prix",  False),
        ("pct_plus_65",        "Part 65+",       "age",   False),
    ]
    INDICATOR_KEYS   = [k for k, _, _, _ in INDICATORS]
    INDICATOR_LABELS = [l for _, l, _, _ in INDICATORS]
    INDICATOR_CMAPS  = [c for _, _, c, _ in INDICATORS]
    INDICATOR_REV    = [rv for _, _, _, rv in INDICATORS]

    try:
        selected_label = st.pills(
            "Indicateur",
            options=INDICATOR_LABELS,
            default=INDICATOR_LABELS[0],
            key="map_indicator_pills",
            label_visibility="collapsed",
        )
    except AttributeError:
        selected_label = st.radio(
            "Indicateur",
            options=INDICATOR_LABELS,
            horizontal=True,
            key="map_indicator_radio",
            label_visibility="collapsed",
        )

    idx = INDICATOR_LABELS.index(selected_label) if selected_label in INDICATOR_LABELS else 0
    col_key       = INDICATOR_KEYS[idx]
    cmap_name     = INDICATOR_CMAPS[idx]
    reverse_scale = INDICATOR_REV[idx]

    # Fallback si la colonne est absente ou entièrement vide
    if col_key not in master.columns or master[col_key].isna().all():
        st.caption(
            f"Indicateur « {selected_metric} » non disponible, "
            "affichage du score global."
        )
        col_key, cmap_name, reverse_scale = "score_global", "score", False

    event = render_national_choropleth(
        master=master,
        geojson=geojson,
        metric=col_key,
        colormap_name=cmap_name,
        reverse=reverse_scale,
        height=560,
        key=f"home_national_map_{col_key}",
    )

    # Clic sur un département → ouvre la fiche
    if event:
        clicked = event.get("last_active_drawing") or event.get("last_object_clicked")
        if clicked:
            props = (clicked.get("properties") or {}) if isinstance(clicked, dict) else {}
            code = props.get("code")
            if code:
                navigate("dept", dept_code=str(code))

    # Légende HTML (Folium n'affiche pas de colorbar native)
    if "zone_short" in master.columns:
        counts = master["zone_short"].value_counts()
        st.markdown(
            '<div class="map-legend">'
            f'<span class="legend-item">'
            f'<span class="swatch" style="background:#A51C30;"></span>'
            f'Critique <span class="count">({int(counts.get("Critique", 0))})</span>'
            '</span>'
            f'<span class="legend-item">'
            f'<span class="swatch" style="background:#E5B04A;"></span>'
            f'Intermédiaire <span class="count">({int(counts.get("Intermédiaire", 0))})</span>'
            '</span>'
            f'<span class="legend-item">'
            f'<span class="swatch" style="background:#1B5E3F;"></span>'
            f'Favorable <span class="count">({int(counts.get("Favorable", 0))})</span>'
            '</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── Cartouches DOM-TOM ────────────────────────────────────────────────
    from ..components.maps import render_dom_cartouches

    st.markdown(
        '<div style="margin-top:16px;padding-top:12px;'
        'border-top:1px solid #E8E6DD;">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#9C9A92;margin-bottom:8px;">'
        'DÉPARTEMENTS ET RÉGIONS D\'OUTRE-MER'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    render_dom_cartouches(
        master=master,
        geojson_dom=geojson,
        metric=col_key,
        colormap_name=cmap_name,
        reverse=reverse_scale,
        height=160,
    )


# ──────────────────────────────────────────────────────────────────────────────
# KPI NATIONAUX
# ──────────────────────────────────────────────────────────────────────────────

def _render_national_kpis(data: dict) -> None:
    master = data["master"] if isinstance(data, dict) else data

    apl_nationale  = 2.9
    temps_median   = round(float(pd.to_numeric(master["temps_acces_median"], errors="coerce").median()), 1) if "temps_acces_median" in master.columns else 12.0
    med_median     = round(float(pd.to_numeric(master["med_gen_pour_100k"], errors="coerce").median()), 0) if "med_gen_pour_100k" in master.columns else 110.0
    nb_critiques   = int((master["zone_short"] == "Critique").sum()) if "zone_short" in master.columns else 0
    nb_depts       = len(master)
    delai_ophtalmo = 52

    kpis = [
        {
            "label":   f'APL · accessibilité DREES {info_tooltip("apl")}',
            "value":   f"{apl_nationale:.1f}",
            "unit":    "/hab.",
            "context": "médiane nationale · données communales ANCT 2023",
            "detail":  (
                "Nombre de consultations disponibles par an et par habitant. "
                "En dessous de 2.5, la DREES considère le territoire "
                "en désert médical officiel."
            ),
            "rouge": False,
        },
        {
            "label":   f'Temps d\'accès {info_tooltip("temps_acces")}',
            "value":   f"{temps_median:.1f}",
            "unit":    "min",
            "context": "médiane nationale · trajet établissement le plus proche",
            "detail":  (
                "Temps de trajet médian vers l'hôpital ou clinique FINESS "
                "le plus proche. Calculé par commune, pondéré par population."
            ),
            "rouge": False,
        },
        {
            "label":   f'Médecins / 100k {info_tooltip("med_100k")}',
            "value":   f"{int(med_median)}",
            "unit":    "",
            "context": "généralistes actifs · médiane nationale · RPPS janv. 2026",
            "detail":  (
                "Densité médiane de médecins généralistes pour 100\u202f000 hab. "
                "Inclut tous modes d'exercice (libéral + salarié). "
                "L'APL est l'indicateur plus précis pour l'accès réel."
            ),
            "rouge": False,
        },
        {
            "label":   f'Délai ophtalmo estimé {info_tooltip("delais_rdv")}',
            "value":   f"{delai_ophtalmo}",
            "unit":    "jours",
            "context": "médiane nationale · DREES enquête 2016-2017",
            "detail":  (
                "Délai médian pour obtenir un RDV chez un ophtalmologue. "
                "Spécialité avec les délais les plus longs en France. "
                "Les délais réels par département ne sont pas disponibles "
                "en open data — voir Méthodologie."
            ),
            "rouge": False,
        },
        {
            "label":   f'Zones critiques {info_tooltip("zone")}',
            "value":   str(nb_critiques),
            "unit":    "",
            "context": f"sur {nb_depts} départements · tiers inférieur",
            "detail":  (
                "Départements dont le score global est dans le tiers "
                "inférieur national (< 33e percentile). Nécessitent "
                "une attention prioritaire en termes d'offre de soins."
            ),
            "rouge": True,
        },
    ]

    st.markdown(
        '<div class="kpi-stack-header">'
        '<div class="eyebrow">France entière</div>'
        '<h3>Les chiffres <em>qui comptent</em></h3>'
        '</div>',
        unsafe_allow_html=True,
    )

    for kpi in kpis:
        val_color = "#A51C30" if kpi["rouge"] else "#0A0A0A"
        st.markdown(
            f'<div style="padding:16px 0 4px;">'
            f'<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;'
            f'text-transform:uppercase;color:#6B6B68;margin-bottom:6px;">'
            f'{kpi["label"]}</div>'
            f'<div style="font-size:34px;font-weight:300;line-height:1;'
            f'letter-spacing:-0.02em;color:{val_color};">'
            f'{kpi["value"]}'
            f'<span style="font-size:13px;font-weight:400;color:#6B6B68;'
            f'margin-left:4px;">{kpi["unit"]}</span>'
            f'</div>'
            f'<div style="font-size:11px;color:#9C9A92;margin-top:4px;'
            f'letter-spacing:0.02em;">{kpi["context"]}</div>'
            f'<div style="font-size:12px;color:#6B6B68;margin-top:6px;'
            f'line-height:1.5;font-style:italic;">{kpi["detail"]}</div>'
            f'</div>'
            f'<hr style="border:none;border-top:1px solid #E8E6DD;margin:8px 0 0;">',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="methodology-card">'
        '<strong>Comment on calcule ces scores ?</strong>'
        ' APL ANCT 2023 (65\u202f%) + temps d\'accès pondéré (35\u202f%), '
        'densité en établissements et délais de RDV. '
        '<a href="?view=methodologie">Méthodologie complète →</a>'
        '</div>',
        unsafe_allow_html=True,
    )
