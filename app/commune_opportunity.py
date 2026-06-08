"""Score d'opportunité d'implantation à la maille communale."""

from __future__ import annotations

import pandas as pd

from .scoring import percentile_rank

# Couleurs issues de COLORMAPS["score"] — du plus faible au plus fort intérêt
_OPPORTUNITY_LEVELS: list[tuple[float, str, str]] = [
    (80.0, "Très forte opportunité", "#1B5E3F"),
    (60.0, "Opportunité élevée", "#A3C282"),
    (40.0, "Opportunité moyenne", "#E5B04A"),
    (20.0, "Opportunité faible", "#D4663B"),
    (0.0,  "Faible intérêt d'implantation", "#A51C30"),
]

_WEIGHTS_WITH_POP = (0.50, 0.30, 0.20)   # temps, prix inverse, population
_WEIGHTS_NO_POP = (0.60, 0.40)           # temps, prix inverse


def opportunite_level(score: float) -> tuple[str, str]:
    """Retourne (libellé, couleur hex) pour un score 0–100."""
    if pd.isna(score):
        return "—", "#E8E6DD"
    for threshold, label, color in _OPPORTUNITY_LEVELS:
        if float(score) >= threshold:
            return label, color
    return _OPPORTUNITY_LEVELS[-1][1], _OPPORTUNITY_LEVELS[-1][2]


def opportunity_legend_items() -> list[tuple[str, str]]:
    """Légende discrète (du plus fort au plus faible intérêt)."""
    return [(label, color) for _, label, color in _OPPORTUNITY_LEVELS]


def build_commune_opportunity_df(
    temps_df: pd.DataFrame,
    immo_df: pd.DataFrame,
    name_to_code: dict[str, str],
    *,
    norm_name,
    population_by_code: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Calcule le score d'opportunité pour chaque commune du département."""
    if temps_df.empty or immo_df.empty:
        return pd.DataFrame()

    temps_agg = (
        temps_df.groupby("commune", as_index=False)["temps_acces"]
        .mean()
    )
    prix_agg = (
        immo_df.groupby("commune", as_index=False)["prix_m2"]
        .median()
    )
    df = temps_agg.merge(prix_agg, on="commune", how="inner")
    if df.empty:
        return pd.DataFrame()

    df["code_commune"] = df["commune"].apply(
        lambda c: name_to_code.get(norm_name(c))
    )
    df = df.dropna(subset=["code_commune", "temps_acces", "prix_m2"])
    if df.empty:
        return pd.DataFrame()

    df["code_commune"] = df["code_commune"].astype(str).str.zfill(5)

    if population_by_code:
        df["population"] = df["code_commune"].map(population_by_code)
        df["population"] = pd.to_numeric(df["population"], errors="coerce")

    pct_temps = percentile_rank(
        pd.to_numeric(df["temps_acces"], errors="coerce"),
        higher_is_better=True,
    )
    pct_prix = percentile_rank(
        pd.to_numeric(df["prix_m2"], errors="coerce"),
        higher_is_better=False,
    )

    has_pop = (
        "population" in df.columns
        and df["population"].notna().sum() >= max(3, len(df) // 2)
    )
    if has_pop:
        pct_pop = percentile_rank(
            pd.to_numeric(df["population"], errors="coerce"),
            higher_is_better=True,
        )
        w_t, w_p, w_pop = _WEIGHTS_WITH_POP
        df["score_opportunite"] = (
            w_t * pct_temps + w_p * pct_prix + w_pop * pct_pop
        ).round(1)
    else:
        w_t, w_p = _WEIGHTS_NO_POP
        df["score_opportunite"] = (w_t * pct_temps + w_p * pct_prix).round(1)

    level_data = df["score_opportunite"].apply(
        lambda s: opportunite_level(float(s)) if pd.notna(s) else ("—", "#E8E6DD")
    )
    df["niveau"] = level_data.apply(lambda x: x[0])
    df["color_hex"] = level_data.apply(lambda x: x[1])
    df["value"] = df["score_opportunite"]
    return df
