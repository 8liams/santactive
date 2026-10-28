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

## 14. Fiabilisation des temps d'accès, territoire de référence, simulateur v2 (28 octobre 2026)

### Audit de l'indicateur interne (`static/data/temps_acces.csv.gz`)
- 34 863 communes, valeurs entières 0–84 min ; **25,5 % de communes à 0** (pas
  98,8 % : ce chiffre d'un bilan antérieur était faux). Départements entièrement
  à 0 : 75, 93, 94, 971, 974.
- Les zéros sont une **présence**, pas un temps : parmi les communes appariées
  à la BPE 2025, 2 581 des 2 642 communes à 0 ont un généraliste recensé (61
  exceptions ; 45 communes équipées ne sont pas à 0). Le fichier
  « professionnels » de l'équipe démultiplie les praticiens par commune du
  code postal (Veaugues : 18 lignes de généralistes pour 600 habitants), ce qui
  explique les écarts.
- Pour les communes sans offre, la corrélation avec la mesure INSEE est de
  0,87 (Spearman) mais l'indicateur sous-compte les communes éloignées
  (Saône-et-Loire 5 contre 30, Nièvre 13 contre 31, Côte-d'Or 62 contre 71)
  et ignore la population. Les docs parlaient de « FINESS + INSEE » : l'offre
  est en réalité le fichier de présences de l'équipe.

### Nouvelle source : Insee « localisation et accès de la population aux équipements » (2025)
- 17 fichiers parquet régionaux (14,5 Go, BPE 2025, distancier Metric-OSRM,
  population carroyée Filosofi, carreaux de 200 m) téléchargés et agrégés par
  `scripts/donnees/calculer_acces_insee.py` (DuckDB) pour sept types
  d'équipements de santé (généraliste D265, pharmacie D307, urgences D106,
  maternité D107, centre de santé D108, MSP D113, infirmier D281).
- Sorties : `static/data/acces_insee_mg_communes_2025.csv` (34 833 communes :
  population localisée, temps moyen et médian pondérés, parts > 10/15/20/30 min,
  présence d'un généraliste), `static/data/acces_insee_departements_2025.csv`
  (par département et type), `data_corrections/references/insee_acces/`
  (tous types, provenance avec sha256). Champ : métropole + Martinique +
  La Réunion ; Guadeloupe, Guyane, Mayotte hors Filosofi.
- Résultats nationaux : 0,8 % de la population à plus de 15 min en voiture d'un
  généraliste (514 000 habitants), 0,18 % à plus de 20 min ; 8 838 communes
  équipées (≈ les 8 873 zéros du fichier interne).
- Intégration : `load_acces_insee_dept()` → colonnes `acces_mg_*` du master ;
  option `SANTACTIVE_TEMPS_SOURCE=interne|insee` (`config.TEMPS_SOURCE`,
  défaut **interne** : la dimension « temps » du score ne change pas sans
  validation). Les diagnostics (accueil, phrase de la fiche, scorecard, Comparer,
  PDF, infobulle) affichent le repère INSEE. Lecture communale (`commune_opportunity`) :
  temps moyen INSEE par commune + présence BPE (`offre_sur_place`), repli sur
  l'interne si le département n'est pas couvert (Guyane).
- Analyse de sensibilité (`scripts/analyse/sensibilite_temps_acces.py`,
  résultat dans `data_corrections/references/insee_acces/sensibilite_temps_acces.csv`) :
  médiane INSEE → 20 départements bougent de ≥ 10 rangs, 14 changent de zone
  (corr. 0,968) ; part > 15 min → 14 départements, 8 zones (corr. 0,979).
  Décision de bascule laissée à William.

### APL 2024
- `calculer_apl_departemental.py --millesime 2024` → `apl_mg_departemental_2024.csv`
  (national 3,72 ; 18,2 % sous 2,5 ; écart de rang médian 2 vs 2023, 4
  départements ≥ 10 rangs, Spearman 0,99). Production : 2023 tant que non validé.

### Territoire de référence (`app/territoire.py`)
- Session + paramètre d'URL `t=` (`fr`, `r53`, `d18`) ; sélecteur dans la barre ;
  `internal_href` ajoute `t=` à tous les liens (chaque lien recharge la page) ;
  les fiches font suivre le territoire ; Prioriser (région pré-filtrée,
  département mis en évidence), Comparer (premier territoire), Accès routier
  (pilote ou message explicite), accueil (bloc de référence) le relisent.

### Simulateur v2 (`app/pages/acces_ign.py`)
- Situation actuelle = carreaux INSEE du département (`static/geo/carreaux_mg_<dept>.csv.gz`,
  `communes_<dept>.json` via API Géo) ; scénario = isochrones IGN 10/15/20 min
  depuis la commune ; gains calculés carreau par carreau (`shapely.contains_xy`).
- Ancien calcul par itinéraires (Cher) : Spearman 0,43 avec l'INSEE, écart
  médian +1,8 min, p90 +7,5 min, 21 700 hab. > 15 min contre 8 100 → conservé
  uniquement dans le panneau de vérification. Le minimum « itinéraire /
  isochrone » est abandonné.
- Pilotes : Cher, Creuse, Seine-Saint-Denis, La Réunion, Martinique
  (`PILOTES_VALIDES`) ; isochrones IGN testées dans les DOM.

### Autres
- Carte de la fiche région : invisible (hauteur 2 px) car initialisée dans un
  panneau fermé avec `maxBounds` → sortie du panneau, cadrée sur la région.
- Leviers régionaux : « Pourquoi maintenant ? » en français (constat rédigé),
  conditions du catalogue conservées dans `conditions_catalogue`.
- Contrôles : segments rectangulaires 6 px, intitulés de widgets non boutons.

## 15. Territoire unique, diagnostic national, simulateur généralisé (28 octobre 2026)

- **Un seul contrôle territorial** dans la barre (`app/components/search_box.py`,
  variante `territoire`) : affiche le territoire de référence, recherche (régions,
  départements, communes, clavier), réinitialise (×, ou « France entière » dans la
  liste). La sélection met à jour le territoire puis ouvre le diagnostic ; une
  commune ouvre sa fiche et rattache son département en référence. Plus de
  sélecteur déroulant.
- **Entrée « Diagnostic »** : fiche du département ou de la région de référence,
  sinon `app/pages/diagnostic_national.py` (repères officiels, zones critiques par
  région, dix départements les moins bien placés avec leurs raisons, éloignement
  INSEE). Pas de score national inventé.
- **Accueil** : cartouches ultramarins seulement en vue nationale (ou celui du
  territoire ultramarin de référence, placé avant la carte) ; carte cadrée et
  territoire en évidence ; résumé compact.
- **Prioriser** : bloc de contexte (position du territoire de référence, périmètre,
  pourquoi les départements listés ressortent : critères du quadrant A, pas un
  classement) ; étiquette « même région que votre territoire ».
- **Simulateur** : vue départementale d'abord (zones continues par classe de temps,
  communes équipées, communes éloignées, secteurs à potentiel avec lien
  « Simuler ici »), puis scénario depuis une commune ; « Avec la nouvelle offre »
  recolore les zones dont la classe change ; « Gain seulement » isole les zones
  passant sous le seuil ; isochrones IGN en couche distincte (pointillés) ;
  carroyage détaillé en couche facultative ; bouton de retour à la vue d'ensemble.
- **Généralisation** : `scripts/donnees/preparer_simulateur.py` (carreaux, zones,
  communes, contrôles → `static/geo/simulateur_index.json`) ; 98 départements
  validés (métropole, Martinique, La Réunion), 42 Mo de données dérivées dans
  `static/geo` ; Guadeloupe, Guyane, Mayotte hors champ INSEE.

## 16. Passe de finition : audit Plédéliac, contrôle territorial, header, capacité (28 octobre 2026)

- **Audit Plédéliac (Côtes-d'Armor)** : 1 556 habitants localisés, 1 214 à plus de
  15 min, et pourtant zéro gain simulé. Cause : le point d'implantation était le
  « centre » API Géo (centroïde), qui tombe dans la forêt de la Hunaudaye ; le
  service IGN y raccorde l'isochrone à un chemin forestier (0,5 km² à 10 min,
  2,0 km² à 20 min, aucun carreau contenu). Projections, croisement spatial,
  seuils et intersections vérifiés carreau par carreau : corrects. Depuis la
  mairie : 73 km² à 10 min, 188 km² à 15 min ; 1 205 des 1 214 habitants de la
  commune passent sous 15 min (gain départemental : +2 652 à 10 min, +1 647 à
  15 min, +46 à 20 min). Sur dix communes (rurales, montagne, urbaines, outre-mer)
  le point retenu change les gains du simple au décuple (Lamballe-Armor : 412 ou
  29 habitants à 10 min selon centroïde ou mairie).
- **Correction** : point d'implantation = mairie (API Géo, champ `mairie`,
  34 846 communes couvertes), à défaut carreau habité le plus peuplé, à défaut
  centroïde ; détection d'isochrone dégénérée (surface 10 min < 2 km² ou aucun
  carreau de la commune contenu à 15 min) → point de repli, sinon « scénario
  indisponible » explicite (jamais un zéro trompeur). Fixtures enregistrées
  (`tests/fixtures/isochrones_pledeliac_*.json`) et tests de non-régression.
- **Petits volumes** : pourcentages honnêtes aux bornes (« > 99,9 % », « < 0,1 % »)
  au lieu de 100 % / 0 % lorsque des habitants existent de l'autre côté (Paris :
  104 habitants à plus de 15 min).
- **Nouvelle offre** : définie à l'écran (point hypothétique de consultation, sans
  hypothèse de capacité), marqueur épingle marine avec étiquette, légende par mode,
  seule l'isochrone du seuil affichée par défaut (les autres en couches), mention
  explicite des deux distanciers (OSRM / Valhalla) et de leurs conséquences.
- **Contrôle territorial** (`search_frontend/index.html`, `search_box.py`) :
  étiquette supprimable (« Bretagne × »), menu ouvert au clic sans saisie
  (France entière, régions, départements, communes rendues par tranches de 40),
  filtrage en direct, clavier. Sélectionner un territoire change la référence
  **sans quitter la page** ; seule une fiche (Diagnostic) suit le territoire.
  Territoire exact de niveau commune (`Territoire("commune", "Nom|dept")`,
  paramètre `t=cNom|dept`) : la barre affiche la commune, Diagnostic ouvre sa
  fiche, le simulateur la présélectionne ; les pages travaillent au département
  (`T.get()` = `as_dept()`, `T.get_exact()` = commune).
- **Header** : Streamlit enveloppe la barre dans un `stLayoutWrapper` de sa propre
  hauteur ; le sticky est posé sur cette enveloppe (`:has(> .st-key-sa_topnav)`),
  `overflow-x: clip` au lieu de `hidden` sur `.block-container` (sinon pas de sticky).
- **Capacité (ETP)** : conclusion lisible (déficit détecté ou non, population et
  communes concernées, ordre de grandeur), « équivalents temps plein » explicité,
  zéro ETP expliqué (ce que cela ne permet pas de conclure), hypothèses et
  conversions dans un panneau dépliable ; calculs inchangés.
- **Parcours** : accueil contextualisé par région (Diagnostiquer → fiche région,
  Simuler → choix explicite du département) ; entrée régionale ou nationale du
  simulateur = choix du département (aucune substitution) ; mentions « pilote »
  retirées.

## 17. Migration du score : temps INSEE 2025 et APL 2024 (28 octobre 2026, validée par William)

- **Règles actives** : dimension « temps » (20 %) = médiane pondérée par la population
  du temps en voiture vers le généraliste le plus proche (INSEE 2025, colonne
  `acces_mg_t_med`) ; APL (30 %) = APL moyen pondéré DREES, millésime 2024 ;
  pondérations, rangs percentiles, terciles, quadrants et catalogue de leviers
  inchangés. La part de population à plus de 15 min reste un repère
  complémentaire de fragilité (affichée, hors score).
- **Configuration** : `SANTACTIVE_TEMPS_SOURCE` (défaut `insee`, `interne` pour
  l'audit) ; `SANTACTIVE_APL_MILLESIME` (défaut `2024`, `2023` pour l'audit) ;
  chemins `APL_DEPT_DREES_PATH`, `APL_COMMUNES_PATH` dérivés ; libellés
  `TEMPS_LABEL_COURT`, `APL_SOURCE_LABEL` utilisés par les pages, le PDF et la
  Méthodologie. Fichiers ajoutés : `static/data/apl_mg_departemental_2024.csv`,
  `static/data/apl_communes_2024.csv` (exporteur paramétré par millésime).
- **Sauvegarde et audit** : score avant migration dans
  `data_corrections/references/audit_migration/score_v1_temps_interne_apl2023.csv` ;
  étiquette Git `avant-migration-score` ; audit des quatre combinaisons par
  `scripts/analyse/audit_migration_score.py` → `audit_migration_departements.csv`
  et `audit_migration_resume.md`.
- **Bilan chiffré (V1 → V4)** : corrélation des scores 0,966 ; écart de rang médian 5,
  maximum 27 (Corse-du-Sud) ; 18 départements déplacés de 10 rangs ou plus ;
  14 changements de zone (entrent en critique : Côtes-d'Armor, Deux-Sèvres,
  Tarn-et-Garonne ; en sortent : Allier, Aveyron, Corrèze ; passent de
  favorable à intermédiaire : Maine-et-Loire, Morbihan, Guadeloupe, Martinique ;
  d'intermédiaire à favorable : Corse-du-Sud, Haute-Corse, Marne, Puy-de-Dôme) ;
  quadrant A : 25 départements (27 avant ; sortent Aude et Vosges) ; leviers
  modifiés pour 15 départements. Effet propre du temps INSEE (V2) : 14 zones,
  20 déplacements ≥ 10 rangs ; effet propre de l'APL 2024 (V3) : 4 zones,
  aucun déplacement ≥ 10 rangs (corrélation 0,997).
- **Compatibilité APL 2024** : même définition DREES (généralistes tous âges,
  population standardisée, hors Mayotte), mêmes colonnes et agrégation ;
  18,2 % de la population sous 2,5 (16,6 % en 2023) ; 7 départements sous 2,5
  (5 en 2023).
- **Limites** : Guadeloupe et Guyane sans temps INSEE (score sur cinq dimensions,
  repli communal et PDF sur l'indicateur interne, nommé comme tel) ; les deux
  temps ne mesurent pas la même grandeur ; l'APL 2024 intègre l'évolution réelle
  de l'offre.
- **Simulateur** : hiérarchie des résultats réordonnée (indicateurs, synthèse
  courte, carte, tableau des communes bénéficiaires, panneau dépliable
  d'hypothèses et de limites) ; cartographie conservée.
- **Rang national** : calculé sur le score non arrondi (cinq égalités au dixième
  apparaissaient avec le temps INSEE, d'où des rangs en double) ; égalité stricte
  départagée par le code du département ; rangs uniques de 1 à 100 (`score_global_raw`).

## 18. Audit final avant publication (28 octobre 2026)

- **Cohérence vérifiée** : score global = moyenne pondérée des dimensions disponibles
  (recalcul indépendant, écart < 0,05 dû à l'arrondi) ; rangs uniques 1–100 ; terciles
  33/34/33 ; sources des dimensions `DREES 2024` et `INSEE 2025` ; chiffres nationaux
  identiques entre accueil, diagnostic national et calculs directs (12,3 M d'habitants
  sous APL 2,5 soit 18,2 % ; 7 départements sous 2,5 ; 514 254 habitants à plus de
  15 min soit 0,8 %) ; agrégats départementaux INSEE et simulateur alignés (carreaux
  réécrits à deux décimales : Cher 8 072 contre 8 080 habitants à plus de 15 min,
  écart < 0,2 % d'arrondi).
- **Guadeloupe et Guyane** (sans temps INSEE, score sur cinq dimensions) :
  Guadeloupe 57,8 (62ᵉ, intermédiaire), Guyane 29,7 (17ᵉ, critique). Sensibilité à
  une imputation du temps : médiane nationale → 61ᵉ / 24ᵉ ; pire valeur → 44ᵉ / 6ᵉ ;
  meilleure valeur → 75ᵉ (favorable) / 40ᵉ (intermédiaire). La comparaison nationale
  reste défendable (zone inchangée sauf dans l'hypothèse la plus favorable) ; la fiche
  affiche la dimension comme « non disponible, exclue du score », le PDF porte
  désormais une mention explicite (score sur 5 dimensions).
- **Corrections certaines** : contours départementaux servis en local
  (`static/geo/departements_simplifie.geojson`, téléchargement en repli) ;
  `requirements.txt` réduit aux dépendances réellement importées (ajout de shapely,
  retrait de geopandas, scikit-learn, statsmodels, streamlit-searchbox, weasyprint
  non utilisés) ; dtypes compacts pour les transactions DVF (122 → 9 Mo) ; infobulles
  APL et score (sources DREES/INSEE) ; note PDF sur les dimensions manquantes.
- **Décision méthodologique à trancher (non modifiée)** : les indicateurs « communes
  critiques » (`nb_communes_critiques`, `pop_communes_critiques`,
  `part_pop_communes_critiques`) et les « secteurs » cités dans les leviers viennent
  encore du fichier interne (1 228 communes, 219 218 habitants à plus de 15 min) alors
  que l'INSEE en compte 1 928 et 514 254. Les leviers mêlent donc un temps médian INSEE
  et des comptes de communes internes sur la même carte. Bascule simulée vers l'INSEE :
  leviers modifiés dans 13 départements ruraux (ajout d'équipes mobiles et de navettes :
  Allier, Hautes-Alpes, Ardèche, Ariège, Aveyron, Corrèze, Dordogne, Gers, Lot,
  Haute-Marne, Nièvre, Var, Vosges). Recommandation : basculer avant publication.
- **Seuils absolus hérités** (pilotage régional : « temps > 12 min », « ≤ 10 min ») :
  déjà quasi inertes avec l'indicateur interne (1 et 99 départements), inertes avec
  l'INSEE (0 et 98) ; à remplacer par un critère relatif (au-dessus du 3ᵉ quartile,
  3,3 min) si l'on souhaite conserver ces mentions.

## 19. Communes critiques et secteurs des leviers : INSEE 2025 (28 octobre 2026, validé par William)

- **Règle** : `nb_communes_critiques` (communes dont le temps moyen vers un généraliste
  dépasse 15 min), `pop_communes_critiques` (habitants des carreaux à plus de 15 min)
  et `part_pop_communes_critiques` viennent de l'INSEE 2025 lorsque le département est
  couvert (98) ; Guadeloupe et Guyane gardent le fichier interne, avec la colonne
  `communes_critiques_source` = « interne » et une mention « indicateur interne, hors
  champ INSEE » dans les textes. Les valeurs internes restent disponibles sous
  `*_interne`. Secteurs cités dans les leviers et l'audio : communes INSEE dont le temps
  moyen dépasse 15 min, les plus peuplées (population municipale API Géo).
- **Volumes** : 1 937 communes et 531 480 habitants (dont 9 communes et 17 k habitants
  internes pour 971/973) contre 1 228 communes et 219 218 habitants avec l'ancien
  fichier. Départements à 3 % ou plus de la population à plus de 15 min : 18 (7 avant).
- **Leviers** (règles inchangées : « ≥ 3 % de la population à plus de 15 min » requis
  pour les équipes mobiles et le transport solidaire, « ≥ 15 communes », « ≥ 10 communes »
  pour le repérage gériatrique) : 13 départements modifiés, tous ruraux ou péri-urbains,
  tous entre 3,1 % et 6,4 % de population éloignée selon l'INSEE alors que l'ancien
  fichier les plaçait sous 3 % (Dordogne 0,3 % → 3,1 %, Gers 0,9 % → 4,5 %, Lot
  1,9 % → 6,4 %). Ajouts : équipes mobiles (Allier, Hautes-Alpes, Ardèche, Ariège,
  Aveyron, Corrèze, Dordogne, Gers, Lot, Haute-Marne, Nièvre), transport solidaire
  (Hautes-Alpes, Ariège, Aveyron, Corrèze, Dordogne, Gers, Lot, avec 65 ans et plus au-dessus
  de la médiane), repérage gériatrique (Var, Vosges : plus de 10 communes éloignées et
  65 ans et plus > médiane + 2 points). Retraits par plafonnement à quatre leviers et
  deux par famille : téléconsultation (Ardèche), repérage gériatrique (Aveyron, Corrèze,
  Dordogne, Haute-Marne), MSP (Nièvre), « maintien » (Vosges). Détail :
  `data_corrections/references/audit_migration/leviers_avant_apres_insee.csv`.
- **Seuils absolus retirés** (pilotage régional) : « temps > 12 min » et « ≤ 10 min »
  n'avaient plus de sens à l'échelle INSEE (médianes de 1 à 6 min ; 1 et 99 départements
  concernés avec l'ancien indicateur). Remplacés par des comparaisons statistiques :
  temps médian au-dessus du troisième quartile des départements (`temps_acces_national_p75`,
  3,3 min) → « temps d'accès élevé » ; au plus égal à la médiane nationale → « temps d'accès
  correct ». Seuil de politique publique conservé : 15 min (convention de lecture
  Sant'active, même valeur que la part INSEE affichée partout). Libellés « vers
  l'établissement le plus proche » corrigés en « vers un généraliste ».
- **Distinction maintenue** : temps de trajet (INSEE), présence d'un généraliste (BPE),
  disponibilité effective des soins (non mesurée : délais, capacité).

## 20. Carte continue des temps d'accès : expérimentation Creuse, Dordogne, Gironde (28 octobre 2026)

- **Méthode (approche B validée)** : grille Lambert-93 de 500 m sur le département (contours
  communaux API Géo), temps en voiture OSRM local (profil voiture, OpenStreetMap, six
  extraits Geofabrik fusionnés, 1,4 Go, graphe construit en 7 min, pic mémoire 5,6 Go)
  depuis la route la plus proche de chaque maille vers le plus rapide des 30 cabinets les
  plus proches à vol d'oiseau (BPE 2025 géolocalisée, type D265, qualité A/B ou M repérée
  à la voie ; 900 cabinets exclus en France, placés au hasard dans la commune), cabinets
  du département et des voisins dans un rayon de 30 km. Statuts : calculé (route à moins
  de 500 m), approché (route entre 500 m et 2 km, teinte claire), non calculé (gris).
  Polygones par (classe, statut), découpés au contour, simplifiés à 60 m.
  Script : `scripts/donnees/carte_continue.py` ; sorties `static/geo/grille_mg_<dept>.csv.gz`,
  `continu_mg_<dept>.json`, `controle_continu_<dept>.json`.
- **Témoin K** : avec 10 voisins, 2,7 % des mailles de Gironde manquaient le cabinet le plus
  rapide (Garonne, estuaire : jusqu'à 11 min d'écart) ; 20 → 0,6 % ; 30 retenu (témoin 60 :
  0 % en Creuse et Dordogne, 0,9 % en Gironde, écart maximal 4,8 min).
- **Contrôle contre les carreaux INSEE 2025** (carreau → maille la plus proche) :

  | Département | Carreaux | Même classe (habitants) | Écart médian | Accord seuil 10 | Accord seuil 15 | Accord seuil 20 |
  |---|---|---|---|---|---|---|
  | Creuse (rural) | 15 870 | 84,8 % (rural 81,9 %, urbain 99,4 %) | −0,4 min | 90,0 % | 93,5 % | 98,2 % |
  | Dordogne (mixte) | 48 997 | 88,0 % (rural 86,3 %, urbain 94,2 %) | +0,1 min | 93,4 % | 97,2 % | 99,6 % |
  | Gironde (urbain) | 56 520 | 94,9 % (rural 89,4 %, urbain 97,7 %) | +0,1 min | 96,7 % | 99,1 % | 99,7 % |

  Les désaccords sont concentrés aux limites de classes (90ᵉ centile de l'écart absolu :
  1,7 à 2,9 min) ; la grille est légèrement plus rapide que l'INSEE en Creuse (réseau 2026
  contre 2022, départ depuis la route et non depuis le carreau). Aucun carreau habité en
  zone « non calculé » (Gironde : 4 sur 56 520).
- **Volumes et performances** : calcul 16 à 52 s par département (dont témoin), fichiers
  0,9 à 1,8 Mo par département (grille + polygones), 4 Mo pour les trois ; chargement
  < 0,05 s ; pages du simulateur en 4 à 6 s dans le navigateur (inchangé).
- **Application** : couche continue utilisée comme fond lorsqu'elle existe (sinon zones
  INSEE habitées), zones INSEE et carroyage en couches facultatives, légende à six classes
  et « non calculé », note de précision sous la carte (concordance mesurée), recoloration
  des mailles contenues dans l'isochrone IGN dans « Avec la nouvelle offre » ; gains et
  populations toujours sur les carreaux INSEE.

## 21. V1 figée pour la mise en production (28 octobre 2026)

- Fonctionnalités de la V1 : parcours territorial (contrôle unifié, territoire de
  référence, Diagnostic par niveau), Prioriser, Diagnostic national / régional /
  départemental / communal, Comparer, simulateur d'implantation (98 départements,
  cartographie INSEE par zones habitées, isochrones IGN, trois modes), leviers,
  exports PDF, Méthodologie. Règles actives : APL DREES 2024, temps INSEE 2025 (score,
  communes critiques, leviers, exports), rangs uniques, pondérations inchangées.
- Carte continue (phase C) : désactivée en production (`SANTACTIVE_CARTE_CONTINUE=off`
  par défaut) ; code conservé inerte ; données expérimentales (Creuse, Dordogne,
  Gironde) et pipeline conservés sur la branche locale `v2/carte-continue`, non
  publiée. Reprise V2 : `docs/ETUDE_CARTE_CONTINUE.md` et §20.
- Déploiement : dépôt GitHub public `8liams/santactive`, branche `main`, Streamlit
  Community Cloud (webhook `share.streamlit.io`, application `santactive.streamlit.app`) ;
  Dockerfile et `railway.toml` conservés pour un hébergement alternatif.
