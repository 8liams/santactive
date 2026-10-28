"""Recherche territoriale : composant Streamlit maison (app/components/search_frontend).

Pourquoi un composant maison : `streamlit-searchbox` affiche ses suggestions
dans le flux de la page (la carte est poussée vers le bas) et déclenche un
aller-retour serveur à chaque frappe. Ici :

- l'index (régions, départements, communes) est chargé une fois par le
  navigateur depuis /app/static/data/index_recherche.json (fichier généré par
  scripts/donnees/generer_index_recherche.py, servi par Streamlit) ;
- les suggestions s'affichent dans un menu flottant sous le champ, sans
  déplacer la mise en page (l'iframe est positionnée en absolu et ne grandit
  que lorsque le menu est ouvert) ;
- classement par pertinence (même règle que app/search.py : exact 100, préfixe
  95, début de mot 85, contenu 70 ; les communes −10), 7 résultats maximum,
  navigation au clavier, fermeture à la sélection, à Échap ou au clic
  extérieur ;
- aucun rerun pendant la frappe : seule la sélection renvoie une valeur à
  Python, qui navigue (router.navigate). Une iframe ne peut pas naviguer la
  page elle-même (bac à sable Streamlit), d'où le protocole de composant.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ..router import navigate

_CLOSED_HEIGHT = {"hero": 56, "nav": 40}
_FRONTEND = Path(__file__).resolve().parent / "search_frontend"
_component = components.declare_component("sa_search", path=str(_FRONTEND))


def render_search_box(master: pd.DataFrame | None = None, *, key: str, variant: str = "hero",
                      placeholder: str = "Département, région ou commune…") -> None:
    """Affiche le champ de recherche ; navigue vers le territoire choisi.

    `variant` : "hero" (accueil) ou "nav" (barre de navigation). `master`
    n'est plus nécessaire (index statique) ; conservé pour la signature."""
    del master
    closed = _CLOSED_HEIGHT.get(variant, 48)
    st.markdown(
        f"<style>.st-key-{key}{{position:relative;height:{closed}px;min-height:{closed}px;"
        f"flex:0 0 {closed}px;z-index:60;}}"
        f".st-key-{key}>div{{position:absolute;top:0;left:0;right:0;}}"
        f".st-key-{key} iframe{{display:block;width:100%;}}</style>",
        unsafe_allow_html=True,
    )
    with st.container(key=key):
        value = _component(variant=variant, placeholder=placeholder, closed=closed, key=f"{key}_cmp", default=None)

    if not isinstance(value, dict) or not value.get("level"):
        return
    # La valeur du composant persiste d'un rerun à l'autre : ne naviguer qu'une fois par sélection.
    handled = st.session_state.setdefault("_search_handled", {})
    stamp = (value.get("code"), value.get("t"))
    if handled.get(key) == stamp:
        return
    handled[key] = stamp
    level, code = value["level"], str(value.get("code", ""))
    if level == "departement":
        navigate("dept", dept_code=code)
    elif level == "region":
        navigate("region", region_code=code)
    elif level == "commune":
        navigate("commune", commune_code=code)
