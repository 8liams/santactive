"""Priorisation régionale ARS — fragilité, impact, faisabilité, priorité d'action."""

from __future__ import annotations

import pandas as pd

from .config import PATHOS_EXCLUDED

APL_SEUIL_DESERT = 2.5

FRAG_LABELS = ("faible", "modérée", "forte", "très forte")
IMPACT_LABELS = ("limité", "moyen", "élevé", "majeur")
FAIS_LABELS = ("difficile", "à consolider", "correcte", "favorable")
PRIO_LABELS = ("à surveiller", "prioritaire", "très prioritaire", "candidat expérimentation")
TENSION_DELAIS = ("faible", "modérée", "forte", "très forte")


def _num(s, default=float("nan")) -> float:
    try:
        v = float(s)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def _signal_rank(series: pd.Series, higher_is_worse: bool) -> pd.Series:
    """Rang percentile intra-série (0–1). NaN conservés."""
    r = series.rank(pct=True, na_option="keep", method="average")
    if higher_is_worse:
        return r
    return 1.0 - r


def _weighted_mean(values: dict[str, float]) -> float:
    valid = [v for v in values.values() if pd.notna(v)]
    if len(valid) < 2:
        return float("nan")
    return sum(valid) / len(valid)


def _score_to_level(score: float, labels: tuple[str, ...]) -> str:
    if pd.isna(score):
        return labels[1]
    if score <= 0.25:
        return labels[0]
    if score <= 0.50:
        return labels[1]
    if score <= 0.75:
        return labels[2]
    return labels[3]


def _level_index(label: str, labels: tuple[str, ...]) -> int:
    try:
        return labels.index(label)
    except ValueError:
        return 1


def _patho_metrics(patho: pd.DataFrame | None, dept_codes: list[str]) -> dict[str, dict]:
    """Prévalence max et volume patients par département."""
    out: dict[str, dict] = {}
    if patho is None or patho.empty or "_error" in patho.columns:
        return out

    dp = patho.copy()
    dp["dept"] = dp["dept"].astype(str).str.zfill(2)
    dp = dp[~dp["patho_niv1"].isin(PATHOS_EXCLUDED)]

    for code in dept_codes:
        d = dp[dp["dept"] == str(code).zfill(2)]
        if d.empty:
            continue
        dg = d.groupby("patho_niv1")[["Ntop", "Npop"]].sum().reset_index()
        dg["prev"] = dg["Ntop"] / dg["Npop"].replace(0, float("nan")) * 100
        dg = dg.dropna(subset=["prev"])
        if dg.empty:
            continue
        top = dg.loc[dg["prev"].idxmax()]
        out[str(code).zfill(2)] = {
            "prev_max": float(top["prev"]),
            "patho_name": str(top["patho_niv1"]),
            "ntop": float(top["Ntop"]),
        }
    return out


def _assign_priorite(frag: str, impact: str, fais: str) -> str:
    fi = _level_index(frag, FRAG_LABELS)
    ii = _level_index(impact, IMPACT_LABELS)
    fai = _level_index(fais, FAIS_LABELS)

    if fi >= 2 and ii >= 2 and fai >= 2:
        return "candidat expérimentation"
    if fi >= 3 or (fi >= 2 and ii >= 3):
        return "très prioritaire"
    if fi >= 2 or (fi >= 1 and ii >= 2):
        return "prioritaire"
    return "à surveiller"


def _generate_raisons(row: pd.Series, patho_info: dict | None) -> list[str]:
    reasons: list[str] = []

    apl = _num(row.get("apl_median_dept"))
    if pd.notna(apl):
        if apl < APL_SEUIL_DESERT:
            reasons.append(
                f"APL de {apl:.1f}\u202f/hab. — désert médical officiel (seuil DREES\u202f: 2,5)."
            )
        elif apl < 3.0:
            reasons.append(f"APL de {apl:.1f}\u202f/hab., sous la médiane nationale (~2,9).")

    nb_crit = int(_num(row.get("nb_communes_critiques"), 0) or 0)
    if nb_crit > 0:
        label = "commune" if nb_crit == 1 else "communes"
        reasons.append(f"{nb_crit} {label} à plus de 15\u202fmin d'un établissement.")

    pct65 = _num(row.get("pct_plus_65"))
    if pd.notna(pct65) and pct65 > 22:
        reasons.append(f"{pct65:.1f}\u202f% de 65 ans et plus — pression démographique élevée.")

    temps = _num(row.get("temps_acces_median"))
    if pd.notna(temps) and temps > 12:
        reasons.append(f"Temps d'accès médian de {temps:.0f}\u202fmin vers l'établissement le plus proche.")

    med = _num(row.get("med_gen_pour_100k"))
    if pd.notna(med) and med < 90:
        reasons.append(f"{med:.0f} médecins généralistes pour 100\u202f000 habitants.")

    hop = int(_num(row.get("nb_hopitaux"), 0) or 0)
    inf = int(_num(row.get("nb_infirmiers"), 0) or 0)
    pha = int(_num(row.get("nb_pharmaciens"), 0) or 0)
    if hop > 0 and inf > 0:
        reasons.append(
            f"{hop} hôpital(aux) et {inf} infirmiers recensés — relais existants pour coordonner."
        )
    elif inf > 0 or pha > 0:
        reasons.append(f"{inf} infirmiers et {pha} pharmaciens — relais de proximité présents.")

    if patho_info and patho_info.get("prev_max", 0) > 0:
        pname = str(patho_info.get("patho_name", ""))[:45]
        reasons.append(
            f"Prévalence {patho_info['prev_max']:.1f}\u202f% — {pname}."
        )

    prix = _num(row.get("prix_m2_moyen"))
    if pd.notna(prix) and prix < 1800:
        reasons.append(f"Prix médian à {prix:.0f}\u202f€/m² — foncier accessible pour ancrer une action.")

    if len(reasons) < 3:
        zone = str(row.get("zone_short", ""))
        if zone:
            reasons.append(f"Zone {zone.lower()} au regard du score territorial global.")
    return reasons[:3]


def _generate_lecture_rapide(frag: str, impact: str, fais: str, prio: str) -> str:
    if prio == "candidat expérimentation":
        return "Bon candidat pour une expérimentation ciblée."
    if frag in ("forte", "très forte") and fais == "difficile":
        return "Besoin fort mais relais d'action limités."
    if frag in ("forte", "très forte") and impact in ("élevé", "majeur") and fais in ("correcte", "favorable"):
        return "Très fragile, impact élevé, faisabilité correcte."
    if prio == "à surveiller":
        return "Situation à surveiller, priorité moindre à court terme."
    if prio == "très prioritaire":
        return "Besoin sanitaire marqué, action publique recommandée."
    return "Territoire à traiter en coordination avec les acteurs locaux."


def _generate_synthese(row: pd.Series, frag: str, impact: str, fais: str, prio: str) -> str:
    nom = str(row.get("Nom du département", "Ce département"))
    if prio == "candidat expérimentation":
        return (
            f"{nom} combine un besoin sanitaire net, un volume de population concerné "
            f"et des relais locaux suffisants pour tester une action de prévention, "
            f"de téléexpertise ou de coordination de parcours."
        )
    if prio == "très prioritaire":
        return (
            f"{nom} requiert une attention ARS rapide\u202f: l'enjeu est élevé "
            f"et les signaux d'accès aux soins justifient un pilotage renforcé."
        )
    if frag in ("forte", "très forte") and fais == "difficile":
        return (
            f"{nom} présente une fragilité importante mais peu de relais immédiats\u202f: "
            f"privilégier coordination, télésuivi et renforts ponctuels plutôt qu'une "
            f"installation lourde."
        )
    if prio == "prioritaire":
        return (
            f"{nom} mérite d'être intégré au plan régional\u202f: une action ciblée "
            f"sur l'accès aux soins ou la prévention chronique peut y avoir un effet mesurable."
        )
    return (
        f"{nom} reste à surveiller dans la durée\u202f: les indicateurs ne justifient "
        f"pas une mobilisation immédiate, mais une veille trimestrielle est pertinente."
    )


def _densite_faisabilite_score(densite: pd.Series) -> pd.Series:
    """Score 0–1 : densité proche de la médiane régionale = plus favorable à la coordination."""
    med = densite.median()
    if pd.isna(med) or med <= 0:
        return pd.Series(0.5, index=densite.index)
    spread = max(densite.max() - med, med - densite.min(), 1.0)
    dist = (densite - med).abs() / spread
    return (1.0 - dist.clip(0, 1)).fillna(0.5)


def compute_dept_priorities(
    region_depts: pd.DataFrame,
    patho: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calcule les 4 dimensions de priorisation pour chaque département de la région."""
    df = region_depts.copy()
    dept_codes = df["dept"].astype(str).str.zfill(2).tolist()
    patho_map = _patho_metrics(patho, dept_codes)

    # ── Fragilité sanitaire ───────────────────────────────────────────────────
    frag_signals = {
        "apl":        _signal_rank(df["apl_median_dept"], higher_is_worse=False),
        "acces":      _signal_rank(df["score_acces"], higher_is_worse=False),
        "med":        _signal_rank(df["med_gen_pour_100k"], higher_is_worse=False),
        "etabs":      _signal_rank(df["structures_pour_100k"], higher_is_worse=False),
        "communes":   _signal_rank(df["nb_communes_critiques"], higher_is_worse=True),
        "seniors":    _signal_rank(df["pct_plus_65"], higher_is_worse=True),
    }
    df["_frag_score"] = df.index.map(
        lambda i: _weighted_mean({k: _num(v.iloc[i]) for k, v in frag_signals.items()})
    )
    desert_bonus = df["apl_median_dept"].apply(
        lambda x: 0.12 if pd.notna(x) and float(x) < APL_SEUIL_DESERT else 0.0
    )
    df["_frag_score"] = (df["_frag_score"].fillna(0.5) + desert_bonus).clip(0, 1)

    # ── Impact potentiel ──────────────────────────────────────────────────────
    pop = pd.to_numeric(df["population_num"], errors="coerce")
    pct65 = pd.to_numeric(df["pct_plus_65"], errors="coerce")
    seniors = pop * pct65 / 100.0

    prev_max = df["dept"].astype(str).str.zfill(2).map(
        lambda c: patho_map.get(c, {}).get("prev_max", float("nan"))
    )
    ntop = df["dept"].astype(str).str.zfill(2).map(
        lambda c: patho_map.get(c, {}).get("ntop", float("nan"))
    )

    impact_signals = {
        "pop":      _signal_rank(pop, higher_is_worse=True),
        "seniors":  _signal_rank(seniors, higher_is_worse=True),
        "communes": _signal_rank(df["nb_communes_critiques"], higher_is_worse=True),
        "patho":    _signal_rank(prev_max, higher_is_worse=True),
        "patients": _signal_rank(ntop, higher_is_worse=True),
    }
    df["_impact_score"] = df.index.map(
        lambda i: _weighted_mean({k: _num(v.iloc[i]) for k, v in impact_signals.items()})
    )

    # ── Faisabilité d'action ──────────────────────────────────────────────────
    relais = (
        pd.to_numeric(df.get("nb_hopitaux"), errors="coerce").fillna(0)
        + pd.to_numeric(df.get("nb_cliniques"), errors="coerce").fillna(0)
    )
    soignants = (
        pd.to_numeric(df.get("nb_infirmiers"), errors="coerce").fillna(0)
        + pd.to_numeric(df.get("nb_pharmaciens"), errors="coerce").fillna(0)
    )

    fais_signals = {
        "relais":   _signal_rank(relais, higher_is_worse=True),
        "soignants": _signal_rank(soignants, higher_is_worse=True),
        "etabs":    _signal_rank(df["structures_pour_100k"], higher_is_worse=True),
        "temps":    _signal_rank(df["temps_acces_median"], higher_is_worse=False),
        "prix":     _signal_rank(df["prix_m2_moyen"], higher_is_worse=False),
        "densite":  _densite_faisabilite_score(pd.to_numeric(df["densite"], errors="coerce")),
    }
    df["_fais_score"] = df.index.map(
        lambda i: _weighted_mean({k: _num(v.iloc[i]) for k, v in fais_signals.items()})
    )

    # ── Niveaux lisibles ────────────────────────────────────────────────────────
    df["fragilite"] = df["_frag_score"].apply(lambda s: _score_to_level(s, FRAG_LABELS))
    df["impact"] = df["_impact_score"].apply(lambda s: _score_to_level(s, IMPACT_LABELS))
    df["faisabilite"] = df["_fais_score"].apply(lambda s: _score_to_level(s, FAIS_LABELS))
    df["priorite"] = df.apply(
        lambda r: _assign_priorite(r["fragilite"], r["impact"], r["faisabilite"]),
        axis=1,
    )

    prio_order = {p: i for i, p in enumerate(reversed(PRIO_LABELS))}
    df["_prio_sort"] = df["priorite"].map(lambda p: prio_order.get(p, 0))
    sorted_idx = df.sort_values(
        ["_prio_sort", "_frag_score", "_impact_score"],
        ascending=[False, False, False],
    ).index
    rank_map = {idx: r + 1 for r, idx in enumerate(sorted_idx)}
    df["priorite_rang"] = df.index.map(rank_map)

    df["lecture_rapide"] = df.apply(
        lambda r: _generate_lecture_rapide(
            r["fragilite"], r["impact"], r["faisabilite"], r["priorite"]
        ),
        axis=1,
    )
    df["raisons"] = df.apply(
        lambda r: _generate_raisons(
            r, patho_map.get(str(r["dept"]).zfill(2))
        ),
        axis=1,
    )
    df["synthese"] = df.apply(
        lambda r: _generate_synthese(
            r, r["fragilite"], r["impact"], r["faisabilite"], r["priorite"]
        ),
        axis=1,
    )

    return df.sort_values("priorite_rang").reset_index(drop=True)


def compute_region_summary(
    priorities: pd.DataFrame,
    region_depts: pd.DataFrame,
    delais_region: pd.DataFrame | None = None,
) -> dict:
    """Résumé régional pour le bandeau supérieur du bloc."""
    if priorities.empty:
        return {
            "dept_top": "—",
            "nb_prioritaires": 0,
            "nb_experimentation": 0,
            "tension_principale": "Données insuffisantes pour identifier une tension dominante.",
        }

    top = priorities.iloc[0]
    nb_prio = int(
        priorities["priorite"].isin(["prioritaire", "très prioritaire"]).sum()
    )
    nb_exp = int((priorities["priorite"] == "candidat expérimentation").sum())

    apl_med_reg = region_depts["apl_median_dept"].median()
    nb_desert = int(
        (pd.to_numeric(region_depts["apl_median_dept"], errors="coerce") < APL_SEUIL_DESERT).sum()
    )
    nb_communes = int(
        pd.to_numeric(region_depts["nb_communes_critiques"], errors="coerce").fillna(0).sum()
    )
    pct65_med = region_depts["pct_plus_65"].median()

    tension = "disparités d'accès aux soins entre départements"
    if nb_desert >= max(1, len(region_depts) // 3):
        tension = "accès aux soins de ville (APL) insuffisant sur plusieurs départements"
    elif nb_communes >= 10:
        tension = "isolement géographique de communes éloignées des établissements"
    elif pd.notna(pct65_med) and pct65_med > 22:
        tension = "vieillissement démographique et pression sur les parcours de soins"
    elif delais_region is not None and not delais_region.empty:
        max_delai = delais_region["delai_jours_median"].max()
        if pd.notna(max_delai) and max_delai >= 90:
            top_spec = delais_region.loc[delais_region["delai_jours_median"].idxmax(), "specialite"]
            tension = f"délais d'accès aux spécialistes, notamment en {top_spec.lower()}"

    return {
        "dept_top": str(top.get("Nom du département", "—")),
        "nb_prioritaires": nb_prio,
        "nb_experimentation": nb_exp,
        "tension_principale": tension,
        "apl_med_reg": apl_med_reg,
    }


def compute_specialites_tension(
    delais: pd.DataFrame | None,
    region_code: str,
) -> pd.DataFrame:
    """Spécialités sous tension à partir des délais DREES régionaux."""
    if delais is None or delais.empty:
        return pd.DataFrame()

    dr = delais[delais["code_region"].astype(str) == str(region_code)].copy()
    if dr.empty:
        return dr

    for col in ("delai_jours_median", "delai_jours_p75"):
        if col in dr.columns:
            dr[col] = pd.to_numeric(dr[col], errors="coerce")

    dr = dr.dropna(subset=["delai_jours_median"]).sort_values(
        "delai_jours_median", ascending=False
    )
    pct = dr["delai_jours_median"].rank(pct=True, method="average")
    dr["tension"] = pct.apply(lambda s: _score_to_level(float(s), TENSION_DELAIS))
    return dr.reset_index(drop=True)
