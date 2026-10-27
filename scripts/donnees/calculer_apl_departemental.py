"""APL départemental aux médecins généralistes à partir de l'APL communal DREES.

Source : DREES, « Accessibilité potentielle localisée (APL) aux professionnels
de santé », fichier « Indicateur d'APL aux médecins généralistes.xlsx »
(millésimes 2022, 2023, 2024 ; Licence Ouverte v2.0).
https://data.drees.solidarites-sante.gouv.fr/explore/dataset/530_l-accessibilite-potentielle-localisee-apl/
Champ : omnipraticiens libéraux et salariés en centre de santé ; France hors
Mayotte. Unité : consultations, visites et téléconsultations accessibles par
an et par habitant standardisé (structure par âge).

Consigne DREES (en-tête du fichier) : « Pour calculer un APL moyen (agrégé au
niveau du département par exemple), l'APL communal doit être pondéré par la
population standardisée. Pour comptabiliser la population sous un seuil d'APL
ou calculer des quantiles, la population non standardisée doit être utilisée. »

Indicateurs produits par département :
- apl_moyen_pondere : Σ(APL_c × pop_std_c) / Σ pop_std_c  (méthode DREES) ;
- apl_median_communal : médiane simple des APL communaux (méthode actuelle du
  projet, non pondérée : chaque village pèse autant qu'une préfecture) ;
- part_pop_apl_inf_2_5 : part de la population (totale) vivant dans une
  commune d'APL < 2,5 (repère de sous-densité du zonage) ;
- apl_p25_pond / apl_p75_pond : quartiles communaux pondérés par la population
  (dispersion intra-départementale) ;
- nb_communes, nb_communes_apl_inf_2_5, population_standardisee ;
- deficit_consult_seuil_2_5 / _3_0 : Σ pop_std_c × max(0, seuil − APL_c), nombre
  de consultations accessibles manquantes pour amener chaque commune sous le
  seuil au niveau du seuil (sans redistribution de l'offre existante).

Usage : python3 scripts/donnees/calculer_apl_departemental.py [--millesime 2023]
Sortie : data_corrections/references/drees/apl_mg_departemental_<millésime>.csv
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data_corrections" / "references" / "drees"
RAW = OUT / "raw"
URL = ("https://data.drees.solidarites-sante.gouv.fr/api/explore/v2.1/catalog/datasets/"
       "530_l-accessibilite-potentielle-localisee-apl/attachments/"
       "indicateur_d_apl_aux_medecins_generalistes_xlsx")
SEUIL = 2.5


def telecharger(refresh: bool) -> Path:
    dest = RAW / "apl_medecins_generalistes.xlsx"
    if refresh or not dest.exists():
        import requests

        RAW.mkdir(parents=True, exist_ok=True)
        r = requests.get(URL, timeout=600)
        r.raise_for_status()
        dest.write_bytes(r.content)
    meta_path = OUT / "apl_provenance.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta.update({
        "url": URL, "producteur": "DREES", "licence": "Licence Ouverte v2.0 (Etalab)",
        "fichier": dest.name, "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        "date_recuperation": date.today().isoformat(),
        "millesimes_disponibles": ["2022", "2023", "2024"],
        "unite": "consultations/visites/téléconsultations accessibles par an et par habitant standardisé",
        "champ": "omnipraticiens libéraux + salariés en centre de santé ; France hors Mayotte",
    })
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return dest


def lire_communes(path: Path, millesime: str) -> pd.DataFrame:
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True)[f"APL {millesime}"]
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 10 or row[0] is None:
            continue
        rows.append(row[:8])
    df = pd.DataFrame(rows, columns=[
        "code_insee", "commune", "apl", "apl_65", "apl_62", "apl_60", "pop_std", "pop_tot"])
    for c in ["apl", "apl_65", "apl_62", "apl_60", "pop_std", "pop_tot"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["code_insee"] = df["code_insee"].astype(str).str.zfill(5)
    df["dept"] = np.where(df["code_insee"].str[:2] == "97",
                          df["code_insee"].str[:3], df["code_insee"].str[:2])
    return df


def _wquantile(v: pd.Series, w: pd.Series, q: float) -> float:
    o = np.argsort(v.values)
    cw = np.cumsum(w.values[o])
    return float(v.values[o][np.searchsorted(cw, q * cw[-1])])


def agreger(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dept, d in df.dropna(subset=["apl"]).groupby("dept"):
        rows.append({
            "dept": dept,
            "apl_moyen_pondere": float((d["apl"] * d["pop_std"]).sum() / d["pop_std"].sum()),
            "apl_median_communal": float(d["apl"].median()),
            "apl_p25_pond": _wquantile(d["apl"], d["pop_tot"], 0.25),
            "apl_p75_pond": _wquantile(d["apl"], d["pop_tot"], 0.75),
            "part_pop_apl_inf_2_5": float(d.loc[d["apl"] < SEUIL, "pop_tot"].sum() / d["pop_tot"].sum()),
            "nb_communes": int(len(d)),
            "nb_communes_apl_inf_2_5": int((d["apl"] < SEUIL).sum()),
            "population_totale": float(d["pop_tot"].sum()),
            "population_standardisee": float(d["pop_std"].sum()),
            # Déficit de consultations accessibles pour porter chaque commune
            # sous le seuil au niveau du seuil : Σ pop_std × max(0, seuil − APL).
            # Base de la simulation de capacité (ETP = déficit / activité d'un ETP).
            "deficit_consult_seuil_2_5": float((d["pop_std"] * (SEUIL - d["apl"]).clip(lower=0)).sum()),
            "deficit_consult_seuil_3_0": float((d["pop_std"] * (3.0 - d["apl"]).clip(lower=0)).sum()),
        })
    return pd.DataFrame(rows).sort_values("dept")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--millesime", default="2023")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    path = telecharger(args.refresh)
    com = lire_communes(path, args.millesime)
    print(f"Communes lues ({args.millesime}) : {len(com)} · APL manquant : {com['apl'].isna().sum()}")
    agg = agreger(com)
    out = OUT / f"apl_mg_departemental_{args.millesime}.csv"
    agg.round(4).to_csv(out, index=False)
    nat = (com["apl"] * com["pop_std"]).sum() / com["pop_std"].sum()
    part = com.loc[com["apl"] < SEUIL, "pop_tot"].sum() / com["pop_tot"].sum()
    print(f"National : APL moyen pondéré {nat:.2f} · part de population sous {SEUIL} : {part:.1%}")
    print(f"Écrit : {out}")


if __name__ == "__main__":
    main()
