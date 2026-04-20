"""Fiche commune : vue resserrée. Données partielles assumées et annoncées."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..components import render_kpi_card
from ..router import navigate


def render(data: dict) -> None:
    commune_code = st.session_state.get("commune_code", "")

    # Le code est au format "NOM_COMMUNE|CODE_DEPT" (construit dans search.py)
    if "|" not in commune_code:
        st.error(f"Code commune invalide ({commune_code!r}). Veuillez relancer une recherche.")
        if st.button("← Retour accueil"):
            navigate("home")
        return

    commune_name, dept_code = commune_code.split("|", 1)
    dept_code = dept_code.zfill(2)

    master: pd.DataFrame = data["master"]
    immo: pd.DataFrame   = data["immo"]
    temps: pd.DataFrame  = data["temps"]
    etabs: pd.DataFrame  = data["etabs"]

    dept_row    = master[master["dept"] == dept_code]
    dept_name   = dept_row.iloc[0]["Nom du département"] if not dept_row.empty else "—"
    region_name = dept_row.iloc[0]["Nom de la région"]   if not dept_row.empty else "—"
    region_code = str(dept_row.iloc[0]["Code région"])    if not dept_row.empty else ""

    # ── TOPBAR ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="fiche-topbar"><div class="breadcrumb">'
        f'<a href="?view=home">Accueil</a>'
        f'<span class="sep">›</span>'
        f'<a href="?view=region&region_code={region_code}">{region_name}</a>'
        f'<span class="sep">›</span>'
        f'<a href="?view=dept&dept_code={dept_code}">{dept_name}</a>'
        f'<span class="sep">›</span>'
        f'<span class="current">{commune_name.title()}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── HEADER ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="fiche-header">'
        f'<div class="fiche-eyebrow">'
        f'<span class="code">COMMUNE</span>'
        f'<span class="dot"></span>'
        f'<span class="region">{dept_name} · {region_name}</span>'
        f'</div>'
        f'<div class="fiche-title-row">'
        f'<h1 class="fiche-title">{commune_name.title()}</h1>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── BANDEAU DONNÉES PARTIELLES ─────────────────────────────────────────────
    st.markdown(
        '<div style="background:#FCF4DB;border:1px solid #F4C430;border-radius:4px;'
        'padding:12px 16px;margin:16px 0 24px;font-size:13px;color:#7D4A00;">'
        '<strong>Données partielles à la maille commune.</strong> Les indicateurs '
        'de santé (médecins, pathologies, APL) ne sont disponibles qu\'au niveau '
        'départemental. Consultez la fiche du département pour le diagnostic complet.'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Agrégation des données communes ───────────────────────────────────────
    name_upper = commune_name.upper()

    immo_c = immo[
        (immo["commune"].str.upper() == name_upper)
        & (immo["code_departement"].astype(str).str.zfill(2) == dept_code)
    ] if not immo.empty and "commune" in immo.columns else pd.DataFrame()

    temps_c = temps[
        (temps["commune"].str.upper() == name_upper)
        & (temps["code_departement"].astype(str).str.zfill(2) == dept_code)
    ] if not temps.empty and "commune" in temps.columns else pd.DataFrame()

    etabs_c = etabs[
        (etabs["commune"].str.upper() == name_upper)
        & (etabs["code_departement"].astype(str).str.zfill(2) == dept_code)
    ] if not etabs.empty and "commune" in etabs.columns else pd.DataFrame()

    prix_m2     = immo_c["prix_m2"].median() if not immo_c.empty else None
    temps_acces = temps_c["temps_acces"].mean() if not temps_c.empty else None
    nb_trans    = len(immo_c)
    nb_etabs_c  = len(etabs_c)

    # ── KPIs COMMUNE ──────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">DONNÉES COMMUNALES</div>'
        '<h2 class="section-title">Ce qu\'on sait '
        '<em>à l\'échelle de la commune.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi_card(
            "Prix médian /m²",
            f"{prix_m2:.0f}\u202f€" if prix_m2 and pd.notna(prix_m2) else "—",
            "Source DVF 2025" if prix_m2 else "Non disponible",
        )
    with c2:
        render_kpi_card(
            "Temps d'accès médical",
            f"{temps_acces:.1f}\u202fmin" if temps_acces and pd.notna(temps_acces) else "—",
            "Vers établissement le + proche" if temps_acces else "Non disponible",
        )
    with c3:
        render_kpi_card(
            "Transactions 2025",
            str(nb_trans) if nb_trans else "—",
            "Ventes immobilières",
        )
    with c4:
        render_kpi_card(
            "Établissements sur place",
            str(nb_etabs_c),
            "Hôpitaux + cliniques FINESS",
        )

    # ── ÉTABLISSEMENTS DU DÉPARTEMENT ─────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">À PROXIMITÉ</div>'
        f'<h2 class="section-title">Établissements de santé '
        f'<em>dans {dept_name}.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    etabs_dept = etabs[etabs["code_departement"].astype(str).str.zfill(2) == dept_code]
    if not etabs_dept.empty:
        cols_to_show = [c for c in ["Rslongue", "categetab", "commune"]
                        if c in etabs_dept.columns]
        etabs_show = etabs_dept.head(15)[cols_to_show].copy()
        rename_map = {"Rslongue": "Établissement", "categetab": "Catégorie",
                      "commune": "Commune"}
        etabs_show = etabs_show.rename(columns=rename_map)
        st.dataframe(etabs_show, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune donnée sur les établissements de ce département.")

    # ── CTA VERS FICHE DÉPARTEMENT ────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">ALLER PLUS LOIN</div>'
        f'<h2 class="section-title">Le diagnostic complet '
        f'<em>du département.</em></h2>'
        '<p class="section-lead">Les indicateurs santé, les recommandations et '
        'les comparaisons sont disponibles à la maille départementale.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        f"Ouvrir la fiche de {dept_name} →",
        use_container_width=True,
        type="primary",
        key="go_to_dept",
    ):
        navigate("dept", dept_code=dept_code)
