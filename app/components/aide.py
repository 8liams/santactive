"""Lien d'aide méthodologique « ? Comprendre cette analyse ».

Chaque page d'analyse renvoie à la section correspondante de la Méthodologie grâce à une ancre
(``?view=methodologie#score`` par exemple). Les identifiants d'ancre sont définis une seule fois ici
et repris par la page Méthodologie.
"""
from __future__ import annotations

from .nav import internal_href

# Ancre → libellé court (utilisé par la Méthodologie pour son sommaire)
SECTIONS: dict[str, str] = {
    "score": "Le score Sant’active",
    "prioriser": "Prioriser",
    "diagnostic": "Diagnostic",
    "comparer": "Comparer",
    "simuler": "Simuler",
    "sources": "Sources",
    "limites": "Limites",
}


def aide_methodo(section: str, libelle: str = "Comprendre cette analyse") -> str:
    """HTML d'un lien discret vers la section ``section`` de la Méthodologie."""
    if section not in SECTIONS:
        section = "score"
    href = internal_href("methodologie") + f"#{section}"
    return (f'<a class="sa-aide" href="{href}" target="_self" aria-label="{libelle} : méthodologie">'
            f'<span class="sa-aide-icon" aria-hidden="true">?</span><span>{libelle}</span></a>')
