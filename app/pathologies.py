"""Prévalences CNAM (cartographie des pathologies 2023) à la maille département.

Les prévalences sont BRUTES : Σ Ntop / Σ Npop sur toutes les classes d'âge.
Elles ne sont pas standardisées sur l'âge (les données chargées ne le
permettent pas proprement) : un département âgé a mécaniquement des
prévalences plus élevées. À présenter comme telles.
"""
from __future__ import annotations

import pandas as pd

PATHO_DIABETE = "Diabète"
PATHO_CARDIO = "Maladies cardioneurovasculaires"

# Une prévalence est jugée « élevée » si elle dépasse de 10 % la médiane des
# départements analysés (repère relatif, choix métier à valider).
PREV_SEUIL_RELATIF = 1.10


_AGG_CACHE: dict[int, pd.DataFrame] = {}


def patho_agg(patho: pd.DataFrame | None) -> pd.DataFrame:
    """Σ Ntop / Npop par (dept, patho_niv1), calculé une fois par DataFrame.

    Évite les ~30 copies du fichier CNAM par rendu de fiche région. La clé est
    l'identité de l'objet renvoyé par le cache Streamlit (stable par session).
    """
    if patho is None or patho.empty or not {"dept", "patho_niv1", "Ntop", "Npop"} <= set(patho.columns):
        return pd.DataFrame(columns=["Ntop", "Npop"])
    key = id(patho)
    if key not in _AGG_CACHE:
        d = patho[["dept", "patho_niv1", "Ntop", "Npop"]]
        if not (d["dept"].astype(str).str.len() >= 2).all():
            d = d.assign(dept=d["dept"].astype(str).str.zfill(2))
        _AGG_CACHE.clear()
        _AGG_CACHE[key] = d.groupby(["dept", "patho_niv1"])[["Ntop", "Npop"]].sum(min_count=1)
    return _AGG_CACHE[key]


def dept_prevalences(patho: pd.DataFrame | None, depts=None) -> pd.DataFrame:
    """Tableau dept × patho_niv1 des prévalences brutes (en %).

    `depts` restreint aux départements analysés (référentiel national
    commun : les 100 départements du master, Mayotte exclue).
    """
    if patho is None or patho.empty or not {"dept", "patho_niv1", "Ntop", "Npop"} <= set(patho.columns):
        return pd.DataFrame()
    g = patho_agg(patho)
    if depts is not None:
        keep = {str(x).zfill(2) for x in depts}
        g = g[g.index.get_level_values("dept").isin(keep)]
    prev = (g["Ntop"] / g["Npop"].where(g["Npop"] > 0) * 100).astype(float)
    return prev.unstack("patho_niv1")


def dept_prevalences_standardisees(patho: pd.DataFrame | None, depts=None) -> pd.DataFrame:
    """Prévalences standardisées sur l'âge (standardisation directe).

    Taux par classe d'âge quinquennale de chaque département, appliqués à la
    structure par âge de référence = population CNAM des départements analysés
    (Σ Npop par classe). Limite : les cellules sous secret statistique (Ntop
    manquant, < 11 patients) sont comptées à 0, ce qui sous-estime légèrement
    les petits départements ; la colonne `couverture` donne la part des poids
    d'âge effectivement couverts. Nécessite la colonne `cla_age_5`.
    """
    need = {"dept", "patho_niv1", "cla_age_5", "Ntop", "Npop"}
    if patho is None or patho.empty or not need <= set(patho.columns):
        return pd.DataFrame()
    d = patho.copy()
    d["dept"] = d["dept"].astype(str).str.zfill(2)
    if depts is not None:
        d = d[d["dept"].isin({str(x).zfill(2) for x in depts})]
    ref = d.drop_duplicates(["dept", "cla_age_5"]).groupby("cla_age_5")["Npop"].sum()
    w = ref / ref.sum()
    d["taux"] = d["Ntop"] / d["Npop"].where(d["Npop"] > 0)
    d["w"] = d["cla_age_5"].map(w)
    d["contrib"] = d["taux"].fillna(0) * d["w"]
    d["w_couv"] = d["w"].where(d["taux"].notna(), 0)
    g = d.groupby(["dept", "patho_niv1"]).agg(std=("contrib", "sum"), couv=("w_couv", "sum"))
    out = (g["std"] * 100).unstack("patho_niv1")
    out.attrs["couverture"] = g["couv"].unstack("patho_niv1")
    return out
