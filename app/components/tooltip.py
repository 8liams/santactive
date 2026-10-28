"""Composant tooltip informatif réutilisable.

Usage :
    from ..components.tooltip import info_tooltip

    st.markdown(
        f'APL {info_tooltip("apl")}',
        unsafe_allow_html=True
    )
"""
from __future__ import annotations

from ..config import APL_AGREGATION

# ── Dictionnaire centralisé de toutes les définitions ────────────────────────
TOOLTIPS: dict[str, dict[str, str]] = {
    "apl": {
        "title": "APL : Accessibilité Potentielle Localisée",
        "body": (
            "Mesure le nombre de consultations disponibles par an "
            "et par habitant, en tenant compte du nombre de médecins "
            "actifs dans un rayon de 20-30 min, de leur volume d'activité "
            "réel, et de la demande locale pondérée par l'âge des habitants."
            "<br><br>"
            "<strong>Repère 2,5 :</strong> un APL inférieur à 2,5 consultations "
            "par an et par habitant est le repère de sous-densité utilisé dans "
            "la méthodologie nationale de zonage des médecins généralistes. "
            "Il s'applique à des territoires (communes, territoires de vie-santé), "
            "pas à un département entier."
            "<br><br>"
            "<strong>Dans Sant'active :</strong> la valeur départementale est la "
            + APL_AGREGATION + "."
            "<br><br>"
            "<strong>Source :</strong> ANCT / Observatoire des territoires · "
            "Millésime 2023"
        ),
    },
    "score_global": {
        "title": "Score global Sant'active",
        "body": (
            "Indicateur synthétique sur 100 calculé à partir de "
            "<strong>6 dimensions pondérées</strong>."
            "<br><br>"
            "<strong>• Accessibilité aux soins :</strong>"
            "<br>APL (30 %) + temps d'accès médian (20 %)"
            "<br><br>"
            "<strong>• Offre médicale :</strong>"
            "<br>médecins généralistes (20 %) + structures de soins (15 %)"
            "<br><br>"
            "<strong>• Contexte territorial :</strong>"
            "<br>part des 65 ans et plus (10 %) + prix immobilier (5 %)"
            "<br><br>"
            "Chaque dimension est convertie en rang percentile national."
            "<br>Un score de 50 correspond à la médiane nationale."
            "<br>Le score est calculé uniquement si au moins 3 dimensions "
            "sont disponibles."
            "<br><br>"
            "<strong>Source :</strong> calcul Sant'active v2 · INSEE · ANCT · "
            "RPPS · FINESS · DVF"
        ),
    },
    "temps_acces": {
        "title": "Temps d'accès à un médecin généraliste",
        "body": (
            "<strong>Repère INSEE 2025</strong> : pour chaque carreau habité de 200 m, "
            "durée en voiture vers le médecin généraliste le plus proche (lieu d'exercice "
            "réel, base permanente des équipements ; distancier Metric-OSRM). Part de la "
            "population à plus de 15 min, médiane pondérée par la population. Guadeloupe, "
            "Guyane et Mayotte sont hors champ."
            "<br><br>"
            "<strong>Dimension du score (20 %)</strong> : indicateur interne historique, "
            "médiane des communes du temps vers la commune équipée la plus proche (0 = "
            "généraliste présent dans la commune). La bascule du score vers le repère INSEE "
            "est préparée (analyse de sensibilité) et soumise à validation."
            "<br><br>"
            "Accessibilité géographique seulement : ni capacité des cabinets, ni délais de rendez-vous."
        ),
    },
    "med_100k": {
        "title": "Médecins généralistes / 100 000 habitants",
        "body": (
            "Nombre de médecins généralistes recensés pour 100 000 habitants, "
            "d'après le fichier des professionnels de santé retraité par "
            "l'équipe (une ligne par lieu d'exercice recensé)."
            "<br><br>"
            "<strong>⚠ Attention :</strong> un praticien exerçant sur "
            "plusieurs lieux peut être compté plusieurs fois, et la "
            "couverture des grandes villes est à vérifier. Indicateur à "
            "lire avec l'APL, qui mesure l'accessibilité aux généralistes."
            "<br><br>"
            "<strong>Source :</strong> données professionnels de santé "
            "retraitées · 2026"
        ),
    },
    "delais_rdv": {
        "title": "Estimation des délais de RDV",
        "body": (
            "Estimation calculée en deux étapes :"
            "<br>1. Base nationale réelle : enquête DREES 2016-2017 "
            "(40 000 personnes, 9 spécialités)"
            "<br>2. Ajustement par l'APL du département : "
            "délai estimé = délai national × (APL national médian / APL dept)"
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
            "par terciles réels sur les 100 départements analysés "
            "(Mayotte exclue faute de données de population) :"
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
            "Prévalence brute par pathologie : part des assurés du "
            "département pris en charge pour cette pathologie, d'après la "
            "consommation de soins remboursée par l'Assurance Maladie."
            "<br><br>"
            "<strong>⚠ Non standardisée sur l'âge :</strong> un département "
            "âgé a mécaniquement des prévalences plus élevées. Les comparaisons "
            "entre départements reflètent en partie la structure par âge."
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
        "title": "Classement national",
        "body": (
            "Position du département dans le classement national par score "
            "global Sant'active."
            "<br><br>"
            "<strong>1er</strong> = meilleure situation relative du pays. "
            "Un rang élevé (ex. 85ème) indique une position plus basse "
            "dans le classement."
            "<br><br>"
            "Le classement évolue si de nouvelles données sont intégrées."
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
        "title": "Accessibilité aux soins",
        "body": (
            "Sous-score d'accessibilité aux soins."
            "<br><br>"
            "Combine :"
            "<br>• APL (accessibilité potentielle localisée)"
            "<br>• Temps d'accès médian aux établissements de santé"
            "<br><br>"
            "Ce sous-score facilite la lecture du diagnostic mais ne "
            "constitue pas à lui seul le score global Sant'active."
        ),
    },
    "score_pros": {
        "title": "Offre médicale",
        "body": (
            "Sous-score de présence médicale."
            "<br><br>"
            "Basé sur la densité de médecins généralistes pour "
            "100 000 habitants."
            "<br><br>"
            "Ce sous-score facilite la lecture du diagnostic mais ne "
            "constitue pas à lui seul le score global Sant'active."
        ),
    },
    "score_etabs": {
        "title": "Structures de soins",
        "body": (
            "Sous-score d'offre de soins."
            "<br><br>"
            "Basé sur la densité d'établissements et structures de santé "
            "pour 100 000 habitants."
            "<br><br>"
            "Ce sous-score facilite la lecture du diagnostic mais ne "
            "constitue pas à lui seul le score global Sant'active."
        ),
    },
    "recommandation": {
        "title": "Recommandations Sant'active",
        "body": (
            "Orientations générées automatiquement à partir du diagnostic "
            "territorial et de la typologie du département (urbain dense, "
            "péri-urbain, rural, etc.)."
            "<br><br>"
            "Chaque piste est qualifiée par un niveau métier :"
            "<br>• Urgence forte : signal territorial marqué"
            "<br>• Prioritaire : levier cohérent avec le diagnostic"
            "<br>• Complémentaire : piste de soutien ou de vigilance"
            "<br><br>"
            "L'ordre d'affichage ne constitue pas un plan de mise en œuvre."
            "<br><br>"
            "<strong>⚠ Ces recommandations sont indicatives.</strong> "
            "Elles ne constituent pas une évaluation de politique publique "
            "et ne doivent pas être utilisées seules pour allouer "
            "des ressources."
        ),
    },
}


def info_tooltip(key: str, size: int = 14, *, open_dir: str = "auto") -> str:
    """Génère le HTML d'une icône ⓘ avec tooltip CSS pur au survol.

    Utilise exclusivement CSS (:hover) — compatible avec st.markdown()
    qui bloque tout JavaScript pour des raisons de sécurité.

    Args:
        key  : clé dans le dictionnaire TOOLTIPS
        size     : taille de l'icône en px (défaut 14)
        open_dir : « right » force l'ouverture vers la droite (évite la sidebar)

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
    dir_class = " sa-tip--open-right" if open_dir == "right" else ""

    return (
        f'<span class="sa-tip{dir_class}" tabindex="0" role="button" aria-label="Définition : {title}">'
        f'<span class="sa-tip-icon" style="font-size:{size - 2}px;">'
        f'ⓘ'
        f'</span>'
        f'<span class="sa-tip-box">'
        f'<strong class="sa-tip-title">{title}</strong>'
        f'<span class="sa-tip-body">{body}</span>'
        f'</span>'
        f'</span>'
    )
