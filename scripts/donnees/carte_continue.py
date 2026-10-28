"""Carte continue des temps d'accès à la médecine générale — approche B (grille sur réseau).

Expérimentation contrôlée (phase C, 28 octobre 2026) : pour un département, une grille
régulière de points (pas PAS_M, Lambert-93) couvrant le département ; pour chaque point,
le temps en voiture (OSRM local, profil voiture, réseau OpenStreetMap) vers le cabinet de
médecine générale le plus rapide parmi les K plus proches à vol d'oiseau (BPE 2025
géolocalisée, type D265, cabinets du département et des voisins dans un rayon de
RAYON_OFFRES_KM). Chaque point reçoit un statut :

- « calcule »     : route carrossable à moins de SNAP_SUR_M (500 m, une maille) du point,
                    itinéraire trouvé ;
- « approche »    : route la plus proche entre 500 m et SNAP_MAX_M : le temps est celui
                    depuis cette route, la maille elle-même n'est pas desservie (teinte
                    plus claire dans l'application) ;
- « non_calcule » : pas de route à moins de SNAP_MAX_M (forêt, plan d'eau, zone sans
                    voie carrossable) ou aucun itinéraire ; affiché en gris neutre.

Le temps d'un point est celui de la maille autour du point de raccordement : ce n'est
pas une mesure exacte en chaque lieu du territoire (la maille fait PAS_M de côté).

Sorties (static/geo) :
- grille_mg_<dept>.csv.gz : lon, lat, duree (min), snap_m, statut, classe ;
- continu_mg_<dept>.json  : polygones par classe (5, 10, 15, 20, 30, 99) et « 0 »
                            (non calculé), WGS84, simplifiés ;
- controle_continu_<dept>.json : concordance avec les carreaux INSEE 2025 (par classe,
                            rural / urbain, autour des seuils 10, 15, 20), test K.

Prérequis : osrm-routed lancé en local (voir docs/ETUDE_CARTE_CONTINUE.md), BPE25.parquet,
contours communaux API Géo. Usage :
  python3 scripts/donnees/carte_continue.py --dept 23 --bpe <BPE25.parquet> \
      --contours <communes_23.geojson> --osrm http://localhost:5000 [--pas 500]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "static" / "geo"
PAS_M = 500
RAYON_OFFRES_KM = 30
K_VOISINS = 30          # test K : 10 voisins manquaient le plus rapide pour 2,7 % des points en Gironde (Garonne, estuaire : jusqu’à 11 min) ; 20 → 0,6 % ; 30 retenu
K_CONTROLE = 60
SNAP_MAX_M = 2000
SNAP_SUR_M = 500        # au-delà : temps « approché » (la route la plus proche est à plus d'une maille)
CLASSES = ((5, 5), (10, 10), (15, 15), (20, 20), (30, 30), (10**9, 99))
TO_WGS = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
TO_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)


def classe(d):
    out = np.full(len(d), 99, dtype=int)
    for borne, lab in reversed(CLASSES):
        out[d <= borne] = lab
    return out


# ── 1. Offres BPE 2025 (cabinets de médecine générale) ────────────────────────

def charger_offres(bpe: Path) -> pd.DataFrame:
    """Cabinets D265 géolocalisés en Lambert-93 avec la qualité de géolocalisation BPE."""
    import duckdb
    con = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{bpe.as_posix()}')").fetchall()]
    typ = next(c for c in cols if c.upper() in ("TYPEQU", "TYPEQU_ID"))
    x = next(c for c in cols if c.upper() in ("LAMBERT_X", "X"))
    y = next(c for c in cols if c.upper() in ("LAMBERT_Y", "Y"))
    dep = next(c for c in cols if c.upper() in ("DEP", "DEPCOM"))
    qual = next((c for c in cols if c.upper().startswith("QUALI")), None)
    epsg = next((c for c in cols if c.upper() == "EPSG"), None)
    sel = f'"{typ}" AS typ, "{x}" AS x, "{y}" AS y, "{dep}" AS dep' + (f', "{qual}" AS qualite' if qual else ", NULL AS qualite") + (f', "{epsg}" AS epsg' if epsg else ", NULL AS epsg")
    df = con.execute(f"SELECT {sel} FROM read_parquet('{bpe.as_posix()}') WHERE \"{typ}\" = 'D265'").df()
    con.close()
    df["dep"] = df["dep"].astype(str).str[:2].where(~df["dep"].astype(str).str.startswith("97"), df["dep"].astype(str).str[:3])
    df["x"] = pd.to_numeric(df["x"], errors="coerce"); df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna(subset=["x", "y"])
    if epsg is not None:
        df = df[df["epsg"].astype(str).str.contains("2154")]       # métropole : Lambert-93
    # Qualité de géolocalisation BPE : QUALITE_XY A/B (acceptable/bonne) conservés ; M (mauvaise)
    # conservé seulement si l'adresse a été repérée à la voie (QUALITE_GEOLOC 11, 12, 21, 22) ;
    # exclus : position aléatoire dans la commune (33), indéterminé. Un cabinet mal placé de
    # plusieurs kilomètres fausserait la grille autour de lui.
    geoloc = next((c for c in cols if c.upper() == "QUALITE_GEOLOC"), None)
    if geoloc is not None and "geoloc" not in df.columns:
        con = duckdb.connect()
        g = con.execute(f'SELECT "{typ}" AS typ, "{x}" AS x, "{y}" AS y, "{geoloc}" AS geoloc FROM read_parquet(\'{bpe.as_posix()}\') WHERE "{typ}" = \'D265\'').df()
        con.close()
        g["x"] = pd.to_numeric(g["x"], errors="coerce"); g["y"] = pd.to_numeric(g["y"], errors="coerce")
        df = df.merge(g.drop_duplicates(["x", "y"])[["x", "y", "geoloc"]], on=["x", "y"], how="left")
    q = df["qualite"].astype(str); gl = df["geoloc"].astype(str) if "geoloc" in df.columns else pd.Series("", index=df.index)
    garde = q.isin(["A", "B"]) | ((q == "M") & gl.isin(["11", "12", "21", "22"]))
    df.attrs["exclus_qualite"] = int((~garde).sum())
    return df[garde].reset_index(drop=True)


# ── 2. Grille ─────────────────────────────────────────────────────────────────

def contour_departement(path: Path):
    g = json.loads(path.read_text(encoding="utf-8"))
    polys = [shape(f["geometry"]) for f in g["features"]]
    geom_wgs = unary_union(polys).buffer(0)
    return transform(TO_L93.transform, geom_wgs)


def grille(dept_l93, pas: int) -> pd.DataFrame:
    minx, miny, maxx, maxy = dept_l93.bounds
    xs = np.arange(math.floor(minx / pas) * pas + pas / 2, maxx, pas)
    ys = np.arange(math.floor(miny / pas) * pas + pas / 2, maxy, pas)
    X, Y = np.meshgrid(xs, ys)
    pts = pd.DataFrame({"x": X.ravel(), "y": Y.ravel()})
    inside = shapely.contains_xy(dept_l93.buffer(pas * 0.75), pts["x"].to_numpy(), pts["y"].to_numpy())
    pts = pts[inside].reset_index(drop=True)
    lon, lat = TO_WGS.transform(pts["x"].to_numpy(), pts["y"].to_numpy())
    pts["lon"] = np.round(lon, 5); pts["lat"] = np.round(lat, 5)
    return pts


# ── 3. OSRM ───────────────────────────────────────────────────────────────────

def osrm_table(base: str, sources_ll: np.ndarray, dests_ll: np.ndarray, session: requests.Session) -> tuple[np.ndarray, np.ndarray]:
    """Durées (s) sources × destinations et distance de raccordement des sources (m)."""
    coords = ";".join(f"{lon:.5f},{lat:.5f}" for lon, lat in np.vstack([sources_ll, dests_ll]))
    ns, nd = len(sources_ll), len(dests_ll)
    url = (f"{base}/table/v1/driving/{coords}?sources={';'.join(map(str, range(ns)))}"
           f"&destinations={';'.join(map(str, range(ns, ns + nd)))}&annotations=duration&skip_waypoints=false")
    for tentative in range(3):
        try:
            r = session.get(url, timeout=120)
            if r.status_code == 200:
                j = r.json()
                dur = np.array([[np.nan if v is None else v for v in row] for row in j["durations"]], dtype=float)
                snap = np.array([s.get("distance", np.nan) if s else np.nan for s in j.get("sources", [])], dtype=float)
                return dur, snap
        except requests.RequestException:
            pass
        time.sleep(1)
    return np.full((ns, nd), np.nan), np.full(ns, np.nan)


def calculer(pts: pd.DataFrame, offres: pd.DataFrame, base: str, k: int, taille_lot: int = 100) -> pd.DataFrame:
    tree = cKDTree(offres[["x", "y"]].to_numpy())
    _, idx = tree.query(pts[["x", "y"]].to_numpy(), k=min(k, len(offres)))
    idx = np.atleast_2d(idx)
    offres_ll = np.column_stack(TO_WGS.transform(offres["x"].to_numpy(), offres["y"].to_numpy()))
    duree = np.full(len(pts), np.nan); snap = np.full(len(pts), np.nan); dest = np.full(len(pts), -1)
    s = requests.Session()
    # lots spatiaux : tri par tuile de 10 × 10 points pour partager les candidats
    ordre = np.lexsort((pts["x"].to_numpy() // (PAS_M * 10), pts["y"].to_numpy() // (PAS_M * 10)))
    t0 = time.time()
    for i in range(0, len(ordre), taille_lot):
        lot = ordre[i:i + taille_lot]
        cand = np.unique(idx[lot].ravel())
        dur, sn = osrm_table(base, pts.loc[lot, ["lon", "lat"]].to_numpy(), offres_ll[cand], s)
        # seul le sous-ensemble des K candidats de chaque point compte (les autres offres de la tuile
        # ne sont pas plus proches à vol d'oiseau, mais les garder ne nuit pas : on prend le min global)
        pos = {c: j for j, c in enumerate(cand)}
        for r_, p in enumerate(lot):
            cols = [pos[c] for c in idx[p]]
            row = dur[r_, cols]
            if np.isfinite(row).any():
                j = int(np.nanargmin(row)); duree[p] = row[j] / 60; dest[p] = idx[p][j]
            snap[p] = sn[r_]
        if (i // taille_lot) % 50 == 0:
            print(f"    {i + len(lot):>7}/{len(pts)} points · {time.time() - t0:5.0f} s", flush=True)
    out = pts.copy()
    out["duree"] = np.round(duree, 2); out["snap_m"] = np.round(snap); out["offre_idx"] = dest
    ok = np.isfinite(duree) & (snap <= SNAP_MAX_M)
    out["statut"] = np.where(ok & (snap <= SNAP_SUR_M), "calcule", np.where(ok, "approche", "non_calcule"))
    out["classe"] = np.where(ok, classe(np.nan_to_num(duree, nan=1e9)), 0)
    return out


# ── 4. Polygones ──────────────────────────────────────────────────────────────

def polygones(gr: pd.DataFrame, dept_l93, pas: int, simplify_m: float = 60) -> dict:
    """Une entité par (classe, statut) : union des mailles, découpée au contour du département,
    simplifiée. Les mailles « approché » gardent leur classe mais un statut distinct (rendu plus clair)."""
    feats = []
    for (cl, stt), sub in gr.groupby(["classe", "statut"]):
        boxes = shapely.box(sub["x"].to_numpy() - pas / 2, sub["y"].to_numpy() - pas / 2, sub["x"].to_numpy() + pas / 2, sub["y"].to_numpy() + pas / 2)
        geom = shapely.union_all(boxes).buffer(0).intersection(dept_l93)
        geom = geom.simplify(simplify_m, preserve_topology=True)
        if geom.is_empty:
            continue
        geom = shapely.set_precision(transform(TO_WGS.transform, geom), 1e-5)
        feats.append({"type": "Feature", "properties": {"classe": int(cl), "nb_mailles": int(len(sub)), "statut": str(stt)},
                      "geometry": mapping(geom)})
    feats.sort(key=lambda f: (f["properties"]["statut"] != "calcule", f["properties"]["classe"]))
    return {"type": "FeatureCollection", "features": feats}


# ── 5. Contrôle contre les carreaux INSEE ─────────────────────────────────────

def controle(gr: pd.DataFrame, dept: str, pas: int) -> dict:
    car = pd.read_csv(GEO / f"carreaux_mg_{dept}.csv.gz", dtype={"code_insee": str, "commune_offre": str})
    x, y = TO_L93.transform(car["lon"].to_numpy(), car["lat"].to_numpy())
    tree = cKDTree(gr[["x", "y"]].to_numpy())
    dist, j = tree.query(np.column_stack([x, y]))
    ok = dist <= pas * 0.75
    c = car[ok].copy(); g = gr.iloc[j[ok]].reset_index(drop=True)
    c["classe_insee"] = classe(c["duree"].to_numpy(float)); c["classe_grille"] = g["classe"].to_numpy()
    c["duree_grille"] = g["duree"].to_numpy(); c["statut_grille"] = g["statut"].to_numpy()
    c["urbain"] = c["pop"] >= 50                       # ≥ 1 250 hab./km² sur le carreau
    calc = c[c["statut_grille"].isin(["calcule", "approche"])]
    def bloc(d):
        if d.empty:
            return {}
        ecart = d["duree_grille"] - d["duree"]
        res = {"carreaux": int(len(d)), "habitants": round(float(d["pop"].sum())),
               "concordance_classe": round(float((d["classe_insee"] == d["classe_grille"]).mean()), 4),
               "concordance_pop": round(float(d.loc[d["classe_insee"] == d["classe_grille"], "pop"].sum() / d["pop"].sum()), 4),
               "ecart_median_min": round(float(ecart.median()), 2), "ecart_moyen_min": round(float(ecart.mean()), 2),
               "ecart_p90_abs_min": round(float(ecart.abs().quantile(0.9)), 2),
               "ecart_une_classe_ou_moins": round(float(((d["classe_insee"] != d["classe_grille"]) & (ecart.abs() <= 2.5)).mean()), 4)}
        for s in (10, 15, 20):
            a = d["duree"] > s; b = d["duree_grille"] > s
            res[f"seuil_{s}"] = {"accord": round(float((a == b).mean()), 4),
                                 "insee_sup_grille_inf_hab": round(float(d.loc[a & ~b, "pop"].sum())),
                                 "insee_inf_grille_sup_hab": round(float(d.loc[~a & b, "pop"].sum()))}
        return res
    return {"dept": dept, "pas_m": pas, "carreaux_apparies": int(len(c)), "carreaux_total": int(len(car)),
            "non_calcules_sur_carreaux_habites": int((c["statut_grille"] == "non_calcule").sum()),
            "approches_sur_carreaux_habites": int((c["statut_grille"] == "approche").sum()),
            "statuts_grille": gr["statut"].value_counts().to_dict(),
            "global": bloc(calc), "rural": bloc(calc[~calc["urbain"]]), "urbain": bloc(calc[calc["urbain"]])}


def test_k(pts: pd.DataFrame, offres: pd.DataFrame, base: str, n: int = 600, seed: int = 1) -> dict:
    """Les K=5 plus proches à vol d'oiseau contiennent-ils le plus rapide par la route ? (K=15 en témoin)"""
    ech = pts.sample(min(n, len(pts)), random_state=seed).reset_index(drop=True)
    a = calculer(ech, offres, base, K_VOISINS); b = calculer(ech, offres, base, K_CONTROLE)
    ok = a["statut"].isin(["calcule", "approche"]) & b["statut"].isin(["calcule", "approche"])
    diff = (b.loc[ok, "duree"] < a.loc[ok, "duree"] - 0.05)
    return {"points": int(ok.sum()), "k5_pas_le_plus_rapide": int(diff.sum()), "part": round(float(diff.mean()), 4),
            "gain_median_min_quand_different": round(float((a.loc[ok, "duree"] - b.loc[ok, "duree"])[diff].median()), 2) if diff.any() else 0.0,
            "gain_max_min": round(float((a.loc[ok, "duree"] - b.loc[ok, "duree"]).max()), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dept", required=True); ap.add_argument("--bpe", required=True); ap.add_argument("--contours", required=True)
    ap.add_argument("--osrm", default="http://localhost:5000"); ap.add_argument("--pas", type=int, default=PAS_M)
    ap.add_argument("--sans-test-k", action="store_true")
    args = ap.parse_args()
    dept = args.dept.zfill(2); t0 = time.time()
    dept_l93 = contour_departement(Path(args.contours))
    offres = charger_offres(Path(args.bpe))
    zone = dept_l93.buffer(RAYON_OFFRES_KM * 1000)
    off = offres[shapely.contains_xy(zone, offres["x"].to_numpy(), offres["y"].to_numpy())].reset_index(drop=True)
    print(f"{dept} : {len(off)} cabinets D265 dans le département + {RAYON_OFFRES_KM} km (dont {int((off['dep'] == dept).sum())} dans le département)"
          + (f" · qualité XY : {off['qualite'].value_counts().to_dict()}" if off["qualite"].notna().any() else ""), flush=True)
    pts = grille(dept_l93, args.pas)
    print(f"  grille {args.pas} m : {len(pts)} points", flush=True)
    gr = calculer(pts, off, args.osrm, K_VOISINS)
    print(f"  calcul : {gr['statut'].value_counts().to_dict()} · {time.time() - t0:.0f} s", flush=True)
    GEO.mkdir(parents=True, exist_ok=True)
    gr[["lon", "lat", "duree", "snap_m", "statut", "classe"]].to_csv(GEO / f"grille_mg_{dept}.csv.gz", index=False, compression="gzip")
    poly = polygones(gr, dept_l93, args.pas)
    (GEO / f"continu_mg_{dept}.json").write_text(json.dumps(poly, separators=(",", ":")))
    ctrl = controle(gr, dept, args.pas)
    if not args.sans_test_k:
        ctrl["test_k"] = test_k(pts, off, args.osrm)
    ctrl["offres"] = {"dans_rayon": int(len(off)), "dans_departement": int((off["dep"] == dept).sum())}
    ctrl["duree_calcul_s"] = round(time.time() - t0)
    ctrl["tailles_ko"] = {f.name: round(f.stat().st_size / 1e3) for f in (GEO / f"grille_mg_{dept}.csv.gz", GEO / f"continu_mg_{dept}.json")}
    (GEO / f"controle_continu_{dept}.json").write_text(json.dumps(ctrl, indent=1, ensure_ascii=False))
    print(json.dumps(ctrl, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
