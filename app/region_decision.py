"""Enrichissement décisionnel fiche région — scores, justifications, synthèse ARS.

Ne modifie pas les calculs de ``region_pilotage`` : produit des champs d'affichage
à partir des signaux déjà calculés.
"""

from __future__ import annotations

import pandas as pd

from .action_impact import (
    HORIZON_COURT,
    project_levier_amplitude_region,
)
from .region_pilotage import (
    _patho_fragment_stats,
    _patho_metrics,
    _patho_short_label,
)

_FAIS_DISPLAY: dict[str, str] = {
    "favorable": "Élevée",
    "correcte": "Élevée",
    "à consolider": "Moyenne",
    "difficile": "Complexe",
}

_IMPACT_DISPLAY: dict[str, str] = {
    "majeur": "Impact très élevé",
    "élevé": "Impact élevé",
    "moyen": "Impact moyen",
    "limité": "Impact limité",
}

_IMPACT_POP_MULT: dict[str, float] = {
    "majeur": 0.80,
    "élevé": 0.60,
    "moyen": 0.42,
    "limité": 0.25,
}

_PUBLIC_SHORT: dict[str, str] = {
    "Seniors (65 ans et plus)": "Seniors",
    "Maladies cardiovasculaires": "Maladies cardiovasculaires",
    "Maladies psychiatriques": "Santé mentale",
    "Maladies respiratoires chroniques": "Maladies respiratoires",
    "Maladies neurologiques ou dégénératives": "Neurologie",
    "Diabète": "Diabète",
    "Cancers": "Cancers",
}


def _num(val, default=float("nan")) -> float:
    try:
        v = float(val)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def _fmt_pop(n: int | None) -> str:
    if n is None or n <= 0:
        return "n.d."
    return f"{int(n):,}".replace(",", "\u202f")


def faisabilite_display(internal: str) -> str:
    return _FAIS_DISPLAY.get(str(internal), "Moyenne")


def impact_display(internal: str) -> str:
    return _IMPACT_DISPLAY.get(str(internal), "Impact moyen")


def _compute_score_priorite(df: pd.DataFrame) -> pd.Series:
    """Score décisionnel 0–100 à partir des signaux régionaux existants."""
    score_sg = 1 - pd.to_numeric(df["score_global"], errors="coerce").rank(
        pct=True, na_option="keep", method="average"
    )
    zone_bonus = df["zone_short"].map(
        {"Critique": 0.07, "Intermédiaire": 0.03, "Favorable": 0.0}
    ).fillna(0)
    raw = (
        0.32 * df["_frag_score"].fillna(0.5)
        + 0.28 * df["_impact_score"].fillna(0.5)
        + 0.22 * df["_fais_score"].fillna(0.5)
        + 0.18 * score_sg.fillna(0.5)
        + zone_bonus
    )
    return (raw.clip(0, 1) * 100).round(0).astype(int)


def _estimate_pop_concernee(row: pd.Series, patho_info: dict | None) -> int | None:
    pop = _num(row.get("population_num"))
    if pd.isna(pop) or pop <= 0:
        return None
    impact = str(row.get("impact", "moyen"))
    mult = _IMPACT_POP_MULT.get(impact, 0.42)
    base = int(pop * mult)
    if patho_info and patho_info.get("ntop"):
        base = max(base, int(patho_info["ntop"]))
    pct65 = _num(row.get("pct_plus_65"))
    if pd.notna(pct65) and pct65 > 0:
        seniors = int(pop * pct65 / 100)
        base = max(base, int(seniors * 0.55))
    return base


def _generate_justification_prioritaire(
    row: pd.Series,
    region_depts: pd.DataFrame,
    patho_info: dict | None,
    master: pd.DataFrame,
) -> str:
    """Justification factuelle pour un territoire prioritaire."""
    clauses: list[str] = []

    apl = _num(row.get("apl_median_dept"))
    apl_nat = pd.to_numeric(master["apl_median_dept"], errors="coerce").median()
    if pd.notna(apl) and pd.notna(apl_nat) and apl < apl_nat * 0.98:
        pct = (1 - apl / apl_nat) * 100
        clause = f"APL inférieur de {pct:.0f}\u202f% à la médiane nationale"
        if patho_info and patho_info.get("prev_max", 0) > 14:
            plabel = _patho_short_label(str(patho_info.get("patho_name", "")))
            if plabel:
                clause += f" et forte prévalence {plabel.lower()}"
        clauses.append(clause)

    temps = _num(row.get("temps_acces_median"))
    temps_reg = pd.to_numeric(
        region_depts["temps_acces_median"], errors="coerce"
    ).median()
    pct65 = _num(row.get("pct_plus_65"))
    if pd.notna(temps) and pd.notna(temps_reg) and temps > temps_reg * 1.08:
        if pd.notna(pct65) and pct65 > 22:
            clauses.append(
                "temps d'accès supérieur à la médiane régionale "
                "et vieillissement marqué de la population"
            )
        else:
            clauses.append("temps d'accès supérieur à la médiane régionale")

    nb_crit = int(_num(row.get("nb_communes_critiques"), 0) or 0)
    if pd.notna(pct65) and pct65 > 23 and nb_crit > 0:
        clauses.append(
            "forte concentration de seniors et éloignement "
            "des établissements de santé"
        )

    if not clauses and patho_info and patho_info.get("prev_max", 0) > 16:
        plabel = _patho_short_label(str(patho_info.get("patho_name", ""))) or "chroniques"
        clauses.append(f"prévalence {plabel.lower()} au-dessus de la médiane régionale")

    score_acces = _num(row.get("score_acces"))
    if not clauses and pd.notna(score_acces) and score_acces < 42:
        clauses.append("accès aux soins de ville sous la médiane régionale")

    if not clauses:
        raisons = row.get("raisons", [])
        if isinstance(raisons, list) and raisons:
            return str(raisons[0]).rstrip(".") + "."
        return str(
            row.get(
                "synthese",
                "Indicateurs territoriaux à approfondir avec les acteurs locaux.",
            )
        )[:140]

    if len(clauses) == 1:
        return clauses[0][0].upper() + clauses[0][1:] + "."
    return clauses[0][0].upper() + clauses[0][1:] + " et " + clauses[1] + "."


def enrich_priorities_decision(
    priorities: pd.DataFrame,
    region_depts: pd.DataFrame,
    patho: pd.DataFrame | None,
    master: pd.DataFrame,
) -> pd.DataFrame:
    """Ajoute score /100, impact estimé, faisabilité affichée et justification."""
    if priorities.empty:
        return priorities.copy()

    df = priorities.copy()
    dept_codes = df["dept"].astype(str).str.zfill(2).tolist()
    patho_map = _patho_metrics(patho, dept_codes)

    df["score_priorite"] = _compute_score_priorite(df)
    df["faisabilite_label"] = df["faisabilite"].map(faisabilite_display)
    df["impact_label"] = df["impact"].map(impact_display)

    pops: list[int | None] = []
    justifs: list[str] = []
    for _, row in df.iterrows():
        code = str(row["dept"]).zfill(2)
        pinfo = patho_map.get(code)
        pops.append(_estimate_pop_concernee(row, pinfo))
        justifs.append(
            _generate_justification_prioritaire(row, region_depts, pinfo, master)
        )

    df["impact_pop"] = pops
    df["justification_prioritaire"] = justifs
    df["lecture_rapide"] = df["justification_prioritaire"]

    return df.sort_values("score_priorite", ascending=False).reset_index(drop=True)


def _aggregate_faisabilite(labels: list[str]) -> str:
    order = {"Complexe": 0, "Moyenne": 1, "Élevée": 2}
    if not labels:
        return "Moyenne"
    return min(labels, key=lambda x: order.get(x, 1))


def _parse_pop_from_amplitude(population_str: str) -> int | None:
    """Extrait un entier depuis un libellé amplitude (« 125 000 habitants »)."""
    if not population_str or population_str == "n.d.":
        return None
    digits = "".join(c for c in population_str if c.isdigit())
    return int(digits) if digits else None


def _build_pourquoi_levier(
    lev: dict,
    region_depts: pd.DataFrame,
    patho: pd.DataFrame | None,
    dept_codes: list[str],
) -> str:
    intitule = str(lev.get("intitule", "")).lower()
    depts = lev.get("depts") or []
    n_depts = len(depts)
    rows = region_depts[region_depts["Nom du département"].isin(depts)]
    pop = int(pd.to_numeric(rows["population_num"], errors="coerce").sum())
    pop_fmt = _fmt_pop(pop if pop > 0 else None)

    if "cardio" in intitule:
        stats = _patho_fragment_stats(patho, dept_codes, "cardio")
        if stats and n_depts:
            prev_reg = pd.Series([s["prev"] for s in stats if pd.notna(s.get("prev"))])
            med = float(prev_reg.median()) if not prev_reg.empty else 0
            above = sum(1 for s in stats if pd.notna(s.get("prev")) and s["prev"] > med)
            n_pat = int(sum(s.get("ntop", 0) for s in stats))
            pat_fmt = _fmt_pop(n_pat if n_pat > 0 else None)
            return (
                f"La prévalence cardiovasculaire dépasse la médiane régionale "
                f"dans {above or n_depts} département{'s' if (above or n_depts) > 1 else ''} "
                f"représentant plus de {pat_fmt.replace(' personnes', '')} patients."
            )

    if "diabète" in intitule or "diabete" in intitule:
        stats = _patho_fragment_stats(patho, dept_codes, "iabète")
        if stats:
            n_pat = int(sum(s.get("ntop", 0) for s in stats))
            return (
                f"Les volumes CNAM diabète identifient {n_pat:,}".replace(",", "\u202f")
                + f" patients sur {n_depts} département{'s' if n_depts > 1 else ''} "
                f"à prévalence au-dessus de la médiane régionale."
            )

    if "santé mentale" in intitule or "psychiatr" in intitule:
        stats = _patho_fragment_stats(patho, dept_codes, "sychiatr")
        if stats and depts:
            return (
                f"Prévalence psychiatrique CNAM élevée combinée à un accès "
                f"aux soins contraint sur {len(depts)} département"
                f"{'s' if len(depts) > 1 else ''} ({', '.join(depts[:2])}{'…' if len(depts) > 2 else ''})."
            )

    if "senior" in intitule or "gériatrique" in intitule or "geriatrique" in intitule:
        pct65 = pd.to_numeric(rows.get("pct_plus_65"), errors="coerce")
        if pct65.notna().any():
            med = float(pct65.median())
            return (
                f"Part des 65+ à {med:.0f}\u202f% en médiane sur {n_depts} "
                f"département{'s' if n_depts > 1 else ''} "
                f"({pop_fmt.replace(' personnes', '')} habitants concernés)."
            )

    if "téléexpertise" in intitule or "teleexpertise" in intitule:
        desert = int(
            (pd.to_numeric(rows["apl_median_dept"], errors="coerce") < 2.5).sum()
        )
        if desert:
            return (
                f"{desert} département{'s' if desert > 1 else ''} en désert médical "
                f"(APL < 2,5) justifient un recours à la téléexpertise "
                f"pour {pop_fmt.replace(' personnes', '')} habitants."
            )

    if "consultations avancées" in intitule or "navettes" in intitule:
        communes = int(pd.to_numeric(rows["nb_communes_critiques"], errors="coerce").fillna(0).sum())
        if communes:
            return (
                f"{communes} communes éloignées des établissements recensées "
                f"sur {n_depts} département{'s' if n_depts > 1 else ''} "
                f"({pop_fmt.replace(' personnes', '')} habitants potentiellement touchés)."
            )

    justification = str(lev.get("justification", "")).strip()
    if justification:
        return justification
    tension = str(lev.get("tension", "")).strip()
    if tension and n_depts:
        return f"{tension.capitalize()} sur {n_depts} département{'s' if n_depts > 1 else ''} ciblés."
    return "Signaux territoriaux convergents sur ce levier."


def _build_pourquoi_maintenant(lev: dict, amplitude_pop: str) -> str:
    tension = str(lev.get("tension", "")).strip()
    depts = lev.get("depts") or []
    n = len(depts)
    if tension:
        return (
            f"{tension.capitalize()} sur {n} département{'s' if n > 1 else ''} "
            f"— population potentiellement concernée\u202f: {amplitude_pop}."
        )
    return (
        f"Convergence des indicateurs régionaux sur {n} département"
        f"{'s' if n > 1 else ''} — {amplitude_pop}."
    )


def enrich_leviers_decision(
    leviers: list[dict],
    region_depts: pd.DataFrame,
    priorities: pd.DataFrame,
    data: dict | None,
    region_name: str,
) -> list[dict]:
    """Enrichit chaque levier pour l'affichage décisionnel."""
    data = data or {}
    patho = data.get("patho")
    dept_codes = region_depts["dept"].astype(str).str.zfill(2).tolist()
    names_to_prio = {
        str(r["Nom du département"]): r
        for _, r in priorities.iterrows()
    }

    enriched: list[dict] = []
    for lev in leviers:
        item = dict(lev)
        amplitude = project_levier_amplitude_region(
            item, region_depts, data, region_name
        )
        item["amplitude"] = amplitude
        item["horizon"] = amplitude.horizon
        item["impact_pop_str"] = amplitude.population

        pop_n = _parse_pop_from_amplitude(amplitude.population)
        if pop_n and pop_n >= 250_000:
            item["impact_niveau"] = "Impact très élevé"
        elif pop_n and pop_n >= 120_000:
            item["impact_niveau"] = "Impact élevé"
        elif pop_n and pop_n >= 50_000:
            item["impact_niveau"] = "Impact moyen"
        else:
            item["impact_niveau"] = "Impact limité"

        fais_labels: list[str] = []
        for dname in item.get("depts") or []:
            prow = names_to_prio.get(dname)
            if prow is not None:
                fais_labels.append(faisabilite_display(str(prow["faisabilite"])))
        item["faisabilite_label"] = _aggregate_faisabilite(fais_labels)
        item["pourquoi_levier"] = _build_pourquoi_levier(
            item, region_depts, patho, dept_codes
        )
        item["pourquoi_maintenant"] = _build_pourquoi_maintenant(
            item, amplitude.population
        )
        enriched.append(item)
    return enriched


def build_decision_synthesis(
    priorities: pd.DataFrame,
    leviers: list[dict],
    publics: list[dict],
) -> dict[str, str]:
    """Synthèse « Ce qu'il faut retenir » pour la section action."""
    top_dept = (
        str(priorities.iloc[0]["Nom du département"])
        if not priorities.empty else "N/D"
    )
    top_public = "N/D"
    if publics:
        top_public = _PUBLIC_SHORT.get(
            publics[0].get("label", ""), publics[0].get("label", "N/D")
        )

    top_action = leviers[0]["intitule"].capitalize() if leviers else "N/D"

    fast_lev = next(
        (lev for lev in leviers if lev.get("horizon") == HORIZON_COURT),
        leviers[1] if len(leviers) > 1 else (leviers[0] if leviers else None),
    )
    fast_action = (
        fast_lev["intitule"].capitalize() if fast_lev else "N/D"
    )

    return {
        "territoire_cible": top_dept,
        "public_cible": top_public,
        "action_prioritaire": top_action,
        "action_rapide": fast_action,
    }
