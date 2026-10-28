"""Temps d'accès routier aux équipements de santé, à partir de la base INSEE
« Données sur la localisation et l'accès de la population aux équipements ».

Source : Insee, base permanente des équipements (BPE) ; distancier Metric-OSRM
(© les contributeurs d'OpenStreetMap et du projet OSRM) ; population carroyée
Filosofi. Licence Ouverte 2.0.
https://www.data.gouv.fr/datasets/donnees-sur-la-localisation-et-lacces-de-la-population-aux-equipements

Principe de la source (note méthodologique Insee) : pour chaque carreau de
200 m habité et chaque type d'équipement, durée et distance par la route vers
l'équipement le plus proche (3 candidats à vol d'oiseau, le plus rapide
retenu ; durée minimale 1 min). Guadeloupe, Guyane et Mayotte sont hors champ
(pas de population carroyée Filosofi).

Ce script agrège les carreaux à la commune et au département, pour une
sélection de types d'équipements de santé (nomenclature BPE 2025) :
  D265 médecin généraliste · D307 pharmacie · D106 urgences · D107 maternité
  D108 centre de santé · D113 maison de santé pluriprofessionnelle · D281 infirmier
Indicateurs par commune et par type :
  pop            population carroyée (Filosofi) rattachée à la commune
  t_moy          durée moyenne pondérée par la population (minutes)
  t_med          durée médiane pondérée par la population (minutes)
  part_sup_10/15/20/30   part de la population à plus de 10/15/20/30 min
  equipe         1 si au moins un carreau a son équipement le plus proche dans
                 la commune elle-même (présence d'un équipement dans la commune)
Par département (même construction, pondérée par la population) :
  t_moy, t_med, part_sup_15/20/30, pop, nb_communes, nb_communes_sup_15 (communes
  dont la durée moyenne dépasse 15 min), pop_communes_sup_15.

Les fichiers parquet régionaux (0,04 à 2,4 Go chacun, 14,5 Go au total pour le
millésime 2025) sont lus localement avec DuckDB puis peuvent être supprimés :
seules les agrégations (quelques centaines de Ko) sont conservées dans le dépôt.

Usage :
  python3 scripts/donnees/calculer_acces_insee.py --raw-dir <dossier des parquet> [--millesime 2025]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "static" / "data"
REF_DIR = ROOT / "data_corrections" / "references" / "insee_acces"

TYPES = {
    "D265": "medecin_generaliste",
    "D307": "pharmacie",
    "D106": "urgences",
    "D107": "maternite",
    "D108": "centre_sante",
    "D113": "maison_sante",
    "D281": "infirmier",
}
SEUILS = (10, 15, 20, 30)


def _wmedian(v: np.ndarray, w: np.ndarray) -> float:
    o = np.argsort(v)
    cw = np.cumsum(w[o])
    if cw[-1] <= 0:
        return float("nan")
    return float(v[o][np.searchsorted(cw, 0.5 * cw[-1])])


def lire_region(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lit un parquet régional, ne garde que les types retenus, agrège par commune
    et par département (médiane et p90 pondérées calculées sur les carreaux)."""
    con = duckdb.connect()
    types_sql = ", ".join(f"'{t}'" for t in TYPES)
    q = f"""
        SELECT depcom, typeeq_id, dep, duree, pop,
               (depcom_equipement = depcom) AS sur_place
        FROM read_parquet('{path.as_posix()}')
        WHERE typeeq_id IN ({types_sql}) AND pop IS NOT NULL AND pop > 0 AND duree IS NOT NULL
    """
    df = con.execute(q).df()
    con.close()
    rows = []
    for (depcom, typ), g in df.groupby(["depcom", "typeeq_id"], sort=False):
        d, p = g["duree"].to_numpy(float), g["pop"].to_numpy(float)
        tot = p.sum()
        row = {
            "code_insee": depcom, "type": typ, "dep": g["dep"].iloc[0],
            "pop": tot, "nb_carreaux": len(g),
            "t_moy": float((d * p).sum() / tot), "t_med": _wmedian(d, p),
            "t_max": float(d.max()),
            "equipe": int(bool(g["sur_place"].fillna(False).any())),
        }
        for s in SEUILS:
            row[f"part_sup_{s}"] = float(p[d > s].sum() / tot)
        rows.append(row)
    deps = []
    for (dep, typ), g in df.groupby(["dep", "typeeq_id"], sort=False):
        d, p = g["duree"].to_numpy(float), g["pop"].to_numpy(float)
        o = np.argsort(d); cw = np.cumsum(p[o])
        deps.append({"dept": dep, "type": typ,
                     "t_med": float(d[o][np.searchsorted(cw, 0.5 * cw[-1])]),
                     "t_p90": float(d[o][np.searchsorted(cw, 0.9 * cw[-1])])})
    return pd.DataFrame(rows), pd.DataFrame(deps)


def agreger_departements(com: pd.DataFrame) -> pd.DataFrame:
    """Agrégats départementaux pondérés par la population carroyée (par type)."""
    rows = []
    for (dep, typ), g in com.groupby(["dep", "type"]):
        p = g["pop"].to_numpy(float)
        tot = p.sum()
        row = {
            "dept": dep, "type": typ, "pop": tot, "nb_communes": len(g),
            "t_moy": float((g["t_moy"].to_numpy(float) * p).sum() / tot),
            # Médiane pondérée des médianes communales (approximation : les
            # carreaux ne sont plus disponibles à ce stade) → on recalcule
            # depuis les parts de population au-delà des seuils pour rester exact
            # sur les parts ; la médiane départementale est celle des communes
            # pondérée par la population.
            "t_med_communes": _wmedian(g["t_med"].to_numpy(float), p),
            "nb_communes_equipees": int(g["equipe"].sum()),
            "nb_communes_sup_15": int((g["t_moy"] > 15).sum()),
            "pop_communes_sup_15": float(p[g["t_moy"].to_numpy(float) > 15].sum()),
        }
        for s in SEUILS:
            row[f"part_sup_{s}"] = float((g[f"part_sup_{s}"].to_numpy(float) * p).sum() / tot)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["type", "dept"])


_CRS = {"02": "EPSG:4559", "04": "EPSG:2975"}   # Martinique, La Réunion ; métropole : EPSG:3035
_REGION_DEPT = {}   # rempli à la lecture : département → fichier régional


def extraire_carreaux(path: Path, dept: str, reg: str) -> Path:
    """Carreaux habités d'un département (généraliste, D265) → static/geo/carreaux_mg_<dept>.csv.gz.

    Colonnes : code_insee (commune du carreau), lon, lat (centre du carreau,
    WGS84), pop (habitants Filosofi rattachés), duree (minutes vers le
    généraliste le plus proche, Metric-OSRM), commune_offre (commune de cet
    équipement). Sert au simulateur d'implantation : situation actuelle par
    carreau, scénario par isochrone IGN.
    """
    from pyproj import Transformer

    con = duckdb.connect()
    df = con.execute(f"""
        SELECT depcom AS code_insee, X, Y, pop, duree, depcom_equipement AS commune_offre
        FROM read_parquet('{path.as_posix()}')
        WHERE typeeq_id = 'D265' AND dep = '{dept}' AND pop > 0 AND duree IS NOT NULL
    """).df()
    con.close()
    tr = Transformer.from_crs(_CRS.get(reg, "EPSG:3035"), "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(df["X"].to_numpy(float) + 100, df["Y"].to_numpy(float) + 100)
    out = pd.DataFrame({"code_insee": df["code_insee"], "lon": lon.round(5), "lat": lat.round(5),
                        "pop": df["pop"].round(2), "duree": df["duree"].round(2), "commune_offre": df["commune_offre"]})
    dest = ROOT / "static" / "geo" / f"carreaux_mg_{dept}.csv.gz"
    out.to_csv(dest, index=False, compression="gzip")
    print(f"   carreaux {dept} : {len(out)} · {out['pop'].sum():,.0f} hab. · {dest.stat().st_size / 1e3:.0f} Ko")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--millesime", default="2025")
    ap.add_argument("--only", nargs="*", help="fichiers à traiter (sinon tous les donnees_<millésime>_reg*.parquet)")
    ap.add_argument("--carreaux", nargs="*", help="départements dont extraire les carreaux (simulateur), ex. 18 23 93 974")
    args = ap.parse_args()
    raw = Path(args.raw_dir)
    if args.carreaux:
        import re
        for dept in args.carreaux:
            dept = dept.zfill(2)
            found = False
            for f in sorted(raw.glob(f"donnees_{args.millesime}_reg*.parquet")):
                reg = re.search(r"reg(\d+)", f.name).group(1)
                con = duckdb.connect()
                n = con.execute(f"SELECT count(*) FROM read_parquet('{f.as_posix()}') WHERE dep='{dept}' AND typeeq_id='D265'").fetchone()[0]
                con.close()
                if n:
                    extraire_carreaux(f, dept, reg); found = True; break
            if not found:
                print(f"   {dept} : absent des fichiers disponibles")
        return
    files = sorted(raw.glob(f"donnees_{args.millesime}_reg*.parquet"))
    if args.only:
        files = [f for f in files if f.name in set(args.only)]
    if not files:
        raise SystemExit(f"Aucun fichier donnees_{args.millesime}_reg*.parquet dans {raw}")
    parts, dparts, prov = [], [], []
    for f in files:
        print(f"→ {f.name} ({f.stat().st_size / 1e6:.0f} Mo)", flush=True)
        d, dd = lire_region(f)
        print(f"   {d['code_insee'].nunique()} communes · {len(d)} lignes commune×type", flush=True)
        parts.append(d); dparts.append(dd)
        prov.append({"fichier": f.name, "taille": f.stat().st_size,
                     "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    com = pd.concat(parts, ignore_index=True).sort_values(["type", "code_insee"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REF_DIR.mkdir(parents=True, exist_ok=True)
    # Fichier communal complet (tous types) dans les références ; dans static,
    # seulement le généraliste (lecture par l'application).
    com.round(3).to_csv(REF_DIR / f"acces_insee_communes_{args.millesime}.csv", index=False)
    mg = com[com["type"] == "D265"].drop(columns=["type"])
    mg.round(3).to_csv(OUT_DIR / f"acces_insee_mg_communes_{args.millesime}.csv", index=False)
    dep = agreger_departements(com).merge(pd.concat(dparts, ignore_index=True), on=["dept", "type"], how="left")
    dep.round(4).to_csv(OUT_DIR / f"acces_insee_departements_{args.millesime}.csv", index=False)
    (REF_DIR / "provenance.json").write_text(json.dumps({
        "source": "Insee, base permanente des équipements ; distancier Metric-OSRM ; population Filosofi",
        "jeu": "Données sur la localisation et l'accès de la population aux équipements",
        "url": "https://www.data.gouv.fr/datasets/donnees-sur-la-localisation-et-lacces-de-la-population-aux-equipements",
        "licence": "Licence Ouverte 2.0", "millesime": args.millesime,
        "citation": "Sources : Insee, base permanente des équipements, distancier Metric-OSRM, "
                    "© les contributeurs d'OpenStreetMap et du projet OSRM",
        "types": TYPES, "seuils_minutes": list(SEUILS),
        "champ": "France métropolitaine, Martinique, La Réunion (Guadeloupe, Guyane, Mayotte hors champ Filosofi)",
        "date_traitement": date.today().isoformat(), "fichiers": prov,
    }, indent=2, ensure_ascii=False))
    g = mg
    print(f"Communes (généraliste) : {len(g)} · population {g['pop'].sum() / 1e6:.1f} M · "
          f"part > 15 min : {(g['part_sup_15'] * g['pop']).sum() / g['pop'].sum():.1%} · "
          f"communes équipées : {int(g['equipe'].sum())}")
    print("Écrit :", OUT_DIR / f"acces_insee_mg_communes_{args.millesime}.csv",
          OUT_DIR / f"acces_insee_departements_{args.millesime}.csv")


if __name__ == "__main__":
    main()
