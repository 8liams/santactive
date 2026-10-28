"""Simulation de capacité en médecine générale fondée sur l'APL communal DREES.

Ce n'est PAS une mesure du nombre de médecins manquants. La simulation répond
à la question : « quel volume d'offre supplémentaire (en consultations, puis
en équivalents temps plein) faudrait-il pour que chaque commune du département
située sous un seuil d'APL atteigne ce seuil, toutes choses égales par
ailleurs ? ». Elle ignore la redistribution de l'offre existante, les flux
inter-départementaux, l'évolution démographique et l'activité réelle des
futurs installés.

Formule (calculée commune par commune dans
scripts/donnees/calculer_apl_departemental.py, source DREES APL, millésime config.APL_MILLESIME) :
    déficit(seuil) = Σ_c pop_std_c × max(0, seuil − APL_c)
    ETP(seuil)     = déficit / activité annuelle d'un ETP
Activité d'un ETP : convention DREES de l'indicateur APL = 5 400 consultations,
visites et téléconsultations par an (bornes d'activité libérale 3 600–6 000,
d'où la fourchette). Seuils : 2,5 (repère de sous-densité du zonage) et 3,0.

Activée seulement si static/data/apl_mg_departemental_<millésime>.csv est présent
(config.APL_MILLESIME ; produit par scripts/donnees/calculer_apl_departemental.py).
"""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import streamlit as st

from .config import APL_DEPT_DREES_PATH, APL_MILLESIME

APL_DEPT_PATH = APL_DEPT_DREES_PATH
ETP_CONSULTATIONS = 5400          # convention DREES (1 ETP) — indicateur APL
ETP_BORNES = (6000, 3600)         # bornes d'activité libérale DREES → fourchette ETP (basse, haute)


@st.cache_data(show_spinner=False)
def load_apl_departemental() -> pd.DataFrame | None:
    if not Path(APL_DEPT_PATH).exists():
        return None
    return pd.read_csv(APL_DEPT_PATH, dtype={"dept": str}).set_index("dept")


def simuler(dept: str) -> dict | None:
    """Indicateurs APL pondérés et fourchettes d'ETP pour un département."""
    apl = load_apl_departemental()
    if apl is None or dept not in apl.index:
        return None
    r = apl.loc[dept]
    out = {
        "apl_moyen_pondere": float(r["apl_moyen_pondere"]),
        "part_pop_apl_inf_2_5": float(r["part_pop_apl_inf_2_5"]),
        "apl_p25": float(r["apl_p25_pond"]), "apl_p75": float(r["apl_p75_pond"]),
        "nb_communes_inf_2_5": int(r["nb_communes_apl_inf_2_5"]), "nb_communes": int(r["nb_communes"]),
    }
    for seuil, col in (("2,5", "deficit_consult_seuil_2_5"), ("3,0", "deficit_consult_seuil_3_0")):
        d = float(r[col])
        out[f"deficit_{seuil}"] = d
        out[f"etp_{seuil}"] = (d / ETP_BORNES[0], d / ETP_CONSULTATIONS, d / ETP_BORNES[1])
    return out


def _fmt(v: float, spec: str = ".1f") -> str:
    return f"{v:{spec}}".replace(",", " ")


def _fr_int(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", "\u202f")


def conclusion_capacite(sim: dict, nom: str, population: float | None) -> dict:
    """Lecture principale du renforcement théorique : déficit détecté ou non, population concernée,
    ordre de grandeur. Les nombres restent ceux du calcul ; seule la présentation change."""
    lo, mid, hi = sim["etp_2,5"]
    lo3, mid3, hi3 = sim["etp_3,0"]
    part = sim["part_pop_apl_inf_2_5"]
    pop_concernee = part * population if population else None
    deficit = sim["deficit_2,5"] > 0 and mid >= 0.5
    return {"deficit": deficit, "part": part, "pop_concernee": pop_concernee, "communes": sim["nb_communes_inf_2_5"],
            "nb_communes": sim["nb_communes"], "etp": (lo, mid, hi), "etp3": (lo3, mid3, hi3),
            "consult": sim["deficit_2,5"], "consult3": sim["deficit_3,0"]}


def render_simulation_capacite(r: pd.Series) -> bool:
    dept = str(r.get("dept", "")).zfill(2)
    sim = simuler(dept)
    if sim is None:
        return False
    nom = html.escape(str(r.get("Nom du département", "")))
    pop = pd.to_numeric(pd.Series([r.get("population_num")]), errors="coerce").iloc[0]
    c = conclusion_capacite(sim, nom, float(pop) if pd.notna(pop) else None)
    lo, mid, hi = c["etp"]
    lo3, mid3, hi3 = c["etp3"]
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">RENFORCEMENT THÉORIQUE DE CAPACITÉ MÉDICALE</div>'
        '<h2 class="section-title">Combien d\'offre de <em>médecine générale</em> manquerait-il\u00a0?</h2>'
        f'<p class="section-lead">Lecture fondée sur l\'APL communal DREES {APL_MILLESIME} (accessibilité potentielle localisée, en '
        'consultations par habitant et par an). Le renforcement est exprimé en ETP, c\'est-à-dire en '
        '<strong>équivalents temps plein</strong> de médecine générale\u202f: un ordre de grandeur théorique, '
        'pas un effectif officiel de médecins manquants.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    pop_txt = (f"<strong>{_fr_int(c['pop_concernee'])} habitants</strong> ({c['part']:.0%})" if c["pop_concernee"] is not None
               else f"<strong>{c['part'] * 100:.0f}\u202f% de la population</strong>")
    if c["deficit"]:
        conclusion = (
            f'<p><strong>Déficit théorique détecté.</strong> Dans {nom}, {pop_txt} vivent dans {c["communes"]} commune{"s" if c["communes"] != 1 else ""} '
            f'sur {c["nb_communes"]} où l\u2019APL est sous le repère de sous-densité 2,5.</p>'
            f'<p>Pour ramener chacune de ces communes au repère 2,5, il manquerait environ <strong>{_fr_int(c["consult"])} consultations par an</strong>, '
            f'soit un renforcement de l\u2019ordre de <strong>{mid:.0f} ETP</strong> (équivalents temps plein) de médecine générale, '
            f'entre {lo:.0f} et {hi:.0f} selon l\u2019activité retenue par médecin.</p>'
            f'<p class="cap-ssq">Avec un repère plus exigeant (APL 3,0)\u202f: environ {mid3:.0f} ETP ({lo3:.0f} à {hi3:.0f}). '
            f'Le total surestime plutôt le besoin réel (un médecin installé relève aussi l\u2019APL des communes voisines).</p>')
        cls = ""
    else:
        conclusion = (
            f'<p><strong>Aucun déficit théorique au repère APL 2,5.</strong> Aucune commune de {nom} '
            + (f'(sur {c["nb_communes"]}) ' if c["communes"] == 0 else f'({c["communes"]} sur {c["nb_communes"]}, poids négligeable) ')
            + 'n\u2019a une accessibilité potentielle inférieure au repère national de sous-densité\u202f: '
            f'le volume de consultations accessibles dépasse partout 2,5 par habitant et par an, le renforcement calculé est donc de 0 ETP '
            f'(équivalent temps plein).</p>'
            f'<p><strong>Ce que cela ne permet pas de conclure</strong>\u202f: que l\u2019offre est suffisante. L\u2019APL ne mesure ni les délais de '
            f'rendez-vous, ni la saturation des patientèles, ni les départs à venir (âge des médecins), ni les écarts à l\u2019intérieur d\u2019une commune. '
            f'Pour {nom}, les difficultés éventuelles se lisent dans la démographie médicale, les délais et les besoins, pas dans ce calcul.</p>'
            + (f'<p class="cap-ssq">Avec un repère plus exigeant (APL 3,0)\u202f: environ {mid3:.0f} ETP ({lo3:.0f} à {hi3:.0f}) '
               f'pour les communes sous 3,0.</p>' if mid3 >= 0.5 else
               '<p class="cap-ssq">Au repère 3,0 également, aucun renforcement théorique notable.</p>'))
        cls = " none"
    st.markdown(f'<div class="cap-conclusion{cls}">{conclusion}</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    kpi = lambda col, lab, val, sub: col.markdown(
        f'<div class="diagnostic-kpi" style="padding:14px;">'
        f'<div class="diagnostic-kpi-label">{lab}</div>'
        f'<div class="diagnostic-kpi-value" style="font-size:28px;">{val}</div>'
        f'<div class="diagnostic-kpi-context"><span style="font-size:11px;color:#6B6B68;">{sub}</span></div>'
        f'</div>', unsafe_allow_html=True)
    kpi(c1, "APL moyen pondéré", _fmt(sim["apl_moyen_pondere"], ".2f"),
        f"consultations par habitant et par an · DREES {APL_MILLESIME} · repère de sous-densité 2,5")
    kpi(c2, "Population sous le repère 2,5", f"{sim['part_pop_apl_inf_2_5'] * 100:.0f}\u202f%",
        f"{sim['nb_communes_inf_2_5']} commune{'s' if sim['nb_communes_inf_2_5'] != 1 else ''} sur {sim['nb_communes']}")
    kpi(c3, "Renforcement théorique étudié", f"≈ {mid:.0f} ETP" if c["deficit"] else "0 ETP",
        f"équivalents temps plein · fourchette {lo:.0f} – {hi:.0f}" if c["deficit"] else "équivalent temps plein · aucun déficit au repère 2,5")
    with st.expander("Hypothèses, seuils et détail du calcul"):
        fr = lambda v, d=1: f"{v:.{d}f}".replace(".", ",")
        st.markdown(
            f"**Formule.** Pour chaque commune sous le seuil\u202f: déficit = population standardisée × (seuil − APL de la commune). "
            f"Somme départementale\u202f: {_fr_int(c['consult'])} consultations par an au seuil 2,5 ; {_fr_int(c['consult3'])} au seuil 3,0.\n\n"
            f"**Conversion en ETP (équivalents temps plein).** 1 ETP = {_fr_int(ETP_CONSULTATIONS)} consultations, visites et téléconsultations par an "
            f"(convention DREES de l\u2019indicateur APL). Fourchette\u202f: {_fr_int(ETP_BORNES[0])} actes par an (médecin très actif, borne basse) à "
            f"{_fr_int(ETP_BORNES[1])} actes (borne haute), d\u2019où {fr(lo)} – {fr(hi)} ETP au seuil 2,5 et {fr(lo3)} – {fr(hi3)} au seuil 3,0.\n\n"
            f"**Seuils.** 2,5 consultations par habitant et par an\u202f: repère national de sous-densité du zonage. 3,0\u202f: repère plus exigeant, "
            f"proche de la moyenne nationale.\n\n"
            f"**Disparités communales.** APL pondéré du premier au troisième quartile\u202f: {fr(sim['apl_p25'])} – {fr(sim['apl_p75'])}.\n\n"
            f"**Limites.** Simulation statique\u202f: offre existante supposée inchangée\u202f; déficit calculé commune par commune alors qu\u2019un "
            f"médecin installé relève aussi l\u2019APL des communes voisines (rayon de 20 min dans la méthode DREES)\u202f: le total tend à surestimer. "
            f"Les ETP ne sont pas des médecins physiques. APL {APL_MILLESIME}, population standardisée. Source\u202f: DREES, APL aux médecins "
            f"généralistes {APL_MILLESIME} (Licence Ouverte).")
    return True
