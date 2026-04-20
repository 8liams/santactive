"""Fiche département : la page-rapport d'un territoire."""

from __future__ import annotations

import unicodedata

import pandas as pd
import streamlit as st

from ..components import render_alert, zone_badge_html
from ..components.tooltip import info_tooltip
from ..config import CMAP, PALETTE, PATHOS_EXCLUDED
from ..pdf_export import generate_department_pdf
from ..router import navigate


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
    render_diagnostic(r, master)
    render_recommandations(r, master, data)
    render_scorecard(r, master)
    render_carte_communale(r, data)
    render_contexte(r, data)
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

    st.html(
        '<div class="fiche-topbar">'
        '<div class="breadcrumb">'
        '<a href="?view=home">Accueil</a>'
        '<span class="sep">›</span>'
        f'<a href="?view=region&region_code={region_code}">{region_name}</a>'
        '<span class="sep">›</span>'
        f'<span class="current">{dept_name}</span>'
        '</div>'
        '</div>'
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Comparer avec…", use_container_width=True):
            st.session_state["compare_base"] = r["dept"]
            navigate("comparer")
    with col2:
        if st.button("Partager ce lien", use_container_width=True):
            st.info(f"?view=dept&dept_code={r['dept']}")
    with col3:
        with st.spinner("Génération…"):
            try:
                recos = _generate_recommendations(r, data["master"], data)
                pdf_bytes = generate_department_pdf(r, data["master"], recos, data)
                dept_slug = str(r.get("Nom du département", "rapport")).lower().replace(" ", "_")
                st.download_button(
                    label="Rapport PDF",
                    data=pdf_bytes,
                    file_name=f"santactive_{dept_slug}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                )
            except Exception as _pdf_err:
                st.error(f"Erreur PDF : {_pdf_err}")


# ──────────────────────────────────────────────────────────────────────────────
# 1. HEADER
# ──────────────────────────────────────────────────────────────────────────────

def render_header(r: pd.Series, master: pd.DataFrame) -> None:
    score = r.get("score_global")
    zone = str(r.get("zone_short", "—"))

    # Rang national
    ranked = (
        master.dropna(subset=["score_global"])
        .sort_values("score_global")
        .reset_index(drop=True)
    )
    rang_idx = ranked.index[ranked["dept"] == r["dept"]].tolist()
    rang_num = rang_idx[0] + 1 if rang_idx else "—"
    nb_total = len(ranked)

    pop = r.get("population_num", 0)
    pop_str = f"{int(pop):,}\u202fhab.".replace(",", "\u202f") if pd.notna(pop) and pop else "—"

    typologie_labels = {
        "urbain_dense": "Urbain dense",
        "urbain":       "Urbain",
        "peri_urbain":  "Péri-urbain",
        "rural":        "Rural",
        "inconnu":      "—",
    }
    typologie_str = typologie_labels.get(str(r.get("typologie", "inconnu")), "—")

    badge_class = {"Critique": "crit", "Intermédiaire": "inter", "Favorable": "fav"}.get(zone, "")
    score_str = f"{float(score):.1f}" if pd.notna(score) else "N/D"
    rang_str  = str(int(rang_num)) if isinstance(rang_num, (int, float)) and pd.notna(rang_num) else "N/D"

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
        '<div class="fiche-meta">'
        '<div class="fiche-meta-item">'
        f'<span class="label">SCORE GLOBAL {info_tooltip("score_global")}</span>'
        f'<span class="value">{score_str}<span class="small">/100</span></span>'
        '</div>'
        '<div class="fiche-meta-item">'
        f'<span class="label">RANG NATIONAL {info_tooltip("rang_national")}</span>'
        f'<span class="value">{rang_str}<span class="small">/{nb_total}</span></span>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. DIAGNOSTIC
# ──────────────────────────────────────────────────────────────────────────────

def _get_situation_label(r: pd.Series) -> tuple[str, str]:
    """Retourne (label_css, label_texte) selon les indicateurs réels.

    Priorité :
    1. APL < 1.5 → critique quelle que soit la zone
    2. APL < 2.5 → préoccupante quelle que soit la zone
    3. Zone calculée si APL disponible et >= 2.5
    4. Score global si APL indisponible
    5. Fallback neutre si rien de disponible
    """
    apl   = r.get("apl_median_dept")
    zone  = str(r.get("zone_short", "")).strip()
    score = r.get("score_global")

    if pd.notna(apl):
        apl_val = float(apl)
        if apl_val < 1.5:
            return ("crit", "critique")
        elif apl_val < 2.5:
            return ("crit", "préoccupante")
        elif apl_val < 3.5:
            return ("inter", "intermédiaire")
        else:
            return ("fav", "favorable")

    if zone == "Critique":
        return ("crit", "préoccupante")
    elif zone == "Favorable":
        return ("fav", "favorable")
    elif zone == "Intermédiaire":
        return ("inter", "intermédiaire")

    if pd.notna(score):
        score_val = float(score)
        if score_val < 33:
            return ("crit", "préoccupante")
        elif score_val < 67:
            return ("inter", "intermédiaire")
        else:
            return ("fav", "favorable")

    return ("inter", "indéterminée")


def _get_sous_effectif(r: pd.Series) -> str | None:
    """Retourne la phrase sur le sous-effectif ou None."""
    apl     = r.get("apl_median_dept")
    apl_nat = 2.9

    if pd.notna(apl):
        delta_pct = (float(apl) - apl_nat) / apl_nat * 100
        if delta_pct < -5:
            return f"un sous-effectif médical de {abs(delta_pct):.0f}\u202f% sous la médiane nationale"
        elif delta_pct > 5:
            return f"un sur-effectif médical de {delta_pct:.0f}\u202f% au-dessus de la médiane nationale"

    return None


def render_diagnostic(r: pd.Series, master: pd.DataFrame) -> None:
    """Phrase éditoriale + APL en chiffre géant (vraies données DREES)."""
    dept_nom = str(r.get("Nom du département", "Ce département"))
    css_class, label_texte = _get_situation_label(r)
    sous_effectif = _get_sous_effectif(r)
    nb_communes_critiques = int(r.get("nb_communes_critiques", 0) or 0)

    if sous_effectif:
        complement = f"<em class='{css_class}'>{label_texte}</em> et {sous_effectif}"
    else:
        complement = f"<em class='{css_class}'>{label_texte}</em>"

    if nb_communes_critiques > 0:
        commune_label = "commune" if nb_communes_critiques == 1 else "communes"
        complement += f" et {nb_communes_critiques} {commune_label} en zone blanche"

    complement += "."

    phrase = f"{dept_nom} présente une situation {complement}"

    # APL DREES (réel si disponible, sinon absent)
    apl = r.get("apl_median_dept")
    apl_nat = (
        master["apl_median_dept"].median()
        if "apl_median_dept" in master.columns
        else None
    )

    col1, col2 = st.columns([1.4, 1], gap="large")
    with col1:
        st.markdown(
            f'<div class="diagnostic-prose">{phrase}</div>',
            unsafe_allow_html=True,
        )
    with col2:
        if pd.notna(apl) and apl_nat is not None and pd.notna(apl_nat):
            from ..components.delais import APL_SEUIL_DESERT
            delta_apl = (apl - apl_nat) / apl_nat * 100
            delta_str = f"{delta_apl:+.0f} %"

            if apl < 2.5:
                color = "crit"
                verdict = "désert médical"
                verdict_detail = f"en dessous du seuil officiel DREES ({APL_SEUIL_DESERT})"
            elif apl < apl_nat * 0.9:
                color = "inter"
                verdict = "sous la médiane nationale"
                verdict_detail = f"médiane nationale\u202f: {apl_nat:.1f}"
            else:
                color = "fav"
                verdict = "au-dessus de la médiane nationale"
                verdict_detail = f"médiane nationale\u202f: {apl_nat:.1f}"

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
                f'Seuil désert médical DREES : &lt; 2.5'
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
                '<div class="diagnostic-kpi-value" style="color:#9C9A92;">—</div>'
                '<div class="diagnostic-kpi-context">'
                '<span>Donnée ANCT non disponible pour ce département</span>'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# 3. SCORECARD
# ──────────────────────────────────────────────────────────────────────────────

def render_scorecard(r: pd.Series, master: pd.DataFrame) -> None:

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">SCORECARD</div>'
        '<h2 class="section-title">'
        'Où ce département <em>décroche,</em> et où il tient bon.</h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Scores ────────────────────────────────────────────────────────────
    def _s(key: str, default: float = 50.0) -> float:
        v = r.get(key)
        try:
            fv = float(v)
            return fv if pd.notna(fv) else default
        except (TypeError, ValueError):
            return default

    score_acces  = _s("score_acces")
    score_pros   = _s("score_pros")
    score_etabs  = _s("score_etabs")
    score_apl    = _s("score_apl")
    score_temps  = _s("score_temps")
    score_med    = _s("score_medecins")
    score_senior = _s("score_seniors")
    score_fonc   = _s("score_foncier")

    val_acces  = float(r.get("apl_median_dept",      0) or 0)
    val_pros   = float(r.get("med_gen_pour_100k",    0) or 0)
    val_etabs  = float(r.get("structures_pour_100k", 0) or 0)
    val_apl    = float(r.get("apl_median_dept",      0) or 0)
    val_temps  = float(r.get("temps_acces_median",   0) or 0)
    val_65     = float(r.get("pct_plus_65",          0) or 0)
    val_prix   = float(r.get("prix_m2_moyen",        0) or 0)

    def _render_bar(label, sublabel, score, raw_val, unit,
                    tooltip_key=None, indent=False):
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
            if raw_val else ""
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

    # ── 3 barres principales + sous-dimensions ────────────────────────────
    _render_bar("Accès aux soins", "APL + temps de trajet médian",
                score_acces, val_acces, "/hab.", tooltip_key="apl")
    _render_bar("Accessibilité APL", "Consultations disponibles / hab.",
                score_apl, val_apl, "/hab.", indent=True)
    _render_bar("Accessibilité physique", "Temps trajet établissement",
                score_temps, val_temps, "min", indent=True)

    _render_bar("Professionnels de santé", "RPPS, hors remplaçants",
                score_pros, val_pros, "/100k", tooltip_key="med_100k")
    _render_bar("Médecins généralistes /100k", "Densité RPPS janv. 2026",
                score_med, val_pros, "/100k", indent=True)

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
    from ..components import render_commune_choropleth
    from ..components.maps import _fetch_communes_geojson

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ZOOM TERRITORIAL</div>'
        '<h2 class="section-title">La carte des communes.</h2>'
        '<p class="section-lead">Survolez une commune pour voir les détails. '
        'Les points rouges signalent les établissements de santé.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    dept_code = str(r["dept"]).zfill(2)

    # Cas particulier : département mono-communal (Paris)
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

    # ── Choix de l'indicateur — pills ────────────────────────────────────────
    indicator_map = {
        "Prix médian /m²": ("prix",  "€/m²",  "prix"),
        "Temps d'accès":   ("temps", "min",   "temps"),
    }
    try:
        layer = st.pills(
            "Indicateur carte",
            options=list(indicator_map.keys()),
            default="Prix médian /m²",
            key=f"layer_{dept_code}",
            label_visibility="collapsed",
        )
    except AttributeError:
        layer = st.radio(
            "Indicateur carte",
            options=list(indicator_map.keys()),
            horizontal=True,
            key=f"layer_{dept_code}",
            label_visibility="collapsed",
        )
    if layer is None:
        layer = "Prix médian /m²"
    value_key, unit, colormap = indicator_map[layer]

    # ── Récupération du GeoJSON communes pour le mapping nom → code INSEE ─────
    communes_gj = _fetch_communes_geojson(dept_code)
    if communes_gj is None:
        st.warning("Découpage communal indisponible (API geo.api.gouv.fr).")
        return

    def _norm_aggressive(s: str) -> str:
        """Normalisation robuste : accents, casse, tirets, Saint/St."""
        import unicodedata as _ud
        if not isinstance(s, str):
            return ""
        s = _ud.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
        for ch in "-'.,()":
            s = s.replace(ch, " ")
        s = " ".join(s.split())
        s = s.replace("SAINTE ", "STE ").replace("SAINT ", "ST ")
        return s

    name_to_code = {}
    for feat in communes_gj.get("features", []):
        nom  = feat["properties"].get("nom", "")
        code = feat["properties"].get("code", "")
        if nom and code:
            name_to_code[_norm_aggressive(nom)] = code

    # ── Données selon l'indicateur ────────────────────────────────────────────
    if value_key == "prix":
        immo: pd.DataFrame = data["immo"]
        df_f = immo[immo["code_departement"].astype(str).str.zfill(2) == dept_code]
        if df_f.empty:
            st.info("Données immobilières non disponibles pour ce département.")
            return
        comm_data = df_f.groupby("commune")["prix_m2"].median().reset_index()
        comm_data.columns = ["commune", "value"]
    else:
        temps: pd.DataFrame = data["temps"]
        df_f = temps[temps["code_departement"].astype(str).str.zfill(2) == dept_code]
        if df_f.empty:
            st.info("Données temps d'accès non disponibles pour ce département.")
            return
        comm_data = df_f.groupby("commune")["temps_acces"].mean().reset_index()
        comm_data.columns = ["commune", "value"]

    total_before = len(comm_data)
    comm_data["code_commune"] = comm_data["commune"].apply(
        lambda c: name_to_code.get(_norm_aggressive(c))
    )
    matched = comm_data["code_commune"].notna().sum()
    comm_data = comm_data.dropna(subset=["code_commune", "value"])

    if comm_data.empty:
        st.warning(
            f"Impossible de matcher les communes avec le référentiel INSEE "
            f"(0 sur {total_before} communes reconnues). "
            "Les noms dans les données diffèrent trop du référentiel officiel."
        )
        return

    # ── Overlay établissements (si lat/lon disponibles) ───────────────────────
    etabs: pd.DataFrame = data["etabs"]
    etabs_f = etabs[etabs["code_departement"].astype(str).str.zfill(2) == dept_code]
    etabs_overlay = None
    if "latitude" in etabs_f.columns and "longitude" in etabs_f.columns:
        etabs_overlay = etabs_f[["latitude", "longitude", "Rslongue"]].copy()
        etabs_overlay.columns = ["lat", "lon", "nom"]
        etabs_overlay = etabs_overlay.dropna(subset=["lat", "lon"]).head(50)

    # ── Rendu Folium ──────────────────────────────────────────────────────────
    render_commune_choropleth(
        dept_code=dept_code,
        data_by_commune=comm_data,
        value_col="value",
        metric_label=layer,
        unit=unit,
        colormap_name=colormap,
        etabs_overlay=etabs_overlay,
        height=540,
        key=f"commune_map_{dept_code}_{value_key}",
    )

    st.caption(
        f"{matched} communes matchées sur {total_before} "
        "(nom ↔ code INSEE officiel) · survolez pour afficher le détail."
    )


# ──────────────────────────────────────────────────────────────────────────────
# 5. PLAN D'ACTION
# ──────────────────────────────────────────────────────────────────────────────

def render_recommandations(r: pd.Series, master: pd.DataFrame, data: dict) -> None:
    recos = _generate_recommendations(r, master, data)
    nb = len(recos)

    if nb == 0:
        return

    _titres = {1: "Un levier", 2: "Deux leviers", 3: "Trois leviers", 4: "Quatre leviers"}
    titre   = _titres.get(nb, f"{nb} leviers")
    suffixe = "prioritaire" if nb == 1 else "prioritaires"

    st.html(
        '<div class="section-header">'
        '<div class="section-eyebrow">PLAN D\'ACTION</div>'
        f'<h2 class="section-title">{titre} <em>{suffixe}</em>.</h2>'
        '<p class="section-lead">Recommandations générées à partir du croisement '
        'des indicateurs. Chiffrées, localisées, hiérarchisées.</p>'
        '</div>'
    )

    if nb == 1:
        _render_reco_card(recos[0], index=1)
    else:
        for i in range(0, nb, 2):
            c1, c2 = st.columns(2, gap="large")
            for j, col in enumerate([c1, c2]):
                if i + j >= nb:
                    break
                with col:
                    _render_reco_card(recos[i + j], index=i + j + 1)


def _generate_recommendations(
    r: pd.Series,
    master: pd.DataFrame,
    data: dict,
) -> list[dict]:
    """Génère des recommandations basées sur les indicateurs réels.

    Couvre 12 cas distincts :
    1.  Désert médical rural → Maison de santé
    2.  Désert médical urbain → Télémédecine + consultations avancées
    3.  Déficit généralistes → Recrutement ciblé
    4.  Population vieillissante + accès dégradé → Télémédecine seniors
    5.  Établissements insuffisants → Antennes hospitalières
    6.  Temps d'accès élevé → Transport sanitaire / navettes santé
    7.  Fort taux pathologies chroniques → Prévention + dépistage
    8.  Jeunesse élevée + pédiatres insuffisants → Renforcer pédiatrie
    9.  Foncier accessible + désert → Attirer médecins via logement
    10. Déficit spécialistes RPPS → Consultations avancées IPA
    11. Situation intermédiaire → Plan de vigilance structuré
    12. Situation favorable → Maintien + veille
    """
    recos: list[dict] = []

    # ── Extraction des indicateurs ────────────────────────────────────────
    score_acces    = float(r.get("score_acces", 50) or 50)
    score_pros     = float(r.get("score_pros", 50) or 50)
    score_etabs    = float(r.get("score_etabs", 50) or 50)
    score_global   = float(r.get("score_global", 50) or 50)
    apl            = float(r.get("apl_median_dept", 3.0) or 3.0)
    pct_65         = float(r.get("pct_plus_65", 20) or 20)
    pct_moins_25   = float(r.get("pct_moins_25", 28) or 28)
    prix_m2        = float(r.get("prix_m2_moyen", 2000) or 2000)
    temps          = float(r.get("temps_acces_median", 10) or 10)
    densite        = float(r.get("densite", 50) or 50)
    med_100k       = float(r.get("med_gen_pour_100k", 100) or 100)
    etabs_100k     = float(r.get("structures_pour_100k", 5) or 5)
    population     = float(r.get("population_num", 300000) or 300000)
    dept_nom       = str(r.get("Nom du département", "Ce département"))
    dept_nom_court = dept_nom.replace("Le ", "").replace("La ", "").replace("Les ", "")

    # ── Médianes nationales ───────────────────────────────────────────────
    med_med_nat    = float(master["med_gen_pour_100k"].median())
    etabs_med_nat  = float(master["structures_pour_100k"].median())
    temps_med_nat  = float(master["temps_acces_median"].median())
    apl_nationale  = 2.9

    # ── Flags ─────────────────────────────────────────────────────────────
    if densite > 500:
        typo = "urbain_dense"
    elif densite > 150:
        typo = "urbain"
    elif densite > 40:
        typo = "peri_urbain"
    else:
        typo = "rural"

    is_rural           = typo in ("rural", "peri_urbain")
    is_urbain          = typo in ("urbain", "urbain_dense")

    is_desert          = apl < 2.5
    is_tres_desert     = apl < 1.5
    acces_critique     = score_acces < 33
    acces_degrade      = score_acces < 45
    pros_critique      = score_pros < 33
    pros_degrade       = score_pros < 45
    etabs_critique     = score_etabs < 33
    etabs_degrade      = score_etabs < 45
    temps_eleve        = temps > temps_med_nat * 1.4
    pop_vieillissante  = pct_65 > 22
    pop_tres_vieille   = pct_65 > 27
    pop_jeune          = pct_moins_25 > 32
    foncier_accessible = prix_m2 < 1500
    foncier_moyen      = prix_m2 < 2500
    deficit_med        = med_100k < med_med_nat * 0.85

    # Pathologies (si disponibles)
    patho_data = data.get("patho")
    taux_diabete    = 0.0
    taux_cardio     = 0.0
    if patho_data is not None and not patho_data.empty:
        dept_patho = patho_data[
            patho_data["dept"].astype(str).str.zfill(2) ==
            str(r.get("dept", "")).zfill(2)
        ]
        if not dept_patho.empty:
            row_p = dept_patho.iloc[0]
            taux_diabete = float(row_p.get("prev_diabete", 0) or 0)
            taux_cardio  = float(row_p.get("prev_cardio", 0) or 0)

    prev_elevee = taux_diabete > 8.0 or taux_cardio > 10.0

    # ── Calculs pour les recos ────────────────────────────────────────────
    deficit_nb = max(0.0, med_med_nat - med_100k)
    besoin_installations = min(int(deficit_nb * population / 100_000), 30)

    # ════════════════════════════════════════════════════════════════════
    # CAS 1 — Désert médical rural → Maison de santé pluridisciplinaire
    # ════════════════════════════════════════════════════════════════════
    if is_desert and is_rural:
        nb_communes_eloignees = int(r.get("nb_communes_critiques", 0) or 0)
        recos.append({
            "title": "Implanter une maison de santé pluridisciplinaire dans les zones isolées.",
            "prose": (
                f"L'APL de {apl:.1f}\u202f/hab. place {dept_nom} en désert "
                f"médical officiel (seuil DREES\u202f: 2,5). "
                + (f"{nb_communes_eloignees}\u202fcommunes sont à plus de 15\u202fmin "
                   "d'un établissement. "
                   if nb_communes_eloignees > 0 else "")
                + (f"Le foncier médian à {prix_m2:.0f}\u202f€/m² "
                   "permet une installation à coût maîtrisé. "
                   if foncier_moyen else "")
                + "Une MSP regroupant généraliste, infirmier et pharmacien "
                  "couvre un bassin de 8\u202f000 à 15\u202f000 habitants."
            ),
            "stats": [
                (f"{apl:.1f}", "APL actuel /hab."),
                ("2.5", "Seuil désert médical"),
                (f"{prix_m2:.0f}\u202f€", "Prix médian /m²"),
            ],
            "priority": 1,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 2 — Désert médical urbain → Télémédecine + consultations avancées
    # ════════════════════════════════════════════════════════════════════
    if is_desert and is_urbain:
        recos.append({
            "title": "Réduire les délais spécialistes par télémédecine et consultations avancées.",
            "prose": (
                f"Malgré une densité urbaine, l'APL de {apl:.1f} traduit "
                "une saturation des médecins de ville. "
                "Les délais estimés pour les spécialistes dépassent "
                "largement la médiane nationale. "
                "Le déploiement de téléconsultations spécialisées, de "
                "créneaux IPA (Infirmiers en Pratique Avancée) et de "
                "centres de santé communautaires permettrait "
                "de désengorger les files d'attente."
            ),
            "stats": [
                (f"{apl:.1f}", "APL actuel /hab."),
                (f"{score_acces:.0f}/100", "Score accès"),
                (f"{int(temps)}\u202fmin", "Temps d'accès médian"),
            ],
            "priority": 1,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 3 — Déficit de généralistes → Recrutement ciblé
    # ════════════════════════════════════════════════════════════════════
    if pros_critique or (deficit_med and is_desert):
        recos.append({
            "title": "Lancer un programme d'attractivité ciblé sur les médecins généralistes.",
            "prose": (
                f"Avec {med_100k:.0f} généralistes pour 100\u202f000 habitants "
                f"contre {med_med_nat:.0f} en médiane nationale, "
                f"{dept_nom} accuse un déficit structurel de "
                f"{med_med_nat - med_100k:.0f} médecins /100k. "
                + (f"Un objectif de {besoin_installations} installations "
                   f"supplémentaires sur 3\u202fans est réaliste. "
                   if besoin_installations > 0 else "")
                + "Contrats de praticien territorial, aides à l'installation, "
                  "partenariat avec les facultés régionales."
            ),
            "stats": [
                (f"{med_100k:.0f}", "Médecins /100k actuels"),
                (f"{med_med_nat:.0f}", "Médiane nationale"),
                (f"+{besoin_installations}", "Installations visées / 3 ans"),
            ],
            "priority": 1 if pros_critique else 2,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 4 — Population vieillissante + accès dégradé → Seniors
    # ════════════════════════════════════════════════════════════════════
    if pop_vieillissante and (acces_degrade or is_desert):
        nb_tablettes = max(10, int(population * pct_65 / 100 / 500))
        recos.append({
            "title": "Déployer un programme de santé numérique pour les seniors isolés.",
            "prose": (
                f"Avec {pct_65:.1f}\u202f% de 65\u202fans et plus "
                f"({'très au-dessus' if pop_tres_vieille else 'au-dessus'} "
                f"de la médiane nationale de ~20\u202f%), {dept_nom} cumule "
                "vieillissement démographique et accès aux soins dégradé. "
                "Les seniors consomment 4× plus de soins que les adultes "
                "de 30\u202fans (DREES). "
                "Tablettes connectées en EHPAD, infirmières itinérantes "
                "équipées et téléconsultations spécialisées gériatriques "
                "réduiraient les renoncements aux soins."
            ),
            "stats": [
                (f"{pct_65:.1f}\u202f%", "Part des 65+"),
                ("~20\u202f%", "Médiane nationale"),
                (f"~{nb_tablettes}", "Structures EHPAD concernées"),
            ],
            "priority": 2,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 5 — Établissements insuffisants → Antennes hospitalières
    # ════════════════════════════════════════════════════════════════════
    if etabs_critique:
        recos.append({
            "title": "Créer des antennes de consultations externes dans les zones sous-dotées.",
            "prose": (
                f"Avec {etabs_100k:.1f} établissements pour 100\u202f000 habitants "
                f"contre {etabs_med_nat:.1f} en médiane nationale, "
                "la couverture hospitalière est insuffisante. "
                "Des antennes légères de consultations externes, "
                "adossées aux hôpitaux de référence, permettraient "
                "de réduire les temps de trajet sans infrastructure lourde. "
                "Format idéal\u202f: consultations 2\u202fjours/semaine en zone rurale."
            ),
            "stats": [
                (f"{etabs_100k:.1f}", "Étabs /100k actuels"),
                (f"{etabs_med_nat:.1f}", "Médiane nationale"),
                (f"{int(temps)}\u202fmin", "Temps d'accès médian"),
            ],
            "priority": 2,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 6 — Temps d'accès très élevé → Transport sanitaire
    # ════════════════════════════════════════════════════════════════════
    if temps_eleve and is_rural and not etabs_critique:
        recos.append({
            "title": "Organiser des navettes santé vers les établissements de référence.",
            "prose": (
                f"Avec un temps d'accès médian de {temps:.0f}\u202fminutes "
                f"(médiane nationale\u202f: {temps_med_nat:.0f}\u202fmin), "
                "de nombreux habitants renoncent aux soins faute de mobilité. "
                "Un service de navettes santé mutualisées entre communes, "
                "cofinancé par le Département et l'ARS, "
                "réduirait le renoncement aux soins des personnes sans véhicule "
                "(seniors, personnes en situation de précarité)."
            ),
            "stats": [
                (f"{temps:.0f}\u202fmin", "Temps d'accès actuel"),
                (f"{temps_med_nat:.0f}\u202fmin", "Médiane nationale"),
            ],
            "priority": 2,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 7 — Forte prévalence pathologies chroniques → Prévention
    # ════════════════════════════════════════════════════════════════════
    if prev_elevee and (acces_degrade or is_desert):
        pathologie_principale = (
            "cardiovasculaires" if taux_cardio > taux_diabete else "diabète"
        )
        taux_principal = max(taux_cardio, taux_diabete)
        recos.append({
            "title": "Renforcer la prévention et le dépistage des pathologies chroniques.",
            "prose": (
                f"{dept_nom} présente un taux de prévalence "
                f"{pathologie_principale} de {taux_principal:.1f}\u202f%, "
                "supérieur à la médiane nationale. "
                "Combiné à un accès aux soins dégradé, ce cumul augmente "
                "le risque de complications graves non prises en charge. "
                "Des programmes de dépistage actif (camions médicaux, "
                "journées de prévention en mairie) et des protocoles "
                "de suivi renforcé pour les patients chroniques "
                "permettraient de réduire la morbi-mortalité évitable."
            ),
            "stats": [
                (f"{taux_principal:.1f}\u202f%", f"Prévalence {pathologie_principale}"),
                (f"{score_acces:.0f}/100", "Score accès"),
            ],
            "priority": 2,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 8 — Population jeune élevée → Renforcer pédiatrie et PMI
    # ════════════════════════════════════════════════════════════════════
    if pop_jeune and (acces_degrade or pros_degrade):
        recos.append({
            "title": "Renforcer l'offre pédiatrique et les services de PMI.",
            "prose": (
                f"Avec {pct_moins_25:.1f}\u202f% de moins de 25\u202fans "
                f"(médiane nationale\u202f: ~28\u202f%), {dept_nom} a une population "
                "significativement jeune. "
                "L'accès aux pédiatres, médecins scolaires et services "
                "de Protection Maternelle et Infantile (PMI) est un enjeu "
                "de prévention à long terme. "
                "Renforcer les consultations pédiatriques avancées "
                "en centres de santé municipaux permettrait de "
                "décharger les généralistes."
            ),
            "stats": [
                (f"{pct_moins_25:.1f}\u202f%", "Part des moins de 25 ans"),
                ("~28\u202f%", "Médiane nationale"),
            ],
            "priority": 3,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 9 — Foncier très accessible + désert → Attirer via logement
    # ════════════════════════════════════════════════════════════════════
    if foncier_accessible and is_desert and not any(
        "attractivité" in rec.get("title", "") for rec in recos
    ):
        recos.append({
            "title": "Mobiliser l'avantage foncier pour attirer des professionnels de santé.",
            "prose": (
                f"Le prix médian à {prix_m2:.0f}\u202f€/m² représente un levier "
                "d'attractivité concret pour les professionnels de santé. "
                "Un programme de mise à disposition de locaux professionnels "
                "à tarif préférentiel ou en bail emphytéotique, couplé "
                "à des aides au logement pour les médecins s'installant "
                "dans les zones sous-denses, constitue une réponse "
                "complémentaire aux aides conventionnelles."
            ),
            "stats": [
                (f"{prix_m2:.0f}\u202f€", "Prix médian /m²"),
                (f"{apl:.1f}", "APL actuel /hab."),
            ],
            "priority": 3,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 10 — Score intermédiaire global → Plan de vigilance
    # ════════════════════════════════════════════════════════════════════
    if not recos and 33 <= score_global <= 55:
        recos.append({
            "title": "Mettre en place un plan de vigilance sur les indicateurs fragiles.",
            "prose": (
                f"{dept_nom} présente une situation intermédiaire "
                f"(score {score_global:.0f}/100) avec des signaux de fragilité "
                "sur certains indicateurs. "
                "Un suivi trimestriel de l'APL, des effectifs RPPS et "
                "du temps d'accès permettrait de détecter précocement "
                "toute dégradation avant qu'elle ne devienne critique. "
                "Les zones péri-urbaines sont particulièrement à surveiller."
            ),
            "stats": [
                (f"{score_global:.0f}/100", "Score global actuel"),
                (f"{apl:.1f}", "APL actuel /hab."),
            ],
            "priority": 3,
        })

    # ════════════════════════════════════════════════════════════════════
    # CAS 11 — Situation favorable → Maintien et benchmarking
    # ════════════════════════════════════════════════════════════════════
    if not recos:
        recos.append({
            "title": "Maintenir les acquis et partager les bonnes pratiques.",
            "prose": (
                f"{dept_nom} présente des indicateurs supérieurs ou proches "
                "de la médiane nationale sur l'ensemble des dimensions. "
                "La priorité est de maintenir cette situation face au "
                "vieillissement démographique des médecins en exercice. "
                "Ce territoire peut servir de référence pour les "
                "départements voisins en difficulté."
            ),
            "stats": [
                (f"{score_global:.0f}/100", "Score global"),
                (f"{apl:.1f}", "APL actuel /hab."),
            ],
            "priority": 3,
        })

    # Trie par priorité et limite à 4
    recos.sort(key=lambda x: x.get("priority", 3))
    return recos[:4]


def _render_reco_card(reco: dict, index: int) -> None:
    """Affiche une carte de recommandation.

    Le badge priorité est basé sur la position dans la liste (index, 1-based),
    pas sur la valeur stockée dans reco['priority'].
    """
    if index == 1:
        badge_label, badge_class = "Priorité 1", "p1"
    elif index == 2:
        badge_label, badge_class = "Priorité 2", "p2"
    else:
        badge_label, badge_class = f"Priorité {index}", "p3"

    stats_html = "".join(
        f'<div class="reco-stat">'
        f'<span class="val">{v}</span>'
        f'<span class="lbl">{l}</span>'
        f'</div>'
        for v, l in reco.get("stats", [])
    )
    stats_block = f'<div class="reco-stats">{stats_html}</div>' if stats_html else ""

    st.html(
        '<div class="reco-card">'
        f'<span class="reco-priority {badge_class}">{badge_label}</span>'
        f'<div class="reco-number">{index:02d} —</div>'
        f'<div class="reco-title">{reco["title"]}</div>'
        f'<div class="reco-prose">{reco["prose"]}</div>'
        f'{stats_block}'
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
        '<em>et de quoi souffrent-ils.</em></h2>'
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
        dept_val = float(r.get(col, 0) or 0)
        nat_val = float(master[col].median())
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
    pop = float(r.get("population_num", 0) or 0)
    for col, lbl in age_cols:
        pct = float(r.get(col, 0) or 0)
        hab = int(pct / 100 * pop)
        hab_str = f"{hab:,}".replace(",", "\u202f")
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

    dg = dp.groupby("patho_niv1")[["Ntop", "Npop"]].sum().reset_index()
    dg["prev"] = (dg["Ntop"] / dg["Npop"] * 100).round(2)
    top5 = dg.sort_values("prev", ascending=False).head(5)
    max_prev = float(top5["prev"].max())

    colors = ["#1A3D8F", "#3A5DA3", "#5A7DB7", "#7B9DCB", "#9BBDDF"]
    html = '<div class="patho-list">'
    for i, (_, row) in enumerate(top5.iterrows()):
        width = (float(row["prev"]) / max_prev * 100) if max_prev else 0
        ntop = int(row["Ntop"])
        ntop_str = f"{ntop:,}".replace(",", "\u202f")
        html += (
            '<div class="patho-item">'
            f'<div class="patho-name">{str(row["patho_niv1"])[:55]}</div>'
            f'<div class="patho-val">{row["prev"]:.2f}\u202f%\u2002·\u2002{ntop_str}\u202fpat.</div>'
            '<div class="patho-bar">'
            f'<div class="patho-bar-fill" style="width:{width:.1f}%;background:{colors[i]};"></div>'
            '</div>'
            '</div>'
        )
    html += '</div>'
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


def render_offre_medicale(r: pd.Series, data: dict) -> None:

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">OFFRE MÉDICALE</div>'
        '<h2 class="section-title">'
        "Combien de <em>spécialistes,</em> et qu'en déduire.</h2>"
        '<p class="section-lead">'
        'Top 5 soins primaires et top 5 spécialistes liés aux pathologies '
        'prédominantes du territoire. Comparés à la médiane nationale '
        'pour 100 000 habitants.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    dept_code  = str(r.get("dept", "")).zfill(2)
    population = float(r.get("Population", 300_000) or 300_000)
    pros       = data.get("pros")

    if pros is None or pros.empty:
        st.info("Données professionnels non disponibles.")
        return

    # ── Agrégation RPPS pour ce département ──────────────────────────────
    pros_dept = pros[
        pros["code_departement"].astype(str).str.zfill(2) == dept_code
    ].copy()

    agg = (
        pros_dept.groupby("specialite").size()
        .reset_index(name="nb")
    )
    agg["pour_100k"] = (agg["nb"] / population * 100_000).round(1)

    # Médiane nationale par spécialité (densité médiane sur tous les depts)
    nat_by_dept = (
        pros.groupby(["code_departement", "specialite"])
        .size().reset_index(name="nb_dept")
    )
    pop_map = data["master"].set_index("dept")["Population"].to_dict()
    nat_by_dept["pop"] = nat_by_dept["code_departement"].map(
        lambda x: float(pop_map.get(str(x).zfill(2), 300_000) or 300_000)
    )
    nat_by_dept["densite"] = (
        nat_by_dept["nb_dept"] / nat_by_dept["pop"] * 100_000
    )
    nat_medians = (
        nat_by_dept.groupby("specialite")["densite"]
        .median().reset_index()
        .rename(columns={"densite": "mediane_nat"})
    )
    agg = agg.merge(nat_medians, on="specialite", how="left")
    agg["mediane_nat"] = agg["mediane_nat"].fillna(0)
    agg["ecart_pct"]   = (
        (agg["pour_100k"] - agg["mediane_nat"]) /
        agg["mediane_nat"].replace(0, float("nan")) * 100
    ).round(0)

    # ── Pathologies dominantes ────────────────────────────────────────────
    _PATHO_MAP = {
        "prev_cardio":        ("Maladies cardiovasculaires", ["Cardiologue"]),
        "prev_diabete":       ("Diabète",                   ["Endocrinologue"]),
        "prev_psychiatrique": ("Maladies psychiatriques",   ["Psychiatre"]),
        "prev_respiratoire":  ("Maladies respiratoires",    ["Pneumologue"]),
        "prev_cancers":       ("Cancers",                   ["Oncologue médical", "Hématologue"]),
        "prev_rhumatologie":  ("Rhumatologie",              ["Rhumatologue"]),
        "prev_neurologie":    ("Neurologie",                ["Neurologue"]),
        "prev_ophtalmologie": ("Ophtalmologie",             ["Ophtalmologiste"]),
    }

    patho_data = data.get("patho")
    top_pathos = {}
    nat_patho  = {}

    if patho_data is not None and not patho_data.empty:
        dept_patho = patho_data[
            patho_data["dept"].astype(str).str.zfill(2) == dept_code
        ]
        if not dept_patho.empty:
            row_p = dept_patho.iloc[0]
            for pk in _PATHO_MAP:
                val = float(row_p.get(pk, 0) or 0)
                if val > 0:
                    top_pathos[pk] = val
                    nat_patho[pk]  = float(
                        patho_data[pk].median()
                        if pk in patho_data.columns else 0
                    )

    top5_pathos = sorted(
        top_pathos.items(), key=lambda x: x[1], reverse=True
    )[:5]

    # ── Calcul du besoin réel ─────────────────────────────────────────────
    def besoin_reel(dept_val, nat_val, patho_key=None):
        if nat_val <= 0 or dept_val >= nat_val:
            return None
        deficit = (nat_val - dept_val) * population / 100_000
        facteur = 1.0
        if patho_key and patho_key in top_pathos:
            taux_d = top_pathos[patho_key]
            taux_n = nat_patho.get(patho_key, taux_d)
            if taux_n > 0:
                facteur = max(1.0, min(1 + (taux_d - taux_n) / taux_n, 2.5))
        return min(int(round(deficit * facteur)), 60)

    # ── Fonction render d'une ligne ───────────────────────────────────────
    def render_row(spec_nom, nb, pour_100k, med_nat,
                   patho_label, patho_key, idx, is_absent=False):
        ecart = (
            ((pour_100k - med_nat) / med_nat * 100)
            if med_nat > 0 else -100
        )
        ecart_color = (
            "#1B5E3F" if ecart >= 10
            else "#A51C30" if ecart <= -10
            else "#6B6B68"
        )
        ecart_str = f"+{int(ecart)} %" if ecart >= 0 else f"{int(ecart)} %"

        br       = besoin_reel(pour_100k, med_nat, patho_key)
        br_str   = f"+{br}" if br else "—"
        br_color = "#A51C30" if br else "#9C9A92"

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
            f'grid-template-columns:3fr 0.6fr 0.8fr 0.8fr 0.7fr 0.9fr;'
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
            f'<div style="font-size:13px;font-weight:700;color:{br_color};text-align:right;">'
            f'{br_str}</div>'
            f'</div>'
        )

    # ── En-tête tableau ───────────────────────────────────────────────────
    header = (
        '<div style="display:grid;'
        'grid-template-columns:3fr 0.6fr 0.8fr 0.8fr 0.7fr 0.9fr;'
        'padding:10px 16px;background:#0A1938;border-radius:6px 6px 0 0;gap:0;">'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);">SPÉCIALITÉ</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">NB</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">/100K</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">MÉD.NAT.</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">ÉCART</div>'
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.5);text-align:right;">BESOIN RÉEL*</div>'
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
        "Médecin généraliste",
        "Infirmier",
        "Pharmacien",
        "Masseur-kinésithérapeute",
        "Chirurgien-dentiste",
    ]

    table_html = (
        f'<div style="border:1px solid #E8E6DD;border-radius:6px;overflow:hidden;">'
        f'{header}'
    )

    # ── TOP 5 SOINS PRIMAIRES ─────────────────────────────────────────────
    table_html += section_sep("TOP 5 · SOINS PRIMAIRES")

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
                spec_nom=spec_exact, nb=0, pour_100k=0.0, med_nat=0.0,
                patho_label=None, patho_key=None, idx=i, is_absent=True,
            )

    # ── TOP 5 SPÉCIALISTES LIÉS AUX PATHOLOGIES ──────────────────────────
    table_html += section_sep(
        "TOP 5 · SPÉCIALISTES LIÉS AUX PATHOLOGIES PRÉDOMINANTES"
    )

    spec_count = 0
    for pk, taux in top5_pathos:
        if spec_count >= 5:
            break
        cfg = _PATHO_MAP.get(pk)
        if not cfg:
            continue
        patho_label, spec_list = cfg
        for spec_exact in spec_list:
            if spec_count >= 5:
                break
            match = agg[
                agg["specialite"].str.lower().str.startswith(spec_exact.lower())
            ]
            if not match.empty:
                row_s = match.iloc[0]
                table_html += render_row(
                    spec_nom=row_s["specialite"], nb=int(row_s["nb"]),
                    pour_100k=float(row_s["pour_100k"]),
                    med_nat=float(row_s["mediane_nat"]),
                    patho_label=patho_label, patho_key=pk, idx=spec_count,
                )
            else:
                table_html += render_row(
                    spec_nom=spec_exact, nb=0, pour_100k=0.0, med_nat=0.0,
                    patho_label=patho_label, patho_key=pk,
                    idx=spec_count, is_absent=True,
                )
            spec_count += 1

    table_html += "</div>"
    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown(
        '<div style="margin-top:10px;padding:12px 16px;background:#F3F2EC;'
        'border-radius:4px;font-size:12px;color:#6B6B68;line-height:1.6;">'
        '<strong style="color:#2B2B2B;">* Besoin réel</strong> = '
        '(médiane nationale \u2212 densité locale) \u00d7 population / 100\u202f000, '
        'amplifié par la prévalence locale de la pathologie associée '
        '(facteur max \u00d72.5, plafon 60). Le RPPS inclut tous les modes '
        "d'exercice ; l'APL reste l'indicateur de référence pour "
        'l\'accès réel aux soins de ville.'
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

    apl = r.get("apl_median_dept")
    dept_code = str(r.get("dept", "")).zfill(2)

    # ── Bandeau si désert médical ──────────────────────────────────────────
    if pd.notna(apl) and is_desert_medical(float(apl)):
        st.markdown(
            f'<div style="background:#FEE9E9;border:1px solid #A51C30;'
            f'border-radius:4px;padding:14px 18px;margin:0 0 24px;'
            f'font-size:14px;color:#5E0000;">'
            f'<strong>Zone en désert médical</strong> — APL de {apl:.1f}\u202f/hab., '
            f'en dessous du seuil DREES de {APL_SEUIL_DESERT} '
            f'consultations/an/habitant. '
            f'Les délais estimés ci-dessous sont probablement sous-évalués.'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Calcul du proxy ────────────────────────────────────────────────────
    APL_NATIONALE = 2.9  # médiane nationale ANCT 2023

    if pd.isna(apl):
        st.info("APL non disponible pour ce département — délais non calculables.")
        return

    delais = compute_delais_proxy(dept_code, float(apl), APL_NATIONALE)

    if delais.empty:
        st.info("Données de délais non disponibles.")
        return

    # ── Affichage en grille 3 colonnes ─────────────────────────────────────
    delais = delais.sort_values("delai_estime_jours")

    cols = st.columns(3)
    for i, (_, row) in enumerate(delais.iterrows()):
        est = int(row["delai_estime_jours"])
        interp = row["interpretation"]

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
                f'</div>',
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

def find_similar_depts(
    r: pd.Series,
    master: pd.DataFrame,
    n: int = 3,
) -> list[dict]:
    """Matching sur score, densité, part des 65+ et zone identique."""
    dept_code = str(r.get("dept", "")).zfill(2)
    zone      = r.get("zone_short", "")
    score     = float(r.get("score_global", 50) or 50)
    densite   = float(r.get("densite", 50) or 50)
    pct_65    = float(r.get("pct_plus_65", 20) or 20)
    region    = str(r.get("Code région", ""))
    is_dom    = dept_code in {"971", "972", "973", "974", "976"}

    candidates = master[
        (master["dept"] != dept_code) &
        (master["zone_short"] == zone)
    ].copy()

    if not is_dom:
        candidates = candidates[
            ~candidates["dept"].isin({"971", "972", "973", "974", "976"})
        ]

    if candidates.empty:
        return []

    def _sim(row):
        s_diff = abs(float(row.get("score_global", 50) or 50) - score) / 100
        d_diff = abs(float(row.get("densite", 50) or 50) - densite) / max(densite, 1)
        p_diff = abs(float(row.get("pct_plus_65", 20) or 20) - pct_65) / 100
        bonus  = -0.1 if str(row.get("Code région", "")) == region else 0
        return 0.40 * s_diff + 0.30 * min(d_diff, 1.0) + 0.30 * p_diff + bonus

    candidates["_sim"] = candidates.apply(_sim, axis=1)
    top = candidates.nsmallest(n, "_sim")

    results = []
    for _, row in top.iterrows():
        same_region = str(row.get("Code région", "")) == region
        results.append({
            "dept":   row["dept"],
            "nom":    row.get("Nom du département", ""),
            "score":  row.get("score_global"),
            "zone":   row.get("zone_short", ""),
            "raison": "Même région · Profil similaire"
                      if same_region else "Même zone · Profil similaire",
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

    cols = st.columns(min(3, len(suggestions)))
    for i, sim in enumerate(suggestions[:3]):
        with cols[i]:
            score_val = sim["score"]
            score_str = f"{score_val:.0f}/100" if pd.notna(score_val) else "—"
            zone_sug  = str(sim["zone"])
            badge_cls = {"Critique": "crit", "Intermédiaire": "inter",
                         "Favorable": "fav"}.get(zone_sug, "")
            st.html(
                '<div class="suggestion-card">'
                f'<div class="suggestion-label">{sim["raison"]}</div>'
                f'<div class="suggestion-name">{sim["nom"]}</div>'
                f'<div class="suggestion-score">{score_str}'
                f'<span class="fiche-zone-badge {badge_cls}" '
                f'style="font-size:11px;padding:4px 10px;">'
                f'{zone_sug}</span>'
                '</div>'
                '</div>'
            )
            if st.button(
                "Voir la fiche →",
                key=f"suggest_{r['dept']}_{sim['dept']}",
                use_container_width=True,
            ):
                navigate("dept", dept_code=sim["dept"])
