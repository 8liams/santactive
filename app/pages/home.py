"""Écran d'accueil : recherche, carte nationale, repères nationaux, outre-mer."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ..components.aide import aide_methodo
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
            _render_reperes(master, data)
    if not dom_ref:
        with st.container(key="home_dom"):
            _render_dom_section(master)


# ──────────────────────────────────────────────────────────────────────────────
# CARTE NATIONALE (Folium/Leaflet)
# ──────────────────────────────────────────────────────────────────────────────

INDICATORS = [
    ("score_global",       "Score Sant’active",   "score_dsfr",  False),
    ("apl_dept",           "APL",            "apl",         False),
    ("acces_mg_part_sup_10_pct", "Éloignement (> 10 min)", "eloignement", False),
    ("med_gen_pour_100k",  "Médecins /100k", "medecins",    False),
    ("prix_m2_moyen",      "Prix immo",      "prix_dsfr",   False),
    ("pct_plus_65",        "Part 65+",       "age_dsfr",    False),
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
INDICATEURS_PRINCIPAUX = ["Score Sant’active", "APL", "Éloignement (> 10 min)"]
# Classes fixes, interprétables, pour l'éloignement (part des habitants à plus de 10 min en voiture d'un généraliste, INSEE 2025)
BINS_FIXES = {"acces_mg_part_sup_10_pct": [0, 2, 5, 10, 20, 100]}


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
    from ..components.maps import COLORMAPS, ZONE_COLORS

    if not geojson:
        st.warning("Carte indisponible. Vérifiez la connexion.")
        return

    labels = [l for _, l, _, _ in INDICATORS]
    st.markdown('<div id="home_carte"></div>', unsafe_allow_html=True)
    selected_label = st.segmented_control("Indicateur affiché", labels, default=labels[0], key="home_indicateur") or labels[0]
    idx = labels.index(selected_label) if selected_label in labels else 0
    col_key, _lab, cmap_name, reverse_scale = INDICATORS[idx]
    if col_key not in master.columns or master[col_key].isna().all():
        # Repli : la colonne INSEE 2025 est relue directement (cache de session antérieur à son ajout)
        if col_key.startswith("acces_mg_"):
            try:
                from ..data_loading import load_acces_insee_dept
                ins = load_acces_insee_dept()
                if col_key in ins.columns:
                    master = master.drop(columns=[c for c in ins.columns if c != "dept" and c in master.columns]).merge(ins, on="dept", how="left")
            except Exception:
                pass
    if col_key not in master.columns or master[col_key].isna().all():
        st.caption(f"Indicateur « {selected_label} » non disponible, affichage du score Sant’active.")
        col_key, cmap_name, reverse_scale = "score_global", "score", False

    t = T.get()
    hl_codes = set(T.dept_codes(t, master)) if not t.is_national else set()
    bounds = _bounds_for(geojson, hl_codes) if hl_codes else None
    sub = {"score_global": "Score Sant’active · 100 départements · cliquez sur un département pour ouvrir sa fiche",
           "apl_dept": f"{APL_LABEL_COURT} · {APL_SOURCE_LABEL}",
           "acces_mg_part_sup_10_pct": "Part des habitants à plus de 10 minutes en voiture d’un généraliste · INSEE 2025 · "
                                       "classes fixes : moins de 2 %, 2 à 5 %, 5 à 10 %, 10 à 20 %, 20 % et plus",
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
        f'<div class="map-sub">{sub} {info_tooltip("score_global") if col_key == "score_global" else ""}{ctx} {aide_methodo("score")}</div></div>',
        unsafe_allow_html=True,
    )

    event = render_national_choropleth(
        master=master, geojson=geojson, metric=col_key, colormap_name=cmap_name,
        reverse=reverse_scale, height=600, key=f"home_national_map_{col_key}_{t.param}",
        bounds=bounds, highlight_codes=hl_codes or None, bins=BINS_FIXES.get(col_key),
    )
    if event:
        clicked = event.get("last_active_drawing")
        if clicked and event.get("last_object_clicked"):
            props = (clicked.get("properties") or {}) if isinstance(clicked, dict) else {}
            code = props.get("code")
            if code and st.session_state.get("_home_map_last_click") != (code, str(event.get("last_object_clicked"))):
                st.session_state["_home_map_last_click"] = (code, str(event.get("last_object_clicked")))
                navigate("dept", dept_code=str(code))

    if False:  # le score suit la même légende par classes que les autres indicateurs (cinq classes de scores)
        pass
    else:
        # Légende = classes de quantiles de la carte (mêmes bornes, mêmes couleurs)
        from ..components.maps import decimales_legende, national_legend_classes
        unit = {"score_global": "score sur 100 (rouge soutenu = le moins bien placé)", "apl_dept": "consult./hab.",
                "acces_mg_part_sup_10_pct": "% des habitants", "med_gen_pour_100k": "généralistes /100 000 hab.",
                "prix_m2_moyen": "€/m²", "pct_plus_65": "% de 65 ans et plus"}.get(col_key, "")
        fixes = BINS_FIXES.get(col_key)
        classes = national_legend_classes(master, col_key, cmap_name, reverse_scale, bins=fixes)
        if classes:
            bornes = [classes[0][0]] + [hi for _, hi, _ in classes]
            dec = decimales_legende(bornes, minimum={"apl_dept": 1, "pct_plus_65": 1, "score_global": 1}.get(col_key, 0))
            fmt = lambda v: f"{v:,.{dec}f}".replace(",", "\u202f").replace(".", ",")
            def lib(i, lo, hi):
                if fixes:
                    if i == 0:
                        return f"moins de {fmt(hi)}"
                    if i == len(classes) - 1:
                        return f"{fmt(lo)} et plus"
                    return f"{fmt(lo)} à {fmt(hi)}"
                return f"{fmt(lo)} à {fmt(hi)}"
            items = "".join(
                f'<span class="legend-item"><span class="swatch" style="background:{c};"></span>{lib(i, lo, hi)}</span>'
                for i, (lo, hi, c) in enumerate(classes))
            note = ("classes fixes, lisibles d’un département à l’autre" if fixes
                    else f"{len(classes)} classes de même effectif de départements (quantiles)")
            st.markdown(
                f'<div class="map-legend map-legend--classes">{items}'
                f'<span class="legend-unit">{unit} · {note}</span></div>',
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

# ──────────────────────────────────────────────────────────────────────────────
# REPÈRES SELON LE TERRITOIRE DE TRAVAIL (France, région, département, commune)
# ──────────────────────────────────────────────────────────────────────────────

def _esc(x) -> str:
    return html.escape(str(x), quote=False)


def _kpi_html(label, value, unit, ctx, tip=None, crit=False):
    t = info_tooltip(tip) if tip else ""
    return (f'<div class="nat-kpi"><div class="nat-kpi-label">{label} {t}</div>'
            f'<div class="nat-kpi-value{" crit" if crit else ""}">{value}<small>{unit}</small></div>'
            f'<div class="nat-kpi-ctx">{ctx}</div></div>')


def _fr(v, dec=1):
    return f"{float(v):.{dec}f}".replace(".", ",")


def _ent(v):
    return f"{int(round(float(v))):,}".replace(",", "\u202f")


def _pop_fmt(v):
    v = float(v)
    return (_fr(v / 1e6) + "\u202fM") if v >= 1e6 else _ent(v)


def _render_reperes(master: pd.DataFrame, data: dict) -> None:
    """Colonne de repères : d'abord le territoire de travail, les références nationales en comparaison."""
    from .. import territoire as T
    t = T.get_exact()
    if t.kind == "commune":
        _render_reperes_commune(master, data, t)
    elif t.kind == "dept":
        _render_reperes_departement(master, data, t.code)
    elif t.kind == "region":
        _render_reperes_region(master, data, t.code)
    else:
        _render_reperes_france(master)


def _render_reperes_france(master: pd.DataFrame) -> None:
    """France entière : ce qui pose problème, en croisant accessibilité potentielle, populations exposées,
    disparités et éloignement (l'éloignement n'est pas le message principal)."""
    num = lambda c: pd.to_numeric(master[c], errors="coerce") if c in master.columns else pd.Series(dtype=float)
    pop = num("population_num"); part_apl = num("part_pop_apl_inf_2_5"); apl = num("apl_dept")
    pop_sous = float((part_apl * pop).sum()); part_sous = pop_sous / float(pop.sum())
    apl_med = float(apl.median()); nb_sous_25 = int((apl < 2.5).sum())
    pop_crit = float(pop[master["zone_short"] == "Critique"].sum())
    pop_ins = float(num("acces_mg_pop").sum()); pop_15 = float(num("acces_mg_pop_sup_15").sum())
    part_15 = pop_15 / pop_ins if pop_ins > 0 else float("nan")
    med = num("med_gen_pour_100k")
    st.markdown(
        '<div class="kpi-stack-header"><div class="eyebrow">France entière</div>'
        '<h3>Où l’accès aux soins <em>pose problème</em></h3></div>'
        '<div class="nat-kpis">'
        + _kpi_html("Habitants sous le repère APL 2,5", _pop_fmt(pop_sous), " hab.",
                    f"{_fr(part_sous * 100)}\u202f% de la population dans une commune en sous-densité de généralistes · DREES {APL_SOURCE_LABEL[-4:]}", "apl", crit=True)
        + _kpi_html("Écart entre départements", f"{_fr(apl.min())} à {_fr(apl.max())}", " consult./hab.",
                    f"APL le plus faible : {master.loc[apl.idxmin(), 'Nom du département']} · le plus élevé : {master.loc[apl.idxmax(), 'Nom du département']} · médiane {_fr(apl_med)}", "apl")
        + _kpi_html("Départements en zone critique", f"{int((master['zone_short'] == 'Critique').sum())}", "",
                    f"{_pop_fmt(pop_crit)} habitants · tiers des départements les moins bien placés au score ; {nb_sous_25} départements sous APL 2,5", "zone")
        + _kpi_html("Généralistes", f"{_ent(med.median())}", " /100k hab.",
                    f"densité médiane · de {_ent(med.min())} à {_ent(med.max())} selon le département · RPPS 2026", "med_100k")
        + _kpi_html("À plus de 15 min d’un généraliste", (_fr(part_15 * 100) + "\u202f%") if pd.notna(part_15) else "N/D", "",
                    f"{_pop_fmt(pop_15)} habitants · l’éloignement reste rare ; les difficultés d’accès tiennent surtout à la capacité (APL) · INSEE 2025", "temps_acces")
        + '</div>'
        '<div class="nat-method">Le score Sant’active classe les départements sur l’offre et l’accès aux soins de premier recours '
        '(APL 30\u202f%, temps d’accès 20\u202f%, généralistes 20\u202f%, structures 15\u202f%, 65 ans et plus 10\u202f%, foncier 5\u202f%). '
        'Les zones sont des terciles de ce classement : elles situent un département, elles ne mesurent pas une évolution. '
        f'<a href="{internal_href("methodologie")}" target="_self">Méthodologie →</a></div>',
        unsafe_allow_html=True)


def _render_reperes_region(master: pd.DataFrame, data: dict, code: str) -> None:
    from .. import territoire as T
    reg = master[master["Code région"].astype(str) == str(code)]
    if reg.empty:
        _render_reperes_france(master); return
    nom = str(reg.iloc[0]["Nom de la région"])
    num = lambda c: pd.to_numeric(reg[c], errors="coerce") if c in reg.columns else pd.Series(dtype=float)
    numn = lambda c: pd.to_numeric(master[c], errors="coerce")
    pop = num("population_num"); part_apl = num("part_pop_apl_inf_2_5"); apl = num("apl_dept"); sc = num("score_global")
    pop_sous = float((part_apl * pop).sum()); part_sous = pop_sous / float(pop.sum()) if pop.sum() > 0 else float("nan")
    part_sous_nat = float((numn("part_pop_apl_inf_2_5") * numn("population_num")).sum() / numn("population_num").sum())
    crit = reg[reg["zone_short"] == "Critique"].sort_values("score_global")
    pop15 = float(num("acces_mg_pop_sup_15").sum()); popins = float(num("acces_mg_pop").sum())
    part15 = pop15 / popins if popins > 0 else float("nan"); part15_nat = float(numn("acces_mg_pop_sup_15").sum() / numn("acces_mg_pop").sum())
    try:
        from ..indices import calculer_indices
        ind = calculer_indices(master, data.get("patho"))
        prio = [str(master.set_index("dept").loc[d, "Nom du département"]) for d in reg["dept"].astype(str) if ind.loc[d, "quadrant"] == "A"]
    except Exception:
        prio = []
    lo = reg.loc[apl.idxmin()]; hi = reg.loc[apl.idxmax()]
    st.markdown(
        f'<div class="kpi-stack-header"><div class="eyebrow">{_esc(nom)}</div>'
        '<h3>Ce qui pose problème <em>dans la région</em></h3></div>'
        '<div class="nat-kpis">'
        + _kpi_html("Habitants sous le repère APL 2,5", _pop_fmt(pop_sous), " hab.",
                    f"{_fr(part_sous * 100)}\u202f% de la population régionale (France : {_fr(part_sous_nat * 100)}\u202f%) · DREES", "apl", crit=part_sous > part_sous_nat)
        + _kpi_html("Disparités entre départements", f"{_fr(apl.min())} à {_fr(apl.max())}", " consult./hab.",
                    f"APL de {_esc(str(lo['Nom du département']))} à {_esc(str(hi['Nom du département']))} · scores de {_fr(sc.min(), 0)} à {_fr(sc.max(), 0)} sur 100", "apl")
        + _kpi_html("Départements en zone critique", f"{len(crit)}", f" sur {len(reg)}",
                    (", ".join(_esc(str(x)) for x in crit["Nom du département"].head(4)) if len(crit) else "aucun · tiers des départements les moins bien placés au score"), "zone", crit=len(crit) > 0)
        + _kpi_html("À examiner en priorité", f"{len(prio)}", f" sur {len(reg)}",
                    (", ".join(_esc(x) for x in prio[:4]) + " · offre sous la médiane nationale et besoins au-dessus") if prio else "aucun département en quadrant « offre faible, besoins forts »")
        + _kpi_html("À plus de 15 min d’un généraliste", (_fr(part15 * 100) + "\u202f%") if pd.notna(part15) else "N/D", "",
                    f"{_pop_fmt(pop15)} habitants (France : {_fr(part15_nat * 100)}\u202f%) · INSEE 2025" if pd.notna(part15) else "temps INSEE non disponible", "temps_acces")
        + '</div>'
        f'<div class="nat-method">Références nationales en comparaison. Diagnostic détaillé, départements prioritaires et leviers : '
        f'<a href="{internal_href("region", region_code=str(code))}" target="_self">fiche {_esc(nom)} →</a> · '
        f'<a href="{internal_href("exploration")}" target="_self">Prioriser →</a></div>',
        unsafe_allow_html=True)


def _render_reperes_departement(master: pd.DataFrame, data: dict, code: str) -> None:
    from ..scoring import fmt_classement_national, get_score_breakdown
    rows = master[master["dept"] == code]
    if rows.empty:
        _render_reperes_france(master); return
    r = rows.iloc[0]; nom = str(r["Nom du département"])
    numn = lambda c: pd.to_numeric(master[c], errors="coerce")
    v = lambda c: pd.to_numeric(pd.Series([r.get(c)]), errors="coerce").iloc[0]
    nb = int(master["score_global"].notna().sum())
    score = v("score_global"); zone = str(r.get("zone_short", "")); apl = v("apl_dept"); apl_med = float(numn("apl_dept").median())
    part_apl = v("part_pop_apl_inf_2_5"); pop = v("population_num")
    part15 = v("acces_mg_part_sup_15"); pop15 = v("acces_mg_pop_sup_15"); part15_nat = float(numn("acces_mg_part_sup_15").median())
    med = v("med_gen_pour_100k"); med_nat = float(numn("med_gen_pour_100k").median())
    p65 = v("pct_plus_65"); p65_nat = float(numn("pct_plus_65").median())
    bd = [b for b in get_score_breakdown(r) if b["score"] is not None]
    faibles = ", ".join(b["label"][0].lower() + b["label"][1:] for b in sorted(bd, key=lambda b: b["score"])[:2])
    lecture = {"Critique": "tiers des départements les moins bien placés", "Intermédiaire": "tiers médian des départements",
               "Favorable": "tiers des départements les mieux placés"}.get(zone, "sans score")
    st.markdown(
        f'<div class="kpi-stack-header"><div class="eyebrow">{_esc(nom)} ({code})</div>'
        '<h3>Ce qui pose problème <em>ici</em></h3></div>'
        '<div class="nat-kpis">'
        + _kpi_html("Score Sant’active", _fr(score) if pd.notna(score) else "N/D", " /100",
                    (f"{fmt_classement_national(r.get('rang_national'), nb)} sur {nb} · {lecture} · décroche sur {_esc(faibles)}" if pd.notna(score) else "données insuffisantes"),
                    "score_global", crit=zone == "Critique")
        + _kpi_html("Accessibilité aux généralistes (APL)", _fr(apl, 2) if pd.notna(apl) else "N/D", " consult./hab.",
                    (f"médiane des départements {_fr(apl_med, 2)} · " + ((f"{_pop_fmt(part_apl * pop)} habitants ({_fr(part_apl * 100, 0)}\u202f%) sous le repère 2,5" if part_apl > 0 else "aucun habitant sous le repère 2,5") if pd.notna(part_apl) and pd.notna(pop) else "")) if pd.notna(apl) else "", "apl", crit=pd.notna(apl) and apl < 2.5)
        + _kpi_html("Généralistes", _ent(med) if pd.notna(med) else "N/D", " /100k hab.",
                    f"médiane {_ent(med_nat)} · RPPS 2026", "med_100k", crit=pd.notna(med) and med < med_nat * 0.8)
        + _kpi_html("À plus de 15 min d’un généraliste", (_fr(part15 * 100) + "\u202f%") if pd.notna(part15) else "N/D", "",
                    (f"{_ent(pop15)} habitants · médiane des départements {_fr(part15_nat * 100)}\u202f% · INSEE 2025" if pd.notna(part15) else "hors champ de la base INSEE (indicateur interne en repli sur la fiche)"), "temps_acces", crit=pd.notna(part15) and part15 > 0.03)
        + _kpi_html("65 ans et plus", (_fr(p65) + "\u202f%") if pd.notna(p65) else "N/D", "",
                    f"médiane {_fr(p65_nat)}\u202f% · recensement 2021", "pct_65", crit=pd.notna(p65) and p65 > p65_nat + 3)
        + '</div>'
        f'<div class="nat-method">Références nationales en comparaison (médianes des départements). '
        f'<a href="{internal_href("dept", dept_code=code)}" target="_self">Diagnostic complet et leviers →</a> · '
        f'<a href="{internal_href("dept", dept_code=code)}#communes" target="_self">Communes prioritaires →</a></div>',
        unsafe_allow_html=True)


def _render_reperes_commune(master: pd.DataFrame, data: dict, t) -> None:
    """Commune : seulement ce qui existe à cette échelle (temps INSEE, APL communal, population) ; le
    score et les comparaisons restent ceux du département, nommés comme tels."""
    from ..commune_opportunity import load_acces_insee_communes, load_apl_communes, norm_commune_name
    from ..scoring import fmt_classement_national
    nom_c, dept = t.commune_nom, t.dept_code
    rows = master[master["dept"] == dept]
    if rows.empty:
        _render_reperes_france(master); return
    r = rows.iloc[0]; nb = int(master["score_global"].notna().sum())
    # données communales : appariement par nom via le référentiel API Géo
    temps = apl_c = popc = None; offre = None
    try:
        from pathlib import Path
        from ..config import DATA_DIR
        ref = pd.read_csv(Path(DATA_DIR) / "communes_population_geoapi.csv", dtype={"code_insee": str, "dept": str})
        ref = ref[ref["dept"].astype(str).str.zfill(2) == dept]
        key = norm_commune_name(nom_c)
        hit = ref[ref["nom"].map(norm_commune_name) == key]
        if not hit.empty:
            code_insee = str(hit.iloc[0]["code_insee"]); popc = float(hit.iloc[0]["population"])
            ins = load_acces_insee_communes(); row = ins[ins["code_insee"] == code_insee]
            if not row.empty:
                temps = float(row.iloc[0]["temps_acces"]); offre = bool(row.iloc[0]["offre_sur_place"])
            apl_c = load_apl_communes().get(code_insee)
    except Exception:
        pass
    cells = ""
    if popc is not None:
        cells += _kpi_html("Population", _ent(popc), " hab.", "population municipale · INSEE")
    if temps is not None:
        cells += _kpi_html("Temps vers un généraliste", _fr(temps, 0), " min",
                           ("généraliste présent dans la commune · " if offre else "") + "moyenne des habitants, en voiture · INSEE 2025", "temps_acces", crit=temps > 15)
    if apl_c is not None and pd.notna(apl_c):
        cells += _kpi_html("APL de la commune", _fr(float(apl_c)), " consult./hab.", "repère de sous-densité 2,5 · DREES", "apl", crit=float(apl_c) < 2.5)
    if not cells:
        cells = _kpi_html("Données communales", "partielles", "", "temps d’accès et APL non appariés pour cette commune")
    cells += _kpi_html(f"Département : {_esc(str(r['Nom du département']))}", _fr(r.get("score_global")) if pd.notna(pd.to_numeric(pd.Series([r.get('score_global')]), errors='coerce').iloc[0]) else "N/D", " /100",
                       f"score Sant’active départemental · {fmt_classement_national(r.get('rang_national'), nb)} sur {nb} · zone {str(r.get('zone_short', '')).lower()}", "score_global")
    st.markdown(
        f'<div class="kpi-stack-header"><div class="eyebrow">{_esc(nom_c)} · {_esc(str(r["Nom du département"]))}</div>'
        '<h3>Ce que l’on sait <em>à l’échelle de la commune</em></h3></div>'
        f'<div class="nat-kpis">{cells}</div>'
        '<div class="nat-method">Pas de score communal : le score, les leviers et la comparaison existent à l’échelle du département. '
        f'<a href="{internal_href("commune", commune_code=t.code)}" target="_self">Fiche de la commune →</a> · '
        f'<a href="{internal_href("dept", dept_code=dept)}" target="_self">Diagnostic du département →</a></div>',
        unsafe_allow_html=True)


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
