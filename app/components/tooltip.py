"""Composant tooltip informatif réutilisable.

Usage :
    from ..components.tooltip import info_tooltip

    st.markdown(
        f'APL {info_tooltip("apl")}',
        unsafe_allow_html=True
    )
"""
from __future__ import annotations

# ── Dictionnaire centralisé de toutes les définitions ────────────────────────
TOOLTIPS: dict[str, dict[str, str]] = {
    "apl": {
        "title": "APL — Accessibilité Potentielle Localisée",
        "body": (
            "Mesure le nombre de consultations disponibles par an "
            "et par habitant, en tenant compte du nombre de médecins "
            "actifs dans un rayon de 20-30 min, de leur volume d'activité "
            "réel, et de la demande locale pondérée par l'âge des habitants."
            "<br><br>"
            "<strong>Seuil officiel DREES :</strong> en dessous de 2.5, "
            "le territoire est considéré en désert médical."
            "<br><br>"
            "<strong>Source :</strong> ANCT / Observatoire des territoires · "
            "Millésime 2023"
        ),
    },
    "score_global": {
        "title": "Score global Sant'active",
        "body": (
            "Indicateur synthétique sur 100 calculé à partir de trois "
            "dimensions pondérées :"
            "<br>• Accès aux soins (35 %) : APL + temps d'accès médian"
            "<br>• Professionnels de santé (35 %) : densité médecins /100k"
            "<br>• Établissements (30 %) : densité hôpitaux FINESS /100k"
            "<br><br>"
            "Chaque dimension est normalisée en rang percentile national "
            "(méthode DREES). Le score 50 correspond à la médiane nationale."
            "<br><br>"
            "<strong>Source :</strong> calcul Sant'active · données "
            "RPPS janv. 2026, FINESS mars 2026, ANCT 2023"
        ),
    },
    "temps_acces": {
        "title": "Temps d'accès médian",
        "body": (
            "Temps de trajet médian (en voiture) vers l'hôpital ou la "
            "clinique FINESS la plus proche, calculé pour chaque commune "
            "du département et agrégé en médiane pondérée par la population."
            "<br><br>"
            "Mesure la distance physique aux structures hospitalières. "
            "Distinct de l'APL qui mesure la disponibilité des médecins "
            "de ville."
            "<br><br>"
            "<strong>Source :</strong> calcul interne · FINESS mars 2026 "
            "+ INSEE 2021"
        ),
    },
    "med_100k": {
        "title": "Médecins généralistes / 100 000 habitants",
        "body": (
            "Nombre de médecins généralistes actifs pour 100 000 habitants."
            "<br><br>"
            "<strong>⚠ Attention :</strong> le RPPS inclut tous les modes "
            "d'exercice (libéral, salarié hospitalier, mixte). Un département "
            "peut afficher une bonne densité RPPS tout en étant en désert "
            "médical selon l'APL, qui ne compte que les libéraux avec une "
            "activité réelle."
            "<br><br>"
            "<strong>Source :</strong> RPPS · DREES · janv. 2026"
        ),
    },
    "delais_rdv": {
        "title": "Estimation des délais de RDV",
        "body": (
            "Estimation calculée en deux étapes :"
            "<br>1. Base nationale réelle : enquête DREES 2016-2017 "
            "(40 000 personnes, 9 spécialités)"
            "<br>2. Ajustement par l'APL du département : "
            "délai estimé = délai national × (APL nationale 2.9 / APL dept)"
            "<br><br>"
            "Un APL faible → délais estimés plus longs, conformément à la "
            "corrélation documentée par la DREES."
            "<br><br>"
            "<strong>⚠ Estimation indicative</strong>, non une mesure "
            "directe. Données départementales directes non disponibles "
            "en open data. Facteur plafonné à ×3."
            "<br><br>"
            "<strong>Source :</strong> DREES · Études et Résultats "
            "n°1085 · oct. 2018"
        ),
    },
    "zone": {
        "title": "Classification par zone",
        "body": (
            "Chaque département est classé en trois zones calculées "
            "par terciles réels sur les 101 départements français :"
            "<br><br>"
            "🔴 <strong>Critique</strong> : score dans le tiers inférieur "
            "(≤ 33e percentile)"
            "<br>"
            "🟡 <strong>Intermédiaire</strong> : tiers médian"
            "<br>"
            "🟢 <strong>Favorable</strong> : tiers supérieur "
            "(≥ 67e percentile)"
            "<br><br>"
            "Les zones ne sont pas figées : elles évoluent si le score "
            "global est recalculé avec de nouvelles données."
        ),
    },
    "prix_m2": {
        "title": "Prix médian au m²",
        "body": (
            "Prix médian des transactions immobilières (maisons + "
            "appartements) en euros par m², calculé sur l'ensemble "
            "des ventes enregistrées dans le département."
            "<br><br>"
            "Indicateur de contexte : un prix bas favorise "
            "l'installation de professionnels de santé (coût du cabinet, "
            "logement). Un prix élevé peut être un frein."
            "<br><br>"
            "<strong>Source :</strong> DVF (Demande de Valeurs Foncières) "
            "· DGFiP · 2025"
        ),
    },
    "patho": {
        "title": "Prévalence des pathologies",
        "body": (
            "Taux de prévalence standardisé par pathologie : "
            "pourcentage de la population du département pris en charge "
            "pour cette pathologie, d'après la consommation de soins "
            "remboursée par l'Assurance Maladie."
            "<br><br>"
            "Un taux élevé indique un besoin de soins plus important, "
            "à croiser avec la disponibilité de l'offre médicale."
            "<br><br>"
            "<strong>Source :</strong> CNAM / Ameli open data · 2023"
        ),
    },
    "pct_65": {
        "title": "Part des 65 ans et plus",
        "body": (
            "Pourcentage de la population ayant 65 ans ou plus. "
            "Indicateur clé pour la santé territoriale : les seniors "
            "consomment environ 4× plus de soins que les adultes de 30 ans "
            "(source DREES), ce qui pèse sur la demande locale."
            "<br><br>"
            "Un département avec un APL faible ET une forte part de 65+ "
            "cumule les deux facteurs de tension sur l'offre de soins."
            "<br><br>"
            "<strong>Source :</strong> INSEE · Recensement 2021"
        ),
    },
    "rang_national": {
        "title": "Rang national",
        "body": (
            "Position du département parmi les 101 départements français "
            "classés par score global croissant. "
            "Rang 1 = situation la plus dégradée. "
            "Rang 101 = situation la plus favorable."
            "<br><br>"
            "Le rang dépend directement du score global Sant'active "
            "et évolue si de nouvelles données sont intégrées."
        ),
    },
    "densite": {
        "title": "Densité de population",
        "body": (
            "Nombre d'habitants par km². Indicateur structurel clé :"
            "<br>• Zones denses (> 200 hab/km²) : offre médicale "
            "généralement plus accessible, mais délais plus longs"
            "<br>• Zones peu denses (< 30 hab/km²) : risque de désert "
            "médical accru, rentabilité des cabinets plus faible"
            "<br><br>"
            "La densité conditionne la viabilité économique d'un cabinet "
            "médical et donc l'attractivité d'un territoire pour "
            "les nouvelles installations."
            "<br><br>"
            "<strong>Source :</strong> INSEE · Recensement 2021"
        ),
    },
    "score_acces": {
        "title": "Score d'accès aux soins",
        "body": (
            "Composante du score global (poids 35 %). Combine :"
            "<br>• APL (65 %) : nombre de consultations disponibles "
            "par an et par habitant"
            "<br>• Temps d'accès médian (35 %) : trajet vers "
            "l'établissement hospitalier le plus proche"
            "<br><br>"
            "Normalisé en rang percentile national. "
            "Score 50 = médiane nationale."
        ),
    },
    "score_pros": {
        "title": "Score professionnels de santé",
        "body": (
            "Composante du score global (poids 35 %). "
            "Basé sur la densité de médecins généralistes actifs "
            "pour 100 000 habitants (données RPPS)."
            "<br><br>"
            "Normalisé en rang percentile national. "
            "Score 50 = médiane nationale."
            "<br><br>"
            "<strong>Limite :</strong> inclut tous modes d'exercice. "
            "L'APL reste l'indicateur d'accès réel de référence."
        ),
    },
    "score_etabs": {
        "title": "Score établissements de santé",
        "body": (
            "Composante du score global (poids 30 %). "
            "Basé sur la densité d'hôpitaux et cliniques FINESS agréés "
            "pour 100 000 habitants."
            "<br><br>"
            "Normalisé en rang percentile national. "
            "Score 50 = médiane nationale."
            "<br><br>"
            "<strong>Limite :</strong> comptabilise la présence "
            "d'établissements, pas leur capacité ni leur spécialité."
        ),
    },
    "recommandation": {
        "title": "Recommandations Sant'active",
        "body": (
            "Orientations générées automatiquement à partir du diagnostic "
            "territorial et de la typologie du département (urbain dense, "
            "péri-urbain, rural, etc.)."
            "<br><br>"
            "Les recommandations sont pondérées par priorité :"
            "<br>• Priorité 1 : levier d'action immédiat"
            "<br>• Priorité 2 : levier d'action complémentaire"
            "<br><br>"
            "<strong>⚠ Ces recommandations sont indicatives.</strong> "
            "Elles ne constituent pas une évaluation de politique publique "
            "et ne doivent pas être utilisées seules pour allouer "
            "des ressources."
        ),
    },
}


def info_tooltip(key: str, size: int = 14) -> str:
    """Génère le HTML d'une icône ⓘ avec tooltip CSS pur au survol.

    Utilise exclusivement CSS (:hover) — compatible avec st.markdown()
    qui bloque tout JavaScript pour des raisons de sécurité.

    Args:
        key  : clé dans le dictionnaire TOOLTIPS
        size : taille de l'icône en px (défaut 14)

    Returns:
        str : HTML inline à injecter via st.markdown(unsafe_allow_html=True)

    Usage:
        st.markdown(f"APL {info_tooltip('apl')}", unsafe_allow_html=True)
    """
    tip = TOOLTIPS.get(key)
    if not tip:
        return ""

    title = tip["title"]
    body  = tip["body"]

    return (
        f'<span class="sa-tip">'
        f'<span class="sa-tip-icon" style="font-size:{size - 2}px;">'
        f'ⓘ'
        f'</span>'
        f'<span class="sa-tip-box">'
        f'<strong class="sa-tip-title">{title}</strong>'
        f'<span class="sa-tip-body">{body}</span>'
        f'</span>'
        f'</span>'
    )
