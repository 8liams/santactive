# Sant'active — Design du moteur de priorisation d'actions territoriales

> Document méthodologique · Grand chantier priorisation · **Sans implémentation UI ni modification du score santé**

**Date :** juin 2026 · **Statut :** spécification cible · **Périmètre :** moteur de calcul uniquement

**Question centrale :** *« Dans quel territoire une action a-t-elle le plus de sens aujourd'hui ? »*

---

## Table des matières

1. [Principes directeurs](#1-principes-directeurs)
2. [Inventaire des données](#2-inventaire-des-données)
3. [Score d'opportunité d'action](#3-score-dopportunité-daction)
4. [Bibliothèque d'actions](#4-bibliothèque-dactions)
5. [Fiche type par action](#5-fiche-type-par-action)
6. [Modèle de scoring commun](#6-modèle-de-scoring-commun)
7. [Architecture logicielle cible](#7-architecture-logicielle-cible)
8. [Phase suivante — indicateurs d'impact affichables](#8-phase-suivante--indicateurs-dimpact-affichables)
9. [Migration depuis l'existant](#9-migration-depuis-lexistant)
10. [Limites, risques et garde-fous](#10-limites-risques-et-garde-fous)
11. [Plan de mise en œuvre](#11-plan-de-mise-en-œuvre)

---

## 1. Principes directeurs

### 1.1 Distinction score santé ↔ score opportunité

| Dimension | Score Sant'active (`score_global`) | Score opportunité d'action |
|-----------|-----------------------------------|----------------------------|
| **Question** | Quelle est la fragilité territoriale ? | Où agir en priorité, avec quel levier ? |
| **Nature** | Indice composite unique, 6 dimensions fixes | Score **par action × territoire** |
| **Sens** | 0 = pire situation, 100 = meilleure | 0 = action peu pertinente, 100 = forte opportunité |
| **Usage** | Cartographie, diagnostic, zones | Classement des recommandations et leviers |
| **Dépendance** | Autonome | Peut **s'inspirer** du score sans le recopier |

> **Règle absolue :** le moteur d'action **ne modifie pas** `app/scoring.py` ni les colonnes `score_*` existantes.  
> La fonction `gauge_investissement()` (100 − score_global) est un **proxy grossier** ; elle peut servir de **signal secondaire** dans le score besoin, jamais comme score opportunité final.

### 1.2 Quatre piliers du score opportunité

Chaque action sur chaque territoire reçoit :

1. **Besoin sanitaire** — l'écart entre la situation locale et un niveau acceptable *pour cette action*
2. **Population concernée** — volume et profil des personnes potentiellement touchées
3. **Potentiel d'impact** — effet attendu si l'action réussit (amplitude du problème × population)
4. **Faisabilité opérationnelle** — existence de relais, contraintes géographiques, attractivité d'ancrage

### 1.3 Granularités

| Niveau | Rôle dans le moteur | Source |
|--------|---------------------|--------|
| **Département** | Unité principale de scoring | `master` |
| **Commune** | Affinement géographique (ciblage MSP, navettes) | `temps`, `immo`, `etabs` |
| **Région** | Contexte délais spécialistes, agrégation pilotage ARS | `delais`, agrégations |
| **National** | Références et percentiles | Médianes / rangs sur 101 dept |

Le moteur calcule d'abord au **département**. Les vues régionales agrègent (top actions, somme populations touchées, moyenne pondérée).

### 1.4 Héritage de l'existant

Le classement territorial régional (`compute_dept_priorities` · `app/region_pilotage.py`) est **réutilisable comme brique** :

- Signaux fragilité / impact / faisabilité déjà calibrés en rangs percentiles **intra-région**
- Matrice `_assign_priorite(frag, impact, fais)` conservée pour la vue ARS « territoires prioritaires »
- Le nouveau moteur **généralise** cette logique au niveau **action × département**, avec des signaux spécifiques par levier

---

## 2. Inventaire des données

### 2.1 DataFrame `master` (101 départements)

Une ligne = un département. Construit par `app/data_loading.py`, enrichi par `app/scoring.py`.

#### A. Identité et géographie

| Variable | Colonne | Niveau | Rôle moteur |
|----------|---------|--------|-------------|
| Code département | `dept` | Dept | Clé primaire |
| Nom | `Nom du département` | Dept | Affichage |
| Région | `Nom de la région`, `Code région` | Dept | Jointure délais, agrégation |
| Score environnement | `enviro_score` | Région (répliqué) | Signal faible (prévention air/eau — hors Roche) |

#### B. Variables de fragilité (besoin structurel)

| Variable | Colonne | Source | Signal |
|----------|---------|--------|--------|
| APL médian | `apl_median_dept` | ANCT 2023 | Accès soins de ville ; seuil désert < 2,5 |
| Dispersion APL | `apl_p25`, `apl_p75` | ANCT | Hétérogénéité intra-dept (ciblage fin) |
| Temps d'accès médian | `temps_acces_median` | FINESS+INSEE | Isolement physique |
| Temps p90 / max | `temps_acces_p90`, `temps_acces_max` | Idem | Queue de distribution, communes extrêmes |
| Communes critiques | `nb_communes_critiques` | Idem | Communes > 15 min vers établissement |
| Nb communes | `nb_communes` | Idem | Dénominateur, dispersion |
| MG / 100k | `med_gen_pour_100k`, `nb_med_gen` | RPPS | Offre ville |
| Structures / 100k | `structures_pour_100k`, `hopitaux_pour_100k` | FINESS | Offre hospitalière |
| Scores dérivés | `score_global`, `score_acces`, `score_pros`, `score_etabs`, `score_temps`, `score_apl`, `score_medecins`, `score_seniors`, `score_foncier` | Calcul | **Signaux secondaires uniquement** — ne pas confondre avec opportunité |
| Zone | `zone_short`, `rang_national` | Calcul | Contexte, pas driver principal |
| Typologie | `typologie` | Calcul (seuils scoring) | Routage urbain/rural |

#### C. Variables d'impact (population et amplitude)

| Variable | Colonne | Source | Signal |
|----------|---------|--------|--------|
| Population | `population_num` | INSEE | Volume absolu |
| Densité | `densite` | INSEE | Typologie, faisabilité coordination |
| Part < 25 ans | `pct_moins_25` | INSEE | Enjeu pédiatrie / PMI |
| Part 25–64 | `pct_25_64` | INSEE | Actifs, prévention |
| Part 65+ | `pct_plus_65` | INSEE | Seniors, gériatrie, télésuivi |
| Volume seniors absolu | `population_num × pct_plus_65 / 100` | Dérivé | Impact chiffrable |
| Volume jeunes absolu | `population_num × pct_moins_25 / 100` | Dérivé | Impact pédiatrie |

#### D. Variables de faisabilité (relais opérationnels)

| Variable | Colonne | Source | Signal |
|----------|---------|--------|--------|
| Total pros | `nb_pros`, `pros_pour_100k` | RPPS | Masse professionnelle |
| Infirmiers | `nb_infirmiers` | RPPS | Coordination, IPA, télésuivi |
| Pharmaciens | `nb_pharmaciens` | RPPS | Proximité, prévention |
| Établissements | `nb_etabs`, `nb_hopitaux`, `nb_cliniques` | FINESS | Relais hospitaliers |
| Foncier | `prix_m2_moyen` | DVF | Attractivité installation |
| Transactions immo | `nb_transactions` | DVF | Liquidité marché (proxy confiance) |
| Surface moyenne | `surface_moy` | DVF | Contexte logement |

#### E. Colonnes master peu exploitées — à activer dans le moteur

`nb_infirmiers`, `nb_pharmaciens`, `nb_hopitaux`, `nb_cliniques`, `apl_p25`, `apl_p75`, `temps_acces_p90`, `temps_acces_max`, `nb_communes`, `nb_transactions`, `pros_pour_100k`, `hopitaux_pour_100k`, `enviro_score`.

### 2.2 Datasets annexes

#### `pros` — détail RPPS

| Colonne | Niveau | Rôle moteur |
|---------|--------|-------------|
| `dept` | Dept | Jointure |
| `specialite_libelle` | Dept (agrégable) | Déficit spécialiste par spécialité ; paradoxe RPPS/APL ; leviers téléexpertise ciblés |

**Features dérivées à pré-calculer :**

- Densité / 100k par spécialité (Cardiologue, Psychiatre, Ophtalmologue, Pédiatre, Endocrinologue, etc.)
- Écart vs médiane nationale par spécialité
- Ratio spécialistes / pathologie CNAM associée (`PATHOS_SPECIALITES_MAP` · `config.py`)
- Flag paradoxe : `med_gen_pour_100k > médiane` ET `apl_median_dept < 2,5`

#### `patho` — CNAM 2023

| Colonne | Niveau | Rôle moteur |
|---------|--------|-------------|
| `dept`, `patho_niv1`, `Ntop`, `Npop` | Dept × pathologie | Prévalence, volume patients |

**Features dérivées (par département, hors `PATHOS_EXCLUDED`) :**

| Feature | Calcul | Usage |
|---------|--------|-------|
| `prev_cardio` | prev max famille cardio | Prévention cardio, parcours |
| `prev_diabete` | prev max famille diabète | Dépistage diabète |
| `prev_psychiatrique` | prev psychiatrie | Santé mentale |
| `prev_respiratoire` | prev respiratoire | BPCO, prévention |
| `prev_cancers` | prev cancers | Dépistage, parcours oncologie |
| `prev_neurologie` | prev neurologie | Parcours neuro, télésuivi |
| `ntop_max` | max Ntop toutes pathos | Impact absolu |
| `patho_dominante` | patho_niv1 à prev max | Public cible principal |

> **Prérequis technique :** centraliser ces agrégations dans un module `feature_store.py` — corrige le bug actuel (`prev_diabete` / `prev_cardio` absents dans les reco dept).

#### `temps` — accessibilité communale

| Colonne | Niveau | Rôle moteur |
|---------|--------|-------------|
| `code_departement`, `commune`, `temps_acces` | Commune | Ciblage MSP/navettes ; part communes > 15 min ; clusters d'isolement |

#### `immo` — foncier communal

| Colonne | Niveau | Rôle moteur |
|---------|--------|-------------|
| `code_departement`, `commune`, `prix_m2` | Commune | Communes à foncier favorable pour implantation |

#### `etabs` — FINESS géolocalisé

| Colonne | Niveau | Rôle moteur |
|---------|--------|-------------|
| `code_departement`, `commune`, `Rslongue`, `categetab`, `latitude`, `longitude` | Commune | Distance aux relais ; antennes ; carte d'offre |

#### `delais` — DREES régional (`static/data/delais_rdv_drees.csv`)

| Colonne | Niveau | Rôle moteur |
|---------|--------|-------------|
| `code_region`, `specialite`, `delai_jours_median`, `delai_jours_p75` | Région × spécialité | Tension spécialiste ; téléexpertise ; consultations avancées |

Spécialités : Ophtalmologue, Dermatologue, Cardiologue, Gynécologue, Psychiatre, Généraliste, Pédiatre, ORL, Rhumatologue, Endocrinologue.

#### `delais_rdv_nationaux.csv` + proxy APL (`app/components/delais.py`)

| Usage | Niveau | Rôle moteur |
|-------|--------|-------------|
| `compute_delais_proxy(dept, apl)` | Dept (estimé) | Délais spécialistes quand pas de mesure dept ; complète `delais` régional |

#### `geojson` — contours

Maille cartographique uniquement ; pas de signal scoring.

### 2.3 Données absentes (limites explicites)

| Donnée | Impact sur le moteur |
|--------|---------------------|
| MSP / CPTS existantes | Pas de score « compléter vs créer » — supposer territoire éligible si signaux réunis |
| EHPAD / places médicalisées | Volume seniors touché = proxy démographique |
| IPA déployés | Non mesuré — inférer via infirmiers + hôpitaux |
| Télésuivi / téléexpertise en place | Non mesuré |
| Ruptures médicaments (ANSM) | `MEDIC_FILE_ID` non chargé |
| Doctolib départemental | Remplacerait le proxy APL à terme |

### 2.4 Taxonomie des variables pour le moteur

```
┌─────────────────────────────────────────────────────────────────┐
│                    FEATURE STORE TERRITORIAL                     │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│  FRAGILITÉ   │    IMPACT    │ FAISABILITÉ  │  POPULATION CIBLE │
│  (besoin)    │  (amplitude) │  (relais)    │  (qui)            │
├──────────────┼──────────────┼──────────────┼───────────────────┤
│ APL, temps   │ population   │ hôpitaux     │ pct_65+, Ntop     │
│ communes crit│ seniors abs  │ infirmiers   │ patho dominante   │
│ scores accès │ prev patho   │ pharmaciens  │ pct_moins_25      │
│ déficit MG   │ nb communes  │ foncier      │ communes isolées  │
│ délais spé   │ écart RPPS   │ densité      │ paradoxe RPPS     │
└──────────────┴──────────────┴──────────────┴───────────────────┘
```

---

## 3. Score d'opportunité d'action

### 3.1 Définition

Pour chaque couple **(territoire T, action A)** :

```
score_opportunite(A, T) = f( score_besoin(A,T), score_impact(A,T), score_faisabilite(A,T) )
```

avec **garde d'éligibilité** :

```
si non eligible(A, T) → score_opportunite = 0  (action exclue du classement)
```

### 3.2 Score besoin `score_besoin` (0–100)

Mesure l'intensité du problème **que cette action adresse** (pas la fragilité globale).

**Méthode générique :**

1. Définir 2 à 5 **signaux d'action** spécifiques (colonnes ou features dérivées)
2. Convertir chaque signal en rang percentile **contextuel** :
   - National par défaut
   - Intra-régional pour pilotage ARS (option `scope="region"`)
3. Orienter le rang : `higher_is_worse=True/False` selon le signal
4. Agréger par **moyenne pondérée** des signaux (poids dans la fiche action)

**Exemple — action MSP :**

| Signal | Variable | Poids | Sens |
|--------|----------|-------|------|
| Désert médical | `2.5 − apl_median_dept` (clamp) | 0,35 | Plus APL bas → plus besoin |
| Isolement | `nb_communes_critiques / nb_communes` | 0,25 | Plus communes éloignées → plus besoin |
| Ruralité | typologie ∈ {rural, peri_urbain} | 0,20 | Boolean → 100/0 |
| Temps d'accès | `temps_acces_median` | 0,20 | Plus temps élevé → plus besoin |

**Différence clé avec score santé :** une action urbaine (téléexpertise) aura un `score_besoin` élevé quand `typologie = urbain` ET `apl` bas ET délais spécialistes élevés — même si le département a un `score_global` intermédiaire.

### 3.3 Score impact `score_impact` (0–100)

Mesure **combien de personnes** peuvent bénéficier de l'action et **à quelle intensité**.

**Formule générique :**

```
score_impact = normalize( Σ w_i × signal_population_i )
```

| Signal impact | Calcul | Actions typiques |
|---------------|--------|------------------|
| Population totale | rang(`population_num`) | Toutes |
| Volume seniors | rang(`pop × pct_65/100`) | Gériatrie, télésuivi seniors |
| Volume jeunes | rang(`pop × pct_moins_25/100`) | PMI, pédiatrie |
| Patients pathologie X | rang(`Ntop` filtré patho) | Prévention ciblée |
| Prévalence pathologie X | rang(`prev` patho) | Dépistage |
| Communes isolées | rang(`nb_communes_critiques`) | Navettes, MSP |
| Amplitude désert | rang(`max(0, 2.9 − apl) × population`) | Recrutement MG |

**Normalisation :** rang percentile 0–100, scope national ou régional selon usage.

### 3.4 Score faisabilité `score_faisabilite` (0–100)

Mesure la probabilité de **déployer** l'action avec les relais existants.

Reprise et extension de `compute_dept_priorities` · `_fais_score` :

| Signal | Variable | Sens pour faisabilité |
|--------|----------|----------------------|
| Relais hospitaliers | `nb_hopitaux + nb_cliniques` | ↑ = mieux |
| Soignants de proximité | `nb_infirmiers + nb_pharmaciens` | ↑ = mieux |
| Offre établissements | `structures_pour_100k` | ↑ = mieux (sauf actions « combler absence ») |
| Temps d'accès | `temps_acces_median` | ↓ = mieux (sauf navettes où signal besoin) |
| Foncier | `prix_m2_moyen` | ↓ = mieux (installation) |
| Densité proche médiane | `_densite_faisabilite_score` | Pic autour médiane régionale |

**Par action :** sous-ensemble de signaux + éventuellement **inversion** (ex. navettes : faisabilité politique/infra faible en zone très isolée → pénalité).

### 3.5 Score opportunité global

**Formule recommandée (v1) — moyenne géométrique pondérée :**

```
score_opportunite = ( score_besoin^α × score_impact^β × score_faisabilite^γ )^(1/(α+β+γ))
```

**Poids par défaut :** α = 0,45 (besoin), β = 0,35 (impact), γ = 0,20 (faisabilité).

> La moyenne géométrique **pénalise** les actions fortes sur un pilier mais nulles sur un autre (ex. besoin élevé mais zero faisabilité).

**Alternative (v1 simplifiée) — moyenne arithmétique :**

```
score_opportunite = 0,45 × score_besoin + 0,35 × score_impact + 0,20 × score_faisabilite
```

**Seuil d'affichage :** ne proposer une action que si `score_opportunite ≥ 40` ET `score_besoin ≥ 30`.

### 3.6 Comparabilité inter-actions

Les scores sont **comparables entre actions pour un même territoire** (classement des leviers) et **entre territoires pour une même action** (pilotage ARS).

Pour éviter qu'une action « généraliste » (conditions larges) domine toujours :

- Appliquer un **plafond** au nombre d'actions affichées (4 dept, 3–8 région)
- Introduire une **pénalité de redondance** : si deux actions partagent > 70 % de signaux, ne garder que la meilleure

---

## 4. Bibliothèque d'actions

### 4.1 Catalogue consolidé (existant + extensions data-driven)

Actions regroupées en **8 familles** alignées Fondation Roche / ARS.

#### Famille 1 — Coordination territoriale et accès de proximité

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `msp` | Maison de santé pluridisciplinaire | Reco dept #1 | Existant |
| `consultations_avancees_proximite` | Consultations avancées (IPA, permanences) | Reco dept #2 (partiel), levier région | Existant |
| `antennes_externes` | Antennes de consultations externes hospitalières | Reco dept #5 | Existant |
| `navettes_sante` | Navettes / transport sanitaire partagé | Reco dept #6, levier région | Existant |
| `cpts_coordination` | Coordination CPTS / parcours ville-hôpital | Levier région | Existant (texte) |
| `permanences_municipales` | Permanences de soins en mairie / centres | **Nouveau** — `temps` communal, `nb_communes_critiques` | Extension |

#### Famille 2 — Numérique en santé

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `teleexpertise` | Téléexpertise spécialisée | Reco dept #2, levier région | Existant |
| `teleconsultation_assistee` | Téléconsultation assistée | Levier région | Existant |
| `telesuivi_chroniques` | Télésuivi patients chroniques | Levier région | Existant |
| `telesuivi_seniors` | Télésuivi / santé numérique seniors | Reco dept #4, levier région | Existant |
| `telemedecine_urbaine` | Télémédecine urbaine (saturation MG) | Reco dept #2 | Existant (fusionnable avec téléexpertise) |

#### Famille 3 — Prévention et dépistage

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `prevention_cardio` | Prévention / dépistage cardiovasculaire | Reco dept #7, levier région | Existant |
| `depistage_diabete` | Dépistage diabète | Levier région | Existant |
| `prevention_sante_mentale` | Prévention santé mentale | Levier région | Existant |
| `prevention_respiratoire` | Prévention BPCO / respiratoire | Levier région | Existant |
| `prevention_fragilite_seniors` | Prévention fragilité seniors | Levier région | Existant |
| `depistage_cancers` | Dépistage cancers (sein, colorectal) | **Nouveau** — `patho` cancers + `pct_25_64` | Extension |
| `prevention_pediatrique` | Renforcement PMI / prévention jeunes | Reco dept #8 | Existant |

#### Famille 4 — Parcours de soins

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `parcours_ville_hopital` | Parcours ville-hôpital coordonné | Levier région | Existant |
| `parcours_chroniques` | Parcours maladies chroniques | Levier région | Existant |
| `parcours_geriatrique` | Parcours gériatrique intégré | Levier région | Existant |
| `parcours_cardio` | Parcours cardiovasculaire coordonné | **Nouveau** — `prev_cardio` + délai Cardiologue | Extension |
| `parcours_psy` | Parcours santé mentale | **Nouveau** — `prev_psychiatrique` + délai Psychiatre | Extension |

#### Famille 5 — Attractivité et installation

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `attractivite_mg` | Programme attractivité / recrutement MG | Reco dept #3 | Existant |
| `levier_foncier` | Levier foncier / bail emphytéotique | Reco dept #9 | Existant |
| `contrats_ territoriaux` | Contrats de praticien territorial | **Nouveau** — désert + faisabilité moyenne | Extension |

#### Famille 6 — Offre spécialisée

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `consultations_avancees_specialistes` | Consultations avancées spécialistes (IPA) | Docstring dept #10 **non codé** | À implémenter |
| `teleexpertise_ophtalmo` | Téléexpertise ophtalmologie | **Nouveau** — délai Ophtalmologue + déficit RPPS | Extension |
| `teleexpertise_dermato` | Téléexpertise dermatologie | **Nouveau** — idem | Extension |
| `renfort_pediatrie` | Renforcement offre pédiatrique | Reco dept #8 | Existant |

#### Famille 7 — Pilotage et veille

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `plan_vigilance` | Plan de vigilance indicateurs | Reco dept #10 | Existant |
| `maintien_acquis` | Maintien / benchmarking | Reco dept #11 | Existant |
| `veille_trimestrielle` | Veille APL / RPPS / temps | **Nouveau** — zone intermédiaire | Extension |

#### Famille 8 — Régional / ARS (agrégation)

| ID | Action | Source actuelle | Statut |
|----|--------|-----------------|--------|
| `plan_regional_acces` | Plan régional accès de ville | Synthèse région | Agrégation |
| `experimentation_territoire` | Expérimentation sur candidats | `candidat expérimentation` | Lien priorisation |

**Total : 32 actions** (22 existantes consolidées + 10 extensions data-driven).

### 4.2 Actions exclues du scoring (hors périmètre v1)

- « Ajouter des médecins » sans levier structurel → remplacé par `attractivite_mg` + `msp` + `levier_foncier`
- Recommandations région « politiques » non conditionnées (`render_reco_ars` legacy) → remplacées par agrégation du moteur

---

## 5. Fiche type par action

Chaque action est définie par un objet **ActionDefinition** (futur code) :

```python
@dataclass
class ActionDefinition:
    id: str
    famille: str
    label: str
    publics: list[str]           # ex. ["Seniors", "Patients chroniques"]
    signaux_besoin: list[Signal] # variable, poids, higher_is_worse, transform
    signaux_impact: list[Signal]
    signaux_faisabilite: list[Signal]
    eligibility: EligibilityRule # conditions minimales (AND/OR)
    exclusions: list[str]        # ids actions incompatibles
    horizon_mois: tuple[int,int] # fourchette déploiement (affichage phase 2)
    indicateurs_impact: list[str] # métriques suivi post-action
```

### 5.1 Fiches détaillées — actions prioritaires (top 12)

---

#### `msp` — Maison de santé pluridisciplinaire

| Dimension | Détail |
|-----------|--------|
| **Publics** | Habitants zones rurales/péri-urbaines, patients sans MG de proximité |
| **Éligibilité** | `apl_median_dept < 2.5` ET `typologie ∈ {rural, peri_urbain}` |
| **Signaux besoin** | APL (0,35), part communes critiques (0,25), temps médian (0,20), déficit MG (0,20) |
| **Signaux impact** | Population dept (0,30), nb communes critiques (0,35), amplitude désert × pop (0,35) |
| **Signaux faisabilité** | Foncier bas (0,30), présence hôpital ≤ 50 km proxy (0,25), infirmiers/100k (0,25), densité (0,20) |
| **Exclusions** | `telemedecine_urbaine` |
| **Horizon** | 18–36 mois |
| **Indicateurs impact futurs** | Évolution APL, nb installations MG, temps d'accès communes ciblées |

---

#### `teleexpertise` — Téléexpertise spécialisée

| Dimension | Détail |
|-----------|--------|
| **Publics** | Patients en attente spécialiste, MG en zone sous-dotée |
| **Éligibilité** | (`apl < 2.5` OU `delai_regional_max ≥ 60 j`) ET déficit ≥ 1 spécialité tension |
| **Signaux besoin** | Délai spécialiste régional (0,30), APL inverse (0,25), paradoxe RPPS/APL (0,25), temps accès (0,20) |
| **Signaux impact** | Population (0,40), volume patho dominante liée spécialité (0,35), communes isolées (0,25) |
| **Signaux faisabilité** | Présence hôpital (0,35), infirmiers (0,30), couverture numérique proxy densité (0,35) |
| **Exclusions** | — |
| **Horizon** | 6–18 mois |
| **Indicateurs impact** | Délai RDV estimé, taux recours téléexpertise (future donnée) |

---

#### `attractivite_mg` — Attractivité / recrutement MG

| Dimension | Détail |
|-----------|--------|
| **Publics** | Population sans accès MG suffisant |
| **Éligibilité** | `med_gen_pour_100k < 0.85 × médiane_nationale` OU (`apl < 2.5` ET déficit MG) |
| **Signaux besoin** | Écart MG/100k vs médiane (0,40), APL (0,35), score_pros inverse (0,25) |
| **Signaux impact** | Population (0,50), amplitude désert × pop (0,50) |
| **Signaux faisabilité** | Foncier (0,40), densité (0,30), présence faculté proxy région (0,30 — future) |
| **Horizon** | 24–48 mois |
| **Indicateurs impact** | MG/100k, APL, nb installations |

---

#### `telesuivi_seniors` — Télésuivi seniors

| Dimension | Détail |
|-----------|--------|
| **Publics** | Personnes ≥ 65 ans, perte d'autonomie, isolement |
| **Éligibilité** | `pct_plus_65 > 22` ET (`score_acces < 45` OU `apl < 2.5` OU `temps > 12`) |
| **Signaux besoin** | Part 65+ (0,35), accès dégradé (0,35), communes critiques (0,30) |
| **Signaux impact** | Volume seniors absolu (0,60), population (0,40) |
| **Signaux faisabilité** | Infirmiers/100k (0,40), hôpitaux (0,30), EHPAD proxy densité seniors (0,30) |
| **Horizon** | 6–12 mois |
| **Indicateurs impact** | Nombre seniors équipés (future), renoncement soins |

---

#### `navettes_sante` — Navettes santé

| Dimension | Détail |
|-----------|--------|
| **Publics** | Personnes sans véhicule, seniors, précarité transport |
| **Éligibilité** | `typologie ∈ {rural, peri_urbain}` ET `temps_acces_median > 1.4 × médiane_nationale` ET `score_etabs ≥ 33` |
| **Signaux besoin** | Temps accès (0,40), communes critiques (0,35), temps p90 (0,25) |
| **Signaux impact** | Pop communes > 15 min (0,50), population rurale proxy (0,50) |
| **Signaux faisabilité** | Présence hôpital référent (0,50), densité faible (0,30), structures/100k (0,20) |
| **Horizon** | 6–12 mois |
| **Indicateurs impact** | Communes desservies, temps moyen trajet |

---

#### `prevention_cardio` — Prévention cardiovasculaire

| Dimension | Détail |
|-----------|--------|
| **Publics** | Adultes à risque CV, patients hypertendus/diabétiques |
| **Éligibilité** | `prev_cardio ≥ P60` national OU `ntop_cardio ≥ P60` ET accès dégradé optionnel |
| **Signaux besoin** | Prévalence cardio (0,45), score_acces inverse (0,30), part 65+ (0,25) |
| **Signaux impact** | Ntop cardio (0,55), population 45–64 (0,45) |
| **Signaux faisabilité** | Pharmaciens/100k (0,35), infirmiers (0,35), MG/100k (0,30) |
| **Horizon** | 6–18 mois |
| **Indicateurs impact** | Prévalence, hospitalisations CV (future) |

---

#### `depistage_diabete` — Dépistage diabète

| Dimension | Détail |
|-----------|--------|
| **Publics** | Population à risque diabète de type 2 |
| **Éligibilité** | `prev_diabete ≥ P50` national |
| **Signaux besoin** | Prévalence diabète (0,50), APL inverse (0,25), score_acces (0,25) |
| **Signaux impact** | Ntop diabète (0,60), population 25–64 (0,40) |
| **Signaux faisabilite** | Pharmaciens (0,40), MG (0,35), structures (0,25) |
| **Horizon** | 6–12 mois |

---

#### `prevention_sante_mentale` — Prévention santé mentale

| Dimension | Détail |
|-----------|--------|
| **Publics** | Publics en souffrance psychique, jeunes, précarité |
| **Éligibilité** | `prev_psychiatrique ≥ P50` ET `score_acces < 50` |
| **Signaux besoin** | Prévalence psy (0,40), délai Psychiatre régional (0,35), accès (0,25) |
| **Signaux impact** | Ntop psy (0,65), population 15–25 proxy (0,35) |
| **Signaux faisabilité** | Psychiatres/100k vs médiane (0,45), hôpitaux (0,30), infirmiers (0,25) |

---

#### `consultations_avancees_specialistes` — IPA / consultations avancées spécialistes

| Dimension | Détail |
|-----------|--------|
| **Publics** | Patients en attente spécialiste, filières MG saturées |
| **Éligibilité** | Déficit RPPS ≥ 1 spécialité liée patho top 3 dept ET (`apl < 2.5` OU délai > P75 régional) |
| **Signaux besoin** | Déficit spécialiste max (0,35), délai spécialiste (0,30), APL (0,20), paradoxe RPPS (0,15) |
| **Signaux impact** | Ntop patho liée (0,50), population (0,50) |
| **Signaux faisabilité** | Infirmiers/100k (0,45), hôpitaux (0,35), densité (0,20) |
| **Horizon** | 12–24 mois |

---

#### `antennes_externes` — Antennes consultations externes

| Dimension | Détail |
|-----------|--------|
| **Éligibilité** | `score_etabs < 33` |
| **Signaux besoin** | Structures/100k (0,45), temps accès (0,35), communes critiques (0,20) |
| **Signaux impact** | Population éloignée hôpitaux (0,55), communes critiques (0,45) |
| **Signaux faisabilité** | Présence ≥ 1 hôpital référent dept ou voisin (0,60), foncier (0,40) |

---

#### `levier_foncier` — Attractivité via foncier

| Dimension | Détail |
|-----------|--------|
| **Éligibilité** | `prix_m2_moyen < P25` national ET `apl < 2.5` |
| **Signaux besoin** | APL (0,50), prix/m² inverse (0,30), déficit MG (0,20) |
| **Signaux impact** | Population désert (0,60), communes isolées (0,40) |
| **Signaux faisabilité** | Liquidité immo `nb_transactions` (0,40), dispersion APL (0,30), densité (0,30) |
| **Exclusions** | Redondant si `attractivite_mg` score > 80 → garder le max |

---

#### `plan_vigilance` / `maintien_acquis` — Pilotage

| Dimension | Détail |
|-----------|--------|
| **Éligibilité vigilance** | Aucune action autre ≥ 40 ET `33 ≤ score_global ≤ 55` |
| **Éligibilité maintien** | Aucune action autre ≥ 40 ET `score_global > 55` |
| **Score** | Fixe bas (30–45) — toujours dernière priorité |
| **Rôle** | Fallback explicite, pas compétition avec actions structurelles |

---

### 5.2 Matrice action × typologie (routage)

| Typologie | Actions prioritaires naturelles |
|-----------|-------------------------------|
| `rural` | MSP, navettes, télésuivi seniors, attractivité MG |
| `peri_urbain` | MSP, consultations avancées, navettes, prévention |
| `urbain` | Téléexpertise, téléconsultation, consultations avancées spécialistes |
| `urbain_dense` | Téléexpertise, parcours spécialistes, prévention ciblée |

---

## 6. Modèle de scoring commun

### 6.1 Pipeline de calcul

```
┌──────────────┐    ┌─────────────────┐    ┌──────────────────┐
│ load_all_data│───▶│ build_features  │───▶│ TerritoryProfile │
│ + patho agg  │    │ (dept + region) │    │  per dept        │
└──────────────┘    └─────────────────┘    └────────┬─────────┘
                                                    │
                    ┌───────────────────────────────┘
                    ▼
         ┌──────────────────────┐
         │ ACTION_REGISTRY (32) │
         └──────────┬───────────┘
                    │ for each (dept, action)
                    ▼
         ┌──────────────────────┐
         │ check_eligibility    │─── non ──▶ score = 0, skip
         └──────────┬───────────┘
                    │ oui
                    ▼
         ┌──────────────────────┐
         │ compute_besoin       │──▶ score_besoin  (0-100)
         │ compute_impact       │──▶ score_impact  (0-100)
         │ compute_faisabilite  │──▶ score_faisabilite (0-100)
         └──────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │ score_opportunite    │
         └──────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │ rank_actions(dept)   │──▶ top N, dedupe
         │ rank_territories(act)│──▶ pour ARS
         └──────────────────────┘
```

### 6.2 Fonctions utilitaires communes

Reprise de `region_pilotage.py` :

| Fonction | Usage |
|----------|-------|
| `_signal_rank(series, higher_is_worse)` | Normalisation percentile |
| `_composite_score(signals_dict)` | Moyenne signaux alignés |
| `_score_to_level(score, labels)` | Quartiles → libellés |
| `_patho_metrics(patho, dept_codes)` | Features patho dept |

**Nouvelles fonctions :**

| Fonction | Rôle |
|----------|------|
| `build_territory_features(master, pros, patho, delais, scope)` | Feature store par dept |
| `compute_action_scores(profile, action_def)` | Triplet besoin/impact/faisabilité |
| `rank_department_actions(dept, registry, top_n=4)` | Remplace `_generate_recommendations` |
| `rank_region_levers(region_depts, registry, top_n=8)` | Remplace `compute_leviers_action` |
| `explain_action_score(result)` | Top 3 signaux contributeurs (phase 2 UI) |

### 6.3 Sortie standard — `ActionScoreResult`

```python
@dataclass
class ActionScoreResult:
    action_id: str
    dept: str
    score_besoin: float
    score_impact: float
    score_faisabilite: float
    score_opportunite: float
    eligible: bool
    publics: list[str]
    population_touchée_estimee: int | None  # phase 2
    signaux_contributeurs: list[dict]         # explicabilité
    horizon_mois: tuple[int, int]
    famille: str
    label: str
```

### 6.4 Règles de classement final

**Fiche département (top 4) :**

1. Filtrer `eligible` ET `score_opportunite ≥ 40`
2. Trier par `score_opportunite` décroissant
3. Dédupliquer familles redondantes (garder max score par famille si > 1)
4. Si < 1 action : fallback `plan_vigilance` ou `maintien_acquis`
5. Badge priorité = **rang** 1–4 post-tri (cohérent si score explicite)

**Fiche région (top 3–8 leviers) :**

1. Calculer scores pour tous dept × actions éligibles
2. Agréger par action : `score_regional = moyenne_pondérée(score_opportunite × population)`
3. Lister départements contributeurs (top 4 par score action)
4. Trier actions par `score_regional`
5. Conserver lien avec `compute_dept_priorities` pour bloc « Où agir »

### 6.5 Calibrage et validation

| Étape | Méthode |
|-------|---------|
| Seuils éligibilité | Reprendre seuils actuels (APL 2,5, scores 33/45, pct 22 %, etc.) |
| Poids signaux | Initialiser depuis poids `region_pilotage` + doc reco dept |
| Validation expert | 10 départements témoins (rural, urbain, DOM, favorable) — comparer ranking moteur vs intuition ARS |
| Régression | Le moteur doit retrouver ≥ 80 % des actions actuellement déclenchées sur échantillon |

---

## 7. Architecture logicielle cible

### 7.1 Structure de fichiers proposée

```
app/
  action_engine/
    __init__.py
    features.py          # build_territory_features, patho aggregations
    registry.py          # ACTION_REGISTRY — 32 ActionDefinition
    scoring.py           # compute_action_scores, score_opportunite
    ranking.py           # rank_department_actions, rank_region_levers
    explain.py           # signaux contributeurs, textes
    types.py             # dataclasses ActionDefinition, ActionScoreResult
  region_pilotage.py     # conservé — territoires prioritaires ARS
  scoring.py             # INCHANGÉ — score santé
```

### 7.2 Dépendances

| Module | Lit | Écrit |
|--------|-----|-------|
| `action_engine` | master, pros, patho, delais, temps (optionnel) | Colonnes **nouvelles** optionnelles `action_*` cache |
| `fiche_departement` | `rank_department_actions` | Remplace `_generate_recommendations` (phase 2) |
| `fiche_region` | `rank_region_levers` + `compute_dept_priorities` | Remplace `compute_leviers_action` (phase 2) |
| `scoring.py` | — | **Aucune modification** |

### 7.3 Cache et performance

- `@st.cache_data` sur `build_territory_features()` et `rank_department_actions(dept)`
- Feature store : ~101 lignes × ~40 features — négligeable
- Calcul complet : 101 dept × 32 actions ≈ 3 200 scores — < 100 ms en Python pur

---

## 8. Phase suivante — indicateurs d'impact affichables

Sans prédiction ML. Indicateurs **estimés** à partir des données actuelles.

### 8.1 Population potentiellement touchée

| Action type | Formule estimée | Données |
|-------------|-----------------|---------|
| Seniors | `int(population × pct_65 / 100 × taux_cible)` | `taux_cible` default 0,3–0,5 selon action |
| Pathologie X | `int(Ntop × part_dept_concernée)` | `patho` |
| Désert médical | `int(population × max(0, 1 − apl/2.9))` | APL |
| Communes isolées | `sum pop communes où temps > 15` | `temps` + pop commune (future) |
| Général | `int(population × score_impact / 100 × 0.2)` | Plafond prudent 20 % pop |

**Affichage :** fourchette `[min, max]` + mention « estimation indicative ».

### 8.2 Publics concernés

Dérivés directement de `ActionDefinition.publics` + patho dominante dept :

- Libellé court (Seniors, Patients chroniques, Familles, etc.)
- Lien patho CNAM si applicable

### 8.3 Horizon temporel

| Classe | Mois | Actions |
|--------|------|---------|
| Rapide | 6–12 | Télésuivi, navettes, dépistage |
| Moyen | 12–24 | Téléexpertise, prévention, IPA |
| Long | 24–48 | MSP, attractivité MG, antennes |

Stocké dans `ActionDefinition.horizon_mois`.

### 8.4 Impact potentiel attendu (qualitatif + proxy quantitatif)

**Échelle qualitative :**

| Niveau | Condition proxy |
|--------|-----------------|
| Faible | score_impact < 40 |
| Modéré | 40–65 |
| Élevé | 65–80 |
| Majeur | > 80 |

**Proxies quantitatifs (v2) :**

| Métrique proxy | Calcul |
|----------------|--------|
| Gain APL potentiel | `min(0.3, (2.9 − apl) × 0.1)` × population |
| Communes reconnectées | `min(nb_communes_critiques, cible_msp)` |
| Patients dépistables | `Ntop × 0.05` (5 % prévalence cible annuelle) |
| Réduction délai estimée | `delai_actuel × 0.15` si téléexpertise (hypothèse 15 %) |

> **Garde-fou :** toujours afficher « impact estimé — scénario, non mesure d'effet ».

### 8.5 Préparation prédiction (hors scope v1, architecture ready)

| Future donnée | Usage |
|---------------|-------|
| Séries temporelles APL / RPPS | Tendance besoin |
| Doctolib départemental | Délais réels vs proxy |
| Fichage expérimentations | Boucle feedback score faisabilité |
| EHPAD / HAD | Affinement publics seniors |

Prévoir champ `confidence: float` dans `ActionScoreResult` (0–1) selon complétude des signaux.

---

## 9. Migration depuis l'existant

### 9.1 Mapping reco département → moteur

| Reco actuelle | Action ID | Changement principal |
|---------------|-----------|----------------------|
| MSP | `msp` | Score vs priorité fixe 1 |
| Télémédecine urbaine | `telemedecine_urbaine` / `teleexpertise` | Fusion possible |
| Attractivité MG | `attractivite_mg` | Score impact chiffré |
| Seniors numériques | `telesuivi_seniors` | Idem |
| Antennes | `antennes_externes` | Idem |
| Navettes | `navettes_sante` | Idem |
| Prévention chroniques | `prevention_cardio` (+ autres) | Fix patho features |
| Pédiatrie | `prevention_pediatrique` | Idem |
| Foncier | `levier_foncier` | Idem |
| Vigilance / Maintien | `plan_vigilance` / `maintien_acquis` | Fallback explicite |

### 9.2 Mapping leviers région → moteur

| Levier actuel | Action ID | Changement |
|---------------|-----------|------------|
| Prévention cardio | `prevention_cardio` | Score dynamique vs 0,75 fixe |
| Dépistage diabète | `depistage_diabete` | Seuil prévalence requis |
| Téléexpertise | `teleexpertise` | Score vs 0,80 fixe si désert |
| Parcours ville-hôpital | `parcours_ville_hopital` | Lié faisabilité réelle |
| … | … | … |

### 9.3 Ce qui ne change pas (phase 1)

- `app/scoring.py` — score santé v2
- UI toutes pages
- `compute_dept_priorities` — bloc « Où agir » région
- Textes prose reco — régénérés en phase 2 depuis `explain.py`

---

## 10. Limites, risques et garde-fous

| Risque | Mitigation |
|--------|------------|
| Confusion score santé / opportunité | Nommage strict `score_opportunite_*` ; jamais afficher comme « score global » |
| Sur-promesse impact population | Fourchettes + disclaimer ; plafonds conservateurs |
| Actions toujours identiques | Seuils éligibilité stricts ; pénalité redondance ; diversité familles |
| Proxy délais APL imprécis | Pondération moindre si `delais` régional absent ; `confidence` basse |
| Deux typologies densité | **Unifier** sur `scoring.typologie` dans le moteur |
| RPPS ≠ APL | Flag paradoxe explicite dans signaux |
| Données MSP/EHPAD absentes | Mentionner « éligibilité théorique » dans explicabilité |

### 10.1 Principes de communication (phase 2 UI)

- Dire **« opportunité d'action estimée »**, pas « priorité absolue »
- Afficher les **3 signaux principaux** qui expliquent le score
- Distinguer ** territoires fragiles** (score santé) vs ** territoires actionnables** (opportunité)

---

## 11. Plan de mise en œuvre

### Phase 0 — Design (ce document) ✅

- Inventaire données
- Bibliothèque actions
- Modèle scoring
- Architecture cible

### Phase 1 — Moteur de calcul (prochain sprint code)

1. `features.py` — agrégations patho, pros, delais ; unification typologie
2. `registry.py` — 12 actions prioritaires (top usage)
3. `scoring.py` + `ranking.py` — pipeline complet
4. Tests unitaires : 10 départements témoins, non-régression vs recos actuelles
5. **Aucun changement UI**

### Phase 2 — Branchement UI

1. Remplacer `_generate_recommendations` par `rank_department_actions`
2. Remplacer `compute_leviers_action` par `rank_region_levers`
3. Badges priorité = rang sur `score_opportunite`
4. Blocs population touchée / horizon / impact

### Phase 3 — Enrichissement

1. 32 actions complètes
2. Maille communale (MSP, navettes)
3. Module `explain.py` — prose dynamique
4. Export PDF aligné

### Phase 4 — Données et prédiction

1. Intégration Doctolib / séries temporelles
2. Feedback expérimentations
3. Affinement poids par calibration ARS

---

## Références

| Document / module | Lien |
|-------------------|------|
| État des lieux données | [ETAT_DES_LIEUX_DONNEES.md](./ETAT_DES_LIEUX_DONNEES.md) |
| Priorisation régionale actuelle | `app/region_pilotage.py` |
| Recos département actuelles | `app/pages/fiche_departement.py` → `_generate_recommendations` |
| Score santé (inchangé) | `app/scoring.py` |
| Chargement données | `app/data_loading.py` |

---

*Document produit pour le grand chantier Sant'active — moteur de priorisation d'actions territoriales · ESData / ESD Paris, juin 2026.*
