"""Index de recherche territoriale pour le composant de recherche du navigateur.

Produit static/data/index_recherche.json (régions, départements, communes)
à partir des mêmes fichiers que l'application. Servi par Streamlit
(server.enableStaticServing) à l'URL /app/static/data/index_recherche.json et
chargé une seule fois par le navigateur : aucune requête au serveur pendant la
frappe.

Usage : python3 scripts/donnees/generer_index_recherche.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.data_loading import load_all_data  # noqa: E402
from app.search import _norm  # noqa: E402

OUT = ROOT / "static" / "data" / "index_recherche.json"


def main() -> None:
    master, _pros, _immo, _etabs, temps, *_rest = load_all_data()
    regions = (master[["Code région", "Nom de la région"]].drop_duplicates().dropna()
               .sort_values("Nom de la région"))
    depts = master[["dept", "Nom du département", "Code région", "Nom de la région"]].dropna()
    communes = (temps[["commune", "code_departement"]].dropna()
                .drop_duplicates(subset=["commune", "code_departement"]))
    communes["code_departement"] = communes["code_departement"].astype(str).str.zfill(2)
    dept_names = dict(zip(depts["dept"].astype(str), depts["Nom du département"]))

    payload = {
        "regions": [{"c": str(r["Code région"]), "n": str(r["Nom de la région"])} for _, r in regions.iterrows()],
        "departements": [{"c": str(r["dept"]), "n": str(r["Nom du département"]),
                          "pc": str(r["Code région"]), "pn": str(r["Nom de la région"])}
                         for _, r in depts.iterrows()],
        # communes : [nom, code département] ; le nom du département est résolu côté navigateur
        "communes": [[str(r["commune"]), r["code_departement"]] for _, r in communes.iterrows()],
        "noms_departements": dept_names,
    }
    # Vérification : la normalisation JS doit reproduire _norm (accents, tirets, apostrophes)
    exemple = _norm("Côtes-d'Armor")
    assert exemple == "cotes d armor", exemple
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"{OUT} : {len(payload['regions'])} régions, {len(payload['departements'])} départements, "
          f"{len(payload['communes'])} communes, {OUT.stat().st_size / 1e6:.2f} Mo")


if __name__ == "__main__":
    main()
