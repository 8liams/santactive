"""Routing applicatif : détermine quelle page afficher."""

from __future__ import annotations

from typing import Literal

import streamlit as st

View = Literal["home", "dept", "region", "commune", "comparer", "methodologie", "about", "enjeux"]

_TERRITORY_PARAMS = ("dept_code", "region_code", "commune_code")


def get_current_view() -> View:
    return st.session_state.get("view", "home")


def _qp_first(value: object) -> str | None:
    """Extrait une valeur scalaire depuis st.query_params (parfois list)."""
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _set_query_params(view: View, params: dict[str, str]) -> None:
    """Remplace entièrement les query params (évite les clés territoriales résiduelles)."""
    qp: dict[str, str] = {"view": view, **params}
    if hasattr(st.query_params, "from_dict"):
        st.query_params.from_dict(qp)
        return
    for key in list(st.query_params.keys()):
        del st.query_params[key]
    st.query_params.update(qp)


def navigate(view: View, **params) -> None:
    """Change de vue et passe des paramètres.

    Usage:
        navigate("dept", dept_code="02")
        navigate("region", region_code="32")
    """
    str_params = {k: str(v) for k, v in params.items()}

    st.session_state["view"] = view
    for key in _TERRITORY_PARAMS:
        if key not in str_params:
            st.session_state.pop(key, None)
    for k, v in str_params.items():
        st.session_state[k] = v

    _set_query_params(view, str_params)
    st.rerun()


def navigate_compare(*dept_codes: str) -> None:
    """Ouvre la comparaison avec 2 à 4 départements pré-sélectionnés."""
    codes = [str(c).zfill(2) for c in dept_codes if c]
    if not codes:
        navigate("comparer")
        return
    st.session_state["comparer_territory_kind"] = "dept"
    st.session_state["comparer_preselect"] = codes
    navigate("comparer")


def init_from_url() -> None:
    """Synchronise l'état depuis l'URL à chaque chargement."""
    qp = dict(st.query_params)
    view = _qp_first(qp.get("view"))
    if view:
        st.session_state["view"] = view
    for k in _TERRITORY_PARAMS:
        val = _qp_first(qp.get(k))
        if val:
            st.session_state[k] = val
        else:
            st.session_state.pop(k, None)
