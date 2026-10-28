"""Composant d'aide contextuelle (icône ⓘ) : définitions centralisées.

Règles éditoriales (finition du 28 octobre 2026) :
- une définition par notion, la même partout (fiches, accueil, Méthodologie, PDF) ;
- chaque aide dit ce que mesure l'indicateur, sa source et son millésime, et la
  limite qui compte pour la décision ; jamais d'affirmation non sourcée ;
- distinction explicite : donnée observée, calcul Sant'active, estimation, simulation ;
- courte : lisible en quelques secondes par un lecteur non spécialiste.

Usage :
    from ..components.tooltip import info_tooltip
    st.markdown(f'APL {info_tooltip("apl")}', unsafe_allow_html=True)
"""
from __future__ import annotations

from ..config import APL_AGREGATION, APL_MILLESIME

_SRC = "<br><br><strong>Source :</strong> "

TOOLTIPS: dict[str, dict[str, str]] = {
    "apl": {
        "title": "APL : accessibilité potentielle localisée",
        "body": (
            "Nombre de consultations de médecine générale (visites et téléconsultations comprises) "
            "accessibles par an et par habitant, en tenant compte de l'activité des médecins, de "
            "l'âge de la population et de la distance aux communes voisines. Indicateur de "
            "référence calculé par la DREES."
            "<br><br><strong>Repère 2,5</strong> : seuil de sous-densité du zonage des généralistes "
            "(il n'existe pas de définition légale du « désert médical »)."
            f"<br><br><strong>Dans Sant'active</strong> : valeur départementale = {APL_AGREGATION}."
            f"{_SRC}DREES, APL aux médecins généralistes, millésime {APL_MILLESIME}."
        ),
    },
    "score_global": {
        "title": "Score Sant'active",
        "body": (
            "Indice sur 100 construit par Sant'active à partir de six indicateurs publics : "
            "APL (30 %), temps d'accès à un généraliste (20 %), densité de généralistes (20 %), "
            "offre hospitalière (15 %), part des 65 ans et plus (10 %), prix immobilier (5 %)."
            "<br><br>Chaque indicateur est converti en rang parmi les 100 départements analysés "
            "(50 = médiane) ; le score est la moyenne pondérée de ces rangs. Il situe un département "
            "par rapport aux autres sur l'offre et l'accès aux soins de premier recours : ce n'est ni "
            "une note de santé, ni une évolution dans le temps."
            "<br><br>Les pondérations sont un choix méthodologique du projet, documenté dans la "
            "Méthodologie ; elles ne sont pas des pondérations officielles."
        ),
    },
    "temps_acces": {
        "title": "Temps d'accès à un médecin généraliste",
        "body": (
            "Temps de trajet en voiture, pour chaque carreau habité de 200 m, vers le cabinet de "
            "médecin généraliste le plus proche (lieu d'exercice réel). Deux lectures : la médiane "
            "pondérée par la population (dimension du score) et la part des habitants à plus de "
            "15 minutes (repère de fragilité)."
            "<br><br>Mesure une distance, pas une disponibilité : un généraliste proche peut ne plus "
            "prendre de patients. Guadeloupe, Guyane et Mayotte sont hors champ."
            f"{_SRC}INSEE, accès aux équipements 2025 (BPE 2025, distancier Metric-OSRM, population Filosofi)."
        ),
    },
    "med_100k": {
        "title": "Médecins généralistes pour 100 000 habitants",
        "body": (
            "Nombre de médecins généralistes en activité au 1<sup>er</sup> janvier 2026 (personnes, "
            "tous modes d'exercice, libéraux et salariés), rapporté à la population du recensement "
            "2021."
            "<br><br>Un effectif de personnes, pas un temps de travail : à lire avec l'APL, qui tient "
            "compte de l'activité réelle et de la demande."
            f"{_SRC}DREES, répertoire RPPS, 1<sup>er</sup> janvier 2026 · INSEE RP 2021."
        ),
    },
    "delais_rdv": {
        "title": "Délais de rendez-vous : estimation indicative",
        "body": (
            "Aucune source publique ne mesure les délais de rendez-vous par département. Sant'active "
            "part des délais nationaux observés par la DREES en 2016-2017 (neuf spécialités) et les "
            "ajuste par le rapport entre l'APL de référence et l'APL du département, plafonné à ×3."
            "<br><br><strong>Ce ne sont pas des délais actuels observés</strong> : c'est une estimation "
            "historique, utile pour comparer des territoires, pas pour annoncer un délai en 2026."
            f"{_SRC}DREES, enquête « Délais d'attente en matière d'accès aux soins », 2016-2017."
        ),
    },
    "zone": {
        "title": "Zones critique, intermédiaire, favorable",
        "body": (
            "Les 100 départements analysés sont classés par score puis répartis en trois groupes de "
            "taille égale (terciles) : 33 critiques, 34 intermédiaires, 33 favorables, par construction."
            "<br><br>Une zone situe un département parmi les autres ; elle ne mesure pas une évolution et "
            "ne constitue pas une classification officielle. Mayotte est hors score (sources incomplètes)."
        ),
    },
    "prix_m2": {
        "title": "Prix médian au m²",
        "body": (
            "Prix médian des transactions immobilières du département (maisons et appartements), en euros "
            "par m². Dans le score (5 %), un prix bas est lu comme un contexte plus favorable à "
            "l'installation d'un professionnel ; ce n'est qu'un indicateur de contexte."
            f"{_SRC}DVF (demandes de valeurs foncières), DGFiP, 2025."
        ),
    },
    "patho": {
        "title": "Prévalence des pathologies",
        "body": (
            "Part des assurés du département pris en charge pour une pathologie, d'après les soins "
            "remboursés par l'Assurance Maladie. Ce sont des patients suivis, pas des besoins non "
            "couverts."
            "<br><br>Les prévalences brutes dépendent de l'âge de la population ; dans la priorisation, "
            "Sant'active utilise des prévalences standardisées sur l'âge, comparables entre départements."
            f"{_SRC}CNAM, cartographie des pathologies et des dépenses, 2023."
        ),
    },
    "pct_65": {
        "title": "Part des 65 ans et plus",
        "body": (
            "Pourcentage de la population âgée de 65 ans ou plus. Dans le score (10 %), une part élevée "
            "est lue comme une pression plus forte sur la demande de soins ; dans la priorisation, elle "
            "entre dans l'indice de besoins."
            f"{_SRC}INSEE, recensement de la population 2021."
        ),
    },
    "rang_national": {
        "title": "Classement national",
        "body": (
            "Position du département parmi les 100 départements analysés, classés par score "
            "Sant'active : 1<sup>er</sup> = le mieux placé, 100<sup>e</sup> = le moins bien placé."
            "<br><br>Les rangs sont uniques (égalité départagée par le code du département). Le "
            "classement change lorsque les données sont mises à jour."
        ),
    },
    "densite": {
        "title": "Densité de population et typologie",
        "body": (
            "Habitants par km² (recensement 2021). Sant'active en déduit une typologie utilisée par les "
            "leviers : rural (jusqu'à 80 hab./km²), péri-urbain (80 à 250), urbain (250 à 1 000), "
            "urbain dense (plus de 1 000)."
            "<br><br>Ces seuils sont une convention de lecture de l'outil, pas une classification officielle."
            f"{_SRC}INSEE, recensement de la population 2021."
        ),
    },
    "score_acces": {
        "title": "Accès aux soins (sous-score)",
        "body": (
            "Lecture combinée de deux dimensions du score : l'APL (60 %) et le temps de trajet en voiture "
            "vers un médecin généraliste (40 %, INSEE 2025), en rangs parmi les départements."
            "<br><br>Facilite la lecture du diagnostic ; ne remplace pas le score Sant’active."
        ),
    },
    "score_pros": {
        "title": "Offre médicale (sous-score)",
        "body": (
            "Rang du département pour la densité de médecins généralistes pour 100 000 habitants "
            "(DREES RPPS 2026). Facilite la lecture du diagnostic ; ne remplace pas le score Sant’active."
        ),
    },
    "score_etabs": {
        "title": "Structures de soins (sous-score)",
        "body": (
            "Rang du département pour le nombre de sites hospitaliers pour 100 000 habitants : centres "
            "hospitaliers et centres hospitaliers régionaux, établissements privés de soins de suite et "
            "de réadaptation. Compte des sites, pas des lits ni des capacités."
            "<br><br>Les cliniques privées de court séjour (médecine, chirurgie, obstétrique) ne sont pas "
            "comptées : l'indicateur ne décrit pas toute l'offre hospitalière du département."
            f"{_SRC}FINESS (ministère chargé de la Santé, diffusion DREES), mars 2026."
        ),
    },
    "recommandation": {
        "title": "Leviers d'action : comment ils sont choisis",
        "body": (
            "Les leviers viennent d'un catalogue d'une vingtaine de dispositifs existants (maisons de "
            "santé, équipes mobiles, téléconsultation assistée, parcours gériatriques…). Chaque levier a "
            "des conditions chiffrées : certaines obligatoires (par exemple au moins 3 % de la "
            "population à plus de 15 min d'un généraliste), d'autres contributives, et des exclusions."
            "<br><br>Un levier apparaît si ses conditions obligatoires sont remplies et qu'au moins un "
            "tiers de ses conditions pondérées le sont. Au plus quatre leviers par département, deux "
            "par famille. Sans levier déclenché, l'outil propose une veille (« maintien »)."
            "<br><br>Règles explicites, sans intelligence artificielle. Ce sont des pistes à instruire "
            "avec les acteurs locaux, pas des prescriptions ni une évaluation de politique publique."
        ),
    },
}


def info_tooltip(key: str, size: int = 14, *, open_dir: str = "auto") -> str:
    """HTML d'une icône ⓘ avec aide au survol, au focus clavier et au toucher (CSS seul :
    st.markdown n'exécute pas de JavaScript). `open_dir="right"` force l'ouverture vers la droite."""
    tip = TOOLTIPS.get(key)
    if not tip:
        return ""
    title = tip["title"]
    body = tip["body"]
    dir_class = " sa-tip--open-right" if open_dir == "right" else ""
    return (
        f'<span class="sa-tip{dir_class}" tabindex="0" role="button" aria-label="Définition : {title}">'
        f'<span class="sa-tip-icon" style="font-size:{size - 2}px;">ⓘ</span>'
        f'<span class="sa-tip-box" role="tooltip">'
        f'<strong class="sa-tip-title">{title}</strong>'
        f'<span class="sa-tip-body">{body}</span>'
        f'</span></span>'
    )
