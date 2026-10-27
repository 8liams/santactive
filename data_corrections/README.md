# Corrections et nouvelles sources de données

Tout est régénérable depuis la racine du dépôt. Les originaux remplacés sont
conservés dans `originaux/` (empreintes SHA-256 dans les messages de commit).

## Appliquées sur la branche (validées)

| Donnée | Script | État |
|---|---|---|
| `static/data/population.csv` | `scripts/donnees/corriger_population.py` | Densité et parts d'âge réalignées pour 21–29, 2A, 2B (permutation des valeurs existantes, validée contre INSEE 2021 et surfaces IGN). Original : `originaux/population.csv`. |
| `static/data/etablissements.csv.gz` | `scripts/donnees/corriger_finess.py` | 289 lignes recodées d'après `Libdepartement` (Guadeloupe 2A→971, Martinique 2B→972, Guyane 9C→973, Réunion 9D→974, Mayotte « 9,00 F »→976, 975, 986). Original : `originaux/etablissements.csv.gz`. |
| `static/data/delais_rdv_nationaux.csv` | (transcription manuelle du tableau 1, DREES ER 1085) | Médianes rétablies (7 spécialités sur 9 portaient la moyenne) + D1/Q1/Q3/D9. Original : `originaux/delais_rdv_nationaux.csv`. |

## Préparées, NON appliquées (en attente de décision)

| Donnée | Script | Fichiers candidats |
|---|---|---|
| Effectifs DREES/RPPS 2026 (jeu A) | `scripts/donnees/telecharger_drees_rpps.py` | `references/drees/drees_medecins_dept_2026.csv`, `drees_autres_rpps_dept_2026.csv`, `drees_infirmieres_liberales_dept_2023.csv` → à copier dans `static/data/` pour activer. Provenance : `references/drees/provenance.json`. |
| APL départemental pondéré + simulation ETP | `scripts/donnees/calculer_apl_departemental.py` | `references/drees/apl_mg_departemental_2023.csv` → à copier dans `static/data/` pour afficher la section « APL communal » des fiches (le score reste sur la médiane). |
| Diagnostic du fichier professionnels (jeu B) | `scripts/donnees/diagnostic_professionnels.py` | `professionnels_diagnostic.csv` (aucune correction possible sans identifiant). |

Fichiers bruts DREES (≈130 Mo) : `references/drees/raw/`, ignoré par Git.

## Comparatifs avant / après

`scripts/donnees/comparer_scores.py [--population …] [--etablissements …] [--drees DOSSIER]`
→ `impact_scores_population.csv`, `impact_scores_finess.csv`,
`impact_scores_population_finess.csv`, `impact_scores_drees.csv`.

## Études

`scripts/analyse/simulation_indices.py` → `simulation_indices.csv` (indices offre / besoins, non appliqués).
