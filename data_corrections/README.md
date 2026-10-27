# Corrections de données préparées — NON APPLIQUÉES

Rien dans ce dossier n'est lu par l'application. Les fichiers de `static/data/`
sont inchangés tant que les corrections ne sont pas validées.

Chaque fichier est régénérable depuis la racine du dépôt :

| Script | Sorties | Objet |
|---|---|---|
| `scripts/donnees/corriger_population.py` | `population_corrigee.csv`, `population_rapport.csv` | Densité et parts d'âge décalées de 2 lignes pour 11 départements (21 à 29, 2A, 2B). Permutation des valeurs existantes, validée contre l'INSEE (âges 2021) et les surfaces IGN. |
| `scripts/donnees/corriger_finess.py` | `etablissements_corrige.csv.gz`, `finess_codes_rapport.csv` | 289 établissements mal codés : Guadeloupe → 2A, Martinique → 2B, Guyane 9C, Réunion 9D, Mayotte « 9,00 F », etc. Recodage d'après la colonne `Libdepartement` du même fichier. |
| `scripts/donnees/diagnostic_professionnels.py` | `professionnels_diagnostic.csv` | Diagnostic seul (pas de correction) : enregistrements démultipliés par le nombre de communes du code postal ; ≈ 1 enregistrement par (code postal, ville, spécialité). |
| `scripts/donnees/comparer_scores.py` | `impact_scores_*.csv` | Scores, rangs, zones et typologies avant / après une correction candidate. |

Références officielles mises en cache dans `references/` (source et empreinte
SHA-256 dans les fichiers `.json` associés quand il s'agit d'un fichier
téléchargé) : surfaces communales et codes postaux (geo.api.gouv.fr), parts
d'âge 2021 (INSEE, estimations de population).

Pour appliquer une correction validée : copier le fichier corrigé à la place
de l'original dans `static/data/`, relancer les tests
(`python3 -m unittest discover -s tests`) et committer avec le rapport.
