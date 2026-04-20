"""Composants cartographiques modernes (Folium / Leaflet)."""

from __future__ import annotations

import requests
import pandas as pd
import folium
import streamlit as st
from branca.colormap import LinearColormap
from streamlit_folium import st_folium

from ..config import PALETTE

# ── Tuiles CartoDB Positron : fond gris-clair minimal institutionnel ──────────
TILE_URL  = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
TILE_ATTR = (
    "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> "
    "© <a href='https://carto.com/'>CARTO</a>"
)

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
# CARTE NATIONALE (101 départements)
# ──────────────────────────────────────────────────────────────────────────────

def render_national_choropleth(
    master: pd.DataFrame,
    geojson: dict,
    metric: str = "score_global",
    colormap_name: str = "score",
    reverse: bool = False,
    height: int = 560,
    key: str = "national_map",
) -> dict | None:
    """Carte choroplèthe nationale avec tooltip adaptatif à l'indicateur."""
    st.markdown(_tooltip_style(), unsafe_allow_html=True)

    if not geojson or master.empty:
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
    cmap = LinearColormap(colors=colors, vmin=vmin, vmax=vmax)

    # Label et format du tooltip selon l'indicateur sélectionné
    _metric_meta: dict[str, tuple[str, str]] = {
        "score_global":         ("Score global",        "{:.1f}/100"),
        "apl_median_dept":      ("APL médian",          "{:.1f}\u202f/hab."),
        "temps_acces_median":   ("Temps d'accès",       "{:.1f}\u202fmin"),
        "med_gen_pour_100k":    ("Médecins / 100k",     "{:.0f}"),
        "structures_pour_100k": ("Structures / 100k",   "{:.1f}"),
        "prix_m2_moyen":        ("Prix médian /m²",     "{:,.0f}\u202f€"),
        "pct_plus_65":          ("Part des 65+",        "{:.1f}\u202f%"),
        "pct_moins_25":         ("Part des <25",        "{:.1f}\u202f%"),
    }
    main_label, main_fmt = _metric_meta.get(metric, (metric, "{}"))

    m = folium.Map(
        location=[46.6, 2.5],
        zoom_start=6,
        tiles=TILE_URL,
        attr=TILE_ATTR,
        zoom_control=True,
        scrollWheelZoom=True,
        min_zoom=5,
        max_zoom=10,
        # Restreint le pan/zoom à l'emprise de la France métropolitaine
        max_bounds=True,
        min_lat=41.0,
        max_lat=51.5,
        min_lon=-5.5,
        max_lon=10.0,
    )
    m.fit_bounds([[41.0, -5.5], [51.5, 10.0]])

    # Enrichit les propriétés GeoJSON — valeur principale + contexte
    import copy
    geojson_enriched = copy.deepcopy(geojson)
    for feat in geojson_enriched["features"]:
        code = feat["properties"]["code"]
        row = master[master["dept"] == code]
        if not row.empty:
            rv = row.iloc[0]
            feat["properties"]["dept_name"]  = str(rv.get("Nom du département", "—"))
            feat["properties"]["region_name"] = str(rv.get("Nom de la région", "—"))
            feat["properties"]["zone"]        = str(rv.get("zone_short", "—"))
            sg = rv.get("score_global")
            feat["properties"]["score_global_display"] = (
                f"{sg:.1f}/100" if pd.notna(sg) else "—"
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
                feat["properties"]["main_display"] = "—"
        else:
            feat["properties"].update(
                dept_name="—", region_name="—", zone="—",
                score_global_display="—", main_display="—",
            )

    def _style(feature: dict) -> dict:
        code = feature["properties"]["code"]
        val = data_map.get(code)
        if val is None or pd.isna(val):
            return {"fillColor": "#E8E6DD", "color": BORDER_COLOR,
                    "weight": 0.6, "fillOpacity": 0.35}
        return {"fillColor": cmap(val), "color": BORDER_COLOR,
                "weight": BORDER_WIDTH, "fillOpacity": 0.88}

    def _highlight(feature: dict) -> dict:
        return {"fillColor": HOVER_COLOR, "color": HOVER_COLOR,
                "weight": 2, "fillOpacity": 0.15}

    tooltip = folium.GeoJsonTooltip(
        fields=["dept_name", "code", "main_display",
                "score_global_display", "zone", "region_name"],
        aliases=["Département", "Code", main_label,
                 "Score global", "Zone", "Région"],
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

    event = st_folium(
        m,
        width=None,
        height=height,
        returned_objects=["last_active_drawing", "last_object_clicked"],
        key=key,
    )
    return event


# ──────────────────────────────────────────────────────────────────────────────
# CARTE COMMUNALE (zoom département)
# ──────────────────────────────────────────────────────────────────────────────

# Coordonnées fixes par département (lat, lon, zoom) — plus fiable que les centroids GeoJSON
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
def _fetch_communes_geojson(dept_code: str) -> dict | None:
    """Récupère le GeoJSON communal depuis geo.api.gouv.fr."""
    url = (
        f"https://geo.api.gouv.fr/departements/{dept_code}/communes"
        "?fields=code,nom,centre,contour&format=geojson&geometry=contour"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


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

    # Pré-calcul des couleurs hex par code commune (évite tout appel dans _style)
    code_to_color: dict[str, str] = {}
    for feat in geojson["features"]:
        code = feat["properties"]["code"]
        val = val_map.get(code)
        if val is not None:
            try:
                code_to_color[code] = cmap(float(val))
            except Exception:
                code_to_color[code] = "#E8E6DD"

    # Enrichit props pour le tooltip
    import copy
    geojson_enriched = copy.deepcopy(geojson)
    for feat in geojson_enriched["features"]:
        code = feat["properties"]["code"]
        val = val_map.get(code)
        if val is not None and not pd.isna(val):
            feat["properties"]["val_display"] = (
                f"{float(val):,.0f}\u202f{unit}".replace(",", "\u202f")
            )
            feat["properties"]["has_data"] = "oui"
        else:
            feat["properties"]["val_display"] = "—"
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

    tooltip = folium.GeoJsonTooltip(
        fields=["nom", "code", "val_display"],
        aliases=["Commune", "Code INSEE", metric_label],
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

    # Légende colormap en bas à droite
    cmap.add_to(m)

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
        width=None,
        height=height,
        returned_objects=["last_object_clicked"],
        key=key,
    )
    return event
