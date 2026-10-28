"""Prioriser : matrice offre × besoins (analyse exploratoire, ne remplace pas le score).

Lecture en trois niveaux :
1. les départements à examiner en priorité (offre faible, besoins forts) avec
   la raison principale de leur positionnement et l'accès au diagnostic ;
2. filtres région / quadrant, matrice (territoire de référence mis en évidence)
   et tableau des départements concernés ;
3. construction des indices, données manquantes et limites, à la demande.
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import territoire as T
from ..components.aide import aide_methodo
from ..components.nav import NavCrumb, dept_link_html, internal_href, render_breadcrumb
from ..indices import QUADRANTS, calculer_indices, expliquer

_COULEURS = {"A": "#A51C30", "B": "#E8A838", "C": "#1A3D8F", "D": "#1B5E3F"}
_LIBS_OFFRE = {"score_apl": "accessibilité aux généralistes (APL)", "score_medecins": "densité de généralistes",
               "score_etabs": "structures hospitalières", "score_temps": "temps d’accès"}
_QUADRANT_LECTURE = {
    "A": "offre faible et besoins forts : territoires à examiner en premier",
    "B": "offre faible, besoins dans la norme : enjeu d’accès avant tout",
    "C": "offre correcte, besoins forts : enjeu de prévention et de parcours",
    "D": "offre correcte, besoins dans la norme : veille",
}


def _raison(e: dict) -> str:
    """Phrase courte : composantes d'offre les plus faibles et besoins dominants."""
    faibles = [_LIBS_OFFRE.get(k, k) for k in e["offre_faible"]]
    forts = e["besoins_forts"]
    parts = []
    if faibles:
        parts.append("offre : " + " et ".join(faibles) + " parmi les plus faibles")
    if forts:
        parts.append("besoins : " + " et ".join(forts) + " élevés")
    return " · ".join(parts)


def render(data: dict) -> None:
    render_breadcrumb([NavCrumb("Accueil", "home"), NavCrumb("Prioriser")], key_prefix="explo_bc")
    master = data["master"]
    t = T.get()
    st.markdown(
        '<div class="fiche-header"><div class="fiche-eyebrow"><span class="code">PRIORISATION</span>'
        '<span class="dot"></span><span class="region">Analyse exploratoire · lecture complémentaire au score</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Prioriser <em>les territoires</em></h1></div>'
        '<p class="fiche-header-lead">Où l’offre de soins est-elle faible alors que les besoins sont élevés ? '
        'Chaque département est situé par rapport aux autres sur deux indices : ce qu’il offre, ce dont sa population a besoin.</p>'
        f'{aide_methodo("prioriser")}</div>', unsafe_allow_html=True)

    ind = calculer_indices(master, data.get("patho"))
    o_med, b_med = ind.attrs["medianes"]
    ind = ind.copy()
    ind["region"] = master.set_index("dept")["Nom de la région"].reindex(ind.index)
    ind["code_region"] = master.set_index("dept")["Code région"].astype(str).reindex(ind.index)

    # ── Niveau 1 : à examiner en priorité ────────────────────────────────────
    ref_region = T.region_code(t, master)
    ref_dept = t.code if t.kind == "dept" else None
    prio = ind[ind["quadrant"] == "A"].copy()
    prio["_tri"] = (o_med - prio["indice_offre"]) + (prio["indice_besoins"] - b_med)
    perim = ""
    if ref_region and not t.is_national:
        dans = prio[prio["code_region"] == ref_region]
        if not dans.empty:
            prio = dans
            perim = f" en {html.escape(str(dans['region'].iloc[0]))}"
    prio = prio.sort_values("_tri", ascending=False)
    # Contexte : où est le territoire de référence, quel périmètre, pourquoi ces départements
    if not t.is_national:
        nom_ref = html.escape(T.nom_court(t, master))
        nom_perim = html.escape(str(prio["region"].iloc[0])) if perim else "France entière"
        if ref_dept and ref_dept in ind.index:
            r0 = ind.loc[ref_dept]; q0 = r0["quadrant"]
            e0 = expliquer(ref_dept, ind)
            est_prio = ref_dept in prio.index
            situation = (f"<strong>{nom_ref}</strong> : {html.escape(QUADRANTS[q0].lower())} (quadrant {q0}) — "
                         + ("il fait partie des départements à examiner en priorité." if est_prio else
                            "il n’est pas dans le quadrant « offre faible, besoins forts » : " + html.escape(_QUADRANT_LECTURE[q0]) + ".")
                         + f" {html.escape(_raison(e0)).capitalize()}.")
        else:
            situation = f"<strong>{nom_ref}</strong> : périmètre de comparaison, ses départements sont situés dans le contexte national."
        autres = [n for n in prio["Nom du département"].astype(str).tolist() if n != (T.nom_court(t, master) if ref_dept else None)]
        st.markdown(
            f'<div class="sa-notice sa-notice--info" style="margin:0 0 10px;">{situation} '
            f'<span style="color:#4B4B48;">Périmètre affiché : <strong>{nom_perim}</strong>. Les départements ci-dessous y ressortent parce que leur '
            f'offre est sous la médiane nationale et leurs besoins au-dessus (critères du moteur, pas un classement « du pire au meilleur ») : '
            + (html.escape(", ".join(autres[:5])) + (" …" if len(autres) > 5 else "") if autres else "aucun autre") + '.</span></div>',
            unsafe_allow_html=True)
    cards = ""
    for code, r in prio.head(6).iterrows():
        e = expliquer(code, ind)
        moi = ' style="outline:2px solid #1A3D8F;"' if code == ref_dept else ""
        if code == ref_dept:
            lien_ref = "Votre territoire de référence"
        elif ref_region and r["code_region"] == ref_region:
            lien_ref = "Même région que votre territoire"
        else:
            lien_ref = ""
        cards += (f'<a class="usage-card" href="{internal_href("dept", dept_code=code)}" target="_self"{moi}>'
                  f'<div class="usage-title">{html.escape(e["nom"])} <span style="font-weight:400;color:#6B6B68;">({code})</span></div>'
                  + (f'<div class="usage-tag">{lien_ref}</div>' if lien_ref else "")
                  + f'<div class="usage-txt">Pourquoi : {html.escape(_raison(e))}.</div>'
                  f'<div class="usage-link">Ouvrir le diagnostic →</div></a>')
    st.markdown(
        f'<h4 class="subsection-title" style="margin-top:4px;">À examiner en priorité{perim} '
        f'<span style="font-weight:400;color:#6B6B68;">· {len(prio)} département{"s" if len(prio) > 1 else ""}</span></h4>'
        '<p class="sa-couverture" style="margin:-6px 0 8px;">Offre sous la médiane nationale et besoins au-dessus (quadrant A). '
        'La raison principale est indiquée ; le détail est dans le diagnostic.</p>'
        + (f'<div class="usage-grid usage-grid--3">{cards}</div>' if cards else
           '<p class="sa-couverture">Aucun département de ce périmètre ne cumule offre faible et besoins forts.</p>'),
        unsafe_allow_html=True)

    # ── Niveau 2 : filtres + matrice ─────────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:18px;"><div class="section-eyebrow">MATRICE</div>'
                '<h2 class="section-title">Offre <em>et</em> besoins, département par département</h2>'
                '<p class="section-lead">Filtrer par région sert à situer ses départements dans le contexte national : '
                'les médianes (traits pointillés) restent celles des 100 départements.</p></div>', unsafe_allow_html=True)
    f1, f2 = st.columns([1, 2])
    regions = ["Toutes les régions"] + sorted(ind["region"].dropna().unique().tolist())
    ref_region_name = None
    if ref_region:
        m = ind[ind["code_region"] == ref_region]
        ref_region_name = str(m["region"].iloc[0]) if not m.empty else None
    if "prio_region" not in st.session_state or st.session_state.get("_prio_region_ctx") != t.param:
        st.session_state["prio_region"] = ref_region_name if ref_region_name in regions else "Toutes les régions"
        st.session_state["_prio_region_ctx"] = t.param
    region = f1.selectbox("Région", regions, key="prio_region")
    quad_opts = ["Tous"] + [f"{q} · {lab}" for q, lab in QUADRANTS.items()]
    # Les cinq choix tiennent sur une ligne en pleine largeur (pas de bouton orphelin) ; en dessous, ils se répartissent en grille.
    with st.container(key="prio_quadrant_row"):
        quad_choice = st.radio("Quadrant", quad_opts, horizontal=True, key="prio_quadrant")
    quad = quad_choice[0] if quad_choice != "Tous" else None
    sel = ind.copy()
    if region != "Toutes les régions":
        sel = sel[sel["region"] == region]
    if quad:
        sel = sel[sel["quadrant"] == quad]

    fig = go.Figure()
    autres = ind.drop(sel.index)
    if not autres.empty:
        fig.add_trace(go.Scatter(x=autres["indice_offre"], y=autres["indice_besoins"], mode="markers",
                                 marker=dict(size=6, color="#C9C6BA", opacity=0.6), name="autres départements",
                                 customdata=autres["Nom du département"],
                                 hovertemplate="%{customdata}<br>offre %{x:.0f} · besoins %{y:.0f}<extra></extra>"))
    with_text = len(sel) <= 30
    for q, lab in QUADRANTS.items():
        sub = sel[sel["quadrant"] == q]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["indice_offre"], y=sub["indice_besoins"], mode="markers+text" if with_text else "markers",
            text=[f"{d} {n}" for d, n in zip(sub.index, sub["Nom du département"])] if with_text and len(sel) <= 14 else list(sub.index),
            textposition="top center", textfont=dict(size=9, color="#4B4B48"),
            marker=dict(size=10, color=_COULEURS[q], opacity=0.9, line=dict(width=0.8, color="white")),
            name=lab, customdata=sub["Nom du département"],
            hovertemplate="<b>%{customdata}</b><br>offre %{x:.0f} · besoins %{y:.0f}<extra></extra>",
        ))
    if ref_dept and ref_dept in ind.index:
        r0 = ind.loc[ref_dept]
        fig.add_trace(go.Scatter(x=[r0["indice_offre"]], y=[r0["indice_besoins"]], mode="markers",
                                 marker=dict(size=20, color="rgba(0,0,0,0)", line=dict(width=2.5, color="#0A1938")),
                                 name="territoire de référence", hoverinfo="skip"))
    fig.add_vline(x=o_med, line=dict(color="#9C9A92", dash="dot", width=1))
    fig.add_hline(y=b_med, line=dict(color="#9C9A92", dash="dot", width=1))
    for (x, y, tx) in ((8, 97, "offre faible · besoins forts"), (92, 97, "offre correcte · besoins forts"),
                       (8, 3, "offre faible · besoins modérés"), (92, 3, "offre correcte · besoins modérés")):
        fig.add_annotation(x=x, y=y, text=tx, showarrow=False, font=dict(size=10, color="#9C9A92"))
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
    ordre = sel.sort_values(["quadrant", "indice_offre"], ascending=[True, True])
    with c1:
        titre = ("Départements " + (f"du quadrant {quad}" if quad else "sélectionnés")
                 + (f" · {html.escape(region)}" if region != "Toutes les régions" else ""))
        st.markdown(f'<h4 class="subsection-title">{titre} ({len(sel)})</h4>', unsafe_allow_html=True)
        limite = 25
        rows = "".join(
            f'<div style="display:grid;grid-template-columns:2fr 1fr 1fr 1.2fr;padding:6px 10px;border-bottom:1px solid #E8E6DD;font-size:13px;align-items:center;'
            + ("background:#E8EDF8;" if d == ref_dept else "") + '">'
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
        if ref_dept in opts and st.session_state.get("_explo_dept_ctx") != t.param:
            st.session_state["explo_dept"] = ref_dept
            st.session_state["_explo_dept_ctx"] = t.param
        if st.session_state.get("explo_dept") not in opts:
            st.session_state["explo_dept"] = opts[0]
        choix = st.selectbox("Département", opts, format_func=lambda d: f"{d} · {ind.loc[d, 'Nom du département']}",
                             key="explo_dept", label_visibility="collapsed")
        e = expliquer(choix, ind)
        r = ind.loc[choix]
        q = r["quadrant"]
        conclusion = {
            "A": "cumule une offre de soins faible et des besoins sanitaires élevés : il fait partie des territoires à examiner en priorité",
            "B": "a une offre de soins faible, pour des besoins dans la norme nationale : l’enjeu est d’abord l’accès",
            "C": "a une offre correcte mais des besoins sanitaires élevés : l’enjeu est la prévention et les parcours de soins",
            "D": "a une offre correcte et des besoins dans la norme : une veille suffit",
        }[q]
        rangs_o = " · ".join(f"{_LIBS_OFFRE.get(k, k)} {v:.0f}" for k, v in e["offre"].items())
        rangs_b = " · ".join(f"{k} {v:.0f}" for k, v in e["besoins"].items())
        st.markdown(
            f'<div class="reco-card reco-card-neutral" style="border-left:4px solid {_COULEURS[q]};">'
            f'<div class="reco-famille"><span>{html.escape(e["quadrant"])}</span><span class="reco-horizon">{html.escape(str(r["region"]))}</span></div>'
            f'<div class="reco-title">{html.escape(e["nom"])}</div>'
            f'<div class="reco-block">{html.escape(e["nom"])} {conclusion}.</div>'
            f'<div class="reco-block"><div class="reco-block-lbl">Ce qui pèse</div>{html.escape(_raison(e)).capitalize()}.</div>'
            f'<details class="reco-details"><summary>Valeurs précises</summary>'
            f'<div class="reco-block">Indice d’offre {e["indice_offre"]:.0f} (médiane nationale {o_med:.0f}) · indice de besoins '
            f'{e["indice_besoins"]:.0f} (médiane {b_med:.0f}).<br>Rangs nationaux, offre : {html.escape(rangs_o)}.<br>'
            f'Rangs nationaux, besoins : {html.escape(rangs_b)}.</div></details>'
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
            "actuels du score Sant’active, renormalisés ; le foncier et le vieillissement en sont exclus.\n"
            "- **Indice besoins sanitaires** : moyenne à poids égaux des rangs percentiles de la part des 65 ans et plus "
            "et des prévalences CNAM 2023 standardisées sur l’âge lorsque la couverture des poids d’âge atteint 90 % "
            "(sinon brutes, signalé). Poids égaux faute de référence validée.\n"
            f"- **Sources** : {' ; '.join(f'{k} : {v}' for k, v in src.items())}.\n"
            f"- **Données manquantes** (départements sans valeur) : "
            + (", ".join(f"{k} : {v}" for k, v in manquants.items() if v) or "aucune")
            + ". Un indice de besoins calculé sur moins de composantes est moins robuste.\n"
            "- **Limites** : les quadrants dépendent des médianes (un département proche d’un trait change de couleur pour "
            "quelques dixièmes de point) ; les prévalences mesurent des patients pris en charge, pas des besoins non couverts ; "
            "les deux indices ne sont pas intégrés au score Sant’active et n’ont pas vocation à le remplacer sans validation. "
            "Matrice expérimentale : elle oriente l’examen, elle ne classe pas officiellement les territoires."
        )
