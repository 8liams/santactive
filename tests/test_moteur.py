"""Tests de non-régression du moteur Sant'active (audit avant présentation ARS).

Lancement depuis la racine du dépôt :
    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import logging
import math
import re
import unittest
import warnings
from pathlib import Path
from unittest import mock

warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)

import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

DATA: dict = {}


def setUpModule() -> None:
    import os

    os.chdir(ROOT)  # les chemins de données sont relatifs à la racine
    from app.data_loading import load_all_data, load_drees_ps
    from app.scoring import compute_scores

    master, pros, immo, etabs, temps, env, patho, delais, presence = load_all_data()
    DATA.update(
        master=compute_scores(master), pros=pros, immo=immo, etabs=etabs,
        temps=temps, env=env, patho=patho, delais=delais, geojson=None,
        presence=presence, drees=load_drees_ps(),
    )


def _row(dept: str) -> pd.Series:
    m = DATA["master"]
    return m[m["dept"] == dept].iloc[0]


def _region_chain(region_code: str):
    from app.pages import fiche_region as fr

    master = DATA["master"]
    rd = master[master["Code région"].astype(str) == region_code].copy()
    name = rd.iloc[0]["Nom de la région"]
    raw = fr.compute_dept_priorities(rd, DATA["patho"], reference=master)
    dl = fr.compute_specialites_tension(DATA["delais"], region_code)
    pub = fr.compute_publics_prioritaires(rd, DATA["patho"], raw, reference=master)
    prio = fr.enrich_priorities_decision(raw, rd, DATA["patho"], master)
    summ = fr.compute_region_summary(prio, rd, dl, publics=pub)
    lev = fr.enrich_leviers_decision(
        fr.compute_leviers_action(rd, raw, DATA["patho"], dl, reference=master),
        rd, prio, DATA, name,
    )
    return rd, name, raw, pub, prio, summ, lev


class TestNumeriques(unittest.TestCase):
    def test_to_num_conserve_zero_et_nan(self):
        from app.scoring import to_num

        self.assertEqual(to_num(0), 0.0)
        self.assertTrue(math.isnan(to_num(None)))
        self.assertTrue(math.isnan(to_num(float("nan"))))
        self.assertTrue(math.isnan(to_num("abc")))

    def test_master_100_departements(self):
        m = DATA["master"]
        self.assertEqual(len(m), 100)
        self.assertNotIn("976", set(m["dept"]))
        self.assertEqual(int(m["nb_classes"].iloc[0]), 100)


class TestPdfDepartement(unittest.TestCase):
    def test_rang_national_pdf_egal_rang_page(self):
        import app.pdf_export as pe
        from app.pages.fiche_departement import _generate_recommendations
        from app.scoring import fmt_classement_national

        master = DATA["master"]
        for dept in ("23", "75", "974", "973"):
            r = _row(dept)
            with mock.patch.object(pe, "fmt_classement_national",
                                   wraps=fmt_classement_national) as spy:
                pe.generate_department_pdf(r, master, _generate_recommendations(r, master, DATA), DATA)
            rang, total = spy.call_args[0]
            self.assertEqual(int(rang), int(r["rang_national"]), dept)
            self.assertEqual(total, 100)
        # Le pire département (rang interne 1) s'affiche 100e, le meilleur 1er
        m = DATA["master"]
        pire = m.loc[m["rang_national"] == 1].iloc[0]
        meilleur = m.loc[m["rang_national"] == 100].iloc[0]
        self.assertEqual(fmt_classement_national(pire["rang_national"], 100), "100\u202fème")
        self.assertEqual(fmt_classement_national(meilleur["rang_national"], 100), "1er")
        self.assertLess(pire["score_global"], meilleur["score_global"])


class TestPrevalences(unittest.TestCase):
    def test_denominateur_non_triple(self):
        from app.pathologies import dept_prevalences

        raw = pd.read_csv(ROOT / "static/data/pathologies.csv.gz", sep=";", low_memory=False)
        raw["dept"] = raw["dept"].astype(str).str.zfill(2)
        cat = "Maladies inflammatoires ou rares ou infection VIH"
        d = raw[(raw["dept"] == "23") & (raw["patho_niv1"] == cat)]
        attendu = d["Ntop"].sum() / d.drop_duplicates("cla_age_5")["Npop"].sum() * 100
        prev = dept_prevalences(DATA["patho"], ["23"]).loc["23", cat]
        self.assertAlmostEqual(prev, attendu, places=2)
        self.assertGreater(prev, 2.0)  # 0,88 % avec l'ancien dénominateur triplé

    def test_prevalences_simples_inchangees(self):
        from app.pathologies import dept_prevalences

        prev = dept_prevalences(DATA["patho"], ["23"]).loc["23", "Diabète"]
        self.assertAlmostEqual(prev, 9.10, places=1)


class TestRegions(unittest.TestCase):
    def test_seniors_pas_toujours_majeur(self):
        _, _, _, pub_guyane, *_ = _region_chain("3")
        seniors = next(p for p in pub_guyane if p["label"].startswith("Seniors"))
        self.assertNotIn(seniors["priorite"], ("majeure", "prioritaire"))
        _, _, _, pub_na, *_ = _region_chain("75")  # Nouvelle-Aquitaine, région âgée
        seniors_na = next(p for p in pub_na if p["label"].startswith("Seniors"))
        self.assertIn(seniors_na["priorite"], ("majeure", "prioritaire"))

    def test_rangs_nationaux_independants_de_la_region(self):
        """Le score de fragilité d'un département ne dépend pas de sa région."""
        from app.region_pilotage import compute_dept_priorities

        master = DATA["master"]
        national = compute_dept_priorities(master, DATA["patho"], reference=master)
        for code in ("3", "4", "94", "11"):
            _, _, raw, *_ = _region_chain(code)
            for _, r in raw.iterrows():
                n = national[national["dept"] == r["dept"]].iloc[0]
                self.assertAlmostEqual(r["_frag_score"], n["_frag_score"], places=9)

    def test_region_mono_departement_non_degeneree(self):
        """Guyane : fragilité très forte (rang national), impact non gonflé à « majeur »."""
        _, _, _, _, prio_gy, *_ = _region_chain("3")
        gy = prio_gy.iloc[0]
        self.assertIn(gy["fragilite"], ("forte", "très forte"))
        self.assertNotEqual(gy["impact"], "majeur")  # valait « majeur » d'office avant
        _, _, _, _, prio_na, *_ = _region_chain("75")
        dordogne = prio_na[prio_na["dept"] == "24"].iloc[0]
        self.assertGreater(gy["_frag_score"], dordogne["_frag_score"])

    def test_classement_unique_page_pdf(self):
        for code in ("24", "75", "11"):
            _, _, _, _, prio, summ, _ = _region_chain(code)
            self.assertEqual(list(prio["priorite_rang"]), list(range(1, len(prio) + 1)))
            scores = prio["score_priorite"].astype(float).tolist()
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertEqual(summ["dept_top"], prio.iloc[0]["Nom du département"])

    def test_leviers_sans_troncature(self):
        """Centre-Val de Loire : le Loiret (APL 1,8) n'est plus exclu."""
        rd, *_rest = _region_chain("24")
        lev = _rest[-1]
        tele = next(l for l in lev if l["intitule"] == "Téléexpertise")
        attendus = set(rd.loc[pd.to_numeric(rd["apl_dept"]) < 2.5, "Nom du département"])
        self.assertEqual(set(tele["depts"]), attendus)   # tous, sans troncature à 4
        self.assertGreaterEqual(len(attendus), 2)

    def test_population_observee_et_non_multiplicateurs(self):
        rd, _, _, _, prio, _, _ = _region_chain("4")
        self.assertEqual(int(prio.iloc[0]["impact_pop"]), int(rd.iloc[0]["population_num"]))

    def test_textes_sans_pluriel_abusif(self):
        _, _, _, _, _, summ, lev = _region_chain("3")
        textes = " ".join([summ["tension_principale"]] + [
            str(l.get("tension", "")) + str(l.get("justification", "")) for l in lev
        ])
        self.assertNotIn("plusieurs départements", textes)


class TestRecommandations(unittest.TestCase):
    def _all_recos(self):
        from app.pages.fiche_departement import _generate_recommendations

        master = DATA["master"]
        return {
            d: _generate_recommendations(_row(d), master, DATA) for d in master["dept"]
        }

    def test_aucune_valeur_inventee_ni_formulation_abusive(self):
        interdits = ("officiel", "+30", "EHPAD concernées", "~20", "~28")
        for d, recos in self._all_recos().items():
            for rec in recos:
                txt = rec["prose"] + " ".join(f"{v} {l}" for v, l in rec.get("stats", []))
                self.assertIsNone(re.search(r"\bnan\b", txt), f"{d}: « nan » dans {rec['title']}")
                for mot in interdits:
                    self.assertNotIn(mot, txt, f"{d}: « {mot} » dans {rec['title']}")

    def test_cas_pathologies_chroniques_se_declenche(self):
        n = sum(
            any("pathologies chroniques" in r["title"] for r in recos)
            for recos in self._all_recos().values()
        )
        self.assertGreater(n, 0)

    def test_temps_zero_non_remplace(self):
        from app.pages.fiche_departement import _generate_recommendations

        r = _row("29")  # Finistère : temps d'accès médian = 0
        self.assertEqual(float(r["temps_acces_median"]), 0.0)
        for rec in _generate_recommendations(r, DATA["master"], DATA):
            self.assertNotIn("10 minutes", rec["prose"])


class TestLibelles(unittest.TestCase):
    def test_pas_de_101_departements_ni_18_regions(self):
        motif = re.compile(r"101\s*d(é|\\u00e9)partements|18 régions")
        for p in list((ROOT / "app").rglob("*.py")) + [ROOT / "streamlit_app.py"]:
            self.assertIsNone(motif.search(p.read_text(encoding="utf-8")), str(p))


class TestPages(unittest.TestCase):
    """Rendu Streamlit des pages sensibles (DOM, Corse, commune à 0 min)."""

    def _run(self, **qp):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        for k, v in qp.items():
            at.query_params[k] = v
        at.run()
        return at

    def test_fiches_region_dom_et_corse(self):
        for code in ("1", "2", "3", "4", "94"):
            at = self._run(view="region", region_code=code)
            self.assertEqual(len(at.exception), 0, f"région {code}: {[e.value for e in at.exception]}")

    def test_fiches_departement_dom_corse(self):
        for code in ("2A", "2B", "971", "973", "974"):
            at = self._run(view="dept", dept_code=code)
            self.assertEqual(len(at.exception), 0, f"dept {code}")
            html = " ".join(m.value for m in at.markdown)
            self.assertNotIn("nan /100k", html)
            self.assertNotIn("nan €", html)

    def test_commune_a_zero_minute(self):
        at = self._run(view="commune", commune_code="Ambérieu-en-Bugey|01")
        self.assertEqual(len(at.exception), 0)
        html = " ".join(m.value for m in at.markdown)
        self.assertIn("0 min", html)


if __name__ == "__main__":
    unittest.main()


class TestEffectifsDrees(unittest.TestCase):
    """Chemin « jeu A » : effectifs DREES/RPPS injectés à la place du fichier équipe."""

    DREES = ROOT / "data_corrections" / "references" / "drees"

    @classmethod
    def setUpClass(cls):
        import app.data_loading as dl

        cls.dl = dl
        cls.orig = (dl.MEDECINS_DREES_PATH, dl.AUTRES_PS_DREES_PATH, dl.IDEL_DREES_PATH)
        dl.MEDECINS_DREES_PATH = cls.DREES / "drees_medecins_dept_2026.csv"
        dl.AUTRES_PS_DREES_PATH = cls.DREES / "drees_autres_rpps_dept_2026.csv"
        dl.IDEL_DREES_PATH = cls.DREES / "drees_infirmieres_liberales_dept_2023.csv"
        dl.load_all_data.clear(); dl.load_drees_ps.clear()
        from app.scoring import compute_scores

        master, pros, immo, etabs, temps, env, patho, delais, presence = dl.load_all_data()
        cls.data = dict(master=compute_scores(master), pros=pros, immo=immo, etabs=etabs,
                        temps=temps, env=env, patho=patho, delais=delais, geojson=None,
                        presence=presence, drees=dl.load_drees_ps())

    @classmethod
    def tearDownClass(cls):
        (cls.dl.MEDECINS_DREES_PATH, cls.dl.AUTRES_PS_DREES_PATH, cls.dl.IDEL_DREES_PATH) = cls.orig
        cls.dl.load_all_data.clear(); cls.dl.load_drees_ps.clear()

    def test_effectifs_personnes_et_source(self):
        m = self.data["master"].set_index("dept")
        self.assertEqual(int(m.loc["75", "nb_med_gen"]), 5040)   # DREES, pas 41 lignes
        self.assertEqual(int(m.loc["973", "nb_med_gen"]), 308)
        self.assertTrue((m["source_effectifs"] == "DREES RPPS 2026").all())
        self.assertAlmostEqual(float(m.loc["75", "med_gen_pour_100k"]), 5040 / 2133111 * 1e5, places=2)
        self.assertGreater(float(m.loc["75", "score_medecins"]), 90)

    def test_presence_conservee_separement(self):
        p = self.data["presence"]
        self.assertIn("nb_villes", p.columns)
        m = self.data["master"].set_index("dept")
        self.assertEqual(int(m.loc["75", "presence_lignes_med_gen"]), 41)

    def test_table_offre(self):
        from app.offre_medicale import table_offre

        r = self.data["master"].set_index("dept").loc["23"]
        r["dept"] = "23"
        t = table_offre(r, self.data).set_index("label")
        self.assertEqual(int(t.loc["Médecins généralistes", "effectif"]), 214)
        self.assertGreater(t.loc["Médecins généralistes", "presence_villes"], 0)
        self.assertIn("Pharmaciens (RPPS 2026)", t.index)

    def test_pages_avec_drees(self):
        from streamlit.testing.v1 import AppTest

        for code in ("75", "973", "2A"):
            at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
            at.query_params["view"] = "dept"; at.query_params["dept_code"] = code
            at.run()
            self.assertEqual(len(at.exception), 0, f"dept {code}: {[e.value for e in at.exception]}")
            html = " ".join(m.value for m in at.markdown)
            self.assertIn("DREES", html)


class TestSimulationCapacite(unittest.TestCase):
    """Section APL pondéré + simulation ETP, activée par la présence du fichier DREES."""

    def test_section_rendue_si_fichier_present(self):
        import app.simulation_capacite as sc
        from streamlit.testing.v1 import AppTest

        orig = sc.APL_DEPT_PATH
        sc.APL_DEPT_PATH = ROOT / "data_corrections/references/drees/apl_mg_departemental_2023.csv"
        sc.load_apl_departemental.clear()
        try:
            sim = sc.simuler("2B")
            self.assertAlmostEqual(sim["apl_moyen_pondere"], 3.70, places=1)
            lo, mid, hi = sim["etp_2,5"]
            self.assertTrue(lo < mid < hi)
            self.assertAlmostEqual(mid, sim["deficit_2,5"] / 5400, places=6)
            at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
            at.query_params["view"] = "dept"; at.query_params["dept_code"] = "23"
            at.run()
            self.assertEqual(len(at.exception), 0)
            html = " ".join(m.value for m in at.markdown)
            self.assertIn("ETP", html); self.assertIn("Simulation, pas mesure", html)
        finally:
            sc.APL_DEPT_PATH = orig; sc.load_apl_departemental.clear()

    def test_section_absente_sans_fichier(self):
        import app.simulation_capacite as sc

        orig = sc.APL_DEPT_PATH
        sc.APL_DEPT_PATH = ROOT / "static/data/inexistant.csv"
        sc.load_apl_departemental.clear()
        try:
            self.assertIsNone(sc.simuler("23"))
        finally:
            sc.APL_DEPT_PATH = orig; sc.load_apl_departemental.clear()
