"""Écran d'accueil : recherche, carte nationale, repères nationaux, outre-mer."""

from __future__ import annotations

import html

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
    _render_territoire_reference(master)
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


def _render_territoire_reference(master: pd.DataFrame) -> None:
    """Territoire de référence (barre de navigation) : situation en un regard et entrées du parcours."""
    from .. import territoire as T
    from .acces_ign import pilotes_disponibles

    t = T.get()
    if t.is_national:
        return
    pilotes = pilotes_disponibles()
    if t.kind == "dept":
        r = T.row(t, master)
        if r is None:
            return
        from ..scoring import fmt_classement_national
        nb_total = int(master["score_global"].notna().sum())
        score = r.get("score_global"); zone = str(r.get("zone_short", "N/D"))
        badge = {"Critique": "crit", "Intermédiaire": "inter", "Favorable": "fav"}.get(zone, "")
        apl = pd.to_numeric(pd.Series([r.get("apl_dept")]), errors="coerce").iloc[0]
        apl_nat = pd.to_numeric(master["apl_dept"], errors="coerce").median()
        lecture = {
            "Critique": "fait partie du tiers des départements les moins bien placés sur l’offre et l’accès aux soins",
            "Intermédiaire": "se situe dans le tiers médian des départements",
            "Favorable": "fait partie du tiers des départements les mieux placés",
        }.get(zone, "n’a pas de score (données insuffisantes)")
        apl_txt = ""
        if pd.notna(apl) and pd.notna(apl_nat):
            apl_txt = (f" Son accessibilité aux généralistes (APL {apl:.1f}) est "
                       + ("sous le repère de sous-densité (2,5)." if apl < 2.5 else
                          f"{'inférieure' if apl < apl_nat else 'supérieure'} à la médiane des départements ({apl_nat:.1f}).")).replace(".", ",", 0)
            apl_txt = apl_txt.replace(f"{apl:.1f}", f"{apl:.1f}".replace(".", ",")).replace(f"{apl_nat:.1f}", f"{apl_nat:.1f}".replace(".", ","))
        sim = (f'<a href="{internal_href("acces", dept_code=t.code)}" target="_self">Simuler une implantation →</a>' if t.code in pilotes
               else '<span class="sa-dim">Simulation routière : pas encore disponible pour ce département</span>')
        st.markdown(
            f'<div class="ref-block"><div class="ref-block-main"><div class="ref-block-eyebrow">Territoire de référence</div>'
            f'<div class="ref-block-title">{html.escape(str(r["Nom du département"]))} <span>({t.code}) · {html.escape(str(r.get("Nom de la région", "")))}</span>'
            f'<i class="fiche-zone-badge {badge}">Zone {zone.lower()}</i></div>'
            f'<p class="ref-block-txt">Score {float(score):.0f}/100, {fmt_classement_national(r.get("rang_national"), nb_total)} sur {nb_total} : '
            f'{html.escape(str(r["Nom du département"]))} {lecture}.{apl_txt}</p></div>'
            f'<div class="ref-block-links"><a class="primary" href="{internal_href("dept", dept_code=t.code)}" target="_self">Diagnostic →</a>'
            f'<a href="{internal_href("dept", dept_code=t.code)}#leviers" target="_self">Leviers recommandés →</a>'
            f'<a href="{internal_href("exploration")}" target="_self">Positionnement national →</a>'
            f'<a href="{internal_href("comparer")}&depts={t.code}" target="_self">Comparer →</a>{sim}</div></div>',
            unsafe_allow_html=True)
    else:
        depts = master[master["Code région"].astype(str) == t.code]
        if depts.empty:
            return
        nb = len(depts); crit = depts[depts["zone_short"] == "Critique"]
        noms_crit = ", ".join(crit.sort_values("score_global")["Nom du département"].astype(str).tolist()[:4])
        pil = [d for d in depts["dept"].astype(str) if d in pilotes]
        sim = (f'<a href="{internal_href("acces", dept_code=pil[0])}" target="_self">Simuler une implantation ({html.escape(pilotes[pil[0]])}) →</a>' if pil
               else '<span class="sa-dim">Simulation routière : aucun pilote dans cette région</span>')
        st.markdown(
            f'<div class="ref-block"><div class="ref-block-main"><div class="ref-block-eyebrow">Territoire de référence</div>'
            f'<div class="ref-block-title">{html.escape(str(depts.iloc[0]["Nom de la région"]))} <span>· région · {nb} départements</span></div>'
            f'<p class="ref-block-txt">{len(crit)} département{"s" if len(crit) != 1 else ""} en zone critique'
            + (f" ({html.escape(noms_crit)})" if noms_crit else "") + f', {int((depts["zone_short"] == "Favorable").sum())} en zone favorable. '
            f'Scores de {pd.to_numeric(depts["score_global"], errors="coerce").min():.0f} à {pd.to_numeric(depts["score_global"], errors="coerce").max():.0f} sur 100.</p></div>'
            f'<div class="ref-block-links"><a class="primary" href="{internal_href("region", region_code=t.code)}" target="_self">Fiche région →</a>'
            f'<a href="{internal_href("exploration")}" target="_self">Prioriser ses départements →</a>'
            f'<a href="{internal_href("comparer")}&depts={",".join(crit.sort_values("score_global")["dept"].astype(str).tolist()[:4] or depts["dept"].astype(str).tolist()[:4])}" target="_self">Comparer ses départements →</a>{sim}</div></div>',
            unsafe_allow_html=True)


def _render_usages(master: pd.DataFrame) -> None:
    """Six entrées par usage : trouver, prioriser, diagnostiquer, leviers, comparer, simuler.
    Avec un département de référence, les entrées s'ouvrent directement sur lui."""
    from .. import territoire as T
    from .acces_ign import pilotes_disponibles

    t = T.get()
    pilotes = pilotes_disponibles()
    pilote = next(iter(pilotes), None)
    crit = master[master["zone_short"] == "Critique"].sort_values("score_global") if "zone_short" in master.columns else master.head(0)
    ex = crit.iloc[0] if not crit.empty else None
    ref = t.code if t.kind == "dept" else None
    ex_code = ref or (str(ex["dept"]) if ex is not None else None)
    ex_nom = T.nom_court(t, master) if ref else (str(ex["Nom du département"]) if ex is not None else "")
    sim_code = ref if ref in pilotes else pilote
    cards = [
        ("Trouver un territoire", "Département, région ou commune : recherche en haut de page, sélecteur de territoire, ou clic sur la carte.",
         None, "Carte ci-dessous ↓", "#home_carte"),
        ("Identifier les priorités", "Matrice offre × besoins : les départements où l\u2019offre est faible et les besoins forts.",
         internal_href("exploration"), "Prioriser →", None),
        ("Consulter un diagnostic", "Situation, scorecard et communes fragiles d\u2019un département."
         + (f" {ex_nom}." if ref else (f" Exemple : {ex_nom}." if ex is not None else "")),
         internal_href("dept", dept_code=ex_code) if ex_code else internal_href("comparer"),
         "Ouvrir le diagnostic →" if ref else "Ouvrir un exemple →", None),
        ("Examiner les leviers", "Actions recommandées par le moteur de règles : publics ciblés, conditions de déploiement, justification territoriale.",
         (internal_href("dept", dept_code=ex_code) + "#leviers") if ex_code else internal_href("methodologie"), "Voir les leviers →", None),
        ("Comparer", "Deux à quatre territoires côte à côte : écarts majeurs, meilleur et moins bon par dimension, référence nationale.",
         internal_href("comparer") + (f"&depts={ref}" if ref else ""), "Comparer →", None),
        ("Simuler une implantation", (f"Où une nouvelle offre de médecine générale rapprocherait des habitants (carreaux INSEE, isochrones IGN). "
                                      f"Pilotes : {', '.join(pilotes.values())}.") if pilotes else "Simulation routière (pilote à venir).",
         internal_href("acces", dept_code=sim_code) if sim_code else None, "Simuler →", None),
    ]
    html_cards = ""
    for titre, txt, href, lab, anchor in cards:
        link = anchor or href
        tgt = ' target="_self"' if href else ""
        html_cards += (f'<a class="usage-card" href="{link}"{tgt}>'
                       f'<div class="usage-title">{titre}</div><div class="usage-txt">{txt}</div>'
                       f'<div class="usage-link">{lab}</div></a>')
    st.markdown(f'<div class="usage-grid usage-grid--6">{html_cards}</div>', unsafe_allow_html=True)


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
           "temps_acces_median": "Temps d'accès médian · minutes (indicateur interne, dimension du score)",
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
    # Accès routier INSEE 2025 : population à plus de 15 min en voiture d'un généraliste
    # (France métropolitaine + Martinique + La Réunion ; Guadeloupe, Guyane, Mayotte hors champ)
    pop_ins = num("acces_mg_pop")
    pop_15 = float(num("acces_mg_pop_sup_15").sum()) if "acces_mg_pop_sup_15" in master.columns else float("nan")
    part_15 = pop_15 / float(pop_ins.sum()) if pd.notna(pop_15) and pop_ins.sum() > 0 else float("nan")
    nb_15 = float(num("acces_mg_nb_communes_sup_15").sum()) if "acces_mg_nb_communes_sup_15" in master.columns else float("nan")
    _fmt_m = lambda v: ((f"{v / 1e6:.1f}".replace(".", ",") + "\u202fM") if v >= 1e6 else f"{int(v):,}".replace(",", "\u202f")) if pd.notna(v) else "N/D"
    nb_depts_sous_2_5 = int((num("apl_dept") < 2.5).sum())
    nb_depts_sous_med = int((num("apl_dept") < apl_med).sum()) if pd.notna(apl_med) else 0

    def kpi(label, value, unit, ctx, tip=None, crit=False):
        t = info_tooltip(tip) if tip else ""
        return (f'<div class="nat-kpi"><div class="nat-kpi-label">{label} {t}</div>'
                f'<div class="nat-kpi-value{" crit" if crit else ""}">{value}<small>{unit}</small></div>'
                f'<div class="nat-kpi-ctx">{ctx}</div></div>')

    fmt_pop = (f"{pop_sous_seuil / 1e6:.1f}".replace(".", ",") + " M") if pd.notna(pop_sous_seuil) else "N/D"
    st.markdown(
        '<div class="kpi-stack-header"><div class="eyebrow">France entière</div>'
        '<h3>Les repères <em>nationaux</em></h3></div>'
        '<div class="nat-kpis">'
        + kpi("APL médiane", f"{apl_med:.1f}".replace(".", ",") if pd.notna(apl_med) else "N/D", " consult./hab.",
              "médiane des départements · DREES 2023 · repère de sous-densité : 2,5", "apl")
        + kpi("Sous le repère APL", fmt_pop, " hab.",
              "habitants d\u2019une commune sous APL 2,5, soit 16,6\u202f% · DREES 2023")
        + kpi("Généralistes", f"{med_med:.0f}" if pd.notna(med_med) else "N/D", " /100k hab.",
              "densité médiane · RPPS 1ᵉʳ janv. 2026", "med_100k")
        + kpi("À plus de 15 min d\u2019un généraliste", f"{part_15 * 100:.1f}".replace(".", ",") if pd.notna(part_15) else "N/D", " %",
              f"{_fmt_m(pop_15)} habitants, {int(nb_15):,} communes au-delà de 15 min en moyenne · INSEE 2025 (hors Guadeloupe, Guyane, Mayotte)".replace(",", "\u202f")
              if pd.notna(pop_15) else "indicateur INSEE indisponible", "temps_acces")
        + '</div>'
        '<div class="nat-zones">'
        f'<div class="nat-zone" style="background:#A51C30;"><b>{nb_depts_sous_2_5}</b>départements sous le repère APL 2,5</div>'
        f'<div class="nat-zone" style="background:#C8922A;"><b>{nb_depts_sous_med}</b>départements sous la médiane APL ({f"{apl_med:.1f}".replace(".", ",")})</div>'
        '</div>'
        '<div class="nat-method">Le score Sant\u2019active (0–100) classe les départements sur six indicateurs publics '
        '(APL 30\u202f%, temps d\u2019accès 20\u202f%, généralistes 20\u202f%, structures 15\u202f%, 65 ans et plus 10\u202f%, '
        'foncier 5\u202f%), en rang percentile. Les zones critique, intermédiaire et favorable sont des terciles de ce classement '
        '(33 / 34 / 33 par construction) : elles situent un département, elles ne mesurent pas une évolution. '
        f'<a href="{internal_href("methodologie")}" target="_self">Méthodologie complète →</a></div>',
        unsafe_allow_html=True,
    )
