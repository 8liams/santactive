"""Barre de partage fiche territoire — copie lien, e-mail, PDF."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ..config import APL_LABEL_COURT
from ..scoring import fmt_classement_national

BASE_URL = "https://santactive.streamlit.app"


def build_fiche_url(view: str, **params: str) -> str:
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    return f"{BASE_URL}/?view={view}&{qs}"


def build_mailto(subject: str, body: str) -> str:
    return (
        f"mailto:?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )


def dept_share_context(r: pd.Series) -> dict[str, str]:
    """Prépare URL, sujet et corps d'e-mail pour une fiche département."""
    dept_nom  = str(r.get("Nom du département", ""))
    dept_code = str(r.get("dept", "")).zfill(2)
    score     = r.get("score_global")
    rang      = r.get("rang_national")
    zone      = str(r.get("zone_short", ""))
    apl       = r.get("apl_dept")
    _nb = r.get("nb_classes")
    nb_classes = int(_nb) if _nb is not None and pd.notna(_nb) else 0

    score_str = f"{float(score):.1f}/100" if score is not None and pd.notna(score) else "N/D"
    classement = (
        fmt_classement_national(rang, nb_classes)
        if rang is not None and pd.notna(rang)
        else "N/D"
    )
    rang_str = f"{classement}/{nb_classes}" if classement != "N/D" else "N/D"
    apl_str   = f"{float(apl):.1f}/hab." if apl is not None and pd.notna(apl) else "N/D"

    fiche_url = build_fiche_url("dept", dept_code=dept_code)
    subject   = f"Sant'active · Fiche {dept_nom} ({dept_code})"
    body = (
        f"Bonjour,\n\n"
        f"Voici la fiche Sant'active du département {dept_nom} ({dept_code}).\n\n"
        f"Score global : {score_str}\n"
        f"Classement national : {rang_str}\n"
        f"Zone : {zone}\n"
        f"{APL_LABEL_COURT} : {apl_str}\n\n"
        f"Consulter la fiche complète :\n{fiche_url}\n\n"
        f"Sant'active · Observatoire Santé Territorial\n"
        f"santactive.esdata@gmail.com"
    )
    return {
        "fiche_url": fiche_url,
        "email_subject": subject,
        "email_body": body,
        "share_title": f"Partager la fiche · {dept_nom}",
    }


def region_share_context(
    region_name: str,
    region_code: str,
    region_depts: pd.DataFrame,
    summary: dict[str, Any],
) -> dict[str, str]:
    """Prépare URL, sujet et corps d'e-mail pour une fiche région."""
    nb_depts = len(region_depts)
    nb_crit  = int((region_depts["zone_short"] == "Critique").sum())
    pop_tot  = region_depts["population_num"].sum()
    pop_str  = f"{int(pop_tot):,}".replace(",", "\u202f") if pd.notna(pop_tot) else "N/D"
    apl_med  = region_depts["apl_dept"].median()
    apl_str  = f"{float(apl_med):.1f}/hab." if pd.notna(apl_med) else "N/D"
    tension  = summary.get("tension_principale", "N/D")

    fiche_url = build_fiche_url("region", region_code=str(region_code))
    subject   = f"Sant'active · Pilotage régional {region_name}"
    body = (
        f"Bonjour,\n\n"
        f"Voici la fiche pilotage Sant'active pour la région {region_name}.\n\n"
        f"Départements : {nb_depts} · Zone critique : {nb_crit}\n"
        f"Population : {pop_str} hab.\n"
        f"{APL_LABEL_COURT} : {apl_str}\n"
        f"Tension principale : {tension}\n\n"
        f"Consulter la fiche complète :\n{fiche_url}\n\n"
        f"Sant'active · Observatoire Santé Territorial\n"
        f"santactive.esdata@gmail.com"
    )
    return {
        "fiche_url": fiche_url,
        "email_subject": subject,
        "email_body": body,
        "share_title": f"Partager la fiche · {region_name}",
    }


def _render_actions_iframe(url: str, mailto: str, key: str) -> None:
    """Deux actions légères (copier le lien, e-mail) dans une seule iframe :
    Streamlit bloque les <script> dans st.markdown, et la copie exige du JS."""
    url_js = json.dumps(url)
    mailto_js = json.dumps(mailto)
    components.html(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;">
<div class="row">
  <button id="copy-{key}" type="button" class="act">
    <svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"/></svg>
    <span>Copier le lien</span></button>
  <a href={mailto_js} class="act">
    <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>
    <span>E-mail</span></a>
</div>
<style>
  .row {{ display:flex; gap:6px; height:34px; }}
  .act {{
    flex:1; display:inline-flex; align-items:center; justify-content:center; gap:6px;
    height:34px; padding:0 10px; box-sizing:border-box; white-space:nowrap;
    background:#fff; color:#1A3D8F; border:1px solid #C9C6BA; border-radius:5px;
    font-family: Marianne, Inter, -apple-system, sans-serif; font-size:12.5px; font-weight:600;
    text-decoration:none; cursor:pointer; transition: background .15s, border-color .15s, color .15s;
  }}
  .act svg {{ width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }}
  .act:hover {{ border-color:#1A3D8F; background:#F3F6FC; }}
  .act.ok {{ background:#1B5E3F; border-color:#1B5E3F; color:#fff; }}
</style>
<script>
(function() {{
  const btn = document.getElementById("copy-{key}");
  const url = {url_js};
  const label = btn.querySelector("span");
  const done = () => {{ label.textContent = "Lien copié"; btn.classList.add("ok");
    setTimeout(() => {{ label.textContent = "Copier le lien"; btn.classList.remove("ok"); }}, 2000); }};
  const fallback = () => {{
    const ta = document.createElement("textarea"); ta.value = url; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try {{ document.execCommand("copy"); done(); }} catch (e) {{ label.textContent = "Copie impossible"; }}
    document.body.removeChild(ta);
  }};
  btn.addEventListener("click", () => {{
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done).catch(fallback);
    else fallback();
  }});
}})();
</script>
</body></html>""",
        height=36,
    )


def render_fiche_share_bar(
    *,
    fiche_url: str,
    email_subject: str,
    email_body: str,
    share_title: str = "Partager cette fiche",
    pdf_bytes: bytes | None = None,
    pdf_filename: str = "santactive_rapport.pdf",
    pdf_error: str | None = None,
    extra_col: Any | None = None,
    key_prefix: str = "share",
    compact: bool = True,
    breadcrumb: Any | None = None,
) -> None:
    """Ligne d'actions discrète : fil d'Ariane à gauche, actions à droite
    (copier le lien · e-mail · PDF · comparer). `breadcrumb` est une fonction
    qui dessine le fil d'Ariane dans la première colonne."""
    del share_title, compact
    mailto = build_mailto(email_subject, email_body)
    widths = [4.2, 1.9, 1.35] + ([1.3] if extra_col is not None else [])

    with st.container(key="fiche_actions"):
        cols = st.columns(widths, gap="small", vertical_alignment="center")
        with cols[0]:
            if breadcrumb is not None:
                breadcrumb()
        with cols[1]:
            _render_actions_iframe(fiche_url, mailto, key_prefix)
        with cols[2]:
            if pdf_bytes:
                st.download_button(label="PDF", data=pdf_bytes, file_name=pdf_filename, mime="application/pdf",
                                   use_container_width=True, type="primary", key=f"{key_prefix}_pdf",
                                   help="Télécharger la fiche au format PDF")
            else:
                st.button("PDF indisponible", disabled=True, use_container_width=True,
                          help=pdf_error or "Génération impossible", key=f"{key_prefix}_pdf_na")
        if extra_col is not None:
            with cols[3]:
                extra_col()
