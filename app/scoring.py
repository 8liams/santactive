"""Scoring territorial : rang percentile + composition du score global."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import POIDS_SCORE, ZONE_LABELS


def percentile_rank(series: pd.Series, inverse: bool = False) -> pd.Series:
    """Retourne le rang percentile (0–100) de chaque valeur.

    Args:
        series: série numérique à classer.
        inverse: True si une valeur élevée doit donner un score bas
                 (par ex. temps d'accès : plus c'est long, moins c'est bon).
    """
    r = series.rank(pct=True) * 100
    return (100 - r) if inverse else r


def compute_scores(master: pd.DataFrame) -> pd.DataFrame:
    """Calcule les scores par composante et le score global.

    - Scores = rangs percentiles nationaux (0–100), donc comparatifs.
    - Score global = moyenne pondérée selon POIDS_SCORE (env exclu car régional).
    - Score global = NaN si une composante requise est manquante (pas d'imputation).
    - Zones = terciles réels (33e et 66e centiles) du score global.
    """
    master = master.copy()

    # Score accès : APL DREES (prioritaire) + temps d'accès en complément
    if "apl_median_dept" in master.columns and master["apl_median_dept"].notna().any():
        score_apl   = percentile_rank(master["apl_median_dept"], inverse=False)
        score_temps = percentile_rank(master["temps_acces_median"], inverse=True)
        # 65 % APL (mesure officielle DREES) + 35 % temps de trajet
        master["score_acces"] = score_apl * 0.65 + score_temps * 0.35
        # Fallback sur temps seul là où l'APL est manquant
        mask_no_apl = master["apl_median_dept"].isna()
        master.loc[mask_no_apl, "score_acces"] = score_temps[mask_no_apl]
    else:
        master["score_acces"] = percentile_rank(master["temps_acces_median"], inverse=True)
    master["score_pros"]  = percentile_rank(master["pros_pour_100k"])
    master["score_etabs"] = percentile_rank(master["structures_pour_100k"])
    master["score_env"]   = percentile_rank(master["enviro_score"])  # info only

    w = POIDS_SCORE
    master["score_global"] = (
        master["score_acces"] * w["acces"]
        + master["score_pros"]  * w["pros"]
        + master["score_etabs"] * w["etabs"]
    )

    # Pas d'imputation : si un indicateur requis manque → score global NaN
    required = ["temps_acces_median", "pros_pour_100k", "structures_pour_100k"]
    mask_incomplete = master[required].isna().any(axis=1)
    master.loc[mask_incomplete, "score_global"] = np.nan

    # Seuils zones = terciles réels du score global
    q33 = master["score_global"].quantile(0.33)
    q66 = master["score_global"].quantile(0.66)

    def categorize(s: float) -> str:
        if pd.isna(s):
            return "Données insuffisantes"
        if s < q33:
            return "Critique"
        if s < q66:
            return "Intermédiaire"
        return "Favorable"

    master["zone_short"] = master["score_global"].apply(categorize)

    # Libellé long avec pastille (rétrocompat avec l'ancien code)
    emoji = {"Critique": "🔴", "Intermédiaire": "🟡", "Favorable": "🟢",
             "Données insuffisantes": "⚪"}
    master["zone"] = master["zone_short"].apply(
        lambda z: f"{emoji.get(z, '⚪')} Zone {z.lower()}" if z != "Données insuffisantes"
                  else "⚪ Données insuffisantes")

    # Typologie urbaine (basée sur la densité INSEE)
    master["typologie"] = master.apply(_classifier_typologie, axis=1)

    return master


def _classifier_typologie(row: pd.Series) -> str:
    """Classifie un département par typologie urbaine (densité INSEE).

    - urbain_dense : >1000 hab/km² (Paris + métropoles ultra-denses)
    - urbain       : 250-1000
    - peri_urbain  : 80-250
    - rural        : <80
    """
    d = row.get("densite")
    if pd.isna(d):
        return "inconnu"
    d = float(d)
    if d > 1000:
        return "urbain_dense"
    if d > 250:
        return "urbain"
    if d > 80:
        return "peri_urbain"
    return "rural"


def gauge_investissement(row) -> float:
    """Jauge d'opportunité d'investissement — source unique de vérité.

    Plus le score global est bas, plus le besoin d'investissement est élevé.
    """
    sg = row.get("score_global")
    if pd.isna(sg):
        return np.nan
    return 100 - float(sg)
