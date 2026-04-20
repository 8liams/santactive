"""Composant : alertes (info / warning / ok / critical)."""

from __future__ import annotations

import streamlit as st

VALID_KINDS = {"info", "warning", "ok", "critical"}


def render_alert(message: str, kind: str = "info") -> None:
    """Affiche une alerte stylée DSFR.

    Args:
        message: contenu HTML autorisé (ex. `<strong>Titre</strong><br>...`).
        kind: "info" (bleu), "warning" (ambre), "ok" (vert), "critical" (rouge).
    """
    if kind not in VALID_KINDS:
        kind = "info"
    st.markdown(
        f'<div class="alert-box alert-{kind}">{message}</div>',
        unsafe_allow_html=True,
    )
