"""APL communal DREES (médecins généralistes, millésime 2023 ou 2024) : extrait léger pour l'application.

Même fichier source que calculer_apl_departemental.py (DREES, Licence Ouverte 2.0).
Sortie : static/data/apl_communes_<millésime>.csv — code_insee, apl, pop_tot, pop_std.
Usage dans l'application : lecture « capacité » de la priorisation communale
(commune disposant d'une offre mais sous le repère APL 2,5) et repère national
de population sous le repère.

Usage : python3 scripts/donnees/exporter_apl_communes.py [--millesime 2024]
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("apl_dept", ROOT / "scripts/donnees/calculer_apl_departemental.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)  # type: ignore[union-attr]

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--millesime", default="2024"); args = ap.parse_args()
    OUT = ROOT / f"static/data/apl_communes_{args.millesime}.csv"
    raw = mod.RAW / "apl_medecins_generalistes.xlsx"
    if not raw.exists():
        raw = mod.telecharger(False)
    df = mod.lire_communes(raw, args.millesime).dropna(subset=["apl"])
    out = df[["code_insee", "apl", "pop_tot", "pop_std"]].copy()
    out["apl"] = out["apl"].round(3); out["pop_std"] = out["pop_std"].round(1)
    out.to_csv(OUT, index=False)
    sous = df.loc[df["apl"] < 2.5, "pop_tot"].sum(); tot = df["pop_tot"].sum()
    print(f"{OUT} : {len(out)} communes, {OUT.stat().st_size / 1e6:.2f} Mo")
    print(f"Population sous APL 2,5 (DREES {args.millesime}, pop. totale du fichier) : {sous:,.0f} / {tot:,.0f} = {sous / tot:.1%}")
    print(f"Communes sous 2,5 : {(df['apl'] < 2.5).sum()} / {len(df)}")


if __name__ == "__main__":
    main()
