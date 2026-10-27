"""Simulation (étude, non appliquée) de deux indices complémentaires.

Indice OFFRE / ACCÈS : APL (30), médecins généralistes /100k (20),
structures /100k (15), temps d'accès (20) → poids actuels renormalisés.
Indice BESOINS : part des 65+ (10), prévalence brute cardio-neuro-vasculaire,
diabète, psychiatrie (CNAM 2023), part des moins de 25 ans → percentiles,
moyenne simple (poids égaux faute de référence validée).
Le foncier (5 %) n'entre dans aucun des deux (contexte d'installation).

Usage : python3 scripts/analyse/simulation_indices.py [--drees DOSSIER]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore"); logging.getLogger("streamlit").setLevel(logging.ERROR)
ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--drees", type=Path)
    ap.add_argument("--standardise", action="store_true", help="prévalences standardisées sur l'âge")
    args = ap.parse_args()
    os.chdir(ROOT); sys.path.insert(0, str(ROOT))
    import app.data_loading as dl
    from app.pathologies import dept_prevalences, dept_prevalences_standardisees
    from app.scoring import compute_scores, percentile_rank

    if args.drees:
        dl.MEDECINS_DREES_PATH = args.drees / "drees_medecins_dept_2026.csv"
        dl.AUTRES_PS_DREES_PATH = args.drees / "drees_autres_rpps_dept_2026.csv"
        dl.IDEL_DREES_PATH = args.drees / "drees_infirmieres_liberales_dept_2023.csv"
        dl.load_all_data.clear(); dl.load_drees_ps.clear()
    master, *_rest = dl.load_all_data()
    patho = _rest[5]
    m = compute_scores(master).set_index("dept")

    offre_w = {"score_apl": .30, "score_medecins": .20, "score_etabs": .15, "score_temps": .20}
    w = pd.Series(offre_w)
    comp = m[list(offre_w)]
    m["indice_offre"] = (comp.mul(w).sum(axis=1) / comp.notna().mul(w).sum(axis=1)).round(1)

    prev = (dept_prevalences_standardisees(patho, m.index) if args.standardise
            else dept_prevalences(patho, m.index))
    print("Prévalences :", "standardisées sur l'âge" if args.standardise else "brutes")
    cols = {"Maladies cardioneurovasculaires": "cardio", "Diabète": "diabete", "Maladies psychiatriques": "psy"}
    bes = pd.DataFrame(index=m.index)
    bes["seniors"] = percentile_rank(m["pct_plus_65"], higher_is_better=True)
    bes["jeunes"] = percentile_rank(m["pct_moins_25"], higher_is_better=True)
    for c, k in cols.items():
        bes[k] = percentile_rank(prev[c].reindex(m.index), higher_is_better=True)
    m["indice_besoins"] = bes.mean(axis=1, skipna=True).round(1)   # 100 = besoins les plus forts

    print("Corrélation Spearman offre ~ besoins :", round(m[["indice_offre", "indice_besoins"]].corr("spearman").iloc[0, 1], 3))
    print("Corrélation score global ~ offre :", round(m[["score_global", "indice_offre"]].corr("spearman").iloc[0, 1], 3),
          "| score global ~ besoins (inversé) :", round(-m[["score_global", "indice_besoins"]].corr("spearman").iloc[0, 1], 3))
    print("Corrélations internes besoins :"); print(bes.corr("spearman").round(2).to_string())
    o_med, b_med = m["indice_offre"].median(), m["indice_besoins"].median()
    m["quadrant"] = np.select(
        [(m.indice_offre < o_med) & (m.indice_besoins >= b_med), (m.indice_offre < o_med),
         (m.indice_besoins >= b_med)],
        ["offre faible · besoins forts", "offre faible · besoins modérés", "offre correcte · besoins forts"],
        "offre correcte · besoins modérés")
    print("\nRépartition :"); print(m["quadrant"].value_counts().to_string())
    sel = ["75", "93", "23", "48", "2A", "2B", "973", "974", "18", "45", "59", "62", "06", "70"]
    print(m.loc[sel, ["Nom du département", "score_global", "zone_short", "indice_offre", "indice_besoins", "quadrant"]].to_string())
    print("\nOffre faible · besoins forts (priorité « double peine ») :")
    q = m[m.quadrant == "offre faible · besoins forts"].sort_values("indice_offre")
    print(q[["Nom du département", "score_global", "zone_short", "indice_offre", "indice_besoins"]].to_string())
    out = ROOT / "data_corrections" / ("simulation_indices_std.csv" if args.standardise else "simulation_indices.csv")
    m[["Nom du département", "score_global", "zone_short", "indice_offre", "indice_besoins", "quadrant"]].to_csv(out)
    print("Écrit :", out)


if __name__ == "__main__":
    main()
