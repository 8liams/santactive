"""Page Comparer : 2 à 4 départements ou régions côte à côte."""

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

NATIONAL_LOWER_IS_BETTER = {
    "temps_acces_median", "nb_communes_critiques", "pct_plus_65", "prix_m2_moyen",
}

_RADAR_DIMENSIONS = [
    ("score_acces",        "Accès aux soins"),
    ("score_pros",         "Professionnels"),
    ("score_etabs",        "Établissements"),
    ("pct_plus_65",        "Jeunesse"),
    ("prix_m2_moyen",      "Accessibilité\nfoncière"),
    ("temps_acces_median", "Proximité\nétablissements"),
]
_RADAR_INVERTED = {"pct_plus_65", "prix_m2_moyen", "temps_acces_median"}


def _pop_weighted_mean(depts: pd.DataFrame, col: str) -> float:
    pop = pd.to_numeric(depts["population_num"], errors="coerce")
    vals = pd.to_numeric(depts[col], errors="coerce")
    mask = pop.notna() & vals.notna() & (pop > 0)
    if not mask.any():
        return float("nan")
    return float((vals[mask] * pop[mask]).sum() / pop[mask].sum())


def build_regions_comparison_df(master: pd.DataFrame) -> pd.DataFrame:
    """Agrège le master départemental en une ligne par région (même logique que fiche région)."""
    rows: list[dict] = []
    for code, group in master.groupby("Code région", sort=False):
        name = str(group["Nom de la région"].iloc[0])
        rows.append({
            "territory_name": name,
            "Nom du département": name,
            "Nom de la région": name,
            "Code région": str(code),
            "dept": "",
            "territory_type": "region",
            "score_global": _pop_weighted_mean(group, "score_global"),
            "apl_median_dept": group["apl_median_dept"].median(),
            "temps_acces_median": _pop_weighted_mean(group, "temps_acces_median"),
            "med_gen_pour_100k": _pop_weighted_mean(group, "med_gen_pour_100k"),
            "structures_pour_100k": _pop_weighted_mean(group, "structures_pour_100k"),
            "prix_m2_moyen": _pop_weighted_mean(group, "prix_m2_moyen"),
            "pct_plus_65": _pop_weighted_mean(group, "pct_plus_65"),
            "nb_communes_critiques": pd.to_numeric(
                group["nb_communes_critiques"], errors="coerce"
            ).fillna(0).sum(),
            "score_acces": _pop_weighted_mean(group, "score_acces"),
            "score_pros": _pop_weighted_mean(group, "score_pros"),
            "score_etabs": _pop_weighted_mean(group, "score_etabs"),
        })
    return pd.DataFrame(rows)


def _territory_label(kind: str, *, plural: bool = False) -> str:
    if kind == "region":
        return "régions" if plural else "région"
    return "départements" if plural else "département"


def render(data: dict) -> None:
    master: pd.DataFrame = data["master"]
    regions_df = build_regions_comparison_df(master)

    st.markdown(
        '<div class="fiche-header fiche-header-tool">'
        '<div class="fiche-eyebrow">'
        '<span class="code">OUTIL</span>'
        '<span class="dot"></span>'
        '<span class="region">Analyse multi-territoriale</span>'
        '</div>'
        '<div class="fiche-title-row">'
        '<h1 class="fiche-title">Comparaison</h1>'
        '</div>'
        '<p class="fiche-header-lead">'
        'Identifiez les écarts, les forces et les priorités entre plusieurs '
        'territoires en quelques secondes pour mieux agir.'
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="comparer-level-hint">'
        'Comparer 2 à 4 <strong>départements</strong> ou '
        '<strong>régions</strong> en fonction de leurs indicateurs clés.'
        '</p>'
        '<p class="comparer-level-hint comparer-level-step">'
        'Choisissez votre niveau d&rsquo;analyse'
        '</p>'
        '<span class="comparer-toggle-anchor" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )

    if "comparer_territory_kind" not in st.session_state:
        st.session_state["comparer_territory_kind"] = "dept"

    toggle_col1, toggle_col2, _ = st.columns([1.15, 1.15, 4.7])
    with toggle_col1:
        if st.button(
            "Départements",
            type="primary" if st.session_state["comparer_territory_kind"] == "dept" else "secondary",
            use_container_width=True,
            key="comparer_btn_dept",
        ):
            st.session_state["comparer_territory_kind"] = "dept"
            st.rerun()
    with toggle_col2:
        if st.button(
            "Régions",
            type="primary" if st.session_state["comparer_territory_kind"] == "region" else "secondary",
            use_container_width=True,
            key="comparer_btn_region",
        ):
            st.session_state["comparer_territory_kind"] = "region"
            st.rerun()

    is_region = st.session_state["comparer_territory_kind"] == "region"
    kind = "region" if is_region else "dept"
    mode_name = "Régions" if is_region else "Départements"
    mode_desc = (
        "Indicateurs agrégés à l'échelle régionale (18 régions)."
        if is_region
        else "Indicateurs à l'échelle départementale (101 départements)."
    )
    st.markdown(
        f'<div class="comparer-mode-banner comparer-mode-{kind}">'
        f'<span class="comparer-mode-kicker">Niveau actif</span>'
        f'<strong class="comparer-mode-name">{mode_name}</strong>'
        f'<span class="comparer-mode-desc">{mode_desc}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if is_region:
        source_df = regions_df
        options = (
            regions_df.dropna(subset=["territory_name"])
            .sort_values("territory_name")["territory_name"]
            .tolist()
        )
        default: list[str] = []
    else:
        source_df = master.assign(
            territory_name=master["Nom du département"],
            territory_type="dept",
        )
        options = (
            master.dropna(subset=["Nom du département"])
            .sort_values("Nom du département")["Nom du département"]
            .tolist()
        )
        default = []
        if "compare_base" in st.session_state:
            base = master[master["dept"] == st.session_state["compare_base"]]
            if not base.empty:
                default = [base.iloc[0]["Nom du département"]]

    placeholder = (
        "Ex : Bretagne, Occitanie"
        if is_region
        else "Ex : Ain, Aisne"
    )
    selected: list[str] = st.multiselect(
        f"Sélectionnez 2 à 4 {_territory_label(kind, plural=True)}",
        options=options,
        default=default,
        max_selections=4,
        placeholder=placeholder,
        key=f"comparer_selection_{kind}",
    )

    if len(selected) < 2:
        st.info(f"Sélectionnez au moins 2 {_territory_label(kind, plural=True)} pour lancer la comparaison.")
        return

    name_col = "territory_name" if is_region else "Nom du département"
    if is_region:
        comp_df = regions_df[regions_df["territory_name"].isin(selected)].copy()
    else:
        comp_df = source_df[source_df["Nom du département"].isin(selected)].copy()

    metrics = COMPARE_METRICS

    # ── TABLEAU COMPARATIF (avec référence nationale) ─────────────────────────
    _render_comparison_table(
        master, comp_df, selected, metrics, name_col=name_col, kind=kind,
    )

    # ── RADAR COMPARATIF ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">RADAR COMPARATIF</div>'
        '<h2 class="section-title">Profils <em>superposés.</em></h2>'
        '<p class="section-lead">Tous les indicateurs sont normalisés en rang '
        'percentile national (0 = pire, 100 = meilleur). '
        'Plus la surface est grande, meilleur est le profil global.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    rank_base = _build_rank_base(master, regions_df)
    master_ranks = _compute_radar_ranks(rank_base)

    theta_labels = [d[1] for d in _RADAR_DIMENSIONS]
    colors = [
        PALETTE["bleu_regalien"],
        PALETTE["rouge_critique"],
        PALETTE["vert_sante"],
        PALETTE["ambre_alerte"],
    ]

    fig = go.Figure()
    for i, name in enumerate(selected):
        row = master_ranks[master_ranks[name_col] == name]
        if row.empty:
            continue
        rv = row.iloc[0]
        r_vals = []
        for col, _ in _RADAR_DIMENSIONS:
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
                name=name,
            )
        )

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
    for i, name in enumerate(selected):
        rows_t = comp_df[comp_df[name_col] == name]
        if rows_t.empty:
            continue
        with link_cols[i]:
            if is_region:
                region_code_val = str(rows_t.iloc[0]["Code région"])
                if st.button(
                    f"Fiche {name} →",
                    key=f"link_region_{region_code_val}",
                    use_container_width=True,
                ):
                    navigate("region", region_code=region_code_val)
            else:
                dept_code_val = rows_t.iloc[0]["dept"]
                if st.button(
                    f"Fiche {name} →",
                    key=f"link_{dept_code_val}",
                    use_container_width=True,
                ):
                    navigate("dept", dept_code=dept_code_val)


def _territory_code(comp_df: pd.DataFrame, name: str, is_region: bool) -> str:
    rows = comp_df[comp_df["territory_name" if is_region else "Nom du département"] == name]
    if rows.empty:
        return ""
    if is_region:
        return str(rows.iloc[0]["Code région"])
    return str(rows.iloc[0]["dept"])


def _build_rank_base(master: pd.DataFrame, regions_df: pd.DataFrame) -> pd.DataFrame:
    dept_rows = master.assign(
        territory_name=master["Nom du département"],
        territory_type="dept",
    )
    return pd.concat([dept_rows, regions_df], ignore_index=True)


def _compute_radar_ranks(df: pd.DataFrame) -> pd.DataFrame:
    master_ranks = df.copy()
    for col, _ in _RADAR_DIMENSIONS:
        if col not in master_ranks.columns:
            master_ranks[f"rank_{col}"] = 0.0
            continue
        if col in _RADAR_INVERTED:
            master_ranks[f"rank_{col}"] = (
                100 - master_ranks[col].rank(pct=True, na_option="keep") * 100
            )
        else:
            master_ranks[f"rank_{col}"] = (
                master_ranks[col].rank(pct=True, na_option="keep") * 100
            )
    return master_ranks


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
    *,
    kind: str = "dept",
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
    unit = _territory_label(kind, plural=True)

    if col == "apl_median_dept":
        if better and not worse:
            return f"{_join_dept_names(better)} atteint la médiane nationale."
        if worse and not better:
            if len(worse) == len(selected):
                return f"Aucun des {unit} sélectionnés n'atteint la médiane nationale."
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
                return f"Aucun des {unit} sélectionnés ne dépasse la référence nationale."
            return f"{_join_dept_names(worse)} reste sous la référence nationale."

    if col == "score_global":
        if worse and not better:
            if len(worse) == len(selected):
                if len(selected) == 2:
                    return f"Les deux {unit} se situent sous la médiane nationale."
                return f"Tous les {unit} sélectionnés sont sous la médiane nationale."
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
            return f"Aucun des {unit} sélectionnés n'atteint la médiane nationale."
        return f"{_join_dept_names(worse)} reste sous la médiane nationale."
    if at and not better and not worse:
        return f"{names_all} est proche de la médiane nationale."
    return f"Écarts contrastés entre les {unit} sélectionnés."


def _render_comparison_table(
    master: pd.DataFrame,
    comp_df: pd.DataFrame,
    selected: list[str],
    metrics: list[tuple[str, str, str, str]],
    *,
    name_col: str = "Nom du département",
    kind: str = "dept",
) -> None:
    is_region = kind == "region"
    region_note = (
        ' Agrégats régionaux\u202f: médiane des départements pour l\'APL, '
        'moyennes pondérées par la population pour les autres indicateurs.'
        if is_region else ''
    )

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">TABLEAU COMPARATIF</div>'
        '<h2 class="section-title">Les chiffres <em>côte à côte.</em></h2>'
        '<p class="section-lead">Comparaison directe entre les territoires sélectionnés, '
        'avec la médiane nationale en référence.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    dept_headers = ""
    for name in selected:
        code_val = _territory_code(comp_df, name, is_region)
        dept_headers += (
            f'<th>'
            f'<div class="col-dept-name">{name}</div>'
            f'<div class="col-dept-code">{code_val}</div>'
            f'</th>'
        )

    rows_html = ""
    for label, col, fmt, unit in metrics:
        if col not in comp_df.columns:
            continue
        nat = _national_reference(master, col)
        values = comp_df.set_index(name_col)[col]
        dept_vals: dict[str, float] = {}
        for name in selected:
            v = values.get(name)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                dept_vals[name] = float(v)

        if nat is None or pd.isna(nat):
            nat_cell = '<td class="cell-na">N/D</td>'
        else:
            nat_cell = (
                f'<td class="cell-national-ref">{format(nat, fmt)}{unit}</td>'
            )

        dept_cells = ""
        for name in selected:
            v = values.get(name)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                dept_cells += '<td class="cell-na">N/D</td>'
                continue
            pos = _position_vs_national(float(v), nat, col) if nat is not None else None
            klass = {
                "better": "cell-above-nat",
                "worse": "cell-below-nat",
                "at": "cell-at-nat",
            }.get(pos or "", "")
            dept_cells += f'<td class="{klass}">{format(v, fmt)}{unit}</td>'

        lecture = _lecture_nationale(label, col, nat, dept_vals, selected, kind=kind)
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
        'défavorable), rouge = en dessous.'
        f'{region_note}'
        '</p>',
        unsafe_allow_html=True,
    )


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
