# Évolutions du moteur Sant'active — branche `fix/audit-moteur-ars`

Document de référence sur ce que le moteur exécute, ce qui a changé par
rapport à `main`, et comment revenir en arrière. La page Méthodologie de
l'application est générée à partir de la même configuration (`app/config.py`).

## 1. Configuration explicite du moteur

| Variable d'environnement (ou `st.secrets`) | Valeurs | Défaut (mode cible) | Mode historique |
|---|---|---|---|
| `SANTACTIVE_SOURCE_EFFECTIFS` | `drees`, `equipe` | `drees` : effectifs DREES/RPPS au 1ᵉʳ janvier 2026 | `equipe` : lignes du fichier territorial (présences, pas effectifs) |
| `SANTACTIVE_APL_METHODE` | `ponderee`, `mediane` | `ponderee` : moyenne des APL communaux pondérée par la population standardisée (méthode DREES) | `mediane` : médiane simple des communes |
| `SANTACTIVE_ETABS_DEFINITION` | `actuelle`, `court_sejour` | `actuelle` : CH + CHR + privés SSR | `court_sejour` (proposé) : CH + CHR + hôpitaux locaux + privés MCO + CLCC |

Une valeur inconnue arrête l'application (pas de bascule silencieuse). Aucun
fichier n'active une méthode par sa seule présence ; un fichier requis absent
lève une erreur explicite. Sur Railway / Streamlit Cloud : variables
d'environnement ou `.streamlit/secrets.toml`.

Comparer deux configurations : `python3 scripts/donnees/comparer_modes.py --apres SANTACTIVE_APL_METHODE=mediane`.

## 2. Score global (inchangé dans sa formule)

6 dimensions en rang percentile sur les 100 départements analysés (Mayotte
exclue), pondérations 30 / 20 / 15 / 20 / 10 / 5 (APL, généralistes /100k,
structures /100k, temps d'accès, part des 65+, prix au m²), poids redistribués
si une dimension manque, score absent sous 3 dimensions, terciles réels.
`tests/test_moteur.py::TestValeursDeReference::test_scores_reproductibles`
recalcule le score indépendamment.

Ce qui alimente les dimensions a changé :

| Dimension | Avant (`main`) | Maintenant |
|---|---|---|
| APL (30 %) | médiane simple des APL communaux (Haute-Corse 0,3) | moyenne pondérée DREES (Haute-Corse 3,7) ; médiane conservée en `apl_median_dept` |
| Généralistes /100k (20 %) | lignes du fichier équipe (Paris 1,9 /100k ; corrélation 0,02 avec la DREES) | effectifs DREES/RPPS 2026 / population INSEE 2021 (Paris 236) |
| Structures /100k (15 %) | CH + CHR + privés SSR, Antilles comptées en Corse | même définition, codes FINESS corrigés (289 lignes) |
| Part des 65+ (10 %) | décalée de 2 lignes pour 11 départements (Creuse 21,6 %) | réalignée (Creuse 30,9 %) |

Limite documentée : APL, généralistes et temps d'accès mesurent trois facettes
de l'offre de médecine générale (70 % du score) ; le score global est à 0,99
un indice d'offre. Étude des deux indices : `scripts/analyse/simulation_indices.py`.

## 3. Données corrigées (originaux dans `data_corrections/originaux/`)

- `population.csv` : permutation des valeurs densité / âges pour 21–29, 2A, 2B
  (`scripts/donnees/corriger_population.py`, validé INSEE 2021 + surfaces IGN).
- `etablissements.csv.gz` : codes département d'après `Libdepartement`
  (`scripts/donnees/corriger_finess.py`).
- `delais_rdv_nationaux.csv` : médianes DREES ER 1085 (7 spécialités portaient la moyenne).

## 4. Nouvelles sources (scripts reproductibles, provenance et SHA-256 dans `data_corrections/references/`)

- DREES, démographie des professionnels de santé (RPPS 2026, SNDS 2023) :
  `scripts/donnees/telecharger_drees_rpps.py` → `static/data/drees_*.csv`.
- DREES, APL communal 2023 → `scripts/donnees/calculer_apl_departemental.py` →
  `static/data/apl_mg_departemental_2023.csv` (moyenne pondérée, part de
  population sous 2,5, quartiles pondérés, déficit de consultations sous seuil).
- API Géo (population municipale, surfaces) →
  `scripts/donnees/telecharger_communes_population.py` →
  `static/data/communes_population_geoapi.csv`.
- Fichiers bruts (≈130 Mo) dans `data_corrections/references/drees/raw/`, hors Git.

## 5. Estimations : règles

- Aucun coefficient forfaitaire. Les volumes affichés sont observés : population
  INSEE des communes à plus de 15 min, habitants des communes sous APL 2,5
  (DREES), seniors, jeunes, patients CNAM.
- « Renforcement théorique de capacité médicale » : Σ pop_std × max(0, seuil − APL_c)
  / 5 400 actes (convention DREES de l'indicateur APL), fourchette 3 600–6 000.
  Simulation statique, surestimation par construction (voisinage ignoré), ETP ≠ médecins.
- Priorisation régionale : rangs nationaux ; score = moyenne à poids égaux du
  besoin (fragilité + complément du score global) et du volume ; faisabilité
  affichée à part ; portée observée des leviers ; publics par position nationale.
- Prévalences CNAM : brutes, et standardisées sur l'âge (standardisation
  directe, référence = ensemble des départements du fichier), signalées non
  comparables sous 90 % de couverture des poids d'âge.
- Délais : médianes nationales DREES 2016-2017 modulées par l'APL (proxy
  étiqueté estimation) ; valeurs régionales sans source retirées.

## 6. Revenir en arrière

- Méthodes : variables d'environnement ci-dessus.
- Données : copier `data_corrections/originaux/*` dans `static/data/`.
- Code : `git checkout main` (aucun commit de la branche n'a été poussé).

## 7. Tests

`python3 -m unittest discover -s tests -v` — 36 tests : valeurs de référence
(DREES, APL, INSEE, FINESS, délais), intégrité, reproductibilité du score,
régions DOM/Corse, PDF, modes de configuration (sous-processus), pages Streamlit
(AppTest, contenu vérifié).
