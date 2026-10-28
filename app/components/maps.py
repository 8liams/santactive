"""Composants cartographiques modernes (Folium / Leaflet)."""

from __future__ import annotations

import requests
import folium
import pandas as pd
import streamlit as st
from branca.colormap import LinearColormap, StepColormap
from streamlit_folium import st_folium

from ..config import APL_LABEL_COURT, PALETTE

# ── Fond de carte : sobre et neutre, pour ne pas concurrencer nos couleurs ──
def _tile_config() -> tuple[str, str]:
    """Fond de carte : clé CARTO via secrets/env, sinon fond libre neutre.

    Ordre : SANTACTIVE_TILE_URL (gabarit complet) → CARTO Positron si
    CARTO_API_KEY est renseignée → fond gris clair Esri « World Light Gray »
    (libre d'usage avec attribution, sans clé) → IGN Plan v2 ou OSM si
    SANTACTIVE_FOND_CARTE vaut « ign » ou « osm ». Jamais de clé dans le code
    ni dans les logs.
    """
    import os

    def _secret(name: str):
        val = os.environ.get(name)
        if val:
            return val
        try:
            return st.secrets.get(name)
        except Exception:
            return None

    custom = _secret("SANTACTIVE_TILE_URL")
    if custom:
        return str(custom), _secret("SANTACTIVE_TILE_ATTR") or "© Fournisseur du fond de carte"
    key = _secret("CARTO_API_KEY")
    if key:
        return (
            f"https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}{{r}}.png?api_key={key}",
            "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> © <a href='https://carto.com/'>CARTO</a>",
        )
    fond = (_secret("SANTACTIVE_FOND_CARTE") or "gris").lower()
    if fond == "osm":
        return ("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>")
    if fond == "ign":
        return (
            "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM"
            "&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",
            "© <a href='https://www.ign.fr/'>IGN</a> · Géoplateforme (Plan IGN v2)",
        )
    return (
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        "Fond : Esri, HERE, Garmin, © OpenStreetMap contributors",
    )


TILE_URL, TILE_ATTR = _tile_config()

BORDER_COLOR = "#FFFFFF"
BORDER_WIDTH = 0.8
HOVER_COLOR  = "#0A1938"

# Dégradés par type d'indicateur
COLORMAPS: dict[str, list[str]] = {
    "score": ["#A51C30", "#D4663B", "#E5B04A", "#A3C282", "#1B5E3F"],
    # Prix : ambre → orange → bordeaux — pas de blanc pour que les valeurs basses restent lisibles
    "prix":  ["#FEF3C7", "#F59E0B", "#D97706", "#B45309", "#7C2D12"],
    "temps": ["#DCFCE7", "#86EFAC", "#F4C430", "#D4663B", "#A51C30"],
    "pros":  ["#A51C30", "#E5B04A", "#A3C282", "#1B5E3F"],
    "age":   ["#E8EDF8", "#C5D4EE", "#5A85C3", "#1A3D8F"],
}


def quantile_bins(values, n_classes: int) -> list[float]:
    """Bornes de classes de quantiles (n_classes couleurs → n_classes + 1 bornes), strictement croissantes."""
    import numpy as np
    arr = np.asarray([float(v) for v in values if pd.notna(v)], dtype=float)
    if arr.size == 0:
        return [0.0, 1.0]
    qs = np.quantile(arr, np.linspace(0, 1, n_classes + 1))
    out = [float(qs[0])]
    for q in qs[1:]:
        q = float(q)
        out.append(q if q > out[-1] else out[-1] + 1e-9)
    return out


def national_legend_classes(master: pd.DataFrame, metric: str, colormap_name: str, reverse: bool = False,
                            bins: list[float] | None = None) -> list[tuple[float, float, str]]:
    """Classes (borne basse, borne haute, couleur) identiques à celles de la carte nationale pour un indicateur."""
    colors = COLORMAPS[colormap_name]
    if reverse:
        colors = list(reversed(colors))
    if bins:
        bins = [float(b) for b in bins]
        return [(bins[i], bins[i + 1], colors[i]) for i in range(len(bins) - 1)]
    vals = pd.to_numeric(master[metric], errors="coerce").dropna().tolist() if metric in master.columns else []
    bins = quantile_bins(vals, len(colors))
    return [(bins[i], bins[i + 1], colors[i]) for i in range(len(colors))]


def decimales_legende(bornes: list[float], minimum: int = 0, maximum: int = 2) -> int:
    """Nombre de décimales nécessaire pour que deux bornes consécutives restent distinctes une fois arrondies."""
    for d in range(minimum, maximum + 1):
        arr = [round(b, d) for b in bornes]
        if all(arr[i] < arr[i + 1] for i in range(len(arr) - 1)):
            return d
    return maximum


def _tooltip_style() -> str:
    """CSS inline pour les tooltips Leaflet — look Sant'active."""
    return """
<style>
.leaflet-tooltip.sa-tooltip {
    background: #0A1938;
    color: white;
    border: none;
    border-radius: 3px;
    padding: 10px 14px;
    font-family: 'Marianne', 'Inter', sans-serif;
    font-size: 12px;
    line-height: 1.5;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
}
.leaflet-tooltip.sa-tooltip::before { display: none; }
.leaflet-container {
    background: #FAFAF8 !important;
    font-family: 'Marianne', sans-serif !important;
}
.leaflet-control-attribution {
    font-size: 10px !important;
    background: rgba(255,255,255,0.75) !important;
    color: #6B6B68 !important;
}
.leaflet-control-zoom a {
    background: white !important;
    color: #0A0A0A !important;
    border: 1px solid #C9C6BA !important;
    border-radius: 3px !important;
}
.leaflet-control-zoom a:hover { background: #F3F2EC !important; }
</style>
"""


# ──────────────────────────────────────────────────────────────────────────────
# CARTE NATIONALE (100 départements analysés, Mayotte exclue)
# ──────────────────────────────────────────────────────────────────────────────

def render_national_choropleth(
    master: pd.DataFrame,
    geojson: dict,
    metric: str = "score_global",
    colormap_name: str = "score",
    reverse: bool = False,
    height: int = 560,
    key: str = "national_map",
    bounds: list | None = None,
    highlight_codes: set | None = None,
    bins: list[float] | None = None,
) -> dict | None:
    """Carte choroplèthe nationale avec tooltip adaptatif à l'indicateur.

    ``bins`` : bornes de classes fixes (interprétables) ; sinon classes de quantiles pour les
    indicateurs autres que le score, échelle linéaire pour le score."""
    st.markdown(_tooltip_style(), unsafe_allow_html=True)

    if not geojson or not geojson.get("features") or master.empty:
        st.warning("Carte indisponible.")
        return None

    data_map = master.set_index("dept")[metric].to_dict()
    clean_values = [v for v in data_map.values() if pd.notna(v)]
    if not clean_values:
        st.info(f"Aucune valeur disponible pour l'indicateur sélectionné.")
        return None

    vmin, vmax = min(clean_values), max(clean_values)
    if vmin == vmax:
        vmax = vmin + 0.01

    colors = COLORMAPS[colormap_name]
    if reverse:
        colors = list(reversed(colors))
    if bins:
        bins = [float(b) for b in bins]
        cmap = StepColormap(colors=colors[:len(bins) - 1], index=bins, vmin=bins[0], vmax=bins[-1])
    elif metric == "score_global":
        cmap = LinearColormap(colors=colors, vmin=vmin, vmax=vmax)
    else:
        # Classes de quantiles : chaque couleur couvre le même nombre de départements, les valeurs
        # extrêmes (Paris pour l'immobilier) n'écrasent plus l'échelle ; la légende reprend ces bornes.
        bins = quantile_bins(clean_values, len(colors))
        cmap = StepColormap(colors=colors, index=bins, vmin=bins[0], vmax=bins[-1])

    # Label et format du tooltip selon l'indicateur sélectionné
    _metric_meta: dict[str, tuple[str, str]] = {
        "score_global":         ("Score Sant’active",        "{:.1f}/100"),
        "apl_dept":      (APL_LABEL_COURT,       "{:.1f}\u202f/hab."),
        "temps_acces_median":   ("Temps d'accès",       "{:.1f}\u202fmin"),
        "med_gen_pour_100k":    ("Médecins / 100k",     "{:.0f}"),
        "structures_pour_100k": ("Structures / 100k",   "{:.1f}"),
        "prix_m2_moyen":        ("Prix médian /m²",     "{:,.0f}\u202f€"),
        "acces_mg_part_sup_10_pct": ("Habitants à plus de 10 min d’un généraliste", "{:.1f}\u202f%"),
        "pct_plus_65":          ("Part des 65+",        "{:.1f}\u202f%"),
        "pct_moins_25":         ("Part des <25",        "{:.1f}\u202f%"),
    }
    main_label, main_fmt = _metric_meta.get(metric, (metric, "{}"))

    # Choroplèthe sans fond de carte : seuls les départements et leurs couleurs
    # comptent à cette échelle (lecture institutionnelle, aucune route ni toponyme).
    m = folium.Map(
        location=[46.5, 2.4],
        zoom_start=6,
        tiles=TILE_URL,          # même fond que le simulateur (style neutre) ; les départements restent la seule information
        attr=TILE_ATTR,
        zoom_control=True,
        scrollWheelZoom=False,   # la molette ne doit pas capturer le défilement de la page
        min_zoom=5,
        max_zoom=10,
        zoom_snap=0.25,          # zooms fractionnaires : la France remplit le cadre
        # Restreint le pan/zoom à l'emprise de la France métropolitaine
        max_bounds=True,
        min_lat=40.5,
        max_lat=52.0,
        min_lon=-6.5,
        max_lon=11.0,
    )
    if bounds:   # emprise d'une région : cadrage sur ses départements (sinon France métropolitaine)
        # Sans maxBounds : avec cette borne, Leaflet échouait (« Invalid LatLng ») au
        # cadrage dans l'iframe encore sans hauteur, et la carte restait invisible.
        for k in ("max_bounds", "maxBounds", "min_lat", "max_lat", "min_lon", "max_lon"):
            m.options.pop(k, None)
        m.options["min_zoom"] = 4
        m.fit_bounds(bounds, padding=(16, 16))
    else:
        m.fit_bounds([[41.3, -5.2], [51.1, 9.6]], padding=(8, 8))

    # Enrichit les propriétés GeoJSON — valeur principale + contexte.
    # Copie superficielle (géométries partagées) : le deepcopy coûtait 0,02-0,4 s.
    rows_by_code = master.set_index("dept").to_dict("index")
    geojson_enriched = {
        **geojson,
        "features": [{**f, "properties": dict(f["properties"])} for f in geojson["features"]],
    }
    for feat in geojson_enriched["features"]:
        code = feat["properties"]["code"]
        rv = rows_by_code.get(code)
        if rv is not None:
            feat["properties"]["dept_name"]  = str(rv.get("Nom du département", "N/D"))
            feat["properties"]["region_name"] = str(rv.get("Nom de la région", "N/D"))
            feat["properties"]["zone"]        = str(rv.get("zone_short", "N/D"))
            sg = rv.get("score_global")
            feat["properties"]["score_global_display"] = (
                f"{sg:.1f}/100" if pd.notna(sg) else "N/D"
            )
            main_val = rv.get(metric)
            if pd.notna(main_val):
                try:
                    feat["properties"]["main_display"] = (
                        main_fmt.format(main_val).replace(",", "\u202f")
                    )
                except Exception:
                    feat["properties"]["main_display"] = str(main_val)
            else:
                feat["properties"]["main_display"] = "N/D"
        else:
            feat["properties"].update(
                dept_name="N/D", region_name="N/D", zone="N/D",
                score_global_display="N/D", main_display="N/D",
            )

    hl = {str(c).zfill(2) for c in (highlight_codes or set())}

    def _style(feature: dict) -> dict:
        code = feature["properties"]["code"]
        val = data_map.get(code)
        dans_hl = code in hl
        # Territoire de référence : contour marqué, le reste de la France estompé
        if val is None or pd.isna(val):
            return {"fillColor": "#E8E6DD", "color": "#0A1938" if dans_hl else BORDER_COLOR,
                    "weight": 2.2 if dans_hl else 0.6, "fillOpacity": 0.35 if not hl or dans_hl else 0.15}
        return {"fillColor": cmap(val), "color": "#0A1938" if dans_hl else BORDER_COLOR,
                "weight": 2.2 if dans_hl else BORDER_WIDTH, "fillOpacity": 0.86 if not hl or dans_hl else 0.42}

    def _highlight(feature: dict) -> dict:
        return {"fillColor": HOVER_COLOR, "color": HOVER_COLOR,
                "weight": 2, "fillOpacity": 0.15}

    tooltip = folium.GeoJsonTooltip(
        fields=["dept_name", "main_display",
                "score_global_display", "zone", "region_name", "code"],
        aliases=["Département", main_label,
                 "Score Sant’active", "Zone", "Région", "Code"],
        localize=True,
        sticky=False,
        labels=True,
        class_name="sa-tooltip",
    )

    folium.GeoJson(
        geojson_enriched,
        style_function=_style,
        highlight_function=_highlight,
        tooltip=tooltip,
        name="departements",
    ).add_to(m)

    m.get_root().header.add_child(
        folium.Element(
            "<style>"
            ".leaflet-control-attribution{display:none!important;}"
            ".leaflet-container{background:#F4F3EE!important;}"
            "</style>"
        )
    )

    event = st_folium(
        m,
        use_container_width=True,
        height=height,
        returned_objects=["last_active_drawing", "last_object_clicked"],
        key=key,
    )
    return event


# ──────────────────────────────────────────────────────────────────────────────
# CARTOUCHES DOM-TOM
# ──────────────────────────────────────────────────────────────────────────────

DOM_CONFIG = {
    "971": {"nom": "Guadeloupe", "lat": 16.17,  "lon": -61.45, "zoom": 8},
    "972": {"nom": "Martinique", "lat": 14.65,  "lon": -61.00, "zoom": 9},
    "973": {"nom": "Guyane",     "lat":  4.00,  "lon": -53.00, "zoom": 5},
    "974": {"nom": "La Réunion", "lat": -21.12, "lon":  55.53, "zoom": 9},
    "976": {"nom": "Mayotte",    "lat": -12.78, "lon":  45.23, "zoom": 9},
}


@st.cache_data(show_spinner=False)
def _contours_dom() -> dict:
    """Contours simplifiés des DROM (static/geo/contours_dom.json, pré-calculés)."""
    import json
    from pathlib import Path

    p = Path("static/geo/contours_dom.json")
    if not p.exists():
        return {}
    try:
        fc = json.loads(p.read_text())
    except Exception:
        return {}
    return {f["properties"]["code"]: f["geometry"] for f in fc.get("features", [])}


def _outline_svg(dept_code: str, fill: str, w: int = 120, h: int = 72) -> str:
    """Silhouette SVG du département, cadrée dans w×h (projection équirectangulaire locale)."""
    import math

    geom = _contours_dom().get(str(dept_code))
    if not geom:
        return ""
    polys = geom.get("coordinates") or []
    if geom.get("type") == "Polygon":
        polys = [polys]
    rings = [poly[0] for poly in polys if poly]          # anneaux extérieurs
    pts = [p for ring in rings for p in ring]
    if not pts:
        return ""
    lat0 = sum(p[1] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))
    xs = [p[0] * k for p in pts]; ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny) or 1.0
    scale = min(w, h) * 0.94 / span
    ox = (w - (maxx - minx) * scale) / 2; oy = (h - (maxy - miny) * scale) / 2
    paths = []
    for ring in rings:
        if len(ring) < 4:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{(p[0] * k - minx) * scale + ox:.1f},{h - ((p[1] - miny) * scale + oy):.1f}"
                     for i, p in enumerate(ring))
        paths.append(d + " Z")
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true">'
            f'<path d="{" ".join(paths)}" fill="{fill}" fill-opacity="0.85" stroke="#fff" stroke-width="0.8"/></svg>')


def render_dom_cartouches(master: pd.DataFrame, only: set | None = None, **_ignored) -> None:
    """Cartouches homogènes des cinq DROM : nom, score ou absence de score,
    catégorie, population, silhouette du territoire, lien vers la fiche.
    `only` : ne rendre que ces codes (territoire ultramarin de référence)."""
    import html as _html

    from .nav import internal_href

    cards = []
    for code, cfg in DOM_CONFIG.items():
        if only is not None and code not in only:
            continue
        row = master[master["dept"].astype(str) == code]
        r = row.iloc[0] if not row.empty else None
        zone = str(r.get("zone_short", "")) if r is not None else ""
        score = r.get("score_global") if r is not None else None
        pop = r.get("population_num") if r is not None else None
        zone_color = {"Critique": "#A51C30", "Intermédiaire": "#E8A838", "Favorable": "#1B5E3F"}.get(zone, "#9C9A92")
        has_score = r is not None and pd.notna(score)
        if has_score:
            rang = r.get("rang_national")
            score_html = (f'<div class="dom-card-score">{float(score):.0f}<small>/100'
                          + (f" · {int(rang)}ᵉ" if pd.notna(rang) else "") + '</small></div>'
                          f'<div class="dom-card-zone"><i style="background:{zone_color};"></i>Zone {_html.escape(zone.lower())}</div>')
        else:
            score_html = ('<div class="dom-card-score nd">Hors score Sant’active</div>'
                          '<div class="dom-card-zone"><i style="background:#9C9A92;"></i>Données partielles</div>')
        pop_html = (f'<div class="dom-card-pop">{int(pop):,} hab.</div>'.replace(",", "\u202f")
                    if pop is not None and pd.notna(pop) else "")
        svg = _outline_svg(code, zone_color if has_score else "#C9C6BA")
        cards.append(
            f'<a class="dom-card" href="{internal_href("dept", dept_code=code)}" target="_self">'
            f'<div class="dom-card-top"><span class="dom-card-name">{_html.escape(cfg["nom"])}</span>'
            f'<span class="dom-card-code">{code}</span></div>'
            f'<div class="dom-card-svg">{svg}</div>'
            f'{score_html}{pop_html}'
            f'<span class="dom-card-link">Voir la fiche →</span></a>'
        )
    st.markdown(f'<div class="dom-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


DEPT_CENTER = {
    "01":(46.10,5.35,9),"02":(49.55,3.62,9),"03":(46.35,3.30,9),
    "04":(44.10,6.23,9),"05":(44.66,6.35,9),"06":(43.93,7.12,9),
    "07":(44.75,4.37,9),"08":(49.67,4.70,9),"09":(42.93,1.60,9),
    "10":(48.30,4.08,9),"11":(43.18,2.35,9),"12":(44.35,2.57,9),
    "13":(43.50,5.45,9),"14":(49.10,0.25,9),"15":(45.05,2.63,9),
    "16":(45.70,0.16,9),"17":(45.75,-0.67,9),"18":(47.08,2.40,9),
    "19":(45.35,1.88,9),"21":(47.42,4.83,9),"22":(48.45,-2.87,9),
    "23":(46.10,2.00,9),"24":(45.15,0.72,9),"25":(47.23,6.35,9),
    "26":(44.73,5.25,9),"27":(49.10,1.15,9),"28":(48.28,1.37,9),
    "29":(48.25,-4.03,9),"2A":(41.86,9.02,9),"2B":(42.40,9.35,9),
    "30":(44.02,4.28,9),"31":(43.60,1.44,9),"32":(43.63,0.58,9),
    "33":(44.84,-0.57,9),"34":(43.60,3.88,9),"35":(48.12,-1.68,9),
    "36":(46.82,1.57,9),"37":(47.38,0.68,9),"38":(45.25,5.63,9),
    "39":(46.67,5.55,9),"40":(43.90,-0.78,9),"41":(47.58,1.33,9),
    "42":(45.75,4.12,9),"43":(45.08,3.88,9),"44":(47.38,-1.57,9),
    "45":(47.90,2.15,9),"46":(44.62,1.67,9),"47":(44.35,0.47,9),
    "48":(44.52,3.50,9),"49":(47.47,-0.55,9),"50":(49.12,-1.27,9),
    "51":(49.05,4.37,9),"52":(48.12,5.13,9),"53":(48.07,-0.77,9),
    "54":(48.68,6.18,9),"55":(49.17,5.38,9),"56":(47.85,-2.90,9),
    "57":(49.12,6.55,9),"58":(47.08,3.65,9),"59":(50.52,3.08,9),
    "60":(49.40,2.45,9),"61":(48.55,0.07,9),"62":(50.52,2.63,9),
    "63":(45.77,3.08,9),"64":(43.30,-0.77,9),"65":(43.10,0.18,9),
    "66":(42.70,2.57,9),"67":(48.58,7.75,9),"68":(47.85,7.35,9),
    "69":(45.75,4.85,9),"70":(47.63,6.15,9),"71":(46.78,4.62,9),
    "72":(47.98,0.20,9),"73":(45.57,6.57,9),"74":(46.02,6.42,9),
    "75":(48.86,2.35,12),"76":(49.67,1.10,9),"77":(48.73,2.97,9),
    "78":(48.85,1.85,9),"79":(46.65,-0.42,9),"80":(49.88,2.30,9),
    "81":(43.92,2.15,9),"82":(44.02,1.35,9),"83":(43.45,6.27,9),
    "84":(44.05,5.05,9),"85":(46.67,-1.43,9),"86":(46.58,0.33,9),
    "87":(45.83,1.27,9),"88":(48.18,6.47,9),"89":(47.80,3.57,9),
    "90":(47.63,6.87,10),"91":(48.60,2.23,10),"92":(48.85,2.22,11),
    "93":(48.92,2.47,11),"94":(48.78,2.47,11),"95":(49.05,2.12,10),
    "971":(16.17,-61.45,10),"972":(14.65,-61.00,10),
    "973":(4.00,-53.00,8),"974":(-21.12,55.53,10),
    "976":(-12.78,45.23,11),
}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_communes_population(dept_code: str) -> dict[str, float]:
    """Population communale INSEE via geo.api.gouv.fr (code INSEE → habitants)."""
    url = (
        f"https://geo.api.gouv.fr/departements/{dept_code}/communes"
        "?fields=code,population&format=json"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return {}

    pop_map: dict[str, float] = {}
    for row in rows:
        code = row.get("code")
        pop = row.get("population")
        if not code or pop is None:
            continue
        try:
            pop_map[str(code).zfill(5)] = float(pop)
        except (TypeError, ValueError):
            continue
    return pop_map


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_dept_outline(dept_code: str) -> dict | None:
    """Contour d'un département (geo.api.gouv.fr), en FeatureCollection."""
    url = f"https://geo.api.gouv.fr/departements/{dept_code}?geometry=contour&format=geojson"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        feat = resp.json()
    except Exception:
        return None
    if feat.get("type") == "FeatureCollection":
        return feat
    if feat.get("type") == "Feature":
        return {"type": "FeatureCollection", "features": [feat]}
    return None


def _round_coords(obj, nd: int = 4):
    """Arrondit les coordonnées (4 décimales ≈ 10 m) : HTML Folium ~40 % plus léger."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(v), nd) for v in obj]
        return [_round_coords(x, nd) for x in obj]
    return obj


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_communes_geojson(dept_code: str) -> dict | None:
    """Récupère le GeoJSON communal depuis geo.api.gouv.fr (coordonnées arrondies)."""
    url = (
        f"https://geo.api.gouv.fr/departements/{dept_code}/communes"
        "?fields=code,nom,centre,contour,population&format=geojson&geometry=contour"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        gj = resp.json()
    except Exception:
        return None
    for f in gj.get("features", []):
        g = f.get("geometry") or {}
        if "coordinates" in g:
            g["coordinates"] = _round_coords(g["coordinates"])
    return gj


def render_commune_choropleth(
    dept_code: str,
    data_by_commune: pd.DataFrame,
    value_col: str,
    metric_label: str,
    unit: str = "",
    colormap_name: str = "prix",
    height: int = 540,
    etabs_overlay=None,
    key: str = "commune_map",
    *,
    discrete: bool = False,
    color_col: str = "color_hex",
    tooltip_fields: list[str] | None = None,
    tooltip_aliases: list[str] | None = None,
    legend_items: list[tuple[str, str]] | None = None,
):
    """Carte communale — couleurs pré-calculées pour éviter les bugs branca."""
    st.markdown(_tooltip_style(), unsafe_allow_html=True)

    geojson = _fetch_communes_geojson(dept_code)
    if geojson is None:
        st.warning(f"Découpage communal indisponible (département {dept_code}).")
        return None

    if "code_commune" not in data_by_commune.columns:
        st.warning("Données communales incomplètes (code INSEE manquant).")
        return None

    data_by_commune = data_by_commune.copy()
    data_by_commune["code_commune"] = (
        data_by_commune["code_commune"].astype(str).str.zfill(5)
    )
    val_map = (
        data_by_commune.dropna(subset=[value_col])
        .set_index("code_commune")[value_col]
        .to_dict()
    )

    extra_cols = [
        c for c in data_by_commune.columns
        if c not in {"code_commune", value_col}
    ]
    props_by_code: dict[str, dict] = {}
    for _, row in data_by_commune.dropna(subset=["code_commune"]).iterrows():
        code = str(row["code_commune"]).zfill(5)
        props_by_code[code] = {
            col: row[col] for col in extra_cols if col in row.index and pd.notna(row[col])
        }

    total_geo = len(geojson["features"])
    total_matched = sum(
        1 for f in geojson["features"]
        if f["properties"]["code"] in val_map
    )

    if total_matched == 0:
        st.warning(
            f"Aucune commune du département {dept_code} matchée "
            f"({total_geo} dans le GeoJSON). Vérifiez les codes INSEE."
        )
        return None

    clean_values = [float(v) for v in val_map.values() if v is not None]
    if not clean_values:
        st.info("Aucune valeur disponible pour cet indicateur.")
        return None

    code_to_color: dict[str, str] = {}
    cmap = None

    if discrete:
        color_map = (
            data_by_commune.dropna(subset=["code_commune"])
            .set_index("code_commune")[color_col]
            .to_dict()
        )
        for code, color in color_map.items():
            code_to_color[str(code).zfill(5)] = str(color)
    else:
        vmin, vmax = min(clean_values), max(clean_values)
        if vmin >= vmax:
            vmax = vmin + 1.0

        colors = COLORMAPS.get(colormap_name, COLORMAPS["prix"])
        cmap = LinearColormap(
            colors=colors,
            vmin=vmin,
            vmax=vmax,
            caption=f"{metric_label} ({unit})" if unit else metric_label,
        )

        for feat in geojson["features"]:
            code = feat["properties"]["code"]
            val = val_map.get(code)
            if val is not None:
                try:
                    code_to_color[code] = cmap(float(val))
                except Exception:
                    code_to_color[code] = "#E8E6DD"

    # Enrichit props pour le tooltip (copie superficielle, géométries partagées)
    geojson_enriched = {
        **geojson,
        "features": [{**f, "properties": dict(f["properties"])} for f in geojson["features"]],
    }
    for feat in geojson_enriched["features"]:
        code = feat["properties"]["code"]
        val = val_map.get(code)
        extras = props_by_code.get(code, {})
        for prop_key, prop_val in extras.items():
            feat["properties"][prop_key] = prop_val
        if val is not None and not pd.isna(val):
            feat["properties"]["val_display"] = (
                f"{float(val):,.0f}\u202f{unit}".replace(",", "\u202f")
                if unit else f"{float(val):,.1f}".replace(",", "\u202f")
            )
            feat["properties"]["has_data"] = "oui"
        else:
            feat["properties"]["val_display"] = "N/D"
            feat["properties"]["has_data"] = "non"

    # Centrage fiable via lookup fixe
    dept_norm = str(dept_code).zfill(2)
    if dept_norm in DEPT_CENTER:
        clat, clon, czoom = DEPT_CENTER[dept_norm]
    else:
        clat, clon, czoom = 46.6, 2.5, 8

    center = [clat, clon]
    zoom   = czoom

    m = folium.Map(
        location=[clat, clon],
        zoom_start=czoom,
        tiles=TILE_URL,
        attr=TILE_ATTR,
        zoom_control=True,
        scrollWheelZoom=True,
    )

    def _style(feature: dict) -> dict:
        code = feature["properties"]["code"]
        color = code_to_color.get(code)
        if color is None:
            return {"fillColor": "#E8E6DD", "color": "#FFFFFF",
                    "weight": 0.5, "fillOpacity": 0.3}
        return {"fillColor": color, "color": "#FFFFFF",
                "weight": 0.6, "fillOpacity": 0.85}

    def _highlight(feature: dict) -> dict:
        return {"fillColor": "#0A1938", "color": "#0A1938",
                "weight": 1.5, "fillOpacity": 0.2}

    if tooltip_fields and tooltip_aliases:
        t_fields = tooltip_fields
        t_aliases = tooltip_aliases
    else:
        t_fields = ["nom", "code", "val_display"]
        t_aliases = ["Commune", "Code INSEE", metric_label]

    # Folium vérifie les champs tooltip sur la 1ère feature uniquement : tous
    # les polygones doivent exposer les mêmes clés (sinon AssertionError).
    for feat in geojson_enriched["features"]:
        for field in t_fields:
            feat["properties"].setdefault(field, "N/D")

    tooltip = folium.GeoJsonTooltip(
        fields=t_fields,
        aliases=t_aliases,
        localize=True,
        sticky=False,
        class_name="sa-tooltip",
    )

    folium.GeoJson(
        geojson_enriched,
        style_function=_style,
        highlight_function=_highlight,
        tooltip=tooltip,
    ).add_to(m)

    # Légende
    if cmap is not None:
        cmap.add_to(m)
    elif legend_items:
        legend_html = (
            '<div style="font-family:Marianne,sans-serif;font-size:11px;'
            'background:white;padding:10px 12px;border-radius:3px;'
            'border:1px solid #C9C6BA;line-height:1.6;">'
            f'<div style="font-weight:600;margin-bottom:6px;color:#0A1938;">'
            f'{metric_label}</div>'
        )
        for label, color in legend_items:
            legend_html += (
                f'<div><span style="display:inline-block;width:12px;height:12px;'
                f'background:{color};margin-right:6px;border-radius:2px;'
                f'vertical-align:middle;"></span>{label}</div>'
            )
        legend_html += "</div>"
        m.get_root().html.add_child(
            folium.Element(
                '<div class="leaflet-bottom leaflet-right" style="pointer-events:none;">'
                '<div class="leaflet-control" style="margin-bottom:28px;margin-right:12px;">'
                f"{legend_html}</div></div>"
            )
        )

    # Overlay établissements
    if etabs_overlay is not None and not etabs_overlay.empty:
        for _, e in etabs_overlay.iterrows():
            if pd.notna(e.get("lat")) and pd.notna(e.get("lon")):
                folium.CircleMarker(
                    location=[float(e["lat"]), float(e["lon"])],
                    radius=5,
                    color="#A51C30",
                    fill=True,
                    fill_color="#FFFFFF",
                    fill_opacity=1.0,
                    weight=2,
                    tooltip=folium.Tooltip(
                        f'<span style="font-family:sans-serif;font-size:11px;">'
                        f'{e.get("nom", "")}</span>',
                    ),
                ).add_to(m)

    st.caption(f"{total_matched} communes sur {total_geo} affichées avec données.")

    event = st_folium(
        m,
        center=center,
        zoom=zoom,
        use_container_width=True,
        height=height,
        returned_objects=["last_object_clicked"],
        key=key,
    )
    return event
