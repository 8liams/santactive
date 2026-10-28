"""Accès routier réel aux soins de premier recours — pilote IGN Géoplateforme.

Affiche les résultats pré-calculés par scripts/donnees/calculer_acces_ign.py
(static/geo/acces_ign_<dept>.json) et un simulateur d'implantation :

1. choix de la commune d'implantation ;
2. choix du seuil de trajet (minutes de voiture) ;
3. situation actuelle (population au-delà du seuil) ;
4. scénario : isochrones IGN calculées depuis la commune choisie (10, 15,
   20 min, mises en cache 24 h) ;
5. visualisation avant / après / gain seulement, cadrée sur le scénario ;
6. synthèse chiffrée et liste des communes nouvellement couvertes.

Couverture « théorique » : une commune est couverte au seuil S si son centre
est à moins de S min d'une commune disposant d'une offre de médecine générale
(itinéraire IGN vers les trois plus proches à vol d'oiseau, ou isochrone IGN
depuis un point d'offre — la plus favorable des deux mesures). Cela ne mesure
ni la capacité des cabinets ni l'accès effectif à une consultation.
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
from ..components.nav import NavCrumb, internal_href, render_breadcrumb

GEO_DIR = Path("static/geo")
# Départements pilotes validés (calcul complet vérifié). Un fichier présent
# dans static/geo n'est affiché que s'il figure ici.
PILOTES_VALIDES = {"18": "Cher"}
SEUILS = (10, 15, 20)
_COULEURS = {10: "#1B5E3F", 15: "#7DBE8F", 20: "#E8A838", 30: "#D9772B", 99: "#A51C30"}
_LIB_CLASSE = {0: "offre sur place", 10: "≤ 10 min", 15: "10–15 min", 20: "15–20 min", 30: "20–30 min", 99: "> 30 min"}
_NEUF = "#1A3D8F"


@st.cache_data(show_spinner=False)
def _charger(dept: str) -> dict | None:
    p = GEO_DIR / f"acces_ign_{dept}.json"
    return json.loads(p.read_text()) if p.exists() else None


def pilotes_disponibles() -> dict[str, str]:
    """Départements pilotes à la fois validés et pré-calculés."""
    return {d: n for d, n in PILOTES_VALIDES.items() if (GEO_DIR / f"acces_ign_{d}.json").exists()}


@st.cache_data(ttl=86400, show_spinner=False)
def _isochrone_live(lon: float, lat: float, minutes: int) -> dict | None:
    """Isochrone IGN à la demande (simulation d'implantation), mise en cache 24 h."""
    import time

    import requests

    params = {"point": f"{lon},{lat}", "resource": "bdtopo-valhalla", "costType": "time",
              "costValue": str(minutes * 60), "profile": "car", "direction": "departure", "geometryFormat": "geojson"}
    for tentative in range(3):           # le service limite les rafales : on réessaie avec une pause
        try:
            r = requests.get("https://data.geopf.fr/navigation/isochrone", timeout=40, params=params)
            if r.status_code == 200:
                return r.json().get("geometry")
            if r.status_code not in (429, 500, 502, 503, 504):
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (tentative + 1))
    return None


def _classe(t) -> int:
    """Classe de temps (borne supérieure en minutes) d'un temps de trajet."""
    if pd.isna(t):
        return 99
    if t <= 0:
        return 0
    for s in (10, 15, 20, 30):
        if t <= s:
            return s
    return 99


def preparer(d: dict) -> pd.DataFrame:
    """Classe « avant » par commune = la plus favorable des deux mesures IGN
    (itinéraire vers les 3 offres les plus proches à vol d'oiseau ; isochrones
    depuis chaque point d'offre). Les deux divergent pour quelques communes
    (une offre plus rapide par la route qu'à vol d'oiseau, ou inversement)."""
    com = pd.DataFrame(d["communes"])
    route = pd.to_numeric(com["temps_ign_min"], errors="coerce")
    iso = pd.to_numeric(com["classe_iso_min"], errors="coerce").fillna(99).astype(int)
    com["classe_route"] = route.apply(_classe)
    com["classe_iso"] = iso.where(com["classe_route"] != 0, 0)
    com["classe_avant"] = com[["classe_route", "classe_iso"]].min(axis=1)
    com["divergence"] = (com["classe_route"] != com["classe_iso"]) & (com["classe_route"] > 0)
    return com


def scenario(com: pd.DataFrame, geoms: dict[int, dict]) -> pd.DataFrame:
    """Classe « après » par commune, connaissant les isochrones (10/15/20) de la nouvelle offre."""
    from shapely.geometry import Point, shape

    polys = {m: shape(g) for m, g in geoms.items() if g}
    com = com.copy()
    pts = [Point(x, y) for x, y in zip(com["lon"], com["lat"])]
    com["classe_neuf"] = [next((m for m in SEUILS if m in polys and polys[m].contains(p)), 99) for p in pts]
    com["classe_apres"] = com[["classe_avant", "classe_neuf"]].min(axis=1)
    return com


def gains(com: pd.DataFrame, seuil: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(communes nouvellement couvertes au seuil, communes déjà couvertes dont la classe s'améliore)."""
    gain = com[(com["classe_avant"] > seuil) & (com["classe_apres"] <= seuil)]
    rapp = com[(com["classe_avant"] <= seuil) & (com["classe_avant"] > 0) & (com["classe_apres"] < com["classe_avant"])]
    return gain, rapp


def _fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def _kpi(label: str, value: str, ctx: str, color: str = "#1A3D8F") -> str:
    return (f'<div class="diagnostic-kpi" style="padding:12px 14px;border-top:3px solid {color};">'
            f'<div class="diagnostic-kpi-label">{label}</div>'
            f'<div class="diagnostic-kpi-value" style="font-size:26px;margin-bottom:6px;">{value}</div>'
            f'<div style="font-size:11px;color:#6B6B68;line-height:1.4;">{ctx}</div></div>')


def render(data: dict) -> None:
    pilotes = pilotes_disponibles()
    qp_dept = str(st.query_params.get("dept_code") or st.session_state.get("dept_code") or "")
    dept = qp_dept if qp_dept in pilotes else (next(iter(pilotes)) if pilotes else "")
    names = data["master"].set_index("dept")["Nom du département"].to_dict()

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Accès routier")], key_prefix="ign_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">PILOTE EXPÉRIMENTAL</span>'
        '<span class="dot"></span><span class="region">IGN Géoplateforme · réseau routier réel · couverture théorique</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Accès routier <em>aux soins de premier recours</em></h1></div>'
        '</div>', unsafe_allow_html=True)
    if not pilotes:
        st.info("Aucun département pilote calculé. Lancer `python3 scripts/donnees/calculer_acces_ign.py --dept 18`.")
        return
    if len(pilotes) > 1:
        dept = st.selectbox("Département pilote", list(pilotes), index=list(pilotes).index(dept),
                            format_func=lambda c: f"{c} · {pilotes[c]}", key="ign_dept")
    d = _charger(dept)
    if not d:
        st.warning("Fichier de calcul introuvable."); return
    com = preparer(d)
    nom_dept = names.get(dept, pilotes.get(dept, dept))
    tot = int(com["population"].sum()) or 1

    # ── Territoire pilote et liens de parcours ───────────────────────────────
    autres = ", ".join(f"{c} · {n}" for c, n in pilotes.items() if c != dept) or "aucun autre pour l’instant"
    st.markdown(
        f'<div class="ign-pilote"><div><span class="ign-pilote-lbl">Territoire pilote</span>'
        f'<span class="ign-pilote-nom">{html.escape(nom_dept)} ({dept})</span>'
        f'<span class="ign-pilote-ctx">{len(com)} communes · {d["nb_points_offre"]} communes avec offre de médecine '
        f'générale · calcul du {d["date_calcul"]} · autres départements : {html.escape(autres)}</span></div>'
        f'<div class="ign-pilote-links"><a href="{internal_href("dept", dept_code=dept)}" target="_self">Diagnostic {html.escape(nom_dept)} →</a>'
        f'<a href="{internal_href("dept", dept_code=dept)}#communes" target="_self">Communes prioritaires →</a></div></div>',
        unsafe_allow_html=True)
    st.markdown(
        '<p class="section-lead" style="max-width:900px;">Temps de trajet en voiture (IGN) depuis le centre de chaque '
        'commune vers la commune la plus proche disposant d’une offre de médecine générale. Mesure de '
        '<strong>couverture géographique théorique</strong> : elle ne dit rien de la capacité des cabinets ni de '
        'l’obtention effective d’un rendez-vous, et ne remplace pas l’indicateur national de temps d’accès.</p>',
        unsafe_allow_html=True)

    # ── Situation actuelle ────────────────────────────────────────────────────
    st.markdown('<h4 class="subsection-title" style="margin-top:14px;">Situation actuelle</h4>', unsafe_allow_html=True)
    c = st.columns(4)
    for col, s in zip(c, (10, 15, 20)):
        pop = int(com.loc[com["classe_avant"] <= s, "population"].sum())
        col.markdown(_kpi(f"≤ {s} min", f"{pop / tot:.0%}", f"de la population ({_fmt(pop)} hab.)", _COULEURS[s]),
                     unsafe_allow_html=True)
    loin = com[com["classe_avant"] > 15]
    c[3].markdown(_kpi("> 15 min", f"{_fmt(loin['population'].sum())}",
                       f"habitants dans {len(loin)} communes au-delà de 15 min", "#D9772B"), unsafe_allow_html=True)

    # ── Simulation ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:26px;"><div class="section-eyebrow">SIMULATION</div>'
                '<h2 class="section-title">Et si une offre s’installait <em>ici</em> ?</h2>'
                '<p class="section-lead">Choisissez une commune sans offre et un seuil de trajet : les isochrones IGN '
                'calculées depuis cette commune donnent la population qui passerait sous le seuil.</p></div>',
                unsafe_allow_html=True)
    cands = com[com["classe_avant"] > 0].sort_values("population", ascending=False)
    labels = {r["nom"]: f'{r["nom"]} · {_fmt(r["population"])} hab. · {_LIB_CLASSE[int(r["classe_avant"])]} aujourd’hui'
              for _, r in cands.iterrows()}
    options = ["—"] + list(labels)
    qp_commune = str(st.query_params.get("commune") or "")
    if qp_commune in labels and "ign_sim" not in st.session_state:
        st.session_state["ign_sim"] = qp_commune
    s1, s2 = st.columns([2.2, 1])
    choix = s1.selectbox("1 · Commune d’implantation (sans offre aujourd’hui)", options,
                         format_func=lambda n: labels.get(n, n), key="ign_sim")
    seuil = s2.radio("2 · Seuil de trajet en voiture", SEUILS, index=1, horizontal=True, key="ign_seuil",
                     format_func=lambda m: f"{m} min")

    sim_geoms: dict[int, dict] = {}
    gain = rapp = pd.DataFrame()
    row = None
    mode = "Situation actuelle"
    cadrage = False
    if choix != "—":
        row = cands[cands["nom"] == choix].iloc[0]
        with st.spinner("Calcul des isochrones IGN depuis la commune choisie…"):
            sim_geoms = {m: g for m in SEUILS if (g := _isochrone_live(float(row["lon"]), float(row["lat"]), m))}
        if not sim_geoms:
            st.warning("Service IGN indisponible pour le moment : scénario non calculé. Réessayez dans quelques secondes.")
        else:
            if len(sim_geoms) < len(SEUILS):
                st.warning("Isochrone(s) manquante(s) : " + ", ".join(f"{m} min" for m in SEUILS if m not in sim_geoms)
                           + " — le scénario est incomplet, réessayez.")
            com = scenario(com, sim_geoms)
            gain, rapp = gains(com, seuil)
            deja = int(com.loc[com["classe_avant"] > seuil, "population"].sum())
            apres = int(com.loc[com["classe_apres"] > seuil, "population"].sum())
            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(_kpi("Avant", f"{_fmt(deja)}", f"habitants à plus de {seuil} min ({int((com['classe_avant'] > seuil).sum())} communes)", "#D9772B"), unsafe_allow_html=True)
            m2.markdown(_kpi("Après", f"{_fmt(apres)}", f"habitants resteraient à plus de {seuil} min", "#D9772B"), unsafe_allow_html=True)
            m3.markdown(_kpi("Nouvellement couverts", f"+{_fmt(gain['population'].sum())}",
                             f"habitants dans {len(gain)} commune{'s' if len(gain) != 1 else ''} passant sous {seuil} min", _NEUF), unsafe_allow_html=True)
            m4.markdown(_kpi("Rapprochés", f"{_fmt(rapp['population'].sum())}",
                             f"habitants déjà sous {seuil} min dont la classe de trajet s’améliore ({len(rapp)} communes)", "#1B5E3F"), unsafe_allow_html=True)

            # Synthèse textuelle, y compris lorsque le gain est nul
            t_route = row["temps_ign_min"]; cl_av = int(row["classe_avant"])
            situ = (f"<strong>{html.escape(choix)}</strong> ({_fmt(row['population'])} hab.) est aujourd’hui dans la classe "
                    f"{_LIB_CLASSE[cl_av]}")
            if pd.notna(t_route):
                situ += f" (itinéraire calculé : {t_route:.0f} min vers {html.escape(str(row['offre_cible']))}"
                if row["divergence"] and row["classe_iso"] < row["classe_route"]:
                    situ += f", mais à l’intérieur de l’isochrone {int(row['classe_iso'])} min d’une autre commune d’offre)"
                else:
                    situ += ")"
            situ += "."
            if len(gain):
                lst = ", ".join(f"{html.escape(r['nom'])} ({_fmt(r['population'])} hab., {_LIB_CLASSE[int(r['classe_avant'])]} → {_LIB_CLASSE[int(r['classe_apres'])]})"
                                for _, r in gain.sort_values("population", ascending=False).head(8).iterrows())
                texte = (f"{situ} Une offre de médecine générale à {html.escape(choix)} placerait <strong>{_fmt(gain['population'].sum())} habitants</strong> "
                         f"de {len(gain)} commune{'s' if len(gain) != 1 else ''} à moins de {seuil} min : {lst}"
                         + (" …" if len(gain) > 8 else "") + ".")
            else:
                texte = (f"{situ} <strong>Aucune commune ne passerait sous {seuil} min</strong> : toutes celles situées à moins de "
                         f"{seuil} min de {html.escape(choix)} sont déjà couvertes par une offre existante au sens de la couverture "
                         f"théorique. Ce zéro ne signifie pas qu’une implantation serait sans intérêt : elle réduirait les "
                         f"distances, soulagerait les cabinets voisins et pourrait répondre à une insuffisance de capacité, que "
                         f"cette mesure géographique ne voit pas.")
            if len(rapp):
                texte += (f" Par ailleurs {_fmt(rapp['population'].sum())} habitants déjà sous le seuil verraient leur classe de trajet "
                          f"s’améliorer.")
            st.markdown(f'<p class="dim-switch-note">{texte}</p>', unsafe_allow_html=True)

            v1, v2 = st.columns([2.2, 1])
            mode = v1.radio("3 · Affichage", ["Situation actuelle", "Avec la nouvelle offre", "Gain seulement"],
                            index=1, horizontal=True, key="ign_mode")
            cadrage = v2.toggle("Cadrer sur le scénario", value=True, key="ign_cadrage")

    # ── Carte ─────────────────────────────────────────────────────────────────
    st.markdown('<h4 class="subsection-title" style="margin-top:14px;">Carte d’accessibilité routière</h4>', unsafe_allow_html=True)
    m = folium.Map(location=[com["lat"].mean(), com["lon"].mean()], zoom_start=9, tiles=TILE_URL, attr=TILE_ATTR,
                   scrollWheelZoom=False)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container{background:#F4F3EE!important;}"
        ".sa-ign-legend{font-family:Marianne,Inter,sans-serif;font-size:11px;background:rgba(255,255,255,.95);"
        "padding:10px 12px;border-radius:4px;border:1px solid #C9C6BA;line-height:1.7;}"
        ".sa-ign-legend b{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#6B6B68;margin-bottom:4px;}"
        ".sa-ign-legend i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:middle;}"
        ".sa-ign-legend i.pt{border-radius:50%;width:10px;height:10px;}"
        ".sa-ign-star{font-size:26px;line-height:1;color:#1A3D8F;text-shadow:0 0 3px #fff,0 0 3px #fff;}</style>"))
    faible = mode == "Gain seulement"
    for s in (30, 20, 15, 10):
        g = d["isochrones"].get(str(s))
        if g:
            folium.GeoJson({"type": "Feature", "geometry": g}, name=f"Aujourd'hui ≤ {s} min",
                           style_function=lambda f, c=_COULEURS[s], fo=0.08 if faible else 0.30, w=0.4 if faible else 1.0:
                           {"fillColor": c, "color": c, "weight": w, "fillOpacity": fo}).add_to(m)
    if sim_geoms and mode != "Situation actuelle":
        for s in (20, 15, 10):
            if s in sim_geoms and (s == seuil or mode == "Avec la nouvelle offre"):
                folium.GeoJson({"type": "Feature", "geometry": sim_geoms[s]}, name=f"Nouvelle offre ≤ {s} min",
                               style_function=lambda f, s_=s: {"fillColor": _NEUF, "color": _NEUF, "weight": 2.2 if s_ == seuil else 1,
                                                               "fillOpacity": 0.22 if s_ == seuil else 0.08,
                                                               "dashArray": "6 4"}).add_to(m)
    gain_codes = set(gain["code_insee"]) if len(gain) else set()
    rapp_codes = set(rapp["code_insee"]) if len(rapp) else set()
    for _, r in com.iterrows():
        cl = int(r["classe_avant"])
        nom = html.escape(str(r["nom"]))
        if cl == 0:
            tip = f"{nom} · offre de médecine générale recensée"
            folium.CircleMarker([r["lat"], r["lon"]], radius=4, color="#FFFFFF", fill=True, fill_color="#0A1938",
                                fill_opacity=1, weight=1.2, tooltip=tip).add_to(m)
            continue
        base = f"{nom} · {_LIB_CLASSE[cl]} · {_fmt(r['population'])} hab."
        if r["code_insee"] in gain_codes:
            tip = f"{base} → {_LIB_CLASSE[int(r['classe_apres'])]} avec la nouvelle offre"
            folium.CircleMarker([r["lat"], r["lon"]], radius=7, color=_NEUF, fill=True, fill_color="#FFFFFF",
                                fill_opacity=1, weight=3, tooltip=tip).add_to(m)
        elif r["code_insee"] in rapp_codes:
            tip = f"{base} → {_LIB_CLASSE[int(r['classe_apres'])]} (rapprochée)"
            folium.CircleMarker([r["lat"], r["lon"]], radius=5, color="#1B5E3F", fill=True, fill_color="#FFFFFF",
                                fill_opacity=1, weight=2, tooltip=tip).add_to(m)
        elif not faible:
            col = _COULEURS[cl]
            folium.CircleMarker([r["lat"], r["lon"]], radius=3 if cl <= 15 else 5, color="#FFFFFF" if cl > 15 else col,
                                fill=True, fill_color=col, fill_opacity=0.95, weight=1 if cl > 15 else 0.5, tooltip=base).add_to(m)
    if row is not None:
        folium.Marker([float(row["lat"]), float(row["lon"])], tooltip=f"Nouvelle offre simulée : {html.escape(choix)}",
                      icon=folium.DivIcon(html='<div class="sa-ign-star">★</div>', icon_size=(26, 26), icon_anchor=(13, 13))).add_to(m)
        if cadrage and sim_geoms:
            from shapely.geometry import shape as _shape
            b = _shape(sim_geoms[max(sim_geoms)]).bounds
            m.fit_bounds([[b[1], b[0]], [b[3], b[2]]], padding=(20, 20))
    legend = ('<div class="sa-ign-legend"><b>Aujourd’hui : trajet vers une offre</b>'
              + "".join(f'<div><i style="background:{_COULEURS[s]};opacity:.75;"></i>≤ {s} min</div>' for s in (10, 15, 20, 30))
              + '<b style="margin-top:6px;">Communes</b>'
              '<div><i class="pt" style="background:#0A1938;"></i>offre de médecine générale</div>'
              '<div><i class="pt" style="background:#D9772B;"></i>à plus de 15 min (taille = éloignement)</div>'
              + (f'<b style="margin-top:6px;">Scénario</b><div><span class="sa-ign-star" style="font-size:14px;">★</span> nouvelle offre simulée</div>'
                 f'<div><i style="border:2px dashed {_NEUF};background:rgba(26,61,143,.2);"></i>zone ≤ {seuil} min depuis la nouvelle offre</div>'
                 f'<div><i class="pt" style="border:3px solid {_NEUF};background:#fff;"></i>commune nouvellement couverte</div>'
                 '<div><i class="pt" style="border:2px solid #1B5E3F;background:#fff;"></i>commune rapprochée</div>' if sim_geoms else "")
              + '</div>')
    m.get_root().html.add_child(folium.Element(
        '<div class="leaflet-bottom leaflet-left" style="pointer-events:none;">'
        f'<div class="leaflet-control" style="margin:0 0 24px 12px;">{legend}</div></div>'))
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=580, returned_objects=[],
              key=f"ign_map_{dept}_{choix}_{seuil}_{mode}_{cadrage}")
    st.caption(f"{int(com['temps_ign_min'].notna().sum())} itinéraires calculés sur {len(com)} communes · {d['nb_points_offre']} points "
               f"d’offre · {int(com['divergence'].sum())} communes où itinéraire et isochrone donnent des classes différentes "
               "(la plus favorable est retenue).")

    if len(gain):
        rows = "".join(
            f'<tr><td class="metric-label">{html.escape(str(r["nom"]))}</td><td>{_fmt(r["population"])}</td>'
            f'<td>{_LIB_CLASSE[int(r["classe_avant"])]}</td><td>{_LIB_CLASSE[int(r["classe_apres"])]}</td>'
            f'<td style="color:#6B6B68;">{html.escape(str(r["offre_cible"]))}</td></tr>'
            for _, r in gain.sort_values("population", ascending=False).iterrows())
        st.markdown('<div class="sa-tbl-scroll"><table class="comparison-table-v2 commune-action-table"><thead><tr>'
                    '<th class="metric-col">Commune nouvellement couverte</th><th class="metric-col">Habitants</th>'
                    '<th class="metric-col">Aujourd’hui</th><th class="metric-col">Avec la nouvelle offre</th>'
                    '<th class="metric-col">Offre la plus proche aujourd’hui</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)

    # ── Communes les plus éloignées + comparaison avec l'indicateur interne ───
    ok = com["temps_ign_min"].notna()
    both = com[ok & com["temps_interne_min"].notna() & (com["classe_avant"] > 0)]
    c1, c2 = st.columns([1, 1], gap="large")
    with c1:
        st.markdown('<h4 class="subsection-title">Communes les plus éloignées aujourd’hui</h4>', unsafe_allow_html=True)
        top = com[com["classe_avant"] > 0].sort_values(["classe_avant", "temps_ign_min"], ascending=[False, False]).head(12)
        rows = "".join(f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.4fr;padding:5px 10px;border-bottom:1px solid #E8E6DD;font-size:12px;">'
                       f'<span>{html.escape(str(r["nom"]))}</span><span style="text-align:right;">{_LIB_CLASSE[int(r["classe_avant"])]}</span>'
                       f'<span style="text-align:right;">{_fmt(r["population"])}</span><span style="text-align:right;color:#6B6B68;">→ {html.escape(str(r["offre_cible"]))}</span></div>'
                       for _, r in top.iterrows())
        st.markdown('<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.4fr;padding:5px 10px;background:#F3F2EC;font-size:10px;font-weight:700;text-transform:uppercase;color:#6B6B68;">'
                    '<span>Commune</span><span style="text-align:right;">Classe</span><span style="text-align:right;">Hab.</span><span style="text-align:right;">Offre la plus proche</span></div>' + rows,
                    unsafe_allow_html=True)
    with c2:
        st.markdown('<h4 class="subsection-title">IGN et indicateur interne</h4>', unsafe_allow_html=True)
        if len(both) > 5:
            corr = both[["temps_ign_min", "temps_interne_min"]].corr("spearman").iloc[0, 1]
            fig = go.Figure(go.Scatter(x=both["temps_interne_min"], y=both["temps_ign_min"], mode="markers",
                                       marker=dict(size=6, color="#1A3D8F", opacity=0.6), customdata=both["nom"],
                                       hovertemplate="%{customdata}<br>interne %{x:.0f} min · IGN %{y:.0f} min<extra></extra>"))
            mx = float(max(both["temps_ign_min"].max(), both["temps_interne_min"].max()))
            fig.add_shape(type="line", x0=0, y0=0, x1=mx, y1=mx, line=dict(color="#9C9A92", dash="dot"))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=30), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF8",
                              xaxis_title="indicateur interne (min)", yaxis_title="itinéraire IGN (min)", font=dict(size=11))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.caption(f"Corrélation de Spearman {corr:.2f} · écart médian IGN − interne : "
                       f"{(both['temps_ign_min'] - both['temps_interne_min']).median():+.1f} min (communes sans offre sur place).")
    st.markdown(
        '<div style="margin-top:12px;font-size:11px;color:#9C9A92;line-height:1.6;"><strong>Limites.</strong> Source : IGN Géoplateforme '
        '(itinéraire et isochrone bdtopo-valhalla), API Géo (centres et population des communes), Licence Ouverte. Origine et destination au '
        'centre de la commune (pas l’adresse du cabinet) ; destination = présence d’une offre recensée, pas sa capacité ni ses '
        'délais ; voiture uniquement ; offres des départements voisins ignorées (couverture sous-estimée près des limites) ; itinéraires '
        'calculés vers les trois offres les plus proches à vol d’oiseau seulement. La simulation suppose une offre de capacité '
        'suffisante et ne tient pas compte des flux vers les départements voisins.</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ign-pilote-links" style="margin-top:14px;"><a href="{internal_href("dept", dept_code=dept)}" target="_self">← Retour au diagnostic {html.escape(nom_dept)}</a>'
        f'<a href="{internal_href("comparer")}&depts={dept}" target="_self">Comparer {html.escape(nom_dept)} →</a></div>',
        unsafe_allow_html=True)
