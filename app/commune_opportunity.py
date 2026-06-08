"""Score d'opportunité d'action à la maille communale."""

from __future__ import annotations

import pandas as pd

from .scoring import percentile_rank

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
    return {
        "pop": float(pop.median()) if pop.notna().any() else 0.0,
        "temps": float(temps.median()) if temps.notna().any() else 10.0,
    }


def estimate_impact_population(
    population: float | None,
    temps_acces: float | None,
) -> int | None:
    """Estimation prudente de la population potentiellement concernée."""
    if population is None or pd.isna(population) or float(population) <= 0:
        return None
    pop = float(population)
    exposure = 0.30
    if temps_acces is not None and pd.notna(temps_acces):
        t = float(temps_acces)
        if t > 15:
            exposure = 0.75
        elif t > 12:
            exposure = 0.60
        elif t > 10:
            exposure = 0.50
        elif t > 8:
            exposure = 0.35
    return int(pop * exposure)


def build_facteur_principal(row: pd.Series, dept_medians: dict[str, float]) -> str:
    """Phrase courte et différenciée — règles déterministes."""
    temps = row.get("temps_acces")
    pop = row.get("population")
    pct_besoin = float(row.get("pct_besoin", 50) or 50)
    pct_pop = float(row.get("pct_pop", 50) or 50)
    pct_fais = float(row.get("pct_faisabilite", 50) or 50)
    score = float(row.get("score_action", 0) or 0)

    temps_f = float(temps) if pd.notna(temps) else None
    pop_f = float(pop) if pd.notna(pop) else None
    temps_med = dept_medians.get("temps", 10.0)
    pop_med = dept_medians.get("pop", 0.0)

    candidates: list[tuple[int, str]] = []

    def _add(priority: int, phrase: str) -> None:
        candidates.append((priority, phrase))

    if temps_f is not None and temps_f > 15:
        _add(90, "Temps de trajet élevé vers les établissements de santé.")
    if temps_f is not None and temps_med > 0 and temps_f > temps_med * 1.15:
        _add(85, "Temps d'accès supérieur à la moyenne départementale.")
    if pop_f is not None and pop_med > 0 and pop_f >= pop_med * 1.2 and temps_f and temps_f > temps_med:
        _add(88, "Accès aux soins éloigné et population importante.")
    if pop_f is not None and 1_500 <= pop_f < 5_000 and temps_f and temps_f > temps_med:
        _add(70, "Commune de taille intermédiaire avec accès contraint.")
    if pop_f is not None and pop_f >= 5_000 and pct_besoin >= 55:
        _add(82, "Population importante exposée à une offre limitée.")
    if pct_besoin >= 70 and pct_pop >= 60:
        _add(86, "Forte combinaison besoin sanitaire et population concernée.")
    if pct_besoin >= 65 and pct_pop >= 50:
        _add(80, "Potentiel élevé pour une action de proximité.")
    if temps_f is not None and temps_f > 12 and pop_f and pop_f >= 2_000:
        _add(75, "Bassin de vie concerné par des difficultés d'accès.")
    if temps_f is not None and temps_med > 0 and temps_f > temps_med and pop_f and pop_med > 0 and pop_f >= pop_med * 0.8:
        _add(72, "Isolement relatif malgré un bassin de population significatif.")
    if pct_fais >= 65 and pct_besoin >= 50:
        _add(68, "Conditions favorables à une expérimentation locale.")
    if score >= 75 and pop_f and pop_f >= 3_000:
        _add(78, "Commune susceptible d'accueillir une action pilote.")
    if pct_besoin >= 55 and pct_pop < 45:
        _add(55, "Faible densité de services à proximité.")
    if pop_f is not None and pop_f >= pop_med and pct_besoin >= 45:
        _add(60, "Population concernée importante au regard du territoire.")
    if score >= 50 and score < 65:
        _add(45, "Zone à surveiller dans une logique de prévention.")
    if pct_besoin >= 60 and pct_pop >= 55 and temps_f and temps_f > 10:
        _add(77, "Commune cumulant plusieurs facteurs de vulnérabilité.")

    if not candidates:
        if temps_f is not None and temps_f > temps_med:
            return "Temps d'accès supérieur à la moyenne départementale."
        if pop_f is not None and pop_f >= pop_med:
            return "Population concernée importante au regard du territoire."
        return "Indicateurs locaux à approfondir avec les acteurs de terrain."

    candidates.sort(key=lambda x: x[0], reverse=True)
    top_priority = candidates[0][0]
    top_rules = [p for pr, p in candidates if pr == top_priority]
    code = str(row.get("code_commune", "0"))
    idx = sum(ord(c) for c in code) % len(top_rules)
    return top_rules[idx]


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
