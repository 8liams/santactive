"""Diagnostic de static/data/professionnels.csv.gz (aucune modification).

Constat testé : le nombre de lignes par (code postal, ville, spécialité) est un
multiple du nombre de communes partageant ce code postal (référentiel
geo.api.gouv.fr), ce qui signe une jointure code postal → communes ayant
démultiplié chaque enregistrement. Une fois ce facteur retiré, il reste au
plus ~1 enregistrement par (code postal, ville, spécialité) : le fichier
indique une PRÉSENCE, pas un effectif de praticiens ni de lieux d'exercice.

Faute d'identifiant (RPPS/ADELI/FINESS), aucun dédoublonnage n'est appliqué.

Usage : python3 scripts/donnees/diagnostic_professionnels.py [--refresh]
Sortie : data_corrections/professionnels_diagnostic.csv (par département).
"""
from __future__ import annotations

import argparse
from math import gcd
from functools import reduce
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "static/data/professionnels.csv.gz"
OUT = ROOT / "data_corrections"
REF = OUT / "references" / "codes_postaux_communes_geoapi.csv"


def ref_codes_postaux(refresh: bool) -> pd.Series:
    if not REF.exists() or refresh:
        import requests

        r = requests.get("https://geo.api.gouv.fr/communes",
                         params={"fields": "code,codesPostaux", "format": "json"}, timeout=120)
        r.raise_for_status()
        rows = [(cp, c["code"]) for c in r.json() for cp in c.get("codesPostaux", [])]
        REF.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=["code_postal", "code_insee"]).to_csv(REF, index=False)
    ref = pd.read_csv(REF, dtype=str)
    return ref.groupby("code_postal")["code_insee"].nunique().rename("k_communes")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    p = pd.read_csv(SRC, sep=";", low_memory=False)
    p["code_postal"] = p["coordonnees_code_postal"].astype(str).str.zfill(5)
    p["dept"] = p["code_departement"].astype(str).str.zfill(2)
    print(f"Lignes : {len(p):,} · doublons exacts (toutes colonnes) : {p.duplicated().sum():,}")

    g = (p.groupby(["dept", "code_postal", "coordonnees_ville", "specialite_libelle"])
         .size().rename("n").reset_index()
         .merge(ref_codes_postaux(args.refresh), on="code_postal", how="left"))
    connu = g["k_communes"].notna()
    g["n_sur_k"] = g["n"] / g["k_communes"]
    print(f"Groupes (cp, ville, spécialité) : {len(g):,} · k connu : {connu.mean():.1%}")
    print(f"n multiple de k : {(g.loc[connu, 'n'] % g.loc[connu, 'k_communes'] == 0).mean():.1%}")
    print(f"n/k = 1 exactement : {(g.loc[connu, 'n_sur_k'] == 1).mean():.1%}")

    par_cp = g[connu].groupby("code_postal").agg(
        k=("k_communes", "first"), pgcd=("n", lambda x: reduce(gcd, x)))
    print(f"Codes postaux où le PGCD des comptes = k : {(par_cp['pgcd'] == par_cp['k']).mean():.1%}")

    gen = g[g["specialite_libelle"] == "Médecin généraliste"]
    diag = gen.groupby("dept").agg(
        lignes_generalistes=("n", "sum"),
        groupes_cp_ville_avec_generaliste=("n", "size"),
        facteur_moyen_demultiplication=("k_communes", "mean"),
    ).round(2)
    diag.to_csv(OUT / "professionnels_diagnostic.csv")
    print(f"Généralistes : {gen['n'].sum():,} lignes pour {len(gen):,} groupes (cp, ville)")
    print(f"Écrit : {OUT / 'professionnels_diagnostic.csv'}")


if __name__ == "__main__":
    main()
