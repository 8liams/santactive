"""Exploration : matrice offre × besoins (prototype, ne remplace pas le score)."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..components.nav import NavCrumb, dept_link_html, render_breadcrumb
from ..indices import QUADRANTS, calculer_indices, expliquer

_COULEURS = {"A": "#A51C30", "B": "#E8A838", "C": "#1A3D8F", "D": "#1B5E3F"}
_LIBS_OFFRE = {"score_apl": "APL pondérée", "score_medecins": "généralistes /100k",
               "score_etabs": "structures /100k", "score_temps": "temps d'accès"}


def render(data: dict) -> None:
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Explorer")], key_prefix="explo_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">PROTOTYPE</span>'
        '<span class="dot"></span><span class="region">Lecture complémentaire au score</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Offre de soins <em>et</em> besoins sanitaires</h1></div>'
        '</div>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-lead" style="max-width:860px;">Chaque département est positionné selon deux '
        'indices distincts : l’<strong>offre et l’accès</strong> (APL pondérée, généralistes, '
        'structures, temps d’accès ; 100 = le plus favorable) et les <strong>besoins sanitaires</strong> '
        '(vieillissement, prévalences standardisées sur l’âge ; 100 = besoins les plus forts). '
        'Le score global actuel est à 0,99 un indice d’offre : cette matrice fait apparaître les '
        'territoires qui cumulent une offre faible et des besoins élevés. Prototype : n’entre pas '
        'dans le classement national.</p>', unsafe_allow_html=True)

    ind = calculer_indices(data["master"], data.get("patho"))
    o_med, b_med = ind.attrs["medianes"]

    fig = go.Figure()
    for q, lab in QUADRANTS.items():
        sub = ind[ind["quadrant"] == q]
        fig.add_trace(go.Scatter(
            x=sub["indice_offre"], y=sub["indice_besoins"], mode="markers+text",
            text=sub.index, textposition="top center", textfont=dict(size=9, color="#4B4B48"),
            marker=dict(size=9, color=_COULEURS[q], opacity=0.85, line=dict(width=0.5, color="white")),
            name=lab, customdata=sub["Nom du département"],
            hovertemplate="<b>%{customdata}</b><br>offre %{x:.0f} · besoins %{y:.0f}<extra></extra>",
        ))
    fig.add_vline(x=o_med, line=dict(color="#9C9A92", dash="dot", width=1))
    fig.add_hline(y=b_med, line=dict(color="#9C9A92", dash="dot", width=1))
    fig.update_layout(
        height=560, margin=dict(l=20, r=20, t=10, b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF8",
        xaxis=dict(title="Indice offre / accès (100 = le plus favorable)", range=[0, 100], gridcolor="#E8E6DD"),
        yaxis=dict(title="Indice besoins sanitaires (100 = besoins les plus forts)", range=[0, 100], gridcolor="#E8E6DD"),
        legend=dict(orientation="h", y=-0.15), font=dict(family="Marianne, Inter, sans-serif", size=12),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    counts = ind["quadrant"].value_counts()
    cols = st.columns(4)
    for col, (q, lab) in zip(cols, QUADRANTS.items()):
        col.markdown(f'<div class="diagnostic-kpi" style="padding:12px;border-top:3px solid {_COULEURS[q]};">'
                     f'<div class="diagnostic-kpi-label">{lab}</div>'
                     f'<div class="diagnostic-kpi-value" style="font-size:26px;">{int(counts.get(q, 0))}</div>'
                     f'<div class="diagnostic-kpi-context"><span style="font-size:11px;color:#6B6B68;">départements</span></div>'
                     f'</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        choix = st.selectbox("Expliquer le positionnement d'un département",
                             options=list(ind.index), format_func=lambda d: f"{d} · {ind.loc[d, 'Nom du département']}",
                             key="explo_dept")
        e = expliquer(choix, ind)
        offre_txt = " · ".join(f"{_LIBS_OFFRE.get(k, k)} {v:.0f}" for k, v in e["offre"].items())
        bes_txt = " · ".join(f"{k} {v:.0f}" for k, v in e["besoins"].items())
        faibles = ", ".join(_LIBS_OFFRE.get(k, k) for k in e["offre_faible"])
        forts = ", ".join(e["besoins_forts"])
        src = " ; ".join(f"{k} : {v}" for k, v in e["sources"].items())
        st.markdown(
            f'<div class="reco-card reco-card-neutral">'
            f'<div class="reco-famille">{html.escape(e["quadrant"])}</div>'
            f'<div class="reco-title">{html.escape(e["nom"])} · offre {e["indice_offre"]:.0f} · besoins {e["indice_besoins"]:.0f}</div>'
            f'<div class="reco-prose"><strong>Offre (rangs nationaux, 100 = favorable).</strong> {html.escape(offre_txt)}. '
            f'Points faibles : {html.escape(faibles)}.</div>'
            f'<div class="reco-prose"><strong>Besoins (rangs nationaux, 100 = forts).</strong> {html.escape(bes_txt)}. '
            f'Besoins dominants : {html.escape(forts)}.</div>'
            f'<div class="reco-score">Sources : {html.escape(src)}</div>'
            f'<div style="margin-top:8px;">{dept_link_html(choix, "Ouvrir la fiche du département →", css_class="region-dept-name")}</div>'
            f'</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<h4 class="subsection-title">Offre faible · besoins forts</h4>', unsafe_allow_html=True)
        a = ind[ind["quadrant"] == "A"].sort_values("indice_offre")
        rows = "".join(
            f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr;padding:6px 10px;border-bottom:1px solid #E8E6DD;font-size:13px;">'
            f'<span>{dept_link_html(d, str(r["Nom du département"]), css_class="region-dept-name")}</span>'
            f'<span style="text-align:right;">{r["indice_offre"]:.0f}</span><span style="text-align:right;">{r["indice_besoins"]:.0f}</span>'
            f'<span style="text-align:right;color:#6B6B68;">{r["score_global"]:.0f} · {html.escape(str(r["zone_short"]))}</span></div>'
            for d, r in a.iterrows())
        st.markdown(
            '<div class="sa-tbl-scroll"><div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr;padding:6px 10px;'
            'background:#F3F2EC;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6B6B68;">'
            '<span>Département</span><span style="text-align:right;">Offre</span><span style="text-align:right;">Besoins</span>'
            '<span style="text-align:right;">Score · zone</span></div>' + rows + '</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="margin-top:16px;font-size:11px;color:#9C9A92;line-height:1.6;">Méthode : indice offre = '
        'poids actuels du score (30/20/15/20) renormalisés ; indice besoins = moyenne à poids égaux des rangs '
        'des 65 ans et plus et des prévalences CNAM 2023 standardisées sur l’âge (brutes si la couverture '
        'est insuffisante). Les traits pointillés sont les médianes. Prototype non intégré au score global.</div>',
        unsafe_allow_html=True)
