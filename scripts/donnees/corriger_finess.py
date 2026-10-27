"""Diagnostic et correction proposée des codes département FINESS.

Constats (static/data/etablissements.csv.gz) :
- Guyane, La Réunion, Mayotte, Saint-Pierre-et-Miquelon, Wallis-et-Futuna
  portent un code FINESS (9C, 9D, 9E, 9J) ou altéré par un tableur (« 9,00 F »)
  au lieu du code INSEE ;
- Guadeloupe et Martinique sont codées 2A et 2B (codes de la Corse) :
  leurs établissements sont comptés dans la Corse-du-Sud et la Haute-Corse.
Règle : le code est contrôlé contre la colonne Libdepartement du MÊME fichier
(nom du département). Toute ligne incohérente est recodée d'après ce libellé.
Aucune ligne n'est créée ni supprimée ; aucune source externe n'est utilisée.

Usage : python3 scripts/donnees/corriger_finess.py
Sorties : data_corrections/etablissements_corrige.csv.gz,
          data_corrections/finess_codes_rapport.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "static/data/etablissements.csv.gz"
OUT = ROOT / "data_corrections"

POP = ROOT / "static/data/population.csv"

# Collectivités hors des 101 départements (pas dans population.csv)
HORS_DEPARTEMENTS = {"SAINT PIERRE ET MIQUELON": "975", "MAYOTTE": "976", "WALLIS ET FUTUNA": "986"}


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    for ch in "-'":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def libelle_vers_code() -> dict[str, str]:
    pop = pd.read_csv(POP, sep=";", dtype=str)
    m = {_norm(n): c for c, n in zip(pop["code_departement"], pop["Nom du département"])}
    m.update(HORS_DEPARTEMENTS)
    return m


def main() -> None:
    raw = pd.read_csv(SRC, sep=";", dtype=str)
    table = libelle_vers_code()
    attendu = raw["Libdepartement"].map(_norm).map(table)
    if attendu.isna().any():
        inconnus = sorted(raw.loc[attendu.isna(), "Libdepartement"].unique())
        raise SystemExit(f"Libellés non reconnus : {inconnus}")
    a_corriger = raw["code_departement"].str.strip() != attendu

    rapport = (
        raw.loc[a_corriger].assign(code_propose=attendu[a_corriger])
        .groupby(["code_departement", "Libdepartement", "code_propose"]).size()
        .rename("lignes").reset_index()
    )
    print(rapport.to_string(index=False))

    corr = raw.copy()
    corr.loc[a_corriger, "code_departement"] = attendu[a_corriger]

    OUT.mkdir(exist_ok=True)
    corr.to_csv(OUT / "etablissements_corrige.csv.gz", sep=";", index=False, compression="gzip")
    rapport.to_csv(OUT / "finess_codes_rapport.csv", index=False)
    print(f"{int(a_corriger.sum())} lignes recodées · lignes totales inchangées : {len(corr)}")
    print("Établissements par département DOM/Corse après correction :")
    print(corr[corr["code_departement"].isin(["2A", "2B", "971", "972", "973", "974", "976"])]
          .groupby("code_departement").size().to_string())


if __name__ == "__main__":
    main()
