"""Composants UI réutilisables (design DSFR)."""

from .alerts import render_alert
from .badges import zone_badge_html
from .kpi_card import render_kpi_card
from .maps import render_commune_choropleth, render_national_choropleth
from .delais import compute_delais_proxy, load_delais_nationaux, is_desert_medical
from .tooltip import info_tooltip, TOOLTIPS

__all__ = [
    "render_alert",
    "render_kpi_card",
    "zone_badge_html",
    "render_national_choropleth",
    "render_commune_choropleth",
    "compute_delais_proxy",
    "load_delais_nationaux",
    "is_desert_medical",
    "info_tooltip",
    "TOOLTIPS",
]
