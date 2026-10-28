"""Page Méthodologie — lecture institutionnelle en cinq sujets.

Publics : ARS, élus, décideurs, professionnels de santé. La page explique ce que mesure l'outil,
d'où viennent les données, comment fonctionne le score, comment sont identifiées les priorités et
les actions, et quelles sont les limites. Les détails d'implémentation (scripts, options, audits,
historique des changements) restent dans la documentation technique du dépôt, hors page publique.
Les libellés affichés sont lus dans la configuration active (millésime APL, définition des
établissements), jamais figés dans le texte.
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
    from ..config import APL_MILLESIME, ETABS_DEFINITION
    return dict(apl_millesime=APL_MILLESIME, etabs_def=ETABS_DEFINITION)


def render(data: dict) -> None:
    cfg = _cfg()
    master = data.get("master")
    nb_scores = int(master["score_global"].notna().sum()) if master is not None else 100
    try:
        from .acces_ign import pilotes_disponibles
        nb_sim = len(pilotes_disponibles())
    except Exception:
        nb_sim = 98
    apl_m = cfg["apl_millesime"]

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Méthodologie")], key_prefix="methodo_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">RESSOURCE</span>'
        '<span class="dot"></span><span class="region">Méthode, sources et limites</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Méthodologie</h1></div>'
        '<p class="fiche-header-lead">Ce que Sant’active mesure, d’où viennent ses données, comment fonctionnent le score, '
        'les priorités et les leviers, et ce qu’il faut garder en tête avant de décider. Lecture en quelques minutes.</p></div>',
        unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 1. CE QUE MESURE SANT'ACTIVE
    # ══════════════════════════════════════════════════════════════════════════
    _section("1 · CE QUE MESURE SANT’ACTIVE", "L’offre de soins de premier recours <em>et son accessibilité.</em>")
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        _encadre("Accès aux soins",
                 "Deux mesures complémentaires, jamais interchangeables : le <strong>temps de trajet</strong> en voiture vers le "
                 "médecin généraliste le plus proche (INSEE), et l’<strong>accessibilité potentielle localisée</strong> (APL, "
                 "DREES), qui compte les consultations réellement disponibles par habitant en tenant compte de l’activité des "
                 "médecins, de la distance et de l’âge de la population.", "#F7F9FD")
    with c2:
        _encadre("Offre médicale",
                 "Les médecins généralistes et spécialistes en activité (répertoire RPPS de la DREES) et les sites hospitaliers "
                 "(fichier FINESS), rapportés à la population de chaque département.", "#F3F2EC")
    with c3:
        _encadre("Besoins et priorités",
                 "Le vieillissement (part des 65 ans et plus) et les pathologies prises en charge par l’Assurance Maladie, "
                 "comparés à âge égal entre départements. Leur croisement avec l’offre désigne les territoires à examiner en "
                 "premier et les actions à instruire.", "#E3EFE8")
    _prose(
        "Sant’active couvre les 100 départements analysés (Mayotte exclue, faute de sources complètes), les régions et, pour "
        "les temps d’accès, les communes. Il ne produit aucune donnée de santé : il réunit des données publiques, calcule des "
        "indicateurs comparables entre territoires et les présente dans une fiche, une carte et un rapport.",
        "Trois statuts sont toujours distingués : la <strong>donnée publique</strong> reprise de son producteur, "
        "l’<strong>indicateur calculé</strong> par Sant’active (score, zones, indices, densités) et "
        "l’<strong>estimation</strong> propre au projet (équivalents temps plein théoriques, gain de proximité du simulateur), "
        "signalée comme telle.")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 2. D'OÙ VIENNENT LES DONNÉES
    # ══════════════════════════════════════════════════════════════════════════
    _section("2 · D’OÙ VIENNENT LES DONNÉES", "Des organismes publics, <em>des millésimes nommés.</em>",
             lead="Chaque indicateur de l’application rappelle son producteur et son année. Les données ne sont pas retouchées ; "
                  "elles sont agrégées à l’échelle du département ou de la commune.")
    _table(["Organisme", "Donnée", "Millésime", "Utilisation dans Sant’active"], [
        ["DREES", "Accessibilité potentielle localisée (APL) aux médecins généralistes", apl_m,
         "Dimension principale du score ; habitants des communes sous le repère de sous-densité 2,5"],
        ["INSEE", "Accès aux équipements : temps de trajet en voiture vers un généraliste, par carreau habité de 200 m", "2025",
         "Dimension temps du score ; habitants et communes à plus de 15 minutes ; lecture communale et simulateur"],
        ["DREES", "Répertoire RPPS des professionnels de santé", "1er janvier 2026",
         "Densité de généralistes (score) ; spécialistes pour les leviers d’action"],
        ["Ministère chargé de la Santé (diffusion DREES)", "Fichier FINESS des établissements", "mars 2026",
         "Sites hospitaliers pour 100 000 habitants : centres hospitaliers, centres hospitaliers régionaux, soins de suite et de "
         "réadaptation privés ; les cliniques privées de court séjour ne sont pas comptées"],
        ["INSEE", "Recensement de la population", "2021", "Population, part des 65 ans et plus, densité, typologie rurale ou urbaine"],
        ["Assurance Maladie (CNAM)", "Cartographie des pathologies et des dépenses", "2023",
         "Patients pris en charge par pathologie ; prévalences comparées à âge égal pour la priorisation"],
        ["DGFiP", "Demandes de valeurs foncières (DVF)", "2025", "Prix médian au m², indicateur de contexte (5 % du score)"],
        ["IGN Géoplateforme, API Géo", "Isochrones routières, contours et population des communes", "service en ligne",
         "Simulateur d’implantation ; fonds et contours des cartes"],
    ])
    st.markdown('<div id="glossaire"></div>', unsafe_allow_html=True)
    with st.expander("Les sigles utilisés dans l’application"):
        _table(["Sigle", "Signification"], [
            ["APL", "Accessibilité potentielle localisée : consultations de médecine générale accessibles par an et par habitant (DREES). Repère de sous-densité : 2,5."],
            ["DREES", "Direction de la recherche, des études, de l’évaluation et des statistiques, service statistique des ministères sociaux."],
            ["RPPS", "Répertoire partagé des professionnels de santé : médecins en activité."],
            ["FINESS", "Fichier national des établissements sanitaires et sociaux."],
            ["INSEE", "Institut national de la statistique et des études économiques."],
            ["CNAM", "Caisse nationale de l’Assurance Maladie."],
            ["DGFiP", "Direction générale des Finances publiques (base DVF des transactions immobilières)."],
            ["IGN", "Institut national de l’information géographique et forestière (isochrones de la Géoplateforme)."],
            ["ARS", "Agence régionale de santé."],
            ["CPTS, MSP", "Communauté professionnelle territoriale de santé ; maison de santé pluriprofessionnelle."],
            ["CH, CHR, SSR, MCO", "Centre hospitalier, centre hospitalier régional, soins de suite et de réadaptation, médecine-chirurgie-obstétrique (court séjour)."],
            ["ETP", "Équivalent temps plein : unité de volume d’activité, pas une personne."],
            ["Isochrone", "Zone atteignable en un temps donné par la route depuis un point."],
        ])
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 3. COMMENT FONCTIONNE LE SCORE
    # ══════════════════════════════════════════════════════════════════════════
    _section("3 · COMMENT FONCTIONNE LE SCORE", "Six dimensions, <em>une position relative.</em>",
             lead=f"Indice sur 100 calculé pour {nb_scores} départements. Il situe un département parmi les autres sur l’offre et "
                  "l’accès aux soins de premier recours ; il ne mesure ni l’état de santé, ni une évolution dans le temps.")
    etabs_txt = {"actuelle": "Sites hospitaliers (CH, CHR, SSR privés) pour 100 000 habitants",
                 "court_sejour": "Sites hospitaliers de court séjour pour 100 000 habitants"}.get(cfg["etabs_def"],
                                                                                              "Sites hospitaliers pour 100 000 habitants")
    rows = [
        ("Accessibilité potentielle", "APL", "30 %", f"Consultations de médecine générale accessibles par habitant et par an · DREES {apl_m}", "Plus c’est élevé, mieux c’est"),
        ("Médecins généralistes", "Densité", "20 %", "Généralistes en activité pour 100 000 habitants · RPPS 2026", "Plus c’est élevé, mieux c’est"),
        ("Temps d’accès", "Trajet", "20 %", "Temps médian en voiture vers un généraliste, pondéré par la population · INSEE 2025", "Plus c’est court, mieux c’est"),
        ("Établissements", "Structures", "15 %", etabs_txt + " · FINESS 2026", "Plus c’est élevé, mieux c’est"),
        ("Seniors", "Pression démographique", "10 %", "Part des 65 ans et plus · INSEE 2021", "Plus c’est faible, mieux c’est"),
        ("Immobilier", "Contexte foncier", "5 %", "Prix médian au m² · DVF 2025", "Plus c’est bas, mieux c’est"),
    ]
    html = ('<div style="border:1px solid #E8E6DD;border-radius:6px;overflow:hidden;margin-bottom:18px;">'
            '<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:10px 20px;background:#0A1938;color:#fff;'
            'font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;"><div>Dimension</div><div>Poids</div>'
            '<div>Indicateur et source</div><div>Sens de lecture</div></div>')
    for i, (dim, sous, poids, texte, sens) in enumerate(rows):
        html += _ROW.format(bg="#fff" if i % 2 == 0 else "#FAFAF8", dim=dim, sous=sous, poids=poids, texte=texte, sens=sens)
    st.markdown(html + "</div>", unsafe_allow_html=True)
    _prose(
        "<strong>Un classement, pas une note.</strong> Pour chaque dimension, le département est classé parmi les autres et "
        "reçoit une position de 0 à 100 (50 = médiane). Le score est la moyenne de ces six positions, pondérée comme ci-dessus. "
        "Les pondérations sont un choix méthodologique du projet, explicite et stable ; elles ne sont pas des pondérations "
        "officielles.",
        "<strong>Trois zones.</strong> Les départements sont répartis en trois groupes de taille égale selon leur score : "
        "<span style='color:#A51C30;font-weight:600;'>critique</span> (tiers le moins bien placé), "
        "<span style='color:#B45309;font-weight:600;'>intermédiaire</span> et "
        "<span style='color:#1B5E3F;font-weight:600;'>favorable</span> (tiers le mieux placé). Le classement national se lit "
        "« 1er = le mieux placé ».",
        "<strong>Quand une donnée manque</strong> (par exemple le temps d’accès INSEE pour la Guadeloupe et la Guyane), le score "
        "est calculé sur les dimensions disponibles, leurs poids étant redistribués, et la fiche le signale.")
    _encadre("Densité et APL peuvent raconter deux histoires",
             "La densité compte des personnes inscrites au répertoire RPPS, quel que soit leur temps de travail ou leur âge. "
             "L’APL compte des consultations réellement accessibles, en tenant compte de l’activité de chaque médecin, de la "
             "distance et des besoins liés à l’âge des habitants. Un département peut donc avoir beaucoup de généralistes et "
             "peu de consultations disponibles, ou l’inverse : c’est pourquoi les deux mesures figurent dans le score.", "#F7F9FD")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 4. PRIORITÉS ET ACTIONS
    # ══════════════════════════════════════════════════════════════════════════
    _section("4 · COMMENT SONT IDENTIFIÉES LES PRIORITÉS ET LES ACTIONS", "Croiser l’offre et les besoins, <em>puis proposer des pistes.</em>")
    _prose(
        "<strong>Offre × besoins.</strong> Le score mesure surtout l’offre. La page Prioriser ajoute un indice de besoins "
        "(vieillissement et pathologies comparées à âge égal) et croise les deux : les départements dont l’offre est sous la "
        "médiane nationale et les besoins au-dessus sont ceux à examiner en premier. Cette lecture complémentaire ne modifie "
        "pas le score.",
        "<strong>Territoires fragiles.</strong> À l’échelle régionale, un score de priorité combine le besoin (fragilité et "
        "score) et le volume de population concernée. Une lecture distincte croise fragilité, impact attendu et faisabilité "
        "pour repérer les candidats à une expérimentation. Dans chaque département, les communes sont classées selon le "
        "temps d’accès, la population exposée et les conditions de déploiement ; les communes sans offre de médecine générale "
        "et peuplées remontent en premier.",
        "<strong>Leviers d’action.</strong> Les recommandations viennent d’un catalogue d’une vingtaine de dispositifs existants "
        "(maisons de santé, aides à l’installation, équipes mobiles, téléconsultation assistée, téléexpertise, premier recours "
        "en santé mentale, prévention, parcours gériatriques…). Chaque levier a des conditions chiffrées sur les indicateurs du "
        "département ; il n’est proposé que si ses conditions obligatoires sont remplies. Au plus quatre leviers par "
        "département, deux par famille ; sans levier déclenché, l’outil recommande une veille. Les règles sont écrites et "
        "reproductibles, sans intelligence artificielle générative. Chaque levier indique son public et, lorsque les données "
        "le permettent, la population concernée avec sa source ; sinon elle est déclarée non quantifiable.",
        f"<strong>Simulateur d’implantation.</strong> Disponible pour {nb_sim} départements. L’utilisateur choisit une commune ; "
        "l’outil calcule, avec les isochrones routières de l’IGN, la population des carreaux INSEE qui passerait sous 10, 15 ou "
        "20 minutes d’un généraliste si un cabinet s’y installait. C’est un gain de proximité théorique, utile pour comparer des "
        "sites candidats ; il ne dit pas si un médecin viendra ni combien de patients il pourra suivre.")
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # 5. LIMITES
    # ══════════════════════════════════════════════════════════════════════════
    _section("5 · QUELLES SONT LES LIMITES", "Ce qu’il faut garder en tête <em>avant de décider.</em>")
    limites = [
        ("Accessibilité géographique ≠ accès effectif",
         "Ni le temps de trajet, ni l’APL ne disent si un rendez-vous est possible : un généraliste proche peut ne plus prendre "
         "de patients. Aucun délai de rendez-vous actuel n’est mesuré ni affiché."),
        ("Des millésimes différents",
         f"Recensement 2021, pathologies 2023, APL {apl_m}, temps d’accès 2025, médecins et établissements 2026, immobilier 2025. "
         "Les écarts entre territoires sont robustes ; les niveaux exacts peuvent avoir évolué."),
        ("Le simulateur mesure une distance, pas une capacité",
         "Il estime combien d’habitants se rapprocheraient d’un cabinet, pas le nombre de consultations qu’un médecin pourrait "
         "assurer ni l’effet sur les cabinets voisins. Les équivalents temps plein théoriques sont un ordre de grandeur."),
        ("Une couverture partielle pour certaines sources",
         "Mayotte est hors score. Guadeloupe et Guyane n’ont pas de temps d’accès INSEE : leur score repose sur cinq dimensions et "
         "la lecture communale s’appuie sur un indicateur de repli, signalé. Les cliniques privées de court séjour ne sont pas "
         "comptées dans l’offre hospitalière. Les inégalités sociales de santé ne sont pas mesurées."),
        ("Un score relatif",
         "Le score situe un département parmi les autres à une date donnée ; il ne mesure pas une évolution et n’est pas une "
         "note de santé. Les leviers sont des pistes à instruire avec les acteurs locaux, pas des prescriptions."),
    ]
    html = '<div style="max-width:860px;">'
    for i, (titre, texte) in enumerate(limites, 1):
        html += ('<div style="display:grid;grid-template-columns:44px 1fr;gap:14px;padding:14px 0;border-bottom:1px solid #E8E6DD;">'
                 f'<div style="font-size:22px;font-weight:300;color:#1A3D8F;">{i:02d}</div>'
                 f'<div><div style="font-size:14px;font-weight:700;color:#0A1938;margin-bottom:3px;">{titre}</div>'
                 f'<div style="font-size:13.5px;color:#2B2B2B;line-height:1.65;">{texte}</div></div></div>')
    st.markdown(html + "</div>", unsafe_allow_html=True)
    _prose(
        "La synthèse vocale des diagnostics (bouton « Écouter ») lit le texte affiché à l’écran avec une voix de synthèse "
        "(service Microsoft) ; elle n’ajoute aucune information.")
    _hr()

    # ── Contact ───────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header"><div class="section-eyebrow">CONTACT</div>'
        '<h2 class="section-title">Une question sur la méthode, <em>une erreur repérée ?</em></h2>'
        '<p class="section-lead">L’équipe répond par e-mail et corrige les données ou les textes lorsqu’une erreur est confirmée.</p></div>'
        '<div style="margin-top:20px;padding:20px 24px;background:#F3F2EC;border-radius:6px;display:flex;align-items:center;'
        'justify-content:space-between;flex-wrap:wrap;gap:16px;">'
        '<div style="font-size:14px;color:#0A1938;">Questions sur les données, les calculs ou la méthode :</div>'
        '<a href="mailto:santactive.esdata@gmail.com" style="padding:12px 24px;background:#1A3D8F;color:white;border-radius:6px;text-decoration:none;'
        'font-size:14px;font-weight:500;white-space:nowrap;">santactive.esdata@gmail.com</a></div>'
        f'<p class="sa-couverture" style="margin-top:16px;">'
        f'<a href="{internal_href("about")}" target="_self">À propos : le projet, l’équipe, les crédits →</a></p>',
        unsafe_allow_html=True)
