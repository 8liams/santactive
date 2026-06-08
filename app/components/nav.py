"""Navigation interne — reste dans le même onglet (pas de liens HTML)."""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from ..router import View, navigate


@dataclass(frozen=True)
class NavCrumb:
    label: str
    view: View | None = None
    params: dict[str, str] = field(default_factory=dict)


def _crumb_key(prefix: str, crumb: NavCrumb, index: int) -> str:
    parts = [prefix, str(index)]
    if crumb.view:
        parts.append(crumb.view)
    for k in sorted(crumb.params):
        parts.append(f"{k}_{crumb.params[k]}")
    return "_".join(parts)


def render_breadcrumb(crumbs: list[NavCrumb], *, key_prefix: str = "bc") -> None:
    """Fil d'Ariane avec boutons Streamlit (navigation same-tab)."""
    if not crumbs:
        return

    st.markdown(
        '<div class="fiche-topbar"><div class="breadcrumb-nav">',
        unsafe_allow_html=True,
    )
    slots = st.columns(len(crumbs) * 2 - 1, gap="small")
    slot_idx = 0

    for i, crumb in enumerate(crumbs):
        with slots[slot_idx]:
            if crumb.view:
                if st.button(
                    crumb.label,
                    key=_crumb_key(key_prefix, crumb, i),
                    type="secondary",
                ):
                    navigate(crumb.view, **crumb.params)
            else:
                st.markdown(
                    f'<span class="breadcrumb-current">{crumb.label}</span>',
                    unsafe_allow_html=True,
                )
        slot_idx += 1

        if i < len(crumbs) - 1:
            with slots[slot_idx]:
                st.markdown(
                    '<span class="breadcrumb-sep">›</span>',
                    unsafe_allow_html=True,
                )
            slot_idx += 1

    st.markdown("</div></div>", unsafe_allow_html=True)


def dept_link_button(
    dept_code: str,
    label: str,
    *,
    key: str,
    use_container_width: bool = False,
) -> None:
    """Ouvre une fiche département sans quitter l'onglet."""
    code = str(dept_code).zfill(2)
    if st.button(
        label,
        key=key,
        type="secondary",
        use_container_width=use_container_width,
    ):
        navigate("dept", dept_code=code)


def render_mobile_nav(current_view: View, *, key_prefix: str = "mnav") -> None:
    """Barre de navigation mobile (boutons Streamlit, même onglet)."""
    items: list[tuple[View, str]] = [
        ("home", "Accueil"),
        ("enjeux", "Enjeux"),
        ("comparer", "Comparer"),
        ("methodologie", "Méthodo"),
        ("about", "À propos"),
    ]
    with st.container(key="sa_mobile_nav"):
        cols = st.columns(len(items), gap="small")
        for col, (view, label) in zip(cols, items):
            with col:
                if st.button(
                    label,
                    key=f"{key_prefix}_{view}",
                    use_container_width=True,
                    type="primary" if view == current_view else "secondary",
                ):
                    navigate(view)
