"""Fiche département : la page-rapport d'un territoire."""

from __future__ import annotations

import html
import unicodedata

import pandas as pd
import streamlit as st

from ..audio_diagnostic import build_audio_diagnostic_text, render_audio_diagnostic_button
from ..components import render_alert, zone_badge_html
from ..components.tooltip import info_tooltip
from ..config import CMAP, PALETTE, PATHOS_EXCLUDED
from ..components.share_bar import dept_share_context, render_fiche_share_bar
from ..components.maps import DEPT_CENTER
from ..components.nav import NavCrumb, internal_href, render_breadcrumb
from ..pdf_export import generate_department_pdf
from ..action_impact import project_levier_impact, render_impact_html
from ..router import navigate, navigate_compare
from ..scoring import fmt_classement_national, to_num
from ..components.delais import APL_SEUIL_DESERT
from ..config import APL_AGREGATION, APL_LABEL, APL_LABEL_COURT
from ..offre_medicale import render_offre_medicale_drees
from ..simulation_capacite import render_simulation_capacite
from ..pathologies import (
    PATHO_CARDIO,
    dept_prevalences_standardisees,
    PATHO_DIABETE,
    PREV_SEUIL_RELATIF,
    dept_prevalences,
)


# ──────────────────────────────────────────────────────────────────────────────
# ENTRÉE PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────

def render(data: dict) -> None:
    dept_code = st.session_state.get("dept_code", "")
    master: pd.DataFrame = data["master"]
    row = master[master["dept"] == dept_code]

    if row.empty:
        st.error(f"Département « {dept_code} » introuvable.")
        if st.button("← Retour accueil"):
            navigate("home")
        return

    r = row.iloc[0]

    render_topbar(r, data)
    render_header(r, master)
    render_diagnostic(r, master, data)
    render_recommandations(r, master, data)
    render_scorecard(r, master)
    render_carte_communale(r, data)
    render_contexte(r, data)
    render_simulation_capacite(r)   # APL pondéré + simulation ETP (si fichier DREES présent)
    render_offre_medicale(r, data)
    render_delais_rdv(r, data)
    render_suggestions_comparaison(r, master)


# ──────────────────────────────────────────────────────────────────────────────
# TOPBAR
# ──────────────────────────────────────────────────────────────────────────────

def render_topbar(r: pd.Series, data: dict) -> None:
    region_code = str(r.get("Code région", ""))
    region_name = str(r.get("Nom de la région", ""))
    dept_name = str(r["Nom du département"])
    dept_code = str(r.get("dept", "")).zfill(2)

    render_breadcrumb([
        NavCrumb("Accueil", "home"),
        NavCrumb(region_name, "region", {"region_code": region_code}),
        NavCrumb(dept_name),
    ], key_prefix=f"dept_bc_{dept_code}")

    share = dept_share_context(r)
    pdf_bytes: bytes | None = None
    pdf_error: str | None = None
    try:
        recos = _generate_recommendations(r, data["master"], data)
        pdf_bytes = generate_department_pdf(r, data["master"], recos, data)
    except Exception as exc:
        pdf_error = str(exc)

    dept_slug = dept_name.lower().replace(" ", "_").replace("'", "")

    def _compare_btn() -> None:
        if st.button("Comparer avec…", use_container_width=True, key="dept_compare_btn"):
            st.session_state["compare_base"] = r["dept"]
            navigate("comparer")

    render_fiche_share_bar(
        fiche_url=share["fiche_url"],
        email_subject=share["email_subject"],
        email_body=share["email_body"],
        share_title=share["share_title"],
        pdf_bytes=pdf_bytes,
        pdf_filename=f"santactive_{dept_slug}.pdf",
        pdf_error=pdf_error,
        extra_col=_compare_btn,
        key_prefix=f"dept_share_{dept_code}",
        compact=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. HEADER
# ──────────────────────────────────────────────────────────────────────────────

def render_header(r: pd.Series, master: pd.DataFrame) -> None:
    score = r.get("score_global")
    zone = str(r.get("zone_short", "N/D"))

    # Rang national — source unique : rang_national / nb_classes (scoring.py),
    # identique au PDF, au partage et à l'audio.
    rang_num = to_num(r.get("rang_national"))
    nb_total = int(master["score_global"].notna().sum())

    pop = r.get("population_num", 0)
    pop_str = f"{int(pop):,}\u202fhab.".replace(",", "\u202f") if pd.notna(pop) and pop else "N/D"

    typologie_labels = {
        "urbain_dense": "Urbain dense",
        "urbain":       "Urbain",
        "peri_urbain":  "Péri-urbain",
        "rural":        "Rural",
        "inconnu":      "N/D",
    }
    typologie_str = typologie_labels.get(str(r.get("typologie", "inconnu")), "N/D")

    badge_class = {"Critique": "crit", "Intermédiaire": "inter", "Favorable": "fav"}.get(zone, "")
    score_str = f"{float(score):.1f}" if pd.notna(score) else "N/D"
    classement_str = (
        fmt_classement_national(rang_num, nb_total)
        if pd.notna(rang_num)
        else "N/D"
    )

    st.markdown(
        '<div class="fiche-header">'
        '<div class="fiche-eyebrow">'
        f'<span class="code">DÉP. {r["dept"]}</span>'
        '<span class="dot"></span>'
        f'<span class="region">{r.get("Nom de la région", "")}</span>'
        '<span class="dot"></span>'
        f'<span class="region">{pop_str}</span>'
        '<span class="dot"></span>'
        f'<span class="region">{typologie_str}</span>'
        '</div>'
        '<div class="fiche-title-row">'
        f'<h1 class="fiche-title">{r["Nom du département"]}</h1>'
        f'<div class="fiche-zone-badge {badge_class}">Zone {zone.lower()}</div>'
        '</div>'
        '<div class="fiche-meta fiche-meta--scores">'
        '<div class="fiche-meta-item">'
        f'<span class="label">SCORE GLOBAL {info_tooltip("score_global", open_dir="right")}</span>'
        f'<span class="value">{score_str}<span class="small">/100</span></span>'
        '</div>'
        '<div class="fiche-meta-item">'
        f'<span class="label">CLASSEMENT NATIONAL {info_tooltip("rang_national", open_dir="right")}</span>'
        f'<span class="value">{classement_str}<span class="small">/{nb_total}</span></span>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. DIAGNOSTIC
# ──────────────────────────────────────────────────────────────────────────────

def _get_situation_label(r: pd.Series) -> tuple[str, str]:
    """Retourne (label_css, label_texte) aligné sur le badge de zone.

    La zone (terciles du score global) est la seule qualification de la
    situation d'ensemble : la phrase ne doit pas contredire le badge.
    """
    zone = str(r.get("zone_short", "")).strip()
    if zone == "Critique":
        return ("crit", "défavorable (tiers inférieur national)")
    if zone == "Intermédiaire":
        return ("inter", "intermédiaire (tiers médian national)")
    if zone == "Favorable":
        return ("fav", "favorable (tiers supérieur national)")
    return ("inter", "non qualifiable (données insuffisantes)")


def _get_ecart_apl(r: pd.Series, apl_nat: float) -> str | None:
    """Phrase d'écart de l'APL à la médiane des départements, ou None."""
    apl = to_num(r.get("apl_dept"))
    if pd.isna(apl) or pd.isna(apl_nat) or apl_nat <= 0:
        return None
    delta_pct = (apl - apl_nat) / apl_nat * 100
    if delta_pct < -5:
        return (f"une accessibilité aux généralistes (APL) inférieure de "
                f"{abs(delta_pct):.0f}\u202f% à la médiane des départements")
    if delta_pct > 5:
        return (f"une accessibilité aux généralistes (APL) supérieure de "
                f"{delta_pct:.0f}\u202f% à la médiane des départements")
    return None


def render_diagnostic(r: pd.Series, master: pd.DataFrame, data: dict) -> None:
    """Phrase éditoriale + APL en chiffre géant (données ANCT)."""
    dept_nom = str(r.get("Nom du département", "Ce département"))
    css_class, label_texte = _get_situation_label(r)
    apl_nat = (
        float(master["apl_dept"].median())
        if "apl_dept" in master.columns
        else float("nan")
    )
    ecart_apl = _get_ecart_apl(r, apl_nat)
    _nb_crit = to_num(r.get("nb_communes_critiques"))
    nb_communes_critiques = int(_nb_crit) if pd.notna(_nb_crit) else 0

    if ecart_apl:
        complement = f"<em class='{css_class}'>{label_texte}</em>, avec {ecart_apl}"
    else:
        complement = f"<em class='{css_class}'>{label_texte}</em>"

    if nb_communes_critiques > 0:
        commune_label = "commune" if nb_communes_critiques == 1 else "communes"
        complement += (f", et {nb_communes_critiques} {commune_label} "
                       "avec un temps d'accès supérieur à 15\u202fmin")

    complement += "."

    phrase = f"{dept_nom} présente une situation {complement}"

    # APL ANCT (réel si disponible, sinon absent)
    apl = to_num(r.get("apl_dept"))

    col1, col2 = st.columns([1.4, 1], gap="large")
    with col1:
        st.markdown(
            f'<div class="diagnostic-prose">{phrase}</div>',
            unsafe_allow_html=True,
        )
    with col2:
        if pd.notna(apl) and pd.notna(apl_nat):
            delta_apl = (apl - apl_nat) / apl_nat * 100
            delta_str = f"{delta_apl:+.0f} %"

            if apl < APL_SEUIL_DESERT:
                color = "crit"
                verdict = f"sous le repère de sous-densité ({APL_SEUIL_DESERT})"
                verdict_detail = f"médiane des départements\u202f: {apl_nat:.1f}"
            elif apl < apl_nat * 0.9:
                color = "inter"
                verdict = "sous la médiane des départements"
                verdict_detail = f"médiane des départements\u202f: {apl_nat:.1f}"
            else:
                color = "fav"
                verdict = "au niveau ou au-dessus de la médiane des départements"
                verdict_detail = f"médiane des départements\u202f: {apl_nat:.1f}"

            st.markdown(
                f'<div class="diagnostic-kpi">'
                f'<div class="diagnostic-kpi-label">'
                f'APL · ACCESSIBILITÉ AUX MÉDECINS GÉNÉRALISTES {info_tooltip("apl")}'
                f'</div>'
                f'<div class="diagnostic-kpi-value {color}">'
                f'{apl:.1f}<span class="max"> consult./an/hab.</span>'
                f'</div>'
                f'<div style="font-size:13px;color:var(--{color},#666);'
                f'font-weight:500;margin:8px 0 4px;">'
                f'{verdict.capitalize()}'
                f'</div>'
                f'<div class="diagnostic-kpi-context">'
                f'<span style="font-size:12px;color:#6B6B68;">{verdict_detail}</span>'
                f'<span style="font-weight:500;">{delta_str}</span>'
                f'</div>'
                f'<div style="font-size:10px;color:#9C9A92;margin-top:10px;'
                f'letter-spacing:0.08em;text-transform:uppercase;">'
                f'Source ANCT · Observatoire des territoires · 2023'
                f'&nbsp;·&nbsp;'
                f'{APL_AGREGATION} · repère sous-densité &lt; 2,5'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="diagnostic-kpi" style="opacity:0.7;">'
                f'<div class="diagnostic-kpi-label">'
                f'APL · ACCESSIBILITÉ AUX MÉDECINS GÉNÉRALISTES {info_tooltip("apl")}'
                f'</div>'
                '<div class="diagnostic-kpi-value" style="color:#9C9A92;">N/D</div>'
                '<div class="diagnostic-kpi-context">'
                '<span>Donnée ANCT non disponible pour ce département</span>'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    dept_code = str(r.get("dept", "")).zfill(2)

    def _dept_audio_text() -> str:
        recos = _generate_recommendations(r, master, data)
        return build_audio_diagnostic_text(r, master, recos, data)

    render_audio_diagnostic_button(
        scope_key=f"dept_{dept_code}",
        build_text=_dept_audio_text,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. SCORECARD
# ──────────────────────────────────────────────────────────────────────────────

def render_scorecard(r: pd.Series, master: pd.DataFrame) -> None:
    """Synthèse compacte des six dimensions, détail complet dans un panneau dépliable."""
    from ..scoring import DIMENSIONS, get_score_breakdown

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">SCORECARD</div>'
        '<h2 class="section-title">Où ce département <em>décroche,</em> et où il tient bon\u00a0?</h2>'
        '</div>',
        unsafe_allow_html=True,
    )
    tiles = ""
    for b in get_score_breakdown(r):
        sc = b["score"]
        if sc is None:
            val, col, delta = "N/D", "#9C9A92", "donnée absente"
        else:
            col = "#A51C30" if sc < 33 else "#C8922A" if sc < 67 else "#1B5E3F"
            d = int(sc - 50)
            delta = f"{d:+d} pts vs médiane"
            val = f"{int(sc)}"
        tiles += (
            f'<div class="sc-tile" style="border-top:3px solid {col};">'
            f'<div class="sc-tile-label">{b["label"]} <span class="sc-tile-w">{int(b["weight"] * 100)}\u202f%</span></div>'
            f'<div class="sc-tile-val" style="color:{col};">{val}</div>'
            f'<div class="sc-tile-delta">{delta}</div></div>'
        )
    st.markdown(f'<div class="sc-tiles">{tiles}</div>', unsafe_allow_html=True)
    with st.expander("Détail des six dimensions (valeurs, sources, explications)"):
        _render_scorecard_detail(r, master)


def _render_scorecard_detail(r: pd.Series, master: pd.DataFrame) -> None:


    # ── Scores ────────────────────────────────────────────────────────────
    # Score ou valeur absente → NaN, affiché « N/D » (jamais 50 ni 0 inventés)
    score_acces  = to_num(r.get("score_acces"))
    score_pros   = to_num(r.get("score_pros"))
    score_etabs  = to_num(r.get("score_etabs"))
    score_apl    = to_num(r.get("score_apl"))
    score_temps  = to_num(r.get("score_temps"))
    score_med    = to_num(r.get("score_medecins"))
    score_senior = to_num(r.get("score_seniors"))
    score_fonc   = to_num(r.get("score_foncier"))

    val_acces  = to_num(r.get("apl_dept"))
    val_pros   = to_num(r.get("med_gen_pour_100k"))
    val_etabs  = to_num(r.get("structures_pour_100k"))
    val_apl    = to_num(r.get("apl_dept"))
    val_temps  = to_num(r.get("temps_acces_median"))
    val_65     = to_num(r.get("pct_plus_65"))
    val_prix   = to_num(r.get("prix_m2_moyen"))

    def _render_bar(label, sublabel, score, raw_val, unit,
                    tooltip_key=None, indent=False):
        if pd.isna(score):
            _render_bar_nd(label, sublabel, tooltip_key, indent)
            return
        tip = info_tooltip(tooltip_key) if tooltip_key else ""
        indent_css = (
            "padding-left:28px;border-left:2px solid #E8E6DD;margin-left:8px;"
            if indent else ""
        )
        lbl_size   = "13px" if indent else "15px"
        lbl_weight = "500"  if indent else "600"
        num_size   = "20px" if indent else "26px"
        mb         = "14px" if indent else "24px"
        try:
            pos = max(2, min(98, int(float(score))))
        except (ValueError, TypeError):
            pos = 50

        if score < 33:
            dot_color = "#A51C30"
        elif score < 67:
            dot_color = "#C8922A"
        else:
            dot_color = "#1B5E3F"

        try:
            d = int(float(score) - 50)
        except (ValueError, TypeError):
            d = 0
        d_str   = f"+{d}\u202fpts vs médiane" if d >= 0 else f"{d}\u202fpts vs médiane"
        d_color = "#1B5E3F" if d >= 0 else "#A51C30"
        val_str = (
            f'<span style="color:#6B6B68;margin-left:6px;">·</span>'
            f' <span style="color:#6B6B68;">{raw_val:.1f}\u202f{unit}</span>'
            if pd.notna(raw_val) else ""
        )

        st.markdown(
            f'<div style="margin-bottom:{mb};{indent_css}">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:baseline;margin-bottom:6px;">'
            f'<div>'
            f'<span style="font-size:{lbl_size};font-weight:{lbl_weight};'
            f'color:#0A1938;">{label}</span>{tip}'
            f'<div style="font-size:11px;color:#9C9A92;margin-top:2px;">'
            f'{sublabel}{val_str}</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<div style="font-size:{num_size};font-weight:300;'
            f'color:#0A1938;line-height:1;">{int(score)}</div>'
            f'<div style="font-size:11px;color:{d_color};'
            f'font-weight:600;margin-top:2px;">{d_str}</div>'
            f'</div>'
            f'</div>'
            f'<div style="position:relative;height:8px;border-radius:4px;'
            f'background:linear-gradient(to right,'
            f'#F5D0D0 0%,#F5D0D0 33%,'
            f'#F0E8D8 33%,#F0E8D8 67%,'
            f'#D0E8DC 67%,#D0E8DC 100%);">'
            f'<div style="position:absolute;left:50%;top:-3px;'
            f'width:1.5px;height:14px;background:#8B8B8B;'
            f'transform:translateX(-50%);opacity:0.5;"></div>'
            f'<div style="position:absolute;left:{pos}%;top:50%;'
            f'transform:translate(-50%,-50%);'
            f'width:14px;height:14px;border-radius:50%;'
            f'background:white;border:2.5px solid {dot_color};'
            f'box-shadow:0 1px 4px rgba(0,0,0,0.15);"></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    def _render_bar_nd(label, sublabel, tooltip_key=None, indent=False):
        tip = info_tooltip(tooltip_key) if tooltip_key else ""
        indent_css = (
            "padding-left:28px;border-left:2px solid #E8E6DD;margin-left:8px;"
            if indent else ""
        )
        mb = "14px" if indent else "24px"
        st.markdown(
            f'<div style="margin-bottom:{mb};{indent_css}">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:baseline;margin-bottom:6px;">'
            f'<div><span style="font-size:15px;font-weight:600;color:#0A1938;">'
            f'{label}</span>{tip}'
            f'<div style="font-size:11px;color:#9C9A92;margin-top:2px;">{sublabel}</div>'
            f'</div>'
            f'<div style="text-align:right;font-size:20px;color:#9C9A92;">N/D</div>'
            f'</div>'
            f'<div style="font-size:11px;color:#9C9A92;">'
            f'Donnée non disponible · dimension exclue du score global '
            f'(poids redistribué)</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── 3 barres principales + sous-dimensions ────────────────────────────
    _render_bar("Accès aux soins", "APL (60 %) + temps d'accès (40 %) · valeur affichée : APL",
                score_acces, val_acces, "/hab.", tooltip_key="apl")
    _render_bar("Accessibilité APL", "Consultations disponibles / hab.",
                score_apl, val_apl, "/hab.", indent=True)
    _couv_t = to_num(r.get("couverture_temps"))
    _render_bar("Accessibilité physique",
                "Temps d'accès communal (médiane simple) · 0 = offre dans la commune"
                + (f" · ⚠ {_couv_t:.0%} des communes couvertes" if pd.notna(_couv_t) and _couv_t < 0.9 else ""),
                score_temps, val_temps, "min", indent=True)

    _render_bar(
        "Professionnels de santé",
        "Médecins généralistes pour 100\u202f000 hab.",
        score_pros, val_pros, "/100k", tooltip_key="med_100k",
    )

    _render_bar("Établissements", "Hôpitaux + cliniques FINESS",
                score_etabs, val_etabs, "/100k")

    # ── Séparateur + facteurs de contexte ────────────────────────────────
    st.markdown(
        '<div style="border-top:1px solid #E8E6DD;margin:8px 0 20px;"></div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#9C9A92;margin-bottom:16px;">'
        'FACTEURS DE CONTEXTE · poids dans le score global'
        '</div>',
        unsafe_allow_html=True,
    )

    _render_bar("Pression démographique", "Part des 65+ · demande de soins",
                score_senior, val_65, "%")
    _render_bar("Contexte foncier", "Prix m² · attractivité installation",
                score_fonc, val_prix, "€/m²")

    # ── Note ──────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="margin-top:8px;font-size:11px;color:#9C9A92;line-height:1.6;">'
        "Score Sant'active v2 · rang percentile national · "
        "0\u202f= pire département · 100\u202f= meilleur · "
        "La barre verticale grise indique la médiane nationale (50)."
        '</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 4. CARTE COMMUNALE
# ──────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper().strip()


SINGLE_COMMUNE_DEPTS = {"75"}  # extensible si d'autres identifiés


def render_carte_communale(r: pd.Series, data: dict) -> None:
    from ..commune_opportunity import (
        action_priority_legend_items,
        build_commune_code_lookup,
        build_commune_opportunity_df,
        top_communes_for_action,
    )
    from ..components import render_commune_choropleth
    from ..components.maps import _fetch_communes_geojson, fetch_communes_population

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ZOOM TERRITORIAL</div>'
        '<h2 class="section-title">Communes prioritaires pour une '
        '<em>action de santé.</em></h2>'
        '<p class="section-lead">'
        "Cette carte identifie les communes où une action de santé pourrait "
        "avoir le plus d\u2019impact, en croisant l\u2019éloignement aux soins, "
        "la population concernée et les conditions de déploiement. "
        "Survolez une commune pour voir le détail."
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    dept_code = str(r["dept"]).zfill(2)

    if dept_code in SINGLE_COMMUNE_DEPTS:
        st.markdown(
            '<div style="background:#FCF4DB;border:1px solid #F4C430;border-radius:4px;'
            'padding:16px 20px;margin:16px 0;">'
            '<strong style="color:#7D4A00;">Département mono-communal</strong><br>'
            '<span style="font-size:13px;color:#2B2B2B;">'
            "Ce département correspond à une seule commune. La cartographie "
            "infra-communale (arrondissements, quartiers) sera disponible dans "
            "une prochaine version de Sant'active."
            "</span></div>",
            unsafe_allow_html=True,
        )
        return

    communes_gj = _fetch_communes_geojson(dept_code)
    if communes_gj is None:
        st.warning("Découpage communal indisponible (API geo.api.gouv.fr).")
        return

    name_to_code, code_to_name = build_commune_code_lookup(
        communes_gj.get("features", [])
    )
    population_by_code = fetch_communes_population(dept_code)
    if not population_by_code:
        for feat in communes_gj.get("features", []):
            code = feat.get("properties", {}).get("code", "")
            pop = feat.get("properties", {}).get("population")
            if code and pop is not None:
                try:
                    population_by_code[str(code).zfill(5)] = float(pop)
                except (TypeError, ValueError):
                    pass

    temps: pd.DataFrame = data["temps"]
    immo: pd.DataFrame = data["immo"]
    temps_f = temps[temps["code_departement"].astype(str).str.zfill(2) == dept_code]
    immo_f = immo[immo["code_departement"].astype(str).str.zfill(2) == dept_code]

    if temps_f.empty and immo_f.empty:
        st.info("Données communales indisponibles pour ce département.")
        return
    if temps_f.empty:
        st.info("Données de temps d'accès indisponibles pour ce département.")
        return
    if immo_f.empty:
        st.info("Données immobilières indisponibles pour ce département.")
        return

    comm_data = build_commune_opportunity_df(
        temps_f,
        immo_f,
        name_to_code,
        code_to_name=code_to_name,
        population_by_code=population_by_code or None,
    )
    if comm_data.empty:
        nb_temps = temps_f["commune"].nunique()
        nb_immo = immo_f["commune"].nunique()
        st.warning(
            f"Impossible de croiser les données pour ce département "
            f"({nb_temps} communes avec temps d'accès, {nb_immo} avec prix immobilier, "
            f"mais aucune commune commune identifiée sur les deux sources). "
            "Les libellés diffèrent probablement entre les fichiers sources."
        )
        return

    comm_data["tt_score"] = comm_data["score_action"].apply(
        lambda x: f"{float(x):.0f} /100" if pd.notna(x) else "N/D"
    )
    comm_data["tt_pop"] = comm_data["population"].apply(
        lambda x: f"{int(x):,}".replace(",", "\u202f") if pd.notna(x) else "N/D"
    )
    comm_data["tt_temps"] = comm_data["temps_acces"].apply(
        lambda x: f"{float(x):.1f} min" if pd.notna(x) else "N/D"
    )
    comm_data["tt_niveau"] = comm_data["niveau"]
    matched = len(comm_data)

    etabs: pd.DataFrame = data["etabs"]
    etabs_f = etabs[etabs["code_departement"].astype(str).str.zfill(2) == dept_code]
    etabs_overlay = None
    if "latitude" in etabs_f.columns and "longitude" in etabs_f.columns:
        etabs_overlay = etabs_f[["latitude", "longitude", "Rslongue"]].copy()
        etabs_overlay.columns = ["lat", "lon", "nom"]
        etabs_overlay = etabs_overlay.dropna(subset=["lat", "lon"]).head(50)

    render_commune_choropleth(
        dept_code=dept_code,
        data_by_commune=comm_data,
        value_col="value",
        metric_label="Priorité d'action locale",
        unit="",
        colormap_name="action_priority",
        etabs_overlay=etabs_overlay,
        height=540,
        key=f"commune_map_{dept_code}_action",
        discrete=True,
        color_col="color_hex",
        tooltip_fields=["nom", "tt_score", "tt_pop", "tt_temps", "tt_niveau"],
        tooltip_aliases=[
            "Commune",
            "Score d'action",
            "Population",
            "Temps d'accès",
            "Niveau de priorité",
        ],
        legend_items=action_priority_legend_items(),
    )

    score_uses_pop = (
        "score_inclut_population" in comm_data.columns
        and bool(comm_data["score_inclut_population"].any())
    )
    st.caption(
        f"{matched} communes analysées · score d\u2019opportunité d\u2019action "
        f"(besoin sanitaire, population concernée, faisabilité"
        + ("" if score_uses_pop else ", population non disponible")
        + ") · survolez pour afficher le détail."
    )

    _render_top_communes_action(comm_data)


def _render_top_communes_action(comm_data: pd.DataFrame) -> None:
    """Top 10 communes où une action pourrait avoir le plus d'impact."""
    from ..commune_opportunity import top_communes_for_action

    top = top_communes_for_action(comm_data, limit=10)
    if top.empty:
        return

    st.markdown(
        '<div class="section-header" style="margin-top:32px;">'
        '<div class="section-eyebrow">PRIORISATION LOCALE</div>'
        '<h2 class="section-title">Top 10 des communes où une action '
        'pourrait avoir le plus d\u2019<em>impact.</em></h2>'
        '<p class="section-lead">'
        "Synthèse d\u2019aide à la décision pour cibler une intervention "
        "de santé à l\u2019échelle communale."
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    rows_html = ""
    for i, row in top.iterrows():
        pop = row.get("population")
        impact = row.get("impact_population")
        niveau = str(row.get("niveau", "N/D"))
        facteur = html.escape(str(row.get("facteur_principal", "N/D")))
        commune_name = html.escape(str(row.get("commune", "N/D")))
        pop_str = (
            f"{int(pop):,}".replace(",", "\u202f") if pd.notna(pop) else "N/D"
        )
        impact_str = (
            f"{int(impact):,}".replace(",", "\u202f") if pd.notna(impact) else "N/D"
        )
        rows_html += (
            f'<tr>'
            f'<td class="cell-rank" data-label="Rang">{i + 1}</td>'
            f'<td class="metric-label">{commune_name}</td>'
            f'<td data-label="Population concernée">{pop_str}</td>'
            f'<td data-label="Population INSEE">{impact_str}</td>'
            f'<td data-label="Niveau de priorité">{niveau}</td>'
            f'<td data-label="Facteurs principaux" '
            f'style="font-size:13px;color:#4A4A4A;line-height:1.45;">'
            f'{facteur}</td>'
            f'</tr>'
        )

    st.markdown(
        '<div class="sa-tbl-scroll">'
        '<table class="comparison-table-v2 commune-action-table">'
        '<thead>'
        '<tr>'
        '<th class="metric-col">Rang</th>'
        '<th class="metric-col">Commune</th>'
        '<th class="metric-col">Population concernée</th>'
        '<th class="metric-col">Population (INSEE)</th>'
        '<th class="metric-col">Niveau de priorité</th>'
        '<th class="metric-col">Facteurs principaux</th>'
        '</tr>'
        '</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
        '<p class="commune-action-meth-note">'
        "Le classement identifie les communes où une action pourrait avoir "
        "le plus d\u2019impact au regard des données disponibles. "
        "Il ne constitue pas une recommandation d\u2019implantation médicale "
        "et doit être complété par l\u2019expertise des acteurs locaux."
        "</p>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 5. PLAN D'ACTION
# ──────────────────────────────────────────────────────────────────────────────

# Affichage uniquement — leviers sans hiérarchie visuelle

_RECO_METH_NOTE = (
    "Ces recommandations sont générées à partir des caractéristiques du territoire. "
    "Elles ne constituent pas un ordre de mise en œuvre et doivent être adaptées "
    "au contexte local, aux moyens disponibles et aux acteurs mobilisables."
)

_IMPACT_METH_NOTE = (
    "L'impact potentiel n'est pas une prédiction médicale. Il s'agit d'une estimation "
    "prudente de la population potentiellement concernée, calculée à partir des "
    "données disponibles (population INSEE, seniors, pathologies CNAM, communes "
    "isolées, indicateurs territoriaux)."
)


def render_recommandations(r: pd.Series, master: pd.DataFrame, data: dict) -> None:
    recos = _generate_recommendations(r, master, data)
    nb = len(recos)

    if nb == 0:
        return

    st.html(
        '<div class="section-header">'
        '<div class="section-eyebrow">PLAN D\'ACTION</div>'
        '<h2 class="section-title">Leviers d\'action <em>recommandés</em>.</h2>'
        '<p class="section-lead">Leviers sélectionnés par un catalogue de règles explicites '
        '(conditions vérifiées sur les indicateurs observés du département, au plus deux par famille). '
        'Pistes d\'action argumentées, pas des prescriptions.</p>'
        '</div>'
    )

    st.markdown(
        f'<p class="reco-impact-meth-note">{_IMPACT_METH_NOTE}</p>',
        unsafe_allow_html=True,
    )

    if nb == 1:
        _render_reco_card(recos[0], r, data)
    else:
        for i in range(0, nb, 2):
            c1, c2 = st.columns(2, gap="large")
            for j, col in enumerate([c1, c2]):
                if i + j >= nb:
                    break
                with col:
                    _render_reco_card(recos[i + j], r, data)

    st.markdown(
        f'<p class="reco-meth-note">{_RECO_METH_NOTE}</p>',
        unsafe_allow_html=True,
    )


def _fmt_int(v) -> str:
    """Entier avec séparateur fin, « N/D » si absent."""
    return f"{int(round(v)):,}".replace(",", "\u202f") if pd.notna(v) else "N/D"


def _generate_recommendations(
    r: pd.Series,
    master: pd.DataFrame,
    data: dict,
) -> list[dict]:
    """Leviers d'action du département : catalogue déterministe (app/leviers.py).

    Chaque levier déclare ses conditions (requises / contributives), ses
    exclusions, son public et un gabarit de texte alimenté par les indicateurs
    observés ; la sélection garde les 4 leviers les mieux appariés, au plus 2
    par famille. `master` n'est plus utilisé directement (profils calculés
    une fois pour les 100 départements).
    """
    from ..leviers import profil, selectionner

    p = profil(str(r.get("dept", "")).zfill(2), data)
    return selectionner(p, n=4)


def _render_reco_card(reco: dict, r: pd.Series, data: dict) -> None:
    """Carte structurée : problème → indicateurs → action → pourquoi → public / secteurs / conditions."""
    impact = project_levier_impact(reco, r, data)
    esc = html.escape
    chips = "".join(f'<span class="reco-chip">{esc(str(v))}</span>' for v in reco.get("indicateurs", [])[:4])
    conds = reco.get("conditions") or []
    conds_html = "".join(
        f'<li>{"✓" if ok else "–"} {esc(lab)}</li>' for lab, ok in conds
    )
    disp = ", ".join(reco.get("dispositifs", []))
    secteurs = reco.get("secteurs") or ""
    st.html(
        '<div class="reco-card reco-card-neutral">'
        f'<div class="reco-famille">{esc(reco.get("famille", ""))} · {esc(reco.get("horizon", ""))}</div>'
        f'<div class="reco-title">{esc(reco["title"])}</div>'
        f'<div class="reco-prose"><strong>Constat.</strong> {esc(reco.get("probleme", ""))}</div>'
        f'<div class="reco-chips">{chips}</div>'
        f'<div class="reco-prose"><strong>Action.</strong> {esc(reco.get("action", ""))}</div>'
        f'<div class="reco-prose reco-pourquoi"><strong>Pourquoi ici.</strong> {esc(reco.get("pourquoi", ""))}</div>'
        + (f'<div class="reco-prose"><strong>Secteurs.</strong> {esc(secteurs)}</div>' if secteurs else "")
        + render_impact_html(impact)
        + '<details class="reco-details"><summary>Conditions, dispositifs et mise en œuvre</summary>'
        f'<ul class="reco-conds">{conds_html}</ul>'
        + (f'<div class="reco-prose"><strong>Dispositifs.</strong> {esc(disp)}</div>' if disp else "")
        + (f'<div class="reco-prose"><strong>Mise en œuvre.</strong> {esc(reco.get("mise_en_oeuvre", ""))}</div>'
           if reco.get("mise_en_oeuvre") else "")
        + f'<div class="reco-score">Score de correspondance {reco.get("score", 0):.2f}</div>'
        '</details>'
        '</div>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# 6. CONTEXTE : DÉMOGRAPHIE + PATHOLOGIES
# ──────────────────────────────────────────────────────────────────────────────

def render_contexte(r: pd.Series, data: dict) -> None:
    st.html(
        '<div class="section-header">'
        '<div class="section-eyebrow">CONTEXTE POPULATIONNEL</div>'
        '<h2 class="section-title">Qui sont les habitants, '
        '<em>et de quoi souffrent-ils\u00a0?</em></h2>'
        '</div>'
    )
    col1, col2 = st.columns(2, gap="large")
    with col1:
        _render_demographie(r, data["master"])
    with col2:
        _render_top_pathologies(r, data["patho"])


def _render_demographie(r: pd.Series, master: pd.DataFrame) -> None:
    st.html('<h4 class="subsection-title">Répartition démographique</h4>')

    age_cols = [
        ("pct_moins_25", "Moins de 25 ans"),
        ("pct_25_64", "25 à 64 ans"),
        ("pct_plus_65", f'65 ans et plus {info_tooltip("pct_65")}'),
    ]

    bars_html = '<div class="age-bars">'
    for col, _ in age_cols:
        dept_val = to_num(r.get(col))
        nat_val = float(master[col].median())
        if pd.isna(dept_val):
            continue
        # Normalise sur 60 % (valeur max théorique de pct_25_64)
        d_h = max(dept_val / 60 * 100, 4)
        n_h = max(nat_val / 60 * 100, 4)
        bars_html += (
            '<div class="age-bar-group">'
            f'<div class="age-bar dept" style="height:{d_h:.0f}%;">{dept_val:.0f}%</div>'
            f'<div class="age-bar nat"  style="height:{n_h:.0f}%;">{nat_val:.0f}%</div>'
            '</div>'
        )
    bars_html += '</div>'

    labels_html = '<div class="age-labels">'
    pop = to_num(r.get("population_num"))
    for col, lbl in age_cols:
        hab_str = _fmt_int(to_num(r.get(col)) / 100 * pop)
        labels_html += (
            f'<div>{lbl}'
            f'<span class="val">{hab_str}\u202fhab.</span>'
            '</div>'
        )
    labels_html += '</div>'

    legend = (
        '<div class="age-legend">'
        '<span><span class="swatch" style="background:#1A3D8F;"></span>Département</span>'
        '<span><span class="swatch" style="background:#9C9A92;"></span>Médiane nationale</span>'
        '</div>'
    )
    st.markdown(bars_html + labels_html + legend, unsafe_allow_html=True)


def _render_top_pathologies(r: pd.Series, patho: pd.DataFrame) -> None:
    st.markdown(
        f'<h4 class="subsection-title">Top 5 pathologies · prévalence {info_tooltip("patho")}</h4>',
        unsafe_allow_html=True,
    )

    if patho.empty or "_error" in patho.columns:
        st.info("Données pathologies non disponibles.")
        return

    dept_code = str(r["dept"]).zfill(2)
    dp = patho[patho["dept"] == dept_code].copy()
    dp = dp[~dp["patho_niv1"].isin(PATHOS_EXCLUDED)]

    if dp.empty:
        st.info("Aucune pathologie recensée pour ce département.")
        return

    dg = dp.groupby("patho_niv1")[["Ntop", "Npop"]].sum(min_count=1).reset_index()
    dg["prev"] = (dg["Ntop"] / dg["Npop"].where(dg["Npop"] > 0) * 100).round(2)
    top5 = dg.dropna(subset=["prev"]).sort_values("prev", ascending=False).head(5)
    max_prev = float(top5["prev"].max())
    # Prévalence standardisée sur l'âge (structure de référence : départements analysés)
    std = dept_prevalences_standardisees(patho)
    std_row = std.loc[dept_code] if not std.empty and dept_code in std.index else None
    couv = std.attrs.get("couverture")
    couv_row = couv.loc[dept_code] if couv is not None and dept_code in couv.index else None

    colors = ["#1A3D8F", "#3A5DA3", "#5A7DB7", "#7B9DCB", "#9BBDDF"]
    html = '<div class="patho-list">'
    for i, (_, row) in enumerate(top5.iterrows()):
        width = (float(row["prev"]) / max_prev * 100) if max_prev else 0
        ntop = int(row["Ntop"])
        ntop_str = f"{ntop:,}".replace(",", "\u202f")
        html += (
            '<div class="patho-item">'
            f'<div class="patho-name">{str(row["patho_niv1"])[:55]}</div>'
            f'<div class="patho-val">{row["prev"]:.2f}\u202f% brute'
            + (f' · {std_row[row["patho_niv1"]]:.2f}\u202f% stand. âge'
               + ("" if couv_row is None or couv_row.get(row["patho_niv1"], 1) >= 0.9
                  else f' <span style="color:#A51C30;">(couverture {couv_row.get(row["patho_niv1"], 0):.0%}, non comparable)</span>')
               if std_row is not None and pd.notna(std_row.get(row["patho_niv1"])) else "")
            + f'\u2002·\u2002{ntop_str}\u202fpat.</div>'
            '<div class="patho-bar">'
            f'<div class="patho-bar-fill" style="width:{width:.1f}%;background:{colors[i]};"></div>'
            '</div>'
            '</div>'
        )
    html += '</div>'
    html += (
        '<div style="font-size:11px;color:#9C9A92;margin-top:6px;line-height:1.5;">'
        'Brute = patients pris en charge / population CNAM du département (2023). '
        'Standardisée = taux par classe d\u2019âge appliqués à la structure par âge '
        'de l\u2019ensemble des départements du fichier CNAM\u202f: elle neutralise l\u2019effet du vieillissement '
        'Cellules sous secret statistique comptées à 0\u202f; si moins de 90\u202f% des poids '
        'd\u2019âge sont couverts, la valeur est signalée comme non comparable.'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# 6b. OFFRE MÉDICALE PAR SPÉCIALITÉ
# ──────────────────────────────────────────────────────────────────────────────

# ── Constantes offre médicale ─────────────────────────────────────────────────

# Mapping patho_niv1 (fragment) → spécialités RPPS concernées
PATHO_TO_SPEC = {
    "cardio": {
        "patho_fragment": "cardio",
        "label": "Maladies cardiovasculaires",
        "specialites": ["Cardiologue", "Médecin vasculaire"],
    },
    "diabete": {
        "patho_fragment": "iabète",
        "label": "Diabète",
        "specialites": ["Endocrinologue", "Diabétologue"],
    },
    "psychiatrique": {
        "patho_fragment": "sychiatr",
        "label": "Maladies psychiatriques",
        "specialites": ["Psychiatre", "Pédopsychiatre"],
    },
    "respiratoire": {
        "patho_fragment": "respiratoire",
        "label": "Maladies respiratoires chroniques",
        "specialites": ["Pneumologue"],
    },
    "cancers": {
        "patho_fragment": "ancers",
        "label": "Cancers",
        "specialites": ["Oncologue", "Cancérologue", "Chirurgien"],
    },
    "ophtalmologie": {
        "patho_fragment": "phtalmolog",
        "label": "Affections ophtalmologiques",
        "specialites": ["Ophtalmologue", "Ophtalmologiste"],
    },
    "rhumatologie": {
        "patho_fragment": "humatolog",
        "label": "Maladies rhumatologiques",
        "specialites": ["Rhumatologue"],
    },
    "neurologie": {
        "patho_fragment": "eurologiq",
        "label": "Maladies neurologiques",
        "specialites": ["Neurologue"],
    },
}

SPEC_PRIMAIRES = [
    "Médecin généraliste",
    "Infirmier",
    "Pharmacien",
    "Masseur-kinésithérapeute",
    "Chirurgien-dentiste",
]


def _build_patho_to_spec(pros_df: pd.DataFrame) -> dict:
    """Construit le mapping pathologie → libellés RPPS réels présents dans les données."""
    spec_col = (
        "specialite_libelle" if "specialite_libelle" in pros_df.columns
        else "specialite" if "specialite" in pros_df.columns
        else pros_df.columns[-1]
    )
    all_specs = pros_df[spec_col].dropna().unique().tolist()

    def find_specs(keywords: list[str]) -> list[str]:
        result = []
        for spec in all_specs:
            sl = spec.lower()
            if any(kw.lower() in sl for kw in keywords):
                result.append(spec)
        return result

    return {
        "prev_cardio": {
            "label":     "Maladies cardiovasculaires",
            "specialites": find_specs(["cardio", "cardiolog"]),
        },
        "prev_diabete": {
            "label":     "Diabète",
            "specialites": find_specs(["endocrin", "diab\u00e9to", "diabeto"]),
        },
        "prev_psychiatrique": {
            "label":     "Maladies psychiatriques",
            "specialites": find_specs(["psychiatr", "p\u00e9dopsychiatr"]),
        },
        "prev_respiratoire": {
            "label":     "Maladies respiratoires chroniques",
            "specialites": find_specs(["pneumo"]),
        },
        "prev_cancers": {
            "label":     "Cancers",
            "specialites": find_specs(["onco", "h\u00e9mato", "hemato", "canc\u00e9ro"]),
        },
        "prev_rhumatologie": {
            "label":     "Rhumatologie",
            "specialites": find_specs(["rhumato"]),
        },
        "prev_neurologie": {
            "label":     "Neurologie",
            "specialites": find_specs(["neurolo"]),
        },
        "prev_ophtalmologie": {
            "label":     "Ophtalmologie",
            "specialites": find_specs(["ophtalmo"]),
        },
    }


def render_offre_medicale(r: pd.Series, data: dict) -> None:
    # Jeu A (effectifs DREES/RPPS) si disponible ; sinon tableau historique
    # fondé sur le fichier équipe (présences, pas effectifs).
    if render_offre_medicale_drees(r, data):
        return

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">OFFRE MÉDICALE</div>'
        '<h2 class="section-title">'
        "Combien de <em>spécialistes,</em> et qu'en déduire\u00a0?</h2>"
        '<p class="section-lead">'
        'Top 5 soins primaires et top 5 spécialistes liés aux pathologies '
        'prédominantes du territoire. Comparés à la médiane nationale '
        'pour 100 000 habitants.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    dept_code  = str(r.get("dept", "")).zfill(2)
    population = to_num(r.get("population_num"))
    pros       = data.get("pros")

    if pros is None or pros.empty:
        st.info("Données professionnels non disponibles.")
        return
    if pd.isna(population) or population <= 0:
        st.info("Population non disponible : densités non calculables.")
        return

    # ── Agrégation RPPS pour ce département ──────────────────────────────
    pros_dept = pros[pros["dept"].astype(str) == dept_code].copy()

    agg = (
        pros_dept.groupby("specialite_libelle").size()
        .reset_index(name="nb")
        .rename(columns={"specialite_libelle": "specialite"})
    )
    agg["pour_100k"] = (agg["nb"] / population * 100_000).round(1)

    # Médiane nationale par spécialité : sur les départements analysés
    # (master, Mayotte exclue), en comptant 0 là où la spécialité est absente.
    master_pop = data["master"].set_index("dept")["population_num"].astype(float)
    counts = (
        pros[pros["dept"].astype(str).isin(master_pop.index)]
        .groupby(["specialite_libelle", "dept"]).size()
        .unstack("dept").reindex(columns=master_pop.index).fillna(0)
    )
    densites = counts.div(master_pop, axis=1) * 100_000
    nat_medians = (
        densites.median(axis=1).rename("mediane_nat").reset_index()
        .rename(columns={"specialite_libelle": "specialite"})
    )
    nat_med_map = nat_medians.set_index("specialite")["mediane_nat"].to_dict()
    agg = agg.merge(nat_medians, on="specialite", how="left")
    agg["mediane_nat"] = agg["mediane_nat"].fillna(0)
    agg["ecart_pct"]   = (
        (agg["pour_100k"] - agg["mediane_nat"]) /
        agg["mediane_nat"].replace(0, float("nan")) * 100
    ).round(0)

    # ── Top 5 pathologies via patho_niv1 → spécialistes RPPS ────────────
    # Règles : (fragment_patho_niv1, label_affiché, keywords_RPPS)
    _PATHO_RULES = [
        ("ardio",      "Maladies cardiovasculaires",        ["cardio", "cardiolog"]),
        ("iab\u00e8te","Diab\u00e8te",                      ["endocrin", "diab\u00e9to", "diabeto"]),
        ("sychiatr",   "Maladies psychiatriques",           ["psychiatr", "p\u00e9dopsychiatr"]),
        ("espira",     "Maladies respiratoires chroniques", ["pneumo"]),
        ("ancer",      "Cancers",                           ["onco", "h\u00e9mato", "hemato", "canc\u00e9ro"]),
        ("phtalmolog", "Affections ophtalmologiques",       ["ophtalmo"]),
        ("humatolog",  "Rhumatologie",                      ["rhumato"]),
        ("eurologiq",  "Neurologie",                        ["neurolo"]),
    ]

    # Libellés RPPS réels pour chaque famille de spécialistes
    _all_rpps = pros["specialite_libelle"].dropna().unique().tolist()

    def _find_rpps(keywords: list[str]) -> list[str]:
        return [s for s in _all_rpps if any(kw.lower() in s.lower() for kw in keywords)]

    # Calcule la prévalence locale et construit top5_pathos
    # [(patho_label, prev_pct, rpps_spec_list)]
    top5_pathos: list[tuple[str, float, list[str]]] = []

    patho_data = data.get("patho")
    if patho_data is not None and not patho_data.empty:
        dp = patho_data[
            patho_data["dept"].astype(str).str.zfill(2) == dept_code
        ].copy()
        if not dp.empty:
            dg = dp.groupby("patho_niv1")[["Ntop", "Npop"]].sum().reset_index()
            dg["prev"] = (
                dg["Ntop"] / dg["Npop"].replace(0, float("nan")) * 100
            )
            candidates = []
            for frag, label, kws in _PATHO_RULES:
                mask = dg["patho_niv1"].str.contains(
                    frag, case=False, na=False, regex=False
                )
                if mask.any():
                    prev = float(dg.loc[mask, "prev"].max())
                    if prev > 0:
                        candidates.append((label, prev, _find_rpps(kws)))
            top5_pathos = sorted(candidates, key=lambda x: x[1], reverse=True)[:5]

    # ── Fonction render d'une ligne ───────────────────────────────────────
    def render_row(spec_nom, nb, pour_100k, med_nat,
                   patho_label, patho_key, idx, is_absent=False):
        if med_nat > 0:
            ecart = (pour_100k - med_nat) / med_nat * 100
            ecart_color = (
                "#1B5E3F" if ecart >= 10
                else "#A51C30" if ecart <= -10
                else "#6B6B68"
            )
            ecart_str = f"+{int(ecart)} %" if ecart >= 0 else f"{int(ecart)} %"
        else:
            # Médiane nationale nulle : écart relatif non défini
            ecart, ecart_color, ecart_str = 0.0, "#9C9A92", "n.s."

        badge = ""
        if patho_label:
            badge = (
                f'<span style="font-size:10px;background:#FEF3F2;'
                f'color:#A51C30;border:1px solid #FECDCA;border-radius:3px;'
                f'padding:1px 6px;margin-left:8px;font-weight:600;">'
                f'{patho_label}</span>'
            )

        nb_display = (
            '<span style="color:#A51C30;font-weight:700;">0</span>'
            if is_absent else str(nb)
        )
        bg = "#FEF8F8" if (is_absent or ecart <= -10) and patho_label else (
            "white" if idx % 2 == 0 else "#FAFAF8"
        )

        return (
            f'<div style="display:grid;'
            f'grid-template-columns:3fr 0.6fr 0.8fr 0.8fr 0.7fr;'
            f'padding:12px 16px;background:{bg};'
            f'border-bottom:1px solid #E8E6DD;gap:0;align-items:center;">'
            f'<div style="font-size:13px;color:#0A1938;font-weight:500;'
            f'display:flex;align-items:center;flex-wrap:wrap;gap:4px;">'
            f'{spec_nom}{badge}</div>'
            f'<div style="font-size:13px;color:#2B2B2B;text-align:right;">{nb_display}</div>'
            f'<div style="font-size:13px;color:#2B2B2B;text-align:right;">{pour_100k:.1f}</div>'
            f'<div style="font-size:13px;color:#9C9A92;text-align:right;">{med_nat:.1f}</div>'
            f'<div style="font-size:13px;font-weight:600;color:{ecart_color};text-align:right;">'
            f'{ecart_str}</div>'
            f'</div>'
        )

    # ── En-tête tableau ───────────────────────────────────────────────────
    header = (
        '<div style="display:grid;'
        'grid-template-columns:3fr 0.6fr 0.8fr 0.8fr 0.7fr;'
        'padding:10px 16px;background:#0A1938;border-radius:6px 6px 0 0;gap:0;">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);">SP\u00c9CIALIT\u00c9</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">NB</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">/100K</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">M\u00c9D.NAT.</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">\u00c9CART</div>'
        '</div>'
    )

    def section_sep(label):
        return (
            f'<div style="padding:8px 16px;background:#F3F2EC;'
            f'font-size:10px;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:#6B6B68;'
            f'border-bottom:1px solid #E8E6DD;">{label}</div>'
        )

    SOINS_PRIMAIRES = [
        "M\u00e9decin g\u00e9n\u00e9raliste",
        "Infirmier",
        "Pharmacien",
        "Masseur-kin\u00e9sith\u00e9rapeute",
        "Chirurgien-dentiste",
    ]

    table_html = (
        '<div class="sa-tbl-scroll">'
        '<div style="min-width:520px;border:1px solid #E8E6DD;'
        'border-radius:6px;overflow:hidden;">'
        f'{header}'
    )

    # ── TOP 5 SOINS PRIMAIRES ─────────────────────────────────────────────
    table_html += section_sep("TOP 5 \u00b7 SOINS PRIMAIRES")

    for i, spec_exact in enumerate(SOINS_PRIMAIRES):
        match = agg[agg["specialite"].str.lower() == spec_exact.lower()]
        if not match.empty:
            row_s = match.iloc[0]
            table_html += render_row(
                spec_nom=row_s["specialite"], nb=int(row_s["nb"]),
                pour_100k=float(row_s["pour_100k"]),
                med_nat=float(row_s["mediane_nat"]),
                patho_label=None, patho_key=None, idx=i,
            )
        else:
            table_html += render_row(
                spec_nom=spec_exact, nb=0, pour_100k=0.0,
                med_nat=float(nat_med_map.get(spec_exact, 0.0)),
                patho_label=None, patho_key=None, idx=i, is_absent=True,
            )

    # ── TOP 5 SPÉCIALISTES LIÉS AUX PATHOLOGIES ──────────────────────────
    table_html += section_sep(
        "TOP 5 \u00b7 SP\u00c9CIALISTES LI\u00c9S AUX PATHOLOGIES PR\u00c9DOMINANTES"
    )

    spec_count = 0
    for patho_label, prev_val, spec_list in top5_pathos:
        if spec_count >= 5:
            break

        # Fallback si aucun libellé RPPS trouvé pour cette famille
        if not spec_list:
            table_html += render_row(
                spec_nom="Sp\u00e9cialiste",
                nb=0, pour_100k=0.0, med_nat=0.0,
                patho_label=patho_label, patho_key=None,
                idx=spec_count, is_absent=True,
            )
            spec_count += 1
            continue

        # Premier libellé exact trouvé dans le RPPS
        spec_exact = spec_list[0]
        match = agg[agg["specialite"] == spec_exact]
        if not match.empty:
            row_s = match.iloc[0]
            table_html += render_row(
                spec_nom=row_s["specialite"], nb=int(row_s["nb"]),
                pour_100k=float(row_s["pour_100k"]),
                med_nat=float(row_s["mediane_nat"]),
                patho_label=patho_label, patho_key=None, idx=spec_count,
            )
        else:
            table_html += render_row(
                spec_nom=spec_exact, nb=0, pour_100k=0.0,
                med_nat=float(nat_med_map.get(spec_exact, 0.0)),
                patho_label=patho_label, patho_key=None,
                idx=spec_count, is_absent=True,
            )
        spec_count += 1

    table_html += "</div></div>"  # ferme inner div + sa-tbl-scroll
    st.markdown(table_html, unsafe_allow_html=True)

    # Note méthodologique
    st.markdown(
        '<div style="margin-top:10px;padding:12px 16px;background:#F3F2EC;'
        'border-radius:4px;font-size:12px;color:#6B6B68;line-height:1.6;">'
        '<strong style="color:#2B2B2B;">Lecture.</strong> Comptages issus du fichier '
        'des professionnels de sant\u00e9 retrait\u00e9 par l\u2019\u00e9quipe '
        '(lignes = lieux d\u2019exercice recens\u00e9s\u202f; un praticien peut '
        'appara\u00eetre plusieurs fois). M\u00e9diane nationale = m\u00e9diane des '
        'densit\u00e9s des d\u00e9partements analys\u00e9s, z\u00e9ros inclus. '
        'Aucun besoin chiffr\u00e9 n\u2019est affich\u00e9\u202f: l\u2019\u00e9cart '
        '\u00e0 la m\u00e9diane n\u2019est pas un nombre de m\u00e9decins manquants. '
        'L\u2019APL reste l\u2019indicateur de r\u00e9f\u00e9rence pour l\u2019acc\u00e8s '
        'aux g\u00e9n\u00e9ralistes.'
        '</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 7. DÉLAI RDV SPÉCIALISTES
# ──────────────────────────────────────────────────────────────────────────────

def render_delais_rdv(r: pd.Series, data: dict) -> None:
    """Délais d'accès aux spécialistes — proxy calculé via APL départemental.

    Méthode : délai national DREES 2016-2017 × (APL nationale / APL département).
    Les zones à faible APL ont des délais estimés plus longs, conformément
    à la corrélation documentée par la DREES dans son enquête.
    """
    from ..components.delais import (
        compute_delais_proxy, is_desert_medical, APL_SEUIL_DESERT
    )

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ACCÈS AUX SPÉCIALISTES</div>'
        f'<h2 class="section-title">Estimation des délais {info_tooltip("delais_rdv")} '
        "<em>d'accès aux soins.</em></h2>"
        '</div>',
        unsafe_allow_html=True,
    )

    apl = r.get("apl_dept")
    dept_code = str(r.get("dept", "")).zfill(2)

    # ── Bandeau si désert médical ──────────────────────────────────────────
    if pd.notna(apl) and is_desert_medical(float(apl)):
        st.markdown(
            f'<div style="background:#FEE9E9;border:1px solid #A51C30;'
            f'border-radius:4px;padding:14px 18px;margin:0 0 24px;'
            f'font-size:14px;color:#5E0000;">'
            f'<strong>APL sous le repère de sous-densité.</strong> APL médian des '
            f'communes de {apl:.1f}\u202f/hab., inférieur à {APL_SEUIL_DESERT} '
            f'consultations/an/habitant.'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Calcul du proxy ────────────────────────────────────────────────────
    # Référence nationale = médiane des valeurs départementales (même méthode que apl_dept)
    APL_NATIONALE = float(pd.to_numeric(data["master"]["apl_dept"], errors="coerce").median())

    if pd.isna(apl):
        st.info("APL non disponible pour ce département : délais non calculables.")
        return

    delais = compute_delais_proxy(dept_code, float(apl), APL_NATIONALE)

    if delais.empty:
        st.info("Données de délais non disponibles.")
        return

    # ── Affichage en grille 3 colonnes ─────────────────────────────────────
    delais = delais.sort_values("delai_estime_jours")
    # Modèle v2 (expérimental) : facteur propre à chaque spécialité (densité DREES)
    from ..components.delais import compute_delais_v2
    try:
        v2 = compute_delais_v2(dept_code, data).set_index("specialite")
    except Exception:
        v2 = pd.DataFrame()

    cols = st.columns(3)
    for i, (_, row) in enumerate(delais.iterrows()):
        est = int(row["delai_estime_jours"])
        interp = row["interpretation"]
        v2_txt = ""
        if not v2.empty and row["specialite"] in v2.index and pd.notna(v2.loc[row["specialite"], "delai_estime_v2_jours"]):
            v2_txt = (f'<div class="comp neutral" style="font-size:11px;">v2 (densité de la spécialité)\u202f: '
                      f'{int(v2.loc[row["specialite"], "delai_estime_v2_jours"])} j · facteur '
                      f'{v2.loc[row["specialite"], "facteur_v2"]:.2f}</div>')

        if est <= 7:
            color_class = "fav"
        elif est <= 30:
            color_class = "inter"
        else:
            color_class = "crit"

        if "+" in interp:
            interp_class = "crit"
        elif "conforme" in interp:
            interp_class = "neutral"
        else:
            interp_class = "fav"

        with cols[i % 3]:
            st.markdown(
                f'<div class="delai-card">'
                f'<div class="spec">{row["specialite"]}</div>'
                f'<div class="dur {color_class}">{est}'
                f'<span class="unit">jours</span></div>'
                f'<div class="comp {interp_class}">{interp}</div>'
                f'{v2_txt}'
                f'</div>',
                unsafe_allow_html=True,
            )
    st.markdown(
        '<div style="font-size:11px;color:#9C9A92;margin-top:6px;line-height:1.5;">Deux modèles sont '
        'affichés pour comparaison\u202f: v1 = médiane nationale DREES × (APL de référence / APL du '
        'département) pour toutes les spécialités\u202f; v2 (expérimental) = la même base modulée, pour '
        'chaque spécialité, par le rapport entre la densité médiane des départements et la densité DREES '
        '2026 du département (généraliste\u202f: APL\u202f; rhumatologue\u202f: repli v1). Facteurs bornés '
        '[0,7\u202f; 3]. Aucun des deux n\u2019est validé par des délais observés localement.</div>',
        unsafe_allow_html=True,
    )

    # ── Note méthodologique ────────────────────────────────────────────────
    dept_name = r.get("Nom du département", "")
    direction = "inférieur" if float(apl) < APL_NATIONALE else "supérieur"
    consequence = "plus longs" if float(apl) < APL_NATIONALE else "plus courts"
    st.markdown(
        f'<div style="margin-top:20px;padding:14px 18px;background:#F3F2EC;'
        f'border-radius:4px;font-size:12px;color:#6B6B68;line-height:1.6;">'
        f'<strong style="color:#2B2B2B;">Comment sont calculées ces estimations ?</strong><br>'
        f'Base\u202f: enquête nationale DREES 2016-2017 (40\u202f000 personnes, France entière). '
        f'Ajustement\u202f: délai national × (APL nationale {APL_NATIONALE} / '
        f'APL {dept_name} {apl:.1f}). '
        f"L'APL de ce département est "
        f'<strong>{direction}</strong> à la médiane nationale, '
        f'ce qui suggère des délais <strong>{consequence}</strong> qu\'en moyenne.'
        f'<br><br>'
        f'Ces valeurs sont des <strong>estimations indicatives</strong>, non des mesures '
        f'directes. Source nationale\u202f: DREES, Études et Résultats n°1085, octobre 2018. '
        f'Données départementales directes non disponibles en open data à ce jour.'
        f'</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 8. COMPARER AVEC
# ──────────────────────────────────────────────────────────────────────────────

def _dept_distance_km(dept_a: str, dept_b: str) -> float:
    """Distance approximative entre centres départementaux."""
    from math import atan2, cos, radians, sin, sqrt

    a = DEPT_CENTER.get(str(dept_a).zfill(2))
    b = DEPT_CENTER.get(str(dept_b).zfill(2))
    if not a or not b:
        return 9999.0
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    x = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(x), sqrt(1 - x))


def find_similar_depts(
    r: pd.Series,
    master: pd.DataFrame,
    n: int = 3,
) -> list[dict]:
    """Suggère des départements proches, en priorité en zone favorable (contraste)."""
    dept_code = str(r.get("dept", "")).zfill(2)
    zone = str(r.get("zone_short", ""))
    score = to_num(r.get("score_global"))
    region = str(r.get("Code région", ""))
    is_dom = dept_code in {"971", "972", "973", "974", "976"}
    dom_codes = {"971", "972", "973", "974", "976"}

    candidates = master[master["dept"] != dept_code].copy()
    if not is_dom:
        candidates = candidates[~candidates["dept"].isin(dom_codes)]

    if candidates.empty:
        return []

    favorable = candidates[candidates["zone_short"] == "Favorable"]
    if not favorable.empty:
        pool = favorable
    elif zone == "Critique":
        pool = candidates[candidates["zone_short"] != "Critique"]
    else:
        pool = candidates

    if pool.empty:
        pool = candidates

    def _rank(row: pd.Series) -> float:
        other = str(row.get("dept", "")).zfill(2)
        dist_km = _dept_distance_km(dept_code, other)
        dist_score = min(dist_km / 400.0, 1.0)
        row_zone = str(row.get("zone_short", ""))
        row_score = to_num(row.get("score_global"))
        zone_bonus = 0.0
        if row_zone == "Favorable":
            zone_bonus = -0.35
        elif zone != row_zone:
            zone_bonus = -0.12
        contrast = (
            min(abs(row_score - score) / 60.0, 1.0)
            if pd.notna(row_score) and pd.notna(score) else 0.0
        )
        region_bonus = -0.18 if str(row.get("Code région", "")) == region else 0.0
        return 0.55 * dist_score + zone_bonus + region_bonus - 0.18 * contrast

    pool = pool.copy()
    pool["_rank"] = pool.apply(_rank, axis=1)
    top = pool.nsmallest(n, "_rank")

    results = []
    for _, row in top.iterrows():
        same_region = str(row.get("Code région", "")) == region
        row_zone = str(row.get("zone_short", ""))
        # « Proche » seulement si la distance le justifie (≤ 250 km entre centres)
        is_near = _dept_distance_km(dept_code, str(row.get("dept", "")).zfill(2)) <= 250
        lieu = "Même région" if same_region else (
            "Proche géographiquement" if is_near else "Autre région"
        )
        if row_zone == "Favorable":
            raison = f"Zone favorable · {lieu}"
        else:
            raison = f"{lieu} · Profil contrasté"
        results.append({
            "dept": row["dept"],
            "nom": row.get("Nom du département", ""),
            "score": row.get("score_global"),
            "zone": row_zone,
            "raison": raison,
        })
    return results


def render_suggestions_comparaison(r: pd.Series, master: pd.DataFrame) -> None:
    st.html(
        '<div class="section-header">'
        '<div class="section-eyebrow">TERRITOIRES SIMILAIRES</div>'
        '<h2 class="section-title">Comparer avec…</h2>'
        '</div>'
    )

    suggestions = find_similar_depts(r, master, n=3)

    if not suggestions:
        st.info("Aucune suggestion disponible.")
        return

    base_dept = str(r["dept"]).zfill(2)
    cols = st.columns(min(3, len(suggestions)))
    for i, sim in enumerate(suggestions[:3]):
        with cols[i]:
            score_val = sim["score"]
            score_str = f"{score_val:.0f}/100" if pd.notna(score_val) else "N/D"
            zone_sug = str(sim["zone"])
            badge_cls = {"Critique": "crit", "Intermédiaire": "inter",
                         "Favorable": "fav"}.get(zone_sug, "")
            sim_dept = str(sim["dept"]).zfill(2)
            fiche_href = internal_href("dept", dept_code=sim_dept)
            st.html(
                f'<a href="{fiche_href}" target="_self" class="suggestion-card suggestion-card-link">'
                f'<div class="suggestion-label">{sim["raison"]}</div>'
                f'<div class="suggestion-name">{sim["nom"]}</div>'
                f'<div class="suggestion-score">{score_str}'
                f'<span class="fiche-zone-badge {badge_cls}" '
                f'style="font-size:11px;padding:4px 10px;">'
                f'{zone_sug}</span>'
                '</div>'
                '</a>'
            )
            if st.button(
                "Voir la comparaison",
                key=f"suggest_{base_dept}_{sim_dept}",
                use_container_width=True,
            ):
                navigate_compare(base_dept, sim_dept)
