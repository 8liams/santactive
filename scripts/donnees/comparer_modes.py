"""Compare les scores nationaux entre deux configurations du moteur.

Chaque configuration est exécutée dans un sous-processus avec ses variables
d'environnement (SANTACTIVE_SOURCE_EFFECTIFS, SANTACTIVE_APL_METHODE,
SANTACTIVE_ETABS_DEFINITION), ce qui garantit que config.py est bien relu.

Usage (depuis la racine) :
    python3 scripts/donnees/comparer_modes.py \\
        --avant SANTACTIVE_APL_METHODE=mediane --apres SANTACTIVE_APL_METHODE=ponderee \\
        [--sortie data_corrections/impact_apl_ponderee.csv]
Sans --avant, la référence est la configuration par défaut.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
COLS = ["Nom du département", "apl_dept", "med_gen_pour_100k", "structures_pour_100k",
        "score_apl", "score_medecins", "score_etabs", "score_global", "rang_affiche", "zone_short"]
_DUMP = """
import json, logging, warnings, sys; warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)
from app.data_loading import load_all_data
from app.scoring import compute_scores
m = compute_scores(load_all_data()[0]).set_index("dept")
m["rang_affiche"] = m["nb_classes"] - m["rang_national"] + 1
m[%r].to_json(sys.argv[1], orient="index", force_ascii=False)
""" % (COLS,)


def scores(env_pairs: list[str], out: Path) -> pd.DataFrame:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for kv in env_pairs:
        k, v = kv.split("=", 1)
        env[k] = v
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run([sys.executable, "-c", _DUMP, str(out)], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("Échec du calcul pour " + str(env_pairs) + " :\n" + r.stderr[-2000:])
    df = pd.read_json(out, orient="index", convert_dates=False)
    df.index = df.index.astype(str).str.zfill(2)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--avant", nargs="*", default=[])
    ap.add_argument("--apres", nargs="+", required=True)
    ap.add_argument("--sortie", type=Path)
    args = ap.parse_args()
    tmp = ROOT / "data_corrections" / ".tmp_scores"
    tmp.mkdir(exist_ok=True)
    a = scores(args.avant, tmp / "avant.json")
    b = scores(args.apres, tmp / "apres.json")
    cmp = a.join(b.drop(columns="Nom du département"), lsuffix="_avant", rsuffix="_apres")
    cmp["delta_score"] = (cmp["score_global_apres"] - cmp["score_global_avant"]).round(1)
    cmp["delta_rang"] = cmp["rang_affiche_apres"] - cmp["rang_affiche_avant"]
    zones = cmp[cmp["zone_short_avant"] != cmp["zone_short_apres"]]
    print(f"Configuration : avant={args.avant or 'défaut'} · après={args.apres}")
    print(f"Zones changées : {len(zones)} · |Δrang| médian : {cmp['delta_rang'].abs().median()} · max : "
          f"{cmp['delta_rang'].abs().max()} ({cmp['delta_rang'].abs().idxmax()})")
    show = ["Nom du département", "score_global_avant", "score_global_apres",
            "rang_affiche_avant", "rang_affiche_apres", "zone_short_avant", "zone_short_apres"]
    print(zones[show].to_string())
    print("\nPlus grands écarts de rang :")
    print(cmp.reindex(cmp["delta_rang"].abs().sort_values(ascending=False).index).head(10)[show].to_string())
    if args.sortie:
        cmp.to_csv(args.sortie)
        print("Écrit :", args.sortie)


if __name__ == "__main__":
    main()
