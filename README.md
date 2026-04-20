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

Chaque département reçoit trois scores en **rang percentile national** (0–100) :

- `score_acces`  — inverse du temps d'accès médian aux soins
- `score_pros`   — professionnels de santé pour 100 000 habitants
- `score_etabs`  — hôpitaux + cliniques pour 100 000 habitants

Le **score global** est une moyenne pondérée :

```
score_global = 0.35 × score_acces + 0.35 × score_pros + 0.30 × score_etabs
```

Si une composante manque, `score_global = NaN` (pas d'imputation). Les zones
(Critique / Intermédiaire / Favorable) sont définies par les **terciles réels** du score
global (33ᵉ et 66ᵉ centiles), et non par des seuils fixes.
