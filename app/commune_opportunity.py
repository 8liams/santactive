"""Score d'opportunité d'action à la maille communale."""

from __future__ import annotations

import pandas as pd

from .scoring import percentile_rank, to_num

# Palette chaude : plus la couleur est intense, plus la priorité d'action est élevée
_PRIORITY_LEVELS: list[tuple[float, str, str]] = [
    (80.0, "Priorité très élevée", "#A51C30"),
    (60.0, "Priorité élevée", "#D4663B"),
    (40.0, "Priorité modérée", "#E5B04A"),
    (20.0, "Priorité limitée", "#E8DFD0"),
    (0.0,  "Faible priorité", "#C9C6BA"),
]

# Besoin sanitaire · population concernée · faisabilité de déploiement
_WEIGHTS_FULL = (0.45, 0.35, 0.20)
_WEIGHTS_NO_POP = (0.65, 0.35)

_MIN_POP_FLOOR = 2_000
_MIN_POP_QUANTILE = 0.50

_NAME_PREFIXES = ("L ", "LE ", "LA ", "LES ")


def action_priority_level(score: float) -> tuple[str, str]:
    """Retourne (libellé, couleur hex) pour un score d'action 0–100."""
    if pd.isna(score):
        return "N/D", "#E8E6DD"
    for threshold, label, color in _PRIORITY_LEVELS:
        if float(score) >= threshold:
            return label, color
    return _PRIORITY_LEVELS[-1][1], _PRIORITY_LEVELS[-1][2]


def action_priority_legend_items() -> list[tuple[str, str]]:
    """Légende carte — du plus prioritaire au moins prioritaire."""
    return [(label, color) for _, label, color in _PRIORITY_LEVELS]


# Alias compatibilité interne
opportunite_level = action_priority_level
opportunity_legend_items = action_priority_legend_items


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


def _dept_medians(df: pd.DataFrame) -> dict[str, float]:
    pop = pd.to_numeric(df.get("population"), errors="coerce")
    temps = pd.to_numeric(df.get("temps_acces"), errors="coerce")
    prix = pd.to_numeric(df.get("prix_m2"), errors="coerce")
    return {
        "pop": float(pop.median()) if pop.notna().any() else 0.0,
        "temps": float(temps.median()) if temps.notna().any() else float("nan"),
        "prix": float(prix.median()) if prix is not None and prix.notna().any() else float("nan"),
    }


def estimate_impact_population(population, temps_acces) -> float | None:
    """Population observée de la commune (INSEE, via geo.api).

    L'ancienne « exposition » (0,30 à 0,75 selon le temps d'accès) n'avait pas
    de source : on affiche la population telle quelle.
    """
    pop = float(population) if pd.notna(population) else None
    return pop if pop is not None and pop > 0 else None


def build_facteur_principal(row: pd.Series, dept_medians: dict[str, float]) -> str:
    """Justification factuelle du classement d'une commune : facteurs observés seulement.

    Temps d'accès (et écart à la médiane des communes du département), population,
    prix au m² s'il est connu, rang des composantes. Aucune pathologie ni
    démographie n'est disponible à la maille communale dans les données chargées :
    on ne l'invente pas.
    """
    temps = to_num(row.get("temps_acces"))
    pop = to_num(row.get("population"))
    prix = to_num(row.get("prix_m2"))
    pct_besoin = to_num(row.get("pct_besoin"))
    pct_pop = to_num(row.get("pct_pop"))
    temps_med = to_num(dept_medians.get("temps"))
    prix_med = to_num(dept_medians.get("prix"))
    parts: list[str] = []
    if pd.notna(temps):
        if temps <= 0:
            parts.append("offre de médecine générale présente dans la commune (0 min)")
        else:
            cmp = (f", {temps / temps_med:.1f}× la médiane du département ({temps_med:.0f} min)"
                   if pd.notna(temps_med) and temps_med > 0 else "")
            parts.append(f"temps d'accès {temps:.0f} min{cmp}")
    if pd.notna(pop) and pop > 0:
        rang = f" ({pct_pop:.0f}ᵉ percentile des communes du département)" if pd.notna(pct_pop) else ""
        parts.append(f"{int(pop):,} habitants{rang}".replace(",", "\u202f"))
    if pd.notna(prix) and prix > 0:
        cmp = (f" ({(prix / prix_med - 1) * 100:+.0f}\u202f% vs département)"
               if pd.notna(prix_med) and prix_med > 0 else "")
        parts.append(f"{prix:,.0f}\u202f€/m²{cmp}".replace(",", "\u202f"))
    if pd.notna(temps) and temps > 15:
        parts.append("commune au-delà de 15 min")
    if not parts:
        return "Données communales insuffisantes pour justifier le classement."
    return " · ".join(parts[0:1]) + (" · " + " · ".join(parts[1:]) if len(parts) > 1 else "") + "."


def build_commune_opportunity_df(
    temps_df: pd.DataFrame,
    immo_df: pd.DataFrame,
    name_to_code: dict[str, str],
    *,
    code_to_name: dict[str, str] | None = None,
    population_by_code: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Calcule le score d'opportunité d'action pour chaque commune du département."""
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

    # Besoin sanitaire ← éloignement aux soins (temps d'accès)
    df["pct_besoin"] = percentile_rank(
        pd.to_numeric(df["temps_acces"], errors="coerce"),
        higher_is_better=True,
    )
    # Faisabilité ← conditions de déploiement (signal prix : territoires moins contraints)
    df["pct_faisabilite"] = percentile_rank(
        pd.to_numeric(df["prix_m2"], errors="coerce"),
        higher_is_better=False,
    )

    n_pop = int(df["population"].notna().sum()) if "population" in df.columns else 0
    n_needed = min(len(df), max(3, int(len(df) * 0.5)))
    has_pop = "population" in df.columns and n_pop >= n_needed

    if has_pop:
        df["pct_pop"] = percentile_rank(
            pd.to_numeric(df["population"], errors="coerce"),
            higher_is_better=True,
        )
        w_b, w_p, w_f = _WEIGHTS_FULL
        df["score_action"] = (
            w_b * df["pct_besoin"]
            + w_p * df["pct_pop"]
            + w_f * df["pct_faisabilite"]
        ).round(1)
        df["score_inclut_population"] = True
    else:
        w_b, w_f = _WEIGHTS_NO_POP
        df["pct_pop"] = float("nan")
        df["score_action"] = (
            w_b * df["pct_besoin"] + w_f * df["pct_faisabilite"]
        ).round(1)
        df["score_inclut_population"] = False

    # Alias rétrocompat (audio, exports internes)
    df["score_opportunite"] = df["score_action"]

    dept_medians = _dept_medians(df)
    df["impact_population"] = df.apply(
        lambda r: estimate_impact_population(r.get("population"), r.get("temps_acces")),
        axis=1,
    )
    df["facteur_principal"] = df.apply(
        lambda r: build_facteur_principal(r, dept_medians),
        axis=1,
    )

    level_data = df["score_action"].apply(
        lambda s: action_priority_level(float(s)) if pd.notna(s) else ("N/D", "#E8E6DD")
    )
    df["niveau"] = level_data.apply(lambda x: x[0])
    df["color_hex"] = level_data.apply(lambda x: x[1])
    df["value"] = df["score_action"]
    return df


def min_population_for_action_ranking(pop_series: pd.Series) -> float:
    """Seuil minimal pour le classement : max(2 000 hab., médiane départementale)."""
    clean = pd.to_numeric(pop_series, errors="coerce").dropna()
    if clean.empty:
        return float(_MIN_POP_FLOOR)
    return max(float(_MIN_POP_FLOOR), float(clean.quantile(_MIN_POP_QUANTILE)))


def top_communes_for_action(
    comm_data: pd.DataFrame,
    *,
    limit: int = 10,
) -> pd.DataFrame:
    """Top communes pour l'action — exclut les micro-communes du classement."""
    score_col = "score_action" if "score_action" in comm_data.columns else "score_opportunite"
    if comm_data.empty or score_col not in comm_data.columns:
        return pd.DataFrame()

    candidates = comm_data.dropna(subset=[score_col]).copy()
    if candidates.empty:
        return pd.DataFrame()

    if "population" in candidates.columns and candidates["population"].notna().any():
        seuil = min_population_for_action_ranking(candidates["population"])
        candidates = candidates[
            pd.to_numeric(candidates["population"], errors="coerce").fillna(0) >= seuil
        ]

    return (
        candidates.sort_values(score_col, ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )
