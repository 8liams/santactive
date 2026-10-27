"""Récupération et extraction des effectifs DREES/RPPS par département.

Source : DREES/OSAM, « La démographie des professionnels de santé depuis 2012 »
https://data.drees.solidarites-sante.gouv.fr/explore/dataset/la-demographie-des-professionnels-de-sante-depuis-2012/
Licence Ouverte v2.0 (Etalab). Publication des fichiers RPPS : 2 juillet 2026.

Fichiers retenus (seuls ceux utiles aux fonctionnalités de Sant'active) :
- Médecins RPPS 2012-2026 : dimension « médecins » du score (généralistes),
  tableau d'offre médicale par spécialité (14 postes), modes d'exercice ;
- Pharmaciens, Sages-femmes, Chirurgiens-dentistes RPPS 2012-2026 : tableau
  d'offre, relais de soins (faisabilité régionale) ;
- Infirmières libérales SNDS 2012-2023 : relais de soins (le RPPS n'est pas
  exploitable pour les infirmières, cf. Lisez-moi DREES).

Définitions (Lisez-moi DREES) :
- effectif = professionnels actifs occupés au 1er janvier de l'année, ayant
  au moins une activité en cours (libérale ou salariée, remplaçante ou non)
  en France métropolitaine ou DROM ; hors étudiants/internes, bénévoles, SSA.
  Chaque professionnel est compté UNE fois, au lieu de son activité la plus
  récente (personnes distinctes, pas lieux d'exercice) ;
- densité = effectif au 1er janvier N / population INSEE estimée au 1er
  janvier N, pour 100 000 habitants (population totale) ;
- « Nombre d'activités » = lieux d'exercice en cours (un médecin exerce en
  moyenne 1,4 activité) : NE PAS confondre avec l'effectif ;
- ND = moins de 10 professionnels (secret statistique) ; « . » = aucun.

Les fichiers bruts (≈120 Mo) sont mis en cache dans
data_corrections/references/drees/raw/ (ignoré par Git). Les extraits
départementaux compacts et les métadonnées de provenance sont écrits dans
data_corrections/references/drees/.

Usage : python3 scripts/donnees/telecharger_drees_rpps.py [--refresh]
Dépendance : openpyxl (lecture des .xlsx).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data_corrections" / "references" / "drees"
RAW = OUT / "raw"
API = ("https://data.drees.solidarites-sante.gouv.fr/api/explore/v2.1/catalog/datasets/"
       "la-demographie-des-professionnels-de-sante-depuis-2012/attachments/")
PAGE = ("https://data.drees.solidarites-sante.gouv.fr/explore/dataset/"
        "la-demographie-des-professionnels-de-sante-depuis-2012/")

FICHIERS = {
    "lisez_moi": ("lisez_moi_drees_demographie_des_professionnels_de_sante_pdf", "pdf"),
    "medecins": ("medecins_rpps_2012_2026_xlsx", "xlsx"),
    "pharmaciens": ("pharmaciens_rpps_2012_2026_xlsx", "xlsx"),
    "sages_femmes": ("sages_femmes_rpps_2012_2026_xlsx", "xlsx"),
    "chirurgiens_dentistes": ("chirurgiens_dentistes_rpps_2012_2026_xlsx", "xlsx"),
    "infirmieres_liberales": ("infirmieres_liberales_snds_2012_2023_xlsx", "xlsx"),
}
ANNEE_RPPS = 2026
ANNEE_IDEL = 2023


def telecharger(refresh: bool) -> dict:
    import requests

    RAW.mkdir(parents=True, exist_ok=True)
    meta = {
        "producteur": "DREES/OSAM",
        "jeu_de_donnees": PAGE,
        "licence": "Licence Ouverte v2.0 (Etalab)",
        "publication_rpps": "2026-07-02",
        "millesime_rpps": f"effectifs au 1er janvier {ANNEE_RPPS}",
        "millesime_infirmieres_liberales": f"SNDS {ANNEE_IDEL}",
        "fichiers": {},
    }
    for cle, (ident, ext) in FICHIERS.items():
        dest = RAW / f"{cle}.{ext}"
        if refresh or not dest.exists():
            r = requests.get(API + ident, timeout=600)
            r.raise_for_status()
            dest.write_bytes(r.content)
        meta["fichiers"][cle] = {
            "url": API + ident,
            "fichier": dest.name,
            "octets": dest.stat().st_size,
            "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "date_recuperation": date.today().isoformat(),
        }
    return meta


def _rows(path: Path, feuille: str, garder):
    """Itère les lignes d'une feuille (openpyxl en lecture seule) et filtre."""
    import openpyxl

    ws = openpyxl.load_workbook(path, read_only=True)[feuille]
    hdr = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            hdr = [str(c) for c in row]
            continue
        rec = dict(zip(hdr, row))
        if garder(rec):
            yield rec


def _code_dept(val: str) -> str:
    """« 001-Ain » → « 01 », « 02A-Corse-du-Sud » → « 2A », « 971-Guadeloupe » → « 971 »."""
    code = str(val).split("-", 1)[0].strip()
    code = code.lstrip("0") if len(code) == 3 and code[0] == "0" else code
    return code.zfill(2)


def _val(v):
    """ND (< 10 professionnels) → NaN ; « . » (aucun) → 0."""
    if v is None or str(v).strip() in ("ND", "nd", ""):
        return float("nan")
    if str(v).strip() == ".":
        return 0.0
    return float(v)


def extraire_medecins() -> None:
    path = RAW / "medecins.xlsx"
    def dept(r):  # exclut « 000-Ensemble » et « 999 » (COM ou étranger)
        d = str(r["departement"])
        return r["departement"] is not None and not d.startswith(("000", "999"))

    def garder(r):
        return (dept(r) and str(r["tranche_age"]).startswith("00-")
                and str(r["sexe"]).startswith("0-"))

    eff = pd.DataFrame(_rows(path, "Effectifs", garder))
    dens = pd.DataFrame(_rows(path, "Densités", garder))
    cle = ["departement", "specialites_agregees", "specialites", "exercice"]
    df = eff[cle + [f"effectif_{ANNEE_RPPS}"]].merge(
        dens[cle + [f"densite_{ANNEE_RPPS}"]], on=cle, how="outer")
    df["dept"] = df["departement"].map(_code_dept)
    df["effectif"] = df[f"effectif_{ANNEE_RPPS}"].map(_val)
    df["densite_drees"] = df[f"densite_{ANNEE_RPPS}"].map(_val)
    df = df[["dept", "departement", "specialites_agregees", "specialites", "exercice",
             "effectif", "densite_drees"]].sort_values(["dept", "specialites", "exercice"])
    df.to_csv(OUT / f"drees_medecins_dept_{ANNEE_RPPS}.csv", index=False)
    print(f"médecins : {len(df)} lignes, {df['dept'].nunique()} départements")

    act = pd.DataFrame(_rows(path, "Nombre d'activités", dept))
    act["dept"] = act["departement"].map(_code_dept)
    act["activites"] = act[f"activités_{ANNEE_RPPS}"].map(_val)
    act = act[["dept", "mode_exercice", "secteur_activite", "specialites_agregees",
               "specialites", "activites"]]
    act.to_csv(OUT / f"drees_medecins_activites_dept_{ANNEE_RPPS}.csv", index=False)
    print(f"médecins (activités / lieux d'exercice) : {len(act)} lignes")


def extraire_autres() -> None:
    frames = []
    for prof in ("pharmaciens", "sages_femmes", "chirurgiens_dentistes"):
        path = RAW / f"{prof}.xlsx"
        garder = lambda r: (r["departement"] is not None
                            and not str(r["departement"]).startswith(("000", "999"))
                            and str(r["tranche_age"]).startswith("00-")
                            and str(r["sexe"]).startswith("0-"))
        eff = pd.DataFrame(_rows(path, "Effectifs", garder))
        dens = pd.DataFrame(_rows(path, "Densités", garder))
        cle = ["departement", "secteur_activite", "exercice"]
        df = eff[cle + [f"effectif_{ANNEE_RPPS}"]].merge(
            dens[cle + [f"densite_{ANNEE_RPPS}"]], on=cle, how="outer")
        df.insert(0, "profession", prof)
        df["dept"] = df["departement"].map(_code_dept)
        df["effectif"] = df[f"effectif_{ANNEE_RPPS}"].map(_val)
        df["densite_drees"] = df[f"densite_{ANNEE_RPPS}"].map(_val)
        frames.append(df[["profession", "dept", "departement", "secteur_activite",
                          "exercice", "effectif", "densite_drees"]])
    out = pd.concat(frames)
    out.to_csv(OUT / f"drees_autres_rpps_dept_{ANNEE_RPPS}.csv", index=False)
    print(f"pharmaciens / sages-femmes / dentistes : {len(out)} lignes")

    path = RAW / "infirmieres_liberales.xlsx"
    garder = lambda r: (not str(r["departement"]).startswith("00 ")
                        and str(r["sexe"]).startswith("0") and str(r["tranche_age"]).startswith("00"))
    idel = pd.DataFrame(_rows(path, "Effectifs", garder))
    idel["dept"] = idel["departement"].map(lambda v: _code_dept(str(v).replace(" - ", "-")))
    idel["effectif"] = idel[f"effectif_{ANNEE_IDEL}"].map(_val)
    idel = idel[["dept", "departement", "effectif"]]
    idel.to_csv(OUT / f"drees_infirmieres_liberales_dept_{ANNEE_IDEL}.csv", index=False)
    print(f"infirmières libérales {ANNEE_IDEL} : {len(idel)} départements")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    meta = telecharger(args.refresh)
    (OUT / "provenance.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    extraire_medecins()
    extraire_autres()
    print(f"Écrit dans {OUT}")


if __name__ == "__main__":
    main()
