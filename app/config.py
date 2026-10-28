"""Configuration centralisée : sources, constantes métier, pondérations."""

import os
from pathlib import Path


def _option(nom: str, defaut: str, valeurs: tuple[str, ...]) -> str:
    """Option de moteur : variable d'environnement, sinon st.secrets, sinon défaut.

    Permet de changer de mode sur Railway / Streamlit Cloud sans toucher au code.
    Une valeur inconnue est refusée (pas de bascule silencieuse).
    """
    val = os.environ.get(nom)
    if val is None:
        try:  # st.secrets lève une exception s'il n'existe pas de secrets.toml
            import streamlit as st

            val = st.secrets.get(nom) if hasattr(st, "secrets") else None
        except Exception:
            val = None
    val = (val or defaut).strip().lower()
    if val not in valeurs:
        raise ValueError(f"{nom}={val!r} : valeurs admises {valeurs}")
    return val


# ─── Sélection EXPLICITE des sources et méthodes du moteur ───────────────────
# Mode cible = valeurs par défaut. L'ancien mode n'existe que pour les
# comparaisons historiques ; aucun fichier n'active une méthode par sa seule
# présence.
SOURCE_EFFECTIFS = _option("SANTACTIVE_SOURCE_EFFECTIFS", "drees", ("drees", "equipe"))
#   drees  : effectifs DREES/RPPS au 1er janvier 2026 (personnes distinctes)
#   equipe : lignes du fichier territorial de l'équipe (présences — historique)
APL_METHODE = _option("SANTACTIVE_APL_METHODE", "ponderee", ("mediane", "ponderee"))
#   mediane  : médiane simple des APL communaux (méthode historique)
#   ponderee : moyenne pondérée par la population standardisée (méthode DREES)
ETABS_DEFINITION = _option("SANTACTIVE_ETABS_DEFINITION", "actuelle", ("actuelle", "court_sejour"))
#   actuelle     : CH + CHR + établissements privés SSR
#   court_sejour : CH + CHR + hôpitaux locaux + privés MCO + CLCC
TEMPS_SOURCE = _option("SANTACTIVE_TEMPS_SOURCE", "insee", ("interne", "insee"))
#   insee   : médiane pondérée par la population du temps de trajet en voiture vers le
#             généraliste le plus proche (Insee 2025, carreaux 200 m, Metric-OSRM) —
#             mode actif depuis le 28 octobre 2026 (validation William) ;
#             Guadeloupe, Guyane et Mayotte sans valeur (poids redistribué)
#   interne : médiane communale du fichier de l'équipe (0 = généraliste présent dans la
#             commune, sinon minutes vers la commune équipée la plus proche) — mode
#             historique, conservé pour l'audit (docs/EVOLUTIONS_MOTEUR.md §17)
APL_MILLESIME = _option("SANTACTIVE_APL_MILLESIME", "2024", ("2023", "2024"))
CARTE_CONTINUE = _option("SANTACTIVE_CARTE_CONTINUE", "off", ("off", "on"))
#   off : V1 — cartographie INSEE (zones habitées) pour tous les départements, présentation homogène ;
#   on  : V2 — grille routière continue (scripts/donnees/carte_continue.py) là où static/geo/continu_mg_<dept>.json existe
#   2024 : millésime actif depuis le 28 octobre 2026 (même définition DREES : APL aux
#          médecins généralistes tous âges, population standardisée) ; 2023 : historique

# ─── Sources locales (prioritaires) ───────────────────────────────────────────
DATA_DIR = Path("static/data")

POP_PATH   = DATA_DIR / "population.csv"
PROS_PATH  = DATA_DIR / "professionnels.csv.gz"
ETABS_PATH = DATA_DIR / "etablissements.csv.gz"
TEMPS_PATH = DATA_DIR / "temps_acces.csv.gz"
IMMO_PATH  = DATA_DIR / "immobilier.csv.gz"
ENV_PATH   = DATA_DIR / "environnement.csv"
PATHO_PATH = DATA_DIR / "pathologies.csv.gz"
MEDIC_PATH = DATA_DIR / "medicaments.csv"

# ─── Effectifs officiels DREES / RPPS (jeu A) ─────────────────────────────────
# Produits par scripts/donnees/telecharger_drees_rpps.py et
# calculer_apl_departemental.py. Utilisés selon SOURCE_EFFECTIFS / APL_METHODE
# (ci-dessus) ; le fichier « professionnels » de l'équipe reste le jeu B
# (présence locale, pas effectifs).
MEDECINS_DREES_PATH  = DATA_DIR / "drees_medecins_dept_2026.csv"
AUTRES_PS_DREES_PATH = DATA_DIR / "drees_autres_rpps_dept_2026.csv"
IDEL_DREES_PATH      = DATA_DIR / "drees_infirmieres_liberales_dept_2023.csv"
APL_DEPT_DREES_PATH  = DATA_DIR / f"apl_mg_departemental_{APL_MILLESIME}.csv"   # APL communal agrégé (DREES, millésime actif)
APL_COMMUNES_PATH    = DATA_DIR / f"apl_communes_{APL_MILLESIME}.csv"           # APL communal (lecture communale, capacité)
ACCES_INSEE_DEPT_PATH = DATA_DIR / "acces_insee_departements_2025.csv"   # accès routier INSEE 2025 (départements)
ACCES_INSEE_COMMUNES_PATH = DATA_DIR / "acces_insee_mg_communes_2025.csv"  # idem, communes (généraliste)

# Catégories FINESS (categetab) comptées comme « structures » selon la définition
ETABS_CATEGORIES = {
    "actuelle": ["Centre Hospitalier (C.H.)", "Centre Hospitalier Régional (C.H.R.)",
                 "Etablissement de santé privé autorisé en SSR"],
    "court_sejour": ["Centre Hospitalier (C.H.)", "Centre Hospitalier Régional (C.H.R.)",
                     "Centre hospitalier, ex Hôpital local",
                     "Etablissement de Soins Pluridisciplinaire", "Etablissement de Soins Chirurgicaux",
                     "Etablissement de Soins Médicaux",
                     "Etablissement Soins Obstétriques Chirurgico-Gynécologiques",
                     "Centre de Lutte Contre Cancer"],
}
TEMPS_LABELS = {"insee": "INSEE 2025", "interne": "indicateur interne"}
TEMPS_LABEL_COURT = TEMPS_LABELS[TEMPS_SOURCE]          # « INSEE 2025 » : libellé de la source active du temps d'accès
TEMPS_DESCRIPTION = {
    "insee": "médiane pondérée par la population du temps en voiture vers le généraliste le plus proche (INSEE 2025, carreaux de 200 m)",
    "interne": "médiane des communes du temps vers la commune équipée la plus proche (fichier interne, 0 = généraliste présent)",
}[TEMPS_SOURCE]
APL_SOURCE_LABEL = f"DREES {APL_MILLESIME}"
APL_LABELS = {"mediane": "APL médian communal", "ponderee": "APL moyen pondéré (méthode DREES)"}
APL_LABEL = APL_LABELS[APL_METHODE]
APL_LABEL_COURT = {"mediane": "APL médian", "ponderee": "APL pondéré"}[APL_METHODE]
APL_AGREGATION = {
    "mediane": "médiane simple des APL communaux (chaque commune pèse autant)",
    "ponderee": "moyenne des APL communaux pondérée par la population standardisée (méthode DREES)",
}[APL_METHODE]

# ─── Google Drive — secours si le fichier local est absent ─────────────────────
POP_FILE_ID   = "11rOLt12iXUxbEQTRlZlbuil_AEp2jxue"
PROS_FILE_ID  = "1_wkO1vtWE2WO9aZmiI8lNPdbecO5V3pA"
ETABS_FILE_ID = "1hZ71udkcpyquNPgGowvSxUrjrmK-n-PC"
TEMPS_FILE_ID = "1BoP_S7BYOvDKpwOhpFSEscTM31ltPEEa"
IMMO_FILE_ID  = "1Psjk6nf41I_X4dnFE0kgXpCNN5is4s9n"
ENV_FILE_ID   = "1rfdxUJDSX5HzHStZgl5LTUPBoGF9V2i4"
MEDIC_FILE_ID = "193dosn8DVXFgALvoWynssmxcs-8eNM82"
PATHO_FILE_ID = "1TrJQTnlwEeGtCb6LRUzbwv3dZ2MviY-W"

GEOJSON_URL = (
    "https://raw.githubusercontent.com/gregoiredavid/"
    "france-geojson/master/departements-version-simplifiee.geojson"
)

# ─── Autres sources locales ───────────────────────────────────────────────────
# APL 2023 — snapshot ANCT (voir static/data/apl_2023.csv)
# Pour mettre à jour : remplacer le CSV par la nouvelle version ANCT
DELAIS_RDV_PATH = "static/data/delais_rdv_drees.csv"

# Valeur affichée lorsqu'une donnée est absente (évite le tiret cadratin « — »)
NA_DISPLAY = "N/D"

# ─── Pondérations du score global (Sant'active v2) ────────────────────────────
# Source de vérité : app/scoring.py → DIMENSIONS et compute_scores().
# 6 dimensions : APL 30 %, temps 20 %, médecins 20 %, structures 15 %,
# seniors 10 %, foncier 5 %.
# Le score environnemental (enviro_score) reste info-only, hors score global.

# ─── Labels des zones (terciles) ──────────────────────────────────────────────
ZONE_LABELS = {
    "critique":      "Zone critique",
    "intermediaire": "Zone intermédiaire",
    "favorable":     "Zone favorable",
}

# ─── Pathologies "bruit médical" à exclure ────────────────────────────────────
PATHOS_SPECIALITES_MAP = {
    "Maladies cardioneurovasculaires":                          ["Cardiologue", "Médecin vasculaire"],
    "Diabète":                                                  ["Endocrinologue"],
    "Cancers":                                                  ["Oncologue", "Radiothérapeute"],
    "Maladies respiratoires chroniques (hors mucoviscidose)":   ["Pneumologue"],
    "Maladies psychiatriques":                                  ["Psychiatre"],
    "Maladies neurologiques ou dégénératives":                  ["Neurologue"],
    "Insuffisance rénale chronique terminale":                  ["Néphrologue"],
    "Maladies inflammatoires ou rares ou VIH ou SIDA":          ["Médecin interniste", "Infectiologue"],
}

PATHOS_EXCLUDED = [
    "Pas de pathologie repérée, traitement, maternité, hospitalisation ou traitement antalgique ou anti-inflammatoire",
    "Hospitalisations hors pathologies repérées (avec ou sans pathologies, traitements ou maternité)",
    "Traitements du risque vasculaire (hors pathologies)",
    "Traitements psychotropes (hors pathologies)",
    # Libellé réel du fichier CNAM 2023 (l'entrée « Pas de pathologie repérée… »
    # ci-dessus ne correspond à aucune ligne, ce traitement n'était pas exclu)
    "Traitements antalgiques ou anti-inflammatoires (hors pathologies, traitements, maternité ou hospitalisations)",
]

# ─── Palette DSFR-inspired ────────────────────────────────────────────────────
PALETTE = {
    "bleu_regalien":   "#1A3D8F",   # principal
    "bleu_actif":      "#2E6BE6",   # CTA, liens, sélection
    "bleu_fonce":      "#0F1E4A",   # sidebar, hero
    "bleu_pale":       "#E8EDF8",   # fonds apaisés
    "vert_sante":      "#00A878",   # favorable
    "ambre_alerte":    "#F4C430",   # intermédiaire
    "rouge_critique":  "#CE0500",   # critique (rouge DSFR)
    "gris_texte":      "#161616",
    "gris_secondaire": "#666666",
    "gris_bordure":    "#E5E5E5",
    "gris_fond":       "#F6F6F6",
    "blanc":           "#FFFFFF",
}

# ─── Mapping zones → couleur ──────────────────────────────────────────────────
CMAP = {
    "Critique":              PALETTE["rouge_critique"],
    "Intermédiaire":         PALETTE["ambre_alerte"],
    "Favorable":             PALETTE["vert_sante"],
    "Données insuffisantes": PALETTE["gris_secondaire"],
}

# ─── Template Plotly global ───────────────────────────────────────────────────
PLOTLY_TEMPLATE = {
    "layout": {
        "font": {"family": "Marianne, Inter, sans-serif", "size": 13,
                 "color": PALETTE["gris_texte"]},
        "title": {"font": {"size": 15, "color": PALETTE["gris_texte"]},
                  "x": 0, "xanchor": "left"},
        "plot_bgcolor":  PALETTE["blanc"],
        "paper_bgcolor": PALETTE["blanc"],
        "xaxis": {"showgrid": False, "zeroline": False,
                  "linecolor": PALETTE["gris_bordure"]},
        "yaxis": {"showgrid": True, "gridcolor": PALETTE["gris_fond"],
                  "zeroline": False, "linecolor": PALETTE["gris_bordure"]},
        "legend": {"orientation": "h", "yanchor": "bottom",
                   "y": -0.25, "xanchor": "left", "x": 0},
        "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
        "hoverlabel": {"bgcolor": PALETTE["blanc"],
                       "bordercolor": PALETTE["bleu_regalien"],
                       "font": {"family": "Marianne, Inter, sans-serif"}},
    }
}
