"""Analyse de sensibilité : remplacer l'indicateur interne de temps d'accès par
l'indicateur INSEE 2025 dans la dimension « temps » (20 %) du score global.

Variantes calculées (pondérations inchangées) :
  A. production : médiane communale interne (0 = généraliste présent) ;
  B. INSEE, médiane pondérée par la population du temps vers le généraliste le
     plus proche (acces_mg_t_med) ;
  C. INSEE, part de la population à plus de 15 min (acces_mg_part_sup_15).
Pour chaque variante : score global, rang, zone ; écarts de rang, changements de
zone, départements les plus affectés, corrélations entre indicateurs.

Usage : python3 scripts/analyse/sensibilite_temps_acces.py
Sortie : data_corrections/references/insee_acces/sensibilite_temps_acces.csv (+ résumé console)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> None:
    import os
    os.chdir(ROOT)
    from app.data_loading import load_all_data
    from app.scoring import compute_scores

    master = load_all_data()[0]
    base = compute_scores(master)
    out = base[["dept", "Nom du département", "temps_acces_median", "acces_mg_t_med", "acces_mg_part_sup_15",
                "score_global", "rang_national", "zone_short"]].rename(
        columns={"score_global": "score_A", "rang_national": "rang_A", "zone_short": "zone_A"})
    variants = {"B": ("acces_mg_t_med", False), "C": ("acces_mg_part_sup_15", False)}
    for name, (col, _) in variants.items():
        m = master.copy()
        m["temps_acces_median"] = m[col]
        v = compute_scores(m)[["dept", "score_global", "rang_national", "zone_short"]].rename(
            columns={"score_global": f"score_{name}", "rang_national": f"rang_{name}", "zone_short": f"zone_{name}"})
        out = out.merge(v, on="dept", how="left")
        out[f"d_rang_{name}"] = out[f"rang_{name}"] - out["rang_A"]
        out[f"d_score_{name}"] = out[f"score_{name}"] - out["score_A"]
    dest = ROOT / "data_corrections" / "references" / "insee_acces" / "sensibilite_temps_acces.csv"
    out.round(3).to_csv(dest, index=False)

    print("Corrélations (Spearman) entre indicateurs départementaux :")
    print(out[["temps_acces_median", "acces_mg_t_med", "acces_mg_part_sup_15"]].corr("spearman").round(2).to_string())
    for name in variants:
        d = out[f"d_rang_{name}"].abs()
        zc = (out[f"zone_{name}"] != out["zone_A"]) & out[f"zone_{name}"].notna()
        print(f"\nVariante {name} : écart de rang médian {d.median():.0f}, moyen {d.mean():.1f}, max {d.max():.0f} ; "
              f"{int((d >= 10).sum())} départements bougent de 10 rangs ou plus ; {int(zc.sum())} changent de zone ; "
              f"corrélation des scores {out['score_A'].corr(out[f'score_{name}']):.3f}")
        print("  changements de zone :", ", ".join(f"{r['Nom du département']} ({r['zone_A']} → {r[f'zone_{name}']})"
                                                  for _, r in out[zc].iterrows()) or "aucun")
        top = out.reindex(out[f"d_rang_{name}"].abs().sort_values(ascending=False).index).head(8)
        print("  plus affectés :", "; ".join(f"{r['Nom du département']} {int(r[f'd_rang_{name}']):+d} rangs" for _, r in top.iterrows()))
    print("\nÉcrit :", dest)


if __name__ == "__main__":
    main()
