"""Accès routier réel aux soins de premier recours — pilote IGN Géoplateforme.

Services (sans clé, Licence Ouverte) :
- itinéraire : https://data.geopf.fr/navigation/itineraire  (resource bdtopo-valhalla)
- isochrone  : https://data.geopf.fr/navigation/isochrone   (resource bdtopo-valhalla)
Documentation : https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/

Méthode (département pilote) :
1. Points d'offre = communes du département où une offre de médecine générale
   est recensée (temps d'accès interne = 0, cohérent avec l'indicateur maison) ;
   coordonnées = centre de la commune (API Géo). Limite : le centre de la
   commune n'est pas l'adresse du cabinet (à remplacer par les coordonnées
   ANS / FINESS+ dans une version suivante).
2. Pour chaque commune du département : temps de trajet routier (voiture)
   vers le point d'offre le plus proche à vol d'oiseau parmi les 3 plus
   proches (le minimum des 3 itinéraires), en minutes. Les communes d'offre
   ont un temps intra-communal nul par construction (présence, pas trajet).
3. Isochrones 10 / 15 / 20 / 30 min depuis chaque point d'offre, unis par
   seuil (shapely) → zones accessibles ; population couverte = population des
   communes dont le centre est dans la zone.
Tout est pré-calculé et mis en cache dans static/geo/acces_ign_<dept>.json
(aucun appel API à la consultation). Respect des quotas : requêtes espacées,
reprise sur cache intermédiaire.

Usage : python3 scripts/donnees/calculer_acces_ign.py --dept 18 [--refresh]
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "static" / "geo"
CACHE_DIR = ROOT / "data_corrections" / "references" / "ign_cache"
ROUTE_URL = "https://data.geopf.fr/navigation/itineraire"
ISO_URL = "https://data.geopf.fr/navigation/isochrone"
SEUILS_MIN = (10, 15, 20, 30)
PAUSE = 0.12   # s entre deux requêtes


def _norm(s: str) -> str:
    from app.commune_opportunity import norm_commune_name
    return norm_commune_name(s)


def _hav(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    x = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(x))


def _cached_get(url: str, params: dict, cache: Path):
    if cache.exists():
        return json.loads(cache.read_text())
    for tentative in range(3):
        try:
            r = requests.get(url, params=params, timeout=40)
            if r.status_code == 200:
                data = r.json()
                cache.write_text(json.dumps(data))
                time.sleep(PAUSE)
                return data
            if r.status_code == 429:
                time.sleep(5 * (tentative + 1)); continue
            return {"_erreur": r.status_code, "_texte": r.text[:200]}
        except requests.RequestException as exc:
            time.sleep(2); last = str(exc)
    return {"_erreur": "reseau", "_texte": last}


def communes(dept: str) -> pd.DataFrame:
    r = requests.get(f"https://geo.api.gouv.fr/departements/{dept}/communes",
                     params={"fields": "code,nom,centre,population"}, timeout=60)
    r.raise_for_status()
    rows = [{"code_insee": c["code"], "nom": c["nom"], "lon": c["centre"]["coordinates"][0],
             "lat": c["centre"]["coordinates"][1], "population": c.get("population", 0)} for c in r.json()]
    df = pd.DataFrame(rows)
    df["key"] = df["nom"].map(_norm)
    return df


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    ap = argparse.ArgumentParser()
    ap.add_argument("--dept", required=True)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    dept = args.dept.zfill(2)
    cache = CACHE_DIR / dept
    cache.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"acces_ign_{dept}.json"
    if out.exists() and not args.refresh:
        print("Déjà calculé :", out); return

    com = communes(dept)
    temps = pd.read_csv(ROOT / "static/data/temps_acces.csv.gz", sep=";")
    temps = temps[temps["code_departement"].astype(str).str.zfill(2) == dept].copy()
    temps["key"] = temps["commune"].map(_norm)
    com = com.merge(temps[["key", "temps_acces"]], on="key", how="left")
    offre = com[com["temps_acces"] == 0].copy()
    print(f"{dept} : {len(com)} communes, {len(offre)} points d'offre (temps interne = 0)")
    if offre.empty:
        raise SystemExit("Aucun point d'offre : vérifier le fichier temps_acces.")

    # ── 2. Itinéraires commune → 3 points d'offre les plus proches ─────────────
    pts = offre[["lon", "lat"]].values.tolist()
    noms = offre["nom"].tolist()
    res = []
    for i, c in com.iterrows():
        if c["temps_acces"] == 0:
            res.append({"code_insee": c["code_insee"], "nom": c["nom"], "population": c["population"],
                        "temps_ign_min": 0.0, "offre_cible": c["nom"], "distance_km": 0.0,
                        "temps_interne_min": 0.0, "statut": "offre sur place"})
            continue
        proches = sorted(range(len(pts)), key=lambda j: _hav((c["lon"], c["lat"]), pts[j]))[:3]
        best = None
        for j in proches:
            params = {"resource": "bdtopo-valhalla", "start": f"{c['lon']},{c['lat']}",
                      "end": f"{pts[j][0]},{pts[j][1]}", "profile": "car", "optimization": "fastest",
                      "timeUnit": "minute", "distanceUnit": "kilometer", "getSteps": "false"}
            d = _cached_get(ROUTE_URL, params, cache / f"route_{c['code_insee']}_{offre.iloc[j]['code_insee']}.json")
            if "_erreur" in d or "duration" not in d:
                continue
            if best is None or d["duration"] < best[0]:
                best = (float(d["duration"]), noms[j], float(d.get("distance", float("nan"))))
        res.append({"code_insee": c["code_insee"], "nom": c["nom"], "population": c["population"],
                    "temps_ign_min": best[0] if best else None, "offre_cible": best[1] if best else None,
                    "distance_km": best[2] if best else None,
                    "temps_interne_min": float(c["temps_acces"]) if pd.notna(c["temps_acces"]) else None,
                    "statut": "calculé" if best else "non joignable par la route"})
        if (len(res) % 50) == 0:
            print(f"  itinéraires : {len(res)}/{len(com)}")
    df = pd.DataFrame(res)

    # ── 3. Isochrones par seuil depuis chaque point d'offre, union ─────────────
    from shapely.geometry import Point, shape
    from shapely.ops import unary_union

    zones = {}
    for seuil in SEUILS_MIN:
        polys = []
        for _, o in offre.iterrows():
            params = {"point": f"{o['lon']},{o['lat']}", "resource": "bdtopo-valhalla", "costType": "time",
                      "costValue": str(seuil * 60), "profile": "car", "direction": "departure",
                      "geometryFormat": "geojson"}
            d = _cached_get(ISO_URL, params, cache / f"iso_{o['code_insee']}_{seuil}.json")
            if "_erreur" in d or "geometry" not in d:
                continue
            try:
                polys.append(shape(d["geometry"]).buffer(0))
            except Exception:
                continue
        union = unary_union(polys).simplify(0.0005) if polys else None
        zones[seuil] = union
        print(f"  isochrones {seuil} min : {len(polys)} polygones")

    # Population couverte par seuil (centre de commune dans la zone)
    classes = []
    for _, c in com.iterrows():
        pt = Point(c["lon"], c["lat"])
        cl = next((s for s in SEUILS_MIN if zones.get(s) is not None and zones[s].contains(pt)), None)
        classes.append(cl if cl is not None else 99)
    com["classe_iso_min"] = classes
    couverture = {str(s): int(com.loc[com["classe_iso_min"] <= s, "population"].sum()) for s in SEUILS_MIN}
    couverture["total"] = int(com["population"].sum())

    from shapely.geometry import mapping
    payload = {
        "dept": dept, "date_calcul": date.today().isoformat(),
        "source": "IGN Géoplateforme (itinéraire bdtopo-valhalla, isochrone bdtopo-valhalla), API Géo, Licence Ouverte",
        "methode": "voiture, temps le plus rapide, origine = centre de commune, destination = commune avec offre de "
                   "médecine générale recensée (temps interne 0) la plus proche parmi 3 candidats",
        "seuils_min": list(SEUILS_MIN), "nb_points_offre": int(len(offre)),
        "points_offre": offre[["code_insee", "nom", "lon", "lat"]].to_dict("records"),
        "communes": df.merge(com[["code_insee", "lon", "lat", "classe_iso_min"]], on="code_insee").to_dict("records"),
        "couverture_population": couverture,
        "isochrones": {str(s): mapping(z) for s, z in zones.items() if z is not None},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False))
    ok = df["temps_ign_min"].notna()
    print(f"Écrit : {out} ({out.stat().st_size / 1e6:.1f} Mo) · itinéraires calculés {ok.sum()}/{len(df)} · "
          f"couverture 15 min : {couverture['15'] / couverture['total']:.0%} de la population")
    both = df[ok & df["temps_interne_min"].notna() & (df["temps_interne_min"] > 0)]
    if not both.empty:
        print(f"Comparaison avec l'indicateur interne (communes > 0) : corrélation Spearman "
              f"{both[['temps_ign_min', 'temps_interne_min']].corr('spearman').iloc[0, 1]:.2f}, "
              f"écart médian {(both['temps_ign_min'] - both['temps_interne_min']).median():+.1f} min")


if __name__ == "__main__":
    main()
