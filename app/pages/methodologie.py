"""Page Méthodologie — documentation complète, citable dans un rapport officiel."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ..router import navigate
from ..components.tooltip import info_tooltip


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


# ── Render principal ──────────────────────────────────────────────────────────

def render(data: dict) -> None:

    _render_page_logo()

    # Breadcrumb
    st.markdown(
        '<div class="fiche-topbar"><div class="breadcrumb">'
        '<a href="?view=home">Accueil</a>'
        '<span class="sep">›</span>'
        '<span class="current">Méthodologie</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="fiche-header">'
        '<div class="fiche-eyebrow">'
        '<span class="code">RESSOURCE</span>'
        '<span class="dot"></span>'
        '<span class="region">Transparence &amp; sources</span>'
        '</div>'
        '<div class="fiche-title-row">'
        '<h1 class="fiche-title">Méthodologie</h1>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # 1. INTRODUCTION
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "PRÉSENTATION",
        "Une méthodologie <em>ouverte et documentée.</em>",
        lead=(
            "Sant'active agrège des données publiques issues de sources officielles "
            "françaises. Tous les calculs sont reproductibles. Les limites sont "
            "explicitées et assumées."
        ),
    )
    _prose(
        "Le dashboard est destiné aux ARS, aux élus locaux et aux professionnels de "
        "santé. Il ne produit pas de vérité absolue sur un territoire — il synthétise "
        "des signaux disponibles pour orienter le diagnostic et la décision. Chaque "
        "indicateur est accompagné de sa source, de son millésime et de ses limites "
        "connues."
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 2. SCORE GLOBAL
    # ══════════════════════════════════════════════════════════════════════════

    st.html("""
<div class="section-header">
<div class="section-eyebrow">SCORING</div>
<h2 class="section-title">Comment on calcule <em>le score global.</em></h2>
<p class="section-lead">Le score Sant'active v2 est un indice composite sur 100,
calculé sur 6 dimensions à partir de données open data officielles.
Il permet de classer les 101 départements français et d'identifier
les zones prioritaires d'intervention.</p>
</div>
""")

    st.html("""
<div style="max-width:720px;font-size:14px;line-height:1.8;color:#2B2B2B;margin-bottom:32px;">
<p>Chaque indicateur est normalisé en <strong>rang percentile</strong>
sur les 101 départements — méthode standard utilisée par la DREES
dans ses propres publications. Un score de 50 correspond exactement
à la médiane nationale. Un score de 100 correspond au meilleur
département sur cette dimension. Un score de 0 au pire.</p>
<p>La normalisation en rang percentile présente un avantage crucial
par rapport à la normalisation min-max : elle est insensible aux
valeurs extrêmes. Paris (APL 5.0) et la Guyane (APL 0.6) n'écrasent
pas l'échelle de tous les autres départements.</p>
<p>Le score final est une <strong>moyenne pondérée des 6 dimensions disponibles</strong>.
Si une dimension est manquante pour un département (données insuffisantes),
son poids est redistribué proportionnellement sur les autres dimensions disponibles.
Un département avec moins de 3 dimensions disponibles ne reçoit pas de score global calculé.</p>
</div>
""")

    st.html("""
<div style="border:1px solid #E8E6DD;border-radius:6px;overflow:hidden;margin-bottom:32px;">
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;background:#0A1938;padding:12px 20px;gap:0;">
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.5);">DIMENSION</div>
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.5);">POIDS</div>
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.5);">INDICATEUR · SOURCE · MILLÉSIME</div>
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.5);">DIRECTION</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:white;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Accessibilité soins de ville</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Dimension principale</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">30 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">APL médian départemental<br><span style="color:#9C9A92;">ANCT · Observatoire des territoires · 2023</span></div>
<div style="font-size:12px;color:#1B5E3F;font-weight:600;">Haut = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:#FAFAF8;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Accessibilité physique</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Temps de trajet</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">20 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Temps d'accès médian pondéré par population<br><span style="color:#9C9A92;">Calcul interne · FINESS mars 2026 + INSEE 2021</span></div>
<div style="font-size:12px;color:#A51C30;font-weight:600;">Bas = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:white;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Densité médecins généralistes</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Offre professionnelle</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">20 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Médecins généralistes actifs pour 100&#8239;000 hab.<br><span style="color:#9C9A92;">RPPS · DREES · janv. 2026</span></div>
<div style="font-size:12px;color:#1B5E3F;font-weight:600;">Haut = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:#FAFAF8;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Offre hospitalière</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Structures de soins</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">15 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Hôpitaux + cliniques FINESS pour 100&#8239;000 hab.<br><span style="color:#9C9A92;">FINESS · DREES · mars 2026</span></div>
<div style="font-size:12px;color:#1B5E3F;font-weight:600;">Haut = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:white;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Pression démographique</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Vieillissement de la population</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">10 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Part des 65 ans et plus<br>Les seniors consomment 4× plus de soins (DREES).<br><span style="color:#9C9A92;">INSEE · Recensement 2021</span></div>
<div style="font-size:12px;color:#A51C30;font-weight:600;">Bas = bon<br><span style="font-weight:400;font-size:11px;color:#9C9A92;">(fort vieillissement = forte demande)</span></div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;background:#FAFAF8;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Contexte foncier</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Attractivité à l'installation</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">5 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Prix médian au m² (DVF)<br>Un foncier accessible facilite l'installation médicale.<br><span style="color:#9C9A92;">DVF · DGFiP · 2025</span></div>
<div style="font-size:12px;color:#A51C30;font-weight:600;">Bas = bon<br><span style="font-weight:400;font-size:11px;color:#9C9A92;">(prix bas = installation facilitée)</span></div>
</div>
</div>
""")

    st.html("""
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:32px;">
<div style="padding:12px 20px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-top:3px solid #A51C30;">
<div style="font-size:12px;font-weight:700;color:#A51C30;">CRITIQUE</div>
<div style="font-size:12px;color:#6B6B68;margin-top:4px;">Score ≤ 33e percentile<br>Tiers inférieur national</div>
</div>
<div style="padding:12px 20px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-top:3px solid #E8A838;">
<div style="font-size:12px;font-weight:700;color:#E8A838;">INTERMÉDIAIRE</div>
<div style="font-size:12px;color:#6B6B68;margin-top:4px;">33e → 67e percentile<br>Tiers médian national</div>
</div>
<div style="padding:12px 20px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-top:3px solid #1B5E3F;">
<div style="font-size:12px;font-weight:700;color:#1B5E3F;">FAVORABLE</div>
<div style="font-size:12px;color:#6B6B68;margin-top:4px;">Score ≥ 67e percentile<br>Tiers supérieur national</div>
</div>
</div>
""")

    st.html("""
<div style="max-width:720px;padding:16px 20px;background:#F3F2EC;border-radius:6px;font-size:13px;color:#4B4B48;line-height:1.7;margin-bottom:32px;">
<strong style="color:#0A1938;display:block;margin-bottom:8px;">Pourquoi ces 6 dimensions et ces pondérations ?</strong>
L'APL reçoit le poids le plus fort (30 %) car c'est l'indicateur le plus précis pour mesurer l'accès réel aux soins de ville — il intègre simultanément l'offre, la demande et la distance.
Le temps d'accès et la densité médecins reçoivent chacun 20 % car ils mesurent deux facettes complémentaires de l'accessibilité.
Les établissements hospitaliers (15 %) complètent avec l'offre de soins secondaires.
La pression démographique (10 %) et le contexte foncier (5 %) sont des facteurs de contexte qui modulent l'intensité du besoin et la capacité d'y répondre.
<br><br>
Ces pondérations sont <strong>transparentes et discutables</strong>. Elles reflètent les priorités de Sant'active mais d'autres pondérations seraient défendables selon les objectifs.
</div>
""")

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 3. INDICATEUR APL
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "APL — ACCESSIBILITÉ POTENTIELLE LOCALISÉE",
        f'L\'indicateur de référence {info_tooltip("apl")} <em>de la DREES.</em>',
    )
    _prose(
        "L'APL (Accessibilité Potentielle Localisée) est l'indicateur officiel de "
        "mesure de l'accès aux médecins généralistes en France. Il a été créé en 2012 "
        "conjointement par la DREES et l'IRDES.",
        "Il exprime le nombre de consultations disponibles par an et par habitant, "
        "en tenant compte de trois facteurs simultanément :",
        "<strong>1. L'offre médicale</strong> : nombre de médecins généralistes actifs "
        "dans un rayon de 20 à 30 minutes de trajet, pondéré par leur volume d'activité "
        "réel en ETP (équivalent temps plein).",
        "<strong>2. La demande</strong> : population locale pondérée par l'âge — un "
        "habitant de 75 ans génère environ 4 fois plus de consultations qu'un adulte "
        "de 30 ans.",
        "<strong>3. La distance</strong> : seuls les médecins accessibles dans un temps "
        "de trajet raisonnable sont comptabilisés.",
        "L'APL dépasse les limites de la densité simple : un médecin à 45 minutes "
        "compte peu, même s'il est «\u202fdans le département\u202f». Un médecin à 5 minutes "
        "dans un territoire voisin compte beaucoup.",
        "<strong>Seuil officiel DREES</strong> : un territoire dont l'APL est inférieur "
        "à 2,5 consultations par an et par habitant est considéré en désert médical.",
        "Dans Sant'active, l'APL est affiché à deux niveaux : valeur médiane "
        "départementale (médiane des valeurs communales) et interquartiles P25\u202f/\u202fP75, "
        "qui montrent la dispersion interne du département. Un département avec une "
        "médiane correcte peut masquer des communes très sous-dotées.",
        "Source\u202f: Observatoire des territoires (ANCT), données communes 2023. "
        "Agrégation à la maille département par calcul de médiane sur les 34\u202f852 "
        "communes disponibles. Médiane nationale\u202f: 2,9 consultations/an/habitant (ANCT 2023).",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 4. INDICATEURS COMPLÉMENTAIRES
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "AUTRES INDICATEURS",
        "Les données <em>qui complètent le diagnostic.</em>",
    )

    st.markdown(
        '<div class="sa-tbl-scroll">'
        '<table class="sources-table">'
        "<thead><tr>"
        "<th>Indicateur</th><th>Ce qu'il mesure</th><th>Source</th>"
        "<th>Millésime</th><th>Limite principale</th>"
        "</tr></thead>"
        "<tbody>"
        "<tr>"
        "<td><strong>Médecins généralistes&nbsp;/ 100k hab.</strong></td>"
        "<td>Densité de praticiens actifs libéraux et mixtes</td>"
        "<td>RPPS, traitement DREES</td><td>Janvier 2026</td>"
        "<td>Ne distingue pas temps plein et partiel</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Établissements FINESS&nbsp;/ 100k hab.</strong></td>"
        "<td>Hôpitaux + cliniques agréés</td>"
        "<td>FINESS, DREES</td><td>Mars 2026</td>"
        "<td>Hors établissements médico-sociaux</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Prix médian&nbsp;/m²</strong></td>"
        "<td>Médiane des transactions immobilières DVF</td>"
        "<td>DVF, DGFiP</td><td>2025</td>"
        "<td>Hors zones &lt; 10 transactions (rural très peu dense)</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Part des 65+</strong></td>"
        "<td>% de personnes âgées de 65 ans et plus</td>"
        "<td>INSEE RP</td><td>2021</td>"
        "<td>Recensement quinquennal, peut sous-estimer le vieillissement réel</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Part des &lt;25</strong></td>"
        "<td>% de jeunes de moins de 25 ans</td>"
        "<td>INSEE RP</td><td>2021</td>"
        "<td>Idem</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Pathologies chroniques</strong></td>"
        "<td>Taux de prévalence standardisé par pathologie (diabète, HTA, "
        "insuffisance cardiaque…)</td>"
        "<td>CNAM / Ameli open data</td><td>2023</td>"
        "<td>Estimations indirectes issues de la consommation de soins</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Score environnemental</strong></td>"
        "<td>Composite qualité de l'air + eau + espaces verts</td>"
        "<td>SPF / DREAL</td><td>Variable</td>"
        "<td>Régional uniquement — non intégré au score global</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Temps d'accès médian</strong></td>"
        "<td>Temps de trajet médian vers l'établissement de santé le plus proche, "
        "pondéré par population communale</td>"
        "<td>Calcul interne FINESS + INSEE</td><td>2026</td>"
        "<td>Trajet routier, pas temps d'attente aux urgences</td>"
        "</tr>"
        "</tbody></table>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 5. DÉLAIS RDV ESTIMÉS
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "DÉLAIS D'ACCÈS AUX SPÉCIALISTES",
        f'Une estimation {info_tooltip("delais_rdv")} <em>documentée et transparente.</em>',
    )
    _prose(
        "Les délais de rendez-vous chez les spécialistes constituent un enjeu majeur "
        "de l'accès aux soins, distincts de la simple présence de médecins sur le "
        "territoire. Aucune source open data ne fournit ces délais à la maille "
        "départementale en France à ce jour.",
        "Sant'active utilise une estimation en deux étapes.",
    )

    st.markdown(
        '<div class="method-content">'
        "<p><strong>Étape 1 — Base nationale réelle (DREES 2016-2017)</strong></p>"
        "<p>L'enquête DREES «\u202fDélais d'attente en matière d'accès aux soins\u202f» "
        "(Études et Résultats n°1085, octobre 2018) est la seule enquête française "
        "avec protocole statistique rigoureux sur ce sujet (label CNIS, 40\u202f000 "
        "personnes, 9 spécialités). Elle fournit les délais médians nationaux ci-dessous.</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="sa-tbl-scroll">'
        '<table class="sources-table">'
        "<thead><tr>"
        "<th>Spécialité</th><th>Délai médian national</th><th>Délai moyen national</th>"
        "</tr></thead>"
        "<tbody>"
        "<tr><td>Médecin généraliste</td><td>2 jours</td><td>6 jours</td></tr>"
        "<tr><td>Pédiatre</td><td>21 jours</td><td>21 jours</td></tr>"
        "<tr><td>Radiologue</td><td>21 jours</td><td>21 jours</td></tr>"
        "<tr><td>Chirurgien-dentiste</td><td>30 jours</td><td>30 jours</td></tr>"
        "<tr><td>Gynécologue</td><td>45 jours</td><td>45 jours</td></tr>"
        "<tr><td>Rhumatologue</td><td>45 jours</td><td>45 jours</td></tr>"
        "<tr><td>Cardiologue</td><td>50 jours</td><td>50 jours</td></tr>"
        "<tr><td>Dermatologue</td><td>52 jours</td><td>61 jours</td></tr>"
        "<tr><td>Ophtalmologue</td><td>52 jours</td><td>80 jours</td></tr>"
        "</tbody></table>"
        "</div>",
        unsafe_allow_html=True,
    )

    _prose(
        "<strong>Étape 2 — Ajustement départemental par l'APL</strong>",
        "La DREES établit dans cette même enquête que les délais sont significativement "
        "plus longs dans les territoires à faible APL. On applique un facteur "
        "d'ajustement\u202f:",
    )

    st.markdown(
        '<div style="background:#F3F2EC;border-radius:4px;padding:16px 24px;'
        'margin:0 0 20px;font-family:monospace;font-size:14px;color:#2B2B2B;">'
        "délai_estimé = délai_national × (APL_nationale / APL_département)"
        "</div>",
        unsafe_allow_html=True,
    )

    _prose(
        "L'APL nationale utilisée est 2,9 (médiane ANCT 2023). Le facteur est plafonné "
        "à ×3 pour éviter des valeurs aberrantes dans les territoires très sous-dotés "
        "(DOM, Corse).",
        "<strong>Exemple 1 — Cher (APL\u202f=\u202f1,7)</strong>\u202f: facteur\u202f=\u202f2,9\u202f/\u202f1,7\u202f=\u202f1,71 "
        "→ délai ophtalmo estimé à <strong>89\u202fjours</strong> (vs 52\u202fjours national).",
        "<strong>Exemple 2 — Métropole de Lyon (APL\u202f≈\u202f3,0)</strong>\u202f: facteur\u202f≈\u202f0,97 "
        "→ délai ophtalmo estimé à <strong>50\u202fjours</strong>.",
        "Ces valeurs sont des estimations indicatives, non des mesures directes. "
        "Elles visent à donner un ordre de grandeur différencié par territoire, "
        "pas une prédiction exacte.",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 6. LIMITES ASSUMÉES
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "LIMITES",
        "Ce que Sant'active <em>ne fait pas.</em>",
    )

    limites = [
        (
            "01",
            "Pas de données infra-départementales sur la santé",
            "Les indicateurs RPPS, CNAM et APL agrégés au département masquent les "
            "disparités internes. Un département avec une bonne médiane peut contenir "
            "des cantons en désert médical. La carte communale (prix m² et temps "
            "d'accès) permet une lecture partielle, mais les données de santé à la "
            "commune ne sont pas disponibles en open data.",
        ),
        (
            "02",
            "Délais RDV estimés, non mesurés",
            "Les délais affichés par spécialité sont des estimations calculées à partir "
            "de données nationales DREES 2016-2017, ajustées par l'APL. Ce ne sont pas "
            "des mesures directes. La situation s'est probablement dégradée depuis 2017. "
            "Une future intégration de données Doctolib départementales améliorerait "
            "significativement cet indicateur.",
        ),
        (
            "03",
            "Score environnemental exclu du score global",
            "L'indicateur environnemental (qualité de l'air, eau, espaces verts) n'est "
            "disponible qu'à la maille régionale. L'appliquer identiquement à tous les "
            "départements d'une région introduirait un biais — deux départements très "
            "différents recevraient le même score environnemental. Il est affiché en "
            "lecture seule.",
        ),
        (
            "04",
            "Données avec décalage temporel",
            "Le recensement INSEE date de 2021. Les données pathologies CNAM de 2023. "
            "Le RPPS est à jour à janvier 2026, FINESS à mars 2026. L'APL est millésimé "
            "2023. Ces décalages sont normaux dans la statistique publique mais peuvent "
            "sous-estimer des évolutions récentes (désertification accélérée dans "
            "certains départements depuis 2023).",
        ),
        (
            "05",
            "DOM-TOM partiellement couverts",
            "Mayotte n'est pas couverte par l'APL ANCT 2023. La Guyane (APL\u202f=\u202f0,6) "
            "et la Haute-Corse (APL\u202f=\u202f0,3) présentent des situations extrêmes pour "
            "lesquelles le plafonnement du facteur de délai (×3) s'applique, limitant "
            "la précision des estimations.",
        ),
        (
            "06",
            "Sant'active n'est pas un outil de pilotage budgétaire",
            "Les recommandations générées sont des orientations basées sur des "
            "indicateurs agrégés. Elles ne constituent pas une évaluation de politique "
            "publique et ne doivent pas être utilisées seules pour allouer des "
            "ressources. Elles visent à orienter le diagnostic, pas à le remplacer.",
        ),
    ]

    cards_html = ""
    for num, title, body in limites:
        cards_html += (
            f'<div class="limit-card">'
            f'<div class="limit-number">{num}</div>'
            f'<div class="limit-title">{title}</div>'
            f'<div class="limit-body">{body}</div>'
            f'</div>'
        )
    st.markdown(cards_html, unsafe_allow_html=True)

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ── Contact ───────────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">CONTACT</div>'
        '<h2 class="section-title">Une question, <em>une erreur\u202f?</em></h2>'
        '<p class="section-lead">'
        "Sant'active est un outil en développement actif. Si vous repérez une "
        "erreur de données, une incohérence ou souhaitez suggérer une amélioration, "
        "contactez l'équipe."
        "</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("""
<div style="margin-top:48px;padding:20px 24px;
            background:#F3F2EC;border-radius:6px;
            display:flex;align-items:center;
            justify-content:space-between;flex-wrap:wrap;gap:16px;">
    <div>
        <div style="font-size:11px;font-weight:700;letter-spacing:0.08em;
                    text-transform:uppercase;color:#6B6B68;margin-bottom:6px;">
            CONTACT · QUESTIONS MÉTHODOLOGIQUES
        </div>
        <div style="font-size:14px;color:#0A1938;">
            Pour toute question sur les données, les calculs ou la méthodologie :
        </div>
    </div>
    <a href="mailto:santactive.esdata@gmail.com"
       style="padding:12px 24px;background:#1A3D8F;color:white;
              border-radius:4px;text-decoration:none;font-size:14px;
              font-weight:500;white-space:nowrap;">
        santactive.esdata@gmail.com
    </a>
</div>
""", unsafe_allow_html=True)
