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
            any(r.get("id") in ("cardio", "diabete", "chroniques", "sante_mentale") for r in recos)
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


class TestInterface(unittest.TestCase):
    """Refonte UI : cohérence carte / classement communal, recherche, outre-mer, veille."""

    def _comm(self):
        from app.commune_opportunity import build_commune_opportunity_df, norm_commune_name

        temps = pd.DataFrame({"commune": ["Alpha", "Beta", "Gamma", "Delta", "Omega"],
                              "temps_acces": [0, 12, 25, 40, 0]})
        immo = pd.DataFrame({"commune": temps["commune"], "prix_m2": [2000, 1500, 1200, 900, 2500]})
        codes = {norm_commune_name(n): f"0000{i}" for i, n in enumerate(temps["commune"], 1)}
        pop = {f"0000{i}": p for i, p in enumerate([20000, 800, 300, 150, 9000], 1)}
        return build_commune_opportunity_df(temps, immo, codes, code_to_name={v: k for k, v in codes.items()},
                                            population_by_code=pop)

    def test_top_communes_exclut_offre_sur_place_et_suit_la_lecture(self):
        from app.commune_opportunity import top_communes_for_action

        df = self._comm()
        prio = top_communes_for_action(df, limit=10, mode="priorite")
        besoin = top_communes_for_action(df, limit=10, mode="besoin")
        for top in (prio, besoin):
            self.assertTrue((pd.to_numeric(top["temps_acces"]) > 0).all(), "une commune à 0 min est classée")
        self.assertEqual(list(pd.to_numeric(besoin["temps_acces"])), [40, 25, 12])
        self.assertEqual(len(prio), 3)
        self.assertTrue(prio["score_action"].is_monotonic_decreasing)
        # carte : les communes avec offre portent le libellé « offre dans la commune », les autres leur niveau
        sur_place = df[pd.to_numeric(df["temps_acces"]) <= 0]
        self.assertTrue((sur_place["niveau"] == "Offre dans la commune").all())
        self.assertTrue((sur_place["besoin_label"] == "Offre dans la commune").all())

    def test_classes_de_besoin(self):
        from app.commune_opportunity import besoin_class

        self.assertEqual(besoin_class(0)[0], "Offre dans la commune")
        self.assertEqual(besoin_class(12)[0], "10 à 15 min")
        self.assertEqual(besoin_class(25)[0], "15 à 30 min")
        self.assertEqual(besoin_class(40)[0], "Plus de 30 min")
        self.assertEqual(besoin_class(float("nan"))[0], "N/D")

    def test_index_recherche_coherent(self):
        import json

        idx = json.loads((ROOT / "static/data/index_recherche.json").read_text())
        master = DATA["master"]
        self.assertEqual({d["c"] for d in idx["departements"]}, set(master["dept"].astype(str)))
        self.assertEqual(len(idx["regions"]), master["Code région"].nunique())
        communes = DATA["temps"][["commune", "code_departement"]].dropna().drop_duplicates()
        self.assertEqual(len(idx["communes"]), len(communes))
        self.assertTrue((ROOT / "app/components/search_frontend/index.html").exists())

    def test_contours_dom(self):
        import json

        fc = json.loads((ROOT / "static/geo/contours_dom.json").read_text())
        self.assertEqual({f["properties"]["code"] for f in fc["features"]}, {"971", "972", "973", "974", "976"})
        from app.components.maps import _outline_svg

        self.assertIn("<path", _outline_svg("974", "#1B5E3F"))

    def test_accueil_sans_panneau_lateral(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        at.query_params["view"] = "home"
        at.run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.sidebar.markdown), 0, "le panneau latéral doit être vide")
        html = " ".join(m.value for m in at.markdown)
        self.assertIn("sa-nav-links", html)
        self.assertIn("dom-card", html)
        self.assertNotIn("ophtalmo", html.lower())

    def test_maintien_signale_les_poches_communales(self):
        from app.leviers import profil, selectionner

        recos = selectionner(profil("21", DATA), n=4)
        self.assertEqual([r["id"] for r in recos], ["maintien"])
        self.assertIn("62 communes", recos[0]["probleme"])
        self.assertTrue(recos[0]["secteurs"])


class TestParcoursEtSimulation(unittest.TestCase):
    """Simulation IGN (calcul pur), lecture capacité, liens de parcours, formulations régionales."""

    def test_simulation_ign_classes_et_gains(self):
        """Situation actuelle par carreau (Insee), scénario par isochrone : gains et rapprochés."""
        import pandas as pd
        from app.pages.acces_ign import _classe, gains, gains_par_commune, scenario, situation_communes

        carreaux = pd.DataFrame([
            # commune A : généraliste présent, carreaux à 1–3 min
            {"code_insee": "A", "lon": 0.0, "lat": 0.0, "pop": 800, "duree": 1.0, "commune_offre": "A"},
            {"code_insee": "A", "lon": 0.05, "lat": 0.0, "pop": 200, "duree": 3.0, "commune_offre": "A"},
            # commune B : 12 min (déjà ≤ 15), dans l'isochrone 10 du scénario → rapprochée
            {"code_insee": "B", "lon": 0.5, "lat": 0.0, "pop": 500, "duree": 12.0, "commune_offre": "A"},
            # commune C : 27 min, dans l'isochrone 10 → nouvellement couverte
            {"code_insee": "C", "lon": 1.0, "lat": 0.0, "pop": 300, "duree": 27.0, "commune_offre": "A"},
            # commune D : 40 min, hors isochrone → inchangée
            {"code_insee": "D", "lon": 5.0, "lat": 5.0, "pop": 200, "duree": 40.0, "commune_offre": "A"},
        ])
        carreaux["classe"] = carreaux["duree"].apply(_classe)
        communes = pd.DataFrame([{"code_insee": c, "nom": c, "lon": x, "lat": 0.0, "population": 1}
                                 for c, x in (("A", 0.0), ("B", 0.5), ("C", 1.0), ("D", 5.0))])
        sit = situation_communes(carreaux, communes).set_index("nom")
        self.assertTrue(sit.loc["A", "offre"]); self.assertFalse(sit.loc["B", "offre"])
        self.assertAlmostEqual(sit.loc["A", "t_moy"], 1.4)
        self.assertEqual(sit.loc["C", "classe"], 30); self.assertEqual(sit.loc["D", "classe"], 99)
        self.assertEqual(sit.loc["C", "pop_sup_15"], 300)
        carre = {"type": "Polygon", "coordinates": [[[0.2, -0.4], [1.8, -0.4], [1.8, 0.4], [0.2, 0.4], [0.2, -0.4]]]}
        com = scenario(carreaux, {10: carre, 15: carre})
        gain, rapp = gains(com, 15)
        self.assertEqual(gain["code_insee"].tolist(), ["C"])      # 27 min → ≤ 10 min
        self.assertEqual(rapp["code_insee"].tolist(), ["B"])      # 12 min → ≤ 10 min
        gpc = gains_par_commune(gain, sit.reset_index())
        self.assertEqual(gpc.iloc[0]["nom"], "C"); self.assertEqual(gpc.iloc[0]["pop_gain"], 300)
        self.assertAlmostEqual(gpc.iloc[0]["part"], 1.0)
        gain20, rapp20 = gains(com, 20)
        self.assertEqual(len(gain20), 1); self.assertEqual(set(rapp20["code_insee"]), {"B"})
        self.assertNotIn("D", com.loc[com["classe_apres"] <= 20, "code_insee"].tolist())

    def test_lecture_capacite(self):
        from app.commune_opportunity import capacite_class, top_communes_for_action

        self.assertIn("capacité insuffisante", capacite_class(1.6, 0)[0])
        self.assertEqual(capacite_class(3.4, 0)[0], "Offre présente, APL ≥ 3")
        self.assertEqual(capacite_class(2.0, 12)[0], "Sans offre sur place, APL < 2,5")
        self.assertEqual(capacite_class(float("nan"), 0)[0], "N/D")
        df = pd.DataFrame({"commune": ["A", "B", "C"], "population": [100, 5000, 300], "temps_acces": [0, 0, 20],
                           "score_action": [10, 20, 30], "apl_commune": [1.5, 3.2, 2.1]})
        top = top_communes_for_action(df, limit=10, mode="capacite")
        self.assertEqual(top["commune"].tolist(), ["C", "A"])

    def test_fichier_apl_communal(self):
        from app.commune_opportunity import load_apl_communes

        apl = load_apl_communes()
        self.assertGreater(len(apl), 30000)
        self.assertLess(apl.get("18279", 9), 2.5)   # Vierzon : offre présente, APL 1,6

    def test_parcours_fiche_et_ign(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        at.query_params["view"] = "dept"; at.query_params["dept_code"] = "18"
        at.run()
        self.assertEqual(len(at.exception), 0)
        html = " ".join(m.value for m in at.markdown)
        self.assertIn("Simuler une implantation (pilote IGN)", html)
        self.assertIn('id="communes"', html)
        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        at.query_params["view"] = "acces"; at.query_params["dept_code"] = "18"
        at.run()
        self.assertEqual(len(at.exception), 0)
        html = " ".join(m.value for m in at.markdown)
        self.assertIn("Territoire pilote", html)
        self.assertIn("Retour au diagnostic", html)
        from app.pages.acces_ign import pilotes_disponibles
        labels = [sb.label for sb in at.selectbox]
        self.assertIn("Commune d’implantation", labels)
        self.assertEqual("Département pilote" in labels, len(pilotes_disponibles()) > 1,
                         "le sélecteur de pilote n'apparaît que s'il y a plusieurs pilotes")
        self.assertIn("Nouvellement couverts", html)
        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        at.query_params["view"] = "exploration"
        at.run()
        self.assertEqual(len(at.exception), 0)
        html = " ".join(m.value for m in at.markdown)
        self.assertIn("Prioriser", html)
        self.assertIn("Ouvrir le diagnostic", html)

    def test_formulations_regionales(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        at.query_params["view"] = "region"; at.query_params["region_code"] = "53"
        at.run()
        self.assertEqual(len(at.exception), 0)
        html = " ".join(m.value for m in at.markdown)
        self.assertNotIn("Situation homogène", html)
        self.assertNotIn("plutôt homogène", html)
        self.assertNotIn("potentiellement touchés", html)
        self.assertNotIn("Publics prioritaires", html)
        self.assertIn("Problématiques de santé", html)

    def test_chiffres_contextualises_dans_les_leviers(self):
        from app.leviers import profil, selectionner

        recos = selectionner(profil("973", DATA), n=4)
        chips = [c for r in recos for c in r["indicateurs"]]
        self.assertTrue(any("pour 100 000 hab." in c and "médiane" in c for c in chips), chips)
        self.assertFalse(any("/100k contre" in c for c in chips), chips)


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


class TestValeursDeReference(unittest.TestCase):
    """Valeurs de référence vérifiables et intégrité des données actives."""

    def test_effectifs_drees_reference(self):
        m = DATA["master"].set_index("dept")
        self.assertEqual(m["source_effectifs"].iloc[0], "DREES RPPS 2026")
        for dept, eff in {"75": 5040, "93": 1682, "23": 214, "973": 308, "974": 1620, "2A": 278, "2B": 298, "18": 296}.items():
            self.assertEqual(int(m.loc[dept, "nb_med_gen"]), eff, dept)
        self.assertEqual(int(m["nb_med_gen"].sum()), 100970 - 144)   # France entière DREES moins Mayotte
        self.assertAlmostEqual(float(m["med_gen_densite_drees"].median()), 146.8, delta=0.3)

    def test_apl_ponderee_reference(self):
        m = DATA["master"].set_index("dept")
        self.assertEqual(m["apl_methode"].iloc[0], "ponderee")
        self.assertAlmostEqual(float(m.loc["2B", "apl_dept"]), 3.70, delta=0.02)
        self.assertAlmostEqual(float(m.loc["2B", "apl_median_dept"]), 0.30, delta=0.01)
        self.assertAlmostEqual(float(m.loc["973", "part_pop_apl_inf_2_5"]), 0.68, delta=0.01)
        self.assertEqual(int((m["apl_dept"] < 2.5).sum()), 5)

    def test_insee_et_finess_corriges(self):
        m = DATA["master"].set_index("dept")
        self.assertAlmostEqual(float(m.loc["23", "pct_plus_65"]), 30.9, delta=0.05)   # Creuse (était 21,6)
        self.assertAlmostEqual(float(m.loc["25", "pct_plus_65"]), 20.0, delta=0.05)   # Doubs (était 30,9)
        self.assertEqual(int(m.loc["971", "nb_etabs"]), 85); self.assertEqual(int(m.loc["972", "nb_etabs"]), 80)
        self.assertEqual(int(m.loc["2A", "nb_etabs"]), 27); self.assertEqual(int(m.loc["2B", "nb_etabs"]), 24)
        self.assertEqual(int(m["nb_dimensions_ok"].min()), 5)   # 57/67/68 sans DVF ; DOM désormais à 6
        self.assertEqual(int((m["nb_dimensions_ok"] == 6).sum()), 97)

    def test_integrite_master(self):
        m = DATA["master"]
        self.assertEqual(m["dept"].nunique(), 100)
        self.assertFalse(m["dept"].duplicated().any())
        ages = m[["pct_moins_25", "pct_25_64", "pct_plus_65"]].astype(float).sum(axis=1)
        self.assertTrue(((ages - 100).abs() < 0.3).all())
        self.assertTrue((m["population_num"] > 70_000).all())
        zones = m["zone_short"].value_counts()
        self.assertEqual(int(zones.sum()), 100)
        self.assertTrue(all(33 <= int(zones[z]) <= 34 for z in ("Critique", "Intermédiaire", "Favorable")))
        self.assertEqual(sorted(m["rang_national"].astype(int).unique())[:2], [1, 2])
        for c in ["med_gen_pour_100k", "structures_pour_100k", "temps_acces_median", "apl_dept"]:
            self.assertFalse(m[c].isna().any(), c)

    def test_scores_reproductibles(self):
        """Le score global est une fonction déterministe des 6 colonnes (recalcul indépendant)."""
        from app.scoring import DIMENSIONS

        m = DATA["master"].set_index("dept")
        w = pd.Series({k: v["weight"] for k, v in DIMENSIONS.items()})
        S = pd.DataFrame(index=m.index)
        for k, v in DIMENSIONS.items():
            r = pd.to_numeric(m[v["col"]], errors="coerce").rank(pct=True) * 100
            S[k] = r if v["hib"] else 100 - r
        g = ((S * w).sum(axis=1, skipna=True) / S.notna().mul(w).sum(axis=1)).round(1)
        self.assertTrue((g - m["score_global"]).abs().max() < 0.051)

    def test_delais_nationaux_drees(self):
        from app.components.delais import load_delais_nationaux

        d = load_delais_nationaux().set_index("specialite")
        self.assertEqual(int(d.loc["Pédiatre", "delai_median_jours"]), 8)
        self.assertEqual(int(d.loc["Cardiologue", "delai_median_jours"]), 37)
        self.assertEqual(int(d.loc["Ophtalmologue", "delai_moyen_jours"]), 80)

    def test_comparer_agregats_regionaux(self):
        from app.pages.comparer import build_regions_comparison_df

        reg = build_regions_comparison_df(DATA["master"])
        self.assertEqual(len(reg), 17)
        m = DATA["master"]; idf = m[m["Code région"].astype(str) == "11"]
        mask = reg.astype(str).apply(lambda c: c.str.contains("Île-de-France")).any(axis=1)
        row = reg[mask].iloc[0]
        attendu = (idf["score_global"] * idf["population_num"]).sum() / idf["population_num"].sum()
        self.assertAlmostEqual(float(row["score_global"]), float(attendu), places=1)


class TestModesConfiguration(unittest.TestCase):
    """Les modes alternatifs se chargent et diffèrent de façon attendue (sous-processus)."""

    def _run(self, env_kv: str, expr: str) -> str:
        import os, subprocess, sys

        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
        k, v = env_kv.split("=", 1); env[k] = v
        code = ("import warnings,logging; warnings.filterwarnings('ignore')\n"
                "from app.data_loading import load_all_data\nfrom app.scoring import compute_scores\n"
                "m=compute_scores(load_all_data()[0]).set_index('dept')\n" f"print({expr})")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        return r.stdout.strip().splitlines()[-1]

    def test_mode_equipe_historique(self):
        out = self._run("SANTACTIVE_SOURCE_EFFECTIFS=equipe", "int(m.loc['75','nb_med_gen']), m['source_effectifs'].iloc[0]")
        self.assertIn("41", out); self.assertIn("historique", out)

    def test_mode_apl_mediane(self):
        out = self._run("SANTACTIVE_APL_METHODE=mediane", "round(float(m.loc['2B','apl_dept']),2)")
        self.assertEqual(out, "0.3")

    def test_mode_etabs_court_sejour(self):
        out = self._run("SANTACTIVE_ETABS_DEFINITION=court_sejour", "int(m.loc['75','nb_structures']), m['structures_definition'].iloc[0]")
        self.assertIn("court_sejour", out)

    def test_valeur_inconnue_refusee(self):
        import os, subprocess, sys

        env = dict(os.environ, PYTHONPATH=str(ROOT), SANTACTIVE_APL_METHODE="moyenne")
        r = subprocess.run([sys.executable, "-c", "import app.config"], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("valeurs admises", r.stderr)


class TestNouvellesPages(unittest.TestCase):
    def test_exploration_et_acces(self):
        from streamlit.testing.v1 import AppTest

        for view, attendu in (("exploration", "besoins"), ("acces", "IGN")):
            at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
            at.query_params["view"] = view
            at.run()
            self.assertEqual(len(at.exception), 0, f"{view}: {[e.value for e in at.exception]}")
            self.assertIn(attendu, " ".join(m.value for m in at.markdown))

    def test_acces_ign_cher_coherent(self):
        import json

        d = json.loads((ROOT / "static/geo/acces_ign_18.json").read_text())
        com = pd.DataFrame(d["communes"])
        self.assertEqual(len(com), 286)
        self.assertTrue(com["temps_ign_min"].notna().all())
        self.assertTrue((com.loc[com["statut"] == "offre sur place", "temps_ign_min"] == 0).all())
        self.assertTrue((com.loc[com["statut"] == "calculé", "temps_ign_min"] > 0).all())
        cov = d["couverture_population"]
        self.assertTrue(cov["10"] <= cov["15"] <= cov["20"] <= cov["30"] <= cov["total"])


class TestFiabilisationEtTerritoire(unittest.TestCase):
    """Chantier du 28 octobre : indicateur INSEE, territoire de référence, simulateur v2, Comparer."""

    def test_territoire_param(self):
        from app.territoire import FRANCE, Territoire, parse

        self.assertEqual(parse("fr"), FRANCE)
        self.assertEqual(parse("d18"), Territoire("dept", "18"))
        self.assertEqual(parse("d1"), Territoire("dept", "01"))
        self.assertEqual(parse("r53"), Territoire("region", "53"))
        self.assertIsNone(parse("xyz"))
        self.assertEqual(Territoire("dept", "974").param, "d974")
        self.assertTrue(FRANCE.is_national)

    def test_acces_insee_departements(self):
        import pandas as pd
        from app.data_loading import load_acces_insee_dept

        d = load_acces_insee_dept()
        self.assertGreaterEqual(len(d), 95)
        self.assertNotIn("973", set(d["dept"]))            # Guyane hors champ Filosofi
        cher = d[d["dept"] == "18"].iloc[0]
        self.assertTrue(0.02 < cher["acces_mg_part_sup_15"] < 0.04)   # 2,8 % en 2025
        self.assertTrue(2 < cher["acces_mg_t_med"] < 10)   # médiane 2,95 min en 2025
        # part nationale pondérée : 0,8 %
        part = (d["acces_mg_pop_sup_15"].sum() / d["acces_mg_pop"].sum())
        self.assertTrue(0.005 < part < 0.012)
        self.assertTrue((d["acces_mg_part_sup_15"] >= d["acces_mg_part_sup_20"]).all())

    def test_lecture_communale_insee(self):
        import pandas as pd
        from app.commune_opportunity import besoin_class, capacite_class, load_acces_insee_communes

        c = load_acces_insee_communes()
        self.assertGreater(len(c), 34000)
        cher = c[c["dep"] == "18"]
        self.assertEqual(int(cher["offre_sur_place"].sum()), 51)       # communes avec généraliste (BPE 2025)
        # présence explicite : une commune équipée à 3 min est « offre dans la commune »,
        # une commune non équipée à 3 min est « 10 min ou moins »
        self.assertEqual(besoin_class(3.0, True)[0], "Offre dans la commune")
        self.assertEqual(besoin_class(3.0, False)[0], "10 min ou moins")
        self.assertEqual(besoin_class(0, None)[0], "Offre dans la commune")   # convention interne conservée
        self.assertIn("capacité insuffisante", capacite_class(1.6, 4.0, True)[0])
        self.assertEqual(capacite_class(2.0, 4.0, False)[0], "Sans offre sur place, APL < 2,5")

    def test_pilotes_et_message_hors_pilote(self):
        from app.pages.acces_ign import PILOTES_VALIDES, pilotes_disponibles

        pil = pilotes_disponibles()
        for d in ("18", "23", "93", "974"):
            self.assertIn(d, pil)
        self.assertTrue(set(pil) <= set(PILOTES_VALIDES))
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
        at.query_params["view"] = "acces"; at.query_params["dept_code"] = "75"
        at.run()
        self.assertEqual(len(at.exception), 0)
        html = " ".join(m.value for m in at.markdown)
        self.assertIn("pas disponible pour Paris", html)

    def test_comparer_similaires_et_synthese(self):
        from app.pages.comparer import _similar, build_regions_comparison_df

        at_master = self._master()
        sim = _similar("18", at_master, 3)
        self.assertEqual(len(sim), 3); self.assertNotIn("18", sim)
        contr = _similar("18", at_master, 3, contraste=True)
        self.assertTrue(all(at_master.set_index("dept").loc[c, "zone_short"] == "Favorable" for c in contr))
        reg = build_regions_comparison_df(at_master)
        self.assertIn("acces_mg_part_sup_15_pct", reg.columns)
        self.assertIn("nb_depts", reg.columns)

    def test_leviers_region_en_clair(self):
        lv = __import__("app.leviers", fromlist=["leviers_region"]).leviers_region(["22", "29", "35", "56"], self._data())
        self.assertTrue(lv)
        for l in lv:
            self.assertNotIn("percentile", l["tension"])
            self.assertNotIn("N/D psychiatres", l["tension"])
            self.assertIn("conditions_catalogue", l)

    @classmethod
    def _data(cls):
        if not hasattr(cls, "_cache"):
            import warnings
            warnings.filterwarnings("ignore")
            from app.data_loading import load_all_data
            from app.scoring import compute_scores
            master, pros, immo, etabs, temps, env, patho, delais, presence = load_all_data()
            master = compute_scores(master)
            master["acces_mg_part_sup_15_pct"] = master["acces_mg_part_sup_15"] * 100
            cls._cache = {"master": master, "pros": pros, "immo": immo, "etabs": etabs, "temps": temps,
                          "env": env, "patho": patho, "delais": delais, "presence": presence}
        return cls._cache

    @classmethod
    def _master(cls):
        return cls._data()["master"]
