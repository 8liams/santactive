"""Accès routier aux soins de premier recours — simulateur d'implantation (pilotes).

Deux sources combinées, chacune à sa place :

- **Situation actuelle** : base INSEE « localisation et accès de la population
  aux équipements » (millésime 2025) — pour chaque carreau habité de 200 m, la
  durée en voiture (distancier Metric-OSRM) vers le médecin généraliste le plus
  proche (BPE 2025, lieu d'exercice réel). Fichier par département pilote :
  static/geo/carreaux_mg_<dept>.csv.gz (scripts/donnees/calculer_acces_insee.py).
- **Scénario** : isochrones IGN Géoplateforme (10, 15, 20 min, réseau routier
  BD TOPO) calculées à la demande depuis le **point d'implantation** : la mairie
  de la commune choisie (API Géo), à défaut le carreau le plus peuplé. Un
  carreau situé dans l'isochrone S min de la nouvelle offre passe à ≤ S min.

  Pourquoi la mairie et non le centre géométrique : le centroïde d'une commune
  étendue peut tomber en forêt ou en zone agricole ; l'isochrone IGN y est
  raccordée à un chemin et reste minuscule (Plédéliac, Côtes-d'Armor : 0,5 km²
  à 10 min depuis le centroïde contre 73 km² depuis la mairie, audit du
  28 octobre 2026). Une isochrone « non raccordée » (surface à 10 min inférieure
  à ISO_MIN_KM2 ou aucun carreau de la commune contenu à 15 min) est détectée,
  le point de repli est essayé, et à défaut le scénario est déclaré indisponible
  plutôt qu'affiché à zéro.

La **nouvelle offre** est un point géographique hypothétique de consultation de
médecine générale, sans hypothèse sur la capacité du cabinet, le nombre de
médecins ou les rendez-vous. Ce que mesure la simulation : un **gain de
proximité géographique théorique** (habitants dont le temps de trajet vers un
généraliste passerait sous le seuil), pas un gain de prise en charge.

Départements : ceux validés par scripts/donnees/preparer_simulateur.py (index
static/geo/simulateur_index.json, clé « ok ») ; PILOTES_VALIDES conserve les
cinq premiers départements vérifiés à la main.
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
ISO_MIN_KM2 = 2.0      # surface minimale plausible d'une isochrone de 10 min en voiture (Mende : 5,6 km²)
_SOURCE_INSEE = ("Insee, base permanente des équipements 2025, distancier Metric-OSRM, "
                 "© les contributeurs d’OpenStreetMap et du projet OSRM")
_POINT_LIB = {"mairie": "à la mairie", "carreau": "au carreau habité le plus peuplé", "centre": "au centre géométrique"}


# ── Chargement ────────────────────────────────────────────────────────────────

_INDEX_PATH = GEO_DIR / "simulateur_index.json"
_NOMS_DEPTS: dict[str, str] = {}


def _index_simulateur() -> dict:
    """Index produit par scripts/donnees/preparer_simulateur.py (contrôles par département)."""
    try:
        return json.loads(_INDEX_PATH.read_text()).get("departements", {})
    except (OSError, ValueError):
        return {}


def pilotes_disponibles() -> dict[str, str]:
    """Départements activables : validés par le pipeline (clé « ok » de l'index) ou pilotes
    historiques, avec fichiers carreaux + communes présents. Ordre : code départemental."""
    idx = _index_simulateur()
    codes = {d for d, v in idx.items() if v.get("ok")} | set(PILOTES_VALIDES)
    out = {}
    for d in sorted(codes, key=lambda c: (len(c), c)):
        if (GEO_DIR / f"carreaux_mg_{d}.csv.gz").exists() and (GEO_DIR / f"communes_{d}.json").exists():
            out[d] = _NOMS_DEPTS.get(d) or PILOTES_VALIDES.get(d) or d
    return out


def enregistrer_noms(master: pd.DataFrame) -> None:
    """Noms des départements (une fois, depuis le master) pour les libellés des pilotes."""
    if not _NOMS_DEPTS and master is not None:
        _NOMS_DEPTS.update(master.set_index("dept")["Nom du département"].astype(str).to_dict())


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

def aire_km2(geom: dict) -> float:
    """Surface approchée (km²) d'une géométrie GeoJSON en WGS84."""
    from shapely.geometry import shape
    g = shape(geom).buffer(0)
    if g.is_empty:
        return 0.0
    lat = g.centroid.y
    return float(g.area * 111.32 * 111.32 * max(math.cos(math.radians(lat)), 0.2))


def point_implantation(row: pd.Series, carreaux_commune: pd.DataFrame) -> tuple[float, float, str]:
    """Point de la nouvelle offre : mairie (API Géo), à défaut carreau le plus peuplé, à défaut centroïde."""
    lon_m, lat_m = row.get("lon_mairie"), row.get("lat_mairie")
    if pd.notna(lon_m) and pd.notna(lat_m):
        return float(lon_m), float(lat_m), "mairie"
    if len(carreaux_commune):
        d = carreaux_commune.sort_values("pop", ascending=False).iloc[0]
        return float(d["lon"]), float(d["lat"]), "carreau"
    return float(row["lon"]), float(row["lat"]), "centre"


def point_repli(carreaux_commune: pd.DataFrame) -> tuple[float, float, str] | None:
    if carreaux_commune.empty:
        return None
    d = carreaux_commune.sort_values("pop", ascending=False).iloc[0]
    return float(d["lon"]), float(d["lat"]), "carreau"


def isochrone_degeneree(geoms: dict[int, dict], carreaux_commune: pd.DataFrame) -> str | None:
    """Raison pour laquelle le jeu d'isochrones n'est pas exploitable (None s'il l'est) :
    surface à 10 min minuscule (point raccordé à un chemin) ou aucun carreau habité de la
    commune contenu à 15 min alors qu'elle en a."""
    from shapely import contains_xy
    from shapely.geometry import shape

    if 10 in geoms:
        a = aire_km2(geoms[10])
        if a < ISO_MIN_KM2:
            return f"surface de l’isochrone 10 min : {a:.1f} km²".replace(".", ",")
    if 15 in geoms and len(carreaux_commune):
        poly = shape(geoms[15]).buffer(0)
        inside = contains_xy(poly, carreaux_commune["lon"].to_numpy(float), carreaux_commune["lat"].to_numpy(float))
        if not inside.any():
            return "aucun carreau habité de la commune dans l’isochrone 15 min"
    return None


def isochrones_scenario(row: pd.Series, carreaux_commune: pd.DataFrame) -> tuple[dict[int, dict], tuple[float, float, str], str | None]:
    """Isochrones 10/15/20 min depuis le point d'implantation, avec contrôle de raccordement
    et repli. Retourne (isochrones, point utilisé, anomalie restante ou None)."""
    pt = point_implantation(row, carreaux_commune)
    geoms = {m: g for m in SEUILS if (g := _isochrone_live(pt[0], pt[1], m))}
    if not geoms:
        return {}, pt, None
    anomalie = isochrone_degeneree(geoms, carreaux_commune)
    if anomalie and pt[2] != "carreau":
        alt = point_repli(carreaux_commune)
        if alt:
            geoms2 = {m: g for m in SEUILS if (g := _isochrone_live(alt[0], alt[1], m))}
            if geoms2 and not isochrone_degeneree(geoms2, carreaux_commune):
                return geoms2, alt, None
    return geoms, pt, anomalie


def _pct(x: float, decimals: int = 0) -> str:
    """Pourcentage honnête aux bornes : « < 1 % » / « > 99 % » (ou « < 0,1 % » / « > 99,9 % » avec une
    décimale) plutôt que 0 % ou 100 % quand des habitants existent de l'autre côté (Paris : gains non
    nuls avec une couverture affichée à 100 %)."""
    v = x * 100
    r = round(v, decimals)
    if v > 0 and r == 0:
        return "< " + ("0,1" if decimals else "1") + "\u202f%"
    if v < 100 and r == 100:
        return "> " + ("99,9" if decimals else "99") + "\u202f%"
    return f"{v:.{decimals}f}".replace(".", ",") + "\u202f%"


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


def _resolve_dept(data: dict, pilotes: dict[str, str]) -> tuple[str | None, str | None]:
    """Département affiché et, le cas échéant, le message qui explique l'écart avec le territoire
    de référence. Retourne (None, None) lorsqu'un choix doit être proposé (région, France entière,
    département non couvert) : rien n'est sélectionné à la place de l'utilisateur."""
    from .. import territoire as T

    master = data["master"]
    t = T.get()
    demande = str(st.query_params.get("dept_code") or "")
    if not demande and t.kind == "dept":
        demande = t.code
    if demande in pilotes:
        return demande, None
    if demande:
        nom = T.nom_court(T.Territoire("dept", demande), master)
        return None, (f"Simulation <strong>non disponible pour {html.escape(nom)}</strong> ({demande}) : ce département est hors du champ "
                      f"de la base Insee « accès aux équipements » (Guadeloupe, Guyane, Mayotte) ou n’a pas passé les contrôles de préparation. "
                      f"Aucun autre territoire n’est substitué ; choisissez un département couvert ci-dessous (cela change le territoire de travail).")
    return None, None


def _render_choix_departement(data: dict, pilotes: dict[str, str]) -> None:
    """Entrée régionale ou nationale : choisir explicitement le département à simuler."""
    from .. import territoire as T

    master = data["master"]
    t = T.get()
    if t.kind == "region":
        codes = [d for d in T.dept_codes(t, master) if d in pilotes]
        titre = f"Choisir un département de {html.escape(T.nom_court(t, master))}"
        lead = (f"Le simulateur fonctionne à l’échelle d’un département (carreaux Insee de 200 m et isochrones routières). "
                f"{len(codes)} département{'s' if len(codes) != 1 else ''} de la région sur {len(T.dept_codes(t, master))} "
                f"{'sont couverts' if len(codes) != 1 else 'est couvert'} ; le territoire de référence reste la région.")
    else:
        codes = list(pilotes)
        titre = "Choisir le département à simuler"
        lead = (f"Le simulateur fonctionne à l’échelle d’un département ({len(codes)} couverts : métropole, Martinique, La Réunion). "
                f"Choisir un département le définit comme territoire de travail ; vous pouvez aussi le rechercher dans la barre.")
    st.markdown(f'<h4 class="subsection-title" style="margin-top:6px;">{titre}</h4><p class="section-lead" style="margin-top:0;">{lead}</p>',
                unsafe_allow_html=True)
    if not codes:
        st.markdown('<div class="sa-notice">Aucun département de cette région n’est couvert par le simulateur '
                    '(Guadeloupe, Guyane et Mayotte sont hors champ de la base Insee). Aucun autre territoire n’est substitué.</div>',
                    unsafe_allow_html=True)
        return
    rows = master.set_index("dept")
    cards = ""
    for c in codes:
        r = rows.loc[c] if c in rows.index else None
        ctx = ""
        if r is not None:
            part = pd.to_numeric(pd.Series([r.get("acces_mg_part_sup_15")]), errors="coerce").iloc[0]
            apl = pd.to_numeric(pd.Series([r.get("apl_dept")]), errors="coerce").iloc[0]
            ctx = (f"{_pct(float(part), 1)} des habitants à plus de 15 min d’un généraliste" if pd.notna(part) else "")
            ctx += (f" · APL {f'{apl:.1f}'.replace('.', ',')}" if pd.notna(apl) else "")
        href = internal_href("acces", dept_code=c, t=f"d{c}") if t.kind != "region" else internal_href("acces", dept_code=c)
        cards += (f'<a class="usage-card" href="{href}" target="_self"><div class="usage-title">{html.escape(pilotes[c])} ({c})</div>'
                  f'<div class="usage-txt">{ctx}</div><div class="usage-link">Explorer puis simuler →</div></a>')
    st.markdown(f'<div class="usage-grid usage-grid--4">{cards}</div>', unsafe_allow_html=True)


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
            f"{_pct(1 - part_sup, 1)} des habitants sont déjà à moins de {seuil} min en voiture d’un généraliste, "
            f"une implantation ne rapproche donc presque personne au sens de cette mesure. Les difficultés d’accès, réelles, relèvent "
            f"de la capacité et de la demande : APL {_v('apl_dept', '{:.1f}')} (médiane des départements {_m('apl_dept', '{:.1f}')}), "
            f"{_v('med_gen_pour_100k', '{:.0f}')} généralistes pour 100 000 habitants (médiane {_m('med_gen_pour_100k', '{:.0f}')}), "
            f"{_v('pct_plus_65', '{:.1f}')} % de 65 ans et plus. Voir la lecture « capacité » et les leviers du "
            f"<a href=\"{internal_href('dept', dept_code=dept)}\" target=\"_self\">diagnostic</a>.")


@st.cache_data(show_spinner=False)
def charger_zones(dept: str) -> dict | None:
    """Zones continues par classe de temps (union des carreaux, préparées hors ligne)."""
    p = GEO_DIR / f"zones_mg_{dept}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _union_squares(df: pd.DataFrame):
    """Union des carrés de 200 m (approximation WGS84) d'un sous-ensemble de carreaux → géométrie."""
    import shapely
    if df.empty:
        return None
    lat = df["lat"].to_numpy(float); lon = df["lon"].to_numpy(float)
    dlat = 100 / 111_320
    dlon = 100 / (111_320 * np.maximum(np.cos(np.radians(lat)), 0.2))
    boxes = shapely.box(lon - dlon, lat - dlat, lon + dlon, lat + dlat)
    g = shapely.union_all(boxes).buffer(0)
    return g if not g.is_empty else None


def _zones_layer(zones: dict | None, name: str, opacity: float, classes=None) -> folium.GeoJson | None:
    if not zones:
        return None
    feats = [f for f in zones["features"] if classes is None or f["properties"]["classe"] in classes]
    if not feats:
        return None
    return folium.GeoJson({"type": "FeatureCollection", "features": feats}, name=name,
                          style_function=lambda f, o=opacity: {"fillColor": _COULEURS[int(f["properties"]["classe"])],
                                                               "color": _COULEURS[int(f["properties"]["classe"])],
                                                               "weight": 0.4, "fillOpacity": o},
                          tooltip=folium.GeoJsonTooltip(fields=["classe"], aliases=["Aujourd’hui : trajet (classe, min ≤)"]))


def render(data: dict) -> None:
    enregistrer_noms(data["master"])
    pilotes = pilotes_disponibles()
    names = data["master"].set_index("dept")["Nom du département"].to_dict()

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Simuler une implantation")], key_prefix="ign_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">SIMULATEUR</span>'
        '<span class="dot"></span><span class="region">Carreaux INSEE 2025 · isochrones IGN · gain de proximité théorique</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Simuler une implantation <em>de médecine générale</em></h1></div>'
        '</div>', unsafe_allow_html=True)
    if not pilotes:
        st.info("Aucun département préparé (scripts/donnees/preparer_simulateur.py).")
        return

    dept, message = _resolve_dept(data, pilotes)
    if message:
        st.markdown(f'<div class="sa-notice">{message}</div>', unsafe_allow_html=True)
    if dept is None:
        _render_choix_departement(data, pilotes)
        return
    nom_dept = names.get(dept, pilotes.get(dept, dept))
    carreaux = charger_carreaux(dept)
    communes = charger_communes(dept)
    zones = charger_zones(dept)
    sit = situation_communes(carreaux, communes)
    tot = float(carreaux["pop"].sum()) or 1.0
    nb_offre = int(sit["offre"].sum())
    loin = sit[sit["t_moy"] > 15]

    # ── Territoire de travail ────────────────────────────────────────────────
    st.markdown(
        f'<div class="ign-pilote"><div><span class="ign-pilote-lbl">Territoire de travail</span>'
        f'<span class="ign-pilote-nom">{html.escape(nom_dept)} ({dept})</span>'
        f'<span class="ign-pilote-ctx">{len(sit)} communes · {nb_offre} avec au moins un généraliste (BPE 2025) · '
        f'{_fmt(tot)} habitants localisés · {len(pilotes)} départements couverts (changer de territoire dans la barre)</span></div>'
        f'<div class="ign-pilote-links"><a href="{internal_href("dept", dept_code=dept)}" target="_self">Diagnostic {html.escape(nom_dept)} →</a>'
        f'<a href="{internal_href("dept", dept_code=dept)}#communes" target="_self">Communes prioritaires →</a></div></div>',
        unsafe_allow_html=True)

    # ── Étape 1 : explorer le département ; étape 2 : simuler depuis une commune ──
    s1, s2 = st.columns([2.2, 1])
    seuil = s2.radio("Seuil de trajet en voiture", SEUILS, index=1, horizontal=True, key=f"ign_seuil_{dept}",
                     format_func=lambda m: f"{m} min")
    cands = sit.assign(_pot=sit[f"pop_sup_{seuil}"]).sort_values(["_pot", "pop"], ascending=False)
    VUE = "—"
    labels = {VUE: "Vue d’ensemble du département (choisir une commune pour simuler)"}
    for _, r in cands.iterrows():
        pot = r[f"pop_sup_{seuil}"]
        labels[r["nom"]] = (f'{r["nom"]} · {_fmt(r["pop"])} hab. · {r["t_moy"]:.0f} min en moyenne'
                            + (f' · {_fmt(pot)} hab. à plus de {seuil} min' if pot >= 50 else "")
                            + (" · généraliste présent" if r["offre"] else ""))
    options = list(labels)
    # La commune choisie est conservée dans une clé propre (ign_choix_<dept>) : le sélecteur est
    # recréé à chaque changement de seuil (ordre et libellés des options dépendent du seuil) et
    # repart de ce choix au lieu de revenir à la vue d'ensemble.
    key_choix = f"ign_choix_{dept}"
    qp_commune = str(st.query_params.get("commune") or "")
    if not qp_commune:
        # Commune choisie dans la barre (territoire exact) : proposée d'emblée si elle est du département
        from .. import territoire as T
        tx = T.get_exact()
        if tx.kind == "commune" and tx.dept_code == dept:
            qp_commune = tx.commune_nom
    if key_choix not in st.session_state:
        st.session_state[key_choix] = qp_commune if qp_commune in labels else VUE
    if st.session_state[key_choix] not in labels:
        st.session_state[key_choix] = VUE
    key_sim = f"ign_sim_{dept}_{seuil}"

    def _on_sel():
        st.session_state[key_choix] = st.session_state[key_sim]
    choix = s1.selectbox("Simuler une implantation dans la commune", options, index=options.index(st.session_state[key_choix]),
                         format_func=lambda n: labels.get(n, n), key=key_sim, on_change=_on_sel,
                         help="Les communes sont classées par population aujourd’hui au-delà du seuil (plus grand potentiel en premier).")
    zone = st.empty()
    if choix == VUE:
        with zone.container():
            _render_vue_departement(data, dept, nom_dept, carreaux, sit, zones, seuil, tot, loin, key_choix)
        return
    row = cands[cands["nom"] == choix].iloc[0]
    part_sup = float(carreaux.loc[carreaux["duree"] > seuil, "pop"].sum()) / tot
    with zone.container():
        st.markdown(f'<div class="sa-loading">Calcul du scénario pour <strong>{html.escape(nom_dept)}</strong> — '
                    f'isochrones IGN depuis la mairie de {html.escape(choix)}…</div>', unsafe_allow_html=True)
    sim_geoms, point, anomalie = isochrones_scenario(row, carreaux[carreaux["code_insee"] == row["code_insee"]])
    with zone.container():
        _render_resultats(data, dept, nom_dept, carreaux, sit, zones, row, choix, seuil, sim_geoms, part_sup, tot, loin, key_choix,
                          point=point, anomalie=anomalie)


def _carte_base(carreaux: pd.DataFrame, zones: dict | None, sit: pd.DataFrame, *, estompe: bool = False,
                detail: bool = True) -> folium.Map:
    """Fond de carte : zones continues par classe (aujourd'hui), communes équipées, communes éloignées,
    carroyage détaillé (> 10 min) en couche facultative."""
    m = folium.Map(location=[float(carreaux["lat"].mean()), float(carreaux["lon"].mean())], zoom_start=9,
                   tiles=TILE_URL, attr=TILE_ATTR, scrollWheelZoom=False, zoom_snap=0.25)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container{background:#F4F3EE!important;}"
        ".sa-ign-legend{font-family:Marianne,Inter,sans-serif;font-size:11px;background:rgba(255,255,255,.95);"
        "padding:10px 12px;border-radius:4px;border:1px solid #C9C6BA;line-height:1.7;}"
        ".sa-ign-legend b{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B68;margin-bottom:4px;}"
        ".sa-ign-legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:middle;}"
        ".sa-ign-legend i.pt{border-radius:50%;width:10px;height:10px;}"
        ".sa-ign-legend i.pin-mini{width:12px;height:12px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:#1A3D8F;border:2px solid #fff;box-shadow:0 0 0 1px #1A3D8F;}"
        ".sa-pin{position:relative;width:34px;height:48px;}"
        ".sa-pin-head{position:absolute;left:1px;top:0;width:32px;height:32px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);"
        "background:#1A3D8F;border:3px solid #fff;box-shadow:0 2px 6px rgba(10,25,56,.45),0 0 0 1.5px #1A3D8F;color:#fff;font-weight:800;"
        "font-size:20px;line-height:26px;text-align:center;font-family:Marianne,Inter,sans-serif;}"
        ".sa-pin-head{display:flex;align-items:center;justify-content:center;}"
        ".sa-pin-head::after{content:'+';transform:rotate(45deg);}"
        ".sa-pin-lbl{position:absolute;left:50%;top:50px;transform:translateX(-50%);white-space:nowrap;font-family:Marianne,Inter,sans-serif;"
        "font-size:11px;font-weight:700;color:#1A3D8F;background:rgba(255,255,255,.95);border:1.5px solid #1A3D8F;border-radius:6px;padding:2px 8px;}"
        "</style>"))
    lz = _zones_layer(zones, "Aujourd’hui : zones par temps de trajet", 0.18 if estompe else 0.55)
    if lz is not None:
        lz.add_to(m)
    if detail:
        fg = folium.FeatureGroup(name="Carroyage détaillé (> 10 min)", show=False)
        layer = _squares_layer(carreaux[carreaux["duree"] > 10], "carreaux", lambda r: _COULEURS[int(r["classe"])], 0.6)
        if layer is not None:
            layer.add_to(fg)
        fg.add_to(m)
    return m


def _legende(m: folium.Map, seuil: int | None, mode: str | None) -> None:
    """Légende cohérente avec le mode : situation actuelle, avec la nouvelle offre, gain seulement."""
    base = ('<b>Aujourd’hui : trajet en voiture vers un généraliste</b>'
            + "".join(f'<div><i style="background:{_COULEURS[s_]};opacity:.75;"></i>{_LIB_CLASSE[s_]}</div>' for s_ in (10, 15, 20, 30, 99)))
    communes = ('<b style="margin-top:6px;">Communes</b>'
                '<div><i class="pt" style="background:#0A1938;"></i>généraliste présent (BPE 2025)</div>'
                '<div><i class="pt" style="background:#D9772B;"></i>temps moyen &gt; 15 min</div>')
    scen = ""
    if mode and mode != "Situation actuelle":
        scen = ('<b style="margin-top:6px;">Scénario</b>'
                '<div><i class="pin-mini"></i>nouvelle offre simulée (point hypothétique)</div>'
                f'<div><i style="border:2px dashed {_NEUF};background:transparent;"></i>isochrone IGN ≤ {seuil} min</div>')
        if mode == "Avec la nouvelle offre":
            scen += (f'<div><i style="background:{_COULEURS[10]};border:2px solid {_NEUF};"></i>zone dont la classe change : nouvelle couleur, '
                     f'contour marine si elle passe sous {seuil} min</div>')
        else:
            scen += (f'<div><i style="background:{_NEUF};"></i>nouvellement couverts (passent sous {seuil} min)</div>'
                     '<div><i style="background:#1B5E3F;opacity:.6;"></i>rapprochés (déjà sous le seuil, trajet raccourci)</div>')
        communes += f'<div><i class="pt" style="background:#fff;border:3px solid {_NEUF};"></i>commune avec habitants nouvellement couverts</div>'
    legend = f'<div class="sa-ign-legend">{base}{communes}{scen}</div>'
    m.get_root().html.add_child(folium.Element(
        '<div class="leaflet-bottom leaflet-left" style="pointer-events:none;">'
        f'<div class="leaflet-control" style="margin:0 0 24px 12px;">{legend}</div></div>'))


def _marqueur_offre(m: folium.Map, lon: float, lat: float, nom: str, libelle_point: str) -> None:
    """Marqueur de la nouvelle offre : épingle marine, étiquette permanente, distinct des points
    d'offre existante (petits disques) et des contours d'isochrones (pointillés)."""
    folium.Marker([lat, lon], tooltip=f"Nouvelle offre simulée : {html.escape(nom)} ({libelle_point})",
                  z_index_offset=1000,
                  icon=folium.DivIcon(html=(f'<div class="sa-pin"><div class="sa-pin-head"></div><div class="sa-pin-tail"></div>'
                                            f'<div class="sa-pin-lbl">Nouvelle offre · {html.escape(nom)}</div></div>'),
                                      icon_size=(34, 48), icon_anchor=(17, 46))).add_to(m)


def _points_communes(m: folium.Map, sit: pd.DataFrame, gpc: pd.DataFrame | None = None, seuil: int | None = None, faible: bool = False) -> None:
    gain_codes = set(gpc["code_insee"]) if gpc is not None and len(gpc) else set()
    for _, r in sit.iterrows():
        nom = html.escape(str(r["nom"]))
        if r["offre"]:
            folium.CircleMarker([r["lat"], r["lon"]], radius=4, color="#FFFFFF", fill=True, fill_color="#0A1938", fill_opacity=1, weight=1.2,
                                tooltip=f"{nom} · généraliste présent · {r['t_moy']:.0f} min en moyenne").add_to(m)
        elif r["code_insee"] in gain_codes:
            g_ = gpc[gpc["code_insee"] == r["code_insee"]].iloc[0]
            folium.CircleMarker([r["lat"], r["lon"]], radius=7, color=_NEUF, fill=True, fill_color="#FFFFFF", fill_opacity=1, weight=3,
                                tooltip=f"{nom} · +{_fmt(g_['pop_gain'])} hab. sous {seuil} min ({g_['part'] * 100:.0f} % de la commune)").add_to(m)
        elif not faible and r["t_moy"] > 15:
            folium.CircleMarker([r["lat"], r["lon"]], radius=5, color="#FFFFFF", fill=True, fill_color="#D9772B", fill_opacity=0.95, weight=1,
                                tooltip=f"{nom} · {r['t_moy']:.0f} min en moyenne · {_fmt(r['pop'])} hab.").add_to(m)


def _render_situation(dept: str, nom_dept: str, carreaux: pd.DataFrame, sit: pd.DataFrame, tot: float, loin: pd.DataFrame, data: dict) -> None:
    st.markdown('<div class="section-header" style="margin-top:22px;"><div class="section-eyebrow">SITUATION ACTUELLE</div>'
                f'<h2 class="section-title">Où vit-on loin d’un généraliste <em>en {html.escape(nom_dept)} ?</em></h2>'
                '<p class="section-lead">Temps de trajet en voiture depuis chaque carreau habité de 200 m vers le médecin '
                'généraliste le plus proche (lieu d’exercice réel, BPE 2025). Accessibilité géographique : elle ne dit rien '
                'de la capacité des cabinets, des délais de rendez-vous ni des transports en commun.</p></div>', unsafe_allow_html=True)
    c = st.columns(4)
    for col, s_ in zip(c, (10, 15, 20)):
        pop = float(carreaux.loc[carreaux["duree"] <= s_, "pop"].sum())
        col.markdown(_kpi(f"≤ {s_} min", _pct(pop / tot), f"de la population ({_fmt(pop)} hab.)", _COULEURS[s_]), unsafe_allow_html=True)
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


def _render_vue_departement(data, dept, nom_dept, carreaux, sit, zones, seuil, tot, loin, key_sim) -> None:
    """Étape 1 : explorer le département avant de simuler."""
    part_sup = float(carreaux.loc[carreaux["duree"] > seuil, "pop"].sum()) / tot
    st.markdown('<div class="section-header" style="margin-top:14px;"><div class="section-eyebrow">EXPLORER</div>'
                f'<h2 class="section-title">Zones bien et mal desservies <em>en {html.escape(nom_dept)}</em></h2>'
                '<p class="section-lead">Les surfaces colorées montrent le temps de trajet en voiture des habitants vers le généraliste le plus '
                'proche (INSEE 2025, zones construites à partir des carreaux de 200 m). Les secteurs orange et rouge sont ceux où une '
                'implantation pourrait rapprocher des habitants ; choisissez ensuite une commune pour simuler.</p></div>', unsafe_allow_html=True)
    if part_sup < 0.01 and float(carreaux.loc[carreaux["duree"] > seuil, "pop"].sum()) < 1000:
        note = _urbain_note(dept, nom_dept, data["master"], part_sup, seuil)
        if note:
            st.markdown(f'<div class="sa-notice sa-notice--info">{note}</div>', unsafe_allow_html=True)
    m = _carte_base(carreaux, zones, sit)
    _points_communes(m, sit)
    m.fit_bounds([[float(carreaux["lat"].min()), float(carreaux["lon"].min())], [float(carreaux["lat"].max()), float(carreaux["lon"].max())]], padding=(10, 10))
    _legende(m, None, None)
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=640, returned_objects=[], key=f"ign_map_{dept}_vue")
    # Secteurs pouvant bénéficier d'une intervention : communes avec le plus d'habitants au-delà du seuil
    pot = sit[sit[f"pop_sup_{seuil}"] >= 50].sort_values(f"pop_sup_{seuil}", ascending=False).head(8)
    if len(pot):
        st.markdown(f'<h4 class="subsection-title" style="margin-top:14px;">Secteurs où une implantation pourrait rapprocher des habitants (seuil {seuil} min)</h4>', unsafe_allow_html=True)
        cards = "".join(
            f'<a class="usage-card" href="{internal_href("acces", dept_code=dept, commune=str(r["nom"]))}" target="_self">'
            f'<div class="usage-title">{html.escape(str(r["nom"]))}</div>'
            f'<div class="usage-txt">{_fmt(r[f"pop_sup_{seuil}"])} habitants à plus de {seuil} min · {r["t_moy"]:.0f} min en moyenne · {_fmt(r["pop"])} hab.'
            + (" · généraliste présent" if r["offre"] else "") + '</div><div class="usage-link">Simuler ici →</div></a>'
            for _, r in pot.iterrows())
        st.markdown(f'<div class="usage-grid usage-grid--4">{cards}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<p class="sa-couverture">Aucune commune n’a 50 habitants ou plus au-delà de {seuil} min : une implantation n’y changerait pas la proximité mesurée.</p>', unsafe_allow_html=True)
    _render_situation(dept, nom_dept, carreaux, sit, tot, loin, data)


def _render_resultats(data, dept, nom_dept, carreaux, sit, zones, row, choix, seuil, sim_geoms, part_sup, tot, loin, key_sim,
                      *, point: tuple[float, float, str] | None = None, anomalie: str | None = None) -> None:
    """Étape 2 : scénario d'implantation. Ordre de lecture : indicateurs d'impact, synthèse courte,
    carte, tableau des communes bénéficiaires, panneau dépliable (hypothèses, méthode, limites)."""
    master = data["master"]
    com = carreaux
    gain = rapp = pd.DataFrame()
    gpc = pd.DataFrame()
    lon_pt, lat_pt, lib_pt = point if point else (float(row["lon"]), float(row["lat"]), "centre")
    valide = bool(sim_geoms) and not anomalie

    def _retour():
        st.session_state[key_sim] = "—"          # key_sim = clé du choix (ign_choix_<dept>)
        for k in [k for k in st.session_state if str(k).startswith(f"ign_sim_{dept}_")]:
            st.session_state.pop(k, None)
    st.button(f"← Vue d’ensemble de {nom_dept}", key=f"ign_back_{dept}", on_click=_retour)

    if not sim_geoms:
        st.warning("Le service d’isochrones IGN n’a pas répondu (lenteur, erreur ou quota). Aucun scénario n’est affiché ; "
                   "la situation actuelle ci-dessous reste valable.")
        if st.button("Réessayer le calcul", key=f"ign_retry_{dept}"):
            _isochrone_live.clear()
            st.rerun()
    elif anomalie:
        st.markdown(
            f'<div class="sa-notice"><strong>Scénario indisponible pour {html.escape(choix)}</strong> : le point d’implantation n’a pas pu être '
            f'raccordé correctement au réseau routier par le service IGN ({html.escape(anomalie)}), y compris depuis le point de repli. '
            f'Aucun gain n’est affiché plutôt qu’un zéro trompeur. Essayez une commune voisine.</div>', unsafe_allow_html=True)
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
        n_gain = float(gain["pop"].sum()); n_rapp = float(rapp["pop"].sum())
        apres = avant - n_gain

        # 1. Indicateurs clés d'impact
        m1, m2, m3, m4 = st.columns(4)
        m1.markdown(_kpi("Nouvellement couverts", f"+{_fmt(n_gain)}",
                         f"habitants qui passeraient sous {seuil} min, dans {len(gpc)} commune{'s' if len(gpc) != 1 else ''}", _NEUF), unsafe_allow_html=True)
        m2.markdown(_kpi("Rapprochés", f"{_fmt(n_rapp)}", f"habitants déjà sous {seuil} min dont le trajet raccourcirait", "#1B5E3F"), unsafe_allow_html=True)
        m3.markdown(_kpi(f"Au-delà de {seuil} min aujourd’hui", f"{_fmt(avant)}",
                         f"habitants ({_pct(avant / tot, 1)} du département)", "#D9772B"), unsafe_allow_html=True)
        m4.markdown(_kpi("Après le scénario", f"{_fmt(apres)}",
                         f"habitants resteraient au-delà de {seuil} min ({_pct(apres / tot, 1)})", "#D9772B"), unsafe_allow_html=True)

        # 2. Synthèse courte, sans jargon
        if n_gain > 0:
            synth = (f"Une nouvelle offre de médecine générale à <strong>{html.escape(choix)}</strong> permettrait à "
                     f"<strong>{_fmt(n_gain)} habitants supplémentaires</strong> de rejoindre un généraliste en moins de {seuil} minutes en voiture. "
                     f"Les gains concernent {len(gpc)} commune{'s' if len(gpc) != 1 else ''}"
                     + (f", d’abord {html.escape(str(gpc.iloc[0]['nom']))} ({_fmt(gpc.iloc[0]['pop_gain'])} habitants)" if len(gpc) > 1 else "") + ".")
        else:
            synth = (f"Une nouvelle offre à <strong>{html.escape(choix)}</strong> ne placerait <strong>personne de plus</strong> sous {seuil} minutes : "
                     f"les habitants à moins de {seuil} min de {html.escape(choix)} le sont déjà d’un généraliste existant. Ce zéro ne signifie pas "
                     f"qu’une implantation serait sans intérêt : capacité des cabinets et délais de rendez-vous ne sont pas mesurés ici.")
        if n_rapp > 0:
            synth += f" Par ailleurs, {_fmt(n_rapp)} habitants déjà couverts bénéficieraient d’un trajet plus court."
        synth += (f" <span class='sa-dim'>Estimation de proximité théorique (point placé {_POINT_LIB.get(lib_pt, lib_pt)}), "
                  f"pas une garantie de prise en charge.</span>")
        st.markdown(f'<p class="ign-synth">{synth}</p>', unsafe_allow_html=True)
        if part_sup < 0.01 and float(carreaux.loc[carreaux["duree"] > seuil, "pop"].sum()) < 1000:
            note = _urbain_note(dept, nom_dept, master, part_sup, seuil)
            if note:
                st.markdown(f'<div class="sa-notice sa-notice--info">{note}</div>', unsafe_allow_html=True)

    # 3. Carte : situation actuelle / avec la nouvelle offre / gain seulement
    v1, v2 = st.columns([2.2, 1])
    modes = ["Situation actuelle", "Avec la nouvelle offre", "Gain seulement"] if valide else ["Situation actuelle"]
    mode = v1.radio("Affichage de la carte", modes, index=1 if valide else 0, horizontal=True, key=f"ign_mode_{dept}_{int(valide)}")
    cadrage = v2.toggle("Cadrer sur le scénario", value=True, key=f"ign_cadrage_{dept}") if sim_geoms else False
    faible = mode == "Gain seulement"
    m = _carte_base(carreaux, zones, sit, estompe=faible)
    if valide and mode != "Situation actuelle":
        from shapely.geometry import mapping as _mapping
        # Isochrone du seuil affichée ; les deux autres restent disponibles dans le sélecteur de couches
        # (les contours Valhalla sont très découpés : les superposer rend la carte illisible).
        for s_ in (20, 15, 10):
            if s_ not in sim_geoms:
                continue
            fg = folium.FeatureGroup(name=f"Isochrone IGN ≤ {s_} min", show=(s_ == seuil))
            folium.GeoJson({"type": "Feature", "geometry": sim_geoms[s_]},
                           style_function=lambda f, s2=s_: {"fillColor": _NEUF, "color": _NEUF, "weight": 2.4 if s2 == seuil else 1.2,
                                                            "fillOpacity": 0.0, "dashArray": "6 4"},
                           tooltip=f"Isochrone IGN {s_} min depuis la nouvelle offre").add_to(fg)
            fg.add_to(m)
        if mode == "Avec la nouvelle offre":
            change = com[com["classe_neuf"] < com["classe"]]
            for cl in sorted(change["classe_neuf"].unique()):
                g = _union_squares(change[change["classe_neuf"] == cl])
                if g is not None:
                    folium.GeoJson({"type": "Feature", "geometry": _mapping(g)}, name=f"Après : ≤ {int(cl)} min",
                                   style_function=lambda f, c=_COULEURS[int(cl)]: {"fillColor": c, "color": c, "weight": 0.6, "fillOpacity": 0.8},
                                   tooltip=f"Avec la nouvelle offre : ≤ {int(cl)} min").add_to(m)
            g_gain = _union_squares(gain)
            if g_gain is not None:
                folium.GeoJson({"type": "Feature", "geometry": _mapping(g_gain)}, name=f"Passe sous {seuil} min",
                               style_function=lambda f: {"fillColor": _NEUF, "color": _NEUF, "weight": 1.4, "fillOpacity": 0.0},
                               tooltip=f"Passe sous {seuil} min").add_to(m)
        else:
            g_gain = _union_squares(gain)
            if g_gain is not None:
                folium.GeoJson({"type": "Feature", "geometry": _mapping(g_gain)}, name=f"Passe sous {seuil} min",
                               style_function=lambda f: {"fillColor": _NEUF, "color": _NEUF, "weight": 1.2, "fillOpacity": 0.6},
                               tooltip=f"Nouvellement couverts : passent sous {seuil} min").add_to(m)
            g_rapp = _union_squares(rapp)
            if g_rapp is not None:
                folium.GeoJson({"type": "Feature", "geometry": _mapping(g_rapp)}, name="Rapprochés",
                               style_function=lambda f: {"fillColor": "#1B5E3F", "color": "#1B5E3F", "weight": 1.0, "fillOpacity": 0.35},
                               tooltip="Rapprochés : déjà sous le seuil, trajet raccourci").add_to(m)
    _points_communes(m, sit, gpc, seuil, faible)
    _marqueur_offre(m, lon_pt, lat_pt, choix, _POINT_LIB.get(lib_pt, lib_pt))
    if cadrage and sim_geoms:
        from shapely.geometry import shape as _shape
        b = _shape(sim_geoms[max(sim_geoms)]).bounds
        m.fit_bounds([[b[1], b[0]], [b[3], b[2]]], padding=(20, 20))
    else:
        m.fit_bounds([[float(carreaux["lat"].min()), float(carreaux["lon"].min())], [float(carreaux["lat"].max()), float(carreaux["lon"].max())]], padding=(10, 10))
    _legende(m, seuil, mode)
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=580, returned_objects=[], key=f"ign_map_{dept}_{choix}_{seuil}_{mode}_{cadrage}")

    # 4. Tableau des communes bénéficiaires
    if len(gpc):
        st.markdown(f'<h4 class="subsection-title" style="margin-top:10px;">Communes bénéficiaires (seuil {seuil} min)</h4>', unsafe_allow_html=True)
        rows = "".join(
            f'<tr><td class="metric-label">{html.escape(str(r["nom"]))}</td><td data-label="Nouvellement couverts">{_fmt(r["pop_gain"])} hab.</td>'
            f'<td data-label="Part de la commune">{_pct(r["part"])}</td><td data-label="Trajet moyen aujourd’hui">{r["t_avant"]:.0f} min</td>'
            f'<td data-label="Avec la nouvelle offre">≤ {int(r["classe_apres"])} min</td></tr>'
            for _, r in gpc.head(15).iterrows())
        st.markdown('<div class="sa-tbl-scroll"><table class="comparison-table-v2 commune-action-table"><thead><tr>'
                    '<th class="metric-col">Commune</th><th class="metric-col">Habitants nouvellement couverts</th>'
                    '<th class="metric-col">Part de la commune</th><th class="metric-col">Trajet moyen aujourd’hui</th>'
                    '<th class="metric-col">Avec la nouvelle offre</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>'
                    + (f'<p class="sa-couverture">{len(gpc) - 15} autres communes concernées, gains plus faibles.</p>' if len(gpc) > 15 else ""),
                    unsafe_allow_html=True)

    # 5. Hypothèses, méthode, incertitudes et limites (dépliable)
    with st.expander("Hypothèses, méthode de calcul et limites du scénario"):
        st.markdown(
            f"**Nouvelle offre simulée.** Un point hypothétique de consultation de médecine générale, placé {_POINT_LIB.get(lib_pt, lib_pt)} de "
            f"{choix} ({lat_pt:.4f}, {lon_pt:.4f}). Aucune hypothèse sur la capacité du cabinet, le nombre de médecins ni les rendez-vous : "
            f"la simulation mesure seulement qui se trouverait à moins de {seuil} min en voiture de ce point. Le point retenu est la mairie "
            f"(le centre géométrique d’une commune étendue peut tomber hors du réseau routier) ; à défaut le carreau habité le plus peuplé.\n\n"
            "**Situation actuelle.** Carreaux habités de 200 m (Insee 2025, population Filosofi) et durée en voiture vers le généraliste le plus "
            "proche (BPE 2025, lieu d’exercice réel, distancier Metric-OSRM).\n\n"
            "**Scénario.** Isochrones IGN Géoplateforme (BD TOPO, moteur Valhalla, voiture, départ) à 10, 15 et 20 min depuis le point d’implantation. "
            "Un carreau contenu dans l’isochrone S passe à ≤ S min. « Nouvellement couverts » : carreaux au-delà du seuil aujourd’hui et dans "
            "l’isochrone du seuil ; « rapprochés » : déjà sous le seuil, mais dans une isochrone plus serrée que leur temps actuel. Une isochrone "
            "dégénérée (point non raccordé au réseau) est détectée et le scénario déclaré indisponible plutôt qu’affiché à zéro.\n\n"
            "**Incertitudes.** Deux distanciers différents (OSRM pour l’existant, Valhalla pour le scénario) : à la limite d’une isochrone, un carreau "
            "peut basculer d’une classe à une minute près. Les surfaces « après » sont les carreaux Insee contenus dans l’isochrone, pas l’isochrone "
            "elle-même. Population carroyée arrondie ; les habitants des départements voisins ne sont pas comptés.\n\n"
            "**Ce qui n’est pas mesuré.** Capacité et patientèle des cabinets, délais de rendez-vous, transports en commun, offre hors département : "
            "il s’agit d’un gain de proximité théorique, pas d’un gain de prise en charge."
        )
    _render_situation(dept, nom_dept, carreaux, sit, tot, loin, data)


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
