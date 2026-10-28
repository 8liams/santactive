"""Page À propos — l'histoire du projet : origine, problématique, objectif, équipe, engagements, contact.

Les sources, calculs et limites sont décrits exclusivement dans la Méthodologie.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from ..components.nav import NavCrumb, internal_href, render_breadcrumb

CONTACT_EMAIL = "santactive.esdata@gmail.com"


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


MEMBRES = [
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


def render(data: dict) -> None:
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("À propos")], key_prefix="about_bc")

    # ── 1. L'HISTOIRE DU PROJET ───────────────────────────────────────────────
    _section("LE PROJET", "Un projet étudiant né d’un <em>défi open data.</em>",
             "Sant’active a été imaginé et construit par les étudiants du Mastère 1 Data de l’ESD Paris pour le challenge de "
             "l’Open Data University, au printemps 2026.", top=8)
    _prose(
        "<p><strong>Le défi.</strong> L’Open Data University, programme de l’association Latitudes, propose aux écoles de mobiliser "
        "leurs étudiants sur la réutilisation de données ouvertes au service d’enjeux sociaux. Le sujet retenu par l’équipe : l’accès "
        "aux soins de premier recours, dont les disparités territoriales pèsent sur la vie quotidienne de millions d’habitants, "
        "alors que les données qui les décrivent existent, publiques mais dispersées et difficiles à lire.</p>"
        "<p><strong>La question.</strong> Comment rendre ces données lisibles et actionnables pour celles et ceux qui décident sur le "
        "terrain : agences régionales de santé, élus et services des collectivités, communautés professionnelles de santé ?</p>"
        "<p><strong>Notre réponse.</strong> Un outil qui réunit, pour chaque département, région et commune, les données publiques sur "
        "l’offre et l’accessibilité des soins, les traduit en un diagnostic lisible, aide à repérer les territoires où l’écart entre "
        "offre et besoins est le plus préoccupant, propose des pistes d’action issues de dispositifs existants et permet de simuler "
        "le gain de proximité d’une nouvelle implantation. Chaque fiche se partage en rapport PDF et par e-mail.</p>"
        "<p>La première version du challenge a ensuite été consolidée et documenté jusqu’à la version publiée ici. Sant’active repose "
        "uniquement sur des données publiques (INSEE, DREES, Assurance Maladie, fichier FINESS, DGFiP, IGN) ; la façon dont elles "
        f"sont utilisées est décrite dans la <a href=\"{internal_href('methodologie')}\" target=\"_self\">Méthodologie</a>. "
        "C’est un travail pédagogique indépendant : il n’engage ni les producteurs de données, ni les institutions citées, et ne "
        "revendique aucun partenariat officiel.</p>"
    )

    # ── 2. L'ÉQUIPE ──────────────────────────────────────────────────────────
    _section("L’ÉQUIPE", "Mastère 1 Data <em>· ESD Paris.</em>")
    _clean_path = "static/brand/logo-esdata-clean.png"
    if not Path(_clean_path).exists():
        _remove_dark_background("static/brand/logo-esdata.png", _clean_path)
    _esdata_b64 = _get_image_b64(_clean_path) or _get_image_b64("static/brand/logo-esdata.png")
    if _esdata_b64:
        st.markdown(f'<div style="margin:4px 0 14px;"><img src="data:image/png;base64,{_esdata_b64}" '
                    'style="width:150px;height:auto;mix-blend-mode:multiply;background:transparent;" alt="ESData, ESD Paris"></div>',
                    unsafe_allow_html=True)
    cards = '<div style="display:flex;flex-wrap:wrap;gap:10px;">'
    for nom, url in MEMBRES:
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

    # ── 3. ENGAGEMENTS ───────────────────────────────────────────────────────
    _section("NOS ENGAGEMENTS", "Ce que nous nous <em>engageons à dire.</em>")
    engagements = [
        ("Des règles lisibles", "Score, zones, priorités et leviers reposent sur des règles écrites et expliquées ; aucune intelligence "
                                "artificielle générative n’intervient dans les résultats."),
        ("Des sources nommées", "Chaque chiffre rappelle l’organisme qui l’a produit et son millésime."),
        ("Des limites dites", "Sant’active décrit l’offre et l’accessibilité géographique des soins ; il ne mesure ni la disponibilité "
                              "réelle des rendez-vous, ni la qualité des soins, ni l’état de santé d’une population. Les pistes d’action "
                              "sont à instruire avec les acteurs locaux."),
    ]
    html = '<div style="max-width:760px;">'
    for titre, texte in engagements:
        html += ('<div style="padding:12px 0;border-bottom:1px solid #E8E6DD;">'
                 f'<div style="font-size:14px;font-weight:700;color:#0A1938;">{titre}</div>'
                 f'<div style="font-size:14px;color:#2B2B2B;line-height:1.7;margin-top:3px;">{texte}</div></div>')
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    # ── 4. CONTACT ET LIENS ──────────────────────────────────────────────────
    _section("CONTACT", "Nous <em>écrire.</em>",
             "Une question, une erreur repérée, une idée d’usage dans votre territoire : l’équipe répond par e-mail.")
    st.markdown(
        '<div style="margin-top:4px;padding:18px 22px;background:#F3F2EC;border-radius:6px;display:flex;align-items:center;'
        'justify-content:space-between;flex-wrap:wrap;gap:14px;">'
        '<div style="font-size:14px;color:#0A1938;line-height:1.6;">Signalement d’erreur, question méthodologique, demande d’accompagnement</div>'
        f'<a href="mailto:{CONTACT_EMAIL}?subject=Sant%27active%20%C2%B7%20question" style="padding:11px 22px;background:#1A3D8F;color:white;'
        f'border-radius:6px;text-decoration:none;font-size:14px;font-weight:500;white-space:nowrap;">{CONTACT_EMAIL}</a></div>',
        unsafe_allow_html=True)
    liens = [
        (internal_href("methodologie"), "_self", "Méthodologie", "Comment fonctionnent le score, la priorisation, le diagnostic, la comparaison et le simulateur ; sources et limites."),
        ("https://www.opendatauniversity.org/", "_blank", "Open Data University", "Le programme de challenges open data à l’origine du projet (association Latitudes)."),
        ("https://ecole-du-digital.com/", "_blank", "ESD Paris", "École Supérieure du Digital, Mastère Data."),
    ]
    html = '<div style="max-width:760px;margin-top:16px;">'
    for url, target, titre, texte in liens:
        html += ('<div style="padding:11px 0;border-bottom:1px solid #E8E6DD;">'
                 f'<a href="{url}" target="{target}" rel="noopener noreferrer" style="font-size:14px;font-weight:600;color:#1A3D8F;text-decoration:none;">{titre} →</a>'
                 f'<div style="font-size:13px;color:#4B4B48;margin-top:2px;line-height:1.55;">{texte}</div></div>')
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
    st.markdown('<p style="font-size:12px;color:#9C9A92;margin-top:18px;">Crédits : équipe Mastère 1 Data ESD Paris · Open Data University × Latitudes · '
                'données publiques INSEE, DREES, Assurance Maladie, FINESS, DGFiP, IGN · fonds de carte © OpenStreetMap · police Marianne.</p>',
                unsafe_allow_html=True)
