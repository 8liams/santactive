"""Projection indicative d'impact pour les leviers d'action territoriaux.

Estimations prudentes à partir des données déjà chargées (INSEE, CNAM, APL, etc.).
Sans prédiction médicale — réutilisable fiche département et, ultérieurement, région.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import PATHOS_EXCLUDED

HORIZON_COURT = "Court terme"
HORIZON_MOYEN = "Moyen terme"
HORIZON_LONG = "Long terme"


@dataclass(frozen=True)
class LevierImpactProjection:
    """Projection d'échelle pour un levier sur un territoire."""

    public: str
    population: str  # libellé affiché, ex. « 18 500 personnes » ou « n.d. »
    horizon: str


@dataclass(frozen=True)
class LevierAmplitudeRegion:
    """Projection territoriale indicative pour un levier à l'échelle régionale."""

    territoires: str
    public: str
    population: str  # ex. « 125 000 habitants », « n.d. »
    horizon: str


def _num(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def _fmt_pop(n: int | None) -> str:
    if n is None or n <= 0:
        return "n.d."
    return f"{int(n):,}".replace(",", "\u202f") + " personnes"


def _dept_patho_ntop(
    patho: pd.DataFrame | None,
    dept: str,
    fragment: str,
) -> int | None:
    """Somme Ntop CNAM pour un fragment patho_niv1 sur un département."""
    if patho is None or patho.empty or "_error" in patho.columns:
        return None
    code = str(dept).zfill(2)
    dp = patho.copy()
    dp["dept"] = dp["dept"].astype(str).str.zfill(2)
    dp = dp[
        (dp["dept"] == code)
        & (~dp["patho_niv1"].isin(PATHOS_EXCLUDED))
        & dp["patho_niv1"].str.contains(fragment, case=False, na=False, regex=False)
    ]
    if dp.empty:
        return None
    total = int(pd.to_numeric(dp["Ntop"], errors="coerce").fillna(0).sum())
    return total if total > 0 else None


def _pop_seniors(r: pd.Series) -> int | None:
    pop = _num(r.get("population_num"))
    pct = _num(r.get("pct_plus_65"))
    if pop <= 0 or pct <= 0:
        return None
    return int(pop * pct / 100)


def _pop_jeunes(r: pd.Series) -> int | None:
    pop = _num(r.get("population_num"))
    pct = _num(r.get("pct_moins_25"))
    if pop <= 0 or pct <= 0:
        return None
    return int(pop * pct / 100)


def _pop_communes_eloignees(r: pd.Series) -> int | None:
    """Estimation prudente : part des communes > 15 min × population × 0,7."""
    pop = _num(r.get("population_num"))
    nb_crit = int(_num(r.get("nb_communes_critiques")))
    nb_total = int(_num(r.get("nb_communes")))
    if pop <= 0 or nb_crit <= 0 or nb_total <= 0:
        return None
    ratio = min(nb_crit / nb_total, 1.0)
    return max(1, int(pop * ratio * 0.7))


def _pop_acces_ville_contraint(r: pd.Series) -> int | None:
    """Population potentiellement pénalisée par un APL bas ou un accès dégradé."""
    pop = _num(r.get("population_num"))
    if pop <= 0:
        return None
    apl = _num(r.get("apl_median_dept"), default=2.9)
    score_acces = _num(r.get("score_acces"), default=50.0)
    if apl >= 2.9 and score_acces >= 45:
        return None
    if apl < 2.9:
        share = min(max(0.0, (2.9 - apl) / 2.9), 0.95)
        return max(1, int(pop * share * 0.75))
    return max(1, int(pop * 0.12))


def _pop_mobilite_limitee(r: pd.Series) -> int | None:
    """Navettes : seniors + part des communes isolées (double comptage évité — max)."""
    seniors = _pop_seniors(r)
    iso = _pop_communes_eloignees(r)
    if seniors is None and iso is None:
        return None
    if seniors is None:
        return iso
    if iso is None:
        return max(1, int(seniors * 0.35))
    return max(1, int(max(seniors * 0.35, iso * 0.5)))


def _classify_levier(title: str) -> str:
    t = title.lower()
    if "maison de santé" in t or "msp" in t:
        return "msp"
    if "télémédecine" in t or "telemedecine" in t or "consultations avancées" in t:
        return "telemedecine"
    if "attractivité" in t and "généralistes" in t:
        return "attractivite_mg"
    if "seniors isolés" in t or "santé numérique pour les seniors" in t:
        return "seniors_numerique"
    if "antennes" in t:
        return "antennes"
    if "navettes" in t:
        return "navettes"
    if "prévention" in t and "chroniques" in t:
        return "prevention_chroniques"
    if "pédiatrique" in t or "pediatrique" in t or "pmi" in t:
        return "pediatrie"
    if "foncier" in t:
        return "foncier"
    if "vigilance" in t:
        return "vigilance"
    if "maintenir" in t or "acquis" in t:
        return "maintien"
    return "generique"


def _prevention_chroniques_public_and_pop(
    reco: dict,
    r: pd.Series,
    patho: pd.DataFrame | None,
) -> tuple[str, int | None]:
    dept = str(r.get("dept", "")).zfill(2)
    title = reco.get("title", "").lower()
    stats = reco.get("stats") or []

    cardio_ntop = _dept_patho_ntop(patho, dept, "cardio")
    diab_ntop = _dept_patho_ntop(patho, dept, "iabète")

    # Inférer la pathologie dominante depuis les stats ou les volumes CNAM
    patho_hint = ""
    for val, lbl in stats:
        lbl_l = str(lbl).lower()
        if "cardio" in lbl_l:
            patho_hint = "cardio"
        elif "diab" in lbl_l:
            patho_hint = "diabete"

    if patho_hint == "cardio" or (cardio_ntop or 0) >= (diab_ntop or 0):
        if cardio_ntop:
            return "Patients cardiovasculaires", cardio_ntop
        if diab_ntop:
            return "Patients diabétiques", diab_ntop
        return "Patients atteints de pathologies chroniques", None

    if diab_ntop:
        return "Patients diabétiques", diab_ntop
    if cardio_ntop:
        return "Patients cardiovasculaires", cardio_ntop
    return "Patients atteints de pathologies chroniques", None


def project_levier_impact(
    reco: dict,
    r: pd.Series,
    data: dict | None = None,
) -> LevierImpactProjection:
    """Projette public, population et horizon pour un levier recommandé.

    Parameters
    ----------
    reco : dict
        Recommandation telle que retournée par ``_generate_recommendations``.
    r : pd.Series
        Ligne ``master`` du département.
    data : dict, optional
        Dictionnaire applicatif (``patho``, etc.).

    Returns
    -------
    LevierImpactProjection
    """
    data = data or {}
    patho = data.get("patho")
    kind = _classify_levier(reco.get("title", ""))

    if kind == "msp":
        return LevierImpactProjection(
            public="Habitants des communes éloignées des établissements",
            population=_fmt_pop(_pop_communes_eloignees(r) or _pop_acces_ville_contraint(r)),
            horizon=HORIZON_LONG,
        )

    if kind == "telemedecine":
        return LevierImpactProjection(
            public="Habitants éloignés des spécialistes",
            population=_fmt_pop(_pop_acces_ville_contraint(r)),
            horizon=HORIZON_COURT,
        )

    if kind == "attractivite_mg":
        pop_est = _pop_acces_ville_contraint(r)
        if pop_est is None and _num(r.get("score_pros"), 50) < 45:
            pop_est = max(1, int(_num(r.get("population_num")) * 0.08))
        return LevierImpactProjection(
            public="Population avec accès aux soins de ville contraint",
            population=_fmt_pop(pop_est),
            horizon=HORIZON_LONG,
        )

    if kind == "seniors_numerique":
        return LevierImpactProjection(
            public="Seniors (65 ans et plus)",
            population=_fmt_pop(_pop_seniors(r)),
            horizon=HORIZON_MOYEN,
        )

    if kind == "antennes":
        return LevierImpactProjection(
            public="Habitants éloignés des établissements",
            population=_fmt_pop(_pop_communes_eloignees(r)),
            horizon=HORIZON_MOYEN,
        )

    if kind == "navettes":
        return LevierImpactProjection(
            public="Personnes sans mobilité vers les soins",
            population=_fmt_pop(_pop_mobilite_limitee(r)),
            horizon=HORIZON_COURT,
        )

    if kind == "prevention_chroniques":
        public, ntop = _prevention_chroniques_public_and_pop(reco, r, patho)
        return LevierImpactProjection(
            public=public,
            population=_fmt_pop(ntop),
            horizon=HORIZON_COURT,
        )

    if kind == "pediatrie":
        return LevierImpactProjection(
            public="Enfants et jeunes de moins de 25 ans",
            population=_fmt_pop(_pop_jeunes(r)),
            horizon=HORIZON_MOYEN,
        )

    if kind == "foncier":
        return LevierImpactProjection(
            public="Professionnels de santé candidats à l'installation",
            population="n.d.",
            horizon=HORIZON_LONG,
        )

    if kind == "vigilance":
        return LevierImpactProjection(
            public="Population du territoire",
            population="n.d.",
            horizon=HORIZON_MOYEN,
        )

    if kind == "maintien":
        return LevierImpactProjection(
            public="Population du territoire",
            population="n.d.",
            horizon=HORIZON_LONG,
        )

    return LevierImpactProjection(
        public="Population du territoire",
        population="n.d.",
        horizon=HORIZON_MOYEN,
    )


def render_impact_html(projection: LevierImpactProjection) -> str:
    """HTML léger pour l'encart « Impact potentiel » (styles ``reco-impact``)."""
    return (
        '<div class="reco-impact">'
        '<div class="reco-impact-title">Impact potentiel</div>'
        '<div class="reco-impact-grid">'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Public concerné</span>'
        f'<span class="reco-impact-val">{projection.public}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Population potentiellement concernée</span>'
        f'<span class="reco-impact-val">{projection.population}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Horizon</span>'
        f'<span class="reco-impact-val">{projection.horizon}</span>'
        '</div>'
        '</div>'
        '</div>'
    )


# ── Projection régionale ──────────────────────────────────────────────────────


def _fmt_amplitude(n: int | None, suffix: str = "personnes") -> str:
    if n is None or n <= 0:
        return "n.d."
    return f"{int(n):,}".replace(",", "\u202f") + f" {suffix}"


def _classify_levier_region(intitule: str, famille: str = "") -> str:
    """Identifie le type de levier régional à partir de son intitulé."""
    t = intitule.lower()
    if "cardiovasculaire" in t:
        return "prevention_cardio"
    if "diabète" in t or "diabete" in t:
        return "depistage_diabete"
    if "santé mentale" in t or "sante mentale" in t:
        return "sante_mentale"
    if "fragilité seniors" in t or "fragilite seniors" in t:
        return "prevention_seniors"
    if "respiratoire" in t:
        return "prevention_respiratoire"
    if "téléexpertise" in t or "teleexpertise" in t:
        return "teleexpertise"
    if "téléconsultation" in t or "teleconsultation" in t:
        return "teleconsultation"
    if "télésuivi des patients chroniques" in t or "telesuivi des patients" in t:
        return "telesuivi_chroniques"
    if "télésuivi seniors" in t or "telesuivi seniors" in t:
        return "telesuivi_seniors"
    if "parcours gériatrique" in t or "parcours geriatrique" in t:
        return "parcours_geriatrique"
    if "ville-hôpital" in t or "ville-hopital" in t:
        return "parcours_ville_hopital"
    if "maladies chroniques" in t:
        return "parcours_chroniques"
    if "consultations avancées" in t or "consultations avancees" in t:
        return "consultations_avancees"
    if "navettes" in t:
        return "navettes"
    return "generique"


def _format_territoires_region(dept_names: list[str], nb_region_depts: int) -> str:
    if not dept_names:
        return "n.d."
    seuil = max(3, int(nb_region_depts * 0.75))
    if len(dept_names) >= seuil:
        return "Plusieurs départements de la région"
    return ", ".join(dept_names[:3])


def _rows_for_levier_depts(
    region_depts: pd.DataFrame,
    dept_names: list[str],
) -> pd.DataFrame:
    if not dept_names:
        return region_depts
    matched = region_depts[
        region_depts["Nom du département"].astype(str).isin(dept_names)
    ]
    return matched if not matched.empty else region_depts


def _sum_patho_ntop(
    patho: pd.DataFrame | None,
    dept_codes: list[str],
    fragment: str,
) -> int | None:
    total = 0
    found = False
    for code in dept_codes:
        n = _dept_patho_ntop(patho, code, fragment)
        if n:
            total += n
            found = True
    return total if found else None


def _sum_across_rows(
    rows: pd.DataFrame,
    fn,
) -> int | None:
    total = 0
    found = False
    for _, row in rows.iterrows():
        n = fn(row)
        if n:
            total += n
            found = True
    return total if found else None


def _public_region(kind: str, public_cible: str) -> str:
    mapping = {
        "prevention_cardio": "Patients cardiovasculaires",
        "depistage_diabete": "Patients diabétiques",
        "sante_mentale": "Patients en santé mentale",
        "prevention_seniors": "Seniors",
        "prevention_respiratoire": "Patients respiratoires",
        "teleexpertise": "Population éloignée des spécialistes",
        "teleconsultation": "Population éloignée des spécialistes",
        "telesuivi_chroniques": "Patients chroniques",
        "telesuivi_seniors": "Seniors",
        "parcours_geriatrique": "Seniors",
        "parcours_ville_hopital": "Patients en parcours complexe",
        "parcours_chroniques": "Patients atteints de pathologies chroniques",
        "consultations_avancees": "Habitants éloignés des établissements",
        "navettes": "Personnes sans mobilité vers les soins",
    }
    return mapping.get(kind, public_cible.split("(")[0].strip() or "Population du territoire")


def _horizon_region(kind: str) -> str:
    court = {
        "prevention_cardio", "depistage_diabete", "sante_mentale",
        "prevention_respiratoire", "teleexpertise", "teleconsultation", "navettes",
    }
    long = set()  # pas de levier MSP explicite au niveau régional actuel
    if kind in court:
        return HORIZON_COURT
    if kind in long:
        return HORIZON_LONG
    return HORIZON_MOYEN


def _population_region(
    kind: str,
    rows: pd.DataFrame,
    patho: pd.DataFrame | None,
) -> str:
    codes = rows["dept"].astype(str).str.zfill(2).tolist()

    if kind == "prevention_cardio":
        return _fmt_amplitude(_sum_patho_ntop(patho, codes, "cardio"), "patients cardiovasculaires")
    if kind == "depistage_diabete":
        return _fmt_amplitude(_sum_patho_ntop(patho, codes, "iabète"), "patients diabétiques")
    if kind == "sante_mentale":
        return _fmt_amplitude(_sum_patho_ntop(patho, codes, "sychiatr"), "personnes")
    if kind == "prevention_respiratoire":
        return _fmt_amplitude(_sum_patho_ntop(patho, codes, "espira"), "patients respiratoires")
    if kind in ("prevention_seniors", "telesuivi_seniors", "parcours_geriatrique"):
        return _fmt_amplitude(_sum_across_rows(rows, _pop_seniors), "seniors")
    if kind in ("teleexpertise", "teleconsultation"):
        pop = _sum_across_rows(rows, _pop_acces_ville_contraint)
        if pop is None:
            pop = max(1, int(rows["population_num"].apply(_num).sum() * 0.12))
        return _fmt_amplitude(pop, "habitants")
    if kind == "navettes":
        return _fmt_amplitude(_sum_across_rows(rows, _pop_mobilite_limitee), "personnes")
    if kind == "consultations_avancees":
        return _fmt_amplitude(
            _sum_across_rows(rows, _pop_communes_eloignees),
            "habitants",
        )
    if kind in ("telesuivi_chroniques", "parcours_chroniques", "parcours_ville_hopital"):
        pop = _sum_across_rows(rows, _pop_acces_ville_contraint)
        if pop is None:
            pop = int(rows["population_num"].apply(_num).sum() * 0.15)
        return _fmt_amplitude(pop, "personnes")
    pop = int(rows["population_num"].apply(_num).sum() * 0.10)
    return _fmt_amplitude(pop if pop > 0 else None, "habitants")


def project_levier_amplitude_region(
    levier: dict,
    region_depts: pd.DataFrame,
    data: dict | None = None,
    region_name: str = "",
) -> LevierAmplitudeRegion:
    """Projette l'amplitude territoriale d'un levier régional.

    Parameters
    ----------
    levier : dict
        Levier retourné par ``compute_leviers_action``.
    region_depts : pd.DataFrame
        Sous-ensemble ``master`` des départements de la région.
    data : dict, optional
        Dictionnaire applicatif (``patho``, etc.).
    region_name : str
        Libellé région (informatif, non utilisé dans le calcul).

    Returns
    -------
    LevierAmplitudeRegion
    """
    _ = region_name
    data = data or {}
    patho = data.get("patho")
    dept_names = list(levier.get("depts") or [])
    intitule = str(levier.get("intitule", ""))
    famille = str(levier.get("famille", ""))
    public_cible = str(levier.get("public_cible", ""))

    kind = _classify_levier_region(intitule, famille)
    rows = _rows_for_levier_depts(region_depts, dept_names)
    nb_region = len(region_depts)

    return LevierAmplitudeRegion(
        territoires=_format_territoires_region(dept_names, nb_region),
        public=_public_region(kind, public_cible),
        population=_population_region(kind, rows, patho),
        horizon=_horizon_region(kind),
    )


def render_amplitude_region_html(amplitude: LevierAmplitudeRegion) -> str:
    """HTML pour l'encart « Amplitude potentielle de l'action » (styles ``reco-impact``)."""
    return (
        '<div class="reco-impact">'
        '<div class="reco-impact-title">Amplitude potentielle de l\'action</div>'
        '<div class="reco-impact-grid">'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Départements concernés</span>'
        f'<span class="reco-impact-val">{amplitude.territoires}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Public principal</span>'
        f'<span class="reco-impact-val">{amplitude.public}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Population potentiellement concernée</span>'
        f'<span class="reco-impact-val">{amplitude.population}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Horizon</span>'
        f'<span class="reco-impact-val">{amplitude.horizon}</span>'
        '</div>'
        '</div>'
        '</div>'
    )
