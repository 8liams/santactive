"""Page Comparer : 2 à 4 départements côte à côte."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..config import PALETTE, PLOTLY_TEMPLATE
from ..router import navigate

# Médiane APL nationale (ANCT 2023) — même référence que l'accueil et les fiches dept.
APL_NATIONAL_REF = 2.9

COMPARE_METRICS: list[tuple[str, str, str, str]] = [
    ("Score global",         "score_global",          ".1f", "/100"),
    ("APL (DREES)",          "apl_median_dept",       ".1f", "/hab."),
    ("Temps d'accès médian", "temps_acces_median",    ".1f", " min"),
    ("Médecins / 100k",      "med_gen_pour_100k",     ".0f", ""),
    ("Structures / 100k",    "structures_pour_100k",  ".1f", ""),
    ("Prix médian m²",       "prix_m2_moyen",         ".0f", " €"),
    ("Part des 65+",         "pct_plus_65",           ".1f", " %"),
    ("Communes > 15 min",    "nb_communes_critiques", ".0f", ""),
]

# Indicateurs où une valeur plus basse est favorable — comparaison inter-départements
COMPARE_LOWER_IS_BETTER = {"temps_acces_median", "nb_communes_critiques"}

# Indicateurs où une valeur plus basse est favorable vs la médiane nationale
NATIONAL_LOWER_IS_BETTER = {
    "temps_acces_median", "nb_communes_critiques", "pct_plus_65", "prix_m2_moyen",
}


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

    metrics = COMPARE_METRICS

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

    # Indicateurs inversés (plus bas = meilleur) — comparaison inter-départements
    lower_is_better = COMPARE_LOWER_IS_BETTER

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
        '<div class="sa-tbl-scroll">'
        '<table class="comparison-table-v2">'
        '<thead>'
        f'<tr><th class="metric-col">Indicateur</th>{header_cells}</tr>'
        '</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
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

    # ── RÉFÉRENCE NATIONALE ───────────────────────────────────────────────────
    _render_national_reference_table(master, comp_df, selected, metrics)

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


def _national_reference(master: pd.DataFrame, col: str) -> float | None:
    """Référence nationale — médiane sur tous les départements (APL = ANCT 2,9)."""
    if col == "apl_median_dept":
        return APL_NATIONAL_REF
    if col not in master.columns:
        return None
    val = pd.to_numeric(master[col], errors="coerce").median()
    return float(val) if pd.notna(val) else None


def _join_dept_names(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} et {names[1]}"
    return ", ".join(names[:-1]) + f" et {names[-1]}"


def _position_vs_national(
    value: float,
    nat: float,
    col: str,
    *,
    tol_ratio: float = 0.02,
) -> str:
    """Retourne 'better', 'worse' ou 'at' par rapport à la médiane nationale."""
    higher_better = col not in NATIONAL_LOWER_IS_BETTER
    tol = max(abs(nat) * tol_ratio, 1e-9)
    if abs(value - nat) <= tol:
        return "at"
    if higher_better:
        return "better" if value > nat else "worse"
    return "better" if value < nat else "worse"


def _lecture_nationale(
    label: str,
    col: str,
    nat: float | None,
    dept_values: dict[str, float],
    selected: list[str],
) -> str:
    """Génère une phrase courte de lecture vs médiane nationale."""
    if nat is None or pd.isna(nat):
        return "Référence nationale indisponible."

    better, worse, at = [], [], []
    for name in selected:
        v = dept_values.get(name)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        pos = _position_vs_national(float(v), nat, col)
        if pos == "better":
            better.append(name)
        elif pos == "worse":
            worse.append(name)
        else:
            at.append(name)

    n = len(better) + len(worse) + len(at)
    if n == 0:
        return "Données insuffisantes pour cette comparaison."

    names_all = _join_dept_names(selected[:4])

    if col == "apl_median_dept":
        if better and not worse:
            return f"{_join_dept_names(better)} atteint la médiane nationale."
        if worse and not better:
            if len(worse) == len(selected):
                return "Aucun département n'atteint la médiane nationale."
            return f"{_join_dept_names(worse)} reste sous la médiane nationale."
        if at and not better and not worse:
            return f"{names_all} se situe à la médiane nationale."
        return f"{_join_dept_names(better)} au-dessus, {_join_dept_names(worse)} en dessous."

    if col == "temps_acces_median":
        if worse and not better:
            if len(worse) == 1:
                return f"{worse[0]} reste moins accessible que la médiane nationale."
            return f"{_join_dept_names(worse)} restent moins accessibles que la médiane nationale."
        if better and not worse:
            return f"{_join_dept_names(better)} est plus accessible que la médiane nationale."
        if at and not better and not worse:
            return f"{names_all} est proche de la médiane nationale."

    if col == "med_gen_pour_100k":
        if len(better) == 1 and not worse:
            return f"{better[0]} dépasse la référence nationale."
        if better and not worse:
            return f"{_join_dept_names(better)} dépassent la référence nationale."
        if worse and not better:
            if len(worse) == len(selected):
                return "Aucun département ne dépasse la référence nationale."
            return f"{_join_dept_names(worse)} reste sous la référence nationale."

    if col == "score_global":
        if worse and not better:
            if len(worse) == len(selected):
                if len(selected) == 2:
                    return "Les deux départements se situent sous la médiane nationale."
                return "Tous les départements sélectionnés sont sous la médiane nationale."
            return f"{_join_dept_names(worse)} se situe sous la médiane nationale."
        if better and not worse:
            return f"{_join_dept_names(better)} se situe au-dessus de la médiane nationale."
        if at and not better and not worse:
            return f"{names_all} est proche de la médiane nationale."

    # Lecture générique
    if better and not worse:
        return f"{_join_dept_names(better)} est au-dessus de la médiane nationale."
    if worse and not better:
        if len(worse) == len(selected):
            return "Aucun département n'atteint la médiane nationale."
        return f"{_join_dept_names(worse)} reste sous la médiane nationale."
    if at and not better and not worse:
        return f"{names_all} est proche de la médiane nationale."
    return f"Écarts contrastés entre les départements sélectionnés."


def _render_national_reference_table(
    master: pd.DataFrame,
    comp_df: pd.DataFrame,
    selected: list[str],
    metrics: list[tuple[str, str, str, str]],
) -> None:
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">RÉFÉRENCE NATIONALE</div>'
        '<h2 class="section-title">Par rapport à la <em>France.</em></h2>'
        '<p class="section-lead">Médiane nationale sur l\'ensemble des départements. '
        'Permet de situer chaque territoire au-delà de la comparaison directe.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    dept_headers = ""
    for d in selected:
        dept_code_val = ""
        rows_d = comp_df[comp_df["Nom du département"] == d]
        if not rows_d.empty:
            dept_code_val = rows_d.iloc[0]["dept"]
        dept_headers += (
            f'<th>'
            f'<div class="col-dept-name">{d}</div>'
            f'<div class="col-dept-code">{dept_code_val}</div>'
            f'</th>'
        )

    rows_html = ""
    for label, col, fmt, unit in metrics:
        if col not in comp_df.columns:
            continue
        nat = _national_reference(master, col)
        values = comp_df.set_index("Nom du département")[col]
        dept_vals: dict[str, float] = {}
        for d in selected:
            v = values.get(d)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                dept_vals[d] = float(v)

        if nat is None or pd.isna(nat):
            nat_cell = '<td class="cell-na">—</td>'
        else:
            nat_cell = (
                f'<td class="cell-national-ref">{format(nat, fmt)}{unit}</td>'
            )

        dept_cells = ""
        for d in selected:
            v = values.get(d)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                dept_cells += '<td class="cell-na">—</td>'
                continue
            pos = _position_vs_national(float(v), nat, col) if nat is not None else None
            klass = {
                "better": "cell-above-nat",
                "worse": "cell-below-nat",
                "at": "cell-at-nat",
            }.get(pos or "", "")
            dept_cells += f'<td class="{klass}">{format(v, fmt)}{unit}</td>'

        lecture = _lecture_nationale(label, col, nat, dept_vals, selected)
        rows_html += (
            f'<tr>'
            f'<td class="metric-label">{label}</td>'
            f'{nat_cell}'
            f'{dept_cells}'
            f'<td class="cell-lecture">{lecture}</td>'
            f'</tr>'
        )

    st.markdown(
        '<div class="sa-tbl-scroll">'
        '<table class="comparison-table-v2 comparison-table-national">'
        '<thead>'
        '<tr>'
        '<th class="metric-col">Indicateur</th>'
        '<th class="metric-col col-national">Réf. nationale</th>'
        f'{dept_headers}'
        '<th class="metric-col col-lecture">Lecture</th>'
        '</tr>'
        '</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
        '<p style="font-size:11px;color:#6B6B68;margin-top:12px;">'
        'Référence nationale = médiane calculée sur les 101 départements '
        '(APL\u202f: médiane ANCT 2023, 2,9\u202f/hab.). '
        'Vert = au-dessus de la médiane (ou en dessous si l\'indicateur est '
        ' défavorable), rouge = en dessous.'
        '</p>',
        unsafe_allow_html=True,
    )


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
