"""Écran d'accueil : recherche, carte nationale, repères nationaux, outre-mer."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..components.nav import internal_href
from ..components.tooltip import info_tooltip
from ..config import APL_LABEL_COURT
from ..router import navigate


def render(data: dict) -> None:
    master: pd.DataFrame = data["master"]
    geojson = data.get("geojson")

    # ── HERO compact + recherche principale ───────────────────────────────────
    nb = int(master["score_global"].notna().sum())
    st.markdown(
        '<div class="home-hero">'
        f'<div class="hero-eyebrow">Observatoire · {nb} départements analysés · vues communales partielles</div>'
        '<h1 class="hero-title">La santé de votre territoire, <em>en un seul regard.</em></h1>'
        '<p class="hero-lead">Accès aux soins, démographie médicale, pathologies et leviers d’action, '
        'consolidés en une fiche pour les ARS, les élus et les professionnels de santé.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    _render_usages(master)

    # ── CARTE + REPÈRES ───────────────────────────────────────────────────────
    with st.container(key="home_map_kpi"):
        col_map, col_kpi = st.columns([2.1, 1], gap="large")
        with col_map:
            _render_national_map(master, geojson)
        with col_kpi:
            _render_national_kpis(master)
    with st.container(key="home_dom"):
        _render_dom_section(master)


# ──────────────────────────────────────────────────────────────────────────────
# CARTE NATIONALE (Folium/Leaflet)
# ──────────────────────────────────────────────────────────────────────────────

INDICATORS = [
    ("score_global",       "Score global",   "score", False),
    ("apl_dept",           "APL",            "score", False),
    ("temps_acces_median", "Temps d'accès",  "temps", False),
    ("med_gen_pour_100k",  "Médecins /100k", "score", False),
    ("prix_m2_moyen",      "Prix immo",      "prix",  False),
    ("pct_plus_65",        "Part 65+",       "age",   False),
]


def _render_usages(master: pd.DataFrame) -> None:
    """Quatre entrées par usage : trouver, prioriser, diagnostiquer, simuler."""
    from .acces_ign import pilotes_disponibles

    pilotes = pilotes_disponibles()
    pilote = next(iter(pilotes), None)
    crit = master[master["zone_short"] == "Critique"].sort_values("score_global") if "zone_short" in master.columns else master.head(0)
    ex = crit.iloc[0] if not crit.empty else None
    cards = [
        ("Trouver un territoire", "Département, région ou commune : utilisez la recherche en haut de page, ou cliquez sur la carte.",
         None, "Carte ci-dessous ↓", "#home_carte"),
        ("Identifier une priorité", "Matrice offre × besoins : les départements où l\u2019offre est faible et les besoins forts.",
         internal_href("exploration"), "Prioriser →", None),
        ("Consulter un diagnostic", "Score, scorecard, leviers d\u2019action et communes fragiles d\u2019un département."
         + (f" Exemple : {ex['Nom du département']} ({float(ex['score_global']):.0f}/100)." if ex is not None else ""),
         internal_href("dept", dept_code=str(ex["dept"])) if ex is not None else internal_href("comparer"),
         "Ouvrir un exemple →", None),
        ("Étudier une implantation", f"Simulation routière IGN : où une nouvelle offre réduirait les temps de trajet. "
         f"Pilote : {pilotes.get(pilote, '—')}." if pilote else "Simulation routière IGN (pilote à venir).",
         internal_href("acces", dept_code=pilote) if pilote else None, "Simuler →", None),
    ]
    html_cards = ""
    for titre, txt, href, lab, anchor in cards:
        link = anchor or href
        tgt = ' target="_self"' if href else ""
        html_cards += (f'<a class="usage-card" href="{link}"{tgt}>'
                       f'<div class="usage-title">{titre}</div><div class="usage-txt">{txt}</div>'
                       f'<div class="usage-link">{lab}</div></a>')
    st.markdown(f'<div class="usage-grid">{html_cards}</div>', unsafe_allow_html=True)


# Indicateurs de la carte : lecture principale (accès aux soins) et lecture détaillée
INDICATEURS_PRINCIPAUX = ["Score global", "APL", "Temps d'accès"]


def _render_national_map(master: pd.DataFrame, geojson) -> None:
    from ..components import render_national_choropleth
    from ..components.maps import COLORMAPS

    if not geojson:
        st.warning("Carte indisponible. Vérifiez la connexion.")
        return

    labels = [l for _, l, _, _ in INDICATORS]
    st.markdown('<div id="home_carte"></div>', unsafe_allow_html=True)
    p1, p2 = st.columns([1.6, 1], vertical_alignment="center")
    with p1:
        principal = st.pills("Accès aux soins", options=INDICATEURS_PRINCIPAUX, default=INDICATEURS_PRINCIPAUX[0],
                             key="map_indicator_pills", label_visibility="collapsed")
    with p2:
        autres = ["—"] + [l for l in labels if l not in INDICATEURS_PRINCIPAUX]
        detail = st.selectbox("Autres indicateurs", autres, key="map_indicator_detail", label_visibility="collapsed",
                              format_func=lambda v: "Autres indicateurs (offre, contexte)…" if v == "—" else v)
    selected_label = detail if detail != "—" else (principal or INDICATEURS_PRINCIPAUX[0])
    idx = labels.index(selected_label) if selected_label in labels else 0
    col_key, _lab, cmap_name, reverse_scale = INDICATORS[idx]
    if col_key not in master.columns or master[col_key].isna().all():
        st.caption(f"Indicateur « {selected_label} » non disponible, affichage du score global.")
        col_key, cmap_name, reverse_scale = "score_global", "score", False

    sub = {"score_global": "Score Sant’active · 100 départements · cliquez sur un département pour ouvrir sa fiche",
           "apl_dept": f"{APL_LABEL_COURT} · DREES 2023",
           "temps_acces_median": "Temps d'accès médian à un généraliste · minutes",
           "med_gen_pour_100k": "Généralistes pour 100 000 habitants · DREES 2026",
           "prix_m2_moyen": "Prix médian au m² · DVF 2025",
           "pct_plus_65": "Part des 65 ans et plus · INSEE 2021"}.get(col_key, "")
    st.markdown(
        f'<div class="map-header"><div class="map-title">Accessibilité aux soins en France</div>'
        f'<div class="map-sub">{sub} {info_tooltip("score_global") if col_key == "score_global" else ""}</div></div>',
        unsafe_allow_html=True,
    )

    event = render_national_choropleth(
        master=master, geojson=geojson, metric=col_key, colormap_name=cmap_name,
        reverse=reverse_scale, height=600, key=f"home_national_map_{col_key}",
    )
    if event:
        clicked = event.get("last_active_drawing")
        if clicked and event.get("last_object_clicked"):
            props = (clicked.get("properties") or {}) if isinstance(clicked, dict) else {}
            code = props.get("code")
            if code and st.session_state.get("_home_map_last_click") != (code, str(event.get("last_object_clicked"))):
                st.session_state["_home_map_last_click"] = (code, str(event.get("last_object_clicked")))
                navigate("dept", dept_code=str(code))

    if col_key == "score_global" and "zone_short" in master.columns:
        counts = master["zone_short"].value_counts()
        st.markdown(
            '<div class="map-legend">'
            + "".join(
                f'<span class="legend-item"><span class="swatch" style="background:{c};"></span>'
                f'{lab} <span class="count">({int(counts.get(lab, 0))})</span></span>'
                for lab, c in (("Critique", "#A51C30"), ("Intermédiaire", "#E8A838"), ("Favorable", "#1B5E3F")))
            + '</div>',
            unsafe_allow_html=True,
        )
    else:
        vals = pd.to_numeric(master[col_key], errors="coerce").dropna()
        stops = ", ".join(reversed(COLORMAPS[cmap_name]) if reverse_scale else COLORMAPS[cmap_name])
        unit = {"apl_dept": "/hab.", "temps_acces_median": "min", "med_gen_pour_100k": "/100k",
                "prix_m2_moyen": "€/m²", "pct_plus_65": "%"}.get(col_key, "")
        if not vals.empty:
            st.markdown(
                '<div class="map-legend map-legend--gradient">'
                f'<span class="count">{vals.min():,.0f} {unit}</span>'
                f'<span class="gradient" style="background:linear-gradient(90deg,{stops});"></span>'
                f'<span class="count">{vals.max():,.0f} {unit}</span></div>'.replace(",", " "),
                unsafe_allow_html=True,
            )
    st.session_state["_home_map_choice"] = (col_key, cmap_name, reverse_scale)


def _render_dom_section(master: pd.DataFrame) -> None:
    from ..components.maps import render_dom_cartouches

    st.markdown('<div class="map-section-eyebrow">Départements et régions d’outre-mer</div>',
                unsafe_allow_html=True)
    render_dom_cartouches(master)


# ──────────────────────────────────────────────────────────────────────────────
# REPÈRES NATIONAUX
# ──────────────────────────────────────────────────────────────────────────────

def _render_national_kpis(master: pd.DataFrame) -> None:
    num = lambda c: pd.to_numeric(master[c], errors="coerce") if c in master.columns else pd.Series(dtype=float)
    apl_med = num("apl_dept").median()
    temps_med = num("temps_acces_median").median()
    med_med = num("med_gen_pour_100k").median()
    part_apl = num("part_pop_apl_inf_2_5")
    pop = num("population_num")
    # Population sous le repère APL 2,5 : Σ part départementale × population INSEE 2021 (11,2 M) ;
    # recalcul direct sur le fichier communal DREES 2023 : 11 210 951 hab. (16,6 %).
    pop_sous_seuil = float((part_apl * pop).sum()) if not part_apl.empty and not pop.empty else float("nan")
    pop_15 = float(num("pop_communes_critiques").sum()) if "pop_communes_critiques" in master.columns else float("nan")
    nb_15 = float(num("nb_communes_critiques").sum()) if "nb_communes_critiques" in master.columns else float("nan")
    _fmt_m = lambda v: (f"{v / 1e6:.1f}\u202fM" if v >= 1e6 else f"{int(v):,}".replace(",", "\u202f")) if pd.notna(v) else "N/D"
    nb_depts_sous_2_5 = int((num("apl_dept") < 2.5).sum())
    nb_depts_sous_med = int((num("apl_dept") < apl_med).sum()) if pd.notna(apl_med) else 0

    def kpi(label, value, unit, ctx, tip=None, crit=False):
        t = info_tooltip(tip) if tip else ""
        return (f'<div class="nat-kpi"><div class="nat-kpi-label">{label} {t}</div>'
                f'<div class="nat-kpi-value{" crit" if crit else ""}">{value}<small>{unit}</small></div>'
                f'<div class="nat-kpi-ctx">{ctx}</div></div>')

    fmt_pop = f"{pop_sous_seuil / 1e6:.1f} M" if pd.notna(pop_sous_seuil) else "N/D"
    st.markdown(
        '<div class="kpi-stack-header"><div class="eyebrow">France entière</div>'
        '<h3>Les repères <em>nationaux</em></h3></div>'
        '<div class="nat-kpis">'
        + kpi("APL médiane", f"{apl_med:.1f}" if pd.notna(apl_med) else "N/D", " consult./hab.",
              "médiane des départements · DREES 2023 · repère de sous-densité : 2,5", "apl")
        + kpi("Sous le repère APL", fmt_pop, " hab.",
              "habitants d\u2019une commune sous APL 2,5, soit 16,6\u202f% · DREES 2023")
        + kpi("Généralistes", f"{med_med:.0f}" if pd.notna(med_med) else "N/D", " /100k hab.",
              "densité médiane · RPPS 1ᵉʳ janv. 2026", "med_100k")
        + kpi("Communes à plus de 15 min", f"{int(nb_15):,}".replace(",", "\u202f") if pd.notna(nb_15) else "N/D", " communes",
              f"{_fmt_m(pop_15)} habitants · temps d\u2019accès interne, partiel (0 = offre dans la commune)", "temps_acces")
        + '</div>'
        '<div class="nat-zones">'
        f'<div class="nat-zone" style="background:#A51C30;"><b>{nb_depts_sous_2_5}</b>départements sous le repère APL 2,5</div>'
        f'<div class="nat-zone" style="background:#C8922A;"><b>{nb_depts_sous_med}</b>départements sous la médiane APL ({apl_med:.1f})</div>'
        '</div>'
        '<div class="nat-method">Le score Sant\u2019active (0–100) classe les départements sur six indicateurs publics '
        '(APL 30\u202f%, temps d\u2019accès 20\u202f%, généralistes 20\u202f%, structures 15\u202f%, 65 ans et plus 10\u202f%, '
        'foncier 5\u202f%), en rang percentile. Les zones critique, intermédiaire et favorable sont des terciles de ce classement '
        '(33 / 34 / 33 par construction) : elles situent un département, elles ne mesurent pas une évolution. '
        f'<a href="{internal_href("methodologie")}" target="_self">Méthodologie complète →</a></div>',
        unsafe_allow_html=True,
    )
