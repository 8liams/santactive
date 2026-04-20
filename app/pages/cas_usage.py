"""Cas d'usage — Wizards guidés (stub, sera complété au prompt 9)."""

from __future__ import annotations

import streamlit as st

from ..router import navigate


def render(data: dict) -> None:
    st.markdown("# Cas d'usage")
    st.info("Les wizards guidés arrivent à l'étape 9.")

    if st.button("← Retour accueil"):
        navigate("home")
