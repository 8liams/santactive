"""Population municipale et surface des communes (référentiel geo.api.gouv.fr).

Source : API Géo (Etalab / DINUM), données INSEE (population municipale du
dernier recensement en vigueur, Code officiel géographique) et IGN (surface).
Licence Ouverte 2.0. Sert à rapporter des indicateurs communaux (temps
d'accès, présence d'offre) à des populations OBSERVÉES, à la place des
coefficients forfaitaires.

Usage : python3 scripts/donnees/telecharger_communes_population.py [--refresh]
Sortie : static/data/communes_population_geoapi.csv
         (code_insee, nom, dept, population, surface_km2, codes_postaux)
         + data_corrections/references/communes_population_provenance.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "static" / "data" / "communes_population_geoapi.csv"
META = ROOT / "data_corrections" / "references" / "communes_population_provenance.json"
URL = "https://geo.api.gouv.fr/communes"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    if OUT.exists() and not args.refresh:
        print("Déjà présent :", OUT)
        return
    import requests

    r = requests.get(URL, params={"fields": "code,nom,codeDepartement,population,surface,codesPostaux",
                                  "format": "json"}, timeout=180)
    r.raise_for_status()
    rows = [{
        "code_insee": c["code"], "nom": c["nom"], "dept": c.get("codeDepartement"),
        "population": c.get("population"), "surface_km2": (c.get("surface") or 0) / 100,
        "codes_postaux": "|".join(c.get("codesPostaux") or []),
    } for c in r.json()]
    df = pd.DataFrame(rows).sort_values("code_insee")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps({
        "url": URL, "producteur": "API Géo (Etalab/DINUM) — population municipale INSEE, surface IGN",
        "licence": "Licence Ouverte 2.0", "date_recuperation": date.today().isoformat(),
        "communes": int(len(df)), "population_totale": int(df["population"].fillna(0).sum()),
        "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
    }, indent=2, ensure_ascii=False))
    print(f"{len(df)} communes · population totale {int(df['population'].fillna(0).sum()):,} · écrit : {OUT}")


if __name__ == "__main__":
    main()
