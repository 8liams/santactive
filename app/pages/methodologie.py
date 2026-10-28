"""Page Méthodologie — décrit exactement ce que le code exécute (sources, millésimes,
calculs, options actives, limites). Les paramètres actifs sont lus dans app/config.py.
"""

from __future__ import annotations

import streamlit as st

from ..components.nav import NavCrumb, internal_href, render_breadcrumb
from ..components.tooltip import info_tooltip


# ── Helpers HTML ──────────────────────────────────────────────────────────────

def _section(eyebrow: str, title: str, lead: str = "") -> None:
    lead_html = f'<p class="section-lead">{lead}</p>' if lead else ""
    st.markdown(
        f'<div class="section-header">'
        f'<div class="section-eyebrow">{eyebrow}</div>'
        f'<h2 class="section-title">{title}</h2>'
        f'{lead_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _prose(*paragraphs: str) -> None:
    html = "".join(f"<p>{p}</p>" for p in paragraphs)
    st.markdown(f'<div class="method-content">{html}</div>', unsafe_allow_html=True)


def _hr() -> None:
    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>", unsafe_allow_html=True)


def _encadre(titre: str, corps: str) -> None:
    st.markdown(
        '<div style="max-width:760px;padding:16px 20px;background:#F3F2EC;border-radius:6px;font-size:13px;'
        'color:#4B4B48;line-height:1.7;margin-bottom:28px;">'
        f'<strong style="color:#0A1938;display:block;margin-bottom:8px;">{titre}</strong>{corps}</div>',
        unsafe_allow_html=True)


def _table(headers: list[str], rows: list[list[str]]) -> None:
    th = "".join(f"<th>{h}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f'<div class="sa-tbl-scroll"><table class="sources-table"><thead><tr>{th}</tr></thead>'
                f'<tbody>{tr}</tbody></table></div>', unsafe_allow_html=True)


_ROW = ('<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;'
        'background:{bg};gap:0;align-items:start;">'
        '<div><div style="font-size:13px;font-weight:700;color:#0A1938;">{dim}</div>'
        '<div style="font-size:11px;color:#9C9A92;margin-top:3px;">{sous}</div></div>'
        '<div style="font-size:22px;font-weight:300;color:#1A3D8F;">{poids}</div>'
        '<div style="font-size:12px;color:#4B4B48;line-height:1.5;">{texte}</div>'
        '<div style="font-size:12px;color:#2B2B2B;font-weight:600;">{sens}</div></div>')


def _cfg() -> dict:
    """Paramètres actifs du moteur, pour que la page décrive ce qui est exécuté."""
    from ..config import (APL_AGREGATION, APL_LABEL, APL_METHODE, ETABS_CATEGORIES,
                          ETABS_DEFINITION, SOURCE_EFFECTIFS, TEMPS_SOURCE)
    return dict(apl_methode=APL_METHODE, apl_label=APL_LABEL, apl_agregation=APL_AGREGATION,
                etabs_def=ETABS_DEFINITION, etabs_cats=ETABS_CATEGORIES[ETABS_DEFINITION],
                source=SOURCE_EFFECTIFS, temps=TEMPS_SOURCE)


def render(data: dict) -> None:
    cfg = _cfg()
    master = data.get("master")
    apl_nat = float(master["apl_dept"].median()) if master is not None and "apl_dept" in master else float("nan")
    nb_scores = int(master["score_global"].notna().sum()) if master is not None else 100
    try:
        from .acces_ign import pilotes_disponibles
        pilotes = pilotes_disponibles()
    except Exception:
        pilotes = {}

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Méthodologie")], key_prefix="methodo_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">RESSOURCE</span>'
        '<span class="dot"></span><span class="region">Transparence &amp; sources</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Méthodologie</h1></div>'
        '<p class="fiche-header-lead">Ce que Sant’active calcule, à partir de quelles données, avec quelles limites. '
        'Cette page décrit la version du moteur réellement exécutée : les options actives y sont lues dans la configuration.</p>'
        '</div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 1. TROIS NIVEAUX DE DONNÉES
    # ══════════════════════════════════════════════════════════════════════════
    _section("PRÉSENTATION", "Trois niveaux de données, <em>clairement distingués.</em>",
             lead="Sant’active est un outil d’aide à la décision pour les ARS, les collectivités et les professionnels : "
                  "il synthétise des signaux publics, il ne mesure pas l’accès effectif aux soins.")
    _table(["Niveau", "Ce que c’est", "Exemples dans l’outil"], [
        ["<strong>Données officielles</strong>", "Publiées telles quelles par un producteur public, reprises sans transformation autre qu’une agrégation documentée",
         "APL communal (DREES), effectifs RPPS (DREES), population et âges (INSEE), temps d’accès par carreau (INSEE), prévalences (CNAM), FINESS, DVF"],
        ["<strong>Données retraitées</strong>", "Agrégats ou croisements calculés par Sant’active à partir des données officielles, méthode indiquée",
         "APL départemental pondéré, part de population à plus de 15 min, densités pour 100 000 habitants, prévalences standardisées"],
        ["<strong>Indicateurs Sant’active</strong>", "Constructions propres à l’outil : conventions et pondérations explicites, non officielles",
         "Score global, zones, indices offre × besoins, priorité d’action communale, catalogue de leviers, simulation d’implantation"],
    ])
    _encadre("Trois notions d’accès, jamais interchangeables",
             "<strong>Accessibilité géographique</strong> : temps nécessaire pour rejoindre une offre (INSEE, IGN). "
             "<strong>Accessibilité potentielle</strong> : offre disponible rapportée aux besoins, pondérée par la distance (APL, DREES). "
             "<strong>Accès effectif</strong> : obtenir un rendez-vous dans un délai raisonnable — aucune source publique ne le mesure à la "
             "maille départementale ; Sant’active ne l’estime qu’à titre indicatif (délais) et le dit.")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 2. SCORE GLOBAL
    # ══════════════════════════════════════════════════════════════════════════
    _section("SCORING", "Comment on calcule <em>le score global.</em>",
             lead=f"Indice composite sur 100, six dimensions, {nb_scores} départements classés (Mayotte hors score : "
                  "APL et plusieurs sources ne la couvrent pas).")
    _prose(
        "Chaque indicateur est normalisé en <strong>rang percentile</strong> parmi les départements analysés : 50 = médiane, "
        "100 = le mieux placé, 0 = le moins bien placé. Cette normalisation est insensible aux valeurs extrêmes (Paris, Guyane).",
        "Le score global est la <strong>moyenne pondérée des dimensions disponibles</strong> ; si une dimension manque, son poids est "
        "redistribué sur les autres. Un département avec moins de trois dimensions n’a pas de score. Les zones critique, "
        "intermédiaire et favorable sont les <strong>terciles</strong> de ce classement (33 / 34 / 33 départements par construction) : "
        "elles situent un territoire, elles ne mesurent pas une évolution et ne constituent pas une classification officielle.",
    )
    apl_ligne = {
        "ponderee": "APL moyen pondéré par la population standardisée (méthode DREES)",
        "mediane": "Médiane simple des APL communaux (chaque commune pèse autant)",
    }[cfg["apl_methode"]]
    med_ligne = {
        "drees": "Généralistes actifs au 1<sup>er</sup> janvier 2026 (personnes, tous modes d’exercice) / population INSEE 2021 × 100&#8239;000<br><span style=\"color:#9C9A92;\">DREES · RPPS · 2026</span>",
        "equipe": "Lignes du fichier territorial de l’équipe (présences, pas effectifs) / population INSEE 2021 — mode historique de comparaison",
    }[cfg["source"]]
    etabs_ligne = {
        "actuelle": "Sites FINESS : centres hospitaliers (CH, CHR) + établissements privés SSR, pour 100&#8239;000 hab.",
        "court_sejour": "Sites FINESS de court séjour : CH, CHR, hôpitaux locaux, privés MCO, centres de lutte contre le cancer, pour 100&#8239;000 hab.",
    }[cfg["etabs_def"]]
    temps_ligne = {
        "interne": "<strong>Mode actif : indicateur interne.</strong> Médiane des communes du temps vers la commune équipée la plus proche "
                   "(0 = généraliste présent dans la commune).<br><span style=\"color:#9C9A92;\">Fichier de l’équipe · 2026 · méthode de production non documentée</span>",
        "insee": "<strong>Mode actif : INSEE.</strong> Médiane pondérée par la population du temps en voiture vers le généraliste le plus proche "
                 "(carreaux de 200 m).<br><span style=\"color:#9C9A92;\">Insee · BPE 2025 · Metric-OSRM · hors Guadeloupe, Guyane, Mayotte</span>",
    }[cfg["temps"]]
    rows = [
        ("Accessibilité soins de ville", "Dimension principale", "30 %", apl_ligne + '<br><span style="color:#9C9A92;">DREES · APL aux médecins généralistes · 2023</span>', "Haut = bon"),
        ("Accessibilité physique", "Temps de trajet", "20 %", temps_ligne, "Bas = bon"),
        ("Densité médecins généralistes", "Offre professionnelle", "20 %", med_ligne, "Haut = bon"),
        ("Offre hospitalière", "Structures de soins", "15 %", etabs_ligne + '<br><span style="color:#9C9A92;">FINESS · mars 2026 · nombre de sites, pas de capacité</span>', "Haut = bon"),
        ("Pression démographique", "Vieillissement", "10 %", 'Part des 65 ans et plus<br><span style="color:#9C9A92;">INSEE · Recensement 2021</span>', "Bas = bon"),
        ("Contexte foncier", "Attractivité à l’installation", "5 %", 'Prix médian au m²<br><span style="color:#9C9A92;">DVF · DGFiP · 2025</span>', "Bas = bon"),
    ]
    head = ('<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;background:#0A1938;padding:12px 20px;">'
            + "".join(f'<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.5);">{h}</div>'
                      for h in ("DIMENSION", "POIDS", "INDICATEUR · SOURCE · MILLÉSIME", "DIRECTION")) + '</div>')
    body = "".join(_ROW.format(bg="white" if i % 2 == 0 else "#FAFAF8", dim=d, sous=s_, poids=w, texte=t, sens=se)
                   for i, (d, s_, w, t, se) in enumerate(rows))
    st.markdown(f'<div style="border:1px solid #E8E6DD;border-radius:6px;overflow:hidden;margin-bottom:28px;">{head}{body}</div>',
                unsafe_allow_html=True)
    _encadre("Pondérations : transparentes, discutables, inchangées sans validation",
             "L’APL (30 %), la densité de généralistes (20 %) et le temps d’accès (20 %) mesurent trois facettes d’une même réalité, "
             "l’offre de médecine générale : le score est d’abord un indice d’offre et d’accès ; les besoins (vieillissement, pathologies) "
             "n’y pèsent que 10 %. Les analyses de sensibilité (pondérations, indices complémentaires, source du temps d’accès) sont "
             "documentées dans le dépôt (scripts/analyse) ; <strong>aucune pondération ni source du score n’est modifiée sans validation explicite</strong>.")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 3. APL
    # ══════════════════════════════════════════════════════════════════════════
    _section("APL : ACCESSIBILITÉ POTENTIELLE LOCALISÉE", f'L’indicateur de référence {info_tooltip("apl")} <em>de la DREES.</em>')
    _prose(
        "L’APL (DREES / IRDES, 2012) exprime le nombre de consultations, visites et téléconsultations de médecine générale accessibles "
        "par an et par habitant standardisé, en combinant l’offre (généralistes libéraux et salariés de centres de santé, pondérés par "
        "leur activité), la demande (population pondérée par l’âge) et la distance (influence décroissante des communes voisines).",
        "<strong>Repère 2,5</strong> : seuil de sous-densité de la méthodologie nationale de zonage des généralistes. Il s’applique à des "
        "communes ou territoires de vie-santé ; il n’existe pas de définition légale du « désert médical ».",
        f"<strong>Agrégation départementale active : {cfg['apl_agregation']}</strong> — pondération prescrite par la DREES pour tout APL agrégé. "
        "Lectures complémentaires sur chaque fiche : part de population sous 2,5, quartiles communaux pondérés, nombre de communes sous 2,5.",
        f"Référence nationale affichée : médiane des {nb_scores} valeurs départementales ({apl_nat:.2f}). APL national pondéré DREES 2023 : 3,74 ; "
        "16,6 % de la population vit dans une commune sous 2,5 (11,2 millions d’habitants, recalcul direct sur le fichier communal).",
        "<strong>Millésime 2024 disponible.</strong> La DREES a publié l’APL 2024 (34 890 communes, population 2022) : APL national 3,72, "
        "18,2 % de la population sous 2,5 ; à l’échelle des départements, le classement est très stable (écart de rang médian 2, "
        "4 départements bougent de 10 rangs ou plus ; baisse la plus forte en Lozère, hausse la plus forte à Paris). Le millésime 2023 "
        "reste celui du score tant que la bascule n’a pas été validée ; le fichier 2024 est calculé et prêt "
        "(data_corrections/references/drees/apl_mg_departemental_2024.csv).",
        "Source : DREES, « Accessibilité potentielle localisée aux professionnels de santé », millésimes 2022–2024, France hors Mayotte, "
        "Licence Ouverte 2.0.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 4. TEMPS D'ACCÈS
    # ══════════════════════════════════════════════════════════════════════════
    _section("TEMPS D’ACCÈS", "Deux indicateurs, <em>un seul dans le score.</em>",
             lead="L’audit d’octobre 2026 a établi ce que mesure l’indicateur interne et introduit la mesure officielle de l’INSEE.")
    _table(["", "Indicateur interne (fichier équipe)", "Repère INSEE 2025"], [
        ["Ce qui est mesuré", "Par commune : 0 si un généraliste y est recensé, sinon minutes vers la commune équipée la plus proche",
         "Par carreau habité de 200 m : minutes en voiture vers le lieu d’exercice du généraliste le plus proche"],
        ["Source de l’offre", "Fichier « professionnels » de l’équipe (présences par code postal)", "Base permanente des équipements 2025 (BPE, type D265)"],
        ["Distancier", "Non documenté", "Metric-OSRM (réseau OpenStreetMap 2022), 3 candidats à vol d’oiseau, durée minimale 1 min"],
        ["Population", "Aucune (médiane simple des communes)", "Population carroyée Filosofi, agrégée par commune et département"],
        ["Champ", "34 863 communes ; 25,5 % à 0 ; 1 241 communes à plus de 15 min",
         "34 833 communes, 64,1 M d’habitants localisés ; hors Guadeloupe, Guyane, Mayotte"],
        ["Résultat national", "Médiane des départements : 6 min", "0,8 % de la population à plus de 15 min d’un généraliste (514 000 habitants), 0,18 % à plus de 20 min"],
        ["Usage dans l’outil", "Dimension « temps » du score (mode interne, actif par défaut)",
         "Diagnostics (accueil, fiches, comparaison, PDF), lecture communale, situation actuelle du simulateur ; dimension du score en mode insee"],
    ])
    _prose(
        "<strong>Ce que l’audit a montré.</strong> Les zéros de l’indicateur interne ne sont pas des temps nuls mais une présence : sur les "
        "communes appariées, 2 581 des 2 642 communes à 0 ont bien un généraliste dans la BPE 2025 (61 exceptions). Pour les autres communes, "
        "les deux mesures sont cohérentes (corrélation de Spearman 0,87), mais l’indicateur interne sous-compte les communes éloignées "
        "(par exemple 5 contre 30 en Saône-et-Loire, 13 contre 31 dans la Nièvre) et il ignore la population. Le chiffre de « 98,8 % de communes à "
        "zéro » qui circulait dans un bilan antérieur était erroné.",
        f"<strong>Conséquences sur le score (analyse de sensibilité, scripts/analyse/sensibilite_temps_acces.py).</strong> Remplacer la dimension "
        "« temps » par la médiane INSEE pondérée déplace 20 départements de 10 rangs ou plus et change la zone de 14 d’entre eux (corrélation des "
        "scores 0,97) ; par la part de population à plus de 15 min : 14 départements et 8 changements de zone (corrélation 0,98). Ce n’est pas "
        f"un changement silencieux : le mode actif est « {cfg['temps']} », la bascule se fait par l’option SANTACTIVE_TEMPS_SOURCE après validation.",
        "<strong>Lecture communale.</strong> Sur les fiches, la carte « besoin d’accès » et le classement communal utilisent désormais le temps moyen "
        "INSEE par commune lorsque le département est couvert (repli explicite sur l’indicateur interne sinon, par exemple en Guyane) ; la présence "
        "d’un généraliste vient de la BPE.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 5. SIMULATEUR D'IMPLANTATION
    # ══════════════════════════════════════════════════════════════════════════
    _section("SIMULATEUR D’IMPLANTATION", "Un gain de proximité <em>théorique.</em>",
             lead=(f"{len(pilotes)} départements activés après validation automatique (fichiers carreaux et communes présents, "
                   "population localisée cohérente avec la population municipale, communes appariées, au moins une commune équipée)."
                   if len(pilotes) > 6 else "Pilotes : " + (", ".join(f"{n} ({c})" for c, n in pilotes.items()) if pilotes else "aucun") + "."))
    _prose(
        "<strong>Situation actuelle</strong> : carreaux INSEE 2025 du département (population, durée vers le généraliste le plus proche). "
        "<strong>Scénario</strong> : la nouvelle offre est un point hypothétique de consultation de médecine générale (aucune hypothèse de capacité, "
        "de nombre de médecins ni de rendez-vous), placé à la <strong>mairie</strong> de la commune choisie (API Géo), à défaut au carreau habité le plus "
        "peuplé. Isochrones IGN Géoplateforme (BD TOPO, Valhalla, voiture, 10 / 15 / 20 min) calculées à la demande depuis ce point ; un carreau "
        "contenu dans l’isochrone S passe à ≤ S min. Le simulateur compte les habitants « nouvellement couverts » (au-delà du seuil aujourd’hui, "
        "sous le seuil après) et « rapprochés » (déjà sous le seuil, trajet raccourci).",
        "<strong>Pourquoi la mairie et non le centre géométrique.</strong> Audit du 28 octobre 2026 à Plédéliac (Côtes-d’Armor) : le centroïde "
        "de la commune tombe dans la forêt de la Hunaudaye ; l’isochrone IGN y est raccordée à un chemin et ne couvre que 0,5 km² à 10 min, d’où "
        "un gain affiché à zéro alors que 1 214 habitants de la commune sont à plus de 15 min. Depuis la mairie, l’isochrone 10 min couvre 73 km² "
        "et 1 205 de ces habitants passent sous 15 min. Sur dix communes testées, le point retenu change les gains du simple au décuple "
        "(Lamballe-Armor : 412 ou 29 habitants à 10 min) : la mairie est le choix le plus défendable (dans le bourg, sur le réseau routier). "
        "Une isochrone dégénérée (moins de 2 km² à 10 min, ou aucun carreau de la commune contenu à 15 min) est détectée ; le point de repli "
        "est essayé et, à défaut, le scénario est déclaré indisponible plutôt qu’affiché à zéro.",
        "<strong>Vérification.</strong> L’ancien calcul par itinéraires entre centres de communes (Cher) a été comparé à la mesure INSEE : corrélation "
        "de Spearman 0,43, écart médian +1,8 min, 90ᵉ centile +7,5 min ; il surestimait la population éloignée (21 700 contre 8 100 habitants à plus "
        "de 15 min dans le Cher). Retenir « la plus favorable » de deux mesures IGN non comparables (itinéraire, isochrone) a été abandonné : la "
        "situation actuelle repose sur l’INSEE, les isochrones ne servent qu’au scénario.",
        "<strong>Couverture.</strong> Pipeline reproductible (scripts/donnees/preparer_simulateur.py) : carreaux, zones continues par classe de "
        "temps (union des carreaux, fermeture 300 m, simplification 150 m), communes API Géo (arrondissements pour Paris, Lyon, Marseille), puis "
        "contrôles automatiques (population localisée cohérente avec la population municipale, communes appariées, communes équipées) ; "
        "un département n’est activé que si tous les contrôles passent (static/geo/simulateur_index.json). Guadeloupe, Guyane et Mayotte sont "
        "hors champ de la source INSEE : le simulateur l’indique et ne produit aucun résultat pour eux. Les habitants des départements voisins "
        "ne sont pas comptés dans les gains.",
        "<strong>Limites</strong> : deux distanciers différents (OSRM pour l’existant, Valhalla pour le scénario : à la limite d’une isochrone un carreau "
        "peut basculer à une minute près) ; un seul point par commune pour la nouvelle offre (la mairie) ; capacité, patientèle, "
        "rendez-vous, transports en commun et flux vers les départements voisins non pris en compte. La simulation estime un gain de proximité, "
        "pas un gain de prise en charge.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 6. SOURCES ET MILLÉSIMES
    # ══════════════════════════════════════════════════════════════════════════
    _section("SOURCES", "Les données <em>et leurs millésimes.</em>")
    _table(["Donnée", "Producteur", "Millésime", "Maille", "Usage", "Limite principale"], [
        ["APL aux médecins généralistes", "DREES", "2023 (2024 disponible)", "Commune", "Score (30 %), part sous 2,5, capacité communale, simulation ETP", "Hors Mayotte ; mesure théorique"],
        ["Effectifs de médecins (RPPS)", "DREES", "1<sup>er</sup> janv. 2026", "Département", "Densité de généralistes (20 %), spécialités", "Personnes, pas ETP ; salariés inclus"],
        ["Infirmières libérales (SNDS)", "DREES", "2023", "Département", "Relais de proximité (leviers)", "Libérales seulement"],
        ["Population, âges, densité", "INSEE RP", "2021", "Département", "Dénominateurs, part des 65+ (10 %)", "Décalage avec 2026"],
        ["Accès aux équipements (temps par carreau)", "INSEE, BPE 2025, Metric-OSRM, Filosofi", "2025", "Carreau 200 m → commune, département",
         "Repère temps d’accès, lecture communale, simulateur", "Hors Guadeloupe, Guyane, Mayotte ; routes OSM 2022 ; voiture seulement"],
        ["Établissements (FINESS)", "ATIH / DGOS", "mars 2026", "Site", "Offre hospitalière (15 %), relais", "Sites, pas capacité"],
        ["Pathologies (cartographie)", "CNAM", "2023", "Département × âge", "Besoins (indices, leviers, publics)", "Patients pris en charge, pas besoins non couverts"],
        ["Transactions immobilières (DVF)", "DGFiP", "2025", "Commune, département", "Contexte foncier (5 %), proxy de déploiement communal", "Zones peu denses mal couvertes"],
        ["Délais d’attente (enquête)", "DREES", "2016-2017", "France entière", "Délais indicatifs par spécialité (modulés par l’APL)", "Estimation, pas mesure"],
        ["Isochrones routières", "IGN Géoplateforme (BD TOPO, Valhalla)", "temps réel, cache 24 h", "Point", "Scénario du simulateur", "Centre de commune ; quotas du service"],
        ["Contours et population des communes", "API Géo (Etalab)", "2026", "Commune", "Cartes communales, simulateur (centre, mairie = point d’implantation)", "—"],
        ["Temps d’accès interne", "Équipe Sant’active", "2026", "Commune", "Dimension « temps » du score (mode interne)", "Méthode non documentée ; 0 = présence"],
        ["Professionnels (fichier équipe)", "Équipe Sant’active", "2026", "Code postal", "Présence locale d’une spécialité", "Pas d’effectifs ; lignes démultipliées par code postal"],
        ["Score environnemental", "SPF / DREAL", "variable", "Région", "Information seule", "Hors score"],
    ])
    _prose("Aucun seuil n’est présenté comme une classification officielle en dehors de son usage dans la source : le repère APL 2,5 est "
           "celui du zonage des généralistes ; les seuils de 10, 15, 20 et 30 minutes sont des conventions de lecture de Sant’active ; "
           "les zones du score sont des terciles.")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 7. DÉLAIS
    # ══════════════════════════════════════════════════════════════════════════
    _section("DÉLAIS D’ACCÈS AUX SPÉCIALISTES", f'Une estimation {info_tooltip("delais_rdv")} <em>indicative.</em>')
    _prose(
        "Aucune source publique ne fournit les délais de rendez-vous à la maille départementale. Sant’active part des médianes nationales de "
        "l’enquête DREES « Délais d’attente en matière d’accès aux soins » (2016-2017 : généraliste 2 jours, pédiatre 8, radiologue 11, dentiste 17, "
        "rhumatologue 31, gynécologue 32, cardiologue 37, dermatologue 50, ophtalmologue 52) et les module par le rapport entre l’APL de "
        f"référence ({apl_nat:.2f}) et l’APL du département, plafonné à ×3.",
        "La DREES documente une corrélation entre faible accessibilité et délais plus longs, pas une proportionnalité ; l’APL ne porte que sur les "
        "généralistes. Ces valeurs sont des estimations indicatives et sont présentées comme telles. Les délais régionaux affichés auparavant ont "
        "été retirés (source non identifiable).",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 8. PRIORISATION, INDICES, LEVIERS
    # ══════════════════════════════════════════════════════════════════════════
    _section("PRIORISATION ET RECOMMANDATIONS", "De la mesure <em>à l’action.</em>")
    _prose(
        "<strong>Prioriser (indices offre × besoins, prototype).</strong> Indice d’offre = moyenne pondérée des rangs percentiles de l’APL (30), "
        "des généralistes /100 000 (20), des structures /100 000 (15) et du temps d’accès (20) ; indice de besoins = moyenne à poids égaux des rangs "
        "de la part des 65 ans et plus et des prévalences CNAM standardisées (diabète, cardio-neuro-vasculaire, psychiatrie, respiratoire). "
        "Quadrants définis par les médianes nationales : sensibles pour les départements proches d’un trait. Ces indices n’entrent pas dans le score.",
        "<strong>Fiche région.</strong> Score de priorité de chaque département = moyenne à poids égaux du besoin (fragilité, rangs nationaux) et du "
        "volume (population, publics concernés) ; les conditions de déploiement sont affichées à part et n’entrent pas dans le score. Les "
        "problématiques de santé prioritaires reposent sur des volumes observés (seniors INSEE, patients CNAM), jamais sur des multiplicateurs.",
        "<strong>Priorité d’action communale.</strong> Score 0–100 = besoin d’accès (45 %), population (35 %), conditions de déploiement approchées "
        "par le prix au m² (20 %), en rangs percentiles au sein du département ; les communes où un généraliste est recensé ne sont pas classées "
        "(lecture « capacité » à part, APL communal). Le proxy prix est partiel et nommé comme tel.",
        "<strong>Catalogue de leviers.</strong> Moteur de règles déterministe (app/leviers.py) : chaque levier a des conditions de déclenchement "
        "chiffrées (APL, densités par spécialité, prévalences, part des 65+, communes éloignées, relais présents), des exclusions, un public ciblé, "
        "un horizon et des dispositifs ; le texte cite les valeurs du territoire avec la médiane nationale. Aucune intelligence artificielle "
        "générative n’intervient. Les volumes affichés sont des populations observées, pas des impacts démontrés.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 9. COUVERTURE ET LIMITES
    # ══════════════════════════════════════════════════════════════════════════
    _section("COUVERTURE ET LIMITES", "Ce que Sant’active <em>ne fait pas.</em>")
    limites = [
        ("01", "Couverture", f"Score et diagnostic : {nb_scores} départements (Mayotte hors score). Régions : 17 (Mayotte exclue). Communes : "
                             "lecture partielle (temps INSEE, APL DREES, prix DVF ; pas de données de santé communales). Simulateur : 98 départements (métropole, Martinique, La Réunion)."),
        ("02", "Accès effectif non mesuré", "Ni le temps de trajet, ni l’APL ne disent si un rendez-vous est possible. Les délais affichés sont des estimations."),
        ("03", "Score = offre et accès", "70 % du score mesure l’offre de médecine générale ; les besoins pèsent 10 %. Les indices offre × besoins corrigent cette lecture sans remplacer le score."),
        ("04", "Décalages temporels", "INSEE RP 2021, CNAM 2023, APL 2023 (2024 disponible), BPE 2025, RPPS 2026, FINESS 2026, DVF 2025, délais 2016-2017."),
        ("05", "Outre-mer", "Mayotte hors score ; Guadeloupe, Guyane et Mayotte hors champ de la base INSEE d’accès (repli sur l’indicateur interne) ; "
                            "La Réunion et la Martinique couvertes, y compris par le simulateur."),
        ("06", "Indicateur interne de temps d’accès", "Méthode de production non documentée ; sa bascule vers l’INSEE dans le score est préparée et soumise à validation."),
        ("07", "Simulation", "Gain de proximité théorique : pas de capacité, pas de rendez-vous, pas de flux interdépartementaux ; deux distanciers."),
        ("08", "Priorités et leviers", "Aides à la décision fondées sur des règles transparentes ; elles ne remplacent ni l’expertise locale ni une évaluation de politique publique."),
        ("09", "Capacité théorique (ETP)", "Les ETP de la simulation de capacité convertissent un déficit de consultations sous un seuil d’APL (5 400 actes par ETP, convention DREES) : "
                                           "ni effectif officiel manquant, ni objectif de recrutement."),
    ]
    st.markdown("".join(f'<div class="limit-card"><div class="limit-number">{n}</div><div class="limit-title">{t}</div>'
                        f'<div class="limit-body">{b}</div></div>' for n, t, b in limites), unsafe_allow_html=True)
    _hr()

    st.markdown(
        '<div class="section-header"><div class="section-eyebrow">CONTACT</div>'
        '<h2 class="section-title">Une question, <em>une erreur ?</em></h2>'
        '<p class="section-lead">Sant’active est en développement actif. Signalez toute erreur de données ou incohérence à l’équipe.</p></div>'
        '<div style="margin-top:24px;padding:20px 24px;background:#F3F2EC;border-radius:6px;display:flex;align-items:center;'
        'justify-content:space-between;flex-wrap:wrap;gap:16px;">'
        '<div><div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#6B6B68;margin-bottom:6px;">'
        'CONTACT · QUESTIONS MÉTHODOLOGIQUES</div><div style="font-size:14px;color:#0A1938;">Pour toute question sur les données, les calculs ou la méthodologie :</div></div>'
        '<a href="mailto:santactive.esdata@gmail.com" style="padding:12px 24px;background:#1A3D8F;color:white;border-radius:6px;text-decoration:none;'
        'font-size:14px;font-weight:500;white-space:nowrap;">santactive.esdata@gmail.com</a></div>'
        f'<p class="sa-couverture" style="margin-top:16px;">Documentation technique : docs/EVOLUTIONS_MOTEUR.md, docs/ETAT_DES_LIEUX_DONNEES.md · '
        f'<a href="{internal_href("about")}" target="_self">À propos →</a></p>',
        unsafe_allow_html=True)
