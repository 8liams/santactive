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

## 8. Moteur de recommandations (catalogue `app/leviers.py`)

- 20 leviers déterministes, chacun avec conditions requises / contributives,
  exclusions, public, dispositifs nationaux existants, horizon, gabarit de
  texte (constat, indicateurs, action, pourquoi ici, secteurs, mise en œuvre).
- Profil territorial vectorisé (100 départements) : APL pondérée, part sous 2,5,
  densités DREES par spécialité (8 postes + sages-femmes), prévalences brutes
  et standardisées (si couverture ≥ 90 %), patients CNAM, démographie,
  communes à plus de 15 min avec population, structures FINESS (CH, CHS, HAD,
  centres de santé), typologie, outre-mer.
- Sélection : toutes les conditions requises vérifiées → score de
  correspondance (part des conditions contributives satisfaites × priorité) →
  au plus 4 leviers, 2 par famille. « Maintien » seulement si rien ne se déclenche.
- Région : agrégation des leviers déclenchés par département, portée observée
  (part de la population régionale). Ancien moteur conservé (`_compute_leviers_action_legacy`).
- Tests : `tests/test_leviers.py`.

## 9. Accès routier IGN (pilote, `app/pages/acces_ign.py`)

Pré-calcul (`scripts/donnees/calculer_acces_ign.py`) : itinéraires voiture
(bdtopo-valhalla) commune → commune la plus proche avec offre de médecine
générale, isochrones 10/15/20/30 min unis par seuil, population couverte,
simulation d'implantation (isochrone à la demande, cache 24 h). Cher : 286
itinéraires, 86 % de la population à moins de 15 min, corrélation 0,43 avec
l'indicateur interne (écart médian +2,3 min). Limites : centres de communes,
pas d'adresse de cabinet ; voiture ; présence ≠ capacité.

## 10. Délais v2 (expérimental, `compute_delais_v2`)

Médiane nationale DREES × facteur propre à chaque spécialité (densité DREES du
département rapportée à la médiane ; APL pour le généraliste), borné [0,7 ; 3].
Affiché en comparaison du modèle v1, non validé par des délais observés.

## 11. Indices offre × besoins (prototype, `app/indices.py`, page Explorer)

Indice offre (poids actuels renormalisés) et indice besoins (65+, prévalences
standardisées si fiables), quadrants par rapport aux médianes, explication par
département. Non intégré au score.

## 12. Interface (refonte du 28 octobre 2026, vérifiée dans le navigateur)

- Navigation unique : barre supérieure (logo, Accueil, Explorer, Comparer,
  Accès routier, Méthodologie, À propos, recherche globale) ; panneau latéral
  et bandeau mobile supprimés ; menu compact `<details>` sur mobile.
- Recherche : composant Streamlit maison (`app/components/search_frontend/`,
  protocole v1 sans dépendance). Index statique
  `static/data/index_recherche.json` (régénérer avec
  `scripts/donnees/generer_index_recherche.py` après un changement de
  données ; `server.enableStaticServing = true` dans `.streamlit/config.toml`,
  ce qui expose en lecture tout le dossier `static/`). Menu flottant, 7
  résultats, classement exact / préfixe / début de mot / contenu (communes
  −10), clavier, aucun rerun pendant la frappe ; la sélection renvoie
  `{level, code}` à Python qui navigue.
- Accueil : hero compact, recherche principale, carte nationale sans fond de
  carte (choroplèthe seule), repères nationaux (APL médiane, population sous
  2,5, généralistes, temps d'accès, terciles), cartouches DOM homogènes avec
  silhouette (`static/geo/contours_dom.json`, `generer_contours_dom.py`),
  Mayotte « hors score global ».
- Fonds de carte (`_tile_config`) : CARTO Positron si `CARTO_API_KEY`, sinon
  Esri World Light Gray (libre, attribution) ; `SANTACTIVE_FOND_CARTE=ign|osm`.
- Fiches : fil d'Ariane et actions (copier, e-mail, PDF, comparer) sur une
  ligne ; unité APL sur sa ligne ; scorecard six tuiles + détail dépliable
  (icône Material rétablie) ; cartes de recommandation sans bloc vide ;
  secteurs non répétés.
- Communes : deux lectures explicites — « besoin d'accès » (classes de temps
  de trajet) et « priorité d'action » (score inchangé : besoin 45 %,
  population 35 %, faisabilité 20 %). Carte et Top 10 suivent la même lecture ;
  les communes avec offre sur place (temps 0) ne sont pas classées ; le seuil
  de population du classement (max(2 000, médiane)) est supprimé — c'est lui
  qui faisait remonter des villes à 0 min.
- Veille (levier « maintien ») : mentionne les communes à plus de 15 min
  (nombre, habitants, part) quand le seuil de 3 % des leviers de proximité
  n'est pas atteint (ex. Côte-d'Or : 62 communes, 5 706 hab., 1 %).
- Comparateur : lien direct `?view=comparer&depts=18,75,23`.
- Vérification : captures Playwright (1440, 1920, 390 px) avant/après ;
  `tests/test_moteur.py::TestInterface` (49 tests au total).

## 13. Parcours ARS et simulateur IGN (28 octobre 2026)

- Parcours « Repérer → Diagnostiquer → Recommander → Simuler → Comparer » :
  liens contextuels (fiche → communes fragiles, simulation IGN si pilote,
  comparer, région ; leviers d'accès → simulation ; simulation → diagnostic ;
  Prioriser → diagnostic ; accueil → quatre usages). Le département est passé
  dans l'URL (`?view=acces&dept_code=18`, `&commune=…`).
- Simulateur (`app/pages/acces_ign.py`) : `PILOTES_VALIDES` liste les
  départements affichables (fichier présent **et** validé) ; classe « avant »
  = la plus favorable de l'itinéraire (3 offres les plus proches à vol
  d'oiseau) et de l'isochrone depuis un point d'offre ; scénario = isochrones
  10/15/20 min depuis la commune (IGN, cache 24 h, reprise sur 429) ;
  « nouvellement couverts » = classe avant > seuil et après ≤ seuil ;
  « rapprochés » = déjà sous le seuil, classe améliorée. Vérifié : Argent-
  sur-Sauldre +2 023 hab. à 15 min (elle-même) ; Jouet-sur-l'Aubois 0
  (déjà dans l'isochrone 15 min d'une offre malgré 17 min par itinéraire),
  1 303 hab. rapprochés. Limites affichées (centres de communes, capacité,
  départements voisins ignorés).
- Lecture communale « capacité » : `static/data/apl_communes_2023.csv`
  (`scripts/donnees/exporter_apl_communes.py`, même source DREES que l'APL
  départementale) ; communes sous 2,5 avec ou sans offre (Vierzon : APL 1,6
  avec offre). « Faisabilité » devient « conditions de déploiement » (prix au
  m², proxy partiel), pondérations inchangées.
- Repère national « 11,2 M d'habitants sous APL 2,5 » : Σ parts
  départementales × population INSEE 2021 ; recalcul direct sur le fichier
  communal : 11 210 951 (16,6 %).
- Formulations : « homogène » si écart ≤ 12 points et aucun critique ;
  « Problématiques de santé prioritaires » ; populations qualifiées.
- Extension IGN : voir le bilan du 28 octobre (≈ 3 itinéraires par commune
  sans offre + 4 isochrones par commune d'offre ; Cher = 907 requêtes, 1,3 Mo).
