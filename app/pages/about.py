"""Page À propos — Sant'active."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from ..router import navigate


def _render_page_logo() -> None:
    """Affiche le logo Sant'active en haut de page."""
    logo_path = Path("static/brand/logo-santactive.png")
    col1, col2 = st.columns([1, 4])
    with col1:
        if logo_path.exists():
            st.image(str(logo_path), width=120)
    st.markdown(
        '<hr style="border:none;border-top:1px solid #E8E6DD;margin:12px 0 32px;">',
        unsafe_allow_html=True,
    )


def render(data: dict) -> None:

    _render_page_logo()

    # Breadcrumb
    st.markdown(
        '<div class="fiche-topbar"><div class="breadcrumb">'
        '<a href="?view=home">Accueil</a>'
        '<span class="sep">›</span>'
        '<span class="current">À propos</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ── SECTION 1 — LE PROJET ─────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">LE PROJET</div>'
        '<h2 class="section-title">'
        "Sant'active — <em>Cartographier la santé, territoire par territoire.</em>"
        '</h2>'
        '<p class="section-lead">'
        "Un outil d'aide à la décision territoriale sur l'accès aux soins en France, "
        "construit à partir de données ouvertes officielles."
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="max-width:720px;font-size:15px;line-height:1.8;color:#2B2B2B;">'
        '<p>'
        "La désertification médicale touche aujourd'hui près de "
        '<strong>87\u202f% du territoire français</strong> et prive des millions '
        "de personnes d'un accès équitable aux soins. Pourtant, les décideurs "
        "— élus locaux, directeurs d'ARS, professionnels de santé — manquent "
        "souvent d'un outil synthétique, lisible et fondé sur des données "
        "officielles pour orienter leurs décisions."
        '</p>'
        '<p>'
        "Sant'active agrège sept sources de données publiques pour produire, "
        "pour chacun des 101 départements français, un diagnostic complet\u202f: "
        "accès aux médecins, établissements de santé, délais estimés, "
        "démographie, pathologies chroniques et contexte immobilier. "
        "L'objectif est de transformer des données brutes en signaux "
        "actionnables — des recommandations chiffrées, localisées, hiérarchisées."
        '</p>'
        '<p>'
        "Toutes les données utilisées sont en accès libre (open data). "
        "Tous les calculs sont documentés et reproductibles."
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── SECTION 2 — LE DÉFI OPEN DATA ────────────────────────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:48px;">'
        '<div class="section-eyebrow">CONTEXTE</div>'
        '<h2 class="section-title">'
        "Un projet né d'un <em>défi Open Data.</em>"
        '</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:28px;">'

        '<div style="flex:1;min-width:260px;padding:24px;background:#F3F2EC;'
        'border-radius:6px;">'
        '<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;'
        'text-transform:uppercase;color:#6B6B68;margin-bottom:12px;">'
        "L'ÉCOLE"
        '</div>'
        '<div style="font-size:17px;font-weight:600;color:#0A1938;margin-bottom:8px;">'
        'ESD — École Supérieure du Digital'
        '</div>'
        '<div style="font-size:14px;color:#4B4B48;line-height:1.6;">'
        'Mastère 1 Data · Promotion 2025-2026<br>Paris, France'
        '</div>'
        '</div>'

        '<div style="flex:1;min-width:260px;padding:24px;background:#F3F2EC;'
        'border-radius:6px;">'
        '<div style="font-size:11px;font-weight:600;letter-spacing:0.08em;'
        'text-transform:uppercase;color:#6B6B68;margin-bottom:12px;">'
        'LE CONCOURS'
        '</div>'
        '<div style="font-size:17px;font-weight:600;color:#0A1938;margin-bottom:8px;">'
        'Open Data University × Latitudes'
        '</div>'
        '<div style="font-size:14px;color:#4B4B48;line-height:1.6;">'
        'Challenge national · Semaine Open Data<br>Avril 2026'
        '</div>'
        '</div>'

        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="max-width:720px;font-size:15px;line-height:1.8;color:#2B2B2B;'
        'padding:24px;border-top:2px solid #E8E6DD;background:#F7F8FC;'
        'border-radius:0 6px 6px 0;">'
        '<em>'
        "\u00ab\u202fL'Open Data University propose aux établissements de formation "
        "à la data de mobiliser leurs élèves sur des challenges qui répondent "
        "à des enjeux sociaux et environnementaux grâce à la réutilisation "
        "de données ouvertes.\u202f\u00bb"
        '</em>'
        '<div style="margin-top:12px;font-size:12px;color:#6B6B68;">'
        '— Open Data University · '
        '<a href="https://www.opendatauniversity.org/" target="_blank" '
        'style="color:#1A3D8F;text-decoration:none;">'
        'opendatauniversity.org'
        '</a>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="max-width:720px;font-size:14px;line-height:1.8;'
        'color:#4B4B48;margin-top:20px;">'
        "Sant'active a été conçu et développé en une semaine dans le cadre "
        "de ce challenge. Le projet répond à la problématique\u202f: "
        '<strong>\u00ab\u202fComment rendre l\'accès aux données de santé territoriale '
        "lisible et actionnable pour les décideurs locaux\u202f?\u202f\u00bb</strong>"
        '</div>',
        unsafe_allow_html=True,
    )

    # ── SECTION 3 — L'ÉQUIPE ──────────────────────────────────────────────────
    st.markdown("""
<div class="section-header" style="margin-top:56px;">
    <div class="section-eyebrow">L'ÉQUIPE</div>
    <h2 class="section-title">
        Mastère 1 Data <em>· ESD Paris.</em>
    </h2>
</div>
""", unsafe_allow_html=True)

    logo_esdata = Path("static/brand/logo-esdata.png")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if logo_esdata.exists():
            st.image(str(logo_esdata), use_container_width=True)
        else:
            st.markdown("""
        <div style="text-align:center;padding:20px;
                    background:#F3F2EC;border-radius:6px;
                    font-size:16px;font-weight:700;color:#0A1938;">
            ESData · ESD Paris
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:24px;'>", unsafe_allow_html=True)

    membres = [
        {"nom": "Sarah Aït Ouhmad",    "linkedin": "https://www.linkedin.com/in/sarah-ait-ouhmad-76947b220/"},
        {"nom": "Nour Amri",           "linkedin": "https://www.linkedin.com/in/nour-amri-610538197/"},
        {"nom": "Orelle Azoulay",      "linkedin": "https://www.linkedin.com/in/orelle-azoulay-742488254/"},
        {"nom": "Anna Damour",         "linkedin": "https://www.linkedin.com/in/anna-damour-a1b586221/"},
        {"nom": "Ackyl Junior Dangi",  "linkedin": "https://www.linkedin.com/in/ackyl-junior-d-872185244/"},
        {"nom": "Jnaina Hakimi",       "linkedin": "https://www.linkedin.com/in/jnainahakimi/"},
        {"nom": "Marwan Karabadja",    "linkedin": "https://www.linkedin.com/in/marwan-karabadja-107565297/"},
        {"nom": "Simon Maurey",        "linkedin": "https://www.linkedin.com/in/simon-maurey/"},
        {"nom": "Mchita Siham",        "linkedin": "https://www.linkedin.com/in/mchita-siham-97308a177/"},
        {"nom": "Métira Merghem",      "linkedin": "https://www.linkedin.com/in/m%C3%A9tira-merghem-243548212/"},
        {"nom": "William Milic",       "linkedin": "https://www.linkedin.com/in/william-milic-194654254/"},
        {"nom": "Telina Ranaivoson",   "linkedin": "https://www.linkedin.com/in/telina-ranaivoson-448ba91b7/"},
        {"nom": "Laura Sambafofolo",   "linkedin": "https://www.linkedin.com/in/laurasambafofolo/"},
        {"nom": "Ryan Moyo",           "linkedin": "https://www.linkedin.com/in/ryan-moyo/"},
    ]

    cards_html = '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;">'
    for m in membres:
        initiales = "".join(
            [p[0].upper() for p in m["nom"].split() if p and p[0].isalpha()]
        )[:2]

        if m.get("linkedin"):
            nom_rendu = (
                f'<a href="{m["linkedin"]}" target="_blank" '
                f'rel="noopener noreferrer" '
                f'style="color:#0A1938;text-decoration:none;font-size:14px;'
                f'font-weight:600;border-bottom:1px solid #1A3D8F;">'
                f'{m["nom"]}</a>'
            )
        else:
            nom_rendu = (
                f'<span style="font-size:14px;font-weight:600;'
                f'color:#0A1938;">{m["nom"]}</span>'
            )

        cards_html += (
            '<div style="display:flex;align-items:center;gap:12px;'
            'padding:14px 18px;background:white;'
            'border:1px solid #E8E6DD;border-radius:6px;'
            'min-width:200px;flex:1;max-width:280px;">'
            '<div style="width:38px;height:38px;border-radius:50%;'
            'background:#1A3D8F;color:white;flex-shrink:0;'
            'display:flex;align-items:center;justify-content:center;'
            'font-size:13px;font-weight:700;">'
            f'{initiales}'
            '</div>'
            f'<div>{nom_rendu}</div>'
            '</div>'
        )
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    st.markdown(
        '<div style="margin-top:32px;padding:20px 24px;'
        'background:#F3F2EC;border-radius:6px;'
        'display:flex;align-items:center;gap:16px;flex-wrap:wrap;">'
        '<div style="width:44px;height:44px;border-radius:50%;'
        'background:#0A1938;color:white;flex-shrink:0;'
        'display:flex;align-items:center;justify-content:center;'
        'font-size:15px;font-weight:700;">'
        'CD'
        '</div>'
        '<div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#6B6B68;margin-bottom:4px;">'
        'INTERVENANTE · ENCADRANTE DU PROJET'
        '</div>'
        '<a href="https://www.linkedin.com/in/caroline-dias-4805489a/" '
        'target="_blank" rel="noopener noreferrer" '
        'style="font-size:16px;font-weight:700;color:#0A1938;'
        'text-decoration:none;border-bottom:1px solid #1A3D8F;">'
        'Caroline Dias'
        '</a>'
        '<div style="font-size:13px;color:#4B4B48;margin-top:3px;">'
        "Cheffe de Projet DSI · Plateformisation d'un système d'information"
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── SECTION 4 — DONNÉES OPEN DATA ────────────────────────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:48px;">'
        '<div class="section-eyebrow">TRANSPARENCE</div>'
        '<h2 class="section-title">'
        '100\u202f% de données <em>ouvertes et officielles.</em>'
        '</h2>'
        '<p class="section-lead">'
        "Toutes les données utilisées dans Sant'active sont en accès libre. "
        "Aucune donnée commerciale ou propriétaire."
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    sources = [
        (
            "INSEE · Recensement 2021",
            "Population, âge, densité par commune et département",
            "https://www.insee.fr",
        ),
        (
            "RPPS · DREES · janv. 2026",
            "Répertoire des professionnels de santé actifs par spécialité",
            "https://www.data.gouv.fr/fr/datasets/annuaire-sante-medecin/",
        ),
        (
            "FINESS · DREES · mars 2026",
            "Établissements sanitaires et sociaux (hôpitaux, cliniques)",
            "https://www.data.gouv.fr/fr/datasets/finess-extraction-du-fichier-des-etablissements/",
        ),
        (
            "APL · ANCT · Observatoire des territoires 2023",
            "Accessibilité Potentielle Localisée aux médecins généralistes",
            "https://www.observatoire-des-territoires.gouv.fr/",
        ),
        (
            "DVF · DGFiP · 2025",
            "Demande de Valeurs Foncières — transactions immobilières",
            "https://www.data.gouv.fr/fr/datasets/demandes-de-valeurs-foncieres/",
        ),
        (
            "CNAM · Ameli open data · 2023",
            "Prévalence des pathologies chroniques par département "
            "(diabète, cardio, cancers, respiratoire, psychiatrique...)",
            "https://data.ameli.fr/",
        ),
        (
            "ANSM · Base des médicaments · 2025",
            "Base nationale des médicaments — consommation et prescriptions",
            "https://base-donnees-publique.medicaments.gouv.fr/",
        ),
        (
            "DREES · Études et Résultats n°1085 · 2018",
            "Enquête nationale sur les délais d'attente en médecine (40 000 personnes)",
            "https://drees.solidarites-sante.gouv.fr/publications/etudes-et-resultats/"
            "la-moitie-des-rendez-vous-sont-obtenus-en-2-jours-chez-le",
        ),
    ]

    rows_html = ""
    for nom, desc, url in sources:
        rows_html += (
            '<div style="display:flex;align-items:flex-start;gap:16px;'
            'padding:14px 0;border-bottom:1px solid #E8E6DD;">'
            '<div style="width:8px;height:8px;border-radius:50%;'
            'background:#1A3D8F;flex-shrink:0;margin-top:6px;"></div>'
            '<div>'
            f'<a href="{url}" target="_blank" '
            'style="font-size:14px;font-weight:600;color:#1A3D8F;text-decoration:none;">'
            f'{nom}'
            '</a>'
            f'<div style="font-size:13px;color:#6B6B68;margin-top:3px;">{desc}</div>'
            '</div>'
            '</div>'
        )
    st.markdown(rows_html, unsafe_allow_html=True)

    # ── SECTION 5 — LIENS ─────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header" style="margin-top:48px;">'
        '<div class="section-eyebrow">LIENS</div>'
        '<h2 class="section-title">En savoir <em>plus.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;">'
        '<a href="https://www.opendatauniversity.org/" target="_blank" '
        'style="padding:12px 24px;background:#1A3D8F;color:white;'
        'border-radius:4px;text-decoration:none;font-size:14px;font-weight:500;">'
        'Open Data University →'
        '</a>'
        '<a href="?view=methodologie" '
        'style="padding:12px 24px;background:white;color:#1A3D8F;'
        'border:1.5px solid #1A3D8F;border-radius:4px;'
        'text-decoration:none;font-size:14px;font-weight:500;">'
        'Notre méthodologie →'
        '</a>'
        '<a href="https://ecole-du-digital.com/" target="_blank" '
        'style="padding:12px 24px;background:white;color:#2B2B2B;'
        'border:1.5px solid #D8D6CE;border-radius:4px;'
        'text-decoration:none;font-size:14px;font-weight:500;">'
        'ESD Paris →'
        '</a>'
        '</div>',
        unsafe_allow_html=True,
    )
