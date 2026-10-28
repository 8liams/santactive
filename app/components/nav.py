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


def render_topnav(current_view: View, master=None, *, with_search: bool = True) -> None:
    """Navigation principale unique : logo, liens, recherche globale.

    Ordinateur : barre horizontale (liens visibles, recherche à droite).
    Mobile : logo + menu dépliable (<details>, sans JavaScript), recherche en
    dessous. Les liens sont des URL internes (?view=…) : le routage et les
    liens directs restent inchangés."""
    if master is not None:
        _sync_territory_selector(master)   # avant les liens : ils portent le territoire à jour
    items = [("home", "Accueil"), ("exploration", "Prioriser"), ("comparer", "Comparer"),
             ("acces", "Accès routier"), ("methodologie", "Méthodologie"), ("about", "À propos")]
    links = "".join(
        f'<a class="sa-nav-link{" sa-nav-link--active" if v == current_view else ""}" '
        f'href="{internal_href(v)}" target="_self"{_cur(v == current_view)}>{label}</a>'
        for v, label in items
    )
    brand = (
        f'<a class="sa-nav-brand" href="{internal_href("home")}" target="_self" aria-label="Sant\u2019active, accueil">'
        '<img src="app/static/brand/logo-santactive-mark.png" alt="" width="30" height="26">'
        '<span>Sant\u2019active</span></a>'
    )
    with st.container(key="sa_topnav"):
        if with_search and master is not None:
            c1, c3, c2 = st.columns([2.05, 0.95, 0.95], gap="small", vertical_alignment="center")
        else:
            c1, c2, c3 = st.container(), None, None
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
        if c3 is not None:
            with c3:
                render_territory_selector(master)
        if c2 is not None:
            from .search_box import render_search_box
            with c2:
                render_search_box(master, key="sa_nav_search", variant="nav",
                                  placeholder="Rechercher un territoire…")


_SEL_KEY, _SEL_LAST = "sa_territoire_sel", "_sa_territoire_affiche"


def _sync_territory_selector(master) -> None:
    """Applique un changement du sélecteur (avant tout rendu) ou l'aligne sur le territoire."""
    from .. import territoire as T

    valid = {v for v, _ in T.options(master)}
    current = T.get().param if T.get().param in valid else "fr"
    widget_val = st.session_state.get(_SEL_KEY)
    last = st.session_state.get(_SEL_LAST)
    if widget_val is not None and last is not None and widget_val != last:
        # L'utilisateur a changé le sélecteur : le territoire suit (page conservée)
        T.set_territoire(T.parse(widget_val) or T.FRANCE)
        current = T.get().param
    elif widget_val != current:
        # Le territoire a changé ailleurs (fiche ouverte, lien direct) : le sélecteur suit
        st.session_state[_SEL_KEY] = current
    st.session_state[_SEL_LAST] = current


def render_territory_selector(master) -> None:
    """Sélecteur du territoire de référence (France, région, département).

    Un changement conserve la page courante : chaque page relit le territoire
    (pré-sélection, mise en évidence). Ouvrir une fiche fait suivre le
    sélecteur (voir app/territoire.py)."""
    from .. import territoire as T

    opts = T.options(master)
    values = [v for v, _ in opts]
    labels = dict(opts)
    st.selectbox("Territoire de référence", values, format_func=lambda v: labels.get(v, v),
                 key=_SEL_KEY, label_visibility="collapsed",
                 help="Territoire de référence : conservé d'une page à l'autre (accueil, Prioriser, "
                      "Comparer, Accès routier). France entière pour revenir au national.")
