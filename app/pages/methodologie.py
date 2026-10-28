"""Page Méthodologie — lecture institutionnelle d'abord, détails techniques ensuite.

La page décrit la version du moteur réellement exécutée : les options actives
sont lues dans app/config.py. Les détails d'audit sont placés dans des panneaux
dépliables pour ne pas gêner la lecture principale.
"""

from __future__ import annotations

import streamlit as st

from ..components.nav import NavCrumb, internal_href, render_breadcrumb
from ..components.tooltip import info_tooltip


# ── Helpers HTML ──────────────────────────────────────────────────────────────

def _section(eyebrow: str, title: str, lead: str = "") -> None:
    lead_html = f'<p class="section-lead">{lead}</p>' if lead else ""
    st.markdown(f'<div class="section-header"><div class="section-eyebrow">{eyebrow}</div>'
                f'<h2 class="section-title">{title}</h2>{lead_html}</div>', unsafe_allow_html=True)


def _prose(*paragraphs: str) -> None:
    st.markdown('<div class="method-content">' + "".join(f"<p>{p}</p>" for p in paragraphs) + "</div>",
                unsafe_allow_html=True)


def _hr() -> None:
    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:36px 0;'>", unsafe_allow_html=True)


def _encadre(titre: str, corps: str, couleur: str = "#F3F2EC") -> None:
    st.markdown(f'<div style="max-width:820px;padding:16px 20px;background:{couleur};border-radius:6px;font-size:13.5px;'
                f'color:#2B2B2B;line-height:1.65;margin-bottom:22px;">'
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
    from ..config import (APL_AGREGATION, APL_LABEL, APL_METHODE, APL_MILLESIME, ETABS_CATEGORIES,
                          ETABS_DEFINITION, SOURCE_EFFECTIFS, TEMPS_SOURCE)
    return dict(apl_methode=APL_METHODE, apl_label=APL_LABEL, apl_agregation=APL_AGREGATION, apl_millesime=APL_MILLESIME,
                etabs_def=ETABS_DEFINITION, etabs_cats=ETABS_CATEGORIES[ETABS_DEFINITION],
                source=SOURCE_EFFECTIFS, temps=TEMPS_SOURCE)


def _exemple_cher_creuse(master) -> tuple[str, str]:
    """Deux phrases d'exemple calculées sur les valeurs actives (jamais des rangs figés)."""
    try:
        from ..indices import calculer_indices
        from ..scoring import fmt_classement_national
        ind = calculer_indices(master, None)
        o_med, b_med = ind.attrs["medianes"]
        m = master.set_index("dept")
        nb = int(master["score_global"].notna().sum())

        def ligne(code: str) -> str:
            r = m.loc[code]; i = ind.loc[code]
            return (f"<strong>{r['Nom du département']}</strong> : score {float(r['score_global']):.1f}, "
                    f"{fmt_classement_national(r['rang_national'], nb)} sur {nb}, zone {str(r['zone_short']).lower()} ; "
                    f"indice d’offre {float(i['indice_offre']):.0f} (médiane {o_med:.0f}), indice de besoins "
                    f"{float(i['indice_besoins']):.0f} (médiane {b_med:.0f}) → quadrant {i['quadrant']}, "
                    f"« {i['quadrant_label'].lower()} »").replace(".", ",")
        return ligne("18"), ligne("23")
    except Exception:
        return "", ""


def render(data: dict) -> None:
    cfg = _cfg()
    master = data.get("master")
    apl_nat = float(master["apl_dept"].median()) if master is not None and "apl_dept" in master else float("nan")
    nb_scores = int(master["score_global"].notna().sum()) if master is not None else 100
    try:
        from .acces_ign import pilotes_disponibles
        nb_sim = len(pilotes_disponibles())
    except Exception:
        nb_sim = 98
    apl_nat_txt = f"{apl_nat:.2f}".replace(".", ",")

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Méthodologie")], key_prefix="methodo_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">RESSOURCE</span>'
        '<span class="dot"></span><span class="region">Méthode, sources et limites</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Méthodologie</h1></div>'
        '<p class="fiche-header-lead">Ce que Sant’active mesure, ce qu’il ne mesure pas, et comment lire ses résultats. '
        'Les détails de calcul sont accessibles dans des panneaux dépliables ; la page décrit la version du moteur '
        'réellement en service.</p></div>', unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # EN BREF
    # ══════════════════════════════════════════════════════════════════════════
    _section("EN BREF", "Trois questions <em>avant de lire un chiffre.</em>")
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        _encadre("Que mesure Sant’active ?",
                 "L’<strong>offre de soins de premier recours</strong> (généralistes, hôpitaux), son "
                 "<strong>accessibilité</strong> géographique (temps de trajet) et potentielle (APL de la DREES), certains "
                 "<strong>besoins</strong> (vieillissement, pathologies prises en charge), les <strong>vulnérabilités</strong> "
                 "qui en résultent et les <strong>actions</strong> envisageables, pour chaque département, région et, "
                 "partiellement, commune.", "#F7F9FD")
    with c2:
        _encadre("Que ne mesure-t-il pas ?",
                 "La <strong>disponibilité réelle des rendez-vous</strong>, la capacité exacte des cabinets, la qualité des "
                 "soins, l’efficacité future d’une action, l’état de santé global d’une population et la plupart des "
                 "inégalités sociales de santé. Aucun délai de rendez-vous actuel n’est affiché : l’enquête DREES 2016-2017 "
                 "n’est citée qu’à titre historique (section 6).", "#FDF8EC")
    with c3:
        _encadre("Comment lire les résultats ?",
                 "Le <strong>score</strong> situe un département parmi les autres sur l’offre et l’accès. Le "
                 "<strong>diagnostic</strong> explique sa position. Les <strong>indices offre × besoins</strong> disent où "
                 "l’écart entre offre et besoins est le plus préoccupant. Les <strong>leviers</strong> sont des pistes "
                 "issues de règles explicites. Le <strong>simulateur</strong> estime un gain de proximité, pas une prise "
                 "en charge.", "#E3F1E8")
    _prose("Trois notions d’accès, jamais interchangeables : l’<strong>accessibilité géographique</strong> (temps de trajet, "
           "INSEE et IGN), l’<strong>accessibilité potentielle</strong> (offre rapportée aux besoins et à la distance : APL, "
           "DREES) et l’<strong>accès effectif</strong> (obtenir un rendez-vous), qu’aucune source publique ne mesure à "
           "l’échelle départementale.")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 1. SOURCES
    # ══════════════════════════════════════════════════════════════════════════
    _section("1 · SOURCES", "Des données publiques, <em>reprises sans retouche.</em>",
             lead="Sant’active ne produit aucune donnée de santé : il harmonise et croise des sources officielles ouvertes. "
                  "Trois niveaux sont distingués partout : donnée officielle, agrégat calculé par Sant’active, indicateur construit.")
    _table(["Donnée", "Producteur", "Millésime", "Maille", "Usage dans Sant’active", "Limite principale"], [
        ["APL aux médecins généralistes", "DREES", f"{cfg['apl_millesime']}", "Commune", "Score (30 %), part de population sous 2,5, lecture communale « capacité », renforcement théorique (ETP)", "Hors Mayotte ; accessibilité théorique"],
        ["Effectifs de médecins (RPPS)", "DREES", "1<sup>er</sup> janv. 2026", "Département", "Densité de généralistes (20 %), densités de spécialistes (leviers)", "Personnes, pas temps de travail"],
        ["Accès aux équipements : temps vers le généraliste le plus proche", "INSEE (BPE 2025, Metric-OSRM, Filosofi)", "2025", "Carreau de 200 m → commune, département", "Temps d’accès (20 %), part à plus de 15 min, communes éloignées, situation actuelle du simulateur", "Hors Guadeloupe, Guyane, Mayotte ; voiture seulement"],
        ["Population, âges, densité", "INSEE, recensement", "2021", "Département", "Dénominateurs, part des 65 ans et plus (10 %), typologie", "Décalage avec 2026"],
        ["Établissements de santé", "FINESS (ministère chargé de la Santé ; diffusion DREES)", "mars 2026", "Site", "Offre hospitalière (15 %), relais pour les leviers", "Sites, pas lits ni capacités ; cliniques privées de court séjour exclues"],
        ["Pathologies prises en charge", "CNAM (cartographie des pathologies)", "2023", "Département × âge", "Indice de besoins, leviers de prévention, publics", "Patients suivis, pas besoins non couverts"],
        ["Transactions immobilières (DVF)", "DGFiP", "2025", "Commune, département", "Contexte foncier (5 %), proxy communal de conditions d’installation", "Zones peu denses mal couvertes"],
        ["Infirmières libérales (SNDS)", "DREES", "2023", "Département", "Relais de proximité (leviers)", "Libérales seulement"],
        ["Délais d’attente (enquête)", "DREES", "2016-2017", "France entière", "Référence historique (Méthodologie uniquement)", "Plus affichée dans les fiches ni les rapports"],
        ["Isochrones routières", "IGN Géoplateforme (BD TOPO, Valhalla)", "à la demande, cache 24 h", "Point", "Scénario du simulateur", "Un point par commune ; service externe"],
        ["Communes : centre, mairie, population", "API Géo (Etalab)", "2026", "Commune", "Cartes communales, point d’implantation", "—"],
        ["Fichiers de l’équipe (temps d’accès, présences)", "Sant’active", "2026", "Commune, code postal", "Repli pour la Guadeloupe et la Guyane (signalé) ; présence locale d’une spécialité", "Méthode non documentée"],
    ])
    _prose(f"Couverture : score et diagnostic pour {nb_scores} départements (Mayotte hors score), 17 régions, lecture communale "
           f"partielle (temps INSEE, APL, prix), simulateur pour {nb_sim} départements (métropole, Martinique, La Réunion).")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 2. SCORE
    # ══════════════════════════════════════════════════════════════════════════
    _section("2 · LE SCORE SANT’ACTIVE", "Six dimensions, <em>une position relative.</em>",
             lead=f"Indice sur 100 calculé pour {nb_scores} départements. Il situe un département parmi les autres sur l’offre "
                  "et l’accès aux soins de premier recours ; il ne mesure ni l’état de santé, ni une évolution.")
    apl_ligne = {"ponderee": "APL moyen pondéré par la population standardisée (méthode DREES)",
                 "mediane": "Médiane simple des APL communaux"}[cfg["apl_methode"]]
    temps_ligne = {
        "insee": "Médiane, pondérée par la population, du temps en voiture vers le généraliste le plus proche (carreaux de 200 m)"
                 '<br><span style="color:#9C9A92;">INSEE · accès aux équipements 2025 · hors Guadeloupe, Guyane, Mayotte</span>',
        "interne": "Indicateur interne historique (mode d’audit)<br><span style=\"color:#9C9A92;\">fichier de l’équipe</span>",
    }[cfg["temps"]]
    med_ligne = {"drees": "Généralistes en activité (personnes) / population 2021 × 100 000<br><span style=\"color:#9C9A92;\">DREES · RPPS · 1<sup>er</sup> janvier 2026</span>",
                 "equipe": "Lignes du fichier de l’équipe (mode historique)"}[cfg["source"]]
    etabs_ligne = {"actuelle": "Sites FINESS : centres hospitaliers (CH, CHR) et établissements privés de soins de suite et de réadaptation, pour 100 000 habitants. Les cliniques privées de court séjour (MCO) ne sont pas comptées : l’indicateur mesure un maillage de sites, pas l’ensemble de l’offre hospitalière",
                   "court_sejour": "Sites FINESS de court séjour (CH, CHR, hôpitaux locaux, privés MCO, centres de lutte contre le cancer), pour 100 000 habitants"}[cfg["etabs_def"]]
    rows = [
        ("Accessibilité aux soins de ville", "APL", "30 %", apl_ligne + f'<br><span style="color:#9C9A92;">DREES · APL aux médecins généralistes · {cfg["apl_millesime"]}</span>', "Haut = favorable"),
        ("Accessibilité physique", "Temps de trajet", "20 %", temps_ligne, "Bas = favorable"),
        ("Densité de généralistes", "Offre professionnelle", "20 %", med_ligne, "Haut = favorable"),
        ("Offre hospitalière", "Structures de soins", "15 %", etabs_ligne + '<br><span style="color:#9C9A92;">FINESS · mars 2026 · sites, pas capacités</span>', "Haut = favorable"),
        ("Pression démographique", "Vieillissement", "10 %", 'Part des 65 ans et plus<br><span style="color:#9C9A92;">INSEE · recensement 2021</span>', "Bas = favorable"),
        ("Contexte foncier", "Installation", "5 %", 'Prix médian au m²<br><span style="color:#9C9A92;">DVF · DGFiP · 2025</span>', "Bas = favorable"),
    ]
    head = ('<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;background:#0A1938;padding:12px 20px;">'
            + "".join(f'<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.5);">{h}</div>'
                      for h in ("DIMENSION", "POIDS", "INDICATEUR · SOURCE · MILLÉSIME", "SENS")) + '</div>')
    body = "".join(_ROW.format(bg="white" if i % 2 == 0 else "#FAFAF8", dim=d, sous=s_, poids=w, texte=t, sens=se)
                   for i, (d, s_, w, t, se) in enumerate(rows))
    st.markdown(f'<div style="border:1px solid #E8E6DD;border-radius:6px;overflow:hidden;margin-bottom:22px;">{head}{body}</div>',
                unsafe_allow_html=True)
    _prose(
        "<strong>Comment lire le score.</strong> Chaque indicateur est converti en <strong>rang percentile</strong> parmi les "
        "départements analysés (50 = médiane, 100 = le mieux placé). Le score est la moyenne pondérée de ces rangs. Les "
        "départements sont ensuite classés du 1<sup>er</sup> (le mieux placé) au 100<sup>e</sup>, puis répartis en trois "
        "<strong>zones</strong> de taille égale, les terciles : 33 critiques, 34 intermédiaires, 33 favorables, par construction. "
        "Une zone situe un territoire ; elle ne mesure pas une évolution et n’est pas une classification officielle.",
        "<strong>Données manquantes.</strong> Si une dimension manque, son poids est réparti sur les autres ; un département "
        "doit avoir au moins trois dimensions pour recevoir un score. Guadeloupe et Guyane (sans temps INSEE) ont un score "
        "sur cinq dimensions, indiqué sur leur fiche et dans leur PDF. Mayotte n’a pas de score.",
        "<strong>Les pondérations sont un choix méthodologique du projet</strong>, documenté et assumé : elles ne sont pas des "
        "pondérations officielles de la DREES, de l’INSEE ni d’une ARS. L’APL pèse le plus parce qu’elle combine déjà offre, "
        "demande et distance. Les trois premières dimensions décrivent l’offre de médecine générale (70 % du score) : le "
        "score est d’abord un indice d’offre et d’accès ; les besoins sont traités dans la priorisation. Aucune pondération ni "
        "source n’est modifiée sans analyse de sensibilité et validation explicite.",
    )
    with st.expander("Détail du calcul et règles de classement"):
        st.markdown(
            "- Rang percentile : `rang(méthode moyenne) / nombre de départements × 100`, inversé pour les indicateurs où "
            "une valeur basse est favorable (temps, 65 ans et plus, prix).\n"
            "- Score = Σ poids × rang / Σ poids des dimensions disponibles ; arrondi au dixième pour l’affichage.\n"
            "- Classement national calculé sur le score non arrondi ; égalité stricte départagée par le code du département "
            "(rangs uniques de 1 à 100).\n"
            "- Zones : tertiles du score (quantiles 0,333 et 0,667).\n"
            "- Sous-scores de lecture (fiche) : accès aux soins = APL 60 % + temps 40 % ; ils ne modifient pas le score Sant’active.\n"
            "- Typologie territoriale par densité (recensement 2021) : rural jusqu’à 80 hab./km², péri-urbain de 80 à 250, "
            "urbain de 250 à 1 000, urbain dense au-delà ; utilisée par certains leviers."
        )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 3. APL et TEMPS
    # ══════════════════════════════════════════════════════════════════════════
    _section("3 · APL ET TEMPS D’ACCÈS", f"Les deux mesures d’accessibilité {info_tooltip('apl')} <em>et ce qu’elles distinguent.</em>")
    _prose(
        "<strong>L’APL</strong> (DREES) exprime le nombre de consultations de médecine générale accessibles par an et par habitant "
        "en combinant l’offre (généralistes libéraux et salariés de centres de santé, pondérés par leur activité), la demande "
        "(population pondérée par l’âge) et la distance (influence décroissante des communes voisines). Le <strong>repère 2,5</strong> "
        "est le seuil de sous-densité du zonage des généralistes ; il n’existe pas de définition légale du « désert médical ». "
        f"Agrégation départementale : {cfg['apl_agregation']}. Référence nationale affichée : médiane des {nb_scores} valeurs "
        f"départementales ({apl_nat_txt}). Millésime actif : {cfg['apl_millesime']} (18,2 % de la population vit dans une commune "
        "sous 2,5, soit 12,3 millions d’habitants).",
        "<strong>Le temps d’accès</strong> (INSEE 2025) est, pour chaque carreau habité de 200 m, le temps en voiture vers le "
        "cabinet de généraliste le plus proche (lieu d’exercice réel de la base permanente des équipements). Deux lectures : la "
        "<strong>médiane pondérée par la population</strong>, qui entre dans le score, et la <strong>part des habitants à plus de "
        "15 minutes</strong>, repère de fragilité affiché partout (0,8 % en France, 514 000 habitants). Le seuil de 15 minutes est "
        "une convention de lecture de Sant’active.",
        "<strong>Ce que ces mesures ne disent pas.</strong> Un généraliste à cinq minutes peut ne plus accepter de patients : le "
        "temps mesure une distance, l’APL une capacité théorique, aucun des deux une disponibilité effective.",
    )
    with st.expander("Audit et bascule vers l’INSEE 2025 (octobre 2026)"):
        st.markdown(
            "L’indicateur interne historique comptait « 0 » lorsqu’un généraliste était présent dans la commune, sinon les minutes "
            "vers la commune équipée la plus proche, sans pondération par la population. L’audit d’octobre 2026 a montré que ces "
            "zéros étaient des présences (2 581 des 2 642 communes à 0 ont bien un généraliste dans la BPE 2025) et que l’indicateur "
            "sous-comptait les communes éloignées. La dimension « temps » du score utilise désormais la médiane INSEE pondérée "
            "(même grandeur, tous les habitants couverts) ; la part à plus de 15 min reste un repère complémentaire.\n\n"
            "Effet mesuré, à APL constant : corrélation des scores 0,97 ; 20 départements déplacés de 10 rangs ou plus ; 14 changements "
            "de zone ; un département sort des priorités (Aude). Les comptes de communes et d’habitants à plus de 15 min utilisés "
            "par les leviers reposent aussi sur l’INSEE (1 928 communes, 514 254 habitants, contre 1 228 et 219 218 avec l’ancien "
            "fichier) ; les règles des leviers étant inchangées, 13 départements ruraux ont vu leurs leviers de proximité "
            "modifiés. L’ancien indicateur reste disponible pour l’audit et sert de repli, signalé, pour la Guadeloupe et la Guyane. "
            "Détail : docs/EVOLUTIONS_MOTEUR.md, §14 à §19."
        )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 4. PRIORISATION
    # ══════════════════════════════════════════════════════════════════════════
    _section("4 · PRIORISER", "Offre × besoins : <em>où l’écart est-il le plus préoccupant ?</em>",
             lead="Le score mesure surtout l’offre. La page Prioriser ajoute les besoins pour répondre à une autre question : "
                  "où agir en premier.")
    _prose(
        "<strong>Indice d’offre</strong> (0–100, 100 = offre la plus favorable) : rangs percentiles de l’APL (30), des généralistes "
        "pour 100 000 habitants (20), des structures pour 100 000 habitants (15) et du temps d’accès (20) : les poids du score, sans "
        "le foncier ni le vieillissement.",
        "<strong>Indice de besoins</strong> (0–100, 100 = besoins les plus forts) : moyenne à poids égaux des rangs de la part des "
        "65 ans et plus et de quatre prévalences de l’Assurance Maladie <strong>standardisées sur l’âge</strong> (diabète, maladies "
        "cardio-neuro-vasculaires, psychiatriques, respiratoires chroniques). Poids égaux : choix explicite, faute de référence validée.",
        "<strong>Quatre quadrants</strong>, séparés par les médianes nationales des deux indices : A « offre faible, besoins forts » "
        "(à examiner en priorité), B « offre faible, besoins modérés » (enjeu d’accès), C « offre correcte, besoins forts » (enjeu de "
        "prévention et de parcours), D « offre correcte, besoins modérés » (veille). Un département proche d’une médiane peut changer "
        "de quadrant à la prochaine mise à jour : la lecture est indicative. Ces indices n’entrent pas dans le score.",
    )
    ex18, ex23 = _exemple_cher_creuse(master) if master is not None else ("", "")
    if ex18 and ex23:
        _encadre("Pourquoi un département peut être dernier au score sans être en quadrant A",
                 f"{ex18}.<br>{ex23}.<br><br>Le Cher est le département le moins bien doté en offre de médecine générale, "
                 "mais ses besoins sanitaires mesurés sont dans la norme : enjeu d’accès, quadrant B. La Creuse est mieux placée au "
                 "score, mais elle cumule une offre sous la médiane et les besoins les plus forts (population la plus âgée de France) : "
                 "quadrant A. Les deux lectures sont complémentaires ; aucune n’est « la bonne » seule.", "#F7F9FD")
    _prose(
        "<strong>Priorités régionales</strong> (fiche région) : score de priorité 0–100 de chaque département = moyenne à poids égaux "
        "du <strong>besoin</strong> (fragilité et position au score, en rangs nationaux) et du <strong>volume</strong> (population et "
        "publics concernés). Les <strong>conditions de déploiement</strong> (relais hospitaliers, soignants, prix, densité) sont "
        "affichées à part et n’entrent pas dans le score : un département très fragile n’est pas rétrogradé parce qu’il est difficile "
        "d’y intervenir. Une lecture complémentaire croise fragilité, impact et faisabilité pour repérer les candidats à une "
        "expérimentation ; elle est nommée comme telle dans le panneau détaillé.",
        "<strong>Priorité d’action communale</strong> (fiche département) : score 0–100 = besoin d’accès (temps de trajet INSEE, 45 %), "
        "population (35 %), conditions d’installation approchées par le prix au m² (20 %), en rangs au sein du département. Les "
        "communes où un généraliste est recensé sont lues à part, par leur APL (« capacité »). Les publics affichés (seniors, patients "
        "suivis, habitants éloignés) sont des volumes observés, jamais des projections.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 5. LEVIERS
    # ══════════════════════════════════════════════════════════════════════════
    _section("5 · LEVIERS D’ACTION", "Des règles explicites, <em>pas une intelligence artificielle.</em>")
    _prose(
        "Le catalogue compte une vingtaine de leviers correspondant à des dispositifs existants : maisons de santé et exercice "
        "coordonné, attractivité et installation, assistants médicaux, consultations avancées, équipes mobiles, téléconsultation "
        "assistée, transport solidaire, santé mentale, parcours gériatriques, dépistages, prévention des maladies chroniques, "
        "périnatalité…",
        "<strong>Déclenchement.</strong> Chaque levier a des conditions chiffrées (APL, densités par spécialité, prévalences "
        "standardisées, part des 65 ans et plus, communes et habitants à plus de 15 min, relais présents, typologie), certaines "
        "<strong>obligatoires</strong> (par exemple « au moins 3 % de la population à plus de 15 min » pour les équipes mobiles et le "
        "transport solidaire), d’autres contributives, et des <strong>exclusions</strong>. Un levier est retenu si ses conditions "
        "obligatoires sont remplies et qu’au moins un tiers de ses conditions pondérées le sont.",
        "<strong>Sélection.</strong> Au plus <strong>quatre leviers</strong> par département, les mieux appariés, au plus "
        "<strong>deux par famille</strong>. Si aucun levier ne se déclenche, l’outil propose un levier de <strong>maintien</strong> "
        "(veille, anticipation des départs) et signale les poches communales d’éloignement. Le texte cite toujours les valeurs du "
        "territoire et la médiane nationale.",
        "<strong>Limites.</strong> Les leviers sont des pistes à instruire avec les acteurs locaux : ils ne constituent ni une "
        "prescription, ni une évaluation de politique publique, ni une estimation d’impact. Les volumes affichés sont des populations "
        "observées. Aucune intelligence artificielle générative ni apprentissage automatique n’intervient : les règles sont écrites, "
        "relisibles et reproductibles.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 6. CAPACITÉ ET DÉLAIS
    # ══════════════════════════════════════════════════════════════════════════
    _section("6 · CAPACITÉ THÉORIQUE ET DÉLAIS", "Deux estimations, <em>présentées comme telles.</em>")
    _prose(
        "<strong>Renforcement théorique de capacité (ETP).</strong> Un équivalent temps plein est une unité de volume d’activité, "
        "pas une personne. Pour chaque commune sous le repère APL 2,5, Sant’active calcule le nombre de consultations manquantes pour "
        "l’amener au repère (population standardisée × écart à 2,5), additionne ces déficits à l’échelle du département et les "
        "convertit en ETP à raison de 5 400 consultations par an et par ETP (convention DREES de l’indicateur), avec une fourchette "
        "de 3 600 à 6 000. Le résultat est un <strong>ordre de grandeur</strong> : l’offre existante est supposée inchangée et les "
        "effets de voisinage sont ignorés, ce qui tend à surestimer. Ce n’est ni un effectif officiel de médecins manquants, ni un "
        "objectif de recrutement.",
        f"<strong>Délais de rendez-vous (référence historique).</strong> Sant’active partait des délais médians nationaux de l’enquête DREES 2016-2017 "
        "(généraliste 2 jours, pédiatre 8, radiologue 11, dentiste 17, rhumatologue 31, gynécologue 32, cardiologue 37, dermatologue 50, "
        f"ophtalmologue 52) et les modulait par le rapport entre l’APL de référence ({apl_nat_txt}) et l’APL du département, plafonné à ×3. "
        "La DREES documente une corrélation entre faible accessibilité et délais plus longs, pas une proportionnalité. "
        "<strong>Ces valeurs ne sont pas des délais observés en 2026</strong>. Depuis le 28 octobre 2026, cette estimation n’est plus "
        "affichée dans les fiches, les e-mails ni les rapports PDF, afin qu’elle ne soit pas lue comme une situation actuelle ; "
        "elle reste documentée ici, avec sa date et ses limites, et le code de calcul est conservé.",
    )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 7. SIMULATEUR
    # ══════════════════════════════════════════════════════════════════════════
    _section("7 · SIMULATEUR D’IMPLANTATION", "Un gain de proximité <em>théorique.</em>",
             lead=f"{nb_sim} départements (métropole, Martinique, La Réunion), activés après contrôles automatiques de cohérence.")
    _prose(
        "<strong>Situation actuelle</strong> : les carreaux INSEE 2025 du département (population et temps vers le généraliste le plus "
        "proche), regroupés en zones par classe de temps. Seules les zones habitées sont colorées : les espaces blancs n’ont pas "
        "d’habitant, pas de donnée inventée.",
        "<strong>Scénario</strong> : la nouvelle offre est un <strong>point hypothétique</strong> de consultation de médecine générale, "
        "placé à la <strong>mairie</strong> de la commune choisie (dans le bourg, sur le réseau routier), sans hypothèse de capacité, de "
        "nombre de médecins ni de rendez-vous. L’IGN calcule les isochrones à 10, 15 et 20 minutes depuis ce point ; chaque carreau "
        "contenu dans l’isochrone voit son temps ramené sous le seuil. Résultat : habitants <strong>nouvellement couverts</strong> "
        "(au-delà du seuil avant, en deçà après) et <strong>rapprochés</strong> (déjà couverts, trajet raccourci). Trois vues : "
        "situation actuelle, avec la nouvelle offre, gain seulement.",
        "<strong>Limites</strong> : deux distanciers (OSRM pour l’existant, Valhalla pour le scénario : à la limite d’une isochrone, un "
        "carreau peut basculer à une minute près) ; un seul point par commune ; les habitants des départements voisins ne sont pas "
        "comptés ; capacité, patientèle, rendez-vous et transports en commun ne sont pas pris en compte. Un point d’implantation "
        "mal raccordé au réseau est détecté et le scénario déclaré indisponible plutôt qu’affiché à zéro.",
    )
    with st.expander("Vérifications réalisées sur le simulateur"):
        st.markdown(
            "- Point d’implantation : le centroïde d’une commune étendue peut tomber hors du réseau routier (Plédéliac, Côtes-d’Armor : "
            "0,5 km² d’isochrone à 10 min depuis le centroïde, 73 km² depuis la mairie). Sur dix communes testées, le point retenu "
            "change les gains du simple au décuple : la mairie est le choix le plus défendable.\n"
            "- Ancien calcul par itinéraires entre centres de communes (Cher) : corrélation de Spearman 0,43 avec l’INSEE, "
            "surestimation de la population éloignée (21 700 contre 8 100 habitants) ; abandonné.\n"
            "- Pipeline reproductible (scripts/donnees/preparer_simulateur.py) : carreaux, zones, communes, contrôles ; un département "
            "n’est activé que si tous les contrôles passent.\n"
            "- Une carte continue des temps d’accès calculée sur le réseau routier a été expérimentée sur trois départements ; elle est "
            "réservée à une version ultérieure et n’est pas affichée dans cette version."
        )
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 8. LIMITES
    # ══════════════════════════════════════════════════════════════════════════
    _section("8 · LIMITES ET TERRITOIRES PARTICULIERS", "Ce qu’il faut garder en tête.")
    limites = [
        ("01", "Accès effectif non mesuré", "Ni le temps de trajet, ni l’APL ne disent si un rendez-vous est possible. Aucun délai de rendez-vous actuel n’est mesuré ni affiché."),
        ("02", "Score relatif", "Le score situe un département parmi les autres ; 70 % mesure l’offre de médecine générale. Les besoins sont traités dans la priorisation."),
        ("03", "Décalages de millésimes", f"Recensement 2021, CNAM 2023, APL {cfg['apl_millesime']}, BPE et temps 2025, RPPS et FINESS 2026, DVF 2025, délais 2016-2017."),
        ("04", "Outre-mer", "Mayotte hors score. Guadeloupe et Guyane sans temps INSEE : score sur cinq dimensions, lecture communale et leviers de proximité en repli sur l’indicateur interne, signalé. Simulateur indisponible pour ces trois territoires ; La Réunion et la Martinique couvertes."),
        ("05", "Simulation", "Gain de proximité théorique : pas de capacité, pas de rendez-vous, pas de flux interdépartementaux, deux distanciers."),
        ("06", "Priorités et leviers", "Règles transparentes qui ne remplacent ni l’expertise locale ni une évaluation de politique publique."),
        ("07", "Inégalités sociales", "Aucune donnée de revenu, de précarité ou de renoncement aux soins n’entre dans l’outil."),
        ("08", "Synthèse vocale", "La lecture audio d’un diagnostic utilise un service externe de synthèse vocale (Microsoft, via la bibliothèque edge-tts) : le texte du diagnostic est transmis à ce service au moment de la génération. Aucune donnée personnelle n’est concernée ; la fonction est facultative."),
    ]
    st.markdown("".join(f'<div class="limit-card"><div class="limit-number">{n}</div><div class="limit-title">{t}</div>'
                        f'<div class="limit-body">{b}</div></div>' for n, t, b in limites), unsafe_allow_html=True)
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 9. GLOSSAIRE
    # ══════════════════════════════════════════════════════════════════════════
    _section("9 · GLOSSAIRE", "Les termes <em>en une phrase.</em>")
    _table(["Terme", "Définition"], [
        ["APL", "Accessibilité potentielle localisée (DREES) : consultations de médecine générale accessibles par an et par habitant, pondérées par l’activité des médecins, l’âge de la population et la distance."],
        ["RPPS", "Répertoire partagé des professionnels de santé : effectifs officiels des médecins en activité."],
        ["FINESS", "Fichier national des établissements sanitaires et sociaux : sites d’établissements de santé."],
        ["INSEE", "Institut national de la statistique et des études économiques : recensement, population, accès aux équipements."],
        ["BPE", "Base permanente des équipements (INSEE) : localisation des équipements, dont les cabinets de médecins généralistes."],
        ["Carroyage", "Découpage du territoire habité en carreaux de 200 m, pour lesquels l’INSEE connaît la population et le temps d’accès."],
        ["Isochrone", "Zone atteignable en un temps donné depuis un point, par la route."],
        ["OSRM / Valhalla", "Deux moteurs de calcul d’itinéraires routiers : OSRM pour les temps INSEE, Valhalla pour les isochrones IGN."],
        ["Rang percentile", "Position d’un département parmi les 100, ramenée sur 100 (50 = médiane)."],
        ["Tercile", "Chacun des trois groupes de taille égale d’un classement : zones critique, intermédiaire, favorable."],
        ["Médiane pondérée", "Valeur telle que la moitié des habitants se situe en dessous."],
        ["Standardisation sur l’âge", "Recalcul d’une prévalence comme si tous les départements avaient la même pyramide des âges, pour les comparer à âge égal."],
        ["ETP", "Équivalent temps plein : unité de volume d’activité (5 400 consultations par an dans la convention DREES), pas une personne."],
        ["Prévalence", "Part des assurés pris en charge pour une pathologie (CNAM)."],
    ])
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 10. HISTORIQUE
    # ══════════════════════════════════════════════════════════════════════════
    _section("10 · HISTORIQUE DES CHANGEMENTS DE MÉTHODE", "Datés et <em>justifiés.</em>",
             lead="Aucune pondération ni source du score n’est modifiée sans analyse de sensibilité et validation explicite.")
    _table(["Date", "Changement", "Justification", "Effet mesuré"], [
        ["28 oct. 2026", "Temps d’accès du score : médiane INSEE 2025 pondérée par la population (remplace l’indicateur interne)",
         "Source officielle et documentée, pondération par les habitants", "Corrélation des scores 0,97 ; 14 changements de zone ; Aude sort des priorités"],
        ["28 oct. 2026", "APL : millésime 2024 (remplace 2023)", "Millésime le plus récent, définition inchangée", "Corrélation 0,99 ; 4 changements de zone ; Vosges sort des priorités"],
        ["28 oct. 2026", "Communes et habitants à plus de 15 min, secteurs des leviers : INSEE 2025 ; seuils régionaux relatifs",
         "Une seule source de temps dans les diagnostics", "Leviers de proximité modifiés dans 13 départements ruraux"],
        ["oct. 2026", "APL départemental : moyenne pondérée par la population standardisée (méthode DREES)", "Consigne DREES pour tout APL agrégé", "Documenté dans docs/EVOLUTIONS_MOTEUR.md"],
        ["oct. 2026", "Densité de généralistes : effectifs DREES/RPPS 2026", "Effectifs de personnes plutôt que présences", "Idem"],
    ])
    with st.expander("Détails d’audit (comparaisons techniques)"):
        st.markdown(
            "- Les deux changements de source réunis : corrélation 0,966 avec l’ancien score ; 18 départements déplacés de 10 rangs "
            "ou plus ; 14 changements de zone ; 25 départements prioritaires contre 27.\n"
            "- Les anciens indicateurs restent calculés et disponibles pour l’audit (colonnes historiques, fichiers 2023, options "
            "d’environnement) ; ils ne sont plus présentés comme actifs.\n"
            "- Scripts : scripts/analyse/audit_migration_score.py, scripts/analyse/sensibilite_temps_acces.py."
        )
    _hr()

    st.markdown(
        '<div class="section-header"><div class="section-eyebrow">CONTACT</div>'
        '<h2 class="section-title">Une question, <em>une erreur ?</em></h2>'
        '<p class="section-lead">Signalez toute erreur de données ou incohérence à l’équipe.</p></div>'
        '<div style="margin-top:20px;padding:20px 24px;background:#F3F2EC;border-radius:6px;display:flex;align-items:center;'
        'justify-content:space-between;flex-wrap:wrap;gap:16px;">'
        '<div style="font-size:14px;color:#0A1938;">Questions sur les données, les calculs ou la méthode :</div>'
        '<a href="mailto:santactive.esdata@gmail.com" style="padding:12px 24px;background:#1A3D8F;color:white;border-radius:6px;text-decoration:none;'
        'font-size:14px;font-weight:500;white-space:nowrap;">santactive.esdata@gmail.com</a></div>'
        f'<p class="sa-couverture" style="margin-top:16px;">Documentation technique : docs/EVOLUTIONS_MOTEUR.md · '
        f'<a href="{internal_href("about")}" target="_self">À propos →</a></p>',
        unsafe_allow_html=True)
