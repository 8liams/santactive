"""Prioriser : matrice offre × besoins (prototype, ne remplace pas le score).

Lecture en trois niveaux : (1) ce que mesurent les deux indices et comment
lire les couleurs ; (2) filtres région / quadrant, matrice et tableau des
départements concernés avec accès au diagnostic ; (3) construction des indices
et données manquantes, à la demande.
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..components.nav import NavCrumb, dept_link_html, internal_href, render_breadcrumb
from ..indices import QUADRANTS, calculer_indices, expliquer

_COULEURS = {"A": "#A51C30", "B": "#E8A838", "C": "#1A3D8F", "D": "#1B5E3F"}
_LIBS_OFFRE = {"score_apl": "APL pondérée", "score_medecins": "généralistes /100k",
               "score_etabs": "structures /100k", "score_temps": "temps d'accès"}
_QUADRANT_LECTURE = {
    "A": "offre faible et besoins forts : territoires à examiner en premier",
    "B": "offre faible, besoins dans la norme : enjeu d'accès avant tout",
    "C": "offre correcte, besoins forts : enjeu de prévention et de parcours",
    "D": "offre correcte, besoins dans la norme : veille",
}


def render(data: dict) -> None:
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Prioriser")], key_prefix="explo_bc")
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">PRIORISATION</span>'
        '<span class="dot"></span><span class="region">Lecture complémentaire au score · prototype</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Prioriser <em>les territoires</em></h1></div>'
        '</div>', unsafe_allow_html=True)

    master = data["master"]
    ind = calculer_indices(master, data.get("patho"))
    o_med, b_med = ind.attrs["medianes"]
    ind = ind.copy()
    ind["region"] = master.set_index("dept")["Nom de la région"].reindex(ind.index)

    # ── Niveau 1 : lecture immédiate ─────────────────────────────────────────
    st.markdown(
        '<div class="prio-intro">'
        '<div class="prio-tile"><div class="prio-tile-lbl">Offre et accès</div>'
        '<div class="prio-tile-txt">Accessibilité aux généralistes (APL), généralistes et structures pour 100 000 habitants, '
        'temps d’accès. <strong>100 = le mieux doté</strong> des 100 départements.</div></div>'
        '<div class="prio-tile"><div class="prio-tile-lbl">Besoins sanitaires</div>'
        '<div class="prio-tile-txt">Part des 65 ans et plus et prévalences standardisées sur l’âge (diabète, '
        'cardio-neuro-vasculaire, psychiatrie, respiratoire). <strong>100 = besoins les plus forts</strong>.</div></div>'
        '<div class="prio-tile"><div class="prio-tile-lbl">Comment lire</div>'
        '<div class="prio-tile-txt">Chaque département est placé par rapport aux médianes (traits pointillés). '
        '<span style="color:#A51C30;font-weight:700;">Rouge</span> : offre faible et besoins forts, à examiner en premier. '
        'Ces indices complètent le score global sans le remplacer : le score mesure surtout l’offre, pas les besoins.</div></div>'
        '</div>', unsafe_allow_html=True)

    # ── Filtres ───────────────────────────────────────────────────────────────
    f1, f2 = st.columns([1, 2])
    regions = ["Toutes les régions"] + sorted(ind["region"].dropna().unique().tolist())
    region = f1.selectbox("Région", regions, key="prio_region")
    quad_opts = ["Tous"] + [f"{q} · {lab}" for q, lab in QUADRANTS.items()]
    quad_choice = f2.radio("Quadrant", quad_opts, horizontal=True, key="prio_quadrant", label_visibility="visible")
    quad = quad_choice[0] if quad_choice != "Tous" else None
    sel = ind.copy()
    if region != "Toutes les régions":
        sel = sel[sel["region"] == region]
    if quad:
        sel = sel[sel["quadrant"] == quad]

    # ── Matrice ───────────────────────────────────────────────────────────────
    fig = go.Figure()
    autres = ind.drop(sel.index)
    if not autres.empty:
        fig.add_trace(go.Scatter(x=autres["indice_offre"], y=autres["indice_besoins"], mode="markers",
                                 marker=dict(size=6, color="#C9C6BA", opacity=0.6), name="autres départements",
                                 customdata=autres["Nom du département"], hoverinfo="skip"))
    for q, lab in QUADRANTS.items():
        sub = sel[sel["quadrant"] == q]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["indice_offre"], y=sub["indice_besoins"], mode="markers+text",
            text=sub.index, textposition="top center", textfont=dict(size=9, color="#4B4B48"),
            marker=dict(size=10, color=_COULEURS[q], opacity=0.9, line=dict(width=0.8, color="white")),
            name=lab, customdata=sub["Nom du département"],
            hovertemplate="<b>%{customdata}</b><br>offre %{x:.0f} · besoins %{y:.0f}<extra></extra>",
        ))
    fig.add_vline(x=o_med, line=dict(color="#9C9A92", dash="dot", width=1))
    fig.add_hline(y=b_med, line=dict(color="#9C9A92", dash="dot", width=1))
    for (x, y, t) in ((8, 97, "offre faible · besoins forts"), (92, 97, "offre correcte · besoins forts"),
                      (8, 3, "offre faible · besoins modérés"), (92, 3, "offre correcte · besoins modérés")):
        fig.add_annotation(x=x, y=y, text=t, showarrow=False, font=dict(size=10, color="#9C9A92"))
    fig.update_layout(
        height=520, margin=dict(l=20, r=20, t=10, b=40), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FAFAF8",
        xaxis=dict(title="Offre et accès (100 = le mieux doté)", range=[0, 100], gridcolor="#E8E6DD"),
        yaxis=dict(title="Besoins sanitaires (100 = besoins les plus forts)", range=[0, 100], gridcolor="#E8E6DD"),
        legend=dict(orientation="h", y=-0.18), font=dict(family="Marianne, Inter, sans-serif", size=12),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    counts = sel["quadrant"].value_counts()
    cols = st.columns(4)
    for col, (q, lab) in zip(cols, QUADRANTS.items()):
        col.markdown(f'<div class="diagnostic-kpi" style="padding:10px 12px;border-top:3px solid {_COULEURS[q]};">'
                     f'<div class="diagnostic-kpi-label">{q} · {lab}</div>'
                     f'<div class="diagnostic-kpi-value" style="font-size:24px;margin-bottom:4px;">{int(counts.get(q, 0))}</div>'
                     f'<div style="font-size:11px;color:#6B6B68;line-height:1.4;">{_QUADRANT_LECTURE[q]}</div></div>',
                     unsafe_allow_html=True)

    # ── Tableau filtré + explication d'un département ─────────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.25, 1], gap="large")
    with c1:
        titre = ("Départements " + (f"du quadrant {quad}" if quad else "sélectionnés")
                 + (f" · {html.escape(region)}" if region != "Toutes les régions" else ""))
        st.markdown(f'<h4 class="subsection-title">{titre} ({len(sel)})</h4>', unsafe_allow_html=True)
        ordre = sel.sort_values(["quadrant", "indice_offre"], ascending=[True, True])
        limite = 25
        rows = "".join(
            f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.2fr;padding:6px 10px;border-bottom:1px solid #E8E6DD;font-size:13px;align-items:center;">'
            f'<span><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{_COULEURS[r["quadrant"]]};margin-right:6px;"></i>'
            f'{dept_link_html(d, str(r["Nom du département"]), css_class="region-dept-name")}</span>'
            f'<span style="text-align:right;">{r["indice_offre"]:.0f}</span><span style="text-align:right;">{r["indice_besoins"]:.0f}</span>'
            f'<span style="text-align:right;color:#6B6B68;">{r["score_global"]:.0f} · {html.escape(str(r["zone_short"]))}</span></div>'
            for d, r in ordre.head(limite).iterrows())
        st.markdown(
            '<div class="sa-tbl-scroll"><div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.2fr;padding:6px 10px;'
            'background:#F3F2EC;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6B6B68;">'
            '<span>Département</span><span style="text-align:right;">Offre</span><span style="text-align:right;">Besoins</span>'
            '<span style="text-align:right;">Score · zone</span></div>' + rows + '</div>'
            + (f'<p class="sa-couverture" style="margin-top:6px;">{len(sel) - limite} autres départements : affinez par région ou par quadrant.</p>'
               if len(sel) > limite else ""), unsafe_allow_html=True)
    with c2:
        st.markdown('<h4 class="subsection-title">Pourquoi ce département est ici</h4>', unsafe_allow_html=True)
        opts = list(ordre.index) if not ordre.empty else list(ind.index)
        choix = st.selectbox("Département", opts, format_func=lambda d: f"{d} · {ind.loc[d, 'Nom du département']}",
                             key="explo_dept", label_visibility="collapsed")
        e = expliquer(choix, ind)
        r = ind.loc[choix]
        pos_o = "sous" if r["indice_offre"] < o_med else "au-dessus de"
        pos_b = "au-dessus de" if r["indice_besoins"] >= b_med else "sous"
        faibles = ", ".join(_LIBS_OFFRE.get(k, k) for k in e["offre_faible"])
        forts = ", ".join(e["besoins_forts"])
        st.markdown(
            f'<div class="reco-card reco-card-neutral" style="border-left:4px solid {_COULEURS[r["quadrant"]]};">'
            f'<div class="reco-famille"><span>{html.escape(e["quadrant"])}</span><span class="reco-horizon">{html.escape(str(r["region"]))}</span></div>'
            f'<div class="reco-title">{html.escape(e["nom"])}</div>'
            f'<div class="reco-block">Son indice d’offre ({e["indice_offre"]:.0f}) est {pos_o} la médiane ({o_med:.0f}) et son indice '
            f'de besoins ({e["indice_besoins"]:.0f}) {pos_b} la médiane ({b_med:.0f}) : {_QUADRANT_LECTURE[r["quadrant"]]}.</div>'
            f'<div class="reco-block"><div class="reco-block-lbl">Points faibles de l’offre</div>{html.escape(faibles)} '
            f'(rangs nationaux : {html.escape(" · ".join(f"{_LIBS_OFFRE.get(k, k)} {v:.0f}" for k, v in e["offre"].items()))})</div>'
            f'<div class="reco-block"><div class="reco-block-lbl">Besoins dominants</div>{html.escape(forts)} '
            f'(rangs nationaux : {html.escape(" · ".join(f"{k} {v:.0f}" for k, v in e["besoins"].items()))})</div>'
            f'<div class="sa-parcours" style="margin:10px 0 0;"><a class="primary" href="{internal_href("dept", dept_code=choix)}" target="_self">Ouvrir le diagnostic →</a>'
            f'<a href="{internal_href("comparer")}&depts={choix}" target="_self">Comparer →</a></div>'
            f'</div>', unsafe_allow_html=True)

    # ── Niveau 3 : construction et données manquantes ─────────────────────────
    with st.expander("Comment sont construits ces indices, et leurs limites"):
        src = ind.attrs.get("sources_besoins", {})
        besoin_cols = [c for c in ind.columns if c.startswith("besoin_")]
        manquants = {c.replace("besoin_", ""): int(ind[c].isna().sum()) for c in besoin_cols}
        st.markdown(
            "- **Indice offre et accès** : moyenne pondérée des rangs percentiles de l’APL pondérée (30), des généralistes "
            "pour 100 000 habitants (20), des structures pour 100 000 habitants (15) et du temps d’accès (20) — les poids "
            "actuels du score global, renormalisés ; le foncier et le vieillissement en sont exclus.\n"
            "- **Indice besoins sanitaires** : moyenne à poids égaux des rangs percentiles de la part des 65 ans et plus "
            "et des prévalences CNAM 2023 standardisées sur l’âge lorsque la couverture des poids d’âge atteint 90 % "
            "(sinon brutes, signalé). Poids égaux faute de référence validée.\n"
            f"- **Sources** : {' ; '.join(f'{k} : {v}' for k, v in src.items())}.\n"
            f"- **Données manquantes** (départements sans valeur) : "
            + (", ".join(f"{k} : {v}" for k, v in manquants.items() if v) or "aucune")
            + ". Un indice de besoins calculé sur moins de composantes est moins robuste.\n"
            "- **Limites** : les quadrants dépendent des médianes (un département proche d’un trait change de couleur pour "
            "quelques dixièmes de point) ; les prévalences mesurent des patients pris en charge, pas des besoins non couverts ; "
            "les deux indices ne sont pas intégrés au score global et n’ont pas vocation à le remplacer sans validation."
        )
