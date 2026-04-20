"""Composant : badges de zone (Critique / Intermédiaire / Favorable)."""

from __future__ import annotations


def zone_badge_html(zone: str) -> str:
    """Retourne le HTML d'un badge coloré pour la zone donnée."""
    cls = {
        "Critique":              "critique",
        "Intermédiaire":         "intermediaire",
        "Favorable":             "favorable",
        "Données insuffisantes": "donnees-insuffisantes",
    }.get(zone, "")
    return f'<span class="zone-badge {cls}">{zone}</span>'
