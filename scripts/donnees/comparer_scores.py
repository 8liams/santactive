"""Compare les scores nationaux avant / après une correction de CSV candidate.

Aucun fichier de static/data n'est modifié : le CSV candidat est injecté à la
place de l'original le temps du calcul.

Usage (depuis la racine du dépôt) :
    python3 scripts/donnees/comparer_scores.py \\
        [--population data_corrections/population_corrigee.csv] \\
        [--etablissements data_corrections/etablissements_corrige.csv.gz] \\
        [--drees data_corrections/references/drees] \\
        [--sortie data_corrections/impact_scores_population.csv]
"""
from __future__ import annotations

import argparse
import logging
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[2]


def _scores(population: Path | None, etablissements: Path | None = None,
            drees: Path | None = None) -> pd.DataFrame:
    import app.config as cfg
    import app.data_loading as dl
    from app.scoring import compute_scores

    orig = dl.POP_PATH, dl.ETABS_PATH, dl.MEDECINS_DREES_PATH, dl.AUTRES_PS_DREES_PATH, dl.IDEL_DREES_PATH
    try:
        if population is not None:
            dl.POP_PATH = population
        if etablissements is not None:
            dl.ETABS_PATH = etablissements
        if drees is not None:  # dossier contenant les 3 extraits DREES
            dl.MEDECINS_DREES_PATH = drees / "drees_medecins_dept_2026.csv"
            dl.AUTRES_PS_DREES_PATH = drees / "drees_autres_rpps_dept_2026.csv"
            dl.IDEL_DREES_PATH = drees / "drees_infirmieres_liberales_dept_2023.csv"
        dl.load_all_data.clear(); dl.load_drees_ps.clear()
        master = dl.load_all_data()[0]
    finally:
        (dl.POP_PATH, dl.ETABS_PATH, dl.MEDECINS_DREES_PATH,
         dl.AUTRES_PS_DREES_PATH, dl.IDEL_DREES_PATH) = orig
        dl.load_all_data.clear(); dl.load_drees_ps.clear()
    s = compute_scores(master).set_index("dept")
    s = s.rename(columns={"nb_dimensions_ok": "nb_dim"})
    s["rang_affiche"] = s["nb_classes"] - s["rang_national"] + 1
    return s[["Nom du département", "nb_dim", "pct_plus_65", "densite", "typologie",
              "nb_med_gen", "med_gen_pour_100k", "score_medecins",
              "score_seniors", "score_global", "rang_affiche", "zone_short"]]


def main() -> None:
    import os
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--population", type=Path)
    ap.add_argument("--etablissements", type=Path)
    ap.add_argument("--drees", type=Path, help="dossier des extraits DREES (jeu A)")
    ap.add_argument("--sortie", type=Path)
    args = ap.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    avant = _scores(None)
    apres = _scores(
        args.population.resolve() if args.population else None,
        args.etablissements.resolve() if args.etablissements else None,
        args.drees.resolve() if args.drees else None,
    )
    cmp = avant.join(apres.drop(columns="Nom du département"), lsuffix="_avant", rsuffix="_apres")
    cmp["delta_score"] = (cmp["score_global_apres"] - cmp["score_global_avant"]).round(1)
    cmp["delta_rang"] = cmp["rang_affiche_apres"] - cmp["rang_affiche_avant"]
    chg = cmp[(cmp["delta_score"] != 0) | (cmp["zone_short_avant"] != cmp["zone_short_apres"])
              | (cmp["typologie_avant"] != cmp["typologie_apres"])]
    print(f"Départements dont le score, la zone ou la typologie change : {len(chg)}")
    print(f"Zones changées : {(cmp['zone_short_avant'] != cmp['zone_short_apres']).sum()}")
    cols = ["Nom du département", "nb_dim_avant", "nb_dim_apres", "med_gen_pour_100k_avant",
            "med_gen_pour_100k_apres", "score_medecins_avant", "score_medecins_apres",
            "score_global_avant", "score_global_apres", "rang_affiche_avant",
            "rang_affiche_apres", "zone_short_avant", "zone_short_apres"]
    print(chg.sort_values("delta_score")[cols].to_string())
    if args.sortie:
        cmp.to_csv(args.sortie)
        print(f"Écrit : {args.sortie}")


if __name__ == "__main__":
    main()
