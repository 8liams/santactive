"""Page Comparer : 2 à 4 départements ou régions côte à côte."""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..config import PALETTE, PLOTLY_TEMPLATE
from ..router import navigate

# Médiane APL nationale (ANCT 2023) — même référence que l'accueil et les fiches dept.
APL_NATIONAL_REF = None  # référence = médiane des valeurs départementales (voir _national_reference)

COMPARE_METRICS: list[tuple[str, str, str, str]] = [
    ("Score global",         "score_global",          ".1f", "/100"),
    ("APL (DREES)",          "apl_dept",       ".1f", "/hab."),
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
            "apl_dept": group["apl_dept"].median(),
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

    if "comparer_preselect" in st.session_state:
        codes = st.session_state.pop("comparer_preselect")
        st.session_state["comparer_territory_kind"] = "dept"
        names: list[str] = []
        for code in codes:
            row = master[master["dept"] == str(code).zfill(2)]
            if not row.empty:
                names.append(str(row.iloc[0]["Nom du département"]))
        if names:
            st.session_state["comparer_selection_dept"] = names[:4]

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
        "Indicateurs agrégés à l'échelle régionale (17 régions, Mayotte exclue)."
        if is_region
        else "Indicateurs à l'échelle départementale (100 départements analysés)."
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
        default = st.session_state.get("comparer_selection_dept", [])
        if not default and "compare_base" in st.session_state:
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
    """Référence nationale — médiane des départements analysés (APL comprise)."""
    if col not in master.columns:
        return None
    val = pd.to_numeric(master[col], errors="coerce").median()
    return float(val) if pd.notna(val) else None


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


def _interpretation_scenario(better: list[str], worse: list[str], at: list[str]) -> str:
    """Retourne all_better | all_worse | all_at | mixed selon les positions vs référence."""
    if better and worse:
        return "mixed"
    if worse:
        return "all_worse"
    if better:
        return "all_better"
    return "all_at"


_INTERPRETATIONS: dict[str, dict[str, str]] = {
    "score_global": {
        "all_better": "Profil sanitaire global plus favorable que la référence nationale.",
        "all_worse": "Situation sanitaire globalement plus fragile que la référence nationale.",
        "all_at": "Profil sanitaire proche de la référence nationale.",
        "mixed": "Profils sanitaires contrastés entre les territoires sélectionnés.",
    },
    "apl_dept": {
        "all_better": "Accès aux médecins plus favorable que la médiane nationale.",
        "all_worse": "Accès aux soins de ville plus contraint que la médiane nationale.",
        "all_at": "Accessibilité aux médecins proche de la référence nationale.",
        "mixed": "Contraste marqué de l'accessibilité aux soins de ville entre les territoires.",
    },
    "temps_acces_median": {
        "all_better": "Temps d'accès inférieur à la médiane nationale.",
        "all_worse": "Éloignement plus marqué des établissements de santé.",
        "all_at": "Proximité des établissements proche de la référence nationale.",
        "mixed": "Écarts sensibles de proximité des établissements entre territoires.",
    },
    "med_gen_pour_100k": {
        "all_better": "Offre médicale supérieure à la médiane nationale.",
        "all_worse": "Densité médicale inférieure à la médiane nationale.",
        "all_at": "Densité médicale proche de la référence nationale.",
        "mixed": "Densité médicale inégale entre les territoires comparés.",
    },
    "structures_pour_100k": {
        "all_better": "Maillage hospitalier relativement dense.",
        "all_worse": "Offre hospitalière plus limitée que la référence nationale.",
        "all_at": "Maillage hospitalier proche de la référence nationale.",
        "mixed": "Maillage hospitalier contrasté entre les territoires sélectionnés.",
    },
    "prix_m2_moyen": {
        "all_better": "Conditions d'installation potentiellement favorables pour les professionnels.",
        "all_worse": "Foncier plus contraint que la médiane nationale.",
        "all_at": "Coût foncier proche de la référence nationale.",
        "mixed": "Conditions d'installation foncière contrastées entre territoires.",
    },
    "pct_plus_65": {
        "all_better": "Pression démographique liée au vieillissement plus modérée.",
        "all_worse": "Pression démographique liée au vieillissement plus élevée.",
        "all_at": "Structure démographique proche de la référence nationale.",
        "mixed": "Pression du vieillissement contrastée entre les territoires.",
    },
    "nb_communes_critiques": {
        "all_better": "Isolement territorial limité.",
        "all_worse": "Part importante de communes éloignées des soins.",
        "all_at": "Isolement territorial proche de la référence nationale.",
        "mixed": "Écarts marqués d'isolement territorial entre les territoires.",
    },
}


_IMPLICATIONS: dict[str, tuple[str, str, str]] = {
    # (libellé court, unité, implication lorsque l'écart est défavorable)
    "score_global": ("score global", "/100", "le territoire le moins bien classé cumule les signaux d'accès défavorables"),
    "apl_dept": ("APL pondéré", " consult./an/hab.", "l'accès aux généralistes y justifie en priorité les leviers d'installation et d'exercice coordonné"),
    "temps_acces_median": ("temps d'accès médian", " min", "l'éloignement y appelle des réponses de proximité (équipes mobiles, téléconsultation assistée)"),
    "med_gen_pour_100k": ("densité de généralistes", " /100k", "la démographie médicale y est le premier facteur limitant"),
    "structures_pour_100k": ("structures hospitalières", " /100k", "les consultations avancées et la coordination ville-hôpital y dépendent de sites moins nombreux"),
    "prix_m2_moyen": ("prix médian au m²", " €", "le coût du foncier peut y freiner l'installation (à l'inverse, un prix bas est un levier)"),
    "pct_plus_65": ("part des 65 ans et plus", " %", "la demande de soins liée à l'âge y est plus forte (parcours gériatriques, autonomie)"),
    "nb_communes_critiques": ("communes à plus de 15 min", "", "l'isolement y concerne davantage de communes (transport solidaire, permanences itinérantes)"),
}


def _fr(v: float, fmt: str) -> str:
    return format(v, fmt).replace(",", "\u202f").replace(".", ",")


def _interpretation_territoriale(
    col: str,
    nat: float | None,
    dept_values: dict[str, float],
    selected: list[str],
) -> str:
    """Conclusion chiffrée : qui est le moins doté, de combien, où par rapport à la référence, implication."""
    if nat is None or pd.isna(nat):
        return "Référence nationale indisponible pour cet indicateur."
    vals = {n: float(v) for n, v in dept_values.items() if n in selected and v is not None and pd.notna(v)}
    if not vals:
        return "Données insuffisantes pour interpréter cet indicateur."
    lib, unit, implication = _IMPLICATIONS.get(col, (col, "", ""))
    lower_better = col in NATIONAL_LOWER_IS_BETTER
    fmt = next((f for _, c, f, _ in COMPARE_METRICS if c == col), ".1f")
    pire = (max if lower_better else min)(vals, key=vals.get)
    meilleur = (min if lower_better else max)(vals, key=vals.get)
    v_pire, v_mieux = vals[pire], vals[meilleur]
    pos = {n: _position_vs_national(v, nat, col) for n, v in vals.items()}
    nb_worse = sum(1 for x in pos.values() if x == "worse")

    def _ecart_nat(v: float) -> str:
        if abs(nat) < 1e-9:
            return ""
        d = (v - nat) / abs(nat) * 100
        return f"{d:+.0f}\u202f% vs référence ({_fr(nat, fmt)}{unit})"

    if len(vals) == 1:
        n, v = next(iter(vals.items()))
        sens = {"worse": "défavorable", "better": "favorable", "at": "comparable"}[pos[n]]
        txt = f"{n}\u202f: {lib} de {_fr(v, fmt)}{unit}, {_ecart_nat(v)}, position {sens}."
        if pos[n] == "worse" and implication:
            txt += f" Implication\u202f: {implication}."
        return txt

    ecart = abs(v_pire - v_mieux)
    rel = (ecart / abs(v_mieux) * 100) if abs(v_mieux) > 1e-9 else float("nan")
    txt = (f"{pire} est le moins favorable ({lib} {_fr(v_pire, fmt)}{unit}, {_ecart_nat(v_pire)}) ; "
           f"{meilleur} le plus favorable ({_fr(v_mieux, fmt)}{unit}). Écart\u202f: {_fr(ecart, fmt)}{unit}"
           + (f" ({rel:.0f}\u202f%)" if pd.notna(rel) else "") + ".")
    if nb_worse == len(vals):
        txt += f" Les {len(vals)} territoires sont sous la référence nationale."
    elif nb_worse == 0:
        txt += " Aucun territoire n'est sous la référence nationale."
    else:
        txt += f" {nb_worse} territoire{'s' if nb_worse > 1 else ''} sur {len(vals)} sous la référence."
    if nb_worse and implication:
        txt += f" Implication\u202f: {implication}."
    return txt


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
        'moyennes pondérées par la population pour les autres indicateurs, '
        'somme pour les communes à plus de 15\u202fmin. ⚠ Mode expérimental\u202f: '
        'la référence reste une médiane de départements, non directement '
        'comparable à ces agrégats régionaux.'
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
            nat_cell = '<td class="cell-na" data-label="Réf. nationale">N/D</td>'
        else:
            nat_cell = (
                f'<td class="cell-national-ref" data-label="Réf. nationale">'
                f'{format(nat, fmt)}{unit}</td>'
            )

        dept_cells = ""
        for name in selected:
            safe_name = html.escape(name)
            v = values.get(name)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                dept_cells += (
                    f'<td class="cell-na" data-label="{safe_name}">N/D</td>'
                )
                continue
            pos = _position_vs_national(float(v), nat, col) if nat is not None else None
            klass = {
                "better": "cell-above-nat",
                "worse": "cell-below-nat",
                "at": "cell-at-nat",
            }.get(pos or "", "")
            dept_cells += (
                f'<td class="{klass}" data-label="{safe_name}">'
                f'{format(v, fmt)}{unit}</td>'
            )

        interpretation = _interpretation_territoriale(col, nat, dept_vals, selected)
        rows_html += (
            f'<tr>'
            f'<td class="metric-label">{label}</td>'
            f'{nat_cell}'
            f'{dept_cells}'
            f'<td class="cell-lecture" data-label="Interprétation">'
            f'{interpretation}</td>'
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
        '<th class="metric-col col-lecture">Interprétation</th>'
        '</tr>'
        '</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
        '<p style="font-size:11px;color:#6B6B68;margin-top:12px;">'
        'Référence nationale = médiane calculée sur les 100 départements analysés '
        '(APL\u202f: médiane des valeurs départementales, DREES 2023). '
        'Vert = au-dessus de la médiane (ou en dessous si l\'indicateur est '
        'défavorable), rouge = en dessous.'
        f'{region_note}'
        '</p>',
        unsafe_allow_html=True,
    )


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
