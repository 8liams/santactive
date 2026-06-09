"""Routing applicatif : détermine quelle page afficher."""

from __future__ import annotations

from typing import Literal

import streamlit as st

View = Literal["home", "dept", "region", "commune", "comparer", "methodologie", "about", "enjeux"]

_TERRITORY_PARAMS = ("dept_code", "region_code", "commune_code")
_NAV_LOCK_KEY = "_nav_programmatic"


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


def _session_territory_params() -> dict[str, str]:
    return {
        k: str(st.session_state[k])
        for k in _TERRITORY_PARAMS
        if st.session_state.get(k) not in (None, "")
    }


def _url_matches_session(view: View, params: dict[str, str]) -> bool:
    qp = dict(st.query_params)
    if _qp_first(qp.get("view")) != view:
        return False
    for k in _TERRITORY_PARAMS:
        in_url = _qp_first(qp.get(k))
        in_sess = params.get(k)
        if in_url != in_sess:
            return False
    return True


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

    st.session_state[_NAV_LOCK_KEY] = True
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
    """Synchronise session ↔ URL (liens HTML ou navigation programmatique)."""
    qp = dict(st.query_params)
    url_view = _qp_first(qp.get("view"))

    if st.session_state.pop(_NAV_LOCK_KEY, None):
        view: View = st.session_state.get("view", "home")  # type: ignore[assignment]
        params = _session_territory_params()
        if not _url_matches_session(view, params):
            _set_query_params(view, params)
        return

    if "view" not in st.session_state:
        st.session_state["view"] = url_view or "home"
        for k in _TERRITORY_PARAMS:
            val = _qp_first(qp.get(k))
            if val:
                st.session_state[k] = val
        return

    if url_view and url_view != st.session_state.get("view"):
        st.session_state["view"] = url_view
    for k in _TERRITORY_PARAMS:
        val = _qp_first(qp.get(k))
        if val:
            st.session_state[k] = val
        else:
            st.session_state.pop(k, None)
