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
PERTINENCE_LABELS = ("à étudier", "pertinent", "très pertinent", "prioritaire")
PUBLIC_PRIO_LABELS = ("modérée", "élevée", "prioritaire", "majeure")
PUBLIC_IMPORTANCE = {
    "majeure": "Importance majeure",
    "prioritaire": "Importance prioritaire",
    "élevée": "Importance élevée",
    "modérée": "Importance modérée",
}

# Fragments patho_niv1 → axes publics / pathologies
PUBLIC_PATHO_AXES: tuple[dict, ...] = (
    {"key": "cardio",      "label": "Maladies cardiovasculaires",           "fragment": "cardio"},
    {"key": "diabete",     "label": "Diabète",                              "fragment": "iabète"},
    {"key": "cancers",     "label": "Cancers",                              "fragment": "ancer"},
    {"key": "respiratoire","label": "Maladies respiratoires chroniques",    "fragment": "espira"},
    {"key": "psychiatrique","label": "Maladies psychiatriques",             "fragment": "sychiatr"},
    {"key": "neurologie",  "label": "Maladies neurologiques ou dégénératives", "fragment": "eurologiq"},
)

SPECIALITE_LEVIERS: dict[str, str] = {
    "Ophtalmologue":   "téléexpertise",
    "Psychiatre":      "télésuivi",
    "Généraliste":     "consultations avancées",
    "Pédiatre":        "consultations avancées",
    "Dermatologue":    "téléexpertise",
    "Cardiologue":     "parcours coordonné",
    "Gynécologue":     "consultations avancées",
    "ORL":             "téléexpertise",
    "Rhumatologue":    "télésuivi",
    "Endocrinologue":  "prévention ciblée",
}


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

    score_acces = _num(row.get("score_acces"))
    if pd.notna(score_acces) and score_acces < 40:
        reasons.append("Accès aux soins dégradé (APL et temps de trajet sous la médiane régionale).")

    etabs = _num(row.get("structures_pour_100k"))
    if pd.notna(etabs) and etabs < 4:
        reasons.append(f"Offre hospitalière limitée ({etabs:.1f} structures /100\u202f000 hab.).")

    if len(reasons) < 3:
        zone = str(row.get("zone_short", ""))
        if zone and zone != "Favorable":
            reasons.append(f"Classé en zone {zone.lower()} au regard des indicateurs territoriaux.")
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


_PATHO_SHORT: tuple[tuple[str, str], ...] = (
    ("cardio", "Maladies cardiovasculaires"),
    ("iabète", "Diabète"),
    ("ancer", "Cancers"),
    ("espira", "Maladies respiratoires"),
    ("sychiatr", "Santé mentale"),
    ("eurologiq", "Neurologie"),
)


def _patho_short_label(patho_name: str) -> str | None:
    low = patho_name.lower()
    for frag, label in _PATHO_SHORT:
        if frag in low:
            return label
    return None


def _pros_per_100k(row: pd.Series, col: str) -> float:
    pop = _num(row.get("population_num"))
    val = _num(row.get(col))
    if pop <= 0 or pd.isna(val):
        return float("nan")
    return val / pop * 100_000


def build_territoire_card(
    row: pd.Series,
    patho_info: dict | None,
    region_depts: pd.DataFrame,
) -> dict[str, list[str]]:
    """Profil synthétique d'un territoire prioritaire (fragilités, atouts, publics)."""
    fragilites: list[str] = []
    atouts: list[str] = []
    publics: list[str] = []

    apl = _num(row.get("apl_median_dept"))
    if pd.notna(apl) and apl < APL_SEUIL_DESERT:
        fragilites.append("Désert médical")

    pct65 = _num(row.get("pct_plus_65"))
    if pd.notna(pct65) and pct65 > 22:
        fragilites.append("Forte part de seniors")
        publics.append("Seniors")

    nb_crit = int(_num(row.get("nb_communes_critiques"), 0) or 0)
    if nb_crit > 0:
        fragilites.append("Communes isolées")

    score_acces = _num(row.get("score_acces"))
    if pd.notna(score_acces) and score_acces < 40:
        fragilites.append("Accès aux soins dégradé")

    etabs = _num(row.get("structures_pour_100k"))
    if pd.notna(etabs) and etabs < 4:
        fragilites.append("Faible offre hospitalière")

    temps = _num(row.get("temps_acces_median"))
    if pd.notna(temps) and temps > 12:
        fragilites.append("Temps d'accès élevé")

    hop = int(_num(row.get("nb_hopitaux"), 0) or 0)
    cli = int(_num(row.get("nb_cliniques"), 0) or 0)
    if hop + cli > 0:
        atouts.append("Réseau hospitalier présent")

    rd = region_depts.copy()
    rd["_inf_100k"] = rd.apply(lambda r: _pros_per_100k(r, "nb_infirmiers"), axis=1)
    rd["_pha_100k"] = rd.apply(lambda r: _pros_per_100k(r, "nb_pharmaciens"), axis=1)
    inf_100k = _pros_per_100k(row, "nb_infirmiers")
    pha_100k = _pros_per_100k(row, "nb_pharmaciens")
    med_inf = rd["_inf_100k"].median()
    med_pha = rd["_pha_100k"].median()
    if pd.notna(inf_100k) and pd.notna(med_inf) and inf_100k >= med_inf * 1.05:
        atouts.append("Densité infirmière élevée")
    if pd.notna(pha_100k) and pd.notna(med_pha) and pha_100k >= med_pha * 1.05:
        atouts.append("Densité pharmaciens élevée")

    prix = _num(row.get("prix_m2_moyen"))
    prix_med = pd.to_numeric(rd.get("prix_m2_moyen"), errors="coerce").median()
    if pd.notna(prix) and pd.notna(prix_med) and prix <= prix_med * 0.85:
        atouts.append("Foncier favorable")

    if pd.notna(temps) and temps <= 10:
        atouts.append("Temps d'accès correct")

    if patho_info and patho_info.get("prev_max", 0) > 0:
        plabel = _patho_short_label(str(patho_info.get("patho_name", "")))
        if plabel and plabel not in publics:
            publics.append(plabel)

    return {
        "fragilites": fragilites[:3],
        "atouts": atouts[:3],
        "publics": publics[:2],
    }


def _densite_faisabilite_score(densite: pd.Series) -> pd.Series:
    """Score 0–1 : densité proche de la médiane régionale = plus favorable à la coordination."""
    med = densite.median()
    if pd.isna(med) or med <= 0:
        return pd.Series(0.5, index=densite.index)
    spread = max(densite.max() - med, med - densite.min(), 1.0)
    dist = (densite - med).abs() / spread
    return (1.0 - dist.clip(0, 1)).fillna(0.5)


def _composite_score(signals: dict[str, pd.Series]) -> pd.Series:
    """Moyenne pondérée des signaux alignés sur le même index (labels, pas positions)."""
    index = next(iter(signals.values())).index

    def _row(idx) -> float:
        return _weighted_mean({k: _num(v.loc[idx]) for k, v in signals.items()})

    return pd.Series([_row(i) for i in index], index=index)


def compute_dept_priorities(
    region_depts: pd.DataFrame,
    patho: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calcule les 4 dimensions de priorisation pour chaque département de la région."""
    df = region_depts.copy().reset_index(drop=True)
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
    df["_frag_score"] = _composite_score(frag_signals)
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
    df["_impact_score"] = _composite_score(impact_signals)

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
    df["_fais_score"] = _composite_score(fais_signals)

    # ── Niveaux lisibles ────────────────────────────────────────────────────────
    df["fragilite"] = df["_frag_score"].apply(lambda s: _score_to_level(s, FRAG_LABELS))
    df["impact"] = df["_impact_score"].apply(lambda s: _score_to_level(s, IMPACT_LABELS))
    df["faisabilite"] = df["_fais_score"].apply(lambda s: _score_to_level(s, FAIS_LABELS))
    df["priorite"] = df.apply(
        lambda r: _assign_priorite(r["fragilite"], r["impact"], r["faisabilite"]),
        axis=1,
    )

    prio_order = {p: i for i, p in enumerate(PRIO_LABELS)}
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


def _pop_territoires_prioritaires(priorities: pd.DataFrame) -> int:
    """Population totale des départements prioritaires ou candidats expérimentation."""
    mask = priorities["priorite"].isin(
        ["prioritaire", "très prioritaire", "candidat expérimentation"]
    )
    pop = pd.to_numeric(priorities.loc[mask, "population_num"], errors="coerce").sum()
    return int(pop) if pd.notna(pop) else 0


def _nb_depts_actionnables(priorities: pd.DataFrame) -> int:
    return int(
        priorities["priorite"].isin(
            ["prioritaire", "très prioritaire", "candidat expérimentation"]
        ).sum()
    )


def _public_principal(publics: list[dict] | None) -> str:
    if not publics:
        return "n.d."
    label = str(publics[0].get("label", ""))
    short = {
        "Seniors (65 ans et plus)": "Seniors",
        "Maladies cardiovasculaires": "Maladies cardiovasculaires",
        "Maladies psychiatriques": "Santé mentale",
        "Maladies respiratoires chroniques": "Maladies respiratoires",
        "Maladies neurologiques ou dégénératives": "Neurologie",
    }
    return short.get(label, label)


def compute_region_summary(
    priorities: pd.DataFrame,
    region_depts: pd.DataFrame,
    delais_region: pd.DataFrame | None = None,
    publics: list[dict] | None = None,
) -> dict:
    """Résumé régional pour le bandeau supérieur du bloc."""
    if priorities.empty:
        return {
            "dept_top": "—",
            "nb_prioritaires": 0,
            "nb_experimentation": 0,
            "tension_principale": "Données insuffisantes pour identifier une tension dominante.",
            "pop_territoires_prioritaires": 0,
            "nb_depts_prioritaires": 0,
            "public_principal": "n.d.",
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
        "pop_territoires_prioritaires": _pop_territoires_prioritaires(priorities),
        "nb_depts_prioritaires": _nb_depts_actionnables(priorities),
        "public_principal": _public_principal(publics),
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
    dr["levier"] = dr["specialite"].map(
        lambda s: SPECIALITE_LEVIERS.get(str(s), "parcours coordonné")
    )
    return dr.reset_index(drop=True)


def _patho_fragment_stats(
    patho: pd.DataFrame | None,
    dept_codes: list[str],
    fragment: str,
) -> list[dict]:
    """Stats par département pour un fragment de patho_niv1."""
    if patho is None or patho.empty or "_error" in patho.columns:
        return []

    dp = patho.copy()
    dp["dept"] = dp["dept"].astype(str).str.zfill(2)
    dp = dp[~dp["patho_niv1"].isin(PATHOS_EXCLUDED)]
    dp = dp[dp["patho_niv1"].str.contains(fragment, case=False, na=False, regex=False)]
    dp = dp[dp["dept"].isin([str(c).zfill(2) for c in dept_codes])]
    if dp.empty:
        return []

    rows: list[dict] = []
    for code in dept_codes:
        c = str(code).zfill(2)
        d = dp[dp["dept"] == c]
        if d.empty:
            continue
        ntop = float(d["Ntop"].sum())
        npop = float(d["Npop"].sum())
        prev = (ntop / npop * 100) if npop > 0 else float("nan")
        rows.append({"dept": c, "ntop": ntop, "prev": prev})
    return rows


def _dept_names_map(region_depts: pd.DataFrame) -> dict[str, str]:
    return {
        str(r["dept"]).zfill(2): str(r["Nom du département"])
        for _, r in region_depts.iterrows()
    }


def compute_publics_prioritaires(
    region_depts: pd.DataFrame,
    patho: pd.DataFrame | None,
    priorities: pd.DataFrame,
) -> list[dict]:
    """Publics et pathologies prioritaires à l'échelle régionale."""
    dept_codes = region_depts["dept"].astype(str).str.zfill(2).tolist()
    names = _dept_names_map(region_depts)
    axes: list[dict] = []

    # ── Seniors (démographie) ─────────────────────────────────────────────────
    if "pct_plus_65" in region_depts.columns:
        rd = region_depts.copy()
        rd["dept_z"] = rd["dept"].astype(str).str.zfill(2)
        rd["seniors_abs"] = (
            pd.to_numeric(rd["population_num"], errors="coerce")
            * pd.to_numeric(rd["pct_plus_65"], errors="coerce") / 100
        )
        rd = rd.dropna(subset=["pct_plus_65"]).sort_values("seniors_abs", ascending=False)
        if not rd.empty:
            top = rd.head(3)
            score = float(rd["pct_plus_65"].rank(pct=True, method="average").max())
            axes.append({
                "label": "Seniors (65 ans et plus)",
                "type": "démographie",
                "depts": [names.get(str(r["dept_z"]), "?") for _, r in top.iterrows()],
                "prev": f"{float(rd['pct_plus_65'].median()):.1f}\u202f% médiane régionale",
                "volume": (
                    f"{int(rd['seniors_abs'].sum()):,}".replace(",", "\u202f") + "\u202f seniors"
                    if rd["seniors_abs"].notna().any() else "n.d."
                ),
                "priorite": _score_to_level(score, PUBLIC_PRIO_LABELS),
                "importance": PUBLIC_IMPORTANCE.get(
                    _score_to_level(score, PUBLIC_PRIO_LABELS), "Importance modérée"
                ),
            })

    # ── Pathologies CNAM ────────────────────────────────────────────────────
    for axis in PUBLIC_PATHO_AXES:
        stats = _patho_fragment_stats(patho, dept_codes, axis["fragment"])
        if not stats:
            continue
        stats.sort(key=lambda x: x.get("prev", 0) or 0, reverse=True)
        top3 = stats[:3]
        total_ntop = sum(s["ntop"] for s in stats)
        max_prev = max(s["prev"] for s in stats if pd.notna(s.get("prev")))
        score = max_prev / 25.0 if pd.notna(max_prev) else 0.5  # ~25% = référence haute
        prio_label = _score_to_level(min(score, 1.0), PUBLIC_PRIO_LABELS)
        axes.append({
            "label": axis["label"],
            "type": "pathologie CNAM",
            "depts": [names.get(s["dept"], s["dept"]) for s in top3],
            "prev": f"{max_prev:.1f}\u202f% max. régionale" if pd.notna(max_prev) else "n.d.",
            "volume": (
                f"{int(total_ntop):,}".replace(",", "\u202f") + "\u202f patients"
                if total_ntop > 0 else "n.d."
            ),
            "priorite": prio_label,
            "importance": PUBLIC_IMPORTANCE.get(prio_label, "Importance modérée"),
        })

    prio_order = {"majeure": 4, "prioritaire": 3, "élevée": 2, "modérée": 1}
    axes.sort(key=lambda a: prio_order.get(a["priorite"], 0), reverse=True)
    return axes


def _lever(
    famille: str,
    intitule: str,
    depts: list[str],
    public: str,
    tension: str,
    justification: str,
    score: float,
) -> dict:
    return {
        "famille": famille,
        "intitule": intitule,
        "depts": depts[:4],
        "public_cible": public,
        "tension": tension,
        "justification": justification,
        "pertinence": _score_to_level(min(max(score, 0), 1), PERTINENCE_LABELS),
    }


def compute_leviers_action(
    region_depts: pd.DataFrame,
    priorities: pd.DataFrame,
    patho: pd.DataFrame | None,
    delais_region: pd.DataFrame | None,
) -> list[dict]:
    """Moteur simple de leviers d'action régionaux."""
    names = _dept_names_map(region_depts)
    dept_codes = region_depts["dept"].astype(str).str.zfill(2).tolist()
    levers: list[dict] = []

    def _dept_list(mask) -> list[str]:
        return [
            names.get(str(r["dept"]).zfill(2), "?")
            for _, r in priorities[mask].iterrows()
        ][:4]

    frag_high = priorities["fragilite"].isin(["forte", "très forte"])
    fais_ok = priorities["faisabilite"].isin(["correcte", "favorable"])
    acces_low = pd.to_numeric(region_depts["score_acces"], errors="coerce") < 45
    acces_depts = [
        names.get(str(r["dept"]).zfill(2), "?")
        for _, r in region_depts[acces_low].iterrows()
    ][:4]

    pct65_high = pd.to_numeric(region_depts["pct_plus_65"], errors="coerce") > 22
    senior_depts = [
        names.get(str(r["dept"]).zfill(2), "?")
        for _, r in region_depts[pct65_high].iterrows()
    ][:4]

    nb_desert = int(
        (pd.to_numeric(region_depts["apl_median_dept"], errors="coerce") < APL_SEUIL_DESERT).sum()
    )
    desert_depts = [
        names.get(str(r["dept"]).zfill(2), "?")
        for _, r in region_depts[
            pd.to_numeric(region_depts["apl_median_dept"], errors="coerce") < APL_SEUIL_DESERT
        ].iterrows()
    ][:4]

    communes_high = pd.to_numeric(region_depts["nb_communes_critiques"], errors="coerce") > 3
    iso_depts = [
        names.get(str(r["dept"]).zfill(2), "?")
        for _, r in region_depts[communes_high].iterrows()
    ][:4]

    temps_high = pd.to_numeric(region_depts["temps_acces_median"], errors="coerce") > 12
    temps_depts = [
        names.get(str(r["dept"]).zfill(2), "?")
        for _, r in region_depts[temps_high].iterrows()
    ][:4]

    relais_mask = priorities["faisabilite"].isin(["correcte", "favorable", "à consolider"])
    coord_mask = frag_high & relais_mask
    coord_depts = _dept_list(coord_mask)

    # ── Prévention ────────────────────────────────────────────────────────────
    cardio_stats = _patho_fragment_stats(patho, dept_codes, "cardio")
    if cardio_stats and senior_depts:
        levers.append(_lever(
            "Prévention et dépistage", "Prévention cardiovasculaire",
            [names.get(s["dept"], s["dept"]) for s in sorted(cardio_stats, key=lambda x: x["prev"], reverse=True)[:3]],
            "Adultes à risque cardiovasculaire",
            "Prévalence cardiovasculaire CNAM élevée et part des seniors importante",
            "Données CNAM et INSEE convergent sur un risque cardio régional.",
            0.75,
        ))

    diab_stats = _patho_fragment_stats(patho, dept_codes, "iabète")
    if diab_stats:
        levers.append(_lever(
            "Prévention et dépistage", "Dépistage diabète",
            [names.get(s["dept"], s["dept"]) for s in sorted(diab_stats, key=lambda x: x["prev"], reverse=True)[:3]],
            "Population à risque de diabète",
            "Prévalence diabète CNAM au-dessus de la médiane régionale",
            "Volumes patients CNAM identifiés sur plusieurs départements.",
            0.65,
        ))

    psy_stats = _patho_fragment_stats(patho, dept_codes, "sychiatr")
    if psy_stats and acces_depts:
        levers.append(_lever(
            "Prévention et dépistage", "Prévention santé mentale",
            [names.get(s["dept"], s["dept"]) for s in sorted(psy_stats, key=lambda x: x["prev"], reverse=True)[:3]],
            "Publics en souffrance psychique",
            "Prévalence psychiatrique CNAM et accès aux soins contraint",
            "Pathologies CNAM combinées à un score d'accès dégradé.",
            0.70,
        ))

    if senior_depts and (frag_high.any() or acces_depts):
        levers.append(_lever(
            "Prévention et dépistage", "Prévention fragilité seniors",
            senior_depts,
            "Personnes de 65 ans et plus",
            "Part des seniors élevée et accès aux soins contraint",
            f"{len(senior_depts)} département(s) au-dessus de 22\u202f% de 65+ avec signaux d'accès faibles.",
            0.72,
        ))

    resp_stats = _patho_fragment_stats(patho, dept_codes, "espira")
    if resp_stats:
        levers.append(_lever(
            "Prévention et dépistage", "Prévention respiratoire",
            [names.get(s["dept"], s["dept"]) for s in sorted(resp_stats, key=lambda x: x["prev"], reverse=True)[:3]],
            "Patients BPCO et pathologies respiratoires",
            "Prévalence respiratoire chronique CNAM significative",
            "Données CNAM sur pathologies respiratoires chroniques.",
            0.60,
        ))

    # ── Numérique ─────────────────────────────────────────────────────────────
    if nb_desert > 0 or (delais_region is not None and not delais_region.empty
                         and delais_region["delai_jours_median"].max() >= 60):
        depts_num = desert_depts or acces_depts
        tension_num = (
            "APL faible sur plusieurs départements"
            if nb_desert > 0
            else "Délais spécialistes régionaux élevés"
        )
        levers.append(_lever(
            "Numérique en santé", "Téléexpertise",
            depts_num,
            "Patients en attente de spécialistes",
            tension_num,
            "Isolement médical et/ou délais DREES justifient un recours au numérique.",
            0.80 if nb_desert > 0 else 0.65,
        ))

    if acces_depts and delais_region is not None and not delais_region.empty:
        levers.append(_lever(
            "Numérique en santé", "Téléconsultation assistée",
            acces_depts,
            "Usagers en difficulté d'accès aux spécialistes",
            "Accès de ville contraint et délais DREES élevés",
            "Croisement score d'accès départemental et délais régionaux.",
            0.68,
        ))

    if senior_depts and frag_high.any():
        levers.append(_lever(
            "Numérique en santé", "Télésuivi des patients chroniques",
            _dept_list(frag_high) or senior_depts,
            "Patients chroniques et seniors",
            "Pathologies chroniques CNAM et territoires fragiles",
            "Besoin de suivi à distance sur départements à fragilité élevée.",
            0.70,
        ))

    # ── Coordination ──────────────────────────────────────────────────────────
    if coord_depts:
        levers.append(_lever(
            "Coordination territoriale", "Parcours ville-hôpital",
            coord_depts,
            "Patients en parcours complexe",
            "Besoin sanitaire fort avec relais locaux déjà présents",
            "Infirmiers, pharmaciens ou établissements recensés sur les territoires ciblés.",
            0.72,
        ))
        levers.append(_lever(
            "Coordination territoriale", "Parcours maladies chroniques",
            coord_depts,
            "Patients atteints de pathologies chroniques",
            "Offre de soins dispersée mais relais de proximité disponibles",
            "Faisabilité d'action favorable malgré une fragilité sanitaire nette.",
            0.68,
        ))

    # ── Accès proximité ───────────────────────────────────────────────────────
    if iso_depts or temps_depts:
        depts_prox = list(dict.fromkeys(iso_depts + temps_depts))[:4]
        levers.append(_lever(
            "Accès de proximité", "Consultations avancées",
            depts_prox,
            "Habitants éloignés des établissements",
            "Communes isolées ou temps d'accès médian élevé",
            "Données communes critiques et temps de trajet vers les établissements.",
            0.70,
        ))
        if iso_depts:
            levers.append(_lever(
                "Accès de proximité", "Navettes santé",
                iso_depts,
                "Personnes sans mobilité vers les soins",
                f"{int(region_depts['nb_communes_critiques'].fillna(0).sum())} communes éloignées des établissements",
                "Isolement géographique recensé dans la région.",
                0.65,
            ))

    # ── Seniors ───────────────────────────────────────────────────────────────
    if senior_depts and frag_high.any():
        levers.append(_lever(
            "Seniors et autonomie", "Télésuivi seniors",
            _dept_list(frag_high & priorities["impact"].isin(["élevé", "majeur"])) or senior_depts,
            "Personnes âgées isolées",
            "Volume de seniors important et fragilité sanitaire élevée",
            "Croisement démographie et priorisation territoriale.",
            0.75,
        ))
        levers.append(_lever(
            "Seniors et autonomie", "Parcours gériatrique",
            senior_depts,
            "Seniors en perte d'autonomie",
            "Part des 65+ élevée et pression sur les parcours de soins",
            "Signal démographique régional au-dessus du seuil de vigilance.",
            0.68,
        ))

    # Dédupliquer par intitulé, trier par pertinence
    seen: set[str] = set()
    unique: list[dict] = []
    pert_order = {p: i for i, p in enumerate(PERTINENCE_LABELS)}
    for lev in sorted(levers, key=lambda x: pert_order.get(x["pertinence"], 0), reverse=True):
        if lev["intitule"] in seen or not lev["depts"]:
            continue
        seen.add(lev["intitule"])
        unique.append(lev)
    return unique[:8]
