"""Page Comparer : 2 à 4 départements côte à côte."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..config import PALETTE, PLOTLY_TEMPLATE
from ..router import navigate


def render(data: dict) -> None:
    master: pd.DataFrame = data["master"]

    st.markdown(
        '<div class="fiche-topbar"><div class="breadcrumb">'
        '<a href="?view=home">Accueil</a>'
        '<span class="sep">›</span>'
        '<span class="current">Comparer</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="fiche-header">'
        '<div class="fiche-eyebrow">'
        '<span class="code">OUTIL</span>'
        '<span class="dot"></span>'
        '<span class="region">Analyse multi-territoriale</span>'
        '</div>'
        '<div class="fiche-title-row">'
        '<h1 class="fiche-title">Comparer</h1>'
        '</div>'
        '<p style="font-size:16px;color:#2B2B2B;max-width:720px;margin-top:16px;">'
        'Sélectionnez 2 à 4 départements pour les comparer sur tous les indicateurs clés.'
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Sélecteur de départements
    options = (
        master.dropna(subset=["Nom du département"])
        .sort_values("Nom du département")["Nom du département"]
        .tolist()
    )
    default: list[str] = []
    if "compare_base" in st.session_state:
        base = master[master["dept"] == st.session_state["compare_base"]]
        if not base.empty:
            default = [base.iloc[0]["Nom du département"]]

    selected: list[str] = st.multiselect(
        "Choisir 2 à 4 départements à comparer",
        options=options,
        default=default,
        max_selections=4,
        key="comparer_selection",
    )

    if len(selected) < 2:
        st.info("Sélectionnez au moins 2 départements pour lancer la comparaison.")
        return

    comp_df = master[master["Nom du département"].isin(selected)].copy()

    # ── TABLEAU SYNOPTIQUE ────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">TABLEAU SYNOPTIQUE</div>'
        '<h2 class="section-title">Les chiffres <em>côte à côte.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    metrics = [
        ("Score global",         "score_global",          ".1f", "/100"),
        ("APL (DREES)",          "apl_median_dept",       ".1f", "/hab."),
        ("Temps d'accès médian", "temps_acces_median",    ".1f", " min"),
        ("Médecins / 100k",      "med_gen_pour_100k",     ".0f", ""),
        ("Structures / 100k",    "structures_pour_100k",  ".1f", ""),
        ("Prix médian m²",       "prix_m2_moyen",         ".0f", " €"),
        ("Part des 65+",         "pct_plus_65",           ".1f", " %"),
        ("Communes > 15 min",    "nb_communes_critiques", ".0f", ""),
    ]

    header_cells = ""
    for d in selected:
        dept_code_val = ""
        rows_d = comp_df[comp_df["Nom du département"] == d]
        if not rows_d.empty:
            dept_code_val = rows_d.iloc[0]["dept"]
        header_cells += (
            f'<th>'
            f'<div class="col-dept-name">{d}</div>'
            f'<div class="col-dept-code">{dept_code_val}</div>'
            f'</th>'
        )

    # Indicateurs inversés (plus bas = meilleur)
    lower_is_better = {"temps_acces_median", "nb_communes_critiques"}

    rows_html = ""
    for label, col, fmt, unit in metrics:
        if col not in comp_df.columns:
            continue
        values = comp_df.set_index("Nom du département")[col]
        valid_vals = values.dropna()
        if valid_vals.empty:
            continue
        best_val = valid_vals.min() if col in lower_is_better else valid_vals.max()
        cells = ""
        for d in selected:
            v = values.get(d)
            if pd.isna(v) if not isinstance(v, float) else (v != v):
                cells += '<td class="cell-na">—</td>'
            else:
                is_best = abs(v - best_val) < 1e-9
                klass = "cell-best" if is_best else ""
                cells += f'<td class="{klass}">{format(v, fmt)}{unit}</td>'
        rows_html += f'<tr><td class="metric-label">{label}</td>{cells}</tr>'

    st.markdown(
        '<table class="comparison-table-v2">'
        '<thead>'
        f'<tr><th class="metric-col">Indicateur</th>{header_cells}</tr>'
        '</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '<p style="font-size:11px;color:#6B6B68;margin-top:12px;">'
        'Les meilleures valeurs sont mises en évidence en vert.'
        '</p>',
        unsafe_allow_html=True,
    )

    # ── RADAR COMPARATIF ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">RADAR COMPARATIF</div>'
        '<h2 class="section-title">Profils <em>superposés.</em></h2>'
        '<p class="section-lead">Tous les indicateurs sont normalisés en rang '
        'percentile national (0 = pire département, 100 = meilleur). '
        'Plus la surface est grande, meilleur est le profil global.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # 6 dimensions pertinentes — rang percentile national
    dimensions = [
        ("score_acces",        "Accès aux soins"),
        ("score_pros",         "Professionnels"),
        ("score_etabs",        "Établissements"),
        ("pct_plus_65",        "Jeunesse"),          # inversé : moins de 65+ = mieux
        ("prix_m2_moyen",      "Accessibilité\nfoncière"),  # inversé : prix bas = mieux
        ("temps_acces_median", "Proximité\nétablissements"),  # inversé : temps bas = mieux
    ]
    inverted_cols = {"pct_plus_65", "prix_m2_moyen", "temps_acces_median"}

    # Calcul des rangs percentiles sur tout le master
    master_ranks = master.copy()
    for col, _ in dimensions:
        if col not in master_ranks.columns:
            master_ranks[f"rank_{col}"] = 0.0
            continue
        if col in inverted_cols:
            master_ranks[f"rank_{col}"] = (
                100 - master_ranks[col].rank(pct=True, na_option="keep") * 100
            )
        else:
            master_ranks[f"rank_{col}"] = (
                master_ranks[col].rank(pct=True, na_option="keep") * 100
            )

    theta_labels = [d[1] for d in dimensions]
    colors = [
        PALETTE["bleu_regalien"],
        PALETTE["rouge_critique"],
        PALETTE["vert_sante"],
        PALETTE["ambre_alerte"],
    ]

    fig = go.Figure()
    for i, dept_name in enumerate(selected):
        row = master_ranks[master_ranks["Nom du département"] == dept_name]
        if row.empty:
            continue
        rv = row.iloc[0]
        r_vals = []
        for col, _ in dimensions:
            v = rv.get(f"rank_{col}")
            r_vals.append(float(v) if pd.notna(v) else 0.0)

        color_hex = colors[i % len(colors)]
        rgb = _hex_to_rgb(color_hex)
        fig.add_trace(
            go.Scatterpolar(
                r=r_vals + [r_vals[0]],
                theta=theta_labels + [theta_labels[0]],
                fill="toself",
                fillcolor=f"rgba({rgb},0.15)",
                line=dict(color=color_hex, width=2),
                name=dept_name,
            )
        )

    # Applique le template en retirant les clés passées explicitement dessous
    layout_opts = {
        k: v for k, v in PLOTLY_TEMPLATE["layout"].items()
        if k not in ("margin", "title", "legend", "polar")
    }
    fig.update_layout(
        **layout_opts,
        polar=dict(
            radialaxis=dict(
                range=[0, 100],
                visible=True,
                tickfont=dict(size=10, color=PALETTE["gris_secondaire"]),
                gridcolor=PALETTE["gris_bordure"],
            ),
            angularaxis=dict(
                tickfont=dict(size=12, family="Marianne, sans-serif"),
                gridcolor=PALETTE["gris_bordure"],
            ),
            bgcolor="#FFFFFF",
        ),
        height=520,
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="top", y=-0.08,
            xanchor="center", x=0.5, font=dict(size=13),
        ),
        margin=dict(l=80, r=80, t=20, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── LIENS VERS LES FICHES ─────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ACCÈS RAPIDE</div>'
        '<h2 class="section-title">Ouvrir la fiche <em>complète.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )
    link_cols = st.columns(len(selected))
    for i, dept_name in enumerate(selected):
        rows_d = comp_df[comp_df["Nom du département"] == dept_name]
        if rows_d.empty:
            continue
        dept_code_val = rows_d.iloc[0]["dept"]
        with link_cols[i]:
            if st.button(
                f"Fiche {dept_name} →",
                key=f"link_{dept_code_val}",
                use_container_width=True,
            ):
                navigate("dept", dept_code=dept_code_val)


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
