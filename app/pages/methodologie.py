"""Page Méthodologie — documentation complète, citable dans un rapport officiel."""

from __future__ import annotations

import streamlit as st

from ..components.nav import NavCrumb, render_breadcrumb

from ..router import navigate
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


# ── Render principal ──────────────────────────────────────────────────────────

_TABLE_DIMENSIONS = '''
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
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">{APL_LIGNE}<br><span style="color:#9C9A92;">DREES · APL aux médecins généralistes · 2023</span></div>
<div style="font-size:12px;color:#2B2B2B;font-weight:600;">Haut = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:#FAFAF8;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Accessibilité physique</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Temps de trajet</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">20 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Médiane simple des temps d'accès communaux (non pondérée ; 0 = offre dans la commune)<br><span style="color:#9C9A92;">Calcul interne de l'équipe · 2026 · méthode de production à documenter</span></div>
<div style="font-size:12px;color:#2B2B2B;font-weight:600;">Bas = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:white;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Densité médecins généralistes</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Offre professionnelle</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">20 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">{MED_LIGNE}</div>
<div style="font-size:12px;color:#2B2B2B;font-weight:600;">Haut = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:#FAFAF8;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Offre hospitalière</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Structures de soins</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">15 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">{ETABS_LIGNE}<br><span style="color:#9C9A92;">FINESS · mars 2026 · nombre de sites, pas de capacité</span></div>
<div style="font-size:12px;color:#2B2B2B;font-weight:600;">Haut = bon</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;border-bottom:1px solid #E8E6DD;background:white;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Pression démographique</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Vieillissement de la population</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">10 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Part des 65 ans et plus<br>Les 75-79 ans consomment environ 1,6 fois la moyenne de soins de médecine générale, les 90 ans et plus 2,3 fois (pondérations APL DREES 2023).<br><span style="color:#9C9A92;">INSEE · Recensement 2021</span></div>
<div style="font-size:12px;color:#2B2B2B;font-weight:600;">Bas = bon<br><span style="font-weight:400;font-size:11px;color:#9C9A92;">(fort vieillissement = forte demande)</span></div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr 2fr 1fr;padding:14px 20px;background:#FAFAF8;gap:0;align-items:start;">
<div><div style="font-size:13px;font-weight:700;color:#0A1938;">Contexte foncier</div><div style="font-size:11px;color:#9C9A92;margin-top:3px;">Attractivité à l'installation</div></div>
<div style="font-size:22px;font-weight:300;color:#1A3D8F;">5 %</div>
<div style="font-size:12px;color:#4B4B48;line-height:1.5;">Prix médian au m² (DVF)<br>Un foncier accessible facilite l'installation médicale.<br><span style="color:#9C9A92;">DVF · DGFiP · 2025</span></div>
<div style="font-size:12px;color:#2B2B2B;font-weight:600;">Bas = bon<br><span style="font-weight:400;font-size:11px;color:#9C9A92;">(prix bas = installation facilitée)</span></div>
</div>
</div>
'''


def _cfg() -> dict:
    """Paramètres actifs du moteur, pour que la page décrive ce qui est exécuté."""
    from ..config import (APL_AGREGATION, APL_LABEL, APL_METHODE, ETABS_CATEGORIES,
                          ETABS_DEFINITION, SOURCE_EFFECTIFS)
    return dict(apl_methode=APL_METHODE, apl_label=APL_LABEL, apl_agregation=APL_AGREGATION,
                etabs_def=ETABS_DEFINITION, etabs_cats=ETABS_CATEGORIES[ETABS_DEFINITION],
                source=SOURCE_EFFECTIFS)


def render(data: dict) -> None:
    cfg = _cfg()
    master = data.get("master")
    apl_nat = (float(master["apl_dept"].median()) if master is not None and "apl_dept" in master else float("nan"))

    render_breadcrumb([
        NavCrumb("Accueil", "home"),
        NavCrumb("Méthodologie"),
    ], key_prefix="methodo_bc")

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
        "santé. Il ne produit pas de vérité absolue sur un territoire, il synthétise "
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
Il permet de classer les 100 départements analysés (Mayotte exclue) et d'identifier
les zones prioritaires d'intervention.</p>
</div>
""")

    st.html("""
<div style="max-width:720px;font-size:14px;line-height:1.8;color:#2B2B2B;margin-bottom:32px;">
<p>Chaque indicateur est normalisé en <strong>rang percentile</strong>
sur les 100 départements analysés (rang percentile, méthode usuelle de normalisation)
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

    apl_ligne = {
        "ponderee": "APL moyen pondéré par la population standardisée (méthode DREES) ; médiane communale conservée pour comparaison",
        "mediane": "Médiane simple des APL communaux (chaque commune pèse autant)",
    }[cfg["apl_methode"]]
    med_ligne = {
        "drees": "Généralistes actifs au 1<sup>er</sup> janvier 2026 (personnes distinctes, tous modes d'exercice) / population INSEE 2021 × 100&#8239;000<br><span style=\"color:#9C9A92;\">DREES · RPPS · 2026</span>",
        "equipe": "Lignes du fichier territorial de l'équipe (présences, pas effectifs) / population INSEE 2021 — mode historique de comparaison<br><span style=\"color:#9C9A92;\">fichier équipe · 2026</span>",
    }[cfg["source"]]
    etabs_ligne = {
        "actuelle": "Sites FINESS : centres hospitaliers (CH, CHR) + établissements privés SSR, pour 100&#8239;000 hab. ; cliniques MCO, hôpitaux locaux et CHS non comptés",
        "court_sejour": "Sites FINESS de court séjour : CH, CHR, hôpitaux locaux, privés MCO, centres de lutte contre le cancer, pour 100&#8239;000 hab.",
    }[cfg["etabs_def"]]
    st.html(_TABLE_DIMENSIONS.format(APL_LIGNE=apl_ligne, MED_LIGNE=med_ligne, ETABS_LIGNE=etabs_ligne))


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
L'APL reçoit le poids le plus fort (30 %) car c'est l'indicateur le plus précis pour mesurer l'accès réel aux soins de ville : il intègre simultanément l'offre, la demande et la distance.
Le temps d'accès et la densité médecins reçoivent chacun 20 % car ils mesurent deux facettes complémentaires de l'accessibilité.
Les établissements hospitaliers (15 %) complètent avec l'offre de soins secondaires.
La pression démographique (10 %) et le contexte foncier (5 %) sont des facteurs de contexte qui modulent l'intensité du besoin et la capacité d'y répondre.
<br><br>
Ces pondérations sont <strong>transparentes et discutables</strong>. Elles reflètent les priorités de Sant'active mais d'autres pondérations seraient défendables selon les objectifs.
<br><br>
<strong>Limite connue.</strong> L'APL, la densité de généralistes et le temps d'accès (70 % du score) mesurent trois facettes d'une même réalité, l'offre de médecine générale : le score global est d'abord un indice d'offre et d'accès (corrélation 0,99 avec un indice d'offre seul), les besoins sanitaires (vieillissement, pathologies) n'y pèsent que 10 %. Une analyse de sensibilité et une étude de deux indices complémentaires (offre/accès et besoins) sont documentées dans le dépôt (scripts/analyse) ; aucun changement de pondération n'est appliqué sans validation.
</div>
""")

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 3. INDICATEUR APL
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "APL : ACCESSIBILITÉ POTENTIELLE LOCALISÉE",
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
        "<strong>2. La demande</strong> : population locale pondérée par l'âge : un "
        "habitant de 75 à 79 ans pèse 1,6 fois la consommation moyenne de médecine générale, "
        "un habitant de 30 à 34 ans 0,8 fois (pondérations DREES 2023).",
        "<strong>3. La distance</strong> : seuls les médecins accessibles dans un temps "
        "de trajet raisonnable sont comptabilisés.",
        "L'APL dépasse les limites de la densité simple : un médecin à 45 minutes "
        "compte peu, même s'il est «\u202fdans le département\u202f». Un médecin à 5 minutes "
        "dans un territoire voisin compte beaucoup.",
        "<strong>Repère 2,5</strong> : un APL inférieur à 2,5 consultations par an et par "
        "habitant est le repère de sous-densité utilisé dans la méthodologie nationale de "
        "zonage des médecins généralistes. Il s'applique à des communes ou territoires de "
        "vie-santé, pas à un département entier\u202f; il n'existe pas de définition légale "
        "du «\u202fdésert médical\u202f».",
        f"<strong>Agrégation départementale active\u202f: {cfg['apl_agregation']}.</strong> "
        + ("La DREES prescrit cette pondération pour tout APL agrégé (en-tête du fichier "
           "communal). La médiane simple des communes, utilisée auparavant, donnait 0,3 à la "
           "Haute-Corse contre 3,7 en moyenne pondérée\u202f: elle reste calculée pour comparaison "
           "(colonne apl_median_dept, mode SANTACTIVE_APL_METHODE=mediane)."
           if cfg["apl_methode"] == "ponderee" else
           "Chaque commune pèse autant quelle que soit sa population\u202f; la DREES recommande "
           "une moyenne pondérée par la population standardisée, disponible en option."),
        "Trois lectures complètent la valeur départementale sur chaque fiche\u202f: la part de "
        "population vivant dans une commune sous le repère 2,5, les quartiles communaux "
        "pondérés par la population (dispersion interne) et le nombre de communes sous 2,5.",
        f"Référence nationale affichée\u202f: médiane des 100 valeurs départementales "
        f"({apl_nat:.2f} consultations/an/habitant)\u202f; APL national pondéré DREES 2023\u202f: 3,74\u202f; "
        "16,6\u202f% de la population vit dans une commune sous 2,5.",
        "Source\u202f: DREES, APL aux médecins généralistes, millésime 2023 (diffusé aussi par "
        "l'Observatoire des territoires, ANCT), 34\u202f954 communes hors Mayotte, population "
        "standardisée 2021. Licence Ouverte 2.0.",
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
        "<td>Effectif de généralistes actifs (tous modes d'exercice, personnes distinctes) / population INSEE 2021</td>"
        "<td>DREES, RPPS (si activé)</td><td>1<sup>er</sup> janvier 2026</td>"
        "<td>Têtes, pas ETP ; salariés inclus</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Établissements FINESS&nbsp;/ 100k hab.</strong></td>"
        "<td>Sites CH + CHR + établissements privés SSR</td>"
        "<td>FINESS</td><td>Mars 2026</td>"
        "<td>Nombre de sites, pas de capacité ; MCO privé, hôpitaux locaux et CHS non comptés</td>"
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
        "<td>Prévalence brute par pathologie (patients pris en charge / population) ; "
        "prévalence standardisée sur l'âge affichée en complément</td>"
        "<td>CNAM, cartographie des pathologies</td><td>2023</td>"
        "<td>Repérage par la consommation de soins ; secret statistique sur les petites cellules</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Score environnemental</strong></td>"
        "<td>Composite qualité de l'air + eau + espaces verts</td>"
        "<td>SPF / DREAL</td><td>Variable</td>"
        "<td>Régional uniquement, non intégré au score global</td>"
        "</tr>"
        "<tr>"
        "<td><strong>Temps d'accès médian</strong></td>"
        "<td>Temps communal (0 = offre présente dans la commune), médiane simple des "
        "communes par département, non pondérée</td>"
        "<td>Calcul interne de l'équipe</td><td>2026</td>"
        "<td>Méthode de production à documenter ; les communes à 0 min correspondent à "
        "99\u202f% à celles où un généraliste est recensé</td>"
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
        "<p><strong>Étape 1 : Base nationale réelle (DREES 2016-2017)</strong></p>"
        "<p>L'enquête DREES «\u202fDélais d'attente en matière d'accès aux soins\u202f» "
        "(Études et Résultats n°1085, octobre 2018) est la seule enquête française "
        "avec protocole statistique rigoureux sur ce sujet (label CNIS, 40\u202f000 "
        "personnes, 9 spécialités, France métropolitaine, résultats provisoires). Elle fournit les "
        "délais nationaux ci-dessous (tableau 1 de la publication)\u202f; elle n'est pas déclinée "
        "par région ni par département.</p>"
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
        "<tr><td>Pédiatre</td><td>8 jours</td><td>22 jours</td></tr>"
        "<tr><td>Radiologue</td><td>11 jours</td><td>21 jours</td></tr>"
        "<tr><td>Chirurgien-dentiste</td><td>17 jours</td><td>28 jours</td></tr>"
        "<tr><td>Rhumatologue</td><td>31 jours</td><td>45 jours</td></tr>"
        "<tr><td>Gynécologue</td><td>32 jours</td><td>44 jours</td></tr>"
        "<tr><td>Cardiologue</td><td>37 jours</td><td>50 jours</td></tr>"
        "<tr><td>Dermatologue</td><td>50 jours</td><td>61 jours</td></tr>"
        "<tr><td>Ophtalmologue</td><td>52 jours</td><td>80 jours</td></tr>"
        "</tbody></table>"
        "</div>",
        unsafe_allow_html=True,
    )

    _prose(
        "<strong>Étape 2 : Ajustement départemental par l'APL</strong>",
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
        f"L'APL national de référence est la médiane des valeurs départementales "
        f"({apl_nat:.2f}, même méthode d'agrégation que l'APL du département). Le facteur est "
        "plafonné à ×3.",
        "<strong>Limites</strong>\u202f: la DREES documente une corrélation entre faible "
        "accessibilité et délais plus longs, pas une proportionnalité inverse\u202f; l'APL ne "
        "porte que sur les généralistes alors que le proxy module aussi les délais de "
        "spécialistes\u202f; un APL supérieur à la référence raccourcit le délai estimé, ce qui "
        "n'est pas établi. Ces valeurs sont des estimations indicatives, non des mesures. "
        "Aucune valeur régionale de délai n'est affichée\u202f: le fichier régional utilisé "
        "auparavant n'avait pas de source identifiable.",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 6. AIDE À LA DÉCISION TERRITORIALE
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "AIDE À LA DÉCISION TERRITORIALE",
        "Au-delà de la mesure, <em>orienter l'action.</em>",
        lead=(
            "Sant'active ne se limite plus à mesurer la fragilité d'un territoire. "
            "L'outil vise à répondre à quatre questions complémentaires pour "
            "l'aide à la décision publique et philanthropique."
        ),
    )

    st.markdown("""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:28px;">
<div style="padding:14px 18px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-left:3px solid #1A3D8F;">
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;">Question 1</div>
<div style="font-size:15px;font-weight:600;color:#0A1938;margin-top:6px;">Où agir ?</div>
</div>
<div style="padding:14px 18px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-left:3px solid #1A3D8F;">
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;">Question 2</div>
<div style="font-size:15px;font-weight:600;color:#0A1938;margin-top:6px;">Pour quel public ?</div>
</div>
<div style="padding:14px 18px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-left:3px solid #1A3D8F;">
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;">Question 3</div>
<div style="font-size:15px;font-weight:600;color:#0A1938;margin-top:6px;">Sur quelle problématique ?</div>
</div>
<div style="padding:14px 18px;background:white;border:1px solid #E8E6DD;border-radius:4px;border-left:3px solid #1A3D8F;">
<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;">Question 4</div>
<div style="font-size:15px;font-weight:600;color:#0A1938;margin-top:6px;">Avec quel type d'action ?</div>
</div>
</div>
""", unsafe_allow_html=True)

    _prose(
        "Cette logique est particulièrement pensée pour les ARS, les collectivités, "
        "les fondations, les acteurs de prévention et les porteurs d'expérimentation.",
        "L'objectif n'est pas d'identifier uniquement les territoires les plus fragiles, "
        "mais les territoires où une action peut être <strong>utile, ciblée et "
        "déployable</strong>, compte tenu du besoin observé et des relais existants.",
        "La fiche région traduit cette logique en blocs de lecture synthétique. "
        "Les calculs sous-jacents restent distincts du score Sant'active départemental "
        "et ne modifient ni les pondérations ni le classement national.",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:32px 0;'>",
                unsafe_allow_html=True)

    # ── Priorisation des territoires ──────────────────────────────────────────

    _section(
        "PRIORISATION DES TERRITOIRES",
        "Comment sont classés <em>les départements d'une région.</em>",
    )
    _prose(
        "Sur la fiche région, chaque département reçoit un score de priorité sur 100 "
        "calculé sur des rangs <strong>nationaux</strong> (les 100 départements analysés), "
        "pour rester comparable d'une région à l'autre\u202f: les régions à un ou deux "
        "départements ne sont plus classées contre elles-mêmes.",
        "Score de priorité = moyenne à poids égaux du <strong>besoin</strong> (fragilité "
        "territoriale et complément du score global) et du <strong>volume</strong> "
        "(population et publics concernés). La <strong>faisabilité</strong> est calculée et "
        "affichée à part\u202f; elle n'entre pas dans le score. Les poids égaux sont un choix "
        "explicite, faute de référence validée pour d'autres.",
    )

    st.markdown("""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-bottom:24px;">
<div style="padding:18px 20px;background:white;border:1px solid #E8E6DD;border-radius:6px;border-top:3px solid #A51C30;">
<div style="font-size:12px;font-weight:700;color:#A51C30;margin-bottom:10px;">1 · FRAGILITÉ TERRITORIALE</div>
<div style="font-size:13px;color:#4B4B48;line-height:1.65;">
Mesure la vulnérabilité sanitaire du département&nbsp;: accès aux soins, APL,
densité médicale, offre hospitalière, vieillissement, isolement géographique.
</div>
</div>
<div style="padding:18px 20px;background:white;border:1px solid #E8E6DD;border-radius:6px;border-top:3px solid #1A3D8F;">
<div style="font-size:12px;font-weight:700;color:#1A3D8F;margin-bottom:10px;">2 · VOLUME CONCERNÉ</div>
<div style="font-size:13px;color:#4B4B48;line-height:1.65;">
Volume observé&nbsp;: population INSEE, seniors, communes à plus de 15 min,
patients CNAM (prévalence et effectifs), en rangs nationaux.
</div>
</div>
<div style="padding:18px 20px;background:white;border:1px solid #E8E6DD;border-radius:6px;border-top:3px solid #1B5E3F;">
<div style="font-size:12px;font-weight:700;color:#1B5E3F;margin-bottom:10px;">3 · FAISABILITÉ D'ACTION</div>
<div style="font-size:13px;color:#4B4B48;line-height:1.65;">
Évalue les conditions de déploiement&nbsp;: structures existantes, professionnels
présents, relais de terrain, accessibilité, contexte foncier.
</div>
</div>
</div>
<div style="max-width:720px;padding:16px 20px;background:#F3F2EC;border-radius:6px;font-size:13px;color:#4B4B48;line-height:1.7;margin-bottom:32px;">
<strong style="color:#0A1938;">Principe clé.</strong>
Un territoire très fragile reste prioritaire même si la capacité d'action locale
est faible : besoin et faisabilité sont deux lectures distinctes. Le score de
priorité combine besoin et volume de population ; la faisabilité renseigne sur
les conditions de déploiement, pas sur l'urgence du besoin.
</div>
""", unsafe_allow_html=True)

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:32px 0;'>",
                unsafe_allow_html=True)

    # ── Publics prioritaires ──────────────────────────────────────────────────

    _section(
        "PUBLICS PRIORITAIRES",
        "Identifier <em>les populations concernées.</em>",
    )
    _prose(
        "Les données CNAM (pathologies chroniques) et INSEE (structure d'âge) "
        "permettent d'identifier, à l'échelle régionale, les publics les plus "
        "concernés par un enjeu de santé.",
        "Plusieurs profils peuvent ressortir selon les régions&nbsp;: seniors, "
        "maladies cardiovasculaires, diabète, cancers, maladies respiratoires, "
        "santé mentale, maladies neurologiques ou dégénératives.",
        "Pour chaque axe, Sant'active indique le volume <strong>observé</strong> "
        "(seniors INSEE, patients CNAM), les départements les plus touchés et un "
        "niveau d'importance fondé sur la position de la région dans la distribution "
        "nationale des départements (part des 65 ans et plus de la région, prévalence "
        "brute régionale). Une région jeune n'a donc pas les seniors comme public "
        "prioritaire par construction.",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:32px 0;'>",
                unsafe_allow_html=True)

    # ── Leviers d'action ──────────────────────────────────────────────────────

    _section(
        "LEVIERS D'ACTION RECOMMANDÉS",
        "Des réponses <em>adaptées au profil territorial.</em>",
    )
    _prose(
        "Sant'active ne repose pas sur une logique unique de recrutement de "
        "médecins. L'outil peut faire émerger plusieurs familles d'actions "
        "cohérentes avec les indicateurs observés.",
    )

    st.markdown("""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px;">
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Prévention</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Dépistage</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Téléexpertise</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Télésuivi</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Coordination territoriale</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Consultations avancées</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Accompagnement des seniors</span>
<span style="padding:6px 12px;background:#F3F2EC;border-radius:4px;font-size:12px;color:#4B4B48;">Navettes santé</span>
</div>
""", unsafe_allow_html=True)

    _prose(
        "Ces leviers ne sont <strong>jamais affichés systématiquement</strong>. "
        "Ils sont générés à partir du profil réel observé sur le territoire "
        "(APL, pathologies CNAM, part des seniors, professionnels et établissements "
        "présents, communes à plus de 15 min). Chaque levier cite TOUS les départements "
        "qui remplissent sa condition et sa portée observée (part de la population "
        "régionale des départements ciblés)\u202f; les volumes affichés sont des quantités "
        "observées (INSEE, CNAM, DREES), jamais des multiplicateurs.",
        "Un levier n'est proposé que lorsqu'il est cohérent avec les indicateurs "
        "disponibles. Deux régions aux profils différents n'affichent donc pas "
        "forcément les mêmes recommandations.",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:32px 0;'>",
                unsafe_allow_html=True)

    # ── Logique de recommandation ─────────────────────────────────────────────

    _section(
        "LOGIQUE DE RECOMMANDATION",
        "De la tension observée <em>à l'action proposée.</em>",
    )

    st.markdown("""
<div style="max-width:520px;margin:0 auto 24px;padding:24px;background:white;border:1px solid #E8E6DD;border-radius:6px;">
<div style="padding:14px 16px;background:#FEF3F3;border-left:3px solid #A51C30;border-radius:4px;margin-bottom:12px;">
<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">Tension observée</div>
<div style="font-size:13px;color:#4B4B48;line-height:1.5;">Ex.&nbsp;: APL faible, délais élevés, prévalence chronique importante</div>
</div>
<div style="text-align:center;color:#C4C2B8;font-size:18px;margin:8px 0;">↓</div>
<div style="padding:14px 16px;background:#EEF2FA;border-left:3px solid #1A3D8F;border-radius:4px;margin-bottom:12px;">
<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">Population concernée</div>
<div style="font-size:13px;color:#4B4B48;line-height:1.5;">Ex.&nbsp;: seniors, patients chroniques, publics en attente de spécialistes</div>
</div>
<div style="text-align:center;color:#C4C2B8;font-size:18px;margin:8px 0;">↓</div>
<div style="padding:14px 16px;background:#F0F7F3;border-left:3px solid #1B5E3F;border-radius:4px;">
<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9C9A92;margin-bottom:4px;">Type d'action recommandé</div>
<div style="font-size:13px;color:#4B4B48;line-height:1.5;">Ex.&nbsp;: téléexpertise, prévention ciblée, coordination de parcours</div>
</div>
</div>
""", unsafe_allow_html=True)

    _prose(
        "Sant'active ne cherche pas à prédire l'impact futur d'une politique "
        "publique. L'outil vise à produire des <strong>pistes d'intervention "
        "cohérentes</strong> avec les données observées, afin d'éclairer le "
        "diagnostic territorial avant toute décision d'engagement.",
    )

    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:40px 0;'>",
                unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # 7. LIMITES ASSUMÉES
    # ══════════════════════════════════════════════════════════════════════════

    _section(
        "LIMITES",
        "Ce que Sant'active <em>ne fait pas.</em>",
    )

    limites = [
        (
            "01",
            "Lecture infra-départementale partielle",
            "Les effectifs DREES et les prévalences CNAM sont agrégés au département. "
            "Seul l'APL est connu à la commune (DREES)\u202f: il alimente la part de population "
            "sous 2,5, les quartiles communaux et la simulation de capacité. La carte "
            "communale (prix m², temps d'accès) reste partielle (couverture des noms de "
            "communes, pas de données de santé communales).",
        ),
        (
            "02",
            "Délais RDV estimés, non mesurés",
            "Les délais départementaux par spécialité sont des estimations (médianes "
            "nationales DREES 2016-2017 modulées par l'APL), pas des mesures. Les délais "
            "régionaux affichés auparavant ont été retirés faute de source identifiable.",
        ),
        (
            "03",
            "Score environnemental exclu du score global",
            "L'indicateur environnemental (qualité de l'air, eau, espaces verts) n'est "
            "disponible qu'à la maille régionale. L'appliquer identiquement à tous les "
            "départements d'une région introduirait un biais : deux départements très "
            "différents recevraient le même score environnemental. Il est affiché en "
            "lecture seule.",
        ),
        (
            "04",
            "Données avec décalage temporel",
            "Population et structure par âge INSEE 2021, pathologies CNAM 2023, APL 2023, "
            "effectifs DREES/RPPS au 1<sup>er</sup> janvier 2026 (densités DREES rapportées à la "
            "population 2026, nos densités à la population 2021\u202f: écart médian +1,3\u202f%), "
            "FINESS mars 2026, DVF 2025, délais DREES 2016-2017. Ces décalages sont normaux "
            "dans la statistique publique et sont indiqués sur chaque indicateur.",
        ),
        (
            "05",
            "DOM-TOM partiellement couverts",
            "Mayotte est hors champ de l'APL DREES et exclue du score (100 départements "
            "analysés). La médiane communale non pondérée pénalise les départements à "
            "nombreux petits villages\u202f: Haute-Corse 0,3 et Corse-du-Sud 1,9 en médiane, "
            "contre 3,7 et 3,9 en moyenne pondérée par la population (méthode DREES). "
            "La Guyane (0,6 en médiane, 2,0 pondérée) reste la plus sous-dotée.",
        ),
        (
            "06",
            "Sant'active n'est pas un outil de pilotage budgétaire",
            "Les recommandations générées sont des orientations basées sur des "
            "indicateurs agrégés. Elles ne constituent pas une évaluation de politique "
            "publique et ne doivent pas être utilisées seules pour allouer des "
            "ressources. Elles visent à orienter le diagnostic, pas à le remplacer.",
        ),
        (
            "07",
            "Priorités territoriales et leviers recommandés",
            "Les priorités territoriales et leviers recommandés constituent des "
            "aides à la décision et non des prescriptions. Ils reposent sur des règles "
            "transparentes construites à partir des données disponibles et ne "
            "remplacent pas l'expertise des acteurs locaux.",
        ),
        (
            "08",
            "Effectifs, présence et temps d'accès\u202f: trois choses différentes",
            "Les effectifs DREES comptent des personnes (têtes, pas ETP, salariés inclus). "
            "Le fichier territorial de l'équipe ne contient pas d'effectifs\u202f: il sert à la "
            "présence locale d'une spécialité (villes où elle est recensée). Le temps d'accès "
            "communal est un calcul interne dont la méthode de production reste à documenter\u202f; "
            "les communes à 0 min sont celles où une offre de médecine générale est recensée. "
            "En Guyane, seules 82\u202f% des communes sont couvertes.",
        ),
        (
            "09",
            "Renforcement théorique de capacité\u202f: une simulation",
            "Les ETP affichés résultent d'une simulation statique (déficit de consultations "
            "sous un seuil d'APL, converti à 5\u202f400 actes par ETP, convention DREES, fourchette "
            "3\u202f600 à 6\u202f000). Ils surestiment le besoin (effets de voisinage ignorés) et ne "
            "sont ni un effectif officiel de médecins manquants ni un objectif de recrutement.",
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
