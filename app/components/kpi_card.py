"""Composant : carte KPI DSFR (chiffre en light weight, label capitalisé)."""

from __future__ import annotations

import streamlit as st


def render_kpi_card(
    label: str,
    value: str,
    comparison: str | None = None,
    direction: str | None = None,
) -> None:
    """Affiche une carte KPI stylée.

    Args:
        label: intitulé court (11px, uppercase).
        value: valeur principale déjà formatée (2.5rem, light weight).
        comparison: texte secondaire optionnel (ex. "+3.2 % vs national").
        direction: "up" (vert) ou "down" (rouge) pour colorer la comparaison.
    """
    comp_html = ""
    if comparison:
        cls = f"kpi-comparison {direction or ''}".strip()
        comp_html = f'<div class="{cls}">{comparison}</div>'
    st.markdown(
        f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {comp_html}
    </div>
    """,
        unsafe_allow_html=True,
    )
