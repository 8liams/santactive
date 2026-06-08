# Sant'active — Guide technique

> Observatoire santé territorial · Outil d'aide à la décision pour ARS, préfectures et élus locaux.

Ce document décrit l'architecture, le flux de données, le scoring et le fonctionnement de l'application Streamlit **Sant'active**.

> **Complément :** pour l'inventaire détaillé des colonnes, scores, recommandations, lacunes et pistes d'indices ARS/Roche, voir [ETAT_DES_LIEUX_DONNEES.md](./ETAT_DES_LIEUX_DONNEES.md).

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture du projet](#2-architecture-du-projet)
3. [Cycle de vie au démarrage](#3-cycle-de-vie-au-démarrage)
4. [Récupération des données](#4-récupération-des-données)
5. [Construction du DataFrame master](#5-construction-du-dataframe-master)
6. [Score Sant'active v2](#6-score-santactive-v2)
7. [Navigation et routing](#7-navigation-et-routing)
8. [Pages de l'application](#8-pages-de-lapplication)
9. [Composants réutilisables](#9-composants-réutilisables)
10. [Export PDF](#10-export-pdf)
11. [Parcours utilisateur](#11-parcours-utilisateur)
12. [Installation et lancement](#12-installation-et-lancement)
13. [Mise à jour des données](#13-mise-à-jour-des-données)
14. [Points clés à retenir](#14-points-clés-à-retenir)

---

## 1. Vue d'ensemble

**Sant'active** est une application **Streamlit** qui croise des données officielles françaises pour produire un diagnostic par territoire, principalement à la **maille département** (101 départements), avec des vues complémentaires à la maille **région** et **commune**.

### Objectif

Identifier les zones où l'accès aux soins est difficile, comprendre les causes (démographie, offre médicale, foncier, pathologies…) et comparer des territoires entre eux.

### Sources de données

| Dataset | Source | Millésime | Maille |
|---------|--------|-----------|--------|
| Population & âge | INSEE | 2021 | Département |
| Professionnels de santé | RPPS | 2026 | Département (+ détail spécialités) |
| Établissements de soin | FINESS | 2026 | Commune (agrégé dept) |
| Temps d'accès | Calcul interne FINESS + INSEE | — | Commune (agrégé dept) |
| Prix immobilier | DVF (médiane) | 2025 | Commune (agrégé dept) |
| APL (accessibilité soins) | ANCT | 2023 | Département |
| Pathologies | CNAM | 2023 | Département |
| Score environnemental | SPF / DREAL | — | Région |
| Délais RDV | DREES | 2016–2017 | Région (+ estimation dept) |

---

## 2. Architecture du projet

```
dashboard_dat/
├── streamlit_app.py              # Point d'entrée — orchestrateur principal
├── requirements.txt
├── README.md
├── docs/
│   └── GUIDE_TECHNIQUE.md        # Ce document
├── static/
│   ├── style.css                 # Styles DSFR-inspired
│   ├── brand/                    # Logos Sant'active
│   └── data/
│       ├── apl_2023.csv          # APL ANCT (snapshot local)
│       ├── delais_rdv_drees.csv  # Délais RDV par région/spécialité
│       └── delais_rdv_nationaux.csv  # Délais médians nationaux
└── app/
    ├── config.py                 # IDs Drive, constantes, palette
    ├── data_loading.py           # Chargement + construction du master
    ├── scoring.py                # Calcul des scores v2
    ├── router.py                 # Navigation SPA + permaliens URL
    ├── search.py                 # Recherche fuzzy territoires
    ├── pdf_export.py             # Export rapport PDF (ReportLab)
    ├── pages/
    │   ├── home.py               # Accueil — carte + recherche + KPIs
    │   ├── fiche_departement.py  # Fiche complète d'un département
    │   ├── fiche_region.py       # Vue agrégée régionale
    │   ├── fiche_commune.py      # Vue resserrée communale
    │   ├── comparer.py           # Comparaison 2–4 départements
    │   ├── enjeux.py             # À quoi ça sert
    │   ├── methodologie.py       # Méthodologie du score
    │   └── about.py              # À propos / crédits
    └── components/
        ├── maps.py               # Cartes Folium/Leaflet
        ├── delais.py             # Estimation délais RDV par dept
        ├── kpi_card.py           # Cartes KPI
        ├── badges.py             # Badges de zone
        ├── alerts.py             # Alertes contextuelles
        └── tooltip.py            # Info-bulles méthodologiques
```

### Rôle des modules principaux

| Module | Responsabilité |
|--------|----------------|
| `streamlit_app.py` | Config page, CSS, sidebar, chargement données, dispatch vers les pages |
| `app/config.py` | Identifiants Google Drive, URLs, pondérations, palette couleurs |
| `app/data_loading.py` | Téléchargement CSV + agrégation en DataFrame `master` |
| `app/scoring.py` | Score Sant'active v2 sur 6 dimensions |
| `app/router.py` | Navigation entre vues + synchronisation URL |
| `app/search.py` | Recherche fuzzy régions / départements / communes |

---

## 3. Cycle de vie au démarrage

Au lancement de `streamlit run streamlit_app.py`, l'orchestrateur exécute les étapes suivantes **dans l'ordre** :

1. **Configuration Streamlit** — titre, favicon, layout wide, sidebar forcée visible
2. **Chargement CSS** — `static/style.css` avec polices Marianne inline en base64
3. **Chargement des données** — `load_all_data()` (mis en cache via `@st.cache_data`)
4. **Calcul des scores** — `compute_scores(master)` sur les 101 départements
5. **GeoJSON** — contours des départements pour la carte
6. **Routing URL** — `init_from_url()` lit les query params (`?view=dept&dept_code=02`)
7. **Sidebar** — navigation + recherche rapide
8. **Affichage** — rendu de la page correspondant à `view`
9. **Nav mobile** — barre de navigation en bas sur petit écran

### Dictionnaire `data` partagé

Toutes les pages reçoivent un dictionnaire commun :

```python
data = {
    "master":  master,   # 1 ligne = 1 département, toutes les métriques + scores
    "pros":    pros,     # Détail RPPS (spécialités par département)
    "immo":    immo,     # Prix/m² par commune
    "etabs":   etabs,    # Établissements FINESS avec coordonnées
    "temps":   temps,    # Temps d'accès par commune
    "env":     env,      # Score environnemental régional
    "patho":   patho,    # Pathologies CNAM
    "delais":  delais,   # Délais RDV DREES par région
    "geojson": geojson,  # Contours GeoJSON des départements
}
```

---

## 4. Récupération des données

### 4.1 Données distantes — Google Drive

La fonction `read_drive_csv()` (`app/data_loading.py`) télécharge les CSV via **gdown** :

```python
gdown.download(f"https://drive.google.com/uc?id={file_id}", tmp, quiet=True)
return pd.read_csv(tmp, **kwargs)
```

Les identifiants des fichiers sont centralisés dans `app/config.py` :

| Constante | Dataset |
|-----------|---------|
| `POP_FILE_ID` | Population INSEE 2021 |
| `PROS_FILE_ID` | Professionnels RPPS 2026 |
| `ETABS_FILE_ID` | Établissements FINESS 2026 |
| `TEMPS_FILE_ID` | Temps d'accès aux soins |
| `IMMO_FILE_ID` | Transactions DVF 2025 |
| `ENV_FILE_ID` | Score environnemental régional |
| `PATHO_FILE_ID` | Pathologies CNAM 2023 |

> **Cache** : `@st.cache_data` sur `load_all_data()` — le téléchargement ne se fait qu'une fois par session serveur Streamlit.

### 4.2 Données locales — `static/data/`

| Fichier | Usage |
|---------|-------|
| `apl_2023.csv` | APL (Accessibilité Potentielle Localisée) — indicateur clé DREES |
| `delais_rdv_drees.csv` | Délais RDV mesurés par **région** et spécialité |
| `delais_rdv_nationaux.csv` | Délais médians **nationaux** — base pour les estimations départementales |

### 4.3 GeoJSON — GitHub

Contours des 101 départements français, téléchargés depuis :

```
https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements-version-simplifiee.geojson
```

Mis en cache 24 h (`ttl=86400`).

---

## 5. Construction du DataFrame master

`load_all_data()` agrège toutes les sources en un seul DataFrame départemental.

### Pipeline de jointure

```
Population INSEE ──┐
RPPS agrégé ───────┤
FINESS agrégé ─────┤
Temps accès agrégé ├──► master (101 lignes)
DVF agrégé ────────┤
Score env. régional┤
APL 2023 local ────┘
         │
         ▼
  Indicateurs dérivés (/100k hab.)
```

### Traitements par source

| Source | Agrégation départementale | Détail conservé |
|--------|---------------------------|-----------------|
| **Population** | pop, densité, tranches d'âge | — |
| **RPPS** | nb pros, médecins gen., infirmiers, pharmaciens | `pros` : spécialités |
| **FINESS** | nb établissements, hôpitaux, cliniques | `etabs` : coords GPS |
| **Temps d'accès** | médiane, P90, max, communes critiques (>15 min) | `temps` : par commune |
| **DVF** | médiane prix/m², nb transactions, surface moy. | `immo` : par commune |
| **Environnement** | jointure sur Code région | info only |
| **Pathologies** | — | `patho` : prévalence par patho/dept |
| **APL** | médiane dept, P25, P75 | depuis CSV local |

### Indicateurs dérivés

Calculés après la jointure :

```python
p100 = master["population_num"] / 100_000
master["pros_pour_100k"]       = master["nb_pros"] / p100
master["med_gen_pour_100k"]    = master["nb_med_gen"] / p100
master["hopitaux_pour_100k"]   = master["nb_hopitaux"] / p100
master["structures_pour_100k"] = (master["nb_hopitaux"] + master["nb_cliniques"]) / p100
```

### Normalisation des codes département

La fonction `_zd()` zero-pad les codes à 2 caractères (`1` → `01`, `2A`/`2B`/`973` préservés).

---

## 6. Score Sant'active v2

Implémenté dans `app/scoring.py`. Chaque département reçoit un **score global 0–100** basé sur **6 dimensions**.

### Dimensions et pondérations

| Dimension | Colonne source | Poids | Sens |
|-----------|---------------|-------|------|
| APL (accessibilité soins de ville) | `apl_median_dept` | **30 %** | ↑ mieux |
| Médecins généralistes /100k | `med_gen_pour_100k` | **20 %** | ↑ mieux |
| Offre hospitalière /100k | `structures_pour_100k` | **15 %** | ↑ mieux |
| Temps d'accès médian | `temps_acces_median` | **20 %** | ↓ mieux |
| Pression démographique (65+) | `pct_plus_65` | **10 %** | ↓ mieux |
| Contexte foncier (prix/m²) | `prix_m2_moyen` | **5 %** | ↓ mieux |

### Méthode de calcul

1. **Rang percentile** (0–100) pour chaque dimension via `percentile_rank()`
2. **Score global** = moyenne pondérée, **renormalisée** si des dimensions manquent (minimum **3 dimensions** requises)
3. **Sous-score accès** = APL 60 % + temps 40 % (rétro-compatibilité)
4. **Rang national** : 1 = pire situation, N = meilleure

### Classification en zones (terciles réels)

| Zone | Définition | Couleur |
|------|-----------|---------|
| **Critique** | ≤ 33e percentile du score global | `#A51C30` |
| **Intermédiaire** | 33e – 66e percentile | `#E8A838` |
| **Favorable** | > 66e percentile | `#1B5E3F` |

> Les zones sont définies par les **terciles réels** du score global, pas par des seuils fixes.

### Typologie urbaine

Basée sur la densité INSEE :

| Densité (hab/km²) | Typologie |
|-------------------|-----------|
| > 1000 | `urbain_dense` |
| > 250 | `urbain` |
| > 80 | `peri_urbain` |
| ≤ 80 | `rural` |

### Seuil désert médical DREES

**APL < 2,5** consultations/an/habitant = désert médical officiel.

---

## 7. Navigation et routing

L'application n'utilise **pas** le système multi-pages natif de Streamlit. C'est une **SPA maison** gérée par `app/router.py`.

### Fonctionnement

```python
def navigate(view, **params):
    st.session_state["view"] = view
    for k, v in params.items():
        st.session_state[k] = v
    st.query_params.update({"view": view, **params})  # Permalien partageable
    st.rerun()
```

### Vues disponibles

| `view` | Page | Paramètres URL |
|--------|------|----------------|
| `home` | Accueil | — |
| `dept` | Fiche département | `dept_code=02` |
| `region` | Fiche région | `region_code=32` |
| `commune` | Fiche commune | `commune_code=Vervins\|02` |
| `comparer` | Comparaison | — |
| `enjeux` | À quoi ça sert | — |
| `methodologie` | Méthodologie | — |
| `about` | À propos | — |

### Exemples de permaliens

```
https://santactive.streamlit.app/?view=dept&dept_code=02
https://santactive.streamlit.app/?view=region&region_code=32
https://santactive.streamlit.app/?view=commune&commune_code=Vervins|02
```

### Recherche

- **Accueil** : barre de recherche live (`streamlit-searchbox`) — régions, départements, communes
- **Sidebar** : recherche rapide (≥ 2 caractères) via `search_territory()` — normalisation Unicode, score de pertinence

---

## 8. Pages de l'application

### 8.1 Accueil (`home.py`)

| Section | Contenu |
|---------|---------|
| Hero | Titre + description de l'observatoire |
| Recherche live | Autocomplétion régions / départements / communes |
| Suggestions | 4 départements les plus critiques (score le plus bas) |
| Carte choroplèthe | 6 indicateurs sélectionnables, clic → fiche dept |
| Cartouches DOM-TOM | Départements d'outre-mer |
| KPIs nationaux | APL, temps d'accès, médecins/100k, délai ophtalmo, zones critiques |

### 8.2 Fiche département (`fiche_departement.py`)

Page la plus riche — **rapport complet** d'un territoire :

1. **Topbar** — fil d'Ariane + boutons de partage (lien + email pré-rempli)
2. **Header** — score, rang national, zone, badge coloré
3. **Diagnostic** — synthèse en langage naturel
4. **Recommandations** — plan d'action chiffré (médecins à recruter, spécialistes manquants via pathologies CNAM)
5. **Scorecard** — radar 6 dimensions avec détail par axe
6. **Carte communale** — prix/m² et temps d'accès par commune
7. **Contexte** — démographie, immobilier, environnement
8. **Offre médicale** — détail RPPS + établissements FINESS
9. **Délais RDV** — estimations par spécialité
10. **Export PDF** — rapport téléchargeable

### 8.3 Fiche région (`fiche_region.py`)

- Agrégation des départements de la région
- Score moyen, nombre de zones critiques, écart min/max
- Carte des départements de la région
- Liste cliquable vers chaque fiche département

### 8.4 Fiche commune (`fiche_commune.py`)

- Données **partielles** (pas de score propre à la commune)
- KPIs locaux : temps d'accès, prix/m², établissements à proximité
- Fil d'Ariane vers département et région parente
- Code commune au format `NOM_COMMUNE|CODE_DEPT`

### 8.5 Comparer (`comparer.py`)

- Sélection de 2 à 4 départements via multiselect
- Tableau synoptique de tous les indicateurs clés
- Graphiques radar Plotly pour comparaison visuelle

### 8.6 Pages informatives

| Page | Contenu |
|------|---------|
| `enjeux.py` | Contexte et cas d'usage (ARS, élus, professionnels) |
| `methodologie.py` | Détail du calcul des scores et des sources |
| `about.py` | Crédits ESData, contact, mentions |

---

## 9. Composants réutilisables

### 9.1 Cartes (`components/maps.py`)

- **Technologie** : Folium + streamlit-folium
- **Tuiles** : CartoDB Positron (fond clair institutionnel)
- **Types** : choroplèthe nationale, cartes communales, cartouches DOM-TOM
- **Dégradés** : score, prix, temps, pros, âge
- **Interaction** : clic sur un département → navigation vers sa fiche

### 9.2 Délais RDV (`components/delais.py`)

Deux sources combinées :

1. **DREES régional** (`delais_rdv_drees.csv`) — délais mesurés par région/spécialité
2. **Proxy départemental** — estimation via ratio APL :

```
délai_estimé_dept = délai_national × (APL_médiane_nationale / APL_dept)
```

- Plafonné à **3×** le délai national (évite les aberrations DOM)
- **Estimation**, pas une mesure directe — la DREES ne publie pas de données départementales récentes

### 9.3 Recherche (`search.py`)

- Normalisation Unicode (accents supprimés via NFKD)
- Match sur nom ou code département
- Score de pertinence : 100 = commence par la requête, 70 = contient, 60 = commune
- Liste des communes construite depuis le dataset `temps`

### 9.4 Autres composants

| Composant | Rôle |
|-----------|------|
| `kpi_card.py` | Cartes indicateurs avec valeur, unité, contexte |
| `badges.py` | Badges colorés de zone (Critique / Intermédiaire / Favorable) |
| `alerts.py` | Alertes contextuelles (désert médical, données manquantes) |
| `tooltip.py` | Info-bulles méthodologiques sur les indicateurs |

---

## 10. Export PDF

Généré par `app/pdf_export.py` avec **ReportLab** :

- En-tête avec logo, score global, zone colorée
- Tableaux d'indicateurs clés
- Scorecard par dimension (6 axes)
- Recommandations chiffrées
- Téléchargement via `st.download_button` sur la fiche département

---

## 11. Parcours utilisateur

```
Arrivée sur l'app
       │
       ▼
   ┌─────────┐
   │ Accueil │
   └────┬────┘
        │
   ┌────┼────────────────┬──────────────┐
   │    │                │              │
   ▼    ▼                ▼              ▼
Recherche          Clic carte      Suggestion      Sidebar
   │                    │           critique           │
   ▼                    ▼              │               ▼
┌──────┐          ┌──────────┐        │          Comparer / Enjeux
│Résultat│        │Fiche dept│◄───────┘          / Méthodo / About
└──┬───┘          └────┬─────┘
   │                   │
   ├─ Département ─────►│
   ├─ Région ──► Fiche région ──► Fiche dept
   └─ Commune ─► Fiche commune ──► Fiche dept
                        │
                   ┌────┼────┐
                   ▼    ▼    ▼
                 PDF  Comparer  Partage (lien/email)
```

---

## 12. Installation et lancement

### Prérequis

- Python 3.10+
- macOS ou Linux
- Sur macOS, `weasyprint` nécessite Pango : `brew install pango`

### Commandes

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

L'application sera disponible sur [http://localhost:8501](http://localhost:8501).

### Dépendances principales

| Package | Usage |
|---------|-------|
| `streamlit` | Framework UI |
| `pandas` / `numpy` | Manipulation de données |
| `gdown` | Téléchargement Google Drive |
| `folium` / `streamlit-folium` | Cartes interactives |
| `plotly` | Graphiques (radar, barres) |
| `streamlit-searchbox` | Recherche live avec autocomplétion |
| `reportlab` | Export PDF |
| `requests` | Téléchargement GeoJSON |

---

## 13. Mise à jour des données

### Données Google Drive

1. Remplacer le CSV sur Google Drive
2. Vérifier que l'ID dans `app/config.py` pointe vers le bon fichier
3. Redémarrer l'app (ou vider le cache Streamlit : `C` dans le menu)

### Données locales

| Fichier | Action |
|---------|--------|
| `static/data/apl_2023.csv` | Remplacer par la nouvelle version ANCT |
| `static/data/delais_rdv_drees.csv` | Mettre à jour si nouvelles données DREES régionales |
| `static/data/delais_rdv_nationaux.csv` | Mettre à jour les délais médians nationaux |

### GeoJSON

L'URL est configurée dans `app/config.py` (`GEOJSON_URL`). Le cache expire après 24 h.

---

## 14. Points clés à retenir

1. **Maille principale = département.** Le score global n'existe qu'à ce niveau. Commune et région sont des vues agrégées ou partielles.

2. **Deux sources de données** : Google Drive (gros CSV, mis à jour via IDs dans `config.py`) + fichiers locaux (`static/data/` pour APL et délais).

3. **Cache Streamlit** — `@st.cache_data` évite de re-télécharger à chaque interaction. Le premier chargement peut prendre du temps (téléchargement de plusieurs CSV depuis Drive).

4. **APL est l'indicateur roi** (30 % du score) — mesure DREES la plus fine de l'accès aux médecins généralistes. Seuil désert médical officiel : **APL < 2,5**.

5. **Le score environnemental est exclu** du calcul global car il n'est disponible qu'à la maille régionale.

6. **Les délais RDV départementaux sont estimés**, pas mesurés — la DREES ne publie pas de données départementales récentes en open data.

7. **Architecture SPA maison** — pas de multi-pages Streamlit natif ; le routing est géré par `session_state` + query params pour des permaliens partageables.

8. **Optimisation mémoire** — les gros DataFrames bruts sont supprimés après agrégation ; downcast float64 → float32 ; seules les colonnes utiles sont conservées dans les datasets de détail.

---

*Document généré pour le projet Sant'active — ESData / ESD Paris, 2026.*
