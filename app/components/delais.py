"""Calcul du proxy de délai RDV par département via APL.

Méthodologie :
    La DREES (enquête 2016-2017) a établi que les délais d'attente sont
    corrélés à l'APL : plus l'APL est faible, plus les délais sont longs.
    On utilise cette relation pour estimer le délai départemental à partir
    du délai national et du ratio APL national / APL département.

    délai_estimé_dept = délai_national × (APL_médiane_nationale / APL_dept)

    Le résultat est plafonné à 3× le délai national (évite les valeurs
    aberrantes pour les DOM avec APL très bas).

    IMPORTANT : ces valeurs sont des ESTIMATIONS, pas des mesures directes.
    Les données DREES sont nationales (pas départementales) et datent de
    2016-2017. À remplacer par les données Doctolib départementales dès
    qu'elles seront disponibles en open data.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd


APL_SEUIL_DESERT = 2.5  # seuil DREES officiel désert médical


def load_delais_nationaux() -> pd.DataFrame:
    """Charge les délais DREES nationaux depuis le CSV local."""
    path = Path("static") / "data" / "delais_rdv_nationaux.csv"
    if not path.exists():
        return pd.DataFrame(
            columns=["specialite", "delai_median_jours",
                     "delai_moyen_jours", "source"]
        )
    df = pd.read_csv(path, sep=";")
    for col in ["delai_median_jours", "delai_moyen_jours"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_delais_proxy(
    dept_code: str,
    apl_dept: float,
    apl_nationale: float = 2.9,
) -> pd.DataFrame:
    """Calcule les délais estimés pour un département.

    Args:
        dept_code    : code département (pour la traçabilité)
        apl_dept     : APL médian du département (ANCT 2023)
        apl_nationale: APL médiane nationale (2.9 selon ANCT 2023)

    Returns:
        DataFrame avec colonnes :
            specialite, delai_median_jours, delai_estime_jours,
            interpretation, source
    """
    df = load_delais_nationaux()
    if df.empty or pd.isna(apl_dept) or apl_dept <= 0:
        return df

    ratio = apl_nationale / apl_dept

    # Facteur d'ajustement : plafonné à 3.0 pour éviter les aberrations
    ratio_capped = min(ratio, 3.0)

    df = df.copy()
    df["delai_estime_jours"] = (
        df["delai_median_jours"] * ratio_capped
    ).round(0).astype(int)

    # Interprétation lisible
    def _interp(row) -> str:
        nat = row["delai_median_jours"]
        est = row["delai_estime_jours"]
        diff = est - nat
        if abs(diff) <= 3:
            return "conforme à la médiane nationale"
        elif diff > 0:
            return f"+{diff} j vs médiane nationale"
        else:
            return f"{diff} j vs médiane nationale"

    df["interpretation"] = df.apply(_interp, axis=1)
    df["dept"] = dept_code
    df["apl_dept"] = apl_dept
    df["methode"] = (
        f"Estimation : délai national × "
        f"(APL nat. {apl_nationale} / APL dept {apl_dept:.1f})"
    )

    return df


def is_desert_medical(apl: float) -> bool:
    """Retourne True si le département est en désert médical (APL < 2.5)."""
    return pd.notna(apl) and float(apl) < APL_SEUIL_DESERT
