"""Tests de cohérence métier (28 octobre 2026).

Garantissent que les populations cibles affichées avec les leviers correspondent au public du
levier et à la source nommée, que les arrondis sont identiques d'une page à l'autre, et que les
classements s'écrivent « 1er, 2e, 59e ».

Exécution : PYTHONPATH=. python3 -m unittest tests.test_coherence_metier
"""
from __future__ import annotations

import os
import unittest
import warnings

import pandas as pd

warnings.filterwarnings("ignore")

MASTER = None
DATA = None


def setUpModule():
    global MASTER, DATA
    os.environ.setdefault("SANTACTIVE_OFFLINE", "1")
    from app.data_loading import load_all_data
    from app.scoring import compute_scores

    master, pros, immo, etabs, temps, env, patho, delais, presence = load_all_data()
    MASTER = compute_scores(master)
    DATA = {"master": MASTER, "pros": pros, "immo": immo, "etabs": etabs, "temps": temps, "env": env,
            "patho": patho, "delais": delais, "presence": presence}


DEPTS_REPRESENTATIFS = ["23", "75", "22", "18", "13", "59", "2A", "971", "974", "04", "93", "48"]


def _row(code: str) -> pd.Series:
    return MASTER[MASTER["dept"] == code].iloc[0]


def _entier(label: str) -> int:
    """Nombre en tête d'un libellé « 7 880 patients … (CNAM 2023) » (la source n'est pas lue)."""
    import re

    m = re.match(r"\s*([\d   ]+)", label)
    assert m, label
    return int("".join(c for c in m.group(1) if c.isdigit()))


class TestPopulationsCibles(unittest.TestCase):
    """Chaque population cible correspond au public du levier et à sa source ; sinon elle est déclarée non quantifiable."""

    def _recos(self, code: str):
        from app.leviers import profil, selectionner

        return selectionner(profil(code, DATA), n=4)

    def test_sante_mentale_compte_les_patients_psychiatriques(self):
        from app.action_impact import patients_cnam, population_cible

        r = _row("23")
        label, ok = population_cible("sante_mentale", r, DATA["patho"])
        self.assertTrue(ok)
        self.assertEqual(_entier(label), patients_cnam(DATA["patho"], "23", "sychiatr"))
        self.assertNotEqual(_entier(label), patients_cnam(DATA["patho"], "23", "ardio"),
                            "la santé mentale ne doit pas afficher les patients cardio-neuro-vasculaires")
        self.assertIn("psychiatr", label)

    def test_publics_non_mesurables_sont_declares_non_quantifiables(self):
        from app.action_impact import NON_QUANTIFIABLE, population_cible

        r = _row("23")
        for lid in ["consult_avancees", "teleexpertise", "depistages", "perinatalite", "mobilite", "assistants",
                    "chroniques", "mediation", "ville_hopital", "sas", "maintien"]:
            label, ok = population_cible(lid, r, DATA["patho"])
            self.assertFalse(ok, lid)
            self.assertEqual(label, NON_QUANTIFIABLE, lid)

    def test_equipes_mobiles_compte_les_habitants_a_plus_de_15_min_insee(self):
        from app.action_impact import population_cible

        r = _row("23")
        label, ok = population_cible("equipes_mobiles", r, DATA["patho"])
        self.assertTrue(ok)
        self.assertEqual(_entier(label), int(round(float(r["acces_mg_pop_sup_15"]))))
        self.assertIn("INSEE 2025", label)

    def test_msp_compte_les_habitants_sous_apl_arrondis(self):
        from app.action_impact import population_cible

        r = _row("23")
        label, ok = population_cible("msp", r, DATA["patho"])
        self.assertTrue(ok)
        attendu = int(round(float(r["population_num"]) * float(r["part_pop_apl_inf_2_5"])))
        self.assertEqual(_entier(label), attendu)
        self.assertEqual(attendu, 39223)  # arrondi, pas troncature (39 222)

    def test_coherence_sur_departements_representatifs(self):
        """Sur chaque département, la population affichée pour un levier retenu est celle de sa règle."""
        from app.action_impact import (MODE_PAR_LEVIER, NON_QUANTIFIABLE, patients_cnam, pop_plus_15_min,
                                       pop_seniors, pop_sous_apl, project_levier_impact)

        for code in DEPTS_REPRESENTATIFS:
            if MASTER[MASTER["dept"] == code].empty:
                continue
            r = _row(code)
            for reco in self._recos(code):
                imp = project_levier_impact(reco, r, DATA)
                lid = reco["id"]
                self.assertIn(lid, MODE_PAR_LEVIER, f"levier {lid} sans règle de population")
                mode = MODE_PAR_LEVIER[lid]
                self.assertEqual(imp.public, reco["public"], lid)
                if mode is None:
                    self.assertEqual(imp.population, NON_QUANTIFIABLE, f"{code} {lid}")
                    continue
                attendu = {"apl": pop_sous_apl(r), "15min": pop_plus_15_min(r), "seniors": pop_seniors(r),
                           "sante_mentale": patients_cnam(DATA["patho"], code, "sychiatr"),
                           "cardio": patients_cnam(DATA["patho"], code, "ardio"),
                           "diabete": patients_cnam(DATA["patho"], code, "iabète")}.get(mode, "jeunes")
                if attendu is None:
                    self.assertEqual(imp.population, NON_QUANTIFIABLE, f"{code} {lid}")
                elif attendu != "jeunes":
                    self.assertEqual(_entier(imp.population), attendu, f"{code} {lid}")

    def test_region_parse_population_ignore_la_source(self):
        from app.region_decision import _parse_pop_from_amplitude

        self.assertEqual(_parse_pop_from_amplitude("39 223 habitants de communes sous le repère APL 2,5 (DREES 2024)"), 39223)
        self.assertIsNone(_parse_pop_from_amplitude("population cible non quantifiable avec les données disponibles"))


class TestArrondisEtFormats(unittest.TestCase):
    def test_arrondi_identique_entre_leviers_pdf_et_courriels(self):
        from app.action_impact import arrondi
        from app.components.share_bar import _entier as mail_entier
        from app.leviers import _n as levier_n
        from app.pdf_export import _num as pdf_num

        def chiffres(txt: str) -> str:
            return "".join(c for c in txt if c.isdigit())

        v = 39222.976  # Creuse : population × part sous APL 2,5
        self.assertEqual(arrondi(v), 39223)
        self.assertEqual(chiffres(levier_n(v)), "39223")
        self.assertEqual(chiffres(mail_entier(v)), "39223")
        self.assertEqual(chiffres(pdf_num(v, 0)), "39223")
        v15 = 7591.8286
        self.assertEqual(arrondi(v15), 7592)
        self.assertEqual(chiffres(levier_n(v15)), "7592")

    def test_classement_francais(self):
        from app.scoring import fmt_classement_national

        self.assertEqual(fmt_classement_national(100, 100), "1er")
        self.assertEqual(fmt_classement_national(99, 100), "2e")
        self.assertEqual(fmt_classement_national(42, 100), "59e")
        self.assertEqual(fmt_classement_national(1, 100), "100e")

    def test_aucun_libelle_score_global_ni_prototype(self):
        """Les textes affichés ne parlent plus de « score global de santé territoriale » ni de « prototype »."""
        import pathlib

        for p in ["app/pdf_export.py", "app/pages/exploration.py", "app/components/tooltip.py"]:
            txt = pathlib.Path(p).read_text(encoding="utf-8")
            self.assertNotIn("Score global de santé territoriale\"", txt, p)
            if p.endswith("exploration.py"):
                self.assertNotIn("· prototype", txt)


class TestCarteContinue(unittest.TestCase):
    """Chaque carte continue livrée passe le contrôle INSEE ; sans fichier, repli V1."""

    def test_departements_livres_valides(self):
        from app.pages.acces_ign import GEO_DIR, continu_valide, departements_continu

        livres = sorted(p.name[len("continu_mg_"):-5] for p in GEO_DIR.glob("continu_mg_*.json"))
        self.assertGreaterEqual(len(livres), 3)
        for d in livres:
            ok, motif = continu_valide(d)
            self.assertTrue(ok, f"{d} : {motif}")
        self.assertEqual(departements_continu(), livres)
        self.assertEqual(continu_valide("972"), (False, "non calculé"))  # Martinique : projection locale non gérée, repli V1


if __name__ == "__main__":
    unittest.main()
