"""Chargement des données depuis Google Drive et construction du master dataframe."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from .config import (
    APL_DEPT_DREES_PATH,
    DATA_DIR,
    APL_METHODE,
    AUTRES_PS_DREES_PATH,
    ETABS_CATEGORIES,
    ETABS_DEFINITION,
    SOURCE_EFFECTIFS,
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
    TEMPS_SOURCE,
    ACCES_INSEE_DEPT_PATH,
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


def _zd_series(s: pd.Series) -> pd.Series:
    """Version vectorisée de _zd (map sur les valeurs distinctes)."""
    uniq = {v: _zd(v) for v in s.dropna().unique()}
    return s.map(uniq)


@st.cache_data(show_spinner="Chargement des données…")
def load_all_data():
    """Charge tous les datasets et construit le master dataframe départemental.

    Retourne un tuple (master, medic, pros, immo, etabs, temps, env, patho).
    """

    # ── Population ────────────────────────────────────────────────────────────
    pop = read_dataset(POP_PATH, POP_FILE_ID, sep=";")
    pop.columns = [c.replace("\r\n", " ").strip() for c in pop.columns]
    pop["dept"] = pop["code_departement"].pipe(_zd_series)
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
    _pros_raw = read_dataset(PROS_PATH, PROS_FILE_ID, sep=";", low_memory=False,
                             usecols=["specialite_libelle", "coordonnees_ville", "code_departement"],
                             dtype={"specialite_libelle": "category", "coordonnees_ville": "category"})
    _pros_raw["dept"] = _pros_raw["code_departement"].pipe(_zd_series)
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
    # Source des effectifs : choix EXPLICITE (config.SOURCE_EFFECTIFS).
    if SOURCE_EFFECTIFS == "drees":
        drees = load_drees_ps()
        if drees["medecins"] is None:
            raise FileNotFoundError(
                "SOURCE_EFFECTIFS=drees mais static/data/drees_medecins_dept_2026.csv est absent "
                "(générer avec scripts/donnees/telecharger_drees_rpps.py)."
            )
        pros_dept = pros_dept.merge(_effectifs_drees(drees), on="dept", how="left")
        pros_dept["source_effectifs"] = "DREES RPPS 2026"
    else:  # « equipe » : comportement historique, comparaisons seulement
        for new, old in [("nb_pros", "presence_lignes_pros"), ("nb_med_gen", "presence_lignes_med_gen"),
                         ("nb_infirmiers", "presence_lignes_infirmiers"),
                         ("nb_pharmaciens", "presence_lignes_pharmaciens")]:
            pros_dept[new] = pros_dept[old]
        pros_dept["source_effectifs"] = "fichier équipe (présences, historique)"

    # ── Établissements ────────────────────────────────────────────────────────
    _etabs_raw = read_dataset(ETABS_PATH, ETABS_FILE_ID, sep=";")
    _etabs_raw["dept"] = _etabs_raw["code_departement"].pipe(_zd_series)
    _cats = ETABS_CATEGORIES
    etabs_dept = _etabs_raw.groupby("dept").agg(
        nb_etabs     =("categetab", "size"),   # toutes les lignes (Rslongue parfois vide)
        nb_hopitaux  =("categetab", lambda x: x.isin(
            ["Centre Hospitalier (C.H.)", "Centre Hospitalier Régional (C.H.R.)"]).sum()),
        # Historique : « cliniques » = établissements privés autorisés en SSR uniquement
        nb_cliniques =("categetab", lambda x: x.str.contains(
            "Clinique|privé", na=False, case=False).sum()),
        nb_structures_actuelle     =("categetab", lambda x: x.isin(_cats["actuelle"]).sum()),
        nb_structures_court_sejour =("categetab", lambda x: x.isin(_cats["court_sejour"]).sum()),
        nb_chs_psychiatrie =("categetab", lambda x: (x == "Centre Hospitalier Spécialisé lutte Maladies Mentales").sum()),
        nb_ssr_prive =("categetab", lambda x: (x == "Etablissement de santé privé autorisé en SSR").sum()),
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
    _temps_raw["dept"] = _temps_raw["code_departement"].pipe(_zd_series)
    temps_dept = _temps_raw.groupby("dept").agg(
        temps_acces_median    =("temps_acces", "median"),
        temps_acces_p90       =("temps_acces", lambda x: x.quantile(0.90)),
        temps_acces_max       =("temps_acces", "max"),
        nb_communes           =("commune",     "count"),
        nb_communes_critiques =("temps_acces", lambda x: (x > 15).sum()),
    ).reset_index()
    # Population OBSERVÉE des communes à plus de 15 min (référentiel geo.api /
    # INSEE, rapproché par libellé normalisé dans le département) : remplace
    # l'ancien forfait « part des communes × population × 0,7 ».
    temps_dept = temps_dept.merge(_pop_communes_critiques(_temps_raw), on="dept", how="left")
    # Trim : ne garder que les colonnes utiles pour la carte commune + fiche commune
    _temps_cols = ["code_departement", "commune", "temps_acces"]
    temps = _temps_raw[[c for c in _temps_cols if c in _temps_raw.columns]].copy()
    del _temps_raw

    # ── Immobilier — médiane ──────────────────────────────────────────────────
    # dtypes compacts : 900 000 transactions ; les noms de communes et codes se répètent
    # (category divise la mémoire par huit, contrainte Streamlit Cloud ~1 Go)
    _immo_raw = read_dataset(IMMO_PATH, IMMO_FILE_ID, sep=";", low_memory=False,
                             usecols=["code_departement", "commune", "prix_m2", "valeur_fonciere", "surface_m2"],
                             dtype={"code_departement": "category", "commune": "category", "prix_m2": "float32",
                                    "valeur_fonciere": "float32", "surface_m2": "float32"})
    _immo_raw["dept"] = _immo_raw["code_departement"].pipe(_zd_series)
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
            _patho_raw["dept"] = _patho_raw["dept"].astype(str).str.zfill(2)
            _g = _patho_raw.groupby(["dept", "patho_niv1", "cla_age_5"])
            patho = pd.concat([_g["Ntop"].sum(min_count=1), _g["Npop"].max()], axis=1).reset_index()
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

    # ── APL départemental : méthode explicite (config.APL_METHODE) ───────────
    # apl_dept = valeur utilisée par le score et les affichages ;
    # apl_median_dept (historique) et apl_moyen_pondere (DREES) restent disponibles.
    if Path(APL_DEPT_DREES_PATH).exists():
        _apl_p = pd.read_csv(APL_DEPT_DREES_PATH, dtype={"dept": str})
        master = master.merge(
            _apl_p[["dept", "apl_moyen_pondere", "part_pop_apl_inf_2_5",
                    "apl_p25_pond", "apl_p75_pond"]],
            on="dept", how="left")
    else:
        for _c in ["apl_moyen_pondere", "part_pop_apl_inf_2_5", "apl_p25_pond", "apl_p75_pond"]:
            master[_c] = pd.NA
    if APL_METHODE == "ponderee":
        if master["apl_moyen_pondere"].isna().all():
            raise FileNotFoundError(
                "APL_METHODE=ponderee mais static/data/apl_mg_departemental_2023.csv est absent "
                "(générer avec scripts/donnees/calculer_apl_departemental.py)."
            )
        master["apl_dept"] = pd.to_numeric(master["apl_moyen_pondere"], errors="coerce")
    else:
        master["apl_dept"] = pd.to_numeric(master["apl_median_dept"], errors="coerce")
    master["apl_methode"] = APL_METHODE

    # ── Accès routier aux généralistes — INSEE 2025 (carreaux 200 m, Metric-OSRM) ──
    # Indicateur officiel, lu en parallèle de l'indicateur interne : il alimente
    # les diagnostics et, si SANTACTIVE_TEMPS_SOURCE=insee, la dimension « temps »
    # du score (voir config.TEMPS_SOURCE et docs/EVOLUTIONS_MOTEUR.md §14).
    master = master.merge(load_acces_insee_dept(), on="dept", how="left")
    master["temps_source"] = TEMPS_SOURCE
    if TEMPS_SOURCE == "insee":
        master["temps_acces_interne_median"] = master["temps_acces_median"]
        master["temps_acces_median"] = master["acces_mg_t_med"]
    # Communes critiques (28 octobre 2026, validation William) : mesure INSEE 2025 lorsque le
    # département est couvert — communes dont le temps moyen vers un généraliste dépasse 15 min,
    # habitants des carreaux à plus de 15 min, part correspondante — ; fichier interne conservé
    # sous *_interne (audit) et utilisé en repli pour Guadeloupe et Guyane (hors champ INSEE).
    _couvert = master["acces_mg_nb_communes_sup_15"].notna()
    for _a, _b in (("nb_communes_critiques", "acces_mg_nb_communes_sup_15"),
                   ("pop_communes_critiques", "acces_mg_pop_sup_15"),
                   ("part_pop_communes_critiques", "acces_mg_part_sup_15")):
        master[f"{_a}_interne"] = master[_a]
        master[_a] = master[_b].where(_couvert, master[_a])
    master["communes_critiques_source"] = np.where(_couvert, "insee", "interne")
    # Repères nationaux du temps d'accès actif (comparaisons relatives dans le pilotage régional)
    _t = pd.to_numeric(master["temps_acces_median"], errors="coerce")
    master["temps_acces_national_med"] = float(_t.median())
    master["temps_acces_national_p75"] = float(_t.quantile(0.75))

    # ── Indicateurs dérivés ───────────────────────────────────────────────────
    # Couverture du fichier temps d'accès : communes présentes / référentiel geo.api
    master["couverture_temps"] = master["nb_communes"] / master["nb_communes_ref"].replace(0, pd.NA)
    master["population_num"] = pd.to_numeric(
        master["population"].astype(str).str.replace(" ", "").str.replace(",", "."),
        errors="coerce",
    )
    p100 = master["population_num"] / 100_000
    master["pros_pour_100k"]       = master["nb_pros"]    / p100
    master["med_gen_pour_100k"]    = master["nb_med_gen"] / p100
    master["hopitaux_pour_100k"]   = master["nb_hopitaux"] / p100
    # Définition des « structures » : choix explicite (config.ETABS_DEFINITION)
    master["nb_structures"] = master[f"nb_structures_{ETABS_DEFINITION}"]
    master["structures_pour_100k"] = master["nb_structures"] / p100
    master["structures_definition"] = ETABS_DEFINITION

    # ── Downcast master — float64 → float32 pour réduire la RAM ─────────────
    _float_cols = master.select_dtypes(include="float64").columns.tolist()
    master[_float_cols] = master[_float_cols].astype("float32")

    delais_df = load_delais_rdv()
    # medic supprimé : non utilisé nulle part (économie ~50–100 Mo)
    return master, pros, immo, etabs, temps, env, patho, delais_df, presence


def _pop_communes_critiques(temps_raw: pd.DataFrame) -> pd.DataFrame:
    """Population des communes à temps d'accès > 15 min, par département.

    Retourne pop_communes_critiques (habitants, INSEE via geo.api),
    part_pop_communes_critiques (sur la population des communes rapprochées)
    et couverture_pop_communes (part des communes du fichier temps rapprochées
    au référentiel : les non rapprochées ne sont pas comptées).
    """
    from .commune_opportunity import norm_commune_name

    cols = ["dept", "nb_communes_ref", "pop_communes_critiques",
            "part_pop_communes_critiques", "couverture_pop_communes"]
    path = DATA_DIR / "communes_population_geoapi.csv"
    if not path.exists():
        return pd.DataFrame(columns=cols)
    ref = pd.read_csv(path, dtype={"code_insee": str, "dept": str})
    ref["dept"] = ref["dept"].astype(str).str.zfill(2)
    ref["key"] = ref["nom"].map(norm_commune_name)
    nb_ref = ref.groupby("dept").size()
    ref = ref.drop_duplicates(["dept", "key"], keep=False)[["dept", "key", "population"]]
    t = temps_raw[["dept", "commune", "temps_acces"]].copy()
    t["key"] = t["commune"].map(norm_commune_name)
    m = t.merge(ref, on=["dept", "key"], how="left")
    m["population"] = pd.to_numeric(m["population"], errors="coerce")
    rows = []
    for dept, d in m.groupby("dept"):
        tot = d["population"].sum()
        crit = d.loc[d["temps_acces"] > 15, "population"]
        rows.append({
            "dept": dept,
            "nb_communes_ref": int(nb_ref.get(dept, 0)),
            "pop_communes_critiques": crit.sum(min_count=1),
            "part_pop_communes_critiques": crit.sum() / tot if tot > 0 else float("nan"),
            "couverture_pop_communes": float(d["population"].notna().mean()),
        })
    g = pd.DataFrame(rows, columns=cols)
    return g


@st.cache_data(show_spinner=False)
def load_acces_insee_dept() -> pd.DataFrame:
    """Accès routier au médecin généraliste le plus proche, par département (INSEE 2025).

    Source : Insee, base permanente des équipements 2025, distancier Metric-OSRM,
    population carroyée Filosofi (scripts/donnees/calculer_acces_insee.py).
    Colonnes : acces_mg_t_med (médiane pondérée par la population, minutes),
    acces_mg_t_moy, acces_mg_t_p90, acces_mg_part_sup_15 / _20 / _30 (parts de
    population au-delà du seuil), acces_mg_pop_sup_15 (habitants), acces_mg_nb_communes_sup_15
    (communes dont le temps moyen dépasse 15 min), acces_mg_pop (population localisée).
    Guadeloupe, Guyane et Mayotte sont hors champ (NaN).
    """
    cols = ["dept", "acces_mg_t_med", "acces_mg_t_moy", "acces_mg_t_p90", "acces_mg_part_sup_15",
            "acces_mg_part_sup_20", "acces_mg_part_sup_30", "acces_mg_pop_sup_15", "acces_mg_nb_communes_sup_15",
            "acces_mg_nb_communes_equipees", "acces_mg_pop"]
    path = Path(ACCES_INSEE_DEPT_PATH)
    if not path.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path, dtype={"dept": str})
    d = d[d["type"] == "D265"].copy()
    d["acces_mg_pop_sup_15"] = d["part_sup_15"] * d["pop"]
    d = d.rename(columns={"t_med": "acces_mg_t_med", "t_moy": "acces_mg_t_moy", "t_p90": "acces_mg_t_p90",
                          "part_sup_15": "acces_mg_part_sup_15", "part_sup_20": "acces_mg_part_sup_20",
                          "part_sup_30": "acces_mg_part_sup_30", "nb_communes_sup_15": "acces_mg_nb_communes_sup_15",
                          "nb_communes_equipees": "acces_mg_nb_communes_equipees", "pop": "acces_mg_pop"})
    return d[cols]


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
    """Contours simplifiés des départements : copie locale (static/geo, gregoiredavid/france-geojson,
    96 départements métropolitains) ; téléchargement seulement si le fichier local manque."""
    local = Path("static") / "geo" / "departements_simplifie.geojson"
    if local.exists():
        try:
            import json
            return json.loads(local.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    try:
        return requests.get(GEOJSON_URL, timeout=15).json()
    except Exception:
        return None
