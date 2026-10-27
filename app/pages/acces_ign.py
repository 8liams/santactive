"""Accès routier réel aux soins de premier recours — pilote IGN Géoplateforme.

Affiche les résultats pré-calculés par scripts/donnees/calculer_acces_ign.py
(static/geo/acces_ign_<dept>.json) : temps de trajet routier par commune vers
l'offre de médecine générale la plus proche, isochrones 10/15/20/30 min,
population couverte, comparaison avec l'indicateur interne, et simulation
d'une implantation (isochrone calculée à la demande, mise en cache).
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

from ..components.maps import TILE_ATTR, TILE_URL
from ..components.nav import NavCrumb, render_breadcrumb

GEO_DIR = Path("static/geo")
_COULEURS = {"10": "#1B5E3F", "15": "#7DBE8F", "20": "#E8A838", "30": "#D9772B"}


@st.cache_data(show_spinner=False)
def _charger(dept: str) -> dict | None:
    p = GEO_DIR / f"acces_ign_{dept}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _disponibles() -> list[str]:
    return sorted(p.stem.replace("acces_ign_", "") for p in GEO_DIR.glob("acces_ign_*.json"))


@st.cache_data(ttl=86400, show_spinner=False)
def _isochrone_live(lon: float, lat: float, minutes: int) -> dict | None:
    """Isochrone IGN à la demande (simulation d'implantation), mise en cache 24 h."""
    import requests

    try:
        r = requests.get("https://data.geopf.fr/navigation/isochrone", timeout=40, params={
            "point": f"{lon},{lat}", "resource": "bdtopo-valhalla", "costType": "time",
            "costValue": str(minutes * 60), "profile": "car", "direction": "departure", "geometryFormat": "geojson"})
        r.raise_for_status()
        return r.json().get("geometry")
    except Exception:
        return None


def render(data: dict) -> None:
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Accès routier")], key_prefix="ign_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">PILOTE</span>'
        '<span class="dot"></span><span class="region">IGN Géoplateforme · réseau routier réel</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Accès routier <em>aux soins de premier recours</em></h1></div>'
        '</div>', unsafe_allow_html=True)
    dispo = _disponibles()
    if not dispo:
        st.info("Aucun département pré-calculé. Lancer `python3 scripts/donnees/calculer_acces_ign.py --dept 18`.")
        return
    names = data["master"].set_index("dept")["Nom du département"].to_dict()
    dept = st.selectbox("Département pilote", dispo, format_func=lambda d: f"{d} · {names.get(d, d)}", key="ign_dept")
    d = _charger(dept)
    if not d:
        st.warning("Fichier introuvable."); return
    com = pd.DataFrame(d["communes"])
    cov = d["couverture_population"]; tot = cov["total"] or 1
    ok = com["temps_ign_min"].notna()

    st.markdown(
        f'<p class="section-lead" style="max-width:900px;">Temps de trajet en voiture (itinéraire le plus rapide, '
        f'IGN) depuis le centre de chaque commune vers la commune la plus proche où une offre de médecine générale est '
        f'recensée ({d["nb_points_offre"]} points d’offre). Calcul du {d["date_calcul"]}, pré-calculé et mis en cache. '
        f'Les communes d’offre sont à 0 par construction (présence, pas trajet).</p>', unsafe_allow_html=True)

    c = st.columns(5)
    for col, s in zip(c, ("10", "15", "20", "30")):
        col.markdown(f'<div class="diagnostic-kpi" style="padding:12px;border-top:3px solid {_COULEURS[s]};">'
                     f'<div class="diagnostic-kpi-label">≤ {s} min</div>'
                     f'<div class="diagnostic-kpi-value" style="font-size:26px;">{cov[s] / tot:.0%}</div>'
                     f'<div class="diagnostic-kpi-context"><span style="font-size:11px;color:#6B6B68;">de la population '
                     f'({cov[s]:,} hab.)</span></div></div>'.replace(",", " "), unsafe_allow_html=True)
    loin = com[ok & (com["temps_ign_min"] > 30)]
    c[4].markdown(f'<div class="diagnostic-kpi" style="padding:12px;border-top:3px solid #A51C30;">'
                  f'<div class="diagnostic-kpi-label">&gt; 30 min</div>'
                  f'<div class="diagnostic-kpi-value" style="font-size:26px;">{len(loin)}</div>'
                  f'<div class="diagnostic-kpi-context"><span style="font-size:11px;color:#6B6B68;">communes · '
                  f'{int(loin["population"].sum()):,} hab.</span></div></div>'.replace(",", " "), unsafe_allow_html=True)

    # ── Simulation d'implantation ─────────────────────────────────────────────
    st.markdown('<h4 class="subsection-title" style="margin-top:18px;">Simuler une implantation</h4>', unsafe_allow_html=True)
    cands = com[ok & (com["temps_ign_min"] > 15)].sort_values("population", ascending=False)
    s1, s2 = st.columns([2, 1])
    choix = s1.selectbox("Commune d'implantation (parmi celles à plus de 15 min)", ["—"] + cands["nom"].tolist(), key="ign_sim")
    minutes = s2.selectbox("Rayon", [10, 15, 20], index=1, key="ign_sim_min")
    sim_geom, gain = None, None
    if choix != "—":
        row = cands[cands["nom"] == choix].iloc[0]
        sim_geom = _isochrone_live(float(row["lon"]), float(row["lat"]), int(minutes))
        if sim_geom:
            from shapely.geometry import Point, shape
            poly = shape(sim_geom)
            deja = com["classe_iso_min"] <= minutes
            dans = com.apply(lambda r: poly.contains(Point(r["lon"], r["lat"])), axis=1)
            gain = com[dans & ~deja]
            st.success(f"Une offre à {choix} placerait {int(gain['population'].sum()):,} habitants supplémentaires "
                       f"({len(gain)} communes) à moins de {minutes} min, hors population déjà couverte.".replace(",", " "))
        else:
            st.warning("Isochrone indisponible pour le moment (service IGN).")

    # ── Carte ─────────────────────────────────────────────────────────────────
    m = folium.Map(location=[com["lat"].mean(), com["lon"].mean()], zoom_start=9, tiles=TILE_URL, attr=TILE_ATTR,
                   scrollWheelZoom=False)
    for s in ("30", "20", "15", "10"):
        g = d["isochrones"].get(s)
        if g:
            folium.GeoJson({"type": "Feature", "geometry": g}, name=f"≤ {s} min",
                           style_function=lambda f, c=_COULEURS[s]: {"fillColor": c, "color": c, "weight": 0.5, "fillOpacity": 0.25}).add_to(m)
    if sim_geom:
        folium.GeoJson({"type": "Feature", "geometry": sim_geom}, name="Simulation",
                       style_function=lambda f: {"fillColor": "#1A3D8F", "color": "#1A3D8F", "weight": 2, "fillOpacity": 0.15, "dashArray": "4"}).add_to(m)
    for _, r in com.iterrows():
        t = r["temps_ign_min"]
        col = "#9C9A92" if pd.isna(t) else "#1B5E3F" if t <= 10 else "#7DBE8F" if t <= 15 else "#E8A838" if t <= 20 else "#D9772B" if t <= 30 else "#A51C30"
        if t == 0:
            etat = "offre sur place"
        elif pd.isna(t):
            etat = "non joignable"
        else:
            etat = f"{t:.0f} min vers {r['offre_cible']}"
        tip = f"{r['nom']} · {etat} · {int(r['population']):,} hab.".replace(",", "\u202f")
        folium.CircleMarker([r["lat"], r["lon"]], radius=3 if t != 0 else 4, color=col, fill=True,
                            fill_opacity=0.9, weight=0.5, tooltip=tip).add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=520, returned_objects=[], key=f"ign_map_{dept}_{choix}_{minutes}")
    st.markdown('<div class="map-legend">' + "".join(
        f'<span class="legend-item"><span class="swatch" style="background:{c};"></span>{lab}</span>'
        for lab, c in (("≤ 10 min", "#1B5E3F"), ("≤ 15", "#7DBE8F"), ("≤ 20", "#E8A838"), ("≤ 30", "#D9772B"), ("> 30", "#A51C30"), ("non joignable", "#9C9A92"))) + '</div>',
        unsafe_allow_html=True)

    # ── Comparaison avec l'indicateur interne ─────────────────────────────────
    both = com[ok & com["temps_interne_min"].notna()]
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown('<h4 class="subsection-title">Communes les plus éloignées</h4>', unsafe_allow_html=True)
        top = com[ok].sort_values("temps_ign_min", ascending=False).head(12)
        rows = "".join(f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.4fr;padding:5px 10px;border-bottom:1px solid #E8E6DD;font-size:12px;">'
                       f'<span>{html.escape(str(r["nom"]))}</span><span style="text-align:right;">{r["temps_ign_min"]:.0f} min</span>'
                       f'<span style="text-align:right;">{int(r["population"]):,}</span><span style="text-align:right;color:#6B6B68;">→ {html.escape(str(r["offre_cible"]))}</span></div>'.replace(",", " ")
                       for _, r in top.iterrows())
        st.markdown('<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.4fr;padding:5px 10px;background:#F3F2EC;font-size:10px;font-weight:700;text-transform:uppercase;color:#6B6B68;">'
                    '<span>Commune</span><span style="text-align:right;">IGN</span><span style="text-align:right;">Hab.</span><span style="text-align:right;">Offre la plus proche</span></div>' + rows,
                    unsafe_allow_html=True)
    with c2:
        st.markdown('<h4 class="subsection-title">IGN vs indicateur interne</h4>', unsafe_allow_html=True)
        if len(both) > 5:
            corr = both[["temps_ign_min", "temps_interne_min"]].corr("spearman").iloc[0, 1]
            fig = go.Figure(go.Scatter(x=both["temps_interne_min"], y=both["temps_ign_min"], mode="markers",
                                       marker=dict(size=6, color="#1A3D8F", opacity=0.6), customdata=both["nom"],
                                       hovertemplate="%{customdata}<br>interne %{x:.0f} min · IGN %{y:.0f} min<extra></extra>"))
            mx = float(max(both["temps_ign_min"].max(), both["temps_interne_min"].max()))
            fig.add_shape(type="line", x0=0, y0=0, x1=mx, y1=mx, line=dict(color="#9C9A92", dash="dot"))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=30), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF8",
                              xaxis_title="interne (min)", yaxis_title="IGN (min)", font=dict(size=11))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.caption(f"Corrélation de Spearman {corr:.2f} · écart médian IGN − interne : "
                       f"{(both['temps_ign_min'] - both['temps_interne_min']).median():+.1f} min "
                       f"(communes hors offre sur place).")
    st.markdown(
        '<div style="margin-top:12px;font-size:11px;color:#9C9A92;line-height:1.6;">Source : IGN Géoplateforme '
        '(itinéraire bdtopo-osrm, isochrone bdtopo-valhalla), API Géo (centres et population des communes), '
        'Licence Ouverte. Limites : origine et destination au centre de la commune (pas l’adresse du cabinet) ; '
        'destination = présence d’une offre recensée, pas sa capacité ; voiture uniquement ; les communes '
        'non joignables par la route restent sans valeur (jamais 0). La simulation ignore la capacité du cabinet '
        'et les flux vers les départements voisins.</div>', unsafe_allow_html=True)
