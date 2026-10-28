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


# Lecture « besoin d'accès » : classes de temps de trajet (minutes), factuelles
_BESOIN_CLASSES: list[tuple[float, str, str]] = [
    (30.0, "Plus de 30 min", "#A51C30"),
    (15.0, "15 à 30 min", "#D4663B"),
    (10.0, "10 à 15 min", "#E5B04A"),
    (0.0,  "10 min ou moins", "#A3C282"),
]
OFFRE_SUR_PLACE = ("Offre dans la commune", "#D9E3D4")


def _offre(temps, offre=None) -> bool:
    """Présence d'un généraliste dans la commune : indicateur explicite (BPE, bool)
    ou, à défaut, convention historique du fichier interne (temps 0)."""
    if offre is not None and not (isinstance(offre, float) and pd.isna(offre)):
        return bool(offre)
    return pd.notna(temps) and float(temps) <= 0


def besoin_class(temps, offre=None) -> tuple[str, str]:
    """(libellé, couleur) de la classe de temps d'accès ; offre sur place = classe à part."""
    if pd.isna(temps):
        return "N/D", "#E8E6DD"
    t = float(temps)
    if _offre(temps, offre):
        return OFFRE_SUR_PLACE
    for seuil, label, color in _BESOIN_CLASSES:
        if t > seuil:
            return label, color
    return _BESOIN_CLASSES[-1][1], _BESOIN_CLASSES[-1][2]


def besoin_legend_items() -> list[tuple[str, str]]:
    return [(label, color) for _, label, color in _BESOIN_CLASSES] + [OFFRE_SUR_PLACE]


# Lecture « capacité » : APL communal DREES (millésime config.APL_MILLESIME ; consultations accessibles par an
# et par habitant), repère de sous-densité 2,5 — mesure théorique de capacité,
# pas une file d'attente observée.
from .config import APL_COMMUNES_PATH as _APL_PATH
_APL_CACHE: dict[str, float] | None = None
CAPACITE_LEGENDE: list[tuple[str, str]] = [
    ("Offre présente, APL < 2,5 (capacité insuffisante)", "#D4663B"),
    ("Offre présente, APL 2,5–3", "#E5B04A"),
    ("Offre présente, APL ≥ 3", "#A3C282"),
    ("Sans offre sur place, APL < 2,5", "#A51C30"),
    ("Sans offre sur place, APL ≥ 2,5", "#D9E3D4"),
]


def load_apl_communes() -> dict[str, float]:
    """APL communal (millésime actif) par code INSEE (vide si le fichier est absent)."""
    global _APL_CACHE
    if _APL_CACHE is None:
        try:
            df = pd.read_csv(_APL_PATH, dtype={"code_insee": str})
            _APL_CACHE = dict(zip(df["code_insee"].str.zfill(5), pd.to_numeric(df["apl"], errors="coerce")))
        except (OSError, ValueError, KeyError):
            _APL_CACHE = {}
    return _APL_CACHE


def capacite_class(apl, temps, offre=None) -> tuple[str, str]:
    """(libellé, couleur) de la lecture capacité pour une commune."""
    if pd.isna(apl):
        return "N/D", "#E8E6DD"
    offre = _offre(temps, offre)
    a = float(apl)
    if offre:
        if a < 2.5:
            return CAPACITE_LEGENDE[0]
        if a < 3.0:
            return CAPACITE_LEGENDE[1]
        return CAPACITE_LEGENDE[2]
    return CAPACITE_LEGENDE[3] if a < 2.5 else CAPACITE_LEGENDE[4]


# Accès routier au généraliste le plus proche, par commune — INSEE 2025 (carreaux
# 200 m, Metric-OSRM, lieu d'exercice réel BPE). Remplace l'indicateur interne pour
# la lecture communale lorsqu'il couvre le département (sinon repli sur l'interne).
_INSEE_PATH = "static/data/acces_insee_mg_communes_2025.csv"
_INSEE_CACHE: pd.DataFrame | None = None


def load_acces_insee_communes() -> pd.DataFrame:
    """code_insee, dep, temps_acces (temps moyen pondéré, min), part_sup_15, offre_sur_place, pop_localisee."""
    global _INSEE_CACHE
    if _INSEE_CACHE is None:
        try:
            df = pd.read_csv(_INSEE_PATH, dtype={"code_insee": str, "dep": str})
            _INSEE_CACHE = pd.DataFrame({
                "code_insee": df["code_insee"].str.zfill(5), "dep": df["dep"].astype(str),
                "temps_acces": pd.to_numeric(df["t_moy"], errors="coerce").round(1),
                "part_sup_15": pd.to_numeric(df["part_sup_15"], errors="coerce"),
                "offre_sur_place": df["equipe"].astype(int) == 1,
                "pop_localisee": pd.to_numeric(df["pop"], errors="coerce"),
            })
        except (OSError, ValueError, KeyError):
            _INSEE_CACHE = pd.DataFrame(columns=["code_insee", "dep", "temps_acces", "part_sup_15", "offre_sur_place", "pop_localisee"])
    return _INSEE_CACHE


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
    offre = _offre(temps, row.get("offre_sur_place"))
    if pd.notna(temps):
        if offre:
            parts.append("généraliste présent dans la commune"
                         + (f" (trajet moyen {temps:.0f} min)" if temps > 0 else ""))
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
    """Calcule le score d'opportunité d'action pour chaque commune du département.

    Temps d'accès communal : INSEE 2025 (temps moyen en voiture vers le généraliste
    le plus proche, carreaux 200 m, présence d'un généraliste = BPE) lorsque le
    département est couvert ; sinon fichier interne (0 = généraliste présent).
    ``df.attrs["source_temps"]`` vaut « insee » ou « interne »."""
    if temps_df.empty or immo_df.empty:
        return pd.DataFrame()

    temps_by_code = _aggregate_by_code(temps_df, "temps_acces", "mean", name_to_code)
    temps_by_code["offre_sur_place"] = pd.to_numeric(temps_by_code.get("temps_acces"), errors="coerce") <= 0
    source_temps = "interne"
    dept = str(temps_df["code_departement"].iloc[0]).zfill(2) if "code_departement" in temps_df.columns else ""
    insee = load_acces_insee_communes()
    if dept and not insee.empty:
        sub = insee[insee["dep"] == dept]
        if len(sub) >= max(3, 0.8 * len(temps_by_code)):
            temps_by_code = sub.rename(columns={"code_insee": "code_commune"})[
                ["code_commune", "temps_acces", "part_sup_15", "offre_sur_place", "pop_localisee"]].copy()
            source_temps = "insee"
    prix_by_code = _aggregate_by_code(immo_df, "prix_m2", "median", name_to_code)

    if temps_by_code.empty or prix_by_code.empty:
        return pd.DataFrame()

    df = temps_by_code.merge(prix_by_code, on="code_commune", how="inner")
    if df.empty:
        return pd.DataFrame()
    df.attrs["source_temps"] = source_temps

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

    # Lecture « priorité d'action » : niveau du score ; les communes qui
    # disposent déjà d'une offre (temps 0) ne sont pas classées — elles sont
    # affichées comme telles sur la carte, et exclues du Top 10.
    temps_num = pd.to_numeric(df["temps_acces"], errors="coerce")
    df["offre_sur_place"] = df["offre_sur_place"].fillna(False).astype(bool)
    level_data = df["score_action"].apply(
        lambda s: action_priority_level(float(s)) if pd.notna(s) else ("N/D", "#E8E6DD")
    )
    df["niveau"] = level_data.apply(lambda x: x[0])
    df["color_hex"] = level_data.apply(lambda x: x[1])
    sur_place = df["offre_sur_place"]
    df.loc[sur_place, "niveau"] = OFFRE_SUR_PLACE[0]
    df.loc[sur_place, "color_hex"] = OFFRE_SUR_PLACE[1]
    df["value"] = df["score_action"]
    # Lecture « besoin d'accès » : classe de temps de trajet
    besoin = [besoin_class(t, o) for t, o in zip(temps_num, df["offre_sur_place"])]
    df["besoin_label"] = [b[0] for b in besoin]
    df["besoin_color"] = [b[1] for b in besoin]
    # Lecture « capacité » : APL communal DREES (millésime actif)
    apl = load_apl_communes()
    df["apl_commune"] = df["code_commune"].astype(str).str.zfill(5).map(apl)
    cap = [capacite_class(a, t, o) for a, t, o in zip(df["apl_commune"], temps_num, df["offre_sur_place"])]
    df["capacite_label"] = [c[0] for c in cap]
    df["capacite_color"] = [c[1] for c in cap]
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
    mode: str = "priorite",
) -> pd.DataFrame:
    """Top communes, selon la lecture choisie — même règle que la carte.

    - « priorite » : score d'action décroissant (besoin 45 %, population 35 %,
      faisabilité 20 %, inchangé) ;
    - « besoin » : temps de trajet décroissant, puis population ;
    - « capacite » : communes sous le repère APL 2,5 (DREES, millésime actif), les plus
      peuplées d'abord, qu'elles aient ou non une offre sur place.
    Dans les deux premiers cas, les communes qui disposent déjà d'une offre de médecine
    générale (temps 0) ne sont pas classées : une action d'accès n'y a pas
    d'objet. Aucun seuil de population : la population est déjà un facteur du
    score, et la lecture « besoin » doit pouvoir faire remonter de petites
    communes isolées (leur population est affichée).
    """
    score_col = "score_action" if "score_action" in comm_data.columns else "score_opportunite"
    if comm_data.empty or score_col not in comm_data.columns:
        return pd.DataFrame()
    temps = pd.to_numeric(comm_data.get("temps_acces"), errors="coerce")
    if mode == "capacite":
        # Communes sous le repère APL 2,5 (avec ou sans offre), les plus peuplées d'abord
        apl = pd.to_numeric(comm_data.get("apl_commune"), errors="coerce")
        cands = comm_data[apl.notna() & (apl < 2.5)].copy()
        cands["_pop"] = pd.to_numeric(cands.get("population"), errors="coerce").fillna(0)
        return cands.sort_values(["_pop", "apl_commune"], ascending=[False, True]).drop(columns=["_pop"]).head(limit).reset_index(drop=True)
    offre = comm_data["offre_sur_place"].fillna(False).astype(bool) if "offre_sur_place" in comm_data.columns else (temps <= 0)
    candidates = comm_data[temps.notna() & ~offre].dropna(subset=[score_col]).copy()
    if candidates.empty:
        return pd.DataFrame()
    if mode == "besoin":
        candidates["_pop"] = pd.to_numeric(candidates.get("population"), errors="coerce").fillna(0)
        candidates["_t"] = pd.to_numeric(candidates["temps_acces"], errors="coerce")
        out = candidates.sort_values(["_t", "_pop"], ascending=[False, False]).drop(columns=["_pop", "_t"])
    else:
        out = candidates.sort_values(score_col, ascending=False)
    return out.head(limit).reset_index(drop=True)
