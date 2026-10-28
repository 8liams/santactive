"""Page Comparer : 2 à 4 départements ou régions côte à côte.

Expérience : territoires choisis affichés en cartouches (retirables), ajout par
recherche, suggestions (même région, profil similaire, situation contrastée),
premier territoire pré-rempli depuis le territoire de référence. Résultats :
ce que l'on apprend (écarts majeurs, meilleur / moins bon par dimension,
points communs, conséquences possibles), tableau avec référence nationale,
radar, accès aux fiches.
"""

from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ..config import APL_SOURCE_LABEL, TEMPS_LABEL_COURT

from .. import territoire as T
from ..components.aide import aide_methodo
from ..components.nav import internal_href
from ..config import PALETTE, PLOTLY_TEMPLATE
from ..router import navigate

# Médiane APL nationale (DREES, millésime actif) — même référence que l'accueil et les fiches dept.
APL_NATIONAL_REF = None  # référence = médiane des valeurs départementales (voir _national_reference)

COMPARE_METRICS: list[tuple[str, str, str, str]] = [
    ("Score Sant’active",         "score_global",          ".1f", "/100"),
    ("APL (DREES)",          "apl_dept",       ".1f", "/hab."),
    (f"Temps d'accès médian ({TEMPS_LABEL_COURT}, score)", "temps_acces_median", ".1f", " min"),
    ("Médecins / 100k",      "med_gen_pour_100k",     ".0f", ""),
    ("Structures / 100k",    "structures_pour_100k",  ".1f", ""),
    ("Prix médian m²",       "prix_m2_moyen",         ".0f", " €"),
    ("Part des 65+",         "pct_plus_65",           ".1f", " %"),
    ("Hab. à > 15 min d'un généraliste", "acces_mg_part_sup_15_pct", ".1f", " %"),
]

NATIONAL_LOWER_IS_BETTER = {
    "temps_acces_median", "nb_communes_critiques", "pct_plus_65", "prix_m2_moyen", "acces_mg_part_sup_15_pct",
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

# Dimensions commentées dans la synthèse (libellé lisible, unité, format)
_SYNTH_METRICS = list(COMPARE_METRICS)


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
            "population_num": pd.to_numeric(group["population_num"], errors="coerce").sum(),
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
            "acces_mg_part_sup_15_pct": (float(pd.to_numeric(group["acces_mg_pop_sup_15"], errors="coerce").sum()
                                               / pd.to_numeric(group["acces_mg_pop"], errors="coerce").sum() * 100)
                                         if pd.to_numeric(group["acces_mg_pop"], errors="coerce").sum() > 0 else float("nan")),
            "score_acces": _pop_weighted_mean(group, "score_acces"),
            "score_pros": _pop_weighted_mean(group, "score_pros"),
            "score_etabs": _pop_weighted_mean(group, "score_etabs"),
            "nb_depts": len(group),
        })
    return pd.DataFrame(rows)


def _territory_label(kind: str, *, plural: bool = False) -> str:
    if kind == "region":
        return "régions" if plural else "région"
    return "départements" if plural else "département"


# ── Sélection ─────────────────────────────────────────────────────────────────

def _init_selection(master: pd.DataFrame, regions_df: pd.DataFrame) -> None:
    """Pré-remplissage : lien ?depts=, navigation programmatique, territoire de référence."""
    t = T.get()
    if "comparer_territory_kind" not in st.session_state:
        st.session_state["comparer_territory_kind"] = "region" if t.kind == "region" else "dept"
    qp_depts = st.query_params.get("depts")
    if qp_depts and "comparer_preselect" not in st.session_state \
            and st.session_state.get("_comparer_qp_applied") != qp_depts:
        st.session_state["_comparer_qp_applied"] = qp_depts
        st.session_state["comparer_preselect"] = [c.strip() for c in str(qp_depts).split(",") if c.strip()][:4]
    if "comparer_preselect" in st.session_state:
        codes = [str(c).zfill(2) for c in st.session_state.pop("comparer_preselect")]
        st.session_state["comparer_territory_kind"] = "dept"
        st.session_state["cmp_sel_dept"] = [c for c in codes if (master["dept"] == c).any()][:4]
    elif "compare_base" in st.session_state:
        base = str(st.session_state.pop("compare_base")).zfill(2)
        st.session_state["comparer_territory_kind"] = "dept"
        st.session_state["cmp_sel_dept"] = [base]
    if "cmp_sel_dept" not in st.session_state:
        st.session_state["cmp_sel_dept"] = [t.code] if t.kind == "dept" and (master["dept"] == t.code).any() else []
    if "cmp_sel_region" not in st.session_state:
        st.session_state["cmp_sel_region"] = [t.code] if t.kind == "region" and (regions_df["Code région"] == t.code).any() else []
    # Rétro-compat : anciens multiselect par nom
    if st.session_state.get("comparer_selection_dept") and not st.session_state["cmp_sel_dept"]:
        names = st.session_state.pop("comparer_selection_dept")
        st.session_state["cmp_sel_dept"] = master[master["Nom du département"].isin(names)]["dept"].astype(str).tolist()[:4]


def _similar(code: str, master: pd.DataFrame, n: int = 3, *, contraste: bool = False) -> list[str]:
    """Départements de profil proche (score, part des 65+, densité) ou, en contraste, de zone opposée
    mais de population comparable."""
    r = master[master["dept"] == code]
    if r.empty:
        return []
    r = r.iloc[0]
    cand = master[master["dept"] != code].copy()
    for c in ("score_global", "pct_plus_65", "densite", "population_num"):
        cand[c] = pd.to_numeric(cand[c], errors="coerce")
    sc, p65, dens, pop = (pd.to_numeric(pd.Series([r.get(c)]), errors="coerce").iloc[0]
                          for c in ("score_global", "pct_plus_65", "densite", "population_num"))
    if contraste:
        zone = str(r.get("zone_short", ""))
        cible = {"Critique": "Favorable", "Favorable": "Critique"}.get(zone, "Critique")
        cand = cand[cand["zone_short"] == cible]
        if pd.notna(pop) and pop > 0:
            import math
            cand = cand.assign(_d=(cand["population_num"] / pop).apply(
                lambda x: abs(math.log(x)) if pd.notna(x) and x > 0 else 9.0)).sort_values("_d")
        return cand["dept"].astype(str).head(n).tolist()
    def _z(col, val):
        s = cand[col]
        sd = s.std() or 1.0
        return ((s - val) / sd).abs() if pd.notna(val) else pd.Series(0.0, index=cand.index)
    cand["_d"] = _z("score_global", sc) + _z("pct_plus_65", p65) + 0.5 * _z("densite", dens)
    cand = cand[cand["typologie"] == r.get("typologie")] if (cand["typologie"] == r.get("typologie")).sum() >= n else cand
    return cand.sort_values("_d")["dept"].astype(str).head(n).tolist()


def _chip_html(name: str, sub: str, score, zone: str) -> str:
    badge = {"Critique": "crit", "Intermédiaire": "inter", "Favorable": "fav"}.get(zone, "")
    sc = f"{float(score):.0f}" if pd.notna(score) else "N/D"
    return (f'<div class="cmp-chip"><div class="cmp-chip-name">{html.escape(name)}</div>'
            f'<div class="cmp-chip-sub">{html.escape(sub)}</div>'
            f'<div class="cmp-chip-score"><b>{sc}</b><span>/100</span>'
            + (f'<i class="cmp-chip-zone {badge}">{html.escape(zone)}</i>' if zone and zone != "N/D" else "") + '</div></div>')


def render(data: dict) -> None:
    master: pd.DataFrame = data["master"].copy()
    master["acces_mg_part_sup_15_pct"] = pd.to_numeric(master.get("acces_mg_part_sup_15"), errors="coerce") * 100
    regions_df = build_regions_comparison_df(master)
    _init_selection(master, regions_df)

    st.markdown(
        '<div class="fiche-header fiche-header-tool">'
        '<div class="fiche-eyebrow"><span class="code">OUTIL</span><span class="dot"></span>'
        '<span class="region">Analyse multi-territoriale</span></div>'
        '<div class="fiche-title-row"><h1 class="fiche-title">Comparer <em>des territoires</em></h1></div>'
        '<p class="fiche-header-lead">Deux à quatre départements, ou deux à quatre régions, côte à côte : '
        'où sont les écarts, qui est le mieux et le moins bien placé sur chaque dimension, et ce que cela implique.</p>'
        f'{aide_methodo("comparer")}</div>', unsafe_allow_html=True)

    kinds = {"dept": "Départements", "region": "Régions"}
    kind = st.radio("Niveau de comparaison", list(kinds), format_func=kinds.get, horizontal=True,
                    key="comparer_territory_kind")
    is_region = kind == "region"
    sel_key = f"cmp_sel_{kind}"
    selected_codes: list[str] = list(st.session_state.get(sel_key, []))

    if is_region:
        source_df = regions_df.set_index("Code région")
        all_codes = source_df.sort_values("territory_name").index.tolist()
        name_of = {c: str(source_df.loc[c, "territory_name"]) for c in all_codes}
        sub_of = {c: f"{int(source_df.loc[c, 'nb_depts'])} départements" for c in all_codes}
    else:
        source_df = master.set_index("dept")
        all_codes = source_df.sort_values("Nom du département").index.astype(str).tolist()
        name_of = {c: str(source_df.loc[c, "Nom du département"]) for c in all_codes}
        sub_of = {c: f"{c} · {source_df.loc[c, 'Nom de la région']}" for c in all_codes}

    # ── Cartouches des territoires choisis + ajout ───────────────────────────
    st.markdown('<div class="section-eyebrow" style="margin-top:6px;">Territoires comparés</div>', unsafe_allow_html=True)
    if selected_codes:
        cols = st.columns(len(selected_codes) + (1 if len(selected_codes) < 4 else 0))
        for i, code in enumerate(selected_codes):
            row = source_df.loc[code]
            with cols[i]:
                st.markdown(_chip_html(name_of[code], sub_of[code], row.get("score_global"),
                                       str(row.get("zone_short", "")) if not is_region else ""), unsafe_allow_html=True)
                if st.button("Retirer", key=f"cmp_rm_{kind}_{code}", use_container_width=True):
                    st.session_state[sel_key] = [c for c in selected_codes if c != code]
                    st.rerun()
        add_col = cols[-1] if len(selected_codes) < 4 else None
    else:
        add_col = st.container()
    if add_col is not None:
        with add_col:
            restants = [c for c in all_codes if c not in selected_codes]
            def _on_add():
                v = st.session_state.get(f"cmp_add_{kind}")
                if v and v not in st.session_state.get(sel_key, []):
                    st.session_state[sel_key] = (st.session_state.get(sel_key, []) + [v])[:4]
                st.session_state[f"cmp_add_{kind}"] = None
            st.selectbox(f"Ajouter {'une région' if is_region else 'un département'}", restants, index=None,
                         format_func=lambda c: f"{name_of[c]}" + ("" if is_region else f" ({c})"),
                         placeholder="Rechercher et ajouter…", key=f"cmp_add_{kind}", on_change=_on_add)

    # ── Suggestions ──────────────────────────────────────────────────────────
    if selected_codes and len(selected_codes) < 4:
        base = selected_codes[0]
        sugg: list[tuple[str, list[str]]] = []
        if is_region:
            autres = [c for c in all_codes if c not in selected_codes]
            scores = source_df.loc[autres, "score_global"].astype(float)
            base_sc = float(source_df.loc[base, "score_global"])
            proches = (scores - base_sc).abs().sort_values().index.tolist()
            sugg.append(("Profil proche", proches[:3]))
            sugg.append(("Situation contrastée", (scores - base_sc).abs().sort_values(ascending=False).index.tolist()[:3]))
        else:
            reg = str(source_df.loc[base, "Code région"])
            meme = [c for c in master.loc[master["Code région"].astype(str) == reg, "dept"].astype(str) if c not in selected_codes]
            if meme:
                sugg.append((f"Même région ({html.escape(str(source_df.loc[base, 'Nom de la région']))})", meme[:4]))
            sugg.append(("Profil similaire", [c for c in _similar(base, master, 4) if c not in selected_codes][:3]))
            sugg.append(("Situation contrastée", [c for c in _similar(base, master, 4, contraste=True) if c not in selected_codes][:3]))
        for lab, codes in sugg:
            codes = [c for c in codes if c and c not in selected_codes]
            if not codes:
                continue
            c0, *cs = st.columns([1.1] + [1] * len(codes) + [max(0.1, 4 - len(codes))])
            c0.markdown(f'<div class="cmp-sugg-lbl">{lab}</div>', unsafe_allow_html=True)
            for col, code in zip(cs, codes):
                if col.button(name_of[code], key=f"cmp_sugg_{kind}_{lab[:6]}_{code}", use_container_width=True):
                    st.session_state[sel_key] = (selected_codes + [code])[:4]
                    st.rerun()

    if len(selected_codes) < 2:
        st.markdown('<p class="sa-couverture" style="margin-top:10px;">Ajoutez au moins deux territoires pour lancer la comparaison. '
                    'La référence nationale (médiane des 100 départements) est toujours affichée.</p>', unsafe_allow_html=True)
        return

    selected = [name_of[c] for c in selected_codes]
    name_col = "territory_name" if is_region else "Nom du département"
    if is_region:
        comp_df = regions_df[regions_df["Code région"].isin(selected_codes)].copy()
    else:
        comp_df = master[master["dept"].isin(selected_codes)].assign(territory_name=lambda d: d["Nom du département"]).copy()
    metrics = COMPARE_METRICS

    # ── CE QU'ON APPREND ──────────────────────────────────────────────────────
    _render_synthese(master, comp_df, selected, name_col=name_col, kind=kind)

    # ── TABLEAU COMPARATIF (avec référence nationale) ─────────────────────────
    _render_comparison_table(master, comp_df, selected, metrics, name_col=name_col, kind=kind)

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
    colors = [PALETTE["bleu_regalien"], PALETTE["rouge_critique"], PALETTE["vert_sante"], PALETTE["ambre_alerte"]]
    fig = go.Figure()
    for i, name in enumerate(selected):
        row = master_ranks[master_ranks[name_col] == name]
        if row.empty:
            continue
        rv = row.iloc[0]
        r_vals = [float(rv.get(f"rank_{col}")) if pd.notna(rv.get(f"rank_{col}")) else 0.0 for col, _ in _RADAR_DIMENSIONS]
        color_hex = colors[i % len(colors)]
        rgb = _hex_to_rgb(color_hex)
        fig.add_trace(go.Scatterpolar(r=r_vals + [r_vals[0]], theta=theta_labels + [theta_labels[0]], fill="toself",
                                      fillcolor=f"rgba({rgb},0.15)", line=dict(color=color_hex, width=2), name=name))
    layout_opts = {k: v for k, v in PLOTLY_TEMPLATE["layout"].items() if k not in ("margin", "title", "legend", "polar")}
    fig.update_layout(
        **layout_opts,
        polar=dict(radialaxis=dict(range=[0, 100], visible=True, tickfont=dict(size=10, color=PALETTE["gris_secondaire"]),
                                   gridcolor=PALETTE["gris_bordure"]),
                   angularaxis=dict(tickfont=dict(size=12, family="Marianne, sans-serif"), gridcolor=PALETTE["gris_bordure"]),
                   bgcolor="#FFFFFF"),
        height=520, showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.08, xanchor="center", x=0.5, font=dict(size=13)),
        margin=dict(l=80, r=80, t=20, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── LIENS VERS LES FICHES ─────────────────────────────────────────────────
    links = "".join(
        f'<a class="primary" href="{internal_href("region", region_code=c) if is_region else internal_href("dept", dept_code=c)}" target="_self">'
        f'Fiche {html.escape(name_of[c])} →</a>' for c in selected_codes)
    st.markdown(f'<div class="sa-parcours" style="margin-top:8px;">{links}</div>', unsafe_allow_html=True)


def _render_synthese(master: pd.DataFrame, comp_df: pd.DataFrame, selected: list[str], *, name_col: str, kind: str) -> None:
    """Ce qu'on apprend : écarts majeurs, meilleur / moins bon par dimension, points communs, implications."""
    vals_by: dict[str, dict[str, float]] = {}
    for _, col, _, _ in _SYNTH_METRICS:
        if col not in comp_df.columns:
            continue
        v = comp_df.set_index(name_col)[col]
        vals_by[col] = {n: float(v.get(n)) for n in selected if n in v.index and pd.notna(v.get(n))}
    ecarts = []
    for label, col, fmt, unit in _SYNTH_METRICS:
        vals = vals_by.get(col, {})
        if len(vals) < 2:
            continue
        nat = _national_reference(master, col)
        lower = col in NATIONAL_LOWER_IS_BETTER
        pire = (max if lower else min)(vals, key=vals.get)
        mieux = (min if lower else max)(vals, key=vals.get)
        rel = abs(vals[pire] - vals[mieux]) / abs(nat) if nat else 0.0
        pos = {n: _position_vs_national(v, nat, col) for n, v in vals.items()} if nat is not None else {}
        ecarts.append((rel, label, col, fmt, unit, pire, mieux, vals, pos, nat))
    if not ecarts:
        return
    ecarts.sort(key=lambda e: e[0], reverse=True)
    majeurs = [e for e in ecarts[:3] if e[0] >= 0.08]
    communs = [e for e in ecarts if e[0] < 0.08 or (e[8] and len(set(e[8].values())) == 1 and "at" not in e[8].values())]

    lib_fr = {"acces_mg_part_sup_15_pct": "la part d’habitants à plus de 15 min d’un généraliste", "score_global": "le score Sant’active", "apl_dept": "l’accessibilité aux généralistes (APL)",
              "temps_acces_median": f"le temps d’accès ({TEMPS_LABEL_COURT})", "med_gen_pour_100k": "la densité de généralistes",
              "structures_pour_100k": "l’offre hospitalière", "prix_m2_moyen": "le prix du foncier", "pct_plus_65": "la part des 65 ans et plus"}
    li = ""
    for rel, label, col, fmt, unit, pire, mieux, vals, pos, nat in majeurs:
        li += (f"<li><strong>{lib_fr.get(col, label).capitalize()}</strong> : {html.escape(pire)} ({_fr(vals[pire], fmt)}{unit}) "
               f"contre {html.escape(mieux)} ({_fr(vals[mieux], fmt)}{unit}), soit un écart de {rel * 100:.0f}\u202f% de la référence nationale"
               + (f" ({_fr(nat, fmt)}{unit})" if nat is not None else "") + ".</li>")
    ecarts_html = f"<ul class='cmp-list'>{li}</ul>" if li else "<p>Les territoires comparés sont proches sur toutes les dimensions.</p>"

    rows = ""
    for rel, label, col, fmt, unit, pire, mieux, vals, pos, nat in sorted(ecarts, key=lambda e: _SYNTH_METRICS.index(next(m for m in _SYNTH_METRICS if m[1] == e[2]))):
        rows += (f"<tr><td class='metric-label'>{label}</td><td class='cell-above-nat'>{html.escape(mieux)} <span>{_fr(vals[mieux], fmt)}{unit}</span></td>"
                 f"<td class='cell-below-nat'>{html.escape(pire)} <span>{_fr(vals[pire], fmt)}{unit}</span></td></tr>")
    table = ("<table class='comparison-table-v2 cmp-best-worst'><thead><tr><th class='metric-col'>Dimension</th>"
             "<th class='metric-col'>Le plus favorable</th><th class='metric-col'>Le moins favorable</th></tr></thead>"
             f"<tbody>{rows}</tbody></table>")

    pc = []
    for rel, label, col, fmt, unit, pire, mieux, vals, pos, nat in ecarts:
        if not pos:
            continue
        side = set(pos.values())
        if side == {"worse"}:
            pc.append(f"tous sous la référence nationale pour {lib_fr.get(col, label)}")
        elif side == {"better"}:
            pc.append(f"tous mieux placés que la référence pour {lib_fr.get(col, label)}")
    communs_html = ("<p><strong>Points communs</strong> : " + " ; ".join(pc) + ".</p>") if pc else \
        "<p><strong>Points communs</strong> : aucune dimension où tous les territoires sont du même côté de la référence nationale.</p>"

    impl = []
    for rel, label, col, fmt, unit, pire, mieux, vals, pos, nat in majeurs:
        lib, u, implication = _IMPLICATIONS.get(col, (label, unit, ""))
        if implication and pos.get(pire) == "worse":
            impl.append(f"<li>Pour {html.escape(pire)}, {implication}.</li>")
    impl_html = (f"<p><strong>Conséquences possibles</strong></p><ul class='cmp-list'>{''.join(impl)}</ul>") if impl else ""

    st.markdown(
        '<div class="section-header"><div class="section-eyebrow">CE QU’ON APPREND</div>'
        '<h2 class="section-title">Les écarts <em>qui comptent.</em></h2></div>'
        f'<div class="cmp-synth"><div class="cmp-synth-main"><p><strong>Écarts majeurs</strong></p>{ecarts_html}{communs_html}{impl_html}'
        '<p class="sa-couverture">Référence nationale = médiane des 100 départements. Un écart est jugé majeur au-delà de 8 % de cette référence. '
        'Les indicateurs décrivent l’offre et le contexte : ils ne mesurent pas l’accès effectif aux rendez-vous.</p></div>'
        f'<div class="cmp-synth-side">{table}</div></div>',
        unsafe_allow_html=True)


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
    "acces_mg_part_sup_15_pct": {
        "all_better": "Éloignement d'un généraliste moins fréquent que la référence nationale.",
        "all_worse": "Part d'habitants à plus de 15 min d'un généraliste supérieure à la référence.",
        "all_at": "Éloignement d'un généraliste proche de la référence nationale.",
        "mixed": "Écarts marqués d'éloignement d'un généraliste entre territoires.",
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
    "score_global": ("score Sant’active", "/100", "le territoire le moins bien classé cumule les signaux d'accès défavorables"),
    "apl_dept": ("APL pondéré", " consult./an/hab.", "l'accès aux généralistes y justifie en priorité les leviers d'installation et d'exercice coordonné"),
    "temps_acces_median": ("temps d'accès médian", " min", "l'éloignement y appelle des réponses de proximité (équipes mobiles, téléconsultation assistée)"),
    "med_gen_pour_100k": ("densité de généralistes", " /100k", "la démographie médicale y est le premier facteur limitant"),
    "structures_pour_100k": ("structures hospitalières", " /100k", "les consultations avancées et la coordination ville-hôpital y dépendent de sites moins nombreux"),
    "prix_m2_moyen": ("prix médian au m²", " €", "le coût du foncier peut y freiner l'installation (à l'inverse, un prix bas est un levier)"),
    "pct_plus_65": ("part des 65 ans et plus", " %", "la demande de soins liée à l'âge y est plus forte (parcours gériatriques, autonomie)"),
    "nb_communes_critiques": ("communes à plus de 15 min d'un généraliste (temps moyen, INSEE 2025)", "", "l'isolement y concerne davantage de communes (transport solidaire, permanences itinérantes)"),
    "acces_mg_part_sup_15_pct": ("part d'habitants à plus de 15 min d'un généraliste", " %", "l'éloignement géographique y justifie des réponses de proximité (antennes, permanences, transport solidaire) — mesure INSEE 2025, hors Guadeloupe, Guyane et Mayotte"),
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
                f'{_fr(nat, fmt)}{unit}</td>'
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
                f'{_fr(float(v), fmt)}{unit}</td>'
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
        f'(APL\u202f: médiane des valeurs départementales, {APL_SOURCE_LABEL}). '
        'Vert = au-dessus de la médiane (ou en dessous si l\'indicateur est '
        'défavorable), rouge = en dessous.'
        f'{region_note}'
        '</p>',
        unsafe_allow_html=True,
    )


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"
