"""Accès routier aux soins de premier recours — simulateur d'implantation (pilotes).

Deux sources combinées, chacune à sa place :

- **Situation actuelle** : base INSEE « localisation et accès de la population
  aux équipements » (millésime 2025) — pour chaque carreau habité de 200 m, la
  durée en voiture (distancier Metric-OSRM) vers le médecin généraliste le plus
  proche (BPE 2025, lieu d'exercice réel). Fichier par département pilote :
  static/geo/carreaux_mg_<dept>.csv.gz (scripts/donnees/calculer_acces_insee.py).
- **Scénario** : isochrones IGN Géoplateforme (10, 15, 20 min, réseau routier
  BD TOPO) calculées à la demande depuis le centre de la commune choisie. Un
  carreau situé dans l'isochrone S min de la nouvelle offre passe à ≤ S min.

Ce que mesure la simulation : un **gain de proximité géographique théorique**
(habitants dont le temps de trajet vers un généraliste passerait sous le seuil),
pas un gain de prise en charge : capacité d'accueil, rendez-vous disponibles et
flux vers les départements voisins ne sont pas pris en compte.

Pilotes : un département n'est proposé que s'il figure dans PILOTES_VALIDES
(calcul vérifié) et si ses fichiers carreaux + communes sont présents.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from ..components.maps import TILE_ATTR, TILE_URL
from ..components.nav import NavCrumb, internal_href, render_breadcrumb

GEO_DIR = Path("static/geo")
# Départements pilotes validés (données INSEE présentes, isochrones IGN testées,
# cohérence contrôlée — voir docs/EVOLUTIONS_MOTEUR.md §14). Un fichier présent
# dans static/geo n'est affiché que si le département figure ici.
PILOTES_VALIDES = {"18": "Cher", "23": "Creuse", "93": "Seine-Saint-Denis", "974": "La Réunion", "972": "Martinique"}
SEUILS = (10, 15, 20)
_COULEURS = {10: "#1B5E3F", 15: "#7DBE8F", 20: "#E8A838", 30: "#D9772B", 99: "#A51C30"}
_LIB_CLASSE = {10: "≤ 10 min", 15: "10–15 min", 20: "15–20 min", 30: "20–30 min", 99: "> 30 min"}
_NEUF = "#1A3D8F"
_SOURCE_INSEE = ("Insee, base permanente des équipements 2025, distancier Metric-OSRM, "
                 "© les contributeurs d’OpenStreetMap et du projet OSRM")


# ── Chargement ────────────────────────────────────────────────────────────────

def pilotes_disponibles() -> dict[str, str]:
    """Départements pilotes validés dont les fichiers (carreaux + communes) sont présents."""
    return {d: n for d, n in PILOTES_VALIDES.items()
            if (GEO_DIR / f"carreaux_mg_{d}.csv.gz").exists() and (GEO_DIR / f"communes_{d}.json").exists()}


@st.cache_data(show_spinner=False)
def charger_carreaux(dept: str) -> pd.DataFrame:
    df = pd.read_csv(GEO_DIR / f"carreaux_mg_{dept}.csv.gz", dtype={"code_insee": str, "commune_offre": str})
    df["classe"] = df["duree"].apply(_classe)
    return df


@st.cache_data(show_spinner=False)
def charger_communes(dept: str) -> pd.DataFrame:
    d = json.loads((GEO_DIR / f"communes_{dept}.json").read_text())
    return pd.DataFrame(d["communes"]).astype({"code_insee": str})


@st.cache_data(show_spinner=False)
def _charger_legacy(dept: str) -> dict | None:
    """Ancien calcul par itinéraires IGN entre centres de communes (Cher) : vérification technique."""
    p = GEO_DIR / f"acces_ign_{dept}.json"
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_data(ttl=86400, show_spinner=False)
def _isochrone_live(lon: float, lat: float, minutes: int) -> dict | None:
    """Isochrone IGN à la demande (voiture, départ), mise en cache 24 h ; reprise sur 429/5xx."""
    import time

    import requests

    params = {"point": f"{lon},{lat}", "resource": "bdtopo-valhalla", "costType": "time",
              "costValue": str(minutes * 60), "profile": "car", "direction": "departure", "geometryFormat": "geojson"}
    for tentative in range(2):
        try:
            r = requests.get("https://data.geopf.fr/navigation/isochrone", timeout=20, params=params)
            if r.status_code == 200:
                return r.json().get("geometry")
            if r.status_code not in (429, 500, 502, 503, 504):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (tentative + 1))
    return None


# ── Calculs ───────────────────────────────────────────────────────────────────

def _classe(t) -> int:
    """Classe de temps (borne supérieure en minutes) : 10, 15, 20, 30 ou 99 (> 30)."""
    if pd.isna(t):
        return 99
    for s in (10, 15, 20, 30):
        if t <= s:
            return s
    return 99


def situation_communes(carreaux: pd.DataFrame, communes: pd.DataFrame) -> pd.DataFrame:
    """Situation actuelle par commune : population carroyée, temps moyen pondéré,
    parts au-delà de 10/15/20/30 min, présence d'un généraliste, classe du temps moyen."""
    rows = []
    for code, g in carreaux.groupby("code_insee", sort=False):
        p, d = g["pop"].to_numpy(float), g["duree"].to_numpy(float)
        tot = p.sum()
        row = {"code_insee": code, "pop": tot, "t_moy": float((d * p).sum() / tot),
               "offre": bool((g["commune_offre"] == code).any())}
        for s in (10, 15, 20, 30):
            row[f"pop_sup_{s}"] = float(p[d > s].sum())
        rows.append(row)
    sit = pd.DataFrame(rows)
    sit["classe"] = sit["t_moy"].apply(_classe)
    out = communes.merge(sit, on="code_insee", how="inner")
    return out


def scenario(carreaux: pd.DataFrame, geoms: dict[int, dict]) -> pd.DataFrame:
    """Classe « nouvelle offre » de chaque carreau : plus petit seuil dont l'isochrone le contient (99 sinon)."""
    from shapely import contains_xy
    from shapely.geometry import shape

    com = carreaux.copy()
    classe_neuf = np.full(len(com), 99, dtype=int)
    for s in sorted(SEUILS, reverse=True):   # du plus large au plus serré : le plus serré l'emporte
        g = geoms.get(s)
        if not g:
            continue
        poly = shape(g).buffer(0)
        inside = contains_xy(poly, com["lon"].to_numpy(float), com["lat"].to_numpy(float))
        classe_neuf[inside] = s
    com["classe_neuf"] = classe_neuf
    com["classe_apres"] = np.minimum(com["classe"], com["classe_neuf"])
    return com


def gains(com: pd.DataFrame, seuil: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carreaux (gagnés, rapprochés) au seuil : gagnés = > seuil aujourd'hui et dans l'isochrone ≤ seuil ;
    rapprochés = déjà ≤ seuil mais dans une isochrone plus serrée que leur temps actuel."""
    gain = com[(com["duree"] > seuil) & (com["classe_neuf"] <= seuil)]
    rapp = com[(com["duree"] <= seuil) & (com["classe_neuf"] < com["duree"])]
    return gain, rapp


def gains_par_commune(gain: pd.DataFrame, sit: pd.DataFrame) -> pd.DataFrame:
    if gain.empty:
        return pd.DataFrame(columns=["code_insee", "nom", "pop_gain", "pop", "part", "t_avant", "classe_apres"])
    g = gain.groupby("code_insee").apply(lambda d: pd.Series({
        "pop_gain": d["pop"].sum(),
        "t_avant": float((d["duree"] * d["pop"]).sum() / d["pop"].sum()),
        "classe_apres": int(d["classe_neuf"].min()),
    }), include_groups=False).reset_index()
    g = g.merge(sit[["code_insee", "nom", "pop", "t_moy"]], on="code_insee", how="left")
    g["part"] = g["pop_gain"] / g["pop"]
    return g.sort_values("pop_gain", ascending=False)


# ── Rendu ─────────────────────────────────────────────────────────────────────

def _fmt(n) -> str:
    return f"{int(round(float(n))):,}".replace(",", " ")


def _kpi(label: str, value: str, ctx: str, color: str = "#1A3D8F") -> str:
    return (f'<div class="diagnostic-kpi" style="padding:12px 14px;border-top:3px solid {color};">'
            f'<div class="diagnostic-kpi-label">{label}</div>'
            f'<div class="diagnostic-kpi-value" style="font-size:26px;margin-bottom:6px;">{value}</div>'
            f'<div style="font-size:11px;color:#6B6B68;line-height:1.4;">{ctx}</div></div>')


def _square(lon: float, lat: float, half_m: float = 100.0) -> list[list[float]]:
    dlat = half_m / 111_320
    dlon = half_m / (111_320 * max(math.cos(math.radians(lat)), 0.2))
    return [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat]]


def _squares_layer(df: pd.DataFrame, name: str, color_fn, fill_opacity: float, weight: float = 0.0,
                   tooltip: str | None = None) -> folium.GeoJson | None:
    if df.empty:
        return None
    feats = [{"type": "Feature", "properties": {"c": color_fn(r)},
              "geometry": {"type": "Polygon", "coordinates": [_square(float(r["lon"]), float(r["lat"]))]}}
             for _, r in df.iterrows()]
    return folium.GeoJson({"type": "FeatureCollection", "features": feats}, name=name,
                          style_function=lambda f, fo=fill_opacity, w=weight: {
                              "fillColor": f["properties"]["c"], "color": f["properties"]["c"],
                              "weight": w, "fillOpacity": fo},
                          tooltip=tooltip)


def _resolve_dept(data: dict, pilotes: dict[str, str]) -> tuple[str, str | None]:
    """Département affiché (toujours un pilote) et, le cas échéant, le message qui explique l'écart
    avec le territoire de référence. Le territoire de travail reste celui de la barre : changer de
    pilote se fait par un lien qui met aussi à jour la référence (paramètre t)."""
    from .. import territoire as T

    master = data["master"]
    t = T.get()
    demande = str(st.query_params.get("dept_code") or "")
    if not demande and t.kind == "dept":
        demande = t.code
    if demande in pilotes:
        return demande, None
    liens = " · ".join(f'<a href="{internal_href("acces", dept_code=c, t=f"d{c}")}" target="_self">{html.escape(n)}</a>'
                       for c, n in pilotes.items())
    if t.kind == "region" and not demande:
        dans_region = [d for d in pilotes if d in set(T.dept_codes(t, master))]
        if dans_region:
            return dans_region[0], None
        return next(iter(pilotes)), (f"Pas de département pilote en {html.escape(T.nom_court(t, master))} pour l’instant. "
                                     f"Simulateur présenté sur un pilote (le territoire de référence reste la région) : {liens}.")
    if demande:
        nom = T.nom_court(T.Territoire("dept", demande), master)
        return next(iter(pilotes)), (f"Simulation <strong>pas encore disponible pour {html.escape(nom)}</strong> ({demande}). "
                                     f"Choisir un pilote change le territoire de travail : {liens}.")
    return next(iter(pilotes)), f"Aucun territoire de référence choisi : simulateur présenté sur le Cher. Pilotes : {liens}."


def _urbain_note(dept: str, nom_dept: str, master: pd.DataFrame, part_sup: float, seuil: int) -> str:
    """Dans un territoire dense, la proximité n'est pas le critère discriminant : orienter vers l'APL,
    la densité et les besoins (valeurs du département, avec la médiane nationale)."""
    r = master[master["dept"] == dept]
    if r.empty:
        return ""
    r = r.iloc[0]
    def _v(col, fmt):
        v = pd.to_numeric(pd.Series([r.get(col)]), errors="coerce").iloc[0]
        return fmt.format(v).replace(".", ",") if pd.notna(v) else "n.d."
    def _m(col, fmt):
        v = pd.to_numeric(master[col], errors="coerce").median()
        return fmt.format(v).replace(".", ",") if pd.notna(v) else "n.d."
    return (f"<strong>Dans {html.escape(nom_dept)}, la proximité géographique n’est pas le critère discriminant</strong> : "
            f"{(1 - part_sup) * 100:.1f}".replace(".", ",") + f" % des habitants sont déjà à moins de {seuil} min en voiture d’un généraliste, "
            f"une implantation ne rapproche donc presque personne au sens de cette mesure. Les difficultés d’accès, réelles, relèvent "
            f"de la capacité et de la demande : APL {_v('apl_dept', '{:.1f}')} (médiane des départements {_m('apl_dept', '{:.1f}')}), "
            f"{_v('med_gen_pour_100k', '{:.0f}')} généralistes pour 100 000 habitants (médiane {_m('med_gen_pour_100k', '{:.0f}')}), "
            f"{_v('pct_plus_65', '{:.1f}')} % de 65 ans et plus. Voir la lecture « capacité » et les leviers du "
            f"<a href=\"{internal_href('dept', dept_code=dept)}\" target=\"_self\">diagnostic</a>.")


def render(data: dict) -> None:
    pilotes = pilotes_disponibles()
    names = data["master"].set_index("dept")["Nom du département"].to_dict()

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Simuler une implantation")], key_prefix="ign_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">PILOTE EXPÉRIMENTAL</span>'
        '<span class="dot"></span><span class="region">Carreaux INSEE 2025 · isochrones IGN · gain de proximité théorique</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Simuler une implantation <em>de médecine générale</em></h1></div>'
        '</div>', unsafe_allow_html=True)
    if not pilotes:
        st.info("Aucun département pilote calculé (fichiers static/geo/carreaux_mg_<dept>.csv.gz et communes_<dept>.json).")
        return

    dept, message = _resolve_dept(data, pilotes)
    if message:
        st.markdown(f'<div class="sa-notice">{message}</div>', unsafe_allow_html=True)
    nom_dept = names.get(dept, pilotes.get(dept, dept))
    carreaux = charger_carreaux(dept)
    communes = charger_communes(dept)
    sit = situation_communes(carreaux, communes)
    tot = float(carreaux["pop"].sum()) or 1.0
    nb_offre = int(sit["offre"].sum())
    loin = sit[sit["t_moy"] > 15]

    # ── Territoire pilote et liens de parcours ───────────────────────────────
    autres = " · ".join(f'<a href="{internal_href("acces", dept_code=c, t=f"d{c}")}" target="_self">{html.escape(n)}</a>'
                        for c, n in pilotes.items() if c != dept) or "aucun autre pour l’instant"
    st.markdown(
        f'<div class="ign-pilote"><div><span class="ign-pilote-lbl">Territoire de travail · pilote</span>'
        f'<span class="ign-pilote-nom">{html.escape(nom_dept)} ({dept})</span>'
        f'<span class="ign-pilote-ctx">{len(sit)} communes · {nb_offre} avec au moins un généraliste (BPE 2025) · '
        f'{_fmt(tot)} habitants localisés · autres pilotes : {autres}</span></div>'
        f'<div class="ign-pilote-links"><a href="{internal_href("dept", dept_code=dept)}" target="_self">Diagnostic {html.escape(nom_dept)} →</a>'
        f'<a href="{internal_href("dept", dept_code=dept)}#communes" target="_self">Communes prioritaires →</a></div></div>',
        unsafe_allow_html=True)

    # ── Scénario : contrôles (clés par département : changer de pilote réinitialise la commune) ──
    st.markdown('<div class="section-header" style="margin-top:18px;"><div class="section-eyebrow">SIMULATION</div>'
                '<h2 class="section-title">Si une offre s’installait <em>ici</em>, qui s’en rapprocherait ?</h2>'
                '<p class="section-lead">Choisissez une commune et un seuil de trajet. Les isochrones IGN calculées depuis '
                'le centre de la commune donnent les habitants qui passeraient sous le seuil, carreau par carreau '
                '(population localisée INSEE).</p></div>', unsafe_allow_html=True)
    s1, s2 = st.columns([2.2, 1])
    seuil = s2.radio("Seuil de trajet en voiture", SEUILS, index=1, horizontal=True, key=f"ign_seuil_{dept}",
                     format_func=lambda m: f"{m} min")
    cands = sit.assign(_pot=sit[f"pop_sup_{seuil}"]).sort_values(["_pot", "pop"], ascending=False)
    labels = {}
    for _, r in cands.iterrows():
        pot = r[f"pop_sup_{seuil}"]
        labels[r["nom"]] = (f'{r["nom"]} · {_fmt(r["pop"])} hab. · {r["t_moy"]:.0f} min en moyenne'
                            + (f' · {_fmt(pot)} hab. à plus de {seuil} min' if pot >= 50 else "")
                            + (" · généraliste présent" if r["offre"] else ""))
    options = list(labels)
    key_sim = f"ign_sim_{dept}"
    qp_commune = str(st.query_params.get("commune") or "")
    if key_sim not in st.session_state or st.session_state[key_sim] not in options:
        st.session_state[key_sim] = qp_commune if qp_commune in labels else options[0]
    choix = s1.selectbox("Commune d’implantation", options, format_func=lambda n: labels.get(n, n), key=key_sim,
                         help="Classées par population aujourd’hui au-delà du seuil choisi (plus grand potentiel en premier).")
    row = cands[cands["nom"] == choix].iloc[0]
    part_sup = float(carreaux.loc[carreaux["duree"] > seuil, "pop"].sum()) / tot

    # Tout ce qui dépend du département et du scénario est rendu dans un même conteneur :
    # au changement de territoire, l'ancien contenu est remplacé par l'état de chargement
    # avant tout appel réseau (aucun résultat du territoire précédent ne reste affiché).
    zone = st.empty()
    with zone.container():
        st.markdown(f'<div class="sa-loading">Calcul du scénario pour <strong>{html.escape(nom_dept)}</strong> — '
                    f'isochrones IGN depuis {html.escape(choix)}…</div>', unsafe_allow_html=True)
    sim_geoms = {m: g for m in SEUILS if (g := _isochrone_live(float(row["lon"]), float(row["lat"]), m))}
    with zone.container():
        _render_resultats(data, dept, nom_dept, carreaux, communes, sit, row, choix, seuil, sim_geoms, part_sup, tot, loin, nb_offre)


def _render_resultats(data, dept, nom_dept, carreaux, communes, sit, row, choix, seuil, sim_geoms, part_sup, tot, loin, nb_offre) -> None:
    master = data["master"]
    com = carreaux
    gain = rapp = pd.DataFrame()
    gpc = pd.DataFrame()
    if not sim_geoms:
        st.warning("Le service d’isochrones IGN n’a pas répondu (lenteur, erreur ou quota). Aucun scénario n’est affiché ; "
                   "la situation actuelle ci-dessous reste valable.")
        if st.button("Réessayer le calcul", key=f"ign_retry_{dept}"):
            _isochrone_live.clear()
            st.rerun()
    else:
        if len(sim_geoms) < len(SEUILS):
            st.warning("Isochrone(s) manquante(s) : " + ", ".join(f"{m} min" for m in SEUILS if m not in sim_geoms)
                       + " — le scénario est incomplet (service IGN). Réessayez dans quelques secondes.")
        com = scenario(carreaux, sim_geoms)
        gain, rapp = gains(com, seuil)
        gpc = gains_par_commune(gain, sit)
        avant = float(com.loc[com["duree"] > seuil, "pop"].sum())
        apres = avant - float(gain["pop"].sum())

        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(_kpi("Nouvellement couverts", f"+{_fmt(gain['pop'].sum())}",
                         f"habitants qui passeraient sous {seuil} min, dans {len(gpc)} commune{'s' if len(gpc) != 1 else ''}", _NEUF),
                    unsafe_allow_html=True)
        m2.markdown(_kpi("Rapprochés", f"{_fmt(rapp['pop'].sum())}",
                         f"habitants déjà sous {seuil} min dont le trajet raccourcirait", "#1B5E3F"), unsafe_allow_html=True)
        m3.markdown(_kpi(f"Au-delà de {seuil} min aujourd’hui", f"{_fmt(avant)}",
                         f"habitants ({avant / tot * 100:.1f}".replace(".", ",") + " % du département)", "#D9772B"), unsafe_allow_html=True)
        m4.markdown(_kpi("Après le scénario", f"{_fmt(apres)}",
                         f"habitants resteraient au-delà de {seuil} min ({apres / tot * 100:.1f}".replace(".", ",") + " %)", "#D9772B"), unsafe_allow_html=True)

        situ = (f"<strong>{html.escape(choix)}</strong> ({_fmt(row['pop'])} habitants localisés) : temps moyen actuel "
                f"{row['t_moy']:.0f} min vers un généraliste"
                + (", un généraliste y est déjà recensé" if row["offre"] else ", aucun généraliste recensé dans la commune") + ".")
        if len(gpc):
            lst = ", ".join(f"{html.escape(str(r['nom']))} ({_fmt(r['pop_gain'])} hab., {r['t_avant']:.0f} min → ≤ {int(r['classe_apres'])} min)"
                            for _, r in gpc.head(8).iterrows())
            texte = (f"{situ} Une offre de médecine générale à {html.escape(choix)} placerait <strong>{_fmt(gain['pop'].sum())} habitants</strong> "
                     f"de {len(gpc)} commune{'s' if len(gpc) != 1 else ''} à moins de {seuil} min : {lst}"
                     + (" …" if len(gpc) > 8 else "") + ".")
        else:
            texte = (f"{situ} <strong>Personne ne passerait sous {seuil} min</strong> : les habitants situés à moins de "
                     f"{seuil} min de {html.escape(choix)} le sont déjà d’un généraliste existant. Ce zéro ne signifie pas "
                     f"qu’une implantation serait sans intérêt : elle raccourcirait des trajets, soulagerait les cabinets "
                     f"voisins et pourrait répondre à un manque de capacité, que cette mesure géographique ne voit pas.")
        if len(rapp):
            texte += f" Par ailleurs {_fmt(rapp['pop'].sum())} habitants déjà sous le seuil verraient leur trajet raccourci."
        texte += (" <span style='color:#6B6B68;'>Gain de proximité théorique : capacité du cabinet, rendez-vous disponibles, "
                  "transports en commun et offres des départements voisins ne sont pas pris en compte.</span>")
        st.markdown(f'<p class="dim-switch-note">{texte}</p>', unsafe_allow_html=True)
        if part_sup < 0.01:
            note = _urbain_note(dept, nom_dept, master, part_sup, seuil)
            if note:
                st.markdown(f'<div class="sa-notice sa-notice--info">{note}</div>', unsafe_allow_html=True)

        if len(gpc):
            rows = "".join(
                f'<tr><td class="metric-label">{html.escape(str(r["nom"]))}</td><td data-label="Nouvellement couverts">{_fmt(r["pop_gain"])} hab.</td>'
                f'<td data-label="Part de la commune">{r["part"] * 100:.0f}\u202f%</td><td data-label="Trajet moyen aujourd’hui">{r["t_avant"]:.0f} min</td>'
                f'<td data-label="Avec la nouvelle offre">≤ {int(r["classe_apres"])} min</td></tr>'
                for _, r in gpc.head(15).iterrows())
            st.markdown('<div class="sa-tbl-scroll"><table class="comparison-table-v2 commune-action-table"><thead><tr>'
                        '<th class="metric-col">Commune</th><th class="metric-col">Habitants nouvellement couverts</th>'
                        '<th class="metric-col">Part de la commune</th><th class="metric-col">Trajet moyen aujourd’hui</th>'
                        '<th class="metric-col">Avec la nouvelle offre</th></tr></thead>'
                        f'<tbody>{rows}</tbody></table></div>'
                        + (f'<p class="sa-couverture">{len(gpc) - 15} autres communes concernées, gains plus faibles.</p>' if len(gpc) > 15 else ""),
                        unsafe_allow_html=True)

    # ── Carte ─────────────────────────────────────────────────────────────────
    v1, v2 = st.columns([2.2, 1])
    mode = v1.radio("Affichage de la carte", ["Situation actuelle", "Avec la nouvelle offre", "Gain seulement"],
                    index=1 if sim_geoms else 0, horizontal=True, key=f"ign_mode_{dept}")
    cadrage = v2.toggle("Cadrer sur le scénario", value=True, key=f"ign_cadrage_{dept}") if sim_geoms else False
    m = folium.Map(location=[float(carreaux["lat"].mean()), float(carreaux["lon"].mean())], zoom_start=9,
                   tiles=TILE_URL, attr=TILE_ATTR, scrollWheelZoom=False)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container{background:#F4F3EE!important;}"
        ".sa-ign-legend{font-family:Marianne,Inter,sans-serif;font-size:11px;background:rgba(255,255,255,.95);"
        "padding:10px 12px;border-radius:4px;border:1px solid #C9C6BA;line-height:1.7;}"
        ".sa-ign-legend b{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B68;margin-bottom:4px;}"
        ".sa-ign-legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:middle;}"
        ".sa-ign-legend i.pt{border-radius:50%;width:10px;height:10px;}"
        ".sa-ign-star{font-size:26px;line-height:1;color:#1A3D8F;text-shadow:0 0 3px #fff,0 0 3px #fff;}</style>"))
    faible = mode == "Gain seulement"
    eloignes = carreaux[carreaux["duree"] > 10]
    layer = _squares_layer(eloignes, "Aujourd’hui : carreaux à plus de 10 min",
                           lambda r: _COULEURS[int(r["classe"])], 0.12 if faible else 0.55)
    if layer is not None:
        layer.add_to(m)
    if sim_geoms and mode != "Situation actuelle":
        for s_ in (20, 15, 10):
            if s_ in sim_geoms and (s_ == seuil or mode == "Avec la nouvelle offre"):
                folium.GeoJson({"type": "Feature", "geometry": sim_geoms[s_]}, name=f"Nouvelle offre ≤ {s_} min",
                               style_function=lambda f, s2=s_: {"fillColor": _NEUF, "color": _NEUF, "weight": 2.2 if s2 == seuil else 1,
                                                                "fillOpacity": 0.10 if s2 == seuil else 0.05, "dashArray": "6 4"}).add_to(m)
        lg = _squares_layer(gain, "Carreaux nouvellement couverts", lambda r: _NEUF, 0.85)
        if lg is not None:
            lg.add_to(m)
        lr = _squares_layer(rapp, "Carreaux rapprochés", lambda r: "#1B5E3F", 0.0, weight=1.2)
        if lr is not None:
            lr.add_to(m)
    gain_codes = set(gpc["code_insee"]) if len(gpc) else set()
    for _, r in sit.iterrows():
        nom = html.escape(str(r["nom"]))
        if r["offre"]:
            folium.CircleMarker([r["lat"], r["lon"]], radius=4, color="#FFFFFF", fill=True, fill_color="#0A1938",
                                fill_opacity=1, weight=1.2,
                                tooltip=f"{nom} · généraliste présent · {r['t_moy']:.0f} min en moyenne").add_to(m)
        elif r["code_insee"] in gain_codes:
            g_ = gpc[gpc["code_insee"] == r["code_insee"]].iloc[0]
            folium.CircleMarker([r["lat"], r["lon"]], radius=7, color=_NEUF, fill=True, fill_color="#FFFFFF", fill_opacity=1, weight=3,
                                tooltip=f"{nom} · +{_fmt(g_['pop_gain'])} hab. sous {seuil} min ({g_['part'] * 100:.0f} % de la commune)").add_to(m)
        elif not faible:
            cl = int(r["classe"])
            folium.CircleMarker([r["lat"], r["lon"]], radius=3 if cl <= 15 else 5, color="#FFFFFF" if cl > 15 else _COULEURS[cl],
                                fill=True, fill_color=_COULEURS[cl], fill_opacity=0.95, weight=1 if cl > 15 else 0.5,
                                tooltip=f"{nom} · {r['t_moy']:.0f} min en moyenne · {_fmt(r['pop'])} hab.").add_to(m)
    folium.Marker([float(row["lat"]), float(row["lon"])], tooltip=f"Nouvelle offre simulée : {html.escape(choix)}",
                  icon=folium.DivIcon(html='<div class="sa-ign-star">★</div>', icon_size=(26, 26), icon_anchor=(13, 13))).add_to(m)
    if cadrage and sim_geoms:
        from shapely.geometry import shape as _shape
        b = _shape(sim_geoms[max(sim_geoms)]).bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]], padding=(20, 20))
    else:
        m.fit_bounds([[float(carreaux["lat"].min()), float(carreaux["lon"].min())],
                      [float(carreaux["lat"].max()), float(carreaux["lon"].max())]], padding=(10, 10))
    legend = ('<div class="sa-ign-legend"><b>Aujourd’hui : trajet vers un généraliste (carreaux 200 m)</b>'
              + "".join(f'<div><i style="background:{_COULEURS[s_]};opacity:.75;"></i>{_LIB_CLASSE[s_]}</div>' for s_ in (15, 20, 30, 99))
              + '<b style="margin-top:6px;">Communes</b>'
              '<div><i class="pt" style="background:#0A1938;"></i>généraliste présent</div>'
              '<div><i class="pt" style="background:#D9772B;"></i>temps moyen &gt; 15 min</div>'
              + (f'<b style="margin-top:6px;">Scénario</b><div><span class="sa-ign-star" style="font-size:14px;">★</span> nouvelle offre simulée</div>'
                 f'<div><i style="border:2px dashed {_NEUF};background:rgba(26,61,143,.15);"></i>zone ≤ {seuil} min depuis la nouvelle offre</div>'
                 f'<div><i style="background:{_NEUF};"></i>habitants nouvellement couverts</div>'
                 '<div><i style="border:2px solid #1B5E3F;background:#fff;"></i>habitants rapprochés</div>' if sim_geoms else "")
              + '</div>')
    m.get_root().html.add_child(folium.Element(
        '<div class="leaflet-bottom leaflet-left" style="pointer-events:none;">'
        f'<div class="leaflet-control" style="margin:0 0 24px 12px;">{legend}</div></div>'))
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=580, returned_objects=[],
              key=f"ign_map_{dept}_{choix}_{seuil}_{mode}_{cadrage}")

    # ── Situation actuelle ────────────────────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:22px;"><div class="section-eyebrow">SITUATION ACTUELLE</div>'
                f'<h2 class="section-title">Où vit-on loin d’un généraliste <em>en {html.escape(nom_dept)} ?</em></h2>'
                '<p class="section-lead">Temps de trajet en voiture depuis chaque carreau habité de 200 m vers le médecin '
                'généraliste le plus proche (lieu d’exercice réel, BPE 2025). Accessibilité géographique : elle ne dit rien '
                'de la capacité des cabinets, des délais de rendez-vous ni des transports en commun.</p></div>', unsafe_allow_html=True)
    c = st.columns(4)
    for col, s_ in zip(c, (10, 15, 20)):
        pop = float(carreaux.loc[carreaux["duree"] <= s_, "pop"].sum())
        col.markdown(_kpi(f"≤ {s_} min", f"{pop / tot * 100:.0f} %", f"de la population ({_fmt(pop)} hab.)", _COULEURS[s_]), unsafe_allow_html=True)
    c[3].markdown(_kpi("> 15 min", _fmt(carreaux.loc[carreaux["duree"] > 15, "pop"].sum()),
                       f"habitants · {len(loin)} commune{'s' if len(loin) != 1 else ''} dont le temps moyen dépasse 15 min", "#D9772B"),
                  unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown('<h4 class="subsection-title">Communes les plus éloignées</h4>', unsafe_allow_html=True)
        top = sit.sort_values("t_moy", ascending=False).head(12)
        rows = "".join(f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr;padding:5px 10px;border-bottom:1px solid #E8E6DD;font-size:12px;">'
                       f'<span>{html.escape(str(r["nom"]))}</span><span style="text-align:right;">{r["t_moy"]:.0f} min</span>'
                       f'<span style="text-align:right;">{_fmt(r["pop"])}</span><span style="text-align:right;color:#6B6B68;">{_fmt(r["pop_sup_15"])}</span></div>'
                       for _, r in top.iterrows())
        st.markdown('<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr;padding:5px 10px;background:#F3F2EC;font-size:10px;font-weight:700;text-transform:uppercase;color:#6B6B68;">'
                    '<span>Commune</span><span style="text-align:right;">Trajet moyen</span><span style="text-align:right;">Hab.</span><span style="text-align:right;">dont &gt; 15 min</span></div>' + rows,
                    unsafe_allow_html=True)
    with c2:
        st.markdown('<h4 class="subsection-title">Répartition de la population</h4>', unsafe_allow_html=True)
        import plotly.graph_objects as go
        bins = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 999)]
        labs = ["≤ 5", "5–10", "10–15", "15–20", "20–30", "> 30"]
        vals = [float(carreaux.loc[(carreaux["duree"] > a) & (carreaux["duree"] <= b), "pop"].sum()) / tot for a, b in bins]
        cols = ["#1B5E3F", "#1B5E3F", "#7DBE8F", "#E8A838", "#D9772B", "#A51C30"]
        fig = go.Figure(go.Bar(x=labs, y=vals, marker_color=cols, text=[f"{v * 100:.0f} %" for v in vals], textposition="outside"))
        fig.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=30), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF8",
                          yaxis=dict(tickformat=".0%", range=[0, max(vals) * 1.25], gridcolor="#E8E6DD"),
                          xaxis_title="minutes de voiture vers le généraliste le plus proche", font=dict(size=11))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Méthode, vérifications et limites"):
        _render_verification(dept, nom_dept, sit, carreaux, data)

    st.markdown(
        f'<div class="ign-pilote-links" style="margin-top:14px;"><a href="{internal_href("dept", dept_code=dept)}" target="_self">← Retour au diagnostic {html.escape(nom_dept)}</a>'
        f'<a href="{internal_href("comparer")}&depts={dept}" target="_self">Comparer {html.escape(nom_dept)} →</a></div>',
        unsafe_allow_html=True)


def _render_verification(dept: str, nom_dept: str, sit: pd.DataFrame, carreaux: pd.DataFrame, data: dict) -> None:
    import plotly.graph_objects as go

    st.markdown(
        "**Situation actuelle.** " + _SOURCE_INSEE + ". Pour chaque carreau habité de 200 m, l’Insee calcule la durée "
        "en voiture vers le généraliste le plus proche (3 candidats à vol d’oiseau, le plus rapide retenu ; durée minimale "
        "1 min). La population des carreaux (Filosofi) diffère légèrement de la population municipale. "
        "Guadeloupe, Guyane et Mayotte sont hors champ de cette base.\n\n"
        "**Scénario.** Isochrones IGN Géoplateforme (BD TOPO, moteur Valhalla, voiture, départ) depuis le centre de la "
        "commune choisie, à 10, 15 et 20 min. Un carreau contenu dans l’isochrone S passe à ≤ S min. Deux distanciers "
        "différents (OSRM pour l’existant, Valhalla pour le scénario) : des écarts de l’ordre de la minute sont possibles "
        "aux limites des isochrones.\n\n"
        "**Ce qui n’est pas mesuré.** Capacité et patientèle des cabinets, délais de rendez-vous, transports en commun, "
        "offres situées hors du département (les carreaux proches d’une limite peuvent déjà être couverts par un "
        "généraliste voisin : l’Insee en tient compte, le scénario aussi puisqu’il ne crée que des gains)."
    )
    # Comparaison avec l'indicateur interne (fichier équipe)
    temps = data.get("temps")
    if temps is not None and not temps.empty:
        from ..commune_opportunity import norm_commune_name
        t = temps[temps["code_departement"].astype(str).str.zfill(2) == dept].copy()
        t["key"] = t["commune"].map(norm_commune_name)
        s = sit.assign(key=sit["nom"].map(norm_commune_name)).merge(t[["key", "temps_acces"]], on="key", how="inner")
        if len(s) > 10:
            nz = s[pd.to_numeric(s["temps_acces"], errors="coerce") > 0]
            rho = nz[["temps_acces", "t_moy"]].corr("spearman").iloc[0, 1] if len(nz) > 5 else float("nan")
            z = s[s["temps_acces"] == 0]
            st.markdown(
                f"**Indicateur interne (fichier équipe).** {len(s)} communes appariées : {len(z)} à « 0 » dans le fichier interne, "
                f"dont {int(z['offre'].sum())} ont bien un généraliste recensé par la BPE 2025 (le 0 signifie « généraliste "
                f"présent », pas un temps de trajet). Pour les communes sans offre, corrélation de Spearman interne / Insee : "
                f"{rho:.2f} ; communes à plus de 15 min : {int((s['temps_acces'] > 15).sum())} (interne) contre "
                f"{int((s['t_moy'] > 15).sum())} (Insee, temps moyen)."
            )
    legacy = _charger_legacy(dept)
    if legacy:
        lg = pd.DataFrame(legacy["communes"]).astype({"code_insee": str})
        both = lg.merge(sit[["code_insee", "t_moy"]], on="code_insee").dropna(subset=["temps_ign_min"])
        both = both[both["temps_ign_min"] > 0]
        if len(both) > 5:
            rho = both[["temps_ign_min", "t_moy"]].corr("spearman").iloc[0, 1]
            st.markdown(
                f"**Ancien calcul par itinéraires (centres de communes, 3 offres candidates, {legacy['date_calcul']}).** "
                f"Corrélation de Spearman avec le temps moyen Insee : {rho:.2f} ; écart médian "
                f"{(both['temps_ign_min'] - both['t_moy']).median():+.1f} min, 90ᵉ centile "
                f"{(both['temps_ign_min'] - both['t_moy']).quantile(0.9):+.1f} min. Les deux mesures IGN (itinéraire et "
                f"isochrone) y divergeaient pour {int(((pd.to_numeric(lg['classe_iso_min'], errors='coerce').fillna(99) != lg['temps_ign_min'].apply(_classe)) & (lg['temps_ign_min'] > 0)).sum())} "
                f"communes : retenir « la plus favorable des deux » combinait des mesures non comparables. La situation "
                f"actuelle repose désormais sur la base Insee (carreaux, adresses réelles) ; les isochrones IGN ne servent "
                f"qu’au scénario."
            )
            fig = go.Figure(go.Scatter(x=both["t_moy"], y=both["temps_ign_min"], mode="markers",
                                       marker=dict(size=6, color="#1A3D8F", opacity=0.6), customdata=both["nom"],
                                       hovertemplate="%{customdata}<br>Insee %{x:.0f} min · itinéraire IGN %{y:.0f} min<extra></extra>"))
            mx = float(max(both["temps_ign_min"].max(), both["t_moy"].max()))
            fig.add_shape(type="line", x0=0, y0=0, x1=mx, y1=mx, line=dict(color="#9C9A92", dash="dot"))
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=30), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF8",
                              xaxis_title="Insee : temps moyen de la commune (min)", yaxis_title="itinéraire IGN centre à centre (min)", font=dict(size=11))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"{len(carreaux):,} carreaux habités · {len(sit)} communes · population localisée {_fmt(carreaux['pop'].sum())} hab. "
               f"(municipale : {_fmt(sit['population'].sum())}).".replace(",", " "))
