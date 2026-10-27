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


def dept_prevalences(patho: pd.DataFrame | None, depts=None) -> pd.DataFrame:
    """Tableau dept × patho_niv1 des prévalences brutes (en %).

    `depts` restreint aux départements analysés (référentiel national
    commun : les 100 départements du master, Mayotte exclue).
    """
    if patho is None or patho.empty or not {"dept", "patho_niv1", "Ntop", "Npop"} <= set(patho.columns):
        return pd.DataFrame()
    d = patho.copy()
    d["dept"] = d["dept"].astype(str).str.zfill(2)
    if depts is not None:
        d = d[d["dept"].isin({str(x).zfill(2) for x in depts})]
    g = d.groupby(["dept", "patho_niv1"])[["Ntop", "Npop"]].sum(min_count=1)
    prev = (g["Ntop"] / g["Npop"].where(g["Npop"] > 0) * 100).astype(float)
    return prev.unstack("patho_niv1")
