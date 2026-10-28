"""Pipeline reproductible du simulateur d'implantation, département par département.

Pour chaque département présent dans les fichiers parquet INSEE « accès aux
équipements » (millésime 2025, déjà téléchargés : voir calculer_acces_insee.py) :

1. carreaux habités (généraliste, type BPE D265) → static/geo/carreaux_mg_<dept>.csv.gz
   (code commune, centre du carreau en WGS84 arrondi à 1e-4°, population, durée
   en minutes arrondie à 0,1, commune de l'équipement le plus proche) ;
2. zones continues par classe de temps (≤ 10, 10–15, 15–20, 20–30, > 30 min) :
   union des carrés de 200 m dans la projection métrique d'origine (EPSG:3035,
   4559 Martinique, 2975 La Réunion), parties et trous < 0,2 km² retirés,
   simplification 150 m, reprojection WGS84 (4 décimales)
   → static/geo/zones_mg_<dept>.json (GeoJSON, propriété « classe ») ;
3. communes du département (API Géo : code, nom, centre, population)
   → static/geo/communes_<dept>.json ;
4. contrôles de validation → static/geo/simulateur_index.json : nombre de
   carreaux, population localisée vs population municipale, communes équipées
   (BPE) vs communes, fichiers présents ; un département n'est activé dans
   l'application que si tous les contrôles passent (clé « ok »).

Reprise : les fichiers déjà produits sont conservés (--refresh pour recalculer).
Quotas : une requête API Géo par département, espacée ; les isochrones IGN du
scénario sont calculées à la demande dans l'application (cache 24 h), aucun
appel IGN ici. Guadeloupe, Guyane et Mayotte sont hors champ de la source INSEE.

Usage : python3 scripts/donnees/preparer_simulateur.py --raw-dir <dossier parquet> [--only 18 23] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "static" / "geo"
_CRS = {"02": "EPSG:4559", "04": "EPSG:2975"}
CLASSES = ((10, "10"), (15, "15"), (20, "20"), (30, "30"), (10**9, "99"))
FERMETURE_M = 300
SIMPLIFY_M = 150          # mètres · trous et parties < MIN_AIRE_KM2 retirés (lisibilité, taille)
MIN_AIRE_KM2 = 0.2


def _classe(d: np.ndarray) -> np.ndarray:
    out = np.full(len(d), "99", dtype=object)
    for borne, lab in reversed(CLASSES):
        out[d <= borne] = lab
    return out


def zones_geojson(df: pd.DataFrame, crs_src: str) -> dict:
    """Union des carrés de 200 m par classe de temps → GeoJSON WGS84 simplifié."""
    import shapely
    from pyproj import Transformer
    from shapely.geometry import mapping
    from shapely.ops import transform

    tr = Transformer.from_crs(crs_src, "EPSG:4326", always_xy=True)
    feats = []
    cl = _classe(df["duree"].to_numpy(float))
    for _, lab in CLASSES:
        sub = df[cl == lab]
        if sub.empty:
            continue
        x = sub["X"].to_numpy(float); y = sub["Y"].to_numpy(float)
        boxes = shapely.box(x, y, x + 200, y + 200)
        # Fermeture morphologique (+FERMETURE_M puis −FERMETURE_M) : les carreaux voisins
        # d'une même classe fusionnent en surfaces continues au lieu d'une mosaïque.
        geom = shapely.union_all(boxes).buffer(FERMETURE_M, join_style="mitre").buffer(-FERMETURE_M, join_style="mitre").buffer(0)
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        nettoyes = []
        for poly in polys:
            if poly.area < MIN_AIRE_KM2 * 1e6:
                continue
            holes = [h for h in poly.interiors if shapely.Polygon(h).area >= MIN_AIRE_KM2 * 1e6]
            nettoyes.append(shapely.Polygon(poly.exterior, holes))
        if not nettoyes:
            continue
        geom = shapely.union_all(nettoyes).simplify(SIMPLIFY_M, preserve_topology=True)
        geom = transform(tr.transform, geom)
        geom = shapely.set_precision(geom, 1e-4)
        if geom.is_empty:
            continue
        feats.append({"type": "Feature", "properties": {"classe": int(lab), "pop": round(float(sub["pop"].sum())),
                                                        "nb_carreaux": int(len(sub))},
                      "geometry": mapping(geom)})
    return {"type": "FeatureCollection", "features": feats}


def communes_api(dept: str, dest: Path, refresh: bool) -> dict | None:
    if dest.exists() and not refresh:
        return json.loads(dest.read_text())
    import requests

    for tentative in range(3):
        try:
            r = requests.get(f"https://geo.api.gouv.fr/departements/{dept}/communes",
                             params={"fields": "code,nom,centre,population"}, timeout=60)
            if r.status_code == 200:
                communes = [{"code_insee": c["code"], "nom": c["nom"], "lon": round(c["centre"]["coordinates"][0], 5),
                             "lat": round(c["centre"]["coordinates"][1], 5), "population": int(c.get("population") or 0)}
                            for c in r.json()]
                # Paris, Lyon, Marseille : l'INSEE rattache les carreaux aux arrondissements municipaux
                if dept in ("75", "69", "13"):
                    r2 = requests.get("https://geo.api.gouv.fr/communes", params={"codeDepartement": dept, "type": "arrondissement-municipal",
                                                                                   "fields": "code,nom,centre,population"}, timeout=60)
                    if r2.status_code == 200:
                        arr = [{"code_insee": c["code"], "nom": c["nom"], "lon": round(c["centre"]["coordinates"][0], 5),
                                "lat": round(c["centre"]["coordinates"][1], 5), "population": int(c.get("population") or 0)}
                               for c in r2.json()]
                        parents = {"75": "75056", "69": "69123", "13": "13055"}
                        communes = [c for c in communes if c["code_insee"] != parents[dept]] + arr
                payload = {"dept": dept, "source": "API Géo (geo.api.gouv.fr), Licence Ouverte",
                           "date": date.today().isoformat(), "communes": communes}
                dest.write_text(json.dumps(payload, ensure_ascii=False))
                time.sleep(0.3)
                return payload
            if r.status_code == 429:
                time.sleep(5 * (tentative + 1)); continue
            return None
        except Exception:
            time.sleep(2)
    return None


def traiter_region(path: Path, only: set[str] | None, refresh: bool, index: dict, refresh_zones: bool = False) -> None:
    reg = re.search(r"reg(\d+)", path.name).group(1)
    crs = _CRS.get(reg, "EPSG:3035")
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT depcom AS code_insee, dep, X, Y, pop, duree, depcom_equipement AS commune_offre
        FROM read_parquet('{path.as_posix()}')
        WHERE typeeq_id = 'D265' AND pop > 0 AND duree IS NOT NULL
    """).df()
    con.close()
    from pyproj import Transformer
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    for dept, d in df.groupby("dep"):
        dept = str(dept)
        if only and dept not in only:
            continue
        t0 = time.time()
        f_car = GEO / f"carreaux_mg_{dept}.csv.gz"
        f_zon = GEO / f"zones_mg_{dept}.json"
        f_com = GEO / f"communes_{dept}.json"
        if refresh or not f_car.exists():
            lon, lat = tr.transform(d["X"].to_numpy(float) + 100, d["Y"].to_numpy(float) + 100)
            pd.DataFrame({"code_insee": d["code_insee"].values, "lon": np.round(lon, 4), "lat": np.round(lat, 4),
                          "pop": d["pop"].round(1).values, "duree": d["duree"].round(1).values,
                          "commune_offre": d["commune_offre"].values}).to_csv(f_car, index=False, compression="gzip")
        if refresh or refresh_zones or not f_zon.exists():
            f_zon.write_text(json.dumps(zones_geojson(d, crs), separators=(",", ":")))
        com = communes_api(dept, f_com, refresh)
        # ── Contrôles ───────────────────────────────────────────────────────
        pop_loc = float(d["pop"].sum())
        pop_mun = float(sum(c["population"] for c in com["communes"])) if com else float("nan")
        codes_com = {c["code_insee"] for c in com["communes"]} if com else set()
        equipees = set(d.loc[d["commune_offre"].isin(set(d["code_insee"])), "commune_offre"].unique())
        nb_com_carreaux = d["code_insee"].nunique()
        checks = {
            "carreaux": int(len(d)) >= 50,
            "communes_api": com is not None and len(codes_com) >= 1,
            "population_coherente": pd.notna(pop_mun) and pop_mun > 0 and 0.6 <= pop_loc / pop_mun <= 1.15,
            "communes_appariees": bool(codes_com) and len(set(d["code_insee"]) & codes_com) / max(1, nb_com_carreaux) >= 0.9,
            "communes_equipees": len(equipees) >= 1,
            "zones": f_zon.exists() and f_zon.stat().st_size > 200,
        }
        index[dept] = {
            "ok": all(checks.values()), "checks": checks, "region_fichier": reg,
            "nb_carreaux": int(len(d)), "population_localisee": round(pop_loc), "population_municipale": round(pop_mun) if pd.notna(pop_mun) else None,
            "nb_communes": len(codes_com), "nb_communes_carreaux": int(nb_com_carreaux), "nb_communes_equipees": len(equipees),
            "part_sup_15": round(float(d.loc[d["duree"] > 15, "pop"].sum() / pop_loc), 4) if pop_loc else None,
            "taille_ko": round((f_car.stat().st_size + f_zon.stat().st_size + (f_com.stat().st_size if f_com.exists() else 0)) / 1e3),
            "date": date.today().isoformat(),
        }
        print(f"  {dept}: {len(d):>6} carreaux · {pop_loc / 1e3:7.0f} k hab. · {len(equipees):>3} communes équipées · "
              f"{index[dept]['taille_ko']:>4} Ko · {'OK' if index[dept]['ok'] else 'À VÉRIFIER ' + str([k for k, v in checks.items() if not v])}"
              f" · {time.time() - t0:.0f} s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--millesime", default="2025")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--refresh-zones", action="store_true", help="recalculer seulement les zones (carreaux et communes conservés)")
    args = ap.parse_args()
    GEO.mkdir(parents=True, exist_ok=True)
    f_index = GEO / "simulateur_index.json"
    index = json.loads(f_index.read_text()).get("departements", {}) if f_index.exists() and not (args.refresh and not args.only) else {}
    only = {d.zfill(2) for d in args.only} if args.only else None
    files = sorted(Path(args.raw_dir).glob(f"donnees_{args.millesime}_reg*.parquet"))
    for f in files:
        print(f"→ {f.name}", flush=True)
        traiter_region(f, only, args.refresh, index, args.refresh_zones)
        f_index.write_text(json.dumps({"source": "Insee, BPE 2025, Metric-OSRM, Filosofi · API Géo · zones : union des carreaux par classe",
                                       "date": date.today().isoformat(), "departements": index}, indent=1, ensure_ascii=False))
    ok = [d for d, v in index.items() if v["ok"]]
    print(f"\n{len(ok)} départements validés sur {len(index)} ; taille totale "
          f"{sum(v['taille_ko'] for v in index.values()) / 1e3:.1f} Mo → {f_index}")


if __name__ == "__main__":
    main()
