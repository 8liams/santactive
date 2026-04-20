"""Scoring Sant'active v2 — 6 dimensions, rang percentile."""
from __future__ import annotations

import numpy as np
import pandas as pd


# ── Dimensions et pondérations ────────────────────────────────────────────────
DIMENSIONS: dict[str, dict] = {
    "apl": {
        "col":    "apl_median_dept",
        "weight": 0.30,
        "hib":    True,
        "label":  "Accessibilité soins de ville (APL)",
        "source": "ANCT 2023",
    },
    "medecins": {
        "col":    "med_gen_pour_100k",
        "weight": 0.20,
        "hib":    True,
        "label":  "Densité médecins généralistes",
        "source": "RPPS janv. 2026",
    },
    "etabs": {
        "col":    "structures_pour_100k",
        "weight": 0.15,
        "hib":    True,
        "label":  "Offre hospitalière",
        "source": "FINESS mars 2026",
    },
    "temps": {
        "col":    "temps_acces_median",
        "weight": 0.20,
        "hib":    False,
        "label":  "Accessibilité physique",
        "source": "Calcul interne FINESS + INSEE",
    },
    "seniors": {
        "col":    "pct_plus_65",
        "weight": 0.10,
        "hib":    False,
        "label":  "Pression démographique (vieillissement)",
        "source": "INSEE RP 2021",
    },
    "foncier": {
        "col":    "prix_m2_moyen",
        "weight": 0.05,
        "hib":    False,
        "label":  "Contexte foncier (attractivité installation)",
        "source": "DVF 2025",
    },
}

assert abs(sum(d["weight"] for d in DIMENSIONS.values()) - 1.0) < 0.001, \
    "Les poids des dimensions doivent sommer à 1.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Normalise une série en rang percentile 0-100. NaN conservés."""
    ranks = series.rank(method="average", na_option="keep", pct=True) * 100
    if not higher_is_better:
        ranks = 100 - ranks
    return ranks


def _classifier_typologie(row: pd.Series) -> str:
    """Classifie un département par densité INSEE."""
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
    """Jauge d'opportunité d'investissement (100 - score_global)."""
    sg = row.get("score_global")
    if pd.isna(sg):
        return np.nan
    return 100 - float(sg)


# ── Calcul principal ──────────────────────────────────────────────────────────

def compute_scores(master: pd.DataFrame) -> pd.DataFrame:
    """Calcule le score Sant'active v2 pour tous les départements.

    Enrichit le DataFrame avec :
    - score_apl, score_medecins, score_etabs, score_temps,
      score_seniors, score_foncier  (0-100 par rang percentile)
    - score_global      : moyenne pondérée, renormalisée si NaN
    - score_acces       : APL 60 % + temps 40 % (sous-score)
    - score_pros        : alias score_medecins
    - rang_national     : 1 = pire, N = meilleur
    - zone_short / zone_color / zone_detail
    - nb_dimensions_ok  : nb de dimensions calculées
    - typologie
    """
    df = master.copy()

    # ── Scores par dimension ─────────────────────────────────────────────
    for dim_key, dim_cfg in DIMENSIONS.items():
        col       = dim_cfg["col"]
        hib       = dim_cfg["hib"]
        score_col = f"score_{dim_key}"

        if col not in df.columns:
            df[score_col] = np.nan
        else:
            df[score_col] = percentile_rank(
                pd.to_numeric(df[col], errors="coerce"),
                higher_is_better=hib,
            )

    # ── Score global pondéré (redistribution si NaN) ─────────────────────
    def _weighted_score(row: pd.Series) -> float:
        total_weight = 0.0
        total_score  = 0.0
        available    = 0

        for dim_key, dim_cfg in DIMENSIONS.items():
            val = row.get(f"score_{dim_key}")
            if pd.notna(val):
                total_weight += dim_cfg["weight"]
                total_score  += dim_cfg["weight"] * float(val)
                available    += 1

        if total_weight == 0 or available < 3:
            return np.nan
        return total_score / total_weight

    df["score_global"] = df.apply(_weighted_score, axis=1).round(1)

    df["nb_dimensions_ok"] = df.apply(
        lambda row: sum(
            1 for dim_key in DIMENSIONS
            if pd.notna(row.get(f"score_{dim_key}"))
        ),
        axis=1,
    )

    # ── Sous-scores pour compatibilité avec le reste du code ─────────────
    # score_acces : APL 60 % + temps 40 %
    df["score_acces"] = df.apply(
        lambda row: (
            0.6 * float(row["score_apl"]) + 0.4 * float(row["score_temps"])
            if pd.notna(row.get("score_apl")) and pd.notna(row.get("score_temps"))
            else (
                float(row["score_apl"])   if pd.notna(row.get("score_apl"))
                else float(row["score_temps"]) if pd.notna(row.get("score_temps"))
                else np.nan
            )
        ),
        axis=1,
    ).round(1)

    # score_pros = score_medecins (alias rétro-compat)
    df["score_pros"] = df["score_medecins"]

    # ── Rang national ─────────────────────────────────────────────────────
    scored_mask = df["score_global"].notna()
    df.loc[scored_mask, "rang_national"] = (
        df.loc[scored_mask, "score_global"]
        .rank(method="min", ascending=True)
        .astype(int)
    )
    df.loc[~scored_mask, "rang_national"] = np.nan
    df["nb_classes"] = int(scored_mask.sum())

    # ── Zones par terciles réels ──────────────────────────────────────────
    scores_valid = df.loc[scored_mask, "score_global"]
    p33 = float(scores_valid.quantile(0.333))
    p67 = float(scores_valid.quantile(0.667))

    def _assign_zone(row) -> tuple[str, str, str]:
        s = row.get("score_global")
        if pd.isna(s):
            return ("N/D", "#9C9A92", "Données insuffisantes")
        s = float(s)
        if s <= p33:
            return ("Critique",      "#A51C30", "Tiers inférieur national")
        elif s <= p67:
            return ("Intermédiaire", "#E8A838", "Tiers médian national")
        else:
            return ("Favorable",     "#1B5E3F", "Tiers supérieur national")

    zones = df.apply(_assign_zone, axis=1, result_type="expand")
    df["zone_short"]  = zones[0]
    df["zone_color"]  = zones[1]
    df["zone_detail"] = zones[2]

    # Libellé long rétro-compat (zone)
    emoji_map = {
        "Critique":      "🔴",
        "Intermédiaire": "🟡",
        "Favorable":     "🟢",
        "N/D":           "⚪",
    }
    df["zone"] = df["zone_short"].apply(
        lambda z: f"{emoji_map.get(z, '⚪')} Zone {z.lower()}"
        if z not in ("N/D", "Données insuffisantes")
        else "⚪ Données insuffisantes"
    )

    # ── Typologie urbaine ─────────────────────────────────────────────────
    df["typologie"] = df.apply(_classifier_typologie, axis=1)

    return df


# ── Détail par dimension (pour la fiche département) ─────────────────────────

_DIM_LABELS = {
    "apl":      "Accessibilité APL",
    "medecins": "Médecins généralistes",
    "etabs":    "Établissements hospitaliers",
    "temps":    "Accessibilité physique",
    "seniors":  "Pression démographique",
    "foncier":  "Contexte foncier",
}


def get_score_breakdown(r: pd.Series) -> list[dict]:
    """Retourne le détail des scores par dimension pour une fiche département."""
    breakdown = []
    for dim_key, dim_cfg in DIMENSIONS.items():
        score_val = r.get(f"score_{dim_key}")
        raw_val   = r.get(dim_cfg["col"])
        breakdown.append({
            "dimension": dim_key,
            "label":     _DIM_LABELS[dim_key],
            "score":     round(float(score_val), 1) if pd.notna(score_val) else None,
            "raw_value": raw_val,
            "weight":    dim_cfg["weight"],
            "hib":       dim_cfg["hib"],
        })
    return breakdown
