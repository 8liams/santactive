"""Fiche commune : vue resserrée. Données partielles assumées et annoncées."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..commune_opportunity import norm_commune_name
from ..components import render_kpi_card
from ..components.nav import NavCrumb, render_breadcrumb
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
    dept_name   = dept_row.iloc[0]["Nom du département"] if not dept_row.empty else "N/D"
    region_name = dept_row.iloc[0]["Nom de la région"]   if not dept_row.empty else "N/D"
    region_code = str(dept_row.iloc[0]["Code région"])    if not dept_row.empty else ""

    # ── TOPBAR ────────────────────────────────────────────────────────────────
    render_breadcrumb([
        NavCrumb("Accueil", "home"),
        NavCrumb(region_name, "region", {"region_code": region_code}),
        NavCrumb(dept_name, "dept", {"dept_code": dept_code}),
        NavCrumb(commune_name.title()),
    ], key_prefix=f"commune_bc_{dept_code}")

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
    # Rapprochement par libellé normalisé (accents, tirets, « Saint »/« St »)
    # dans le département : les sources n'ont pas de code INSEE commun.
    name_key = norm_commune_name(commune_name)

    def _match(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "commune" not in df.columns:
            return pd.DataFrame()
        d = df[df["code_departement"].astype(str).str.zfill(2) == dept_code]
        return d[d["commune"].map(norm_commune_name) == name_key]

    immo_c  = _match(immo)
    temps_c = _match(temps)
    etabs_c = _match(etabs)
    etabs_ok = not etabs.empty and "commune" in etabs.columns and (
        etabs["code_departement"].astype(str).str.zfill(2) == dept_code
    ).any()

    prix_m2     = immo_c["prix_m2"].median() if not immo_c.empty else float("nan")
    temps_acces = temps_c["temps_acces"].mean() if not temps_c.empty else float("nan")
    # Repère INSEE 2025 par commune (temps moyen en voiture vers le généraliste le plus proche),
    # apparié par le libellé normalisé via le référentiel API Géo du département.
    temps_insee, offre_insee = float("nan"), None
    try:
        from ..commune_opportunity import load_acces_insee_communes as _load_insee_communes
        ref = pd.read_csv("static/data/communes_population_geoapi.csv", dtype={"code_insee": str, "dept": str})
        ref = ref[ref["dept"].astype(str).str.zfill(2) == dept_code]
        codes = ref.loc[ref["nom"].map(norm_commune_name) == norm_commune_name(commune_name), "code_insee"].str.zfill(5).tolist()
        ins = _load_insee_communes()
        hit = ins[ins["code_insee"].isin(codes)]
        if len(hit) == 1:
            temps_insee = float(hit.iloc[0]["temps_acces"]); offre_insee = bool(hit.iloc[0]["offre_sur_place"])
    except Exception:
        pass
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
            f"{prix_m2:.0f}\u202f€" if pd.notna(prix_m2) else "N/D",
            (f"Source DVF 2025 · {nb_trans} vente{'s' if nb_trans > 1 else ''}"
             if pd.notna(prix_m2) else "Non disponible"),
        )
    with c2:
        if pd.notna(temps_insee):
            render_kpi_card(
                "Temps vers un généraliste",
                f"{temps_insee:.0f}\u202fmin",
                ("généraliste présent dans la commune · " if offre_insee else "") + "moyenne des habitants, voiture · INSEE 2025",
            )
        else:
            render_kpi_card(
                "Temps d'accès (indicateur interne)",
                f"{temps_acces:.0f}\u202fmin" if pd.notna(temps_acces) else "N/D",
                "0 = généraliste présent dans la commune" if pd.notna(temps_acces) else "Non disponible",
            )
    with c3:
        render_kpi_card(
            "Transactions 2025",
            str(nb_trans) if nb_trans else "Aucune (ou commune non rapprochée)",
            "Ventes immobilières",
        )
    with c4:
        render_kpi_card(
            "Établissements FINESS",
            str(nb_etabs_c) if etabs_ok else "N/D",
            "Recensés dans la commune" if etabs_ok
            else "Non disponible pour ce département",
        )

    # ── ÉTABLISSEMENTS DU DÉPARTEMENT ─────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">DANS LE DÉPARTEMENT</div>'
        f'<h2 class="section-title">Établissements de santé '
        f'<em>dans {dept_name}.</em></h2>'
        '<p class="section-lead">Extrait du fichier FINESS chargé (commune '
        'sélectionnée en premier). Aucune notion de distance : le fichier ne '
        'contient pas de coordonnées.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    etabs_dept = etabs[etabs["code_departement"].astype(str).str.zfill(2) == dept_code]
    if not etabs_dept.empty:
        cols_to_show = [c for c in ["Rslongue", "categetab", "commune"]
                        if c in etabs_dept.columns]
        if "commune" in etabs_dept.columns:
            same = etabs_dept["commune"].map(norm_commune_name) == name_key
            etabs_dept = pd.concat([etabs_dept[same], etabs_dept[~same]])
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
