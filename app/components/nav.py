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
    """URL interne (?view=…) pour navigation same-tab via target=\"_self\".

    Chaque lien interne recharge la page (nouvelle session Streamlit) : le
    territoire de référence (paramètre ``t``) est donc ajouté à tous les liens
    lorsqu'il n'est pas « France entière », sauf s'il est déjà fourni."""
    qp = {"view": view, **params}
    if "t" not in qp:
        try:
            from .. import territoire as T
            t = T.get()
            if not t.is_national:
                qp["t"] = t.param
        except Exception:
            pass
    qs = urlencode(qp)
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


def _cur(active: bool) -> str:
    return ' aria-current="page"' if active else ""


def _diagnostic_href(master) -> str:
    """Entrée « Diagnostic » de la barre : fiche du département ou de la région de
    référence, synthèse nationale sinon."""
    from .. import territoire as T

    t = T.get()
    if t.kind == "dept":
        return internal_href("dept", dept_code=t.code)
    if t.kind == "region":
        return internal_href("region", region_code=t.code)
    return internal_href("diagnostic")


def render_topnav(current_view: View, master=None, *, with_search: bool = True) -> None:
    """Navigation principale unique : logo, liens, contrôle territorial (recherche + sélection).

    Ordinateur : barre horizontale. Mobile : logo + menu dépliable (<details>),
    contrôle territorial en dessous. Les liens sont des URL internes (?view=…)
    qui portent le territoire de référence."""
    items = [("home", "Accueil", internal_href("home")), ("exploration", "Prioriser", internal_href("exploration")),
             ("diagnostic", "Diagnostic", _diagnostic_href(master)), ("comparer", "Comparer", internal_href("comparer")),
             ("acces", "Simuler", internal_href("acces")), ("methodologie", "Méthodologie", internal_href("methodologie")),
             ("about", "À propos", internal_href("about"))]
    actif = "diagnostic" if current_view in ("dept", "region", "commune", "diagnostic") else current_view
    links = "".join(
        f'<a class="sa-nav-link{" sa-nav-link--active" if v == actif else ""}" '
        f'href="{href}" target="_self"{_cur(v == actif)}>{label}</a>'
        for v, label, href in items
    )
    brand = (
        f'<a class="sa-nav-brand" href="{internal_href("home")}" target="_self" aria-label="Sant\u2019active, accueil">'
        '<img src="app/static/brand/logo-santactive-mark.png" alt="" width="30" height="26">'
        '<span>Sant\u2019active</span></a>'
    )
    with st.container(key="sa_topnav"):
        if with_search and master is not None:
            c1, c2 = st.columns([2.3, 1.2], gap="small", vertical_alignment="center")
        else:
            c1, c2 = st.container(), None
        with c1:
            st.markdown(
                '<nav class="sa-nav" aria-label="Navigation principale">'
                + brand
                + f'<div class="sa-nav-links">{links}</div>'
                + '<details class="sa-nav-mobile"><summary aria-label="Menu">'
                '<span></span><span></span><span></span></summary>'
                f'<div class="sa-nav-mobile-links">{links}</div></details>'
                '</nav>',
                unsafe_allow_html=True,
            )
        if c2 is not None:
            from .search_box import render_search_box
            with c2:
                render_search_box(master, key="sa_territoire", variant="territoire",
                                  placeholder="France entière · rechercher un territoire")
