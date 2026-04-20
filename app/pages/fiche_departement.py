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
    render_scorecard(r, master)
    render_carte_communale(r, data)
    render_recommandations(r, master, data)
    render_contexte(r, data)
    render_offre_specialistes(r, data)
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
        if st.button("⧉  Comparer avec…", use_container_width=True):
            st.session_state["compare_base"] = r["dept"]
            navigate("comparer")
    with col2:
        if st.button("⇄  Partager ce lien", use_container_width=True):
            st.info(f"?view=dept&dept_code={r['dept']}")
    with col3:
        with st.spinner("Génération du PDF…"):
            try:
                recos = _generate_recommendations(r, data["master"], data)
                pdf_bytes = generate_department_pdf(r, data["master"], recos, data)
                dept_slug = str(r.get("Nom du département", "rapport")).lower().replace(" ", "_")
                st.download_button(
                    label="⬇  Rapport PDF",
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
    score_str = f"{score:.1f}" if pd.notna(score) else "—"
    rang_str = str(rang_num)

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

def render_diagnostic(r: pd.Series, master: pd.DataFrame) -> None:
    """Phrase éditoriale + APL en chiffre géant (vraies données DREES)."""
    zone = str(r.get("zone_short", ""))

    phrases = []
    if zone == "Critique":
        phrases.append("présente une situation <em>préoccupante</em>")
    elif zone == "Intermédiaire":
        phrases.append("présente une situation <em>mitigée</em>")
    else:
        phrases.append("présente une situation <em>favorable</em>")

    pros = r.get("pros_pour_100k")
    med_pros = master["pros_pour_100k"].median()
    if pd.notna(pros) and pd.notna(med_pros) and med_pros > 0:
        delta = (pros - med_pros) / med_pros * 100
        if delta < -15:
            phrases.append(
                f"un <strong>sous-effectif médical de {abs(delta):.0f}\u202f%</strong> "
                "sous la médiane nationale"
            )

    nc = r.get("nb_communes_critiques")
    if pd.notna(nc) and int(nc) > 0:
        nc_int = int(nc)
        commune_label = "commune" if nc_int == 1 else "communes"
        phrases.append(
            f"<strong>{nc_int} {commune_label} en zone blanche</strong>"
        )

    phrase = (
        f"{r['Nom du département']} "
        f"{' et '.join(phrases) if phrases else 'est dans la moyenne nationale'}."
    )

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
    st.html(
        '<div class="section-header">'
        '<div class="section-eyebrow">SCORECARD</div>'
        '<h2 class="section-title">Où ce département <em>décroche</em>, '
        'et où il tient bon.</h2>'
        '</div>'
    )

    scores = [
        (f'Accès aux soins {info_tooltip("score_acces")}',
         "APL + temps de trajet médian",
         r.get("score_acces"), master["score_acces"]),
        (f'Professionnels de santé {info_tooltip("score_pros")}',
         "RPPS, hors remplaçants",
         r.get("score_pros"), master["score_pros"]),
        (f'Établissements {info_tooltip("score_etabs")}',
         "Hôpitaux + cliniques FINESS",
         r.get("score_etabs"), master["score_etabs"]),
    ]

    rows_html = ""
    for label, desc, val, series in scores:
        if pd.isna(val):
            continue
        med = float(series.median())
        q25 = float(series.quantile(0.25))
        q75 = float(series.quantile(0.75))
        val = float(val)
        delta = val - med
        color = "crit" if val < 33 else ("inter" if val < 66 else "fav")
        delta_cls = "pos" if delta >= 0 else "neg"

        rows_html += (
            '<div class="score-row">'
            '<div class="score-label">'
            f'{label}<span class="desc">{desc}</span>'
            '</div>'
            '<div class="score-bar">'
            f'<div class="score-bar-range" style="left:{q25:.1f}%;width:{q75-q25:.1f}%;"></div>'
            f'<div class="score-bar-median" style="left:{med:.1f}%;"></div>'
            f'<div class="score-bar-dept {color}" style="left:{val:.1f}%;"></div>'
            '</div>'
            '<div class="score-value">'
            f'<span class="num">{val:.0f}</span>'
            f'<span class="delta {delta_cls}">{delta:+.0f}\u202fpts vs médiane</span>'
            '</div>'
            '</div>'
        )

    st.markdown(f'<div class="scorecard-block">{rows_html}</div>', unsafe_allow_html=True)


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
    titre = _titres.get(nb, f"{nb} leviers")

    st.html(
        '<div class="section-header">'
        '<div class="section-eyebrow">PLAN D\'ACTION</div>'
        f'<h2 class="section-title">{titre} <em>prioritaires</em>.</h2>'
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
    r: pd.Series, master: pd.DataFrame, data: dict
) -> list[dict]:
    """Recommandations adaptées à la typologie du territoire.

    Principe : on ne déclenche une reco que si le BESOIN RÉEL est établi,
    pas seulement un écart statistique. Les volumes sont plafonnés à des
    valeurs réalistes pour éviter des résultats absurdes (ex. Paris).
    """
    recos: list[dict] = []
    dept_code = str(r["dept"]).zfill(2)
    typologie = str(r.get("typologie", "inconnu"))

    score_acces = float(r.get("score_acces", 50) or 50)
    score_pros  = float(r.get("score_pros",  50) or 50)
    score_etabs = float(r.get("score_etabs", 50) or 50)
    nc          = float(r.get("nb_communes_critiques", 0) or 0)
    pct65       = float(r.get("pct_plus_65", 0) or 0)
    pop         = float(r.get("population_num", 0) or 0)

    acces_degrade  = score_acces < 40
    offre_degradee = score_pros  < 35

    # ── RURAL / PÉRI-URBAIN ────────────────────────────────────────────────────
    if typologie in ("rural", "peri_urbain"):

        # R1 : MSP si communes en zone blanche
        if nc >= 3:
            temps_df: pd.DataFrame = data["temps"]
            top_com = (
                temps_df[temps_df["code_departement"].astype(str).str.zfill(2) == dept_code]
                .sort_values("temps_acces", ascending=False)
                .head(1)
            )
            target_com = top_com.iloc[0]["commune"] if not top_com.empty else "zone isolée"
            recos.append({
                "priority": "P1",
                "title": f"Implanter une maison de santé pluridisciplinaire à {target_com}.",
                "prose": (
                    f"{int(nc)} communes sont à plus de 15 minutes d'un établissement. "
                    "Le foncier rural permet une installation à coût maîtrisé."
                ),
                "stats": [
                    (f"{int(nc)}", "Communes cibles"),
                    ("~12\u202fkm", "Isochrone 10\u202fmin"),
                    (f"~{min(int(nc) * 800, 15000):,}".replace(",", "\u202f"), "Hab. desservis"),
                ],
            })

        # R2 : Recrutement généralistes — plafonné à 30
        if offre_degradee and acces_degrade:
            pros_cur    = float(r.get("pros_pour_100k", 0) or 0)
            pros_median = float(master["pros_pour_100k"].median())
            if pros_cur > 0 and pros_median > pros_cur:
                deficit_theorique = int((pros_median - pros_cur) * pop / 100_000)
                cible = min(max(deficit_theorique, 5), 30)
                recos.append({
                    "priority": "P1",
                    "title": f"Attirer {cible} généralistes sur 3 ans via dispositif ZRR.",
                    "prose": (
                        "Prime d'installation, logement de fonction, garantie de revenu "
                        "plancher 24\u202fmois. Partenariat avec les facultés de médecine "
                        "régionales pour les internes."
                    ),
                    "stats": [
                        (f"+{cible}", "Objectif 3\u202fans"),
                        ("60\u202fk€", "Prime /install."),
                        ("+4\u202fà\u202f6\u202fpts", "Impact score"),
                    ],
                })

        # R3 : Télémédecine seniors si acces dégradé + surreprésentation 65+
        if pct65 > master["pct_plus_65"].quantile(0.75) and acces_degrade:
            recos.append({
                "priority": "P2",
                "title": "Déployer la télémédecine pour les seniors isolés.",
                "prose": (
                    f"{pct65:.0f}\u202f% de +65 ans combiné à un accès dégradé. "
                    "Tablettes connectées en EHPAD + infirmières itinérantes équipées."
                ),
                "stats": [
                    (f"{pct65:.0f}\u202f%", "Part des 65+"),
                    ("~200", "Tablettes"),
                    ("4", "Spécialités"),
                ],
            })

    # ── URBAIN / URBAIN DENSE ─────────────────────────────────────────────────
    elif typologie in ("urbain", "urbain_dense"):

        # R1 : Délais RDV spécialistes (vrai enjeu urbain)
        recos.append({
            "priority": "P1",
            "title": "Réduire les délais de RDV pour les spécialités sous tension.",
            "prose": (
                "En zone dense, l'enjeu n'est pas la couverture géographique mais "
                "l'accès aux spécialistes. Créneaux ARS en centres municipaux, "
                "téléconsultation ophtalmo/dermato, partenariats CHU."
            ),
            "stats": [
                ("≈\u202f82\u202fj", "Délai moyen spé."),
                ("-30\u202f%", "Objectif 2\u202fans"),
                ("5", "Spécialités cibles"),
            ],
        })

        # R2 : Pathologie dominante en milieu urbain
        patho_df: pd.DataFrame = data["patho"]
        if not patho_df.empty and "_error" not in patho_df.columns:
            dept_patho = patho_df[patho_df["dept"] == dept_code]
            if not dept_patho.empty and "patho_niv1" in dept_patho.columns:
                top = (
                    dept_patho[~dept_patho["patho_niv1"].isin(PATHOS_EXCLUDED)]
                    .groupby("patho_niv1")["Ntop"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(1)
                )
                if not top.empty:
                    ntop_str = f"{int(top.iloc[0]):,}".replace(",", "\u202f")
                    recos.append({
                        "priority": "P2",
                        "title": f"Campagne de prévention ciblée : {top.index[0][:50]}.",
                        "prose": (
                            f"{ntop_str} patients concernés. Dépistage en entreprise "
                            "et dans les centres de santé de quartier prioritaires."
                        ),
                        "stats": [
                            (ntop_str, "Patients"),
                            ("Quartiers QPV", "Zonage cible"),
                            ("12\u202fmois", "Durée"),
                        ],
                    })

        # R3 : Déserts médicaux urbains intra-départementaux
        if score_pros < 35:
            recos.append({
                "priority": "P2",
                "title": "Cibler les déserts médicaux intra-urbains (quartiers prioritaires).",
                "prose": (
                    "Le ratio moyen masque de fortes disparités entre quartiers. "
                    "Centres de santé municipaux + permanences d'accès aux soins dans les QPV."
                ),
                "stats": [
                    ("QPV", "Périmètre cible"),
                    ("3–5", "Centres à ouvrir"),
                    ("+15\u202f%", "Couverture visée"),
                ],
            })

    # ── RECO COMMUNE : ratio patients/spécialistes (tous territoires) ──────────
    pros_df: pd.DataFrame = data["pros"]
    patho_df2: pd.DataFrame = data["patho"]
    if (
        not patho_df2.empty and "_error" not in patho_df2.columns
        and not pros_df.empty
    ):
        dept_patho2 = patho_df2[patho_df2["dept"] == dept_code]
        if not dept_patho2.empty and "patho_niv1" in dept_patho2.columns:
            from ..config import PATHOS_SPECIALITES_MAP

            worst = None  # (name, ratio, nb_pat, nb_spec, specs)
            for patho_name, specs in PATHOS_SPECIALITES_MAP.items():
                rows = dept_patho2[dept_patho2["patho_niv1"] == patho_name]
                if rows.empty:
                    continue
                nb_pat = int(rows["Ntop"].sum())
                if nb_pat < 1000:
                    continue
                nb_spec = int(
                    pros_df[
                        (pros_df["dept"] == dept_code)
                        & (pros_df["specialite_libelle"].isin(specs))
                    ].shape[0]
                )
                if nb_spec == 0:
                    continue
                ratio = nb_pat / nb_spec
                if worst is None or ratio > worst[1]:
                    worst = (patho_name, ratio, nb_pat, nb_spec, specs)

            if worst and worst[1] > 5000:
                patho_name, ratio, nb_pat, nb_spec, specs = worst
                nb_pat_str = f"{nb_pat:,}".replace(",", "\u202f")
                ratio_str  = f"{int(ratio):,}".replace(",", "\u202f")
                recos.append({
                    "priority": "P2",
                    "title": (
                        f"Renforcer l'offre en {specs[0].lower()} "
                        f"face à : {patho_name[:40]}."
                    ),
                    "prose": (
                        f"{nb_pat_str} patients pour {nb_spec}\u202f"
                        f"{specs[0].lower()}{'s' if nb_spec > 1 else ''}. "
                        "Cabinet de groupe + téléconsultation recommandés."
                    ),
                    "stats": [
                        (ratio_str, f"Pat.\u202f/\u202f{specs[0].lower()}"),
                        (f"{nb_spec}", "Actifs"),
                        (f"+{max(int(ratio / 2000), 2)}", "Recrutement cible"),
                    ],
                })

    # ── FALLBACK ───────────────────────────────────────────────────────────────
    if not recos:
        recos.append({
            "priority": "P3",
            "title": "Maintenir les acquis et surveiller l'évolution trimestrielle.",
            "prose": (
                "Aucune priorité critique identifiée. "
                "Dispositif de veille recommandé pour anticiper les retournements."
            ),
            "stats": [],
        })

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

def render_offre_specialistes(r: pd.Series, data: dict) -> None:
    """Tableau spécialistes présents vs médiane nationale pour 100 000 hab."""
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">OFFRE MÉDICALE</div>'
        '<h2 class="section-title">Combien de <em>spécialistes</em>, '
        'et qu\'en déduire.</h2>'
        '<p class="section-lead">Effectifs par spécialité dans le département, '
        'comparés à la densité médiane nationale pour 100\u202f000 habitants.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    pros: pd.DataFrame = data["pros"]
    master: pd.DataFrame = data["master"]
    dept_code = str(r["dept"]).zfill(2)
    pop = float(r.get("population_num", 0) or 0)

    if pros.empty or pop == 0:
        st.info("Données professionnels indisponibles pour ce département.")
        return

    counts_dept = (
        pros[pros["dept"] == dept_code]["specialite_libelle"]
        .value_counts()
        .head(12)
    )
    if counts_dept.empty:
        st.info("Aucun professionnel recensé pour ce département.")
        return

    # Médiane nationale par spécialité (pour 100 000 hab.)
    pros_nat = pros.groupby(["dept", "specialite_libelle"]).size().reset_index(name="n")
    pros_nat = pros_nat.merge(master[["dept", "population_num"]], on="dept", how="left")
    pros_nat["per_100k"] = pros_nat["n"] / pros_nat["population_num"] * 100_000
    medians = pros_nat.groupby("specialite_libelle")["per_100k"].median().to_dict()

    rows_html = ""
    for spec, nb in counts_dept.items():
        per_100k_dept = nb / pop * 100_000
        median_nat = float(medians.get(spec, 0))
        if median_nat > 0:
            delta = (per_100k_dept - median_nat) / median_nat * 100
            delta_str = f"{delta:+.0f}\u202f%"
            color = "crit" if delta < -30 else ("inter" if delta < -10 else "fav")
            besoin = max(0, int((median_nat - per_100k_dept) * pop / 100_000))
            besoin = min(besoin, 15)
            besoin_str = f"+{besoin}" if besoin > 0 else "—"
        else:
            delta_str, color, besoin_str = "—", "neutral", "—"

        rows_html += (
            "<tr>"
            f'<td class="spec-name">{spec}</td>'
            f'<td class="spec-count">{int(nb)}</td>'
            f'<td class="spec-density">{per_100k_dept:.1f}</td>'
            f'<td class="spec-median">{median_nat:.1f}</td>'
            f'<td class="spec-delta {color}">{delta_str}</td>'
            f'<td class="spec-besoin {color}">{besoin_str}</td>'
            "</tr>"
        )

    st.markdown(
        '<table class="offre-table">'
        "<thead><tr>"
        "<th>Spécialité</th>"
        '<th style="text-align:right;">Nb</th>'
        f'<th style="text-align:right;">/\u202f100k {info_tooltip("med_100k")}</th>'
        '<th style="text-align:right;">Méd.\u202fnat.</th>'
        '<th style="text-align:right;">Écart</th>'
        '<th style="text-align:right;">Besoin*</th>'
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="margin-top:16px;padding:12px 16px;background:#F3F2EC;'
        'border-radius:4px;font-size:12px;color:#6B6B68;line-height:1.6;">'
        '<strong style="color:#2B2B2B;">'
        'Pourquoi ces chiffres peuvent sembler contradictoires avec l\'APL\u202f?'
        '</strong><br>'
        'Le RPPS comptabilise <strong>tous les modes d\'exercice</strong>\u202f: '
        'libéral, salarié hospitalier, mixte. L\'APL ne compte que les médecins '
        'libéraux avec une <strong>activité réelle pondérée</strong>. Un médecin '
        'salarié à l\'hôpital compte dans le RPPS mais pas dans l\'APL. '
        'Un département peut afficher une densité RPPS correcte tout en étant '
        'en désert médical selon l\'APL, qui reste l\'indicateur de référence '
        'DREES pour l\'accès réel aux soins de ville.<br><br>'
        '* Besoin théorique pour atteindre la médiane nationale, '
        'plafonné à 15 installations sur 3 ans.'
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
