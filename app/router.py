"""Routing applicatif : détermine quelle page afficher."""

from __future__ import annotations

from typing import Literal

import streamlit as st

View = Literal["home", "dept", "region", "commune", "comparer", "methodologie", "about", "enjeux"]


def get_current_view() -> View:
    return st.session_state.get("view", "home")


def navigate(view: View, **params) -> None:
    """Change de vue et passe des paramètres.

    Usage:
        navigate("dept", dept_code="02")
        navigate("region", region_code="32")
    """
    st.session_state["view"] = view
    for k, v in params.items():
        st.session_state[k] = v
    # Mise à jour de l'URL (permalien partageable)
    st.query_params.update({"view": view, **params})
    st.rerun()


def init_from_url() -> None:
    """Initialise l'état depuis les query params à l'arrivée sur le site."""
    qp = dict(st.query_params)
    if "view" in qp and "view" not in st.session_state:
        st.session_state["view"] = qp["view"]
    for k in ["dept_code", "region_code", "commune_code"]:
        if k in qp and k not in st.session_state:
            st.session_state[k] = qp[k]
