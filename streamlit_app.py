"""Sant'active — orchestrateur principal."""

from __future__ import annotations

import base64
import re
import warnings
from pathlib import Path

import streamlit as st

from app.data_loading import load_all_data, load_drees_ps, load_geojson
from app.pages import (
    about,
    acces_ign,
    exploration,
    comparer,
    enjeux,
    fiche_commune,
    fiche_departement,
    fiche_region,
    home,
    methodologie,
)  # noqa: E402  (importés après set_page_config)
from app.components.nav import render_topnav
from app.router import get_current_view, init_from_url, navigate
from app.scoring import compute_scores

warnings.filterwarnings("ignore")

STATIC_DIR = Path(__file__).parent / "static"


def _get_image_b64(path: str) -> str:
    """Convertit une image en base64 pour injection HTML inline.

    Streamlit ne gère pas bien les PNG transparents dans st.image()
    sur fond sombre. L'injection HTML inline via base64 contourne
    ce problème et permet de contrôler les styles CSS.
    """
    p = Path(path)
    if not p.exists():
        return ""
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
# Favicon : version fond blanc (le PNG original a un fond noir)
_favicon_path = STATIC_DIR / "brand" / "logo-santactive-favicon.png"
_logo_path    = STATIC_DIR / "brand" / "logo-santactive.png"
_page_icon    = str(_favicon_path) if _favicon_path.exists() else (
                str(_logo_path) if _logo_path.exists() else "🏥")
st.set_page_config(
    page_title="Sant'active",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="collapsed",  # navigation supérieure ; panneau latéral = recherche et navigation
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Sant'active · Outil d'aide à la décision territoriale en santé.",
    },
)

st.markdown("""
<style>
/* ─── HEADER : transparent ───────────────────────────────────────────────── */
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
}

/* ─── PANNEAU LATÉRAL : supprimé (navigation supérieure unique) ──────────── */
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] { display: none !important; width: 0 !important; }

/* ─── RESTE ──────────────────────────────────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.block-container { padding-top: 0.25rem !important; max-width: 100% !important; }
</style>
""", unsafe_allow_html=True)


# ─── CSS ──────────────────────────────────────────────────────────────────────
def _inline_fonts(css: str) -> str:
    pattern = re.compile(r"url\(['\"]?\./fonts/marianne/([^'\")]+)['\"]?\)")

    def _sub(match: re.Match) -> str:
        fname = match.group(1)
        font_path = STATIC_DIR / "fonts" / "marianne" / fname
        if not font_path.exists():
            return match.group(0)
        b64 = base64.b64encode(font_path.read_bytes()).decode("ascii")
        return f"url(data:font/woff2;base64,{b64}) format('woff2')"

    return pattern.sub(_sub, css)


def load_css(path: Path) -> None:
    if not path.exists():
        return
    css = _inline_fonts(path.read_text(encoding="utf-8"))
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


load_css(STATIC_DIR / "style.css")

# ─── DATA ─────────────────────────────────────────────────────────────────────
try:
    master, pros, immo, etabs, temps, env, patho, delais, presence = load_all_data()
    master = compute_scores(master)
except (KeyError, FileNotFoundError, ValueError) as exc:
    st.error(
        "Impossible de charger les données (fichier ou configuration du moteur). "
        f"Détail technique : `{exc}`."
    )
    st.stop()
except Exception as exc:
    st.error(
        "Impossible de charger les données depuis Google Drive. "
        "Rechargez la page dans quelques instants."
    )
    st.exception(exc)
    st.stop()

geojson = load_geojson()

# ─── ROUTING — init depuis URL ─────────────────────────────────────────────────
init_from_url()
view = get_current_view()

# Territoire de référence : une fiche ouverte devient le contexte avant même
# l'affichage de la barre (le sélecteur la reflète dès ce rendu).
from app import territoire as _T
if view == "dept" and st.session_state.get("dept_code") and (master["dept"] == str(st.session_state["dept_code"])).any():
    _T.follow_dept(str(st.session_state["dept_code"]))
elif view == "region" and st.session_state.get("region_code"):
    _T.follow_region(str(st.session_state["region_code"]))
elif view == "commune" and st.session_state.get("dept_code"):
    _T.follow_dept(str(st.session_state["dept_code"]))

render_topnav(view, master, with_search=True)

# ─── CONTEXTE PARTAGÉ ─────────────────────────────────────────────────────────
data = {
    "master":  master,
    "pros":    pros,
    "immo":    immo,
    "etabs":   etabs,
    "temps":   temps,
    "env":     env,
    "patho":   patho,
    "delais":  delais,
    "geojson": geojson,
    "presence": presence,      # jeu B : présence locale des spécialités (fichier équipe)
    "drees": load_drees_ps(),  # jeu A : effectifs officiels DREES/RPPS (si présents)
}

# ─── ROUTING : afficher la bonne page ─────────────────────────────────────────
if view == "home":
    home.render(data)
elif view == "dept":
    fiche_departement.render(data)
elif view == "region":
    fiche_region.render(data)
elif view == "commune":
    fiche_commune.render(data)
elif view == "exploration":
    exploration.render(data)
elif view == "acces":
    acces_ign.render(data)
elif view == "methodologie":
    methodologie.render(data)
elif view == "about":
    about.render(data)
elif view == "enjeux":
    enjeux.render(data)
elif view == "comparer":
    comparer.render(data)
else:
    navigate("home")
