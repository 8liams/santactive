"""Sant'active — orchestrateur principal."""

from __future__ import annotations

import base64
import re
import warnings
from pathlib import Path

import streamlit as st

from app.data_loading import load_all_data, load_geojson
from app.pages import (
    about,
    comparer,
    enjeux,
    fiche_commune,
    fiche_departement,
    fiche_region,
    home,
    methodologie,
)  # noqa: E402  (importés après set_page_config)
from app.router import get_current_view, init_from_url, navigate
from app.scoring import compute_scores

warnings.filterwarnings("ignore")

STATIC_DIR = Path(__file__).parent / "static"

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
_logo_path = STATIC_DIR / "brand" / "logo-santactive.png"
st.set_page_config(
    page_title="Sant'active",
    page_icon=str(_logo_path) if _logo_path.exists() else "🏥",
    layout="wide",
    initial_sidebar_state="expanded",  # toujours ouverte (boutons collapse masqués)
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

/* ─── SIDEBAR TOUJOURS VISIBLE (force override du collapse Streamlit) ───── */
[data-testid="stSidebar"] {
    transform: none !important;
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    min-width: 245px !important;
    max-width: 245px !important;
    width: 245px !important;
    position: relative !important;
    z-index: 100 !important;
}
/* Masque les boutons ouvrir/fermer devenus inutiles */
[data-testid="stSidebarCollapseButton"]   { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }

/* ─── RESTE ──────────────────────────────────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
.block-container { padding-top: 1rem !important; max-width: 100% !important; }
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
master, pros, immo, etabs, temps, env, patho, delais = load_all_data()
master = compute_scores(master)
geojson = load_geojson()

# ─── ROUTING — init depuis URL ─────────────────────────────────────────────────
init_from_url()
view = get_current_view()

# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Brand block ──────────────────────────────────────────────────────────
    st.markdown(
        '<div style="text-align:center;padding-bottom:4px;">'
        '<span style="font-family:Marianne,Inter,sans-serif;'
        'font-size:18px;font-weight:700;color:#FFFFFF;letter-spacing:0.02em;">'
        "Sant'active"
        '</span><br>'
        '<span style="font-size:10px;color:rgba(255,255,255,0.45);'
        'letter-spacing:0.12em;text-transform:uppercase;">'
        "Observatoire santé territorial"
        '</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "<hr style='border:none;border-top:1px solid rgba(255,255,255,0.1);"
        "margin:16px 0 20px;'>",
        unsafe_allow_html=True,
    )

    # ── Navigation ───────────────────────────────────────────────────────────
    st.markdown(
        '<p style="font-size:10px;font-weight:700;letter-spacing:0.14em;'
        'color:rgba(255,255,255,0.4);text-transform:uppercase;margin:0 0 8px 4px;">'
        "Navigation</p>",
        unsafe_allow_html=True,
    )

    _nav = [
        ("Accueil",      "home",        "home"),
        ("Enjeux",       "enjeux",      "enjeux"),
        ("Comparaison",  "comparer",    "comparer"),
    ]
    for label, target, v_key in _nav:
        is_active = view == v_key
        if st.button(
            label,
            use_container_width=True,
            type="primary" if is_active else "secondary",
            key=f"nav_{v_key}",
        ):
            navigate(target)

    # ── Recherche rapide sidebar ──────────────────────────────────────────────
    st.sidebar.markdown(
        '<div style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        'text-transform:uppercase;color:rgba(255,255,255,0.35);'
        'margin:20px 0 6px;padding:0 4px;">RECHERCHE RAPIDE</div>',
        unsafe_allow_html=True,
    )
    sidebar_search = st.sidebar.text_input(
        "Rechercher",
        placeholder="D\u00e9partement, r\u00e9gion\u2026",
        key="sidebar_search_input",
        label_visibility="collapsed",
    )
    if sidebar_search and len(sidebar_search) >= 2:
        from app.search import search_territory
        _sb_results = search_territory(sidebar_search, master, limit=5)
        for _r in _sb_results:
            _lbl = _r.name
            if _r.level == "departement":
                _lbl += f" ({_r.code})"
            if st.sidebar.button(_lbl, key=f"sb_result_{_r.code}",
                                 use_container_width=True):
                if _r.level == "departement":
                    navigate("dept", dept_code=_r.code)
                elif _r.level == "region":
                    navigate("region", region_code=_r.code)

    st.markdown(
        '<p style="font-size:10px;font-weight:700;letter-spacing:0.14em;'
        'color:rgba(255,255,255,0.4);text-transform:uppercase;'
        'margin:20px 0 8px 4px;">'
        "Ressources</p>",
        unsafe_allow_html=True,
    )

    if st.button(
        "Méthodologie",
        use_container_width=True,
        type="primary" if view == "methodologie" else "secondary",
        key="nav_methodo",
    ):
        navigate("methodologie")

    if st.button(
        "À propos",
        use_container_width=True,
        type="primary" if view == "about" else "secondary",
        key="nav_about",
    ):
        navigate("about")

    # ── Footer ───────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="margin-top:40px;padding:14px 4px 0;">'
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);'
        'margin:0 0 10px;">'
        '<p style="font-size:10px;color:rgba(255,255,255,0.3);line-height:1.6;'
        'margin:0;">'
        "Sources&nbsp;: INSEE 2021 · RPPS 2026<br>"
        "FINESS 2026 · DVF 2025<br>"
        "ANSM · CNAM 2023 · DREES"
        "</p></div>",
        unsafe_allow_html=True,
    )

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
