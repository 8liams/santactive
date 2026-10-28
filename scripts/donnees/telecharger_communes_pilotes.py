"""Communes (code, nom, centre, population) des départements pilotes du simulateur.

Source : API Géo (geo.api.gouv.fr, Licence Ouverte) — population municipale
INSEE, centre géométrique de la commune. Fichier léger par département dans
static/geo/communes_<dept>.json ; aucun appel réseau à la consultation.

Usage : python3 scripts/donnees/telecharger_communes_pilotes.py 18 23 93 974
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "static" / "geo"


def telecharger(dept: str) -> Path:
    r = requests.get(f"https://geo.api.gouv.fr/departements/{dept}/communes",
                     params={"fields": "code,nom,centre,population"}, timeout=60)
    r.raise_for_status()
    communes = [{"code_insee": c["code"], "nom": c["nom"], "lon": round(c["centre"]["coordinates"][0], 5),
                 "lat": round(c["centre"]["coordinates"][1], 5), "population": int(c.get("population") or 0)}
                for c in r.json()]
    dest = OUT / f"communes_{dept}.json"
    dest.write_text(json.dumps({"dept": dept, "source": "API Géo (geo.api.gouv.fr), Licence Ouverte",
                                "date": date.today().isoformat(), "communes": communes}, ensure_ascii=False))
    print(f"{dept} : {len(communes)} communes → {dest} ({dest.stat().st_size / 1e3:.0f} Ko)")
    return dest


if __name__ == "__main__":
    for d in sys.argv[1:]:
        telecharger(d.zfill(2))
