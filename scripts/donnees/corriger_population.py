"""Diagnostic et correction proposée de static/data/population.csv.

Anomalie : pour 11 départements (21 à 29, 2A, 2B), les colonnes densité et
structure par âge sont décalées de deux lignes par rapport au code et au nom.
Origine probable : ces colonnes ont été triées avec la Corse codée « 20 »
(ordre 19, 2A, 2B, 21…), alors que codes, noms et population l'ont été avec
2A/2B après 29. La colonne population, elle, est correcte.

Méthode (aucune valeur estimée ni inventée) :
1. Référentiels officiels, mis en cache dans data_corrections/references/ :
   - surfaces communales IGN via geo.api.gouv.fr → densité = population / surface ;
   - INSEE, estimations de population au 1er janvier 2021 par département et
     âge quinquennal (estim-pop-dep-sexe-aq-1975-2023.xls, feuille 2021).
2. Détection : écart d'âge > 1,5 point ou écart de densité > 7 %.
3. Correction : permutation des VALEURS EXISTANTES du fichier selon
   l'hypothèse de tri « Corse = 20 » (pas de recopie des valeurs INSEE).
4. Validation : après permutation, les 100 départements doivent être à
   moins de 7 % de densité et 1,5 point de part d'âge des références.

Usage (depuis la racine du dépôt) :
    python3 scripts/donnees/corriger_population.py [--insee-xls CHEMIN] [--refresh]
Sorties : data_corrections/population_corrigee.csv et
          data_corrections/population_rapport.csv (avant / après).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "static/data/population.csv"
OUT = ROOT / "data_corrections"
REF = OUT / "references"
INSEE_URL = ("https://www.insee.fr/fr/statistiques/fichier/1893198/"
             "estim-pop-dep-sexe-aq-1975-2023.xls")
COLS = ["reg", "nom_reg", "dept", "nom", "pop", "densite", "pct_moins_25", "pct_25_64", "pct_plus_65"]
STAT_COLS = ["densite", "pct_moins_25", "pct_25_64", "pct_plus_65"]
# Tolérances : hors anomalie, les parts d'âge concordent avec l'INSEE à
# < 0,9 pt ; la densité diffère jusqu'à ~6 % (surfaces geo.api incluant
# lacs/glaciers : Isère, Savoie, Haute-Savoie), d'où 7 %.
TOL_DENS, TOL_AGE = 0.07, 1.5


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(
        s.astype(str).str.replace(r"\s", "", regex=True).str.replace(",", "."), errors="coerce"
    )


def ref_surfaces(depts: list[str], refresh: bool) -> pd.DataFrame:
    path = REF / "surfaces_communes_geoapi.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"dept": str})
    import requests

    rows = []
    for d in depts:
        r = requests.get(f"https://geo.api.gouv.fr/departements/{d}/communes",
                         params={"fields": "surface"}, timeout=60)
        r.raise_for_status()
        rows.append({"dept": d, "surface_km2": sum((c.get("surface") or 0) for c in r.json()) / 100})
    out = pd.DataFrame(rows)
    REF.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return out


def ref_ages(xls: Path | None, refresh: bool) -> pd.DataFrame:
    path = REF / "insee_estim_pop_2021_parts_age.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"dept": str})
    if xls is None or not xls.exists():
        sys.exit(f"Fichier INSEE requis (--insee-xls), à télécharger depuis {INSEE_URL}")
    raw = pd.read_excel(xls, "2021", header=None)  # nécessite xlrd
    body = raw.iloc[5:]
    body = body[body[0].astype(str).str.match(r"^(\d\d|2A|2B|97\d)$")]
    ages = body.iloc[:, 2:22].apply(pd.to_numeric)  # 20 classes quinquennales, « Ensemble »
    total = ages.sum(axis=1)
    out = pd.DataFrame({
        "dept": body[0].astype(str).values,
        "pop_estim_2021": total.values,
        "ref_moins_25": (ages.iloc[:, 0:5].sum(axis=1) / total * 100).values,
        "ref_25_64": (ages.iloc[:, 5:13].sum(axis=1) / total * 100).values,
        "ref_plus_65": (ages.iloc[:, 13:20].sum(axis=1) / total * 100).values,
    })
    REF.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    meta = {"source": INSEE_URL, "feuille": "2021",
            "sha256": hashlib.sha256(xls.read_bytes()).hexdigest()}
    (REF / "insee_estim_pop_2021_parts_age.json").write_text(json.dumps(meta, indent=2))
    return out


def ecarts(df: pd.DataFrame) -> pd.DataFrame:
    e = pd.DataFrame({"dept": df["dept"]})
    e["ecart_densite_pct"] = (df["densite"] / df["densite_ref"] - 1) * 100
    for c, r in [("pct_moins_25", "ref_moins_25"), ("pct_25_64", "ref_25_64"), ("pct_plus_65", "ref_plus_65")]:
        e[f"ecart_{c}_pts"] = df[c] - df[r]
    e["anormal"] = (e["ecart_densite_pct"].abs() > TOL_DENS * 100) | (
        e[[c for c in e.columns if c.endswith("_pts")]].abs().max(axis=1) > TOL_AGE
    )
    return e


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--insee-xls", type=Path)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    raw = pd.read_csv(SRC, sep=";", dtype=str)
    df = raw.copy()
    df.columns = COLS
    for c in ["pop"] + STAT_COLS:
        df[c] = _num(df[c])

    ref = ref_surfaces(df["dept"].tolist(), args.refresh).merge(
        ref_ages(args.insee_xls, args.refresh), on="dept", how="left")
    df = df.merge(ref, on="dept", how="left")
    df["densite_ref"] = df["pop"] / df["surface_km2"]

    avant = ecarts(df)
    print(f"Lignes hors tolérance avant correction : "
          f"{df.loc[avant['anormal'], 'dept'].tolist()}")

    # Hypothèse structurelle : les colonnes statistiques sont dans l'ordre des
    # codes avec la Corse triée comme « 20 » (19, 2A, 2B, 21…). La ligne k du
    # fichier porte donc les statistiques du k-ième département de cet ordre.
    # (Un appariement « au plus proche » est à proscrire : Doubs et Eure ont
    # des profils trop voisins pour être départagés par les tolérances.)
    ordre_codes = df["dept"].tolist()
    ordre_stats = sorted(ordre_codes, key=lambda c: c.replace("2A", "20A").replace("2B", "20B"))
    source = dict(zip(ordre_stats, range(len(df))))  # dept → ligne portant ses stats
    corr = df.copy()
    for i, code in enumerate(ordre_codes):
        corr.loc[i, STAT_COLS] = df.loc[source[code], STAT_COLS].values
    bloc = [i for i, c in enumerate(ordre_codes) if source[c] != i]
    for i in bloc:
        print(f"  {ordre_codes[i]:>3} {df.at[i, 'nom']:<16} ← valeurs de la ligne "
              f"{ordre_codes[source[ordre_codes[i]]]}")

    apres = ecarts(corr)
    if apres["anormal"].any():
        sys.exit("Échec de validation : " + ", ".join(corr.loc[apres["anormal"], "dept"]))
    # L'hypothèse doit améliorer CHAQUE ligne déplacée (pas seulement passer le seuil)
    err = lambda e: e["ecart_pct_plus_65_pts"].abs() + e["ecart_pct_moins_25_pts"].abs()
    pire = [ordre_codes[i] for i in bloc if err(apres).iloc[i] >= err(avant).iloc[i]]
    if pire:
        sys.exit("Hypothèse non confirmée pour : " + ", ".join(pire))
    print(f"Validation : 100/100 départements conformes (densité ±{TOL_DENS:.0%}, "
          f"âges ±{TOL_AGE} pt) ; écart d'âge réduit pour les {len(bloc)} lignes déplacées.")

    # Fichier corrigé : même format que l'original (séparateur, virgule décimale)
    out = raw.copy()
    for k, c in enumerate(STAT_COLS, start=5):
        fmt = corr[c].map(lambda v: (f"{v:.1f}".rstrip("0").rstrip(".")).replace(".", ","))
        out.iloc[bloc, k] = fmt.iloc[bloc].values
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "population_corrigee.csv", sep=";", index=False)

    rapport = df[["dept", "nom"]].copy()
    for c in STAT_COLS:
        rapport[f"{c}_avant"] = df[c]
        rapport[f"{c}_apres"] = corr[c]
    rapport["densite_ref_ign"] = df["densite_ref"].round(1)
    rapport["ref_plus_65_insee"] = df["ref_plus_65"].round(1)
    rapport["modifie"] = rapport.index.isin(bloc)
    rapport.to_csv(OUT / "population_rapport.csv", index=False)
    print(f"Écrit : {OUT / 'population_corrigee.csv'} et population_rapport.csv")


if __name__ == "__main__":
    main()
