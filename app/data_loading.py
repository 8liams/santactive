"""Chargement des données depuis Google Drive et construction du master dataframe."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from .config import (
    AUTRES_PS_DREES_PATH,
    DELAIS_RDV_PATH,
    IDEL_DREES_PATH,
    MEDECINS_DREES_PATH,
    ENV_FILE_ID,
    ENV_PATH,
    ETABS_FILE_ID,
    ETABS_PATH,
    GEOJSON_URL,
    IMMO_FILE_ID,
    IMMO_PATH,
    PATHO_FILE_ID,
    PATHO_PATH,
    POP_FILE_ID,
    POP_PATH,
    PROS_FILE_ID,
    PROS_PATH,
    TEMPS_FILE_ID,
    TEMPS_PATH,
)


def read_drive_csv(file_id: str, **kwargs) -> pd.DataFrame:
    """Télécharge un CSV Google Drive (secours si fichier local absent)."""
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


def read_dataset(local_path: Path | str, file_id: str, **kwargs) -> pd.DataFrame:
    """Lit un CSV local en priorité, sinon bascule sur Google Drive."""
    path = Path(local_path)
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path, **kwargs)
    return read_drive_csv(file_id, **kwargs)


def _zd(s) -> str:
    """Zero-pad département code à 2 caractères."""
    return str(s).strip().zfill(2)


@st.cache_data(show_spinner="Chargement des données…")
def load_all_data():
    """Charge tous les datasets et construit le master dataframe départemental.

    Retourne un tuple (master, medic, pros, immo, etabs, temps, env, patho).
    """

    # ── Population ────────────────────────────────────────────────────────────
    pop = read_dataset(POP_PATH, POP_FILE_ID, sep=";")
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
    _pros_raw = read_dataset(PROS_PATH, PROS_FILE_ID, sep=";", low_memory=False)
    _pros_raw["dept"] = _pros_raw["code_departement"].apply(_zd)
    pros_dept = _pros_raw.groupby("dept").agg(
        nb_pros        =("specialite_libelle", "count"),
        nb_med_gen     =("specialite_libelle", lambda x: (x == "Médecin généraliste").sum()),
        nb_infirmiers  =("specialite_libelle", lambda x: (x == "Infirmier").sum()),
        nb_pharmaciens =("specialite_libelle", lambda x: (x == "Pharmacien").sum()),
    ).reset_index()
    # Présence locale (jeu B) : nombre de villes du département où la
    # spécialité est recensée. Le fichier démultiplie chaque enregistrement
    # par le nombre de communes du code postal : les lignes ne sont pas des
    # effectifs, seules les présences (code postal, ville) sont exploitables.
    presence = (
        _pros_raw.groupby(["dept", "specialite_libelle"])
        .agg(nb_villes=("coordonnees_ville", "nunique"), nb_lignes=("specialite_libelle", "size"))
        .reset_index()
    )
    # Trim : ne garder que les 2 colonnes utiles en aval (reco spécialistes)
    pros = _pros_raw[["dept", "specialite_libelle"]].copy()
    del _pros_raw
    pros_dept = pros_dept.rename(columns={
        "nb_pros": "presence_lignes_pros", "nb_med_gen": "presence_lignes_med_gen",
        "nb_infirmiers": "presence_lignes_infirmiers", "nb_pharmaciens": "presence_lignes_pharmaciens",
    })
    pros_dept["source_effectifs"] = "fichier équipe (présence)"
    # Effectifs officiels (jeu A) si disponibles, sinon repli sur les lignes du
    # fichier équipe (comportement historique, à signaler dans l'UI).
    drees = load_drees_ps()
    if drees["medecins"] is not None:
        eff = _effectifs_drees(drees)
        pros_dept = pros_dept.merge(eff, on="dept", how="left")
        pros_dept["source_effectifs"] = "DREES RPPS 2026"
    else:
        for new, old in [("nb_pros", "presence_lignes_pros"), ("nb_med_gen", "presence_lignes_med_gen"),
                         ("nb_infirmiers", "presence_lignes_infirmiers"),
                         ("nb_pharmaciens", "presence_lignes_pharmaciens")]:
            pros_dept[new] = pros_dept[old]

    # ── Établissements ────────────────────────────────────────────────────────
    _etabs_raw = read_dataset(ETABS_PATH, ETABS_FILE_ID, sep=";")
    _etabs_raw["dept"] = _etabs_raw["code_departement"].apply(_zd)
    etabs_dept = _etabs_raw.groupby("dept").agg(
        nb_etabs     =("Rslongue", "count"),
        nb_hopitaux  =("categetab", lambda x: x.isin(
            ["Centre Hospitalier (C.H.)", "Centre Hospitalier Régional (C.H.R.)"]).sum()),
        nb_cliniques =("categetab", lambda x: x.str.contains(
            "Clinique|privé", na=False, case=False).sum()),
    ).reset_index()
    # Trim : ne garder que les colonnes utiles pour la carte et la fiche commune
    # Le fichier FINESS chargé nomme la commune « Ville » (pas de coordonnées)
    if "commune" not in _etabs_raw.columns and "Ville" in _etabs_raw.columns:
        _etabs_raw = _etabs_raw.rename(columns={"Ville": "commune"})
    _etabs_cols = ["code_departement", "commune", "Rslongue", "categetab", "latitude", "longitude"]
    etabs = _etabs_raw[[c for c in _etabs_cols if c in _etabs_raw.columns]].copy()
    del _etabs_raw

    # ── Temps d'accès (médiane + p90, robuste aux outliers) ──────────────────
    _temps_raw = read_dataset(TEMPS_PATH, TEMPS_FILE_ID, sep=";")
    _temps_raw["dept"] = _temps_raw["code_departement"].apply(_zd)
    temps_dept = _temps_raw.groupby("dept").agg(
        temps_acces_median    =("temps_acces", "median"),
        temps_acces_p90       =("temps_acces", lambda x: x.quantile(0.90)),
        temps_acces_max       =("temps_acces", "max"),
        nb_communes           =("commune",     "count"),
        nb_communes_critiques =("temps_acces", lambda x: (x > 15).sum()),
    ).reset_index()
    # Trim : ne garder que les colonnes utiles pour la carte commune + fiche commune
    _temps_cols = ["code_departement", "commune", "temps_acces"]
    temps = _temps_raw[[c for c in _temps_cols if c in _temps_raw.columns]].copy()
    del _temps_raw

    # ── Immobilier — médiane ──────────────────────────────────────────────────
    _immo_raw = read_dataset(IMMO_PATH, IMMO_FILE_ID, sep=";", low_memory=False)
    _immo_raw["dept"] = _immo_raw["code_departement"].apply(_zd)
    immo_dept = _immo_raw.groupby("dept").agg(
        prix_m2_moyen   =("prix_m2",        "median"),
        nb_transactions =("valeur_fonciere","count"),
        surface_moy     =("surface_m2",     "mean"),
    ).reset_index()
    # Trim : ne garder que les 3 colonnes utiles pour la carte et la fiche commune
    _immo_cols = ["code_departement", "commune", "prix_m2"]
    immo = _immo_raw[[c for c in _immo_cols if c in _immo_raw.columns]].copy()
    del _immo_raw

    # ── Environnement (granularité régionale — info only) ────────────────────
    env = read_dataset(ENV_PATH, ENV_FILE_ID, sep=";")
    env.columns = ["Code_region", "nom_region", "enviro_score"]
    env["enviro_score"] = pd.to_numeric(
        env["enviro_score"].astype(str).str.replace(",", "."), errors="coerce")

    # ── Pathologies (jointure par code département "dept") ───────────────────
    try:
        _patho_raw = read_dataset(PATHO_PATH, PATHO_FILE_ID, sep=";", low_memory=False)
        if "dept" in _patho_raw.columns:
            _patho_raw["dept"] = _patho_raw["dept"].astype(str).str.zfill(2)
        for _c in ["Ntop", "Npop"]:
            if _c in _patho_raw.columns:
                _patho_raw[_c] = pd.to_numeric(_patho_raw[_c], errors="coerce")
        # Une ligne par (dept, patho_niv1, classe d'âge). Certaines pathologies
        # de niveau 1 regroupent plusieurs codes `top` (ex. « inflammatoires ou
        # rares ou VIH » : 3 codes) qui répètent la même population Npop :
        # Npop est pris une seule fois (max), Ntop est sommé (borne haute si
        # un patient relève de plusieurs codes). Sans cela, Npop était compté
        # 3 fois et la prévalence divisée par 3.
        if {"cla_age_5", "Ntop", "Npop"} <= set(_patho_raw.columns):
            patho = (
                _patho_raw.groupby(["dept", "patho_niv1", "cla_age_5"], as_index=False)
                .agg(Ntop=("Ntop", lambda s: s.sum(min_count=1)), Npop=("Npop", "max"))
            )
        else:
            _patho_cols = ["dept", "patho_niv1", "Ntop", "Npop"]
            patho = _patho_raw[[c for c in _patho_cols if c in _patho_raw.columns]].copy()
        del _patho_raw
        # Downcast pour économiser la RAM
        for _c in ["Ntop", "Npop"]:
            if _c in patho.columns:
                patho[_c] = patho[_c].astype("float32")
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

    # ── Downcast master — float64 → float32 pour réduire la RAM ─────────────
    _float_cols = master.select_dtypes(include="float64").columns.tolist()
    master[_float_cols] = master[_float_cols].astype("float32")

    delais_df = load_delais_rdv()
    # medic supprimé : non utilisé nulle part (économie ~50–100 Mo)
    return master, pros, immo, etabs, temps, env, patho, delais_df, presence


@st.cache_data(show_spinner=False)
def load_drees_ps() -> dict:
    """Effectifs officiels DREES/RPPS par département (jeu A), si présents.

    Clés : medecins (dept, specialites, exercice, effectif, densite_drees),
    autres (profession, dept, secteur_activite, exercice, effectif,
    densite_drees), idel (dept, effectif). None si le fichier est absent.
    """
    out = {"medecins": None, "autres": None, "idel": None}
    if Path(MEDECINS_DREES_PATH).exists():
        out["medecins"] = pd.read_csv(MEDECINS_DREES_PATH, dtype={"dept": str})
    if Path(AUTRES_PS_DREES_PATH).exists():
        out["autres"] = pd.read_csv(AUTRES_PS_DREES_PATH, dtype={"dept": str})
    if Path(IDEL_DREES_PATH).exists():
        out["idel"] = pd.read_csv(IDEL_DREES_PATH, dtype={"dept": str})
    return out


def _effectifs_drees(drees: dict) -> pd.DataFrame:
    """Agrégats départementaux issus des extraits DREES (personnes, pas lieux)."""
    med = drees["medecins"]
    ens = med[med["exercice"] == "0-Ensemble"]
    # « 00-Ensemble » existe pour chaque niveau d'agrégation : on retient le total
    mg = (ens[ens["specialites"] == "01-Médecine générale"]
          .drop_duplicates("dept").set_index("dept"))
    tous = (ens[(ens["specialites"] == "00-Ensemble")
                & (ens["specialites_agregees"] == "00-Ensemble")]
            .drop_duplicates("dept").set_index("dept"))
    ville = med[(med["specialites"] == "01-Médecine générale")
                & med["exercice"].isin(["1-Libéral", "2-Mixte"])].groupby("dept")["effectif"].sum(min_count=1)
    eff = pd.DataFrame({
        "nb_med_gen": mg["effectif"],
        "med_gen_densite_drees": mg["densite_drees"],
        "nb_med_gen_ville": ville,          # libéraux + mixtes (offre de ville)
        "nb_pros": tous["effectif"],         # tous médecins (généralistes + spécialistes)
    })
    autres = drees.get("autres")
    if autres is not None:
        a = autres[(autres["secteur_activite"].astype(str).str.startswith("00"))
                   & (autres["exercice"] == "0-Ensemble")]
        piv = a.pivot_table(index="dept", columns="profession", values="effectif", aggfunc="first")
        if "pharmaciens" in piv.columns:
            eff["nb_pharmaciens"] = piv["pharmaciens"]
        if "chirurgiens_dentistes" in piv.columns:
            eff["nb_dentistes"] = piv["chirurgiens_dentistes"]
        if "sages_femmes" in piv.columns:
            eff["nb_sages_femmes"] = piv["sages_femmes"]
    idel = drees.get("idel")
    if idel is not None:
        eff["nb_infirmiers"] = idel.set_index("dept")["effectif"]  # libérales, SNDS 2023
    return eff.reset_index()


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
