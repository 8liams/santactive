"""Enrichissement décisionnel fiche région — scores, justifications, synthèse ARS.

Ne modifie pas les calculs de ``region_pilotage`` : produit des champs d'affichage
à partir des signaux déjà calculés.
"""

from __future__ import annotations

import pandas as pd

from .action_impact import project_levier_amplitude_region
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

# (anciens multiplicateurs de « population concernée » supprimés : volumes observés)

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
    """Score de priorité 0-100 = besoin territorial pondéré par le volume.

    - besoin  : moyenne à poids égaux de la fragilité (rangs nationaux) et du
      complément du score global (1 − score/100) ;
    - volume  : rang national de la population et des publics concernés
      (_impact_score) ;
    - score   : moyenne à poids égaux de besoin et volume.
    La FAISABILITÉ n'entre pas dans le score : elle est affichée à part. Un
    département très fragile n'est pas rétrogradé parce qu'il est difficile
    d'y intervenir. Aucun bonus de zone (le score global est déjà présent).
    Poids égaux = choix explicite, faute de référence validée pour d'autres.
    """
    frag = pd.to_numeric(df["_frag_score"], errors="coerce")
    sg = 1 - pd.to_numeric(df["score_global"], errors="coerce") / 100
    besoin = pd.concat([frag, sg], axis=1).mean(axis=1, skipna=True)
    volume = pd.to_numeric(df["_impact_score"], errors="coerce")
    score = pd.concat([besoin, volume], axis=1).mean(axis=1, skipna=True)
    df["score_besoin"] = (besoin.clip(0, 1) * 100).round(0).astype("Int64")
    df["score_volume"] = (volume.clip(0, 1) * 100).round(0).astype("Int64")
    return (score.clip(0, 1) * 100).round(0).astype("Int64")


def _estimate_pop_concernee(row: pd.Series, patho_info: dict | None) -> int | None:
    """Population observée du département (INSEE).

    Remplace l'ancienne « population concernée » obtenue par des
    multiplicateurs non sourcés (0,80 / 0,60 / 0,42 / 0,25 / 0,55).
    """
    pop = _num(row.get("population_num"))
    if pd.isna(pop) or pop <= 0:
        return None
    return int(pop)


def _generate_justification_prioritaire(
    row: pd.Series,
    region_depts: pd.DataFrame,
    patho_info: dict | None,
    master: pd.DataFrame,
) -> str:
    """Justification factuelle pour un territoire prioritaire."""
    clauses: list[str] = []

    apl = _num(row.get("apl_dept"))
    apl_nat = pd.to_numeric(master["apl_dept"], errors="coerce").median()
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

    nb_crit = _num(row.get("nb_communes_critiques"))
    if pd.notna(pct65) and pct65 > 23 and pd.notna(nb_crit) and nb_crit > 0:
        clauses.append(
            "forte part de seniors et communes à plus de 15\u202fmin "
            "de temps d'accès"
        )

    if not clauses and patho_info and patho_info.get("prev_max", 0) > 16:
        plabel = _patho_short_label(str(patho_info.get("patho_name", ""))) or "chroniques"
        clauses.append(
            f"prévalence brute {plabel.lower()} élevée ({patho_info['prev_max']:.1f}\u202f%)"
        )

    score_acces = _num(row.get("score_acces"))
    if not clauses and pd.notna(score_acces) and score_acces < 42:
        clauses.append(f"score d'accès aux soins de {score_acces:.0f}/100 (rang national)")

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

    # Classement unique (page, tableau technique et PDF) : score de priorité
    df = df.sort_values(
        ["score_priorite", "_frag_score"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)
    df["priorite_rang"] = range(1, len(df) + 1)
    return df


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
    # Statistiques calculées sur les seuls départements ciblés par le levier
    dept_codes = rows["dept"].astype(str).str.zfill(2).tolist() or dept_codes
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
            (pd.to_numeric(rows["apl_dept"], errors="coerce") < 2.5).sum()
        )
        if desert:
            return (
                f"{desert} département{'s' if desert > 1 else ''} avec un APL "
                f"sous le repère de 2,5 ({pop_fmt.replace(' personnes', '')} "
                f"habitants dans les départements ciblés)."
            )

    if "consultations avancées" in intitule or "navettes" in intitule:
        communes = int(pd.to_numeric(rows["nb_communes_critiques"], errors="coerce").fillna(0).sum())
        if communes:
            return (
                f"{communes} communes éloignées des établissements recensées "
                f"sur {n_depts} département{'s' if n_depts > 1 else ''} "
                f"({pop_fmt.replace(' personnes', '')} habitants dans ces départements, INSEE)."
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
            f"— {amplitude_pop}."
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
        pop_n = int(item.get("population_ciblee") or 0) or None
        item["impact_pop_str"] = (
            f"{_fmt_pop(pop_n)} habitants (départements ciblés, INSEE)"
            if pop_n else "n.d."
        )

        # Portée observée : part de la population régionale des départements ciblés
        pop_reg = float(pd.to_numeric(region_depts["population_num"], errors="coerce").sum())
        part = (pop_n / pop_reg) if pop_n and pop_reg > 0 else None
        item["portee_pct"] = part
        item["impact_niveau"] = (
            f"Portée : {part:.0%} de la population régionale" if part is not None else "Portée n.d."
        )

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
            item, item["impact_pop_str"]
        )
        enriched.append(item)
    return enriched


def _build_justification_action_prioritaire(lev: dict, region_name: str) -> str:
    """Phrase unique expliquant pourquoi le levier #1 ressort en tête."""
    intitule = str(lev.get("intitule", "")).lower()
    action = str(lev.get("intitule", "cette action")).capitalize()
    n_depts = len(lev.get("depts") or [])

    if "cardio" in intitule:
        return (
            f"La {action.lower()} apparaît comme l'action la plus pertinente "
            f"en {region_name} au regard du nombre de patients concernés, "
            f"de la concentration géographique des besoins et du potentiel "
            f"d'impact régional."
        )
    if "diabète" in intitule or "diabete" in intitule:
        return (
            f"Le {action.lower()} ressort en tête en {region_name} "
            f"compte tenu des volumes CNAM identifiés sur {n_depts} "
            f"département{'s' if n_depts > 1 else ''} et du potentiel "
            f"d'intervention à court terme."
        )
    if "senior" in intitule or "gériatrique" in intitule or "geriatrique" in intitule:
        return (
            f"La {action.lower()} concentre les signaux démographiques "
            f"et d'accès les plus marqués en {region_name}, "
            f"sur {n_depts} département{'s' if n_depts > 1 else ''} "
            f"à forte part de seniors."
        )
    if "téléexpertise" in intitule or "teleexpertise" in intitule:
        return (
            f"La {action.lower()} répond aux contraintes d'accès "
            f"aux spécialistes observées en {region_name}, "
            f"avec un déploiement possible sur {n_depts} "
            f"département{'s' if n_depts > 1 else ''}."
        )
    if "santé mentale" in intitule or "psychiatr" in intitule:
        return (
            f"La {action.lower()} fait émerger en {region_name} "
            f"par la combinaison prévalence CNAM et difficultés "
            f"d'accès aux soins sur {n_depts} "
            f"département{'s' if n_depts > 1 else ''}."
        )

    pourquoi = str(lev.get("pourquoi_levier", "")).strip()
    if pourquoi:
        return (
            f"{action} apparaît comme l'action la plus pertinente "
            f"en {region_name}\u202f: {pourquoi[0].lower() + pourquoi[1:]}"
            if pourquoi[0].isupper() else
            f"{action} apparaît comme l'action la plus pertinente "
            f"en {region_name}\u202f: {pourquoi}"
        )
    return (
        f"{action} ressort comme la priorité régionale en {region_name} "
        f"au regard des besoins observés, des publics concernés "
        f"et du potentiel d'impact estimé."
    )


def build_action_prioritaire(
    leviers: list[dict],
    region_name: str,
) -> dict[str, str] | None:
    """Carte stratégique « Action régionale prioritaire » (levier #1)."""
    if not leviers:
        return None

    lev = leviers[0]
    amplitude = lev.get("amplitude")
    depts = lev.get("depts") or []

    return {
        "action": str(lev["intitule"]).capitalize(),
        "population": str(lev.get("impact_pop_str", "n.d.")),
        "territoires": ", ".join(depts) if depts else "n.d.",
        "faisabilite": str(lev.get("faisabilite_label", "Moyenne")),
        "horizon": (
            amplitude.horizon if amplitude
            else str(lev.get("horizon", "Moyen terme"))
        ),
        "justification": _build_justification_action_prioritaire(lev, region_name),
    }
