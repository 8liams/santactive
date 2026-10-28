"""Écran d'accueil : recherche, carte nationale, repères nationaux, outre-mer."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ..components.nav import internal_href
from ..components.tooltip import info_tooltip
from ..config import APL_LABEL_COURT, APL_SOURCE_LABEL, TEMPS_LABEL_COURT
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
    from .. import territoire as T
    t = T.get()
    dom_ref = bool(set(T.dept_codes(t, master)) & _DOM) and not t.is_national
    if dom_ref:
        with st.container(key="home_dom"):
            _render_dom_section(master)
    with st.container(key="home_map_kpi"):
        col_map, col_kpi = st.columns([2.1, 1], gap="large")
        with col_map:
            _render_national_map(master, geojson)
        with col_kpi:
            _render_national_kpis(master)
    if not dom_ref:
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
    """Résumé compact du territoire de référence : une phrase, une action principale, deux liens."""
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
        lecture = {"Critique": "parmi le tiers des départements les moins bien placés",
                   "Intermédiaire": "dans le tiers médian des départements",
                   "Favorable": "parmi le tiers des départements les mieux placés"}.get(zone, "sans score")
        apl_txt = (f" · APL {f'{apl:.1f}'.replace('.', ',')}" + (" (sous le repère 2,5)" if apl < 2.5 else "")) if pd.notna(apl) else ""
        score_txt = (f"score {float(score):.0f}/100, {fmt_classement_national(r.get('rang_national'), nb_total)} sur {nb_total}"
                     if pd.notna(score) else "sans score")
        titre = f'{html.escape(str(r["Nom du département"]))} <span>({t.code}) · {html.escape(str(r.get("Nom de la région", "")))}</span>'
        texte = f"{score_txt}, {lecture}{apl_txt}."
        primaire = (internal_href("dept", dept_code=t.code), "Ouvrir le diagnostic →")
        secondaires = [(internal_href("comparer") + f"&depts={t.code}", "Comparer")]
        if t.code in pilotes:
            secondaires.append((internal_href("acces", dept_code=t.code), "Simuler une implantation"))
    else:
        depts = master[master["Code région"].astype(str) == t.code]
        if depts.empty:
            return
        crit = depts[depts["zone_short"] == "Critique"]
        badge, zone = "", ""
        titre = f'{html.escape(str(depts.iloc[0]["Nom de la région"]))} <span>· région · {len(depts)} départements</span>'
        sc = pd.to_numeric(depts["score_global"], errors="coerce")
        texte = (f"{len(crit)} département{'s' if len(crit) != 1 else ''} en zone critique"
                 + (f" ({html.escape(', '.join(crit.sort_values('score_global')['Nom du département'].astype(str).tolist()[:3]))})" if len(crit) else "")
                 + f", scores de {sc.min():.0f} à {sc.max():.0f} sur 100.")
        primaire = (internal_href("region", region_code=t.code), "Ouvrir la fiche région →")
        codes = (crit.sort_values("score_global")["dept"].astype(str).tolist() or depts["dept"].astype(str).tolist())[:4]
        secondaires = [(internal_href("comparer") + "&depts=" + ",".join(codes), "Comparer ses départements")]
        pil = [d for d in depts["dept"].astype(str) if d in pilotes]
        if pil:
            secondaires.append((internal_href("acces"), f"Simuler ({len(pil)} département{'s' if len(pil) != 1 else ''} couverts)"))
    st.markdown(
        f'<div class="ref-line"><div class="ref-line-main"><span class="ref-line-eyebrow">Territoire de référence</span>'
        f'<span class="ref-line-title">{titre}'
        + (f'<i class="fiche-zone-badge {badge}">Zone {zone.lower()}</i>' if zone and zone != "N/D" else "") + '</span>'
        f'<span class="ref-line-txt">{texte}</span></div>'
        f'<div class="ref-line-links"><a class="primary" href="{primaire[0]}" target="_self">{primaire[1]}</a>'
        + "".join(f'<a href="{h}" target="_self">{l} →</a>' for h, l in secondaires)
        + f'<a class="ref-line-reset" href="{internal_href("home", t="fr")}" target="_self">France entière</a></div></div>',
        unsafe_allow_html=True)


def _render_usages(master: pd.DataFrame) -> None:
    """Trois entrées métier : prioriser, diagnostiquer, simuler. Avec un département de
    référence, elles s'ouvrent directement sur lui. La recherche reste dans la barre."""
    from .. import territoire as T
    from .acces_ign import pilotes_disponibles

    t = T.get()
    pilotes = pilotes_disponibles()
    crit = master[master["zone_short"] == "Critique"].sort_values("score_global") if "zone_short" in master.columns else master.head(0)
    ex = crit.iloc[0] if not crit.empty else None
    nom_t = html.escape(T.nom_court(t, master)) if not t.is_national else ""
    # Diagnostiquer : le territoire de référence (département ou région), sinon un exemple national
    if t.kind == "dept":
        diag = (f"Situation, scorecard, leviers recommandés et communes fragiles. {nom_t}.", internal_href("dept", dept_code=t.code), "Ouvrir le diagnostic →")
    elif t.kind == "region":
        diag = (f"Situation régionale, départements critiques, leviers et communes fragiles. {nom_t}.",
                internal_href("region", region_code=t.code), "Ouvrir le diagnostic →")
    else:
        diag = ("Situation, scorecard, leviers recommandés et communes fragiles d\u2019un département."
                + (f" Exemple : {html.escape(str(ex['Nom du département']))}." if ex is not None else ""),
                internal_href("dept", dept_code=str(ex["dept"])) if ex is not None else internal_href("diagnostic"), "Ouvrir un exemple →")
    # Simuler : le département de référence s'il est couvert ; une région propose le choix du département
    if t.kind == "dept" and t.code in pilotes:
        sim = (f"Où une nouvelle offre de médecine générale rapprocherait des habitants, carreau par carreau. {nom_t}.",
               internal_href("acces", dept_code=t.code), "Simuler une implantation →")
    elif t.kind == "dept":
        sim = (f"Non disponible pour {nom_t} (hors champ de la base Insee). {len(pilotes)} départements couverts : métropole, Martinique, La Réunion.",
               internal_href("acces"), "Voir les départements couverts →")
    elif t.kind == "region":
        pil = [d for d in T.dept_codes(t, master) if d in pilotes]
        sim = (f"Où une nouvelle offre rapprocherait des habitants, carreau par carreau. {nom_t} : {len(pil)} département{'s' if len(pil) != 1 else ''} "
               f"couvert{'s' if len(pil) != 1 else ''}, à choisir.", internal_href("acces"), "Choisir un département →")
    else:
        sim = (f"Où une nouvelle offre de médecine générale rapprocherait des habitants, carreau par carreau. Disponible pour {len(pilotes)} départements.",
               internal_href("acces"), "Choisir un département →")
    cards = [
        ("Prioriser", "Où l\u2019offre est faible et les besoins forts : les départements à examiner en premier, par région.",
         internal_href("exploration"), "Prioriser les territoires →"),
        ("Diagnostiquer",) + diag,
        ("Simuler",) + sim,
    ]
    html_cards = "".join(
        f'<a class="usage-card" href="{href}" target="_self"><div class="usage-title">{titre}</div>'
        f'<div class="usage-txt">{txt}</div><div class="usage-link">{lab}</div></a>'
        for titre, txt, href, lab in cards)
    st.markdown(f'<div class="usage-grid usage-grid--3">{html_cards}</div>', unsafe_allow_html=True)


# Indicateurs de la carte : un seul contrôle, un seul état (clé home_indicateur)
INDICATEURS_PRINCIPAUX = ["Score global", "APL", "Temps d'accès"]


def _bounds_for(geojson: dict, codes: set[str]) -> list | None:
    pts = []
    for f in geojson.get("features", []):
        if str(f["properties"].get("code")) not in codes:
            continue
        g = f["geometry"]
        rings = g["coordinates"] if g["type"] == "Polygon" else [r for poly in g["coordinates"] for r in poly]
        for ring in rings:
            pts.extend(ring)
    if not pts:
        return None
    return [[min(p[1] for p in pts), min(p[0] for p in pts)], [max(p[1] for p in pts), max(p[0] for p in pts)]]


def _render_national_map(master: pd.DataFrame, geojson) -> None:
    from .. import territoire as T
    from ..components import render_national_choropleth
    from ..components.maps import COLORMAPS

    if not geojson:
        st.warning("Carte indisponible. Vérifiez la connexion.")
        return

    labels = [l for _, l, _, _ in INDICATORS]
    st.markdown('<div id="home_carte"></div>', unsafe_allow_html=True)
    selected_label = st.radio("Indicateur affiché", labels, horizontal=True, key="home_indicateur")
    idx = labels.index(selected_label) if selected_label in labels else 0
    col_key, _lab, cmap_name, reverse_scale = INDICATORS[idx]
    if col_key not in master.columns or master[col_key].isna().all():
        st.caption(f"Indicateur « {selected_label} » non disponible, affichage du score global.")
        col_key, cmap_name, reverse_scale = "score_global", "score", False

    t = T.get()
    hl_codes = set(T.dept_codes(t, master)) if not t.is_national else set()
    bounds = _bounds_for(geojson, hl_codes) if hl_codes else None
    sub = {"score_global": "Score Sant’active · 100 départements · cliquez sur un département pour ouvrir sa fiche",
           "apl_dept": f"{APL_LABEL_COURT} · {APL_SOURCE_LABEL}",
           "temps_acces_median": f"Temps d’accès médian · minutes · {TEMPS_LABEL_COURT} (dimension du score)",
           "med_gen_pour_100k": "Généralistes pour 100 000 habitants · DREES 2026",
           "prix_m2_moyen": "Prix médian au m² · DVF 2025",
           "pct_plus_65": "Part des 65 ans et plus · INSEE 2021"}.get(col_key, "")
    ctx = ""
    if hl_codes:
        nom = html.escape(T.nom_court(t, master))
        ctx = (f' · <strong>{nom}</strong> en évidence' + ("" if bounds else " (hors du fond métropolitain : voir le cartouche ci-dessus)")
               + f' · <a href="{internal_href("home", t="fr")}" target="_self">France entière</a>')
    st.markdown(
        f'<div class="map-header"><div class="map-title">Accessibilité aux soins en France</div>'
        f'<div class="map-sub">{sub} {info_tooltip("score_global") if col_key == "score_global" else ""}{ctx}</div></div>',
        unsafe_allow_html=True,
    )

    event = render_national_choropleth(
        master=master, geojson=geojson, metric=col_key, colormap_name=cmap_name,
        reverse=reverse_scale, height=600, key=f"home_national_map_{col_key}_{t.param}",
        bounds=bounds, highlight_codes=hl_codes or None,
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
                f'<span class="count">{vals.min():,.0f} {unit}</span>'
                f'<span class="gradient" style="background:linear-gradient(90deg,{stops});"></span>'
                f'<span class="count">{vals.max():,.0f} {unit}</span></div>'.replace(",", " "),
                unsafe_allow_html=True,
            )
    st.session_state["_home_map_choice"] = (col_key, cmap_name, reverse_scale)


_DOM = {"971", "972", "973", "974", "976"}


def _render_dom_section(master: pd.DataFrame) -> None:
    """Cartouches ultramarins : tous en vue nationale ; seulement celui du territoire si
    un département ou une région d'outre-mer est la référence ; rien sinon."""
    from .. import territoire as T
    from ..components.maps import render_dom_cartouches

    t = T.get()
    if t.is_national:
        st.markdown('<div class="map-section-eyebrow">Départements et régions d’outre-mer</div>', unsafe_allow_html=True)
        render_dom_cartouches(master)
        return
    codes = [c for c in T.dept_codes(t, master) if c in _DOM]
    if not codes:
        return
    st.markdown('<div class="map-section-eyebrow">Territoire ultramarin de référence</div>', unsafe_allow_html=True)
    render_dom_cartouches(master, only=set(codes))


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
    # Population sous le repère APL 2,5 : Σ part départementale × population INSEE 2021 (APL 2024 : 12,3 M, 18,2 % sur le fichier communal).
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
    _part_sous = (f"{pop_sous_seuil / float(pop.sum()) * 100:.1f}".replace(".", ",") + "\u202f%") if pd.notna(pop_sous_seuil) and pop.sum() > 0 else "n.d."
    st.markdown(
        '<div class="kpi-stack-header"><div class="eyebrow">France entière</div>'
        '<h3>Les repères <em>nationaux</em></h3></div>'
        '<div class="nat-kpis">'
        + kpi("APL médiane", f"{apl_med:.1f}".replace(".", ",") if pd.notna(apl_med) else "N/D", " consult./hab.",
              f"médiane des départements · {APL_SOURCE_LABEL} · repère de sous-densité : 2,5", "apl")
        + kpi("Sous le repère APL", fmt_pop, " hab.",
              f"habitants d\u2019une commune sous APL 2,5, soit {_part_sous} · {APL_SOURCE_LABEL}")
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
