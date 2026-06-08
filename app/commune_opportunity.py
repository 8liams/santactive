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

_NAME_PREFIXES = ("L ", "LE ", "LA ", "LES ")


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


def norm_commune_name(s: str) -> str:
    """Normalisation robuste des libellés communaux."""
    import unicodedata

    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    for ch in "-'.,()":
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    s = s.replace("SAINTE ", "STE ").replace("SAINT ", "ST ")
    return s


def commune_name_keys(name: str) -> list[str]:
    """Variantes de recherche pour un libellé communal."""
    base = norm_commune_name(name)
    if not base:
        return []
    keys = {base}
    for prefix in _NAME_PREFIXES:
        if base.startswith(prefix):
            keys.add(base[len(prefix):].strip())
    return list(keys)


def build_commune_code_lookup(
    geojson_features: list[dict],
) -> tuple[dict[str, str], dict[str, str]]:
    """Construit les tables nom → code INSEE et code → nom officiel."""
    name_to_code: dict[str, str] = {}
    code_to_name: dict[str, str] = {}
    for feat in geojson_features:
        nom = feat.get("properties", {}).get("nom", "")
        code = feat.get("properties", {}).get("code", "")
        if not nom or not code:
            continue
        code = str(code).zfill(5)
        code_to_name[code] = nom
        for key in commune_name_keys(nom):
            name_to_code[key] = code
    return name_to_code, code_to_name


def lookup_commune_code(name: str, name_to_code: dict[str, str]) -> str | None:
    for key in commune_name_keys(name):
        code = name_to_code.get(key)
        if code:
            return str(code).zfill(5)
    return None


def _aggregate_by_code(
    df: pd.DataFrame,
    value_col: str,
    agg: str,
    name_to_code: dict[str, str],
) -> pd.DataFrame:
    if df.empty or value_col not in df.columns:
        return pd.DataFrame(columns=["code_commune", value_col])

    work = df[["commune", value_col]].copy()
    work["code_commune"] = work["commune"].apply(
        lambda c: lookup_commune_code(c, name_to_code)
    )
    work = work.dropna(subset=["code_commune", value_col])
    if work.empty:
        return pd.DataFrame(columns=["code_commune", value_col])

    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna(subset=[value_col])
    if work.empty:
        return pd.DataFrame(columns=["code_commune", value_col])

    grouped = (
        work.groupby("code_commune", as_index=False)[value_col]
        .agg(agg)
    )
    return grouped


def build_commune_opportunity_df(
    temps_df: pd.DataFrame,
    immo_df: pd.DataFrame,
    name_to_code: dict[str, str],
    *,
    code_to_name: dict[str, str] | None = None,
    population_by_code: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Calcule le score d'opportunité pour chaque commune du département."""
    if temps_df.empty or immo_df.empty:
        return pd.DataFrame()

    temps_by_code = _aggregate_by_code(temps_df, "temps_acces", "mean", name_to_code)
    prix_by_code = _aggregate_by_code(immo_df, "prix_m2", "median", name_to_code)

    if temps_by_code.empty or prix_by_code.empty:
        return pd.DataFrame()

    df = temps_by_code.merge(prix_by_code, on="code_commune", how="inner")
    if df.empty:
        return pd.DataFrame()

    code_to_name = code_to_name or {}
    df["commune"] = df["code_commune"].map(code_to_name).fillna(df["code_commune"])

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
