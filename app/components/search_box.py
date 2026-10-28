"""Contrôle territorial : composant Streamlit maison (app/components/search_frontend).

Pourquoi un composant maison : `streamlit-searchbox` affiche ses suggestions
dans le flux de la page (la carte est poussée vers le bas) et déclenche un
aller-retour serveur à chaque frappe. Ici :

- l'index (régions, départements, communes) est chargé une fois par le
  navigateur depuis /app/static/data/index_recherche.json (fichier généré par
  scripts/donnees/generer_index_recherche.py, servi par Streamlit) ;
- le menu s'ouvre au clic, même sans saisie (exploration par catégories :
  régions, départements, communes, rendues progressivement au défilement) ;
  la saisie filtre en direct, le clavier navigue, Échap ferme ;
- le menu flotte sous le champ sans déplacer la mise en page (l'iframe est
  positionnée en absolu et ne grandit que lorsque le menu est ouvert) ;
- aucun rerun pendant la frappe : seule la sélection renvoie une valeur à
  Python. Une iframe ne peut pas naviguer la page elle-même (bac à sable
  Streamlit), d'où le protocole de composant.

Variante « territoire » (barre) : affiche le territoire choisi sous forme
d'étiquette supprimable (« Bretagne × »). Sélectionner un territoire change le
territoire de référence **sans quitter la page** : Accueil reste Accueil,
Prioriser reste Prioriser… Seule une page de diagnostic (fiche) suit le nouveau
territoire, puisqu'elle est le diagnostic de ce territoire.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ..router import navigate

_CLOSED_HEIGHT = {"hero": 56, "nav": 40, "territoire": 48}
_FRONTEND = Path(__file__).resolve().parent / "search_frontend"
_component = components.declare_component("sa_search", path=str(_FRONTEND))
_FICHES = ("dept", "region", "commune", "diagnostic")


def _ouvrir_fiche(t) -> None:
    """Page de diagnostic du territoire exact (fiche commune, département, région, ou synthèse nationale)."""
    if t.kind == "commune":
        navigate("commune", commune_code=t.code)
    elif t.kind == "dept":
        navigate("dept", dept_code=t.code)
    elif t.kind == "region":
        navigate("region", region_code=t.code)
    else:
        navigate("diagnostic")


def appliquer_selection(level: str, code: str) -> None:
    """Met à jour le territoire de référence puis reste sur la page courante (une fiche suit le territoire)."""
    from .. import territoire as T
    from ..router import get_current_view

    if level == "departement":
        t = T.Territoire("dept", code.zfill(2))
    elif level == "region":
        t = T.Territoire("region", code)
    elif level == "commune" and "|" in code:
        nom, dept = code.split("|", 1)
        t = T.Territoire("commune", f"{nom}|{dept.zfill(2)}")
    else:
        t = T.FRANCE
    T.set_territoire(t)
    view = get_current_view()
    if view in _FICHES:
        _ouvrir_fiche(t)
    else:
        navigate(view)


def render_search_box(master: pd.DataFrame | None = None, *, key: str, variant: str = "hero",
                      placeholder: str = "Département, région ou commune…") -> None:
    """Affiche le champ de recherche ; applique le territoire choisi.

    `variant` : "hero" (accueil), "nav" (barre) ou "territoire" (contrôle unique
    de la barre : étiquette du territoire, recherche, exploration, réinitialisation)."""
    closed = _CLOSED_HEIGHT.get(variant, 48)
    st.markdown(
        f"<style>.st-key-{key}{{position:relative;height:{closed}px;min-height:{closed}px;"
        f"flex:0 0 {closed}px;z-index:60;}}"
        f".st-key-{key}>div{{position:absolute;top:0;left:0;right:0;}}"
        f".st-key-{key} iframe{{display:block;width:100%;}}</style>",
        unsafe_allow_html=True,
    )
    from .. import territoire as T

    t = T.get_exact()
    extra = {}
    if variant == "territoire":
        extra = {"current_param": t.param,
                 "current_label": T.label(t, master) if master is not None and not t.is_national else ""}
    with st.container(key=key):
        value = _component(variant=variant, placeholder=placeholder, closed=closed, key=f"{key}_cmp", default=None, **extra)

    if not isinstance(value, dict) or not value.get("level"):
        return
    # La valeur du composant persiste d'un rerun à l'autre : n'agir qu'une fois par sélection.
    handled = st.session_state.setdefault("_search_handled", {})
    stamp = (value.get("code"), value.get("t"))
    if handled.get(key) == stamp:
        return
    handled[key] = stamp
    level, code = value["level"], str(value.get("code", ""))
    if variant == "territoire":
        appliquer_selection(level, code)
        return
    # Variante accueil / barre simple : ouvrir la fiche du territoire choisi
    if level == "fr":
        T.set_territoire(T.FRANCE)
        navigate("home")
    elif level == "departement":
        T.set_territoire(T.Territoire("dept", code.zfill(2)))
        navigate("dept", dept_code=code)
    elif level == "region":
        T.set_territoire(T.Territoire("region", code))
        navigate("region", region_code=code)
    elif level == "commune":
        if "|" in code:
            nom, dept = code.split("|", 1)
            T.set_territoire(T.Territoire("commune", f"{nom}|{dept.zfill(2)}"))
        navigate("commune", commune_code=code)
