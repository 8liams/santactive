# Sant'active — État des lieux des données, calculs et opportunités

> Document méthodologique · Diagnostic des indicateurs existants pour construire un indice d'opportunité d'action ARS et des recommandations alignées Fondation Roche (prévention, téléexpertise, télésuivi, coordination, parcours patients, dépistage, numérique en santé).

**Date :** juin 2026 · **Statut :** audit code existant, sans implémentation.

---

## Table des matières

1. [Synthèse exécutive](#1-synthèse-exécutive)
2. [Colonnes du DataFrame `master`](#2-colonnes-du-dataframe-master)
3. [Scores déjà calculés](#3-scores-déjà-calculés)
4. [Indicateurs de fragilité territoriale](#4-indicateurs-de-fragilité-territoriale)
5. [Indicateurs de faisabilité d'action](#5-indicateurs-de-faisabilité-daction)
6. [Données pathologies CNAM](#6-données-pathologies-cnam)
7. [Calcul du besoin réel en professionnels](#7-calcul-du-besoin-réel-en-professionnels)
8. [Recommandations déjà générées](#8-recommandations-déjà-générées)
9. [Pages région et nationale](#9-pages-région-et-nationale)
10. [Croisements possibles pour futurs indices](#10-croisements-possibles-pour-futurs-indices)
11. [Points d'attention et lacunes](#11-points-dattention-et-lacunes)
12. [Datasets secondaires (hors `master`)](#12-datasets-secondaires-hors-master)

---

## 1. Synthèse exécutive

| Ce qui existe déjà | Ce qui manque pour les objectifs ARS / Roche |
|--------------------|----------------------------------------------|
| Score global v2 (6 dimensions), APL, RPPS, FINESS, pathologies CNAM, temps d'accès, immobilier | Indice ARS dédié, score prévention/numérique formalisés |
| Recommandations textuelles (jusqu'à 4) avec quelques leviers Roche (télémédecine, prévention, EHPAD) | Recommandations **non chiffrées par levier** ; cas « IPA spécialistes » **documenté mais non codé** |
| Données commune (prix, temps, établissements) | MSP, CPTS, EHPAD, télésuivi : **absents des données** |
| `gauge_investissement` = `100 - score_global` | **Fonction définie mais jamais appelée** |
| CSV délais DREES **régionaux** chargé en mémoire | **Jamais utilisé** dans l'UI (proxy APL à la place) |

### Objectifs visés (hors scope de ce document)

1. Indice d'opportunité d'action pour les ARS
2. Recommandations plus réalistes que « ajouter des médecins »
3. Leviers compatibles Fondation Roche : prévention, téléexpertise, télésuivi, coordination, parcours patients, dépistage, numérique en santé

---

## 2. Colonnes du DataFrame `master`

Une ligne = **1 département** (~101 lignes). Colonnes issues de `app/data_loading.py` (`load_all_data()`) + `app/scoring.py` (`compute_scores()`).

### 2.1 Identité et géographie

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `dept` | Code département (zero-pad) | INSEE (via pop) | Département | Texte / code |
| `Nom du département` | Libellé | INSEE | Département | Texte |
| `Nom de la région` | Libellé région | INSEE | Département (attribut régional) | Texte |
| `Code région` | Code INSEE région | INSEE | Département | Texte |
| `Code_region` | Doublon issu de la jointure environnement | SPF/DREAL | Région (répliqué sur chaque dept) | Texte |

### 2.2 Démographie

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `population` | Population totale | INSEE RP 2021 | Département | Nombre brut |
| `population_num` | Population numérique nettoyée | Dérivé | Département | Nombre brut |
| `densite` | Densité hab/km² | INSEE | Département | Nombre brut |
| `pct_moins_25` | Part < 25 ans (%) | INSEE | Département | Ratio |
| `pct_25_64` | Part 25–64 ans (%) | INSEE | Département | Ratio |
| `pct_plus_65` | Part ≥ 65 ans (%) | INSEE | Département | Ratio |

### 2.3 Professionnels de santé (RPPS)

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `nb_pros` | Total professionnels RPPS | RPPS janv. 2026 | Département | Nombre brut |
| `nb_med_gen` | Médecins généralistes | RPPS | Département | Nombre brut |
| `nb_infirmiers` | Infirmiers | RPPS | Département | Nombre brut |
| `nb_pharmaciens` | Pharmaciens | RPPS | Département | Nombre brut |
| `pros_pour_100k` | Tous pros / 100k hab. | Dérivé | Département | Ratio |
| `med_gen_pour_100k` | MG / 100k hab. | Dérivé | Département | Ratio |

> Détail par spécialité : dataset séparé `pros` (`dept`, `specialite_libelle`), **pas dans `master`**.

### 2.4 Établissements (FINESS)

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `nb_etabs` | Total établissements comptés | FINESS mars 2026 | Département | Nombre brut |
| `nb_hopitaux` | CH + CHR | FINESS (`categetab`) | Département | Nombre brut |
| `nb_cliniques` | Cliniques / privé | FINESS | Département | Nombre brut |
| `hopitaux_pour_100k` | Hôpitaux / 100k | Dérivé | Département | Ratio |
| `structures_pour_100k` | (Hôpitaux + cliniques) / 100k | Dérivé | Département | Ratio |

> Coordonnées GPS, nom, catégorie : dataset `etabs` (maille commune).

### 2.5 Accessibilité physique

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `temps_acces_median` | Temps trajet médian vers établissement le plus proche | Calcul interne FINESS + INSEE | Département (agrégé) | Nombre brut |
| `temps_acces_p90` | 90e percentile temps d'accès | Idem | Département | Nombre brut |
| `temps_acces_max` | Temps max | Idem | Département | Nombre brut |
| `nb_communes` | Nb communes dans le calcul | Idem | Département | Nombre brut |
| `nb_communes_critiques` | Communes avec temps > **15 min** | Idem | Département | Nombre brut |

> Détail commune : dataset `temps` (`code_departement`, `commune`, `temps_acces`).

### 2.6 Immobilier (DVF)

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `prix_m2_moyen` | Médiane prix/m² départementale | DVF 2025 | Département (agrégé) | Nombre brut |
| `nb_transactions` | Nb transactions | DVF | Département | Nombre brut |
| `surface_moy` | Surface moyenne | DVF | Département | Nombre brut |

> Détail commune : dataset `immo` (`commune`, `prix_m2`).

### 2.7 APL (accessibilité soins de ville)

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `apl_median_dept` | APL médian département | ANCT 2023 (`static/data/apl_2023.csv`) | Département | Nombre brut |
| `apl_p25` | APL 25e percentile | ANCT | Département | Nombre brut |
| `apl_p75` | APL 75e percentile | ANCT | Département | Nombre brut |

**Seuil désert médical DREES :** APL < 2,5 consultations/an/habitant.

### 2.8 Environnement

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `enviro_score` | Score environnemental | SPF/DREAL | **Région** (jointure sur code région) | Score (/20) |

> **Exclu du score global.** Présent dans `master` mais **non affiché** sur la fiche département principale (utilisé dans `app/export/pdf_generator.py`).

### 2.9 Scores calculés (`app/scoring.py`)

| Colonne | Signification | Source | Niveau | Type |
|---------|---------------|--------|--------|------|
| `score_apl` | Rang percentile APL | Calcul | Département | Score 0–100 |
| `score_medecins` | Rang percentile MG/100k | Calcul | Département | Score |
| `score_etabs` | Rang percentile structures/100k | Calcul | Département | Score |
| `score_temps` | Rang percentile temps (inversé) | Calcul | Département | Score |
| `score_seniors` | Rang percentile 65+ (inversé) | Calcul | Département | Score |
| `score_foncier` | Rang percentile prix/m² (inversé) | Calcul | Département | Score |
| `score_global` | Moyenne pondérée v2 | Calcul | Département | Score |
| `score_acces` | Sous-score APL 60 % + temps 40 % | Calcul | Département | Score |
| `score_pros` | Alias de `score_medecins` | Calcul | Département | Score |
| `nb_dimensions_ok` | Nb dimensions calculées (sur 6) | Calcul | Département | Nombre |
| `rang_national` | Classement (1 = pire situation) | Calcul | Département | Rang |
| `nb_classes` | Nb départements scorés | Calcul | National | Nombre |
| `zone_short` | Critique / Intermédiaire / Favorable | Calcul (terciles réels) | Département | Catégorie |
| `zone_color` | Couleur hex zone | Calcul | Département | Texte |
| `zone_detail` | Libellé tercile | Calcul | Département | Texte |
| `zone` | Libellé long avec emoji | Calcul | Département | Texte |
| `typologie` | urbain_dense / urbain / peri_urbain / rural | Calcul (seuils densité) | Département | Catégorie |

### 2.10 Colonnes `master` peu ou pas exploitées dans l'UI

Les colonnes suivantes sont **calculées et présentes** dans `master`, mais **rarement ou jamais affichées** :

`nb_pros`, `nb_infirmiers`, `nb_pharmaciens`, `nb_etabs`, `nb_hopitaux`, `nb_cliniques`, `pros_pour_100k`, `hopitaux_pour_100k`, `apl_p25`, `apl_p75`, `temps_acces_p90`, `temps_acces_max`, `nb_communes`, `surface_moy`, `nb_transactions`, `Code_region`, `enviro_score`.

---

## 3. Scores déjà calculés

### 3.1 Score Sant'active v2 — `compute_scores()` · `app/scoring.py`

**Principe commun :** `percentile_rank()` = rang percentile national × 100.

**Sens général : 100 = meilleur département, 0 = pire.** Pour les dimensions « plus bas = mieux », le rang est inversé (`100 − rang`).

| Score | Formule | Variables brutes | Pondération dans `score_global` | Sens 0/100 | Limites connues |
|-------|---------|------------------|--------------------------------|------------|-----------------|
| `score_apl` | Percentile(`apl_median_dept`), ↑ | APL ANCT | **30 %** | 0 = pire | NaN si APL absent |
| `score_medecins` | Percentile(`med_gen_pour_100k`), ↑ | RPPS | **20 %** | 0 = pire | RPPS inclut hospitalier + libéral |
| `score_etabs` | Percentile(`structures_pour_100k`), ↑ | FINESS | **15 %** | 0 = pire | Hôpitaux + cliniques seulement |
| `score_temps` | Percentile(`temps_acces_median`), ↓ | Temps accès | **20 %** | 0 = pire | Seuil commune critique = 15 min |
| `score_seniors` | Percentile(`pct_plus_65`), ↓ | INSEE | **10 %** | 0 = pire | Proxy de demande, pas besoins cliniques |
| `score_foncier` | Percentile(`prix_m2_moyen`), ↓ | DVF | **5 %** | 0 = pire | Médiane dept, pas foncier médical |
| **`score_global`** | `Σ(poids × score_dim) / Σ(poids_disponibles)` | Scores ci-dessus | 100 % | 0 = pire | **Minimum 3 dimensions** sinon NaN |
| `score_acces` | `0.6 × score_apl + 0.4 × score_temps` (fallback partiel) | Scores APL/temps | Hors global (sous-score) | 0 = pire | Utilisé dans reco + scorecard |
| `score_pros` | = `score_medecins` | — | Alias | 0 = pire | — |

**Classification en zones (`zone_short`) :** terciles **réels** du `score_global` (33e et 66e centiles).

**Typologie (`typologie`) — seuils dans `scoring.py` :**

| Densité (hab/km²) | Typologie |
|-------------------|-----------|
| > 1000 | `urbain_dense` |
| > 250 | `urbain` |
| > 80 | `peri_urbain` |
| ≤ 80 | `rural` |

> Pondérations officielles : `app/scoring.py` → `DIMENSIONS` (Sant'active v2, 6 dimensions).

### 3.2 `gauge_investissement()` · `app/scoring.py`

| Élément | Détail |
|---------|--------|
| **Fonction** | `gauge_investissement(row)` |
| **Formule** | `100 − score_global` |
| **Sens** | **100 = forte opportunité d'investissement** (inverse du score territorial) |
| **Limite** | **Jamais appelée** dans l'application |

### 3.3 Délais RDV estimés — `compute_delais_proxy()` · `app/components/delais.py`

| Élément | Détail |
|---------|--------|
| **Fonction** | `compute_delais_proxy(dept_code, apl_dept, apl_nationale=2.9)` |
| **Formule** | `delai_estime = delai_national × min(APL_nationale / APL_dept, 3.0)` |
| **Variables** | `delai_median_jours` (CSV `static/data/delais_rdv_nationaux.csv`), APL dept, APL nat = 2,9 |
| **Sens** | Plus le délai est **élevé**, plus l'accès est **mauvais** |
| **Limites** | **Estimation** basée sur DREES 2016–2017 ; plafond ×3 ; pas de mesure départementale directe |

**Spécialités dans le CSV national :** MG, Pédiatre, Radiologue, Chirurgien-dentiste, Gynécologue, Rhumatologue, Cardiologue, Dermatologue, Ophtalmologue.

### 3.4 Rangs radar comparateur — `app/pages/comparer.py`

Percentiles calculés **à la volée** sur 6 axes (dont 3 inversés : part 65+, prix/m², temps d'accès). **Non stockés dans `master`.**

### 3.5 Similarité entre départements — `find_similar_depts()` · `fiche_departement.py`

```
sim = 0,40 × |Δscore_global|/100 + 0,30 × |Δdensité| + 0,30 × |Δpct_65+|/100 + bonus région (−0,1)
```

Matching sur départements de **même zone** (`zone_short`), hors DOM si métropole.

---

## 4. Indicateurs de fragilité territoriale

Indicateurs **déjà disponibles** pour mesurer la fragilité d'un territoire.

| Indicateur | Colonne / source | Niveau | Utilisation UI |
|------------|------------------|--------|----------------|
| **APL** | `apl_median_dept` | Département | Diagnostic, score, reco, proxy délais |
| **Désert médical** | APL < 2,5 | Département | Bandeaux, diagnostic, reco |
| **Médecins /100k** | `med_gen_pour_100k` | Département | Score, offre médicale, reco |
| **Structures /100k** | `structures_pour_100k` | Département | Score, reco |
| **Temps d'accès médian** | `temps_acces_median` | Département (+ commune) | Score, carte, reco |
| **Communes « zone blanche »** | `nb_communes_critiques` (> 15 min) | Département | Diagnostic, comparer |
| **Part des 65+** | `pct_plus_65` | Département | Score, reco seniors, région |
| **Part des < 25 ans** | `pct_moins_25` | Département | Reco pédiatrie/PMI |
| **Pathologies CNAM** | dataset `patho` | Département | Top 5, offre médicale |
| **Délais RDV** | proxy dept + CSV régional (non UI) | Dept (estim.) / Région (mesuré) | Fiche dept |
| **Score global + zone** | `score_global`, `zone_short` | Département | Carte, header, reco |
| **Rang national** | `rang_national` | Département | Header fiche |
| **Densité / population** | `densite`, `population_num` | Département | Typologie, besoin réel |
| **Prix immobilier** | `prix_m2_moyen` (+ commune via `immo`) | Dept / commune | Score foncier, reco |
| **Paradoxe RPPS/APL** | croisement RPPS vs APL | Département | Bandeau offre médicale |
| **Écart intra-régional** | max − min `score_global` | Région (calcul) | Fiche région |
| **Score environnemental** | `enviro_score` | Région | Quasi invisible UI |

### Lacunes fragilité

- Pas d'indicateur **MSP / CPTS / EHPAD / HAD**
- Pas de **pathologie agrégée** dans `master` (calcul à la volée uniquement)
- Reco prévention (cas 7) cherche `prev_diabete` / `prev_cardio` **inexistants** dans `patho` → quasi jamais déclenchée
- Ruptures médicaments (ANSM) : `MEDIC_FILE_ID` dans config, **données non chargées**

---

## 5. Indicateurs de faisabilité d'action

Indicateurs pour évaluer si une intervention est **réaliste** sur un territoire.

| Levier de faisabilité | Disponible ? | Détail |
|-----------------------|--------------|--------|
| Présence établissements | **Oui** | `nb_hopitaux`, `nb_cliniques`, `nb_etabs` ; carte points FINESS ; liste commune |
| Offre pros existante | **Oui** | RPPS agrégé + détail toutes spécialités dans `pros` |
| Attractivité foncière | **Oui** | `prix_m2_moyen` dept ; médiane commune DVF |
| Densité / typologie | **Oui** | `densite`, `typologie` (⚠️ seuils différents dans reco vs scoring) |
| Communes accessibles | **Partiel** | `temps` par commune ; `nb_communes_critiques` |
| **EHPAD** | **Non** | Mention textuelle dans reco seulement |
| **Hôpitaux** | **Oui** | FINESS CH/CHR |
| **MSP / CPTS** | **Non** | Mention textuelle « MSP » dans reco cas 1 |
| Structures expérimentation | **Partiel** | Hôpitaux/cliniques + coords GPS ; pas de label « expérimentation » |
| Infirmiers / pharmaciens | **Oui dans master** | `nb_infirmiers`, `nb_pharmaciens` — **non affichés** |
| IPA / télémédecine | **Non en données** | Uniquement dans textes reco |
| Dispersion APL | **Oui** | `apl_p25`, `apl_p75` — **non exploités** |
| Volume marché immo | **Oui** | `nb_transactions` — **non affiché** |

### Typologie utilisée dans les recommandations

Seuils dans `_generate_recommendations()` · **`fiche_departement.py`** — **différents** de `scoring.typologie` :

| Densité (hab/km²) | Reco | Scoring |
|-------------------|------|---------|
| > 500 | `urbain_dense` | > 1000 |
| > 150 | `urbain` | > 250 |
| > 40 | `peri_urbain` | > 80 |
| sinon | `rural` | `rural` |

→ Un même département peut être classé « urbain » pour les recommandations et « péri-urbain » dans le header.

---

## 6. Données pathologies CNAM

### 6.1 Structure brute (`patho`)

| Colonne | Signification |
|---------|---------------|
| `dept` | Code département |
| `patho_niv1` | Libellé pathologie CNAM niveau 1 |
| `Ntop` | Nombre de patients |
| `Npop` | Population de référence |
| **Prévalence** | Calculée à l'affichage : `prev = Ntop / Npop × 100` |

**Source :** CNAM 2023 · Google Drive (`PATHO_FILE_ID`).

**Niveau géographique :** département uniquement. Pas de maille commune.

### 6.2 Pathologies exclues (`PATHOS_EXCLUDED` · `app/config.py`)

1. Pas de pathologie repérée, traitement, maternité, hospitalisation ou traitement antalgique ou anti-inflammatoire
2. Hospitalisations hors pathologies repérées (avec ou sans pathologies, traitements ou maternité)
3. Traitements du risque vasculaire (hors pathologies)
4. Traitements psychotropes (hors pathologies)

### 6.3 Pathologies mappées aux spécialités (`PATHOS_SPECIALITES_MAP`)

| Pathologie CNAM (nom exact) | Spécialités liées |
|----------------------------|-------------------|
| Maladies cardioneurovasculaires | Cardiologue, Médecin vasculaire |
| Diabète | Endocrinologue |
| Cancers | Oncologue, Radiothérapeute |
| Maladies respiratoires chroniques (hors mucoviscidose) | Pneumologue |
| Maladies psychiatriques | Psychiatre |
| Maladies neurologiques ou dégénératives | Neurologue |
| Insuffisance rénale chronique terminale | Néphrologue |
| Maladies inflammatoires ou rares ou VIH ou SIDA | Médecin interniste, Infectiologue |

### 6.4 Pathologies utilisées dans l'offre médicale (`_PATHO_RULES` · `fiche_departement.py`)

Matching par **fragment** dans `patho_niv1` :

| Fragment | Label affiché | Keywords RPPS |
|----------|---------------|---------------|
| `ardio` | Maladies cardiovasculaires | cardio, cardiolog |
| `iabète` | Diabète | endocrin, diabéto |
| `sychiatr` | Maladies psychiatriques | psychiatr, pédopsychiatr |
| `espira` | Maladies respiratoires chroniques | pneumo |
| `ancer` | Cancers | onco, hémato, cancéro |
| `phtalmolog` | Affections ophtalmologiques | ophtalmo |
| `humatolog` | Rhumatologie | rhumato |
| `eurologiq` | Neurologie | neurolo |

→ Top 5 pathologies **dynamiques** par département (prévalence max par famille), puis lien au **premier libellé RPPS** trouvé.

---

## 7. Calcul du besoin réel en professionnels

**Fichier :** `render_offre_medicale()` → fonction interne `besoin_reel()` · `app/pages/fiche_departement.py`

### 7.1 Formules réelles (code)

**Cas généralistes en désert médical (APL < 2,5) :**

```
besoin = int((2,9 − APL_dept) × population / 290)
plafond = 60
```

**Cas standard (toute spécialité, densité locale < médiane nationale) :**

```
besoin = int((mediane_nat − densité_locale) × population / 100 000)
plafond = 60
```

**Sinon :** `None` (affiché « — »)

### 7.2 Spécialités concernées à l'affichage

- **Top 5 soins primaires (fixes) :** Médecin généraliste, Infirmier, Pharmacien, Masseur-kinésithérapeute, Chirurgien-dentiste
- **Top 5 spécialistes :** dérivés des 5 pathologies prédominantes du département

### 7.3 Influence des pathologies

| Ce que dit l'UI | Ce que fait le code |
|-----------------|---------------------|
| « Amplifié par prévalence (facteur max ×2,5, plafond 60) » | **`patho_key` passé en paramètre mais jamais utilisé** |
| Badge pathologie sur spécialiste | **Visuel seulement** ; besoin = écart RPPS vs médiane |

### 7.4 Limites documentées

- RPPS = tous modes d'exercice ; APL = référence pour l'accès réel en ville
- Paradoxe RPPS élevé + APL bas → besoin MG calculé sur APL, pas RPPS
- Plafond à 60 professionnels
- Pas de projection démographique
- Spécialistes absents (0 RPPS) : besoin non calculé si médiane nationale = 0

### 7.5 Besoin dans les recommandations (cas 3)

```
deficit_nb = max(0, med_med_nat − med_100k)
besoin_installations = min(int(deficit_nb × population / 100 000), 30)
```

→ Objectif « installations MG sur 3 ans », plafond **30** (différent du plafond 60 de l'offre médicale).

---

## 8. Recommandations déjà générées

### 8.1 Département — `_generate_recommendations()` · `app/pages/fiche_departement.py`

Maximum **4 recommandations**, triées par `priority` (1 > 2 > 3). Le badge affiché = position dans la liste (1-based).

| # | Titre | Conditions de déclenchement | Indicateurs clés | Priorité | Levier Roche |
|---|-------|----------------------------|------------------|----------|--------------|
| 1 | Implanter une maison de santé pluridisciplinaire | `APL < 2,5` ET rural/péri-urbain | APL, nb_communes_critiques, prix_m2 | 1 | Coordination (MSP) |
| 2 | Télémédecine + consultations avancées | `APL < 2,5` ET urbain | APL, score_acces, temps | 1 | Téléexpertise, numérique |
| 3 | Programme d'attractivité MG / recrutement | `score_pros < 33` OU (déficit MG ET désert) | med_gen/100k, besoin_installations | 1–2 | ⚠️ « Ajouter des MG » |
| 4 | Santé numérique pour seniors isolés | `pct_65 > 22 %` ET (score_acces < 45 OU désert) | 65+, population | 2 | Télésuivi, EHPAD |
| 5 | Antennes consultations externes | `score_etabs < 33` | structures/100k, temps | 2 | Parcours / proximité |
| 6 | Navettes santé | temps > 1,4× médiane ET rural ET pas etabs critique | temps, typologie | 2 | Coordination mobilité |
| 7 | Prévention / dépistage chroniques | `prev > seuil` ET accès dégradé | **prev_diabete/cardio (bug)** | 2 | Prévention, dépistage |
| 8 | Renforcer pédiatrie / PMI | `pct_moins_25 > 32 %` ET accès/pros dégradés | < 25 ans | 3 | Prévention |
| 9 | Levier foncier pour attirer pros | `prix_m2 < 1500` ET désert | prix, APL | 3 | Attractivité installation |
| 10 | Plan de vigilance | Aucune reco ET score 33–55 | score_global, APL | 3 | Pilotage |
| 11 | Maintien des acquis | Fallback si rien d'autre | score_global, APL | 3 | Benchmark |

**Non implémenté** malgré la docstring de la fonction : « Déficit spécialistes RPPS → Consultations avancées IPA ».

**Seuils reco prévention (cas 7) :** `taux_diabete > 8,0 %` ou `taux_cardio > 10,0 %` — colonnes **`prev_diabete` / `prev_cardio` absentes** du dataset `patho`.

### 8.2 Région — `render_reco_ars()` · `app/pages/fiche_region.py`

| Titre | Déclenchement | Niveau |
|-------|---------------|--------|
| Concentrer FIR sur territoires critiques | ≥ 1 dept zone Critique (top 3 nommés) | Région |
| Plan gériatrique pour dept X | dept max `pct_plus_65` > 22 % | Région |
| Plan réduction délais ophta + psy | **Toujours affiché** (sans condition data) | Région |

→ Recommandations région = **texte politique**, pas de scoring FIR calculé.

---

## 9. Pages région et nationale

### 9.1 Accueil national (`app/pages/home.py`)

| Élément | Calculé depuis données | Fixe / hardcodé |
|---------|------------------------|-----------------|
| Carte choroplèche | `master` + geojson | — |
| 6 indicateurs carte | Colonnes master | — |
| KPI APL 2,9 | — | **Constante hardcodée** |
| KPI temps d'accès | Médiane `temps_acces_median` | Calculé |
| KPI MG/100k | Médiane `med_gen_pour_100k` | Calculé |
| KPI délai ophtalmo 52 j | — | **Constante hardcodée** |
| KPI zones critiques | Count `zone_short == Critique` | Calculé |
| Suggestions critiques | 4 dept min `score_global` | Calculé |

### 9.2 Fiche région (`app/pages/fiche_region.py`)

| Élément | Type de calcul |
|---------|----------------|
| Population totale | **Somme** des départements |
| Score moyen région | **Moyenne** `score_global` |
| APL médian région | **Médiane** des APL départementaux |
| Écart intra-régional | max − min `score_global` |
| Zone région (badge) | ≥ 50 % dept critiques → Critique ; sinon si ≥ 1 critique → Intermédiaire ; sinon Favorable |
| Diagnostic texte | Meilleur / pire département |
| Carte | GeoJSON filtré + scores dept |
| Classement | Tri `score_global` |
| Reco ARS | Heuristiques (§ 8.2) |

### 9.3 Manques vs fiche département

| Présent en département | Absent en région |
|------------------------|------------------|
| Scorecard 6 dimensions | ✗ |
| Carte communale | ✗ |
| Pathologies CNAM | ✗ |
| Offre médicale / besoin réel | ✗ |
| Délais RDV (même proxy) | ✗ |
| Recommandations chiffrées par territoire | ✗ |
| Export PDF | ✗ |
| Données `delais` DREES régionales | Chargées mais **non utilisées** |

### 9.4 Pistes pour un vrai pilotage ARS (données déjà présentes)

- Cartographie intra-régionale zones + APL + communes critiques
- Agrégation pathologies / spécialistes au niveau région (non codée aujourd'hui)
- CSV `static/data/delais_rdv_drees.csv` par région (10 spécialités × 13 régions)
- `enviro_score` régional (dans master, invisible UI)
- `apl_p25` / `apl_p75` pour hétérogénéité intra-départementale

---

## 10. Croisements possibles pour futurs indices

Propositions **conceptuelles** à partir des données existantes — **sans implémentation**.

### 10.1 Indice de priorité d'intervention

```
Priorité = f(100 − score_global, apl_median_dept, nb_communes_critiques, pct_plus_65, prev_patho_chroniques)
```

- Pondérer : désert APL (< 2,5) + communes > 15 min + top patho CNAM (cardio, diabète, psychiatrie)
- Données : `master` + agrégation `patho`

### 10.2 Indice de faisabilité

```
Faisabilité = g(structures_pour_100k, nb_hopitaux, prix_m2_moyen, densite, nb_infirmiers, nb_pharmaciens)
```

- Foncier bas + présence hôpital + infirmiers/pharmaciens = terrain favorable MSP / télésuivi
- Données : colonnes master **peu utilisées** aujourd'hui

### 10.3 Score d'opportunité d'action

```
Opportunité = gauge_investissement (100 − score_global) × Faisabilité
```

- La fonction `gauge_investissement()` existe déjà dans `scoring.py`
- Croiser avec présence d'établissements et dispersion APL (`apl_p75 − apl_p25`)

### 10.4 Score prévention

```
Prévention = h(prev_cardio, prev_diabète, prev_psychiatrique, prev_respiratoire, pct_plus_65, score_acces)
```

- Calculer prévalences depuis `patho` (comme `_render_top_pathologies`)
- Croiser avec accès dégradé → cible dépistage / parcours chroniques (aligné Fondation Roche)
- **Prérequis :** corriger le bug `prev_diabete` / `prev_cardio` dans les recommandations

### 10.5 Score numérique / téléexpertise

```
Numérique = i(typologie_urbaine, temps_acces_median, delai_estime_ophta/psy, apl_median_dept, nb_communes_critiques)
```

- **Urbain saturé** (APL bas, MG RPPS ok) → téléconsultation spécialistes
- **Rural isolé** (communes éloignées, temps élevé) → télésuivi seniors + navettes
- Données : typologie reco, proxy délais (`delais_rdv_nationaux.csv`), `temps`, `apl`
- Enrichissement : brancher **`delais_rdv_drees.csv`** (mesures régionales vs proxy)

---

## 11. Points d'attention et lacunes

| # | Point | Impact |
|---|-------|--------|
| 1 | `gauge_investissement()` et `data["delais"]` non exploités | Briques prêtes pour indice opportunité / pilotage ARS |
| 2 | Bug reco prévention : `prev_diabete` / `prev_cardio` absents | Cas 7 quasi inopérant |
| 3 | Note UI « besoin réel × prévalence » ≠ code | Affichage trompeur offre médicale |
| 4 | Deux typologies densité (reco vs scoring) | Incohérence urbain/rural |
| 5 | Pas de données MSP / CPTS / EHPAD / télésuivi | Leviers Roche = narratif, pas indicateurs |
| 6 | Cas IPA spécialistes documenté, non codé | Recommandation manquante |
| 7 | `MEDIC_FILE_ID` (ANSM) non chargé | Ruptures médicaments absentes |
| 8 | `enviro_score` dans master, invisible fiche dept | Donnée régionale sous-utilisée |
| 9 | Leviers les plus matures : télémédecine (cas 2, 4), prévention (cas 7 si corrigé), MSP (cas 1), navettes (cas 6) | Base pour refonte reco Roche |

---

## 12. Datasets secondaires (hors `master`)

| Dataset | Colonnes | Niveau | Chargé ? | Utilisé UI ? |
|---------|----------|--------|----------|--------------|
| `pros` | `dept`, `specialite_libelle` | Département (détail) | Oui | Fiche dept (offre médicale) |
| `immo` | `code_departement`, `commune`, `prix_m2` | Commune | Oui | Carte dept, fiche commune |
| `etabs` | `code_departement`, `commune`, `Rslongue`, `categetab`, `latitude`, `longitude` | Commune | Oui | Carte dept, fiche commune |
| `temps` | `code_departement`, `commune`, `temps_acces` | Commune | Oui | Carte dept, fiche commune, recherche |
| `env` | `Code_region`, `nom_region`, `enviro_score` | Région | Oui | Jointure master uniquement |
| `patho` | `dept`, `patho_niv1`, `Ntop`, `Npop` | Département | Oui | Fiche dept |
| `delais` | `code_region`, `region`, `specialite`, `delai_jours_median`, `delai_jours_p75` | Région | Oui | **Non** |
| `delais_rdv_nationaux.csv` | `specialite`, `delai_median_jours`, … | National | Oui (à la demande) | Proxy dept |
| `geojson` | Contours départements | Département | Oui | Cartes nationales / région |

**Spécialités DREES régionales** (`delais_rdv_drees.csv`) : Ophtalmologue, Dermatologue, Cardiologue, Gynécologue, Psychiatre, Généraliste, Pédiatre, ORL, Rhumatologue, Endocrinologue.

---

## Références code

| Module | Rôle |
|--------|------|
| `app/data_loading.py` | Construction `master` et datasets secondaires |
| `app/scoring.py` | Scores v2, zones, typologie, `gauge_investissement` |
| `app/components/delais.py` | Proxy délais RDV, seuil désert |
| `app/pages/fiche_departement.py` | Diagnostic, reco, offre médicale, besoin réel |
| `app/pages/fiche_region.py` | Agrégations régionales, reco ARS |
| `app/pages/home.py` | Vue nationale, KPIs |
| `app/config.py` | Mapping pathologies, constantes, IDs Drive |

---

*Document généré pour le projet Sant'active — ESData / ESD Paris, 2026.*

*Voir aussi : [GUIDE_TECHNIQUE.md](./GUIDE_TECHNIQUE.md) pour l'architecture générale de l'application.*
