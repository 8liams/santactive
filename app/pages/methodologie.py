"""Page Méthodologie — organisée par fonctionnalité, pédagogique, avec ancres.

Sections (ancres reprises par les liens « Comprendre cette analyse » des pages) : score, prioriser,
diagnostic, comparer, simuler, sources, limites. Pour chaque mécanisme : la question à laquelle il
répond, comment il fonctionne (étapes, mini-formule, pondérations et seuils réellement utilisés),
comment interpréter le résultat et ses limites. Aucun détail d'implémentation, d'audit ni
d'historique : ces éléments restent dans la documentation technique du dépôt.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from ..components.aide import SECTIONS
from ..components.nav import NavCrumb, internal_href, render_breadcrumb


# ── Helpers HTML ──────────────────────────────────────────────────────────────

def _section(anchor: str, eyebrow: str, title: str, question: str) -> None:
    st.markdown(f'<div id="{anchor}" style="position:relative;top:-72px;"></div>'
                f'<div class="section-header"><div class="section-eyebrow">{eyebrow}</div>'
                f'<h2 class="section-title">{title}</h2></div>'
                f'<div class="meth-q">Question : {question}</div>', unsafe_allow_html=True)


def _prose(*paragraphs: str) -> None:
    st.markdown('<div class="method-content">' + "".join(f"<p>{p}</p>" for p in paragraphs) + "</div>",
                unsafe_allow_html=True)


def _steps(*steps: tuple[str, str]) -> None:
    st.markdown('<div class="meth-steps">' + "".join(f"<div class='meth-step'><b>{t}</b>{d}</div>" for t, d in steps) + "</div>",
                unsafe_allow_html=True)


def _formula(expr: str, note: str = "") -> None:
    st.markdown(f'<div class="meth-formula">{expr}' + (f"<br><small>{note}</small>" if note else "") + "</div>",
                unsafe_allow_html=True)


def _grid2(*cells: tuple[str, str]) -> None:
    st.markdown('<div class="meth-grid2">' + "".join(f"<div><b>{t}</b><br>{d}</div>" for t, d in cells) + "</div>",
                unsafe_allow_html=True)


def _hr() -> None:
    st.markdown("<hr style='border:none;border-top:1px solid #E8E6DD;margin:34px 0;'>", unsafe_allow_html=True)


def _table(headers: list[str], rows: list[list[str]]) -> None:
    th = "".join(f"<th>{h}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f'<div class="sa-tbl-scroll"><table class="sources-table"><thead><tr>{th}</tr></thead>'
                f'<tbody>{tr}</tbody></table></div>', unsafe_allow_html=True)


def _scroll_to_hash() -> None:
    """Fait défiler jusqu'à l'ancre de l'URL une fois la page rendue (Streamlit ne le fait pas seul)."""
    components.html("""<script>
(function(){
  var h = window.parent.location.hash.replace('#','');
  if (!h) return;
  var n = 0;
  var t = setInterval(function(){
    var el = window.parent.document.getElementById(h);
    if (el) { el.scrollIntoView({behavior:'smooth', block:'start'}); clearInterval(t); }
    if (++n > 40) clearInterval(t);
  }, 250);
})();
</script>""", height=0)


def render(data: dict) -> None:
    from ..config import APL_MILLESIME
    master = data.get("master")
    nb_scores = int(master["score_global"].notna().sum()) if master is not None else 100
    try:
        from .acces_ign import pilotes_disponibles
        nb_sim = len(pilotes_disponibles())
    except Exception:
        nb_sim = 98

    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Méthodologie")], key_prefix="methodo_bc")
    toc = "".join(f'<a href="#{a}">{lib}</a>' for a, lib in SECTIONS.items())
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">RESSOURCE</span>'
        '<span class="dot"></span><span class="region">Comment fonctionne Sant’active</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Méthodologie</h1></div>'
        '<p class="fiche-header-lead">Pour chaque outil de Sant’active : la question à laquelle il répond, comment il calcule, '
        'comment lire le résultat et ce qu’il ne dit pas. Quelques formules simples, aucune compétence technique requise.</p>'
        f'<div class="meth-toc">{toc}</div></div>', unsafe_allow_html=True)
    _scroll_to_hash()

    # ══════════════════════════════════════════════════════════════════════════
    # SCORE
    # ══════════════════════════════════════════════════════════════════════════
    _section("score", "1 · LE SCORE SANT’ACTIVE", "Un seul chiffre pour <em>situer un département.</em>",
             "comment ce département se place-t-il par rapport aux autres sur l’offre et l’accès aux soins de premier recours ?")
    _steps(("1 · Six indicateurs", "Accessibilité (APL), médecins, temps d’accès, établissements, seniors, immobilier."),
           ("2 · Une position par indicateur", f"Chaque département est classé parmi les {nb_scores} ; sa position va de 0 (le moins bien placé) à 100 (le mieux placé)."),
           ("3 · Une moyenne pondérée", "Les six positions sont combinées avec les poids ci-dessous."),
           ("4 · Trois zones", "Les départements sont répartis en trois tiers : critique, intermédiaire, favorable."))
    st.markdown(
        '<div class="meth-bar">'
        '<span style="flex:30;background:#1A3D8F;">APL 30 %</span>'
        '<span style="flex:20;background:#2E6BE6;">Médecins 20 %</span>'
        '<span style="flex:20;background:#5A85C3;">Temps 20 %</span>'
        '<span style="flex:15;background:#8FA8D8;">Établissements 15 %</span>'
        '<span style="flex:10;background:#B45309;">Seniors 10 %</span>'
        '<span style="flex:5;background:#D97706;">Immo 5 %</span></div>'
        '<div class="meth-bar-legend">'
        f'<span><b>APL</b> consultations accessibles par habitant (DREES {APL_MILLESIME}) · plus, c’est mieux</span>'
        '<span><b>Médecins</b> généralistes pour 100 000 habitants (RPPS 2026) · plus, c’est mieux</span>'
        '<span><b>Temps</b> trajet médian en voiture vers un généraliste (INSEE 2025) · moins, c’est mieux</span>'
        '<span><b>Établissements</b> sites hospitaliers pour 100 000 habitants (FINESS 2026) · plus, c’est mieux</span>'
        '<span><b>Seniors</b> part des 65 ans et plus (INSEE 2021) · moins, c’est mieux</span>'
        '<span><b>Immobilier</b> prix médian au m² (DVF 2025) · moins, c’est mieux</span></div>', unsafe_allow_html=True)
    _formula("Score = 0,30 × APL + 0,20 × Médecins + 0,20 × Temps + 0,15 × Établissements + 0,10 × Seniors + 0,05 × Immobilier",
             "chaque terme est une position de 0 à 100 ; 50 = médiane des départements. Si un indicateur manque, son poids est "
             "redistribué sur les autres (au moins trois dimensions).")
    _grid2(("Comment lire", "Le score est <em>relatif</em> : 60 signifie « mieux placé que la plupart des départements », pas « 60 % "
                            "d’accès aux soins ». Le classement se lit « 1er = le mieux placé ». La zone est le tiers d’appartenance : "
                            "<span style='color:#A51C30;font-weight:600;'>critique</span>, "
                            "<span style='color:#B45309;font-weight:600;'>intermédiaire</span>, "
                            "<span style='color:#1B5E3F;font-weight:600;'>favorable</span>."),
           ("Ce que ce n’est pas", "Ni une note de santé de la population, ni une mesure de la disponibilité des rendez-vous, ni une "
                                   "évolution dans le temps. Les pondérations sont un choix du projet, stable et explicite, pas une norme officielle."),
           ("Densité et APL", "La densité compte des personnes inscrites au RPPS ; l’APL compte des consultations accessibles en tenant "
                              "compte de l’activité réelle des médecins, de la distance et de l’âge des habitants. Les deux peuvent diverger : "
                              "c’est pourquoi le score les combine."),
           ("Deux sous-lectures", "La fiche propose aussi un sous-score d’accès (APL 60 % + temps 40 %) et un sous-score d’offre "
                                  "(médecins), pour comprendre d’où vient la position globale."))
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # PRIORISER
    # ══════════════════════════════════════════════════════════════════════════
    _section("prioriser", "2 · PRIORISER", "Croiser l’offre et les besoins pour <em>savoir où agir d’abord.</em>",
             "où l’offre de soins est-elle faible alors que les besoins de la population sont élevés ?")
    _steps(("1 · Indice d’offre", "Positions APL, médecins, établissements et temps d’accès, pondérées 30 / 20 / 15 / 20."),
           ("2 · Indice de besoins", "Part des 65 ans et plus et prévalences de quatre pathologies, comparées à âge égal entre départements ; "
                                     "moyenne à poids égaux."),
           ("3 · Deux médianes", "Chaque indice est comparé à la médiane nationale."),
           ("4 · Quatre situations", "Le croisement place chaque département dans l’un des quatre cadrans."))
    st.markdown(
        '<div class="meth-quad">'
        '<div style="background:#FBEEF0;border-color:#EBC4C8;"><b>A · Offre faible, besoins forts</b><br>À examiner en premier.</div>'
        '<div style="background:#FEF4DC;border-color:#F0D9A6;"><b>B · Offre faible, besoins modérés</b><br>Offre à renforcer, pression moindre.</div>'
        '<div style="background:#FEF4DC;border-color:#F0D9A6;"><b>C · Offre correcte, besoins forts</b><br>Vigilance sur les parcours et la prévention.</div>'
        '<div style="background:#E3EFE8;border-color:#CFE3D8;"><b>D · Offre correcte, besoins modérés</b><br>Situation favorable, veille.</div></div>',
        unsafe_allow_html=True)
    _prose(
        "<strong>À l’échelle régionale</strong>, un score de priorité (0 à 100) combine à parts égales le besoin (fragilité du "
        "département et score Sant’active) et le volume de population concernée ; il ne tient pas compte de la faisabilité. Une "
        "lecture distincte, « fragilité × impact × faisabilité », repère les candidats à une expérimentation ; ce n’est pas un "
        "second score.",
        "<strong>Leviers d’action.</strong> Une vingtaine de dispositifs existants (maisons de santé, aides à l’installation, équipes "
        "mobiles, téléconsultation assistée, téléexpertise, premier recours en santé mentale, prévention, parcours gériatriques…) "
        "sont décrits par des conditions chiffrées sur les indicateurs du département. Un levier est proposé si ses conditions "
        "obligatoires sont remplies et qu’au moins un tiers de ses conditions pondérées le sont ; au plus quatre leviers, deux par "
        "famille ; sans levier déclenché, l’outil recommande une veille. Chaque levier nomme son public et, quand les données le "
        "permettent, la population concernée avec sa source ; sinon elle est déclarée non quantifiable.")
    _grid2(("Comment lire", "Le cadran A ne dit pas « le pire département » : il dit que l’écart entre ce qui est offert et ce qui est "
                            "demandé y est le plus préoccupant. Deux départements au score proche peuvent se trouver dans des cadrans différents."),
           ("Limites", "Cette lecture est exploratoire et ne modifie pas le score. Les prévalences mesurent des patients pris en charge, pas des "
                       "besoins non couverts. Les leviers sont des pistes à instruire avec les acteurs locaux, sans intelligence artificielle "
                       "générative, pas des prescriptions."))
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # DIAGNOSTIC
    # ══════════════════════════════════════════════════════════════════════════
    _section("diagnostic", "3 · DIAGNOSTIC", "Comprendre <em>un territoire</em> en une fiche.",
             "qu’est-ce qui, dans ce département, pose problème, pour qui, et où précisément ?")
    _steps(("1 · Situation", "Score, zone, classement et comparaison de chaque indicateur à la médiane des départements."),
           ("2 · Communes fragiles", "Classement des communes selon le temps d’accès, la population exposée et les conditions de déploiement."),
           ("3 · Publics et besoins", "Seniors, pathologies prises en charge, spécialités peu présentes."),
           ("4 · Leviers", "Les actions dont les conditions sont remplies, avec leur public et leurs communes."))
    _formula("Priorité d’une commune = 0,45 × besoin (temps d’accès) + 0,35 × population + 0,20 × faisabilité",
             "les communes qui disposent déjà d’une offre de médecine générale ne sont pas classées : une action d’accès n’y a pas d’objet.")
    _formula("ETP théoriques = déficit de consultations accessibles ÷ 5 400",
             "déficit calculé commune par commune pour ramener l’APL au repère 2,5 ; 5 400 consultations par an et par équivalent "
             "temps plein (convention DREES), fourchette 3 600 à 6 000. Un ordre de grandeur, pas un effectif à recruter.")
    _grid2(("Comment lire", "Les constats mettent en avant les écarts les plus marqués à la médiane. « Vigilance » signale un indicateur "
                            "moins bien placé que la médiane, « point d’appui » l’inverse. Le rapport PDF et l’e-mail reprennent les mêmes chiffres."),
           ("Limites", "Un généraliste à 5 minutes peut ne plus prendre de patients : la fiche décrit l’accessibilité géographique et "
                       "potentielle, pas l’accès effectif. Aucun délai de rendez-vous actuel n’est mesuré."))
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # COMPARER
    # ══════════════════════════════════════════════════════════════════════════
    _section("comparer", "4 · COMPARER", "Mettre des territoires <em>côte à côte.</em>",
             "sur quels indicateurs ces départements ou ces régions se distinguent-ils, et qu’est-ce que cela implique ?")
    _steps(("1 · Choix", "Deux à quatre départements, ou deux à quatre régions."),
           ("2 · Mêmes indicateurs", "Les six dimensions du score et les indicateurs d’accès, avec la médiane nationale en repère."),
           ("3 · Écarts", "Pour chaque ligne, le mieux et le moins bien placé, et l’écart entre eux."),
           ("4 · Lecture", "Une phrase par indicateur dit ce que l’écart signifie pour l’accès aux soins."))
    _grid2(("Comment lire", "Comparer des territoires de même nature (deux ruraux, deux urbains) donne les écarts les plus parlants. "
                            "Les régions sont comparées sur la médiane et la dispersion de leurs départements."),
           ("Limites", "Les indicateurs ont des millésimes différents (recensement 2021, APL " + APL_MILLESIME + ", RPPS 2026) ; les écarts "
                       "sont fiables, les niveaux exacts peuvent avoir bougé. Aucun calcul nouveau : Comparer réutilise les valeurs des fiches."))
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # SIMULER
    # ══════════════════════════════════════════════════════════════════════════
    _section("simuler", "5 · SIMULER UNE IMPLANTATION", "Estimer un <em>gain de proximité.</em>",
             "si un cabinet de médecine générale s’installait dans cette commune, combien d’habitants s’en rapprocheraient ?")
    _steps(("1 · Point d’implantation", "La mairie de la commune choisie (ou un point déplacé sur la carte)."),
           ("2 · Isochrones", "Les zones atteignables en 10, 15 et 20 minutes en voiture, calculées par le service d’itinéraires de l’IGN."),
           ("3 · Population", "Les carreaux INSEE de 200 m situés dans ces zones, avec leur population et leur temps d’accès actuel."),
           ("4 · Gain", "Les habitants aujourd’hui à plus de 15 minutes d’un généraliste qui passeraient sous ce seuil."))
    _formula("Gain = population des carreaux (temps actuel > 15 min) ∩ isochrone 15 min du nouveau cabinet",
             f"disponible pour {nb_sim} départements ; le même calcul est donné pour 10 et 20 minutes.")
    _grid2(("Comment lire", "Le gain compare des sites candidats : un gain élevé signale une commune bien placée pour desservir des habitants "
                            "éloignés. Il se lit avec la population totale desservie et le temps d’accès actuel de la commune."),
           ("Limites", "Le simulateur mesure une distance, pas une capacité : il ne dit ni si un médecin viendra, ni combien de patients il "
                       "pourra suivre, ni l’effet sur les cabinets voisins. Guadeloupe, Guyane et Mayotte ne sont pas couvertes."))
    _hr()

    # ══════════════════════════════════════════════════════════════════════════
    # SOURCES
    # ══════════════════════════════════════════════════════════════════════════
    _section("sources", "6 · D’OÙ VIENNENT LES DONNÉES", "Des organismes publics, <em>des millésimes nommés.</em>",
             "sur quelles données repose chaque indicateur, et de quand datent-elles ?")
    _table(["Organisme", "Donnée", "Millésime", "Utilisation"], [
        ["DREES", "Accessibilité potentielle localisée (APL) aux médecins généralistes", APL_MILLESIME,
         "Score (30 %), habitants sous le repère 2,5, équivalents temps plein théoriques"],
        ["INSEE", "Accès aux équipements : temps de trajet en voiture vers un généraliste, par carreau habité de 200 m", "2025",
         "Score (20 %), habitants et communes à plus de 15 minutes, communes fragiles, simulateur"],
        ["DREES", "Répertoire RPPS des professionnels de santé", "1er janvier 2026", "Score (20 %), spécialités pour les leviers"],
        ["Ministère chargé de la Santé (diffusion DREES)", "Fichier FINESS des établissements", "mars 2026",
         "Score (15 %) : centres hospitaliers, centres hospitaliers régionaux, soins de suite et de réadaptation privés ; "
         "les cliniques privées de court séjour ne sont pas comptées"],
        ["INSEE", "Recensement de la population", "2021", "Population, part des 65 ans et plus (score 10 %), densité"],
        ["Assurance Maladie (CNAM)", "Cartographie des pathologies et des dépenses", "2023", "Indice de besoins, leviers de prévention"],
        ["DGFiP", "Demandes de valeurs foncières (DVF)", "2025", "Prix médian au m² (score 5 %)"],
        ["IGN Géoplateforme, API Géo", "Isochrones routières, contours et population des communes", "service en ligne", "Simulateur, cartes"],
    ])
    _prose("Trois statuts sont distingués dans toute l’application : la <strong>donnée publique</strong> reprise de son producteur, "
           "l’<strong>indicateur calculé</strong> par Sant’active (score, zones, indices, densités) et l’<strong>estimation</strong> "
           "propre au projet (équivalents temps plein, gain de proximité), toujours signalée comme telle.")
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
    # LIMITES
    # ══════════════════════════════════════════════════════════════════════════
    _section("limites", "7 · LES LIMITES", "Ce qu’il faut garder en tête <em>avant de décider.</em>",
             "que ne dit pas Sant’active, et où ses chiffres demandent de la prudence ?")
    limites = [
        ("Accessibilité géographique ≠ accès effectif",
         "Ni le temps de trajet, ni l’APL ne disent si un rendez-vous est possible. Aucun délai de rendez-vous actuel n’est mesuré ni affiché."),
        ("Des millésimes différents",
         f"Recensement 2021, pathologies 2023, APL {APL_MILLESIME}, temps d’accès 2025, médecins et établissements 2026, immobilier 2025. "
         "Les écarts entre territoires sont robustes ; les niveaux exacts peuvent avoir évolué."),
        ("Le simulateur mesure une distance, pas une capacité",
         "Il estime combien d’habitants se rapprocheraient d’un cabinet, pas le nombre de consultations qu’un médecin pourrait assurer. "
         "Les équivalents temps plein théoriques sont un ordre de grandeur."),
        ("Une couverture partielle pour certaines sources",
         "Mayotte est hors score. Guadeloupe et Guyane n’ont pas de temps d’accès INSEE : score sur cinq dimensions et lecture communale "
         "sur un indicateur de repli, signalé. Les cliniques privées de court séjour ne sont pas comptées. Les inégalités sociales de "
         "santé ne sont pas mesurées."),
        ("Un score relatif, des pistes et non des prescriptions",
         "Le score situe un département parmi les autres à une date donnée ; il ne mesure pas une évolution. Les leviers sont des pistes "
         "à instruire avec les acteurs locaux."),
    ]
    html = '<div style="max-width:860px;">'
    for i, (titre, texte) in enumerate(limites, 1):
        html += ('<div style="display:grid;grid-template-columns:44px 1fr;gap:14px;padding:14px 0;border-bottom:1px solid #E8E6DD;">'
                 f'<div style="font-size:22px;font-weight:300;color:#1A3D8F;">{i:02d}</div>'
                 f'<div><div style="font-size:14px;font-weight:700;color:#0A1938;margin-bottom:3px;">{titre}</div>'
                 f'<div style="font-size:13.5px;color:#2B2B2B;line-height:1.65;">{texte}</div></div></div>')
    st.markdown(html + "</div>", unsafe_allow_html=True)
    _prose("La synthèse vocale des diagnostics (bouton « Écouter ») lit le texte affiché à l’écran avec une voix de synthèse "
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
