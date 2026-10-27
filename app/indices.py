"""Deux indices complémentaires (prototype) : offre / accès et besoins sanitaires.

Indice OFFRE / ACCÈS (0-100, 100 = offre la plus favorable) : rangs
percentiles de l'APL pondérée (30), des généralistes /100k (20), des
structures /100k (15) et du temps d'accès (20) — les poids actuels du score,
renormalisés (le foncier et le vieillissement n'en font pas partie).

Indice BESOINS (0-100, 100 = besoins les plus forts) : moyenne à poids égaux
des rangs percentiles de la part des 65 ans et plus, et des prévalences
STANDARDISÉES sur l'âge (diabète, cardio-neuro-vasculaire, psychiatrie,
respiratoire) lorsque leur couverture est suffisante (≥ 90 % des poids d'âge),
sinon brutes (signalé). Poids égaux = choix explicite, faute de référence
validée.

Le score global n'est pas modifié ; cette lecture est un outil d'exploration.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .pathologies import dept_prevalences, dept_prevalences_standardisees
from .scoring import percentile_rank

OFFRE_POIDS = {"score_apl": 0.30, "score_medecins": 0.20, "score_etabs": 0.15, "score_temps": 0.20}
BESOINS_PATHOS = {
    "Diabète": "diabète", "Maladies cardioneurovasculaires": "cardio-neuro-vasculaire",
    "Maladies psychiatriques": "psychiatrie", "Maladies respiratoires chroniques (hors mucoviscidose)": "respiratoire",
}
QUADRANTS = {
    "A": "Offre faible · besoins forts", "B": "Offre faible · besoins modérés",
    "C": "Offre correcte · besoins forts", "D": "Offre correcte · besoins modérés",
}

_CACHE: dict[int, pd.DataFrame] = {}


def calculer_indices(master: pd.DataFrame, patho: pd.DataFrame | None) -> pd.DataFrame:
    key = id(master)
    if key in _CACHE:
        return _CACHE[key]
    m = master.set_index("dept").copy()
    w = pd.Series(OFFRE_POIDS)
    comp = m[list(OFFRE_POIDS)].astype(float)
    m["indice_offre"] = (comp.mul(w).sum(axis=1) / comp.notna().mul(w).sum(axis=1)).round(1)

    std = dept_prevalences_standardisees(patho, m.index)
    brut = dept_prevalences(patho, m.index)
    couv = std.attrs.get("couverture") if not std.empty else None
    comp_b = pd.DataFrame(index=m.index)
    comp_b["seniors"] = percentile_rank(m["pct_plus_65"].astype(float), higher_is_better=True)
    sources = {"seniors": "INSEE 2021"}
    for col, lab in BESOINS_PATHOS.items():
        serie, src = None, None
        if not std.empty and col in std.columns:
            s = std[col].reindex(m.index)
            if couv is not None and col in couv.columns:
                fiable = couv[col].reindex(m.index) >= 0.9
                if fiable.mean() >= 0.9:
                    serie, src = s.where(fiable), "CNAM 2023, standardisée"
        if serie is None and not brut.empty and col in brut.columns:
            serie, src = brut[col].reindex(m.index), "CNAM 2023, brute"
        if serie is not None:
            comp_b[lab] = percentile_rank(serie.astype(float), higher_is_better=True)
            sources[lab] = src
    m["indice_besoins"] = comp_b.mean(axis=1, skipna=True).round(1)
    for c in comp_b.columns:
        m[f"besoin_{c}"] = comp_b[c].round(1)
    o_med, b_med = m["indice_offre"].median(), m["indice_besoins"].median()
    m["quadrant"] = np.select(
        [(m["indice_offre"] < o_med) & (m["indice_besoins"] >= b_med),
         (m["indice_offre"] < o_med), (m["indice_besoins"] >= b_med)],
        ["A", "B", "C"], "D")
    m["quadrant_label"] = m["quadrant"].map(QUADRANTS)
    m.attrs["sources_besoins"] = sources
    m.attrs["medianes"] = (float(o_med), float(b_med))
    _CACHE.clear(); _CACHE[key] = m
    return m


def expliquer(dept: str, ind: pd.DataFrame) -> dict:
    """Composantes qui positionnent un département (rangs percentiles)."""
    r = ind.loc[dept]
    offre = {k: float(r[k]) for k in OFFRE_POIDS if pd.notna(r.get(k))}
    besoins = {c.replace("besoin_", ""): float(r[c]) for c in ind.columns if c.startswith("besoin_") and pd.notna(r[c])}
    return {
        "nom": str(r["Nom du département"]), "quadrant": QUADRANTS[r["quadrant"]],
        "indice_offre": float(r["indice_offre"]), "indice_besoins": float(r["indice_besoins"]),
        "offre": offre, "besoins": besoins,
        "offre_faible": sorted(offre, key=offre.get)[:2], "besoins_forts": sorted(besoins, key=besoins.get, reverse=True)[:2],
        "sources": ind.attrs.get("sources_besoins", {}),
    }
