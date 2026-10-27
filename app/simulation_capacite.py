"""Simulation de capacité en médecine générale fondée sur l'APL communal DREES.

Ce n'est PAS une mesure du nombre de médecins manquants. La simulation répond
à la question : « quel volume d'offre supplémentaire (en consultations, puis
en équivalents temps plein) faudrait-il pour que chaque commune du département
située sous un seuil d'APL atteigne ce seuil, toutes choses égales par
ailleurs ? ». Elle ignore la redistribution de l'offre existante, les flux
inter-départementaux, l'évolution démographique et l'activité réelle des
futurs installés.

Formule (calculée commune par commune dans
scripts/donnees/calculer_apl_departemental.py, source DREES APL 2023) :
    déficit(seuil) = Σ_c pop_std_c × max(0, seuil − APL_c)
    ETP(seuil)     = déficit / activité annuelle d'un ETP
Activité d'un ETP : convention DREES de l'indicateur APL = 5 400 consultations,
visites et téléconsultations par an (bornes d'activité libérale 3 600–6 000,
d'où la fourchette). Seuils : 2,5 (repère de sous-densité du zonage) et 3,0.

Activée seulement si static/data/apl_mg_departemental_2023.csv est présent
(candidat : data_corrections/references/drees/apl_mg_departemental_2023.csv).
"""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import streamlit as st

from .config import DATA_DIR

APL_DEPT_PATH = DATA_DIR / "apl_mg_departemental_2023.csv"
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


def render_simulation_capacite(r: pd.Series) -> bool:
    dept = str(r.get("dept", "")).zfill(2)
    sim = simuler(dept)
    if sim is None:
        return False
    nom = html.escape(str(r.get("Nom du département", "")))
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ACCESSIBILITÉ AUX GÉNÉRALISTES · APL COMMUNAL</div>'
        '<h2 class="section-title">Où l\'offre de <em>médecine générale</em> manque-t-elle ?</h2>'
        '<p class="section-lead">APL communal DREES 2023 agrégé selon la méthode DREES '
        '(moyenne pondérée par la population standardisée) et simulation de capacité. '
        'Ces valeurs complètent le score, qui utilise toujours la médiane communale.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    kpi = lambda col, lab, val, sub: col.markdown(
        f'<div class="diagnostic-kpi" style="padding:14px;">'
        f'<div class="diagnostic-kpi-label">{lab}</div>'
        f'<div class="diagnostic-kpi-value" style="font-size:28px;">{val}</div>'
        f'<div class="diagnostic-kpi-context"><span style="font-size:11px;color:#6B6B68;">{sub}</span></div>'
        f'</div>', unsafe_allow_html=True)
    kpi(c1, "APL moyen pondéré", _fmt(sim["apl_moyen_pondere"], ".2f"),
        "consult./an/hab. standardisé · méthode DREES")
    kpi(c2, "Population sous 2,5", f"{sim['part_pop_apl_inf_2_5']:.0%}",
        f"{sim['nb_communes_inf_2_5']} communes sur {sim['nb_communes']}")
    kpi(c3, "Disparités communales", f"{_fmt(sim['apl_p25'], '.1f')} – {_fmt(sim['apl_p75'], '.1f')}",
        "quartiles communaux pondérés par la population")
    lo, mid, hi = sim["etp_2,5"]
    kpi(c4, "Simulation · seuil 2,5", f"≈ {mid:.0f} ETP", f"fourchette {lo:.0f} – {hi:.0f} ETP")
    lo3, mid3, hi3 = sim["etp_3,0"]
    st.markdown(
        '<div style="margin-top:10px;padding:12px 16px;background:#F3F2EC;border-radius:4px;'
        'font-size:12px;color:#6B6B68;line-height:1.6;">'
        f'<strong style="color:#2B2B2B;">Simulation, pas mesure.</strong> Pour porter chaque '
        f'commune de {nom} située sous le seuil au niveau de ce seuil, il manquerait environ '
        f'{_fmt(sim["deficit_2,5"], ",.0f")} consultations accessibles par an (seuil 2,5), soit '
        f'<strong>{mid:.0f} ETP</strong> de médecine générale à 5 400 actes/an par ETP '
        f'(convention DREES ; fourchette {lo:.0f}–{hi:.0f} ETP pour 6 000–3 600 actes). '
        f'Au seuil 3,0 : ≈ {mid3:.0f} ETP ({lo3:.0f}–{hi3:.0f}). Hypothèses : offre existante '
        'inchangée, pas de flux entre départements, APL 2023. Source : DREES, APL aux médecins '
        'généralistes 2023 (Licence Ouverte).'
        '</div>',
        unsafe_allow_html=True,
    )
    return True
