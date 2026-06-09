# Dashboard Santé & Territoires

Outil d'aide à la décision territoriale destiné aux **ARS**, **préfectures** et **élus
locaux** pour piloter la politique de santé à la maille départementale. Le dashboard
croise densité médicale, accès aux soins, pathologies, démographie et immobilier pour
identifier les zones prioritaires d'intervention.

## Sources de données

| Dataset                  | Source        | Millésime |
|--------------------------|---------------|-----------|
| Population & âge         | INSEE         | 2021      |
| Professionnels de santé  | RPPS          | 2026      |
| Établissements de soin   | FINESS        | 2026      |
| Prix immobilier          | DVF (médiane) | 2025      |
| Ruptures médicaments     | ANSM          | courant   |
| Pathologies              | CNAM          | 2023      |
| Score environnemental    | SPF / DREAL   | régional  |

⚠️ Le score environnemental n'est disponible qu'à la maille régionale : il est affiché
comme indicateur d'information mais **exclu du score global** (qui reste strictement
départemental).

## Prérequis

- Python 3.10+
- macOS ou Linux
- Sur macOS, `weasyprint` nécessite les dépendances système Pango :

```bash
brew install pango
```

## Installation et lancement

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

L'application sera disponible sur [http://localhost:8501](http://localhost:8501).

## Arborescence

```
dashboard_dat/
├── streamlit_app.py           # orchestrateur (< 150 lignes)
├── requirements.txt
├── README.md
└── app/
    ├── __init__.py
    ├── config.py              # IDs Drive, pondérations, constantes
    ├── data_loading.py        # chargement + construction du master
    ├── scoring.py             # percentile_rank, compute_scores, jauge
    ├── components/            # composants UI réutilisables (étape 2)
    └── tabs/
        ├── tab_decision.py    # Aide à la décision
        ├── tab_map.py         # Carte & vue nationale
        ├── tab_pathologies.py # Pathologies
        ├── tab_ages.py        # Tranches d'âge
        ├── tab_medicaments.py # Médicaments ANSM
        └── tab_immobilier.py  # Immobilier & santé
```

## Méthodologie du score

Chaque indicateur est transformé en **rang percentile national** (0–100) :
100 = meilleure situation relative, 50 = médiane nationale, 0 = plus défavorable.

Le **score global** Sant'active v2 est une moyenne pondérée de **6 dimensions** :

| Dimension | Poids |
|-----------|-------|
| APL (accessibilité aux soins de ville) | 30 % |
| Temps d'accès médian | 20 % |
| Médecins généralistes / 100k | 20 % |
| Structures de soins / 100k | 15 % |
| Part des 65 ans et plus | 10 % |
| Prix immobilier médian | 5 % |

Si une dimension manque, son poids est redistribué sur les dimensions disponibles.
Un score global n'est calculé que si **au moins 3 dimensions** sont disponibles.

Les sous-scores `score_acces`, `score_pros` et `score_etabs` facilitent la lecture
du diagnostic mais ne constituent pas à eux seuls la formule du score global.

Les zones (Critique / Intermédiaire / Favorable) sont définies par les **terciles réels**
du score global (33ᵉ et 66ᵉ centiles), et non par des seuils fixes.

Voir `app/scoring.py` → `DIMENSIONS` et `compute_scores()`.
