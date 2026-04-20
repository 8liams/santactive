"""Page Enjeux — Pourquoi Sant'active existe."""
from __future__ import annotations

import streamlit as st


def render(data: dict) -> None:

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">CONTEXTE</div>'
        '<h2 class="section-title">Un probl\u00e8me r\u00e9el, <em>des donn\u00e9es pour agir.</em></h2>'
        '<p class="section-lead">'
        'La d\u00e9sertification m\u00e9dicale est une r\u00e9alit\u00e9 document\u00e9e. '
        'Sant\u2019active transforme des donn\u00e9es ouvertes officielles '
        'en diagnostics actionnables pour ceux qui d\u00e9cident.'
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── CHIFFRES CLÉS ─────────────────────────────────────────────────────────
    chiffres_html = (
        '<div style="display:flex;gap:16px;flex-wrap:wrap;margin:32px 0;">'
        '<div style="flex:1;min-width:180px;padding:24px;background:white;'
        'border:1px solid #E8E6DD;border-top:3px solid #A51C30;border-radius:0 0 6px 6px;">'
        '<div style="font-size:36px;font-weight:300;color:#A51C30;letter-spacing:-0.02em;line-height:1;">87\u202f%</div>'
        '<div style="font-size:13px;font-weight:600;color:#0A1938;margin:8px 0 6px;">du territoire en d\u00e9sert m\u00e9dical</div>'
        '<div style="font-size:12px;color:#9C9A92;line-height:1.5;">Selon les crit\u00e8res APL de la DREES.<br>Source\u202f: AMF / Mutualit\u00e9 Fran\u00e7aise \u00b7 2023</div>'
        '</div>'
        '<div style="flex:1;min-width:180px;padding:24px;background:white;'
        'border:1px solid #E8E6DD;border-top:3px solid #A51C30;border-radius:0 0 6px 6px;">'
        '<div style="font-size:36px;font-weight:300;color:#A51C30;letter-spacing:-0.02em;line-height:1;">6,7\u202fM</div>'
        '<div style="font-size:13px;font-weight:600;color:#0A1938;margin:8px 0 6px;">de Fran\u00e7ais sans m\u00e9decin traitant</div>'
        '<div style="font-size:12px;color:#9C9A92;line-height:1.5;">Soit 11\u202f% de la population nationale.<br>Source\u202f: DREES \u00b7 janv. 2023</div>'
        '</div>'
        '<div style="flex:1;min-width:180px;padding:24px;background:white;'
        'border:1px solid #E8E6DD;border-top:3px solid #A51C30;border-radius:0 0 6px 6px;">'
        '<div style="font-size:36px;font-weight:300;color:#A51C30;letter-spacing:-0.02em;line-height:1;">52\u202fj</div>'
        '<div style="font-size:13px;font-weight:600;color:#0A1938;margin:8px 0 6px;">d\u2019attente chez l\u2019ophtalmologue</div>'
        '<div style="font-size:12px;color:#9C9A92;line-height:1.5;">D\u00e9lai m\u00e9dian national.<br>Source\u202f: DREES \u00b7 enqu\u00eate 2016-2017</div>'
        '</div>'
        '<div style="flex:1;min-width:180px;padding:24px;background:white;'
        'border:1px solid #E8E6DD;border-top:3px solid #A51C30;border-radius:0 0 6px 6px;">'
        '<div style="font-size:36px;font-weight:300;color:#A51C30;letter-spacing:-0.02em;line-height:1;">70</div>'
        '<div style="font-size:13px;font-weight:600;color:#0A1938;margin:8px 0 6px;">d\u00e9partements ont perdu des g\u00e9n\u00e9ralistes</div>'
        '<div style="font-size:12px;color:#9C9A92;line-height:1.5;">Entre 2020 et 2023. Le Cher\u202f: \u221210,25\u202f%.<br>Source\u202f: DREES \u00b7 RPPS 2023</div>'
        '</div>'
        '</div>'
        '<div style="max-width:720px;font-size:14px;line-height:1.8;color:#4B4B48;margin-bottom:48px;">'
        'Face \u00e0 ce constat, les d\u00e9cideurs \u2014 \u00e9lus locaux, directeurs d\u2019ARS, '
        'professionnels de sant\u00e9 souhaitant s\u2019installer \u2014 manquent d\u2019un outil '
        'qui <strong>croise ces donn\u00e9es de fa\u00e7on lisible et actionnable</strong>. '
        'Sant\u2019active r\u00e9pond \u00e0 ce manque.'
        '</div>'
    )
    st.markdown(chiffres_html, unsafe_allow_html=True)

    # ── CAS D'USAGE ───────────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">CAS D\u2019USAGE</div>'
        '<h2 class="section-title">Qui utilise Sant\u2019active, <em>et pour quoi faire.</em></h2>'
        '</div>',
        unsafe_allow_html=True,
    )

    cas_usages = [
        {
            "numero": "01",
            "profil": "Directeur d\u2019ARS",
            "usage": (
                "Identifier les d\u00e9partements prioritaires pour l\u2019allocation "
                "du Fonds d\u2019Intervention R\u00e9gional (FIR). Croiser l\u2019APL, "
                "le vieillissement et la densit\u00e9 d\u2019\u00e9tablissements pour "
                "hi\u00e9rarchiser les zones d\u2019intervention."
            ),
        },
        {
            "numero": "02",
            "profil": "\u00c9lu local \u2014 Maire ou Pr\u00e9sident de D\u00e9partement",
            "usage": (
                "Pr\u00e9parer un Plan Local d\u2019Urbanisme int\u00e9grant l\u2019acc\u00e8s aux "
                "soins. Identifier les communes les plus \u00e9loign\u00e9es d\u2019un "
                "\u00e9tablissement pour cibler l\u2019implantation d\u2019une maison de "
                "sant\u00e9 pluridisciplinaire."
            ),
        },
        {
            "numero": "03",
            "profil": "M\u00e9decin en fin d\u2019\u00e9tudes",
            "usage": (
                "Comparer les territoires pour choisir o\u00f9 s\u2019installer\u202f: "
                "croiser l\u2019APL (besoin r\u00e9el), le prix immobilier "
                "(co\u00fbt d\u2019installation) et les aides disponibles "
                "dans les zones sous-denses."
            ),
        },
        {
            "numero": "04",
            "profil": "Chercheur en sant\u00e9 publique",
            "usage": (
                "Disposer d\u2019un tableau de bord reproductible croisant "
                "sept sources open data officielles. Comparer des "
                "d\u00e9partements aux profils similaires pour analyser "
                "l\u2019impact des politiques d\u2019acc\u00e8s aux soins."
            ),
        },
    ]

    grid_html = (
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));'
        'gap:16px;margin-top:8px;margin-bottom:48px;">'
    )
    for c in cas_usages:
        grid_html += (
            '<div style="padding:24px;background:white;border:1px solid #E8E6DD;border-radius:6px;">'
            f'<div style="font-size:11px;font-weight:700;color:#9C9A92;letter-spacing:0.08em;margin-bottom:12px;">{c["numero"]}</div>'
            f'<div style="font-size:14px;font-weight:700;color:#0A1938;margin-bottom:10px;">{c["profil"]}</div>'
            f'<div style="font-size:13px;color:#4B4B48;line-height:1.7;">{c["usage"]}</div>'
            '</div>'
        )
    grid_html += "</div>"
    st.markdown(grid_html, unsafe_allow_html=True)

    # ── DIFFÉRENCIATION ───────────────────────────────────────────────────────
    def _row(bg: str, label: str, classique: str, santactive: str) -> str:
        return (
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;'
            f'padding:14px 20px;background:{bg};gap:0;">'
            f'<div style="font-size:13px;font-weight:600;color:#0A1938;">{label}</div>'
            f'<div style="font-size:13px;color:#9C9A92;">{classique}</div>'
            f'<div style="font-size:13px;color:#1A3D8F;font-weight:500;">{santactive}</div>'
            '</div>'
        )

    diff_html = (
        '<div class="section-header">'
        '<div class="section-eyebrow">DIFF\u00c9RENCIATION</div>'
        '<h2 class="section-title">Pourquoi Sant\u2019active <em>est diff\u00e9rent.</em></h2>'
        '</div>'
        '<div style="border:1px solid #E8E6DD;border-radius:6px;overflow:hidden;max-width:860px;margin-top:8px;">'
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;background:#0A1938;padding:14px 20px;gap:0;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.45);">ASPECT</div>'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:rgba(255,255,255,0.45);">APPROCHE CLASSIQUE</div>'
        '<div style="font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#F4C430;">SANT\u2019ACTIVE</div>'
        '</div>'
        + _row("white",   "Indicateur d\u2019acc\u00e8s",     "Densit\u00e9 m\u00e9dicale brute (RPPS)",  "APL ANCT 2023 \u00b7 pond\u00e9r\u00e9 par \u00e2ge et activit\u00e9 r\u00e9elle")
        + _row("#FAFAF8", "D\u00e9lais de RDV",               "Non disponible ou national uniquement",    "Proxy par d\u00e9partement via APL \u00d7 DREES \u00b7 transparent")
        + _row("white",   "Granularit\u00e9",                 "Nationale ou r\u00e9gionale",              "101 d\u00e9partements + carte des 35\u202f000 communes")
        + _row("#FAFAF8", "Recommandations",                  "Absentes ou g\u00e9n\u00e9riques",         "Adapt\u00e9es \u00e0 la typologie INSEE \u00b7 chiffr\u00e9es \u00b7 localis\u00e9es")
        + _row("white",   "Transparence",                     "Bo\u00eete noire",                         "Page m\u00e9thodologie \u00b7 sources dat\u00e9es \u00b7 limites assum\u00e9es")
        + '</div>'
    )
    st.markdown(diff_html, unsafe_allow_html=True)

    # ── CTA ───────────────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:48px;'>", unsafe_allow_html=True)
    if st.button("Explorer les donn\u00e9es \u2192", type="primary", key="enjeux_cta"):
        from ..router import navigate
        navigate("home")
    st.markdown("</div>", unsafe_allow_html=True)
