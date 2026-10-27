"""Le catalogue de leviers ne s'active que lorsque ses conditions sont vérifiées."""
from __future__ import annotations

import logging
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore"); logging.getLogger("streamlit").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
DATA: dict = {}


def setUpModule():
    import os

    os.chdir(ROOT)
    from app.data_loading import load_all_data, load_drees_ps
    from app.scoring import compute_scores

    master, pros, immo, etabs, temps, env, patho, delais, presence = load_all_data()
    DATA.update(master=compute_scores(master), pros=pros, immo=immo, etabs=etabs, temps=temps, env=env,
                patho=patho, delais=delais, geojson=None, presence=presence, drees=load_drees_ps())


class TestCatalogue(unittest.TestCase):
    def test_conditions_requises_verifiees_partout(self):
        from app.leviers import CATALOGUE, evaluer, profil

        for dept in DATA["master"]["dept"]:
            p = profil(dept, DATA)
            for lev in CATALOGUE:
                ev = evaluer(lev, p)
                if ev is None or lev.id == "maintien":
                    continue
                for c in lev.conditions:
                    if c.requise:
                        self.assertTrue(c.test(p), f"{dept} {lev.id} : condition requise « {c.label} » non vérifiée")
                for ex in lev.exclusions:
                    self.assertFalse(ex.test(p) is True, f"{dept} {lev.id} : exclusion « {ex.label} » active")

    def test_dom_uniquement_outre_mer(self):
        from app.leviers import CATALOGUE_PAR_ID, evaluer, profil

        lev = CATALOGUE_PAR_ID["dom"]
        for dept in DATA["master"]["dept"]:
            ev = evaluer(lev, profil(dept, DATA))
            if ev:
                self.assertIn(dept, {"971", "972", "973", "974"})
        self.assertIsNotNone(evaluer(lev, profil("973", DATA)))

    def test_diversite_entre_territoires(self):
        from app.leviers import profil, selectionner

        temoins = {"75": None, "973": None, "23": None, "18": None, "93": None, "35": None, "2B": None, "974": None}
        ids = {}
        for d in temoins:
            ids[d] = [x["id"] for x in selectionner(profil(d, DATA), n=4)]
        self.assertNotEqual(ids["75"], ids["973"]); self.assertNotEqual(ids["23"], ids["93"])
        self.assertEqual(ids["75"], ["maintien"])           # Paris : aucun signal d'alerte
        self.assertIn("dom", ids["973"])
        self.assertGreaterEqual(len({tuple(v) for v in ids.values()}), 6)   # au moins 6 combinaisons distinctes
        tous = [i for v in ids.values() for i in v]
        self.assertGreaterEqual(len(set(tous)), 8)

    def test_textes_sans_valeur_manquante(self):
        from app.leviers import profil, selectionner

        for d in ("973", "23", "18", "93", "2B", "974", "59", "13"):
            for rec in selectionner(profil(d, DATA), n=4):
                for k in ("probleme", "action", "pourquoi"):
                    self.assertTrue(rec[k].strip(), (d, rec["id"], k))
                    self.assertNotIn("nan", rec[k].lower().split(), (d, rec["id"]))
                    self.assertNotIn("N/D", rec[k], (d, rec["id"], k))

    def test_region_agregation(self):
        from app.leviers import leviers_region

        m = DATA["master"]
        bret = m[m["Code région"].astype(str) == "53"]["dept"].tolist()
        lev = leviers_region(bret, DATA)
        self.assertTrue(lev)
        for l in lev:
            self.assertTrue(set(l["depts"]) <= set(m[m["dept"].isin(bret)]["Nom du département"]))


if __name__ == "__main__":
    unittest.main()
