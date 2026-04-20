"""Configuration centralisée : IDs Drive, constantes métier, pondérations."""

# ─── Google Drive — identifiants des datasets ─────────────────────────────────
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

# ─── Sources locales ──────────────────────────────────────────────────────────
# APL 2023 — snapshot ANCT (voir static/data/apl_2023.csv)
# Pour mettre à jour : remplacer le CSV par la nouvelle version ANCT
DELAIS_RDV_PATH = "static/data/delais_rdv_drees.csv"

# ─── Pondérations du score global ─────────────────────────────────────────────
# NB : env = 0 car le score environnemental est à maille régionale (pas départementale).
#      Il est conservé comme indicateur info-only affiché séparément.
POIDS_SCORE = {
    "acces": 0.35,
    "pros":  0.35,
    "etabs": 0.30,
    "env":   0.00,
}

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
