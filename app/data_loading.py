"""Chargement des données depuis Google Drive et construction du master dataframe."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from .config import (
    DELAIS_RDV_PATH,
    ENV_FILE_ID,
    ETABS_FILE_ID,
    GEOJSON_URL,
    IMMO_FILE_ID,
    MEDIC_FILE_ID,
    PATHO_FILE_ID,
    POP_FILE_ID,
    PROS_FILE_ID,
    TEMPS_FILE_ID,
)


def read_drive_csv(file_id: str, **kwargs) -> pd.DataFrame:
    """Télécharge un CSV Google Drive (gère aussi les gros fichiers via gdown)."""
    import gdown

    tmp = tempfile.mktemp(suffix=".csv")
    try:
        out = gdown.download(
            f"https://drive.google.com/uc?id={file_id}",
            tmp, quiet=True,
        )
        if out is None:
            raise RuntimeError(f"gdown n'a pas pu télécharger le fichier {file_id}")
        return pd.read_csv(tmp, **kwargs)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _zd(s) -> str:
    """Zero-pad département code à 2 caractères."""
    return str(s).strip().zfill(2)


@st.cache_data(show_spinner="Chargement des données…")
def load_all_data():
    """Charge tous les datasets et construit le master dataframe départemental.

    Retourne un tuple (master, medic, pros, immo, etabs, temps, env, patho).
    """

    # ── Population ────────────────────────────────────────────────────────────
    pop = read_drive_csv(POP_FILE_ID, sep=";")
    pop.columns = [c.replace("\r\n", " ").strip() for c in pop.columns]
    pop["dept"] = pop["code_departement"].apply(_zd)
    for c in pop.columns:
        for kw, alias in [
            ("25 ans",    "pct_moins_25"),
            ("25 à 64",   "pct_25_64"),
            ("65 ans",    "pct_plus_65"),
            ("Population","population"),
            ("Densité",   "densite"),
        ]:
            if kw in c:
                pop.rename(columns={c: alias}, inplace=True)
                break
    for col in ["population", "densite", "pct_moins_25", "pct_25_64", "pct_plus_65"]:
        if col in pop.columns:
            pop[col] = pd.to_numeric(
                pop[col].astype(str).str.replace(" ", "").str.replace(",", "."),
                errors="coerce",
            )

    # ── Professionnels de santé ───────────────────────────────────────────────
    pros = read_drive_csv(PROS_FILE_ID, sep=";", low_memory=False)
    pros["dept"] = pros["code_departement"].apply(_zd)
    pros_dept = pros.groupby("dept").agg(
        nb_pros        =("specialite_libelle", "count"),
        nb_med_gen     =("specialite_libelle", lambda x: (x == "Médecin généraliste").sum()),
        nb_infirmiers  =("specialite_libelle", lambda x: (x == "Infirmier").sum()),
        nb_pharmaciens =("specialite_libelle", lambda x: (x == "Pharmacien").sum()),
    ).reset_index()

    # ── Établissements ────────────────────────────────────────────────────────
    etabs = read_drive_csv(ETABS_FILE_ID, sep=";")
    etabs["dept"] = etabs["code_departement"].apply(_zd)
    etabs_dept = etabs.groupby("dept").agg(
        nb_etabs     =("Rslongue", "count"),
        nb_hopitaux  =("categetab", lambda x: x.isin(
            ["Centre Hospitalier (C.H.)", "Centre Hospitalier Régional (C.H.R.)"]).sum()),
        nb_cliniques =("categetab", lambda x: x.str.contains(
            "Clinique|privé", na=False, case=False).sum()),
    ).reset_index()

    # ── Temps d'accès (médiane + p90, robuste aux outliers) ──────────────────
    temps = read_drive_csv(TEMPS_FILE_ID, sep=";")
    temps["dept"] = temps["code_departement"].apply(_zd)
    temps_dept = temps.groupby("dept").agg(
        temps_acces_median    =("temps_acces", "median"),
        temps_acces_p90       =("temps_acces", lambda x: x.quantile(0.90)),
        temps_acces_max       =("temps_acces", "max"),
        nb_communes           =("commune",     "count"),
        nb_communes_critiques =("temps_acces", lambda x: (x > 15).sum()),
    ).reset_index()

    # ── Immobilier — médiane ──────────────────────────────────────────────────
    immo = read_drive_csv(IMMO_FILE_ID, sep=";", low_memory=False)
    immo["dept"] = immo["code_departement"].apply(_zd)
    immo_dept = immo.groupby("dept").agg(
        prix_m2_moyen   =("prix_m2",        "median"),
        nb_transactions =("valeur_fonciere","count"),
        surface_moy     =("surface_m2",     "mean"),
    ).reset_index()

    # ── Environnement (granularité régionale — info only) ────────────────────
    env = read_drive_csv(ENV_FILE_ID, sep=";")
    env.columns = ["Code_region", "nom_region", "enviro_score"]
    env["enviro_score"] = pd.to_numeric(
        env["enviro_score"].astype(str).str.replace(",", "."), errors="coerce")

    # ── Médicaments ───────────────────────────────────────────────────────────
    medic = read_drive_csv(MEDIC_FILE_ID, sep=";")

    # ── Pathologies (jointure par code département "dept") ───────────────────
    try:
        patho = read_drive_csv(PATHO_FILE_ID, sep=";", low_memory=False)
        if "dept" in patho.columns:
            patho["dept"] = patho["dept"].astype(str).str.zfill(2)
    except Exception as e:
        patho = pd.DataFrame({"_error": [str(e)]})

    # ── Master join ───────────────────────────────────────────────────────────
    keep = ["dept", "Nom du département", "Nom de la région", "Code région",
            "population", "densite", "pct_moins_25", "pct_25_64", "pct_plus_65"]
    master = pop[[c for c in keep if c in pop.columns]].copy()
    master = master.merge(pros_dept,  on="dept", how="left")
    master = master.merge(etabs_dept, on="dept", how="left")
    master = master.merge(temps_dept, on="dept", how="left")
    master = master.merge(immo_dept,  on="dept", how="left")
    env["Code_region"] = env["Code_region"].astype(str)
    master["Code région"] = master["Code région"].astype(str)
    master = master.merge(
        env[["Code_region", "enviro_score"]],
        left_on="Code région", right_on="Code_region", how="left",
    )

    # ── APL ANCT 2023 (accessibilité potentielle localisée) — chargement inline ──
    try:
        _apl_path = Path("static") / "data" / "apl_2023.csv"
        if _apl_path.exists():
            apl_df = pd.read_csv(_apl_path, sep=";", dtype={"dept": str})
            apl_df["dept"] = apl_df["dept"].apply(
                lambda x: x if str(x) in {"2A", "2B"} or len(str(x)) == 3
                          else str(x).zfill(2)
            )
            for _c in ["apl_median_dept", "apl_p25", "apl_p75"]:
                apl_df[_c] = pd.to_numeric(apl_df[_c], errors="coerce")
            master = master.merge(apl_df, on="dept", how="left")
        else:
            master["apl_median_dept"] = pd.NA
            master["apl_p25"] = pd.NA
            master["apl_p75"] = pd.NA
    except Exception:
        master["apl_median_dept"] = pd.NA
        master["apl_p25"] = pd.NA
        master["apl_p75"] = pd.NA

    # ── Indicateurs dérivés ───────────────────────────────────────────────────
    master["population_num"] = pd.to_numeric(
        master["population"].astype(str).str.replace(" ", "").str.replace(",", "."),
        errors="coerce",
    )
    p100 = master["population_num"] / 100_000
    master["pros_pour_100k"]       = master["nb_pros"]    / p100
    master["med_gen_pour_100k"]    = master["nb_med_gen"] / p100
    master["hopitaux_pour_100k"]   = master["nb_hopitaux"] / p100
    master["structures_pour_100k"] = (master["nb_hopitaux"] + master["nb_cliniques"]) / p100

    delais_df = load_delais_rdv()
    return master, medic, pros, immo, etabs, temps, env, patho, delais_df


@st.cache_data(show_spinner=False)
def load_apl() -> pd.DataFrame:
    """Charge l'APL depuis le snapshot ANCT/DREES 2023 (local uniquement).

    Source : Observatoire des territoires, APL médecins généralistes,
    données communes 2023 agrégées à la maille département.
    Seuil désert médical DREES : APL < 2.5 consultations/an/habitant.
    Pour mettre à jour, remplacer static/data/apl_2023.csv.
    """
    path = Path("static") / "data" / "apl_2023.csv"
    if not path.exists():
        return pd.DataFrame(
            columns=["dept", "apl_median_dept", "apl_p25", "apl_p75"]
        )
    df = pd.read_csv(path, sep=";", dtype={"dept": str})
    df["dept"] = df["dept"].apply(
        lambda x: x if str(x) in {"2A", "2B"} or len(str(x)) == 3
                  else str(x).zfill(2)
    )
    for col in ["apl_median_dept", "apl_p25", "apl_p75"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def load_delais_rdv() -> pd.DataFrame:
    """Charge les délais RDV DREES par région et spécialité."""
    from pathlib import Path

    path = Path(DELAIS_RDV_PATH)
    if not path.exists():
        return pd.DataFrame(
            columns=["code_region", "region", "specialite",
                     "delai_jours_median", "delai_jours_p75"]
        )
    return pd.read_csv(path, sep=";")


@st.cache_data(show_spinner="Chargement de la carte…")
def load_geojson():
    """Télécharge le GeoJSON des départements français."""
    try:
        return requests.get(GEOJSON_URL, timeout=15).json()
    except Exception:
        return None
