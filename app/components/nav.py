"""Navigation interne — fil d'Ariane et liens territoriaux en texte."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from urllib.parse import urlencode

import streamlit as st

from ..router import View


@dataclass(frozen=True)
class NavCrumb:
    label: str
    view: View | None = None
    params: dict[str, str] = field(default_factory=dict)


def internal_href(view: View, **params: str) -> str:
    """URL interne (?view=…) pour navigation same-tab via target=\"_self\"."""
    qs = urlencode({"view": view, **params})
    return f"?{qs}"


def dept_link_html(
    dept_code: str,
    label: str,
    *,
    css_class: str = "dept-table-link",
) -> str:
    """Lien HTML vers une fiche département (texte fin, pas bouton Streamlit)."""
    code = str(dept_code).zfill(2)
    href = internal_href("dept", dept_code=code)
    return (
        f'<a href="{href}" target="_self" class="{css_class}">'
        f"{html.escape(label)}</a>"
    )


def render_breadcrumb(crumbs: list[NavCrumb], *, key_prefix: str = "bc") -> None:
    """Fil d'Ariane en liens texte (pas de boutons Streamlit)."""
    del key_prefix  # conservé pour compatibilité des appels existants
    if not crumbs:
        return

    parts: list[str] = []
    for i, crumb in enumerate(crumbs):
        if crumb.view:
            href = internal_href(crumb.view, **crumb.params)
            parts.append(
                f'<a href="{href}" target="_self">{html.escape(crumb.label)}</a>'
            )
        else:
            parts.append(f'<span class="current">{html.escape(crumb.label)}</span>')
        if i < len(crumbs) - 1:
            parts.append('<span class="sep">›</span>')

    st.markdown(
        '<div class="fiche-topbar"><div class="breadcrumb">'
        + "".join(parts)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def render_sidebar_nav(
    current_view: View,
    items: list[tuple[str, View]],
    *,
    key_prefix: str = "snav",
) -> None:
    """Liens sidebar desktop — même mécanisme que le fil d'Ariane (href, pas st.button)."""
    del key_prefix
    links: list[str] = []
    for label, view in items:
        active = " sa-sidebar-nav-link--active" if view == current_view else ""
        href = internal_href(view)
        links.append(
            f'<a href="{href}" target="_self" class="sa-sidebar-nav-link{active}">'
            f"{html.escape(label)}</a>"
        )
    st.markdown(
        '<nav class="sa-sidebar-nav" aria-label="Navigation principale">'
        + "".join(links)
        + "</nav>",
        unsafe_allow_html=True,
    )


def render_mobile_nav(current_view: View, *, key_prefix: str = "mnav") -> None:
    """Bandeau mobile fixe — liens horizontaux (HTML, pas de colonnes Streamlit)."""
    del key_prefix
    items: list[tuple[View, str]] = [
        ("home", "Accueil"),
        ("comparer", "Comparaison"),
        ("enjeux", "À quoi ça sert ?"),
        ("methodologie", "Méthodologie"),
        ("about", "À propos"),
    ]
    links: list[str] = []
    for view, label in items:
        active = " sa-mnav-link--active" if view == current_view else ""
        href = internal_href(view)
        links.append(
            f'<a href="{href}" target="_self" class="sa-mnav-link{active}">'
            f"{html.escape(label)}</a>"
        )
    st.markdown(
        '<nav class="sa-mobile-nav" aria-label="Navigation principale">'
        + "".join(links)
        + "</nav>",
        unsafe_allow_html=True,
    )
