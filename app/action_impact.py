"""Publics et volumes OBSERVÉS associés aux leviers d'action territoriaux.

Règles (révision du 28 octobre 2026) :
- la population cible est déduite de l'identifiant du levier du catalogue (``app/leviers.py``),
  jamais d'un mot du titre ;
- chaque volume est une quantité mesurée dans les données chargées, nommée avec sa source :
  habitants des communes sous le repère APL 2,5 (DREES), habitants à plus de 15 minutes d'un
  généraliste (INSEE 2025), personnes de 65 ans et plus ou de moins de 25 ans (INSEE RP 2021),
  patients pris en charge pour une pathologie (CNAM 2023) ;
- lorsqu'aucune donnée chargée ne décrit le public du levier (patients nécessitant un avis
  spécialisé, personnes de 50 à 74 ans, femmes enceintes, patientèle, personnes âgées sans
  véhicule…), la population est déclarée « non quantifiable avec les données disponibles »
  plutôt qu'approchée par une autre population ;
- arrondi à l'entier le plus proche, identique à celui des textes des leviers, des PDF et des
  e-mails (``round``), jamais une troncature.

Ce n'est jamais une prédiction d'effet de l'action.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import APL_MILLESIME, PATHOS_EXCLUDED

HORIZON_COURT = "Court terme"
HORIZON_MOYEN = "Moyen terme"
HORIZON_LONG = "Long terme"

NON_QUANTIFIABLE = "population cible non quantifiable avec les données disponibles"


@dataclass(frozen=True)
class LevierImpactProjection:
    """Public et volume observé pour un levier sur un département."""

    public: str
    population: str   # libellé affiché, ex. « 7 880 patients suivis pour troubles psychiatriques (CNAM 2023) »
    horizon: str
    quantifie: bool = True


@dataclass(frozen=True)
class LevierAmplitudeRegion:
    """Public et volume observé pour un levier à l'échelle régionale."""

    territoires: str
    public: str
    population: str
    horizon: str
    quantifie: bool = True


# ── Helpers numériques ────────────────────────────────────────────────────────
def _num(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        return v if pd.notna(v) else default
    except (TypeError, ValueError):
        return default


def arrondi(v) -> int | None:
    """Entier le plus proche (jamais une troncature) ; None si absent ou nul."""
    x = _num(v, default=float("nan"))
    if pd.isna(x) or x <= 0:
        return None
    return int(round(x))


def _fmt_n(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def _fmt(n: int | None, unite: str) -> str:
    return NON_QUANTIFIABLE if n is None else f"{_fmt_n(n)} {unite}"


# ── Volumes observés par département ─────────────────────────────────────────
def pop_sous_apl(r: pd.Series) -> int | None:
    """Habitants des communes dont l'APL est sous le repère 2,5 (DREES) : population × part, arrondie."""
    pop = _num(r.get("population_num"))
    part = _num(r.get("part_pop_apl_inf_2_5"), default=float("nan"))
    if pop <= 0 or pd.isna(part) or part <= 0:
        return None
    return arrondi(pop * part)


def pop_plus_15_min(r: pd.Series) -> int | None:
    """Habitants à plus de 15 minutes en voiture d'un généraliste : INSEE 2025 ; repli sur l'indicateur interne."""
    v = arrondi(r.get("acces_mg_pop_sup_15"))
    if v is None:
        v = arrondi(r.get("pop_communes_critiques"))
    return v


def pop_seniors(r: pd.Series) -> int | None:
    pop, pct = _num(r.get("population_num")), _num(r.get("pct_plus_65"))
    return arrondi(pop * pct / 100) if pop > 0 and pct > 0 else None


def pop_jeunes(r: pd.Series) -> int | None:
    pop, pct = _num(r.get("population_num")), _num(r.get("pct_moins_25"))
    return arrondi(pop * pct / 100) if pop > 0 and pct > 0 else None


def patients_cnam(patho: pd.DataFrame | None, dept: str, fragment: str) -> int | None:
    """Patients pris en charge (Ntop CNAM) pour les pathologies dont le libellé contient ``fragment``."""
    if patho is None or patho.empty or "_error" in patho.columns:
        return None
    from .pathologies import patho_agg

    code = str(dept).zfill(2)
    g = patho_agg(patho)
    if code not in g.index.get_level_values("dept"):
        return None
    d = g.loc[code]
    mask = d.index.str.contains(fragment, case=False, regex=False) & ~d.index.isin(PATHOS_EXCLUDED)
    total = int(pd.to_numeric(d.loc[mask, "Ntop"], errors="coerce").fillna(0).sum())
    return total if total > 0 else None


# ── Population cible par levier (source unique, département et région) ───────
# Fragments de libellés CNAM (patho_niv1) utilisés pour les leviers de pathologie.
FRAGMENT_CNAM = {"sante_mentale": "sychiatr", "cardio": "ardio", "diabete": "iabète"}

# Unités affichées, avec la source, pour chaque mode de quantification.
_UNITES = {
    "apl": f"habitants de communes sous le repère APL 2,5 (DREES {APL_MILLESIME})",
    "15min": "habitants à plus de 15 min d'un généraliste (INSEE 2025)",
    "seniors": "personnes de 65 ans et plus (INSEE RP 2021)",
    "jeunes": "personnes de moins de 25 ans (INSEE RP 2021)",
    "sante_mentale": "patients suivis pour troubles psychiatriques (CNAM 2023)",
    "cardio": "patients suivis pour maladies cardio-neuro-vasculaires (CNAM 2023)",
    "diabete": "patients suivis pour diabète (CNAM 2023)",
}

# Mode de quantification par identifiant de levier ; None = non quantifiable.
MODE_PAR_LEVIER: dict[str, str | None] = {
    "msp": "apl",
    "attractivite": "apl",
    "teleconsultation": "apl",
    "equipes_mobiles": "15min",
    "autonomie": "seniors",
    "pediatrie": "jeunes",
    "sante_mentale": "sante_mentale",
    "cardio": "cardio",
    "diabete": "diabete",
    # Publics que les données chargées ne décrivent pas : on ne substitue aucune autre population.
    "assistants": None,       # patientèle des généralistes
    "sas": None,              # population urbaine recourant aux soins non programmés
    "consult_avancees": None, # patients nécessitant un avis spécialisé
    "teleexpertise": None,    # patients en attente d'un avis spécialisé
    "depistages": None,       # personnes de 50 à 74 ans (tranche absente du recensement chargé)
    "perinatalite": None,     # femmes enceintes, jeunes enfants
    "chroniques": None,       # patients chroniques toutes pathologies (doubles comptes CNAM)
    "mobilite": None,         # personnes âgées sans véhicule des communes éloignées
    "mediation": None,        # habitants des quartiers à faible recours
    "ville_hopital": None,    # patients en parcours complexe
    "dom": None,
    "maintien": None,
    "vigilance": None,
}


def _volume_dept(mode: str | None, r: pd.Series, patho: pd.DataFrame | None) -> int | None:
    if mode is None:
        return None
    dept = str(r.get("dept", "")).zfill(2)
    if mode == "apl":
        return pop_sous_apl(r)
    if mode == "15min":
        return pop_plus_15_min(r)
    if mode == "seniors":
        return pop_seniors(r)
    if mode == "jeunes":
        return pop_jeunes(r)
    if mode in FRAGMENT_CNAM:
        return patients_cnam(patho, dept, FRAGMENT_CNAM[mode])
    return None


def population_cible(levier_id: str, r: pd.Series, patho: pd.DataFrame | None = None) -> tuple[str, bool]:
    """(libellé, quantifié) de la population cible d'un levier pour un département."""
    mode = MODE_PAR_LEVIER.get(levier_id)
    if mode is None:
        return NON_QUANTIFIABLE, False
    n = _volume_dept(mode, r, patho)
    if n is None:
        return NON_QUANTIFIABLE, False
    return _fmt(n, _UNITES[mode]), True


def project_levier_impact(reco: dict, r: pd.Series, data: dict | None = None) -> LevierImpactProjection:
    """Public (celui du catalogue), population cible observée et horizon d'un levier recommandé."""
    data = data or {}
    levier_id = str(reco.get("id", "") or "")
    label, ok = population_cible(levier_id, r, data.get("patho"))
    return LevierImpactProjection(
        public=str(reco.get("public") or "Population du territoire"),
        population=label,
        horizon=str(reco.get("horizon") or HORIZON_MOYEN),
        quantifie=ok,
    )


def render_impact_html(projection: LevierImpactProjection) -> str:
    """HTML léger pour l'encart « Public et volume observés » (styles ``reco-impact``)."""
    return (
        '<div class="reco-impact">'
        '<div class="reco-impact-title">Public et population cible</div>'
        '<div class="reco-impact-grid">'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Public concerné</span>'
        f'<span class="reco-impact-val">{projection.public}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Population cible observée</span>'
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
def _format_territoires_region(dept_names: list[str], nb_region_depts: int) -> str:
    if not dept_names:
        return "n.d."
    seuil = max(3, int(nb_region_depts * 0.75))
    if len(dept_names) >= seuil:
        return "Plusieurs départements de la région"
    return ", ".join(dept_names[:3])


def _rows_for_levier_depts(region_depts: pd.DataFrame, dept_names: list[str]) -> pd.DataFrame:
    if not dept_names:
        return region_depts
    matched = region_depts[region_depts["Nom du département"].astype(str).isin(dept_names)]
    return matched if not matched.empty else region_depts


def population_cible_region(levier_id: str, rows: pd.DataFrame, patho: pd.DataFrame | None = None) -> tuple[str, bool]:
    """Somme des volumes départementaux (même règle qu'au niveau département) sur les départements ciblés."""
    mode = MODE_PAR_LEVIER.get(levier_id)
    if mode is None:
        return NON_QUANTIFIABLE, False
    total, found = 0, False
    for _, row in rows.iterrows():
        n = _volume_dept(mode, row, patho)
        if n:
            total += n
            found = True
    if not found:
        return NON_QUANTIFIABLE, False
    return _fmt(total, _UNITES[mode]), True


def project_levier_amplitude_region(levier: dict, region_depts: pd.DataFrame, data: dict | None = None,
                                    region_name: str = "") -> LevierAmplitudeRegion:
    """Départements concernés, public du catalogue, population cible observée et horizon d'un levier régional."""
    _ = region_name
    data = data or {}
    dept_names = list(levier.get("depts") or [])
    rows = _rows_for_levier_depts(region_depts, dept_names)
    label, ok = population_cible_region(str(levier.get("id", "") or ""), rows, data.get("patho"))
    public = str(levier.get("public_cible") or levier.get("public") or "Population du territoire").split("(")[0].strip()
    return LevierAmplitudeRegion(
        territoires=_format_territoires_region(dept_names, len(region_depts)),
        public=public or "Population du territoire",
        population=label,
        horizon=str(levier.get("horizon") or HORIZON_MOYEN),
        quantifie=ok,
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
        '<span class="reco-impact-lbl">Population cible observée</span>'
        f'<span class="reco-impact-val">{amplitude.population}</span>'
        '</div>'
        '<div class="reco-impact-item">'
        '<span class="reco-impact-lbl">Horizon</span>'
        f'<span class="reco-impact-val">{amplitude.horizon}</span>'
        '</div>'
        '</div>'
        '</div>'
    )
