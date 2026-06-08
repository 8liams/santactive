"""Composants UI réutilisables (design DSFR)."""

from .alerts import render_alert
from .badges import zone_badge_html
from .kpi_card import render_kpi_card
from .maps import render_commune_choropleth, render_national_choropleth
from .nav import NavCrumb, dept_link_button, render_breadcrumb, render_mobile_nav
from .delais import compute_delais_proxy, load_delais_nationaux, is_desert_medical
from .share_bar import (
    dept_share_context,
    region_share_context,
    render_fiche_share_bar,
)
from .tooltip import info_tooltip, TOOLTIPS

__all__ = [
    "render_alert",
    "render_kpi_card",
    "zone_badge_html",
    "render_national_choropleth",
    "render_commune_choropleth",
    "NavCrumb",
    "render_breadcrumb",
    "render_mobile_nav",
    "dept_link_button",
    "compute_delais_proxy",
    "load_delais_nationaux",
    "is_desert_medical",
    "info_tooltip",
    "TOOLTIPS",
    "render_fiche_share_bar",
    "dept_share_context",
    "region_share_context",
]
