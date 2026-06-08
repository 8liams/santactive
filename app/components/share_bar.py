"""Barre de partage fiche territoire — copie lien, e-mail, PDF."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ..scoring import fmt_rang_affichage

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
    apl       = r.get("apl_median_dept")
    nb_classes = int(r.get("nb_classes", 101) or 101)

    score_str = f"{float(score):.1f}/100" if score is not None and pd.notna(score) else "N/D"
    rang_aff  = fmt_rang_affichage(rang, nb_classes) if rang is not None and pd.notna(rang) else "N/D"
    rang_str  = f"{rang_aff}/{nb_classes}" if rang_aff != "N/D" else "N/D"
    apl_str   = f"{float(apl):.1f}/hab." if apl is not None and pd.notna(apl) else "N/D"

    fiche_url = build_fiche_url("dept", dept_code=dept_code)
    subject   = f"Sant'active — Fiche {dept_nom} ({dept_code})"
    body = (
        f"Bonjour,\n\n"
        f"Voici la fiche Sant'active du département {dept_nom} ({dept_code}).\n\n"
        f"Score global : {score_str}\n"
        f"Indice de fragilité nationale : {rang_str}\n"
        f"Zone : {zone}\n"
        f"APL médian : {apl_str}\n\n"
        f"Consulter la fiche complète :\n{fiche_url}\n\n"
        f"—\n"
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
    apl_med  = region_depts["apl_median_dept"].median()
    apl_str  = f"{float(apl_med):.1f}/hab." if pd.notna(apl_med) else "N/D"
    tension  = summary.get("tension_principale", "—")

    fiche_url = build_fiche_url("region", region_code=str(region_code))
    subject   = f"Sant'active — Pilotage régional {region_name}"
    body = (
        f"Bonjour,\n\n"
        f"Voici la fiche pilotage Sant'active pour la région {region_name}.\n\n"
        f"Départements : {nb_depts} · Zone critique : {nb_crit}\n"
        f"Population : {pop_str} hab.\n"
        f"APL médian : {apl_str}\n"
        f"Tension principale : {tension}\n\n"
        f"Consulter la fiche complète :\n{fiche_url}\n\n"
        f"—\n"
        f"Sant'active · Observatoire Santé Territorial\n"
        f"santactive.esdata@gmail.com"
    )
    return {
        "fiche_url": fiche_url,
        "email_subject": subject,
        "email_body": body,
        "share_title": f"Partager la fiche · {region_name}",
    }


def _render_copy_button(url: str, key: str) -> None:
    """Bouton copie via iframe (Streamlit bloque les <script> dans markdown)."""
    url_js = json.dumps(url)
    btn_id = f"copy-btn-{key}"
    components.html(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;">
<button id="{btn_id}" type="button" class="btn-share-copy">
  Copier le lien
</button>
<style>
  .btn-share-copy {{
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem 1rem;
    min-height: 2.5rem;
    background: #FFFFFF;
    color: #1A3D8F;
    border: 1.5px solid #1A3D8F;
    border-radius: 4px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    font-family: Marianne, Inter, -apple-system, sans-serif;
    transition: background 0.18s, color 0.18s, border-color 0.18s;
  }}
  .btn-share-copy:hover {{ background: #F3F2EC; }}
  .btn-share-copy.is-copied {{
    background: #1B5E3F;
    color: #FFFFFF;
    border-color: #1B5E3F;
  }}
</style>
<script>
(function() {{
  const btn = document.getElementById("{btn_id}");
  const url = {url_js};
  btn.addEventListener("click", function() {{
    const done = () => {{
      btn.textContent = "Lien copié !";
      btn.classList.add("is-copied");
      setTimeout(() => {{
        btn.textContent = "Copier le lien";
        btn.classList.remove("is-copied");
      }}, 2200);
    }};
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(url).then(done).catch(fallback);
    }} else {{
      fallback();
    }}
    function fallback() {{
      const ta = document.createElement("textarea");
      ta.value = url;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {{
        document.execCommand("copy");
        done();
      }} catch (e) {{
        btn.textContent = "Sélectionnez le lien ci-dessous";
      }}
      document.body.removeChild(ta);
    }}
  }});
}})();
</script>
</body></html>""",
        height=46,
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
) -> None:
    """Affiche la barre de partage (copie, e-mail, PDF)."""
    mailto = build_mailto(email_subject, email_body)

    st.markdown(
        f'<div class="fiche-share-bar">'
        f'<div class="fiche-share-header">'
        f'<span class="fiche-share-eyebrow">Partager</span>'
        f'<span class="fiche-share-title">{share_title}</span>'
        f'</div>'
        f'<p class="fiche-share-lead">Copiez le lien direct, envoyez un e-mail '
        f'prérempli ou téléchargez le rapport PDF.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    n_cols = 4 if extra_col is not None else 3
    widths = [1, 1, 1, 1] if n_cols == 4 else [1, 1, 1.2]
    cols = st.columns(widths)

    with cols[0]:
        _render_copy_button(fiche_url, key_prefix)

    with cols[1]:
        st.link_button(
            "Envoyer par e-mail",
            mailto,
            use_container_width=True,
            type="secondary",
        )

    with cols[2]:
        if pdf_bytes:
            st.download_button(
                label="Télécharger le PDF",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                use_container_width=True,
                type="primary",
                key=f"{key_prefix}_pdf",
            )
        elif pdf_error:
            st.button(
                "PDF indisponible",
                disabled=True,
                use_container_width=True,
                help=pdf_error,
                key=f"{key_prefix}_pdf_err",
            )
        else:
            st.button(
                "Télécharger le PDF",
                disabled=True,
                use_container_width=True,
                key=f"{key_prefix}_pdf_na",
            )

    if extra_col is not None and n_cols == 4:
        with cols[3]:
            extra_col()
