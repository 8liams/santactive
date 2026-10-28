"""Page À propos — Sant'active.

Présente le projet (objectif, publics), son origine et l'équipe, les sources publiques et leur
provenance, les engagements de transparence avec leurs limites, les contacts et ressources.
Les explications techniques détaillées (calculs, hypothèses, glossaire) sont dans la Méthodologie.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from ..components.nav import NavCrumb, internal_href, render_breadcrumb
from ..config import APL_MILLESIME

CONTACT_EMAIL = "santactive.esdata@gmail.com"
DEPOT_GITHUB = "https://github.com/8liams/santactive"


def _get_image_b64(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _remove_dark_background(image_path: str, output_path: str, threshold: int = 30) -> str:
    """Supprime le fond noir/sombre d'un PNG via PIL."""
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(image_path).convert("RGBA")
        data = np.array(img)
        r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]
        dark_mask = (r.astype(int) + g.astype(int) + b.astype(int)) < (threshold * 3)
        data[:, :, 3] = np.where(dark_mask, 0, a)
        Image.fromarray(data).save(output_path, "PNG")
        return output_path
    except ImportError:
        return image_path


def _section(eyebrow: str, title_html: str, lead: str | None = None, top: int = 48) -> None:
    st.markdown(
        f'<div class="section-header" style="margin-top:{top}px;">'
        f'<div class="section-eyebrow">{eyebrow}</div>'
        f'<h2 class="section-title">{title_html}</h2>'
        + (f'<p class="section-lead">{lead}</p>' if lead else "")
        + '</div>',
        unsafe_allow_html=True,
    )


def _prose(html: str) -> None:
    st.markdown(f'<div style="max-width:760px;font-size:15px;line-height:1.8;color:#2B2B2B;">{html}</div>',
                unsafe_allow_html=True)


# Sources réellement utilisées par l'application (producteur · millésime · rôle · lien de référence).
# Trois statuts distinguent la donnée publique, l'agrégat calculé par Sant'active et l'estimation propre au projet.
SOURCES: list[tuple[str, str, str, str]] = [
    ("INSEE · Recensement de la population 2021", "Population municipale, âge, densité par commune et par département.",
     "https://www.insee.fr/fr/statistiques?categorie=1&debut=0&idprec=5650720", "Donnée publique"),
    ("INSEE · Accès aux équipements 2025 (BPE 2025, distancier Metric-OSRM)",
     "Temps de trajet en voiture, par carreau habité de 200 m, vers le médecin généraliste le plus proche ; "
     "habitants à plus de 15 minutes ; dimension temps du score et lecture communale.",
     "https://www.insee.fr/fr/metadonnees/source/serie/s1161", "Donnée publique"),
    ("DREES · Accessibilité potentielle localisée (APL) aux médecins généralistes · millésime " + APL_MILLESIME,
     "Consultations accessibles par an et par habitant, par commune ; valeur départementale pondérée par la population "
     "standardisée ; habitants sous le repère 2,5.",
     "https://data.drees.solidarites-sante.gouv.fr/explore/?q=APL", "Donnée publique · agrégat Sant'active"),
    ("DREES · Répertoire RPPS des professionnels de santé · 1er janvier 2026",
     "Médecins généralistes et spécialistes en activité, par département.",
     "https://data.drees.solidarites-sante.gouv.fr/explore/?q=RPPS", "Donnée publique"),
    ("FINESS · ministère chargé de la Santé (diffusion DREES) · mars 2026",
     "Sites d'établissements de santé ; retenus dans le score : centres hospitaliers, centres hospitaliers régionaux, "
     "établissements privés de soins de suite et de réadaptation. Les cliniques privées de court séjour ne sont pas comptées.",
     "https://www.data.gouv.fr/fr/datasets/finess-extraction-du-fichier-des-etablissements/", "Donnée publique"),
    ("CNAM · Cartographie des pathologies et des dépenses · 2023",
     "Patients pris en charge par pathologie et par département ; prévalences brutes et standardisées sur l'âge.",
     "https://data.ameli.fr/", "Donnée publique · standardisation Sant'active"),
    ("DGFiP · Demandes de valeurs foncières (DVF) · 2025",
     "Prix médian des transactions immobilières, indicateur de contexte (5 % du score).",
     "https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres/", "Donnée publique"),
    ("IGN · Géoplateforme · service d'isochrones",
     "Zones atteignables en 10, 15 et 20 minutes en voiture depuis un point d'implantation ; simulateur.",
     "https://geoservices.ign.fr/documentation/services/services-geoplateforme/itineraire", "Service public en ligne"),
    ("API Géo (geo.api.gouv.fr) · contours et population des communes",
     "Référentiel des communes, contours départementaux et communaux servis par l'État.",
     "https://geo.api.gouv.fr/", "Service public en ligne"),
]


def render(data: dict) -> None:
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("À propos")], key_prefix="about_bc")

    # ── 1. CE QU'EST SANT'ACTIVE ─────────────────────────────────────────────
    _section("LE PROJET", "Sant'active : <em>l'accès aux soins, territoire par territoire.</em>",
             "Un outil d'aide à la décision sur l'offre et l'accès aux soins de premier recours, construit à partir de "
             "données publiques, pour les agences régionales de santé, les collectivités et les professionnels de santé.", top=8)
    _prose(
        "<p>Sant'active réunit, pour chacun des 100 départements analysés (Mayotte exclue, faute de sources complètes), "
        "les données publiques qui décrivent l'offre de soins de premier recours et son accessibilité : accessibilité "
        "potentielle aux généralistes (APL), temps de trajet vers un généraliste, effectifs de médecins, sites hospitaliers, "
        "démographie, pathologies prises en charge et contexte immobilier.</p>"
        "<p>Il en tire un <strong>diagnostic lisible</strong> (score Sant'active, zone, comparaison nationale), une "
        "<strong>priorisation</strong> des territoires où l'écart entre offre et besoins est le plus préoccupant, des "
        "<strong>leviers d'action</strong> issus de dispositifs existants et sélectionnés par des règles explicites, et un "
        "<strong>simulateur</strong> de gain de proximité pour une implantation. Chaque fiche se partage en PDF et par e-mail.</p>"
        "<p>Ses publics : directions et délégations départementales des ARS, élus et services des collectivités, "
        "communautés professionnelles territoriales de santé (CPTS), professionnels de santé qui préparent un projet.</p>"
    )
    st.markdown(
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 4px;">'
        f'<a href="{internal_href("home")}" target="_self" class="reco-link">Ouvrir un diagnostic →</a>'
        f'<a href="{internal_href("methodologie")}" target="_self" class="reco-link">Lire la méthodologie →</a>'
        '</div>', unsafe_allow_html=True)

    # ── 2. ORIGINE ET ÉQUIPE ──────────────────────────────────────────────────
    _section("ORIGINE ET ÉQUIPE", "Un projet étudiant né d'un <em>défi open data.</em>")
    _prose(
        "<p>Sant'active a été conçu par les étudiants du Mastère 1 Data de l'ESD Paris (École Supérieure du Digital, "
        "promotion 2025-2026) dans le cadre du challenge de l'Open Data University, programme porté par l'association "
        "Latitudes, qui propose aux établissements de formation de mobiliser leurs élèves sur la réutilisation de données "
        "ouvertes au service d'enjeux sociaux et environnementaux (semaine Open Data, avril 2026).</p>"
        "<p>La question posée : <strong>comment rendre les données publiques sur l'accès aux soins lisibles et "
        "actionnables pour les décideurs territoriaux ?</strong> La première version réalisée pendant le challenge a ensuite été "
        "consolidé, audité et documenté jusqu'à la version 1 publiée ici. Sant'active est un travail pédagogique "
        "indépendant : il n'engage ni les producteurs de données cités, ni les institutions mentionnées, et ne revendique "
        "aucun partenariat officiel.</p>"
    )

    _clean_path = "static/brand/logo-esdata-clean.png"
    if not Path(_clean_path).exists():
        _remove_dark_background("static/brand/logo-esdata.png", _clean_path)
    _esdata_b64 = _get_image_b64(_clean_path) or _get_image_b64("static/brand/logo-esdata.png")
    if _esdata_b64:
        st.markdown(f'<div style="margin:16px 0 12px;"><img src="data:image/png;base64,{_esdata_b64}" '
                    'style="width:150px;height:auto;mix-blend-mode:multiply;background:transparent;" alt="ESData, ESD Paris"></div>',
                    unsafe_allow_html=True)

    membres = [
        ("Sarah Aït Ouhmad", "https://www.linkedin.com/in/sarah-ait-ouhmad-76947b220/"),
        ("Nour Amri", "https://www.linkedin.com/in/nour-amri-1b3071297/"),
        ("Orelle Azoulay", "https://www.linkedin.com/in/orelle-azoulay-742488254/"),
        ("Anna Damour", "https://www.linkedin.com/in/anna-damour-a1b586221/"),
        ("Ackyl Junior Dangi", "https://www.linkedin.com/in/ackyl-junior-d-872185244/"),
        ("Jnaina Hakimi", "https://www.linkedin.com/in/jnainahakimi/"),
        ("Marwan Karabadja", "https://www.linkedin.com/in/marwan-karabadja-107565297/"),
        ("Simon Maurey", "https://www.linkedin.com/in/simon-maurey/"),
        ("Mchita Siham", "https://www.linkedin.com/in/mchita-siham-97308a177/"),
        ("Métira Merghem", "https://www.linkedin.com/in/m%C3%A9tira-merghem-243548212/"),
        ("William Milic", "https://www.linkedin.com/in/william-milic-194654254/"),
        ("Telina Ranaivoson", "https://www.linkedin.com/in/telina-ranaivoson-448ba91b7/"),
        ("Laura Sambafofolo", "https://www.linkedin.com/in/laurasambafofolo/"),
        ("Ryan Moyo", "https://www.linkedin.com/in/ryan-moyo/"),
    ]
    cards = '<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#6B6B68;margin:6px 0 10px;">Équipe étudiante · Mastère 1 Data, ESD Paris</div>'
    cards += '<div style="display:flex;flex-wrap:wrap;gap:10px;">'
    for nom, url in membres:
        initiales = "".join(p[0].upper() for p in nom.split() if p and p[0].isalpha())[:2]
        cards += ('<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:white;border:1px solid #E8E6DD;'
                  'border-radius:6px;min-width:190px;flex:1;max-width:260px;">'
                  '<div style="width:32px;height:32px;border-radius:50%;background:#1A3D8F;color:white;flex-shrink:0;display:flex;'
                  f'align-items:center;justify-content:center;font-size:12px;font-weight:700;">{initiales}</div>'
                  f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#0A1938;text-decoration:none;font-size:14px;'
                  f'font-weight:600;border-bottom:1px solid #1A3D8F;">{nom}</a></div>')
    cards += "</div>"
    st.markdown(cards, unsafe_allow_html=True)
    st.markdown(
        '<div style="margin-top:18px;padding:16px 20px;background:#F3F2EC;border-radius:6px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">'
        '<div style="width:40px;height:40px;border-radius:50%;background:#0A1938;color:white;flex-shrink:0;display:flex;align-items:center;'
        'justify-content:center;font-size:14px;font-weight:700;">CD</div><div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#6B6B68;margin-bottom:3px;">Encadrement pédagogique</div>'
        '<a href="https://www.linkedin.com/in/caroline-dias-4805489a/" target="_blank" rel="noopener noreferrer" '
        'style="font-size:15px;font-weight:700;color:#0A1938;text-decoration:none;border-bottom:1px solid #1A3D8F;">Caroline Dias</a>'
        '<div style="font-size:13px;color:#4B4B48;margin-top:2px;">Intervenante ESD Paris · cheffe de projet DSI</div></div></div>',
        unsafe_allow_html=True)

    # ── 3. SOURCES PUBLIQUES ─────────────────────────────────────────────────
    _section("SOURCES", "Des données publiques <em>au service de la décision.</em>",
             "Sant'active ne produit aucune donnée de santé : il réutilise des données diffusées par leurs producteurs "
             "publics et des services en ligne de l'État. Trois statuts sont distingués dans toute l'application.")
    st.markdown(
        '<div style="display:flex;gap:14px;flex-wrap:wrap;margin:6px 0 18px;">'
        '<div style="flex:1;min-width:220px;padding:16px 18px;background:#F7F8FC;border-radius:6px;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#1A3D8F;margin-bottom:6px;">Donnée publique</div>'
        '<div style="font-size:13.5px;color:#2B2B2B;line-height:1.6;">Valeur reprise telle quelle de son producteur (INSEE, DREES, CNAM, DGFiP, FINESS), avec son millésime.</div></div>'
        '<div style="flex:1;min-width:220px;padding:16px 18px;background:#F3F2EC;border-radius:6px;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#0A1938;margin-bottom:6px;">Indicateur calculé</div>'
        '<div style="font-size:13.5px;color:#2B2B2B;line-height:1.6;">Agrégat ou rapport construit par Sant\'active à partir de ces données : APL départemental pondéré, densités, prévalences standardisées, score, zones, indices offre × besoins.</div></div>'
        '<div style="flex:1;min-width:220px;padding:16px 18px;background:#FDF8EC;border-radius:6px;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#8A5A00;margin-bottom:6px;">Estimation ou simulation</div>'
        '<div style="font-size:13.5px;color:#2B2B2B;line-height:1.6;">Calcul propre au projet, toujours signalé comme tel : équivalents temps plein théoriques, gain de proximité du simulateur, leviers d\'action.</div></div>'
        '</div>', unsafe_allow_html=True)

    rows_html = ""
    for nom, desc, url, statut in SOURCES:
        rows_html += (
            '<div style="display:flex;align-items:flex-start;gap:14px;padding:12px 0;border-bottom:1px solid #E8E6DD;">'
            '<div style="width:8px;height:8px;border-radius:50%;background:#1A3D8F;flex-shrink:0;margin-top:7px;"></div>'
            '<div style="flex:1;">'
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="font-size:14px;font-weight:600;color:#1A3D8F;text-decoration:none;">{nom}</a>'
            f'<span style="font-size:11px;color:#6B6B68;margin-left:8px;letter-spacing:0.04em;text-transform:uppercase;">{statut}</span>'
            f'<div style="font-size:13px;color:#4B4B48;margin-top:3px;line-height:1.55;">{desc}</div>'
            '</div></div>')
    st.markdown(rows_html, unsafe_allow_html=True)
    st.markdown(
        '<p style="max-width:760px;font-size:13px;color:#6B6B68;line-height:1.7;margin-top:12px;">'
        "Les données tabulaires sont diffusées par leurs producteurs sur leurs portails ou sur data.gouv.fr ; les services "
        "d'isochrones et de référentiel géographique sont des services en ligne de l'État, interrogés à la demande. Les fonds de "
        "carte proviennent d'OpenStreetMap et de ses contributeurs. Les conditions d'utilisation applicables sont celles indiquées "
        "par chaque producteur. L'enquête DREES de 2016-2017 sur les délais de rendez-vous, utilisée dans les premières versions, "
        "n'intervient plus dans les diagnostics ; elle reste citée dans l'historique de la Méthodologie."
        '</p>', unsafe_allow_html=True)

    # ── 4. TRANSPARENCE ET LIMITES ───────────────────────────────────────────
    _section("TRANSPARENCE", "Ce que nous nous <em>engageons à dire.</em>")
    engagements = [
        ("Des règles lisibles", "Le score, les zones, les priorités et les leviers reposent sur des règles écrites, publiées dans la "
                                "Méthodologie et reproductibles ; aucune intelligence artificielle générative n'intervient dans les résultats."),
        ("Des sources nommées", "Chaque indicateur affiche son producteur et son millésime ; les changements de méthode sont datés et "
                                "justifiés dans l'historique de la Méthodologie."),
        ("Des limites assumées", "Sant'active décrit l'offre et l'accessibilité géographique des soins de premier recours. Il ne mesure "
                                 "ni la disponibilité réelle des rendez-vous, ni la qualité des soins, ni l'état de santé d'une population ; "
                                 "le score situe un département parmi les autres, ce n'est pas une note de santé."),
        ("Des pistes, pas des prescriptions", "Les leviers d'action sont des pistes à instruire avec les acteurs locaux ; ils ne "
                                              "constituent ni une évaluation de politique publique ni un ordre de mise en œuvre."),
        ("Un code ouvert", f"Le code de l'application et sa documentation technique sont publiés sur GitHub ({DEPOT_GITHUB.replace('https://', '')})."),
    ]
    html = '<div style="max-width:760px;">'
    for titre, texte in engagements:
        html += ('<div style="padding:12px 0;border-bottom:1px solid #E8E6DD;">'
                 f'<div style="font-size:14px;font-weight:700;color:#0A1938;">{titre}</div>'
                 f'<div style="font-size:14px;color:#2B2B2B;line-height:1.7;margin-top:3px;">{texte}</div></div>')
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    # ── 5. CONTACT ET RESSOURCES ─────────────────────────────────────────────
    _section("CONTACT ET RESSOURCES", "Nous <em>écrire.</em>",
             "Une question sur une donnée, une erreur repérée, une idée d'usage dans votre territoire : l'équipe répond par e-mail.")
    st.markdown(
        '<div style="margin-top:4px;padding:18px 22px;background:#F3F2EC;border-radius:6px;display:flex;align-items:center;'
        'justify-content:space-between;flex-wrap:wrap;gap:14px;">'
        '<div style="font-size:14px;color:#0A1938;line-height:1.6;">Signalement d\'erreur, question méthodologique, demande d\'accompagnement</div>'
        f'<a href="mailto:{CONTACT_EMAIL}?subject=Sant%27active%20%C2%B7%20question" style="padding:11px 22px;background:#1A3D8F;color:white;'
        f'border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;white-space:nowrap;">{CONTACT_EMAIL}</a></div>',
        unsafe_allow_html=True)
    ressources = [
        (internal_href("methodologie"), "_self", "Méthodologie", "Ce que mesure l'outil, ses calculs, ses hypothèses, ses limites et son historique."),
        (internal_href("methodologie") + "#glossaire", "_self", "Comprendre les sigles et indicateurs", "Glossaire : APL, RPPS, FINESS, BPE, carroyage, isochrone, standardisation, ETP…"),
        (DEPOT_GITHUB, "_blank", "Code source et documentation technique (GitHub)", "Dépôt public : code de l'application, journal des évolutions du moteur, scripts d'audit."),
        ("https://www.opendatauniversity.org/", "_blank", "Open Data University", "Le programme de challenges open data à l'origine du projet (association Latitudes)."),
        ("https://ecole-du-digital.com/", "_blank", "ESD Paris", "École Supérieure du Digital, Mastère Data."),
    ]
    html = '<div style="max-width:760px;margin-top:16px;">'
    for url, target, titre, texte in ressources:
        html += ('<div style="padding:11px 0;border-bottom:1px solid #E8E6DD;">'
                 f'<a href="{url}" target="{target}" rel="noopener noreferrer" style="font-size:14px;font-weight:600;color:#1A3D8F;text-decoration:none;">{titre} →</a>'
                 f'<div style="font-size:13px;color:#4B4B48;margin-top:2px;line-height:1.55;">{texte}</div></div>')
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.markdown('<p style="font-size:12px;color:#9C9A92;margin-top:18px;">Crédits : équipe Mastère 1 Data ESD Paris · Open Data University × Latitudes · '
                'fonds de carte © OpenStreetMap · police Marianne (État français).</p>', unsafe_allow_html=True)
