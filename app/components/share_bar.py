"""Barre de partage d'une fiche territoire : copier le lien, e-mail, PDF.

E-mail : lien ``mailto:`` ouvert par le client de messagerie de l'utilisateur
(Gmail, Apple Mail, Outlook…). Le corps est en texte brut, encodé en URL (les
clients n'acceptent pas de HTML dans un mailto) ; il est volontairement court
(les clients tronquent les corps au-delà de quelques milliers de caractères),
structuré en sections, et contient le lien direct vers la fiche publique.
Aucun envoi n'est déclenché par l'application : l'utilisateur relit et envoie.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ..config import APL_MILLESIME
from ..scoring import fmt_classement_national

BASE_URL = "https://santactive.streamlit.app"
_SIGNATURE = ("Sant'active · aide à la décision territoriale en santé\n"
              "Données publiques : DREES, INSEE, Assurance Maladie, FINESS, IGN · santactive.esdata@gmail.com")
_LIMITES = ("Lecture à garder en tête : les indicateurs décrivent l'offre et l'accessibilité géographique "
            "des soins (données publiques, millésimes 2021 à 2026) ; ils ne mesurent pas la disponibilité réelle "
            "des rendez-vous. Le score situe un département parmi les autres, il n'est pas une note de santé. "
            "Les leviers sont des pistes fondées sur des règles explicites, à instruire avec les acteurs locaux.")


def build_fiche_url(view: str, **params: str) -> str:
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    return f"{BASE_URL}/?view={view}&{qs}"


def build_mailto(subject: str, body: str) -> str:
    # RFC 6068 : sauts de ligne en CRLF (%0D%0A), acceptés par Gmail, Apple Mail, Thunderbird et Outlook.
    body_crlf = body.replace("\r\n", "\n").replace("\n", "\r\n")
    return f"mailto:?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body_crlf)}"


def _num(v) -> float:
    try:
        return float(v) if v is not None and pd.notna(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _fr(v: float, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


def _pct(v: float, dec: int = 1) -> str:
    return f"{v * 100:.{dec}f}".replace(".", ",") + " %"


def _entier(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", " ")


def _sens(val: float, ref: float, higher_good: bool) -> str:
    if pd.isna(val) or pd.isna(ref):
        return ""
    ecart = val - ref
    if abs(ecart) < 1e-9:
        return "au niveau de la médiane nationale"
    mieux = (ecart > 0) == higher_good
    return "au-dessus de la médiane nationale" if ecart > 0 else "sous la médiane nationale"


def dept_share_context(r: pd.Series, master: pd.DataFrame | None = None, recos: list[dict] | None = None) -> dict[str, str]:
    """URL, objet et corps d'e-mail pour une fiche département : situation, constats chiffrés,
    publics, leviers, lien, limites. Texte brut, sans jargon, environ 1 800 caractères."""
    nom = str(r.get("Nom du département", ""))
    code = str(r.get("dept", "")).zfill(2)
    region = str(r.get("Nom de la région", ""))
    score = _num(r.get("score_global")); rang = r.get("rang_national"); zone = str(r.get("zone_short", "")).lower()
    nb = int(_num(r.get("nb_classes"))) if pd.notna(_num(r.get("nb_classes"))) else 100
    classement = fmt_classement_national(rang, nb) if rang is not None and pd.notna(rang) else "N/D"
    apl = _num(r.get("apl_dept")); part15 = _num(r.get("acces_mg_part_sup_15")); pop15 = _num(r.get("acces_mg_pop_sup_15"))
    med = _num(r.get("med_gen_pour_100k")); p65 = _num(r.get("pct_plus_65")); part_apl = _num(r.get("part_pop_apl_inf_2_5"))
    pop = _num(r.get("population_num"))
    m = master
    apl_nat = _num(m["apl_dept"].median()) if m is not None else float("nan")
    med_nat = _num(m["med_gen_pour_100k"].median()) if m is not None else float("nan")
    p65_nat = _num(m["pct_plus_65"].median()) if m is not None else float("nan")
    part15_nat = _num(m["acces_mg_part_sup_15"].median()) if m is not None and "acces_mg_part_sup_15" in m else float("nan")

    lecture = {"critique": "parmi le tiers des départements les moins bien placés",
               "intermédiaire": "dans le tiers médian des départements",
               "favorable": "parmi le tiers des départements les mieux placés"}.get(zone, "")
    situation = (f"{nom} obtient un score Sant'active de {_fr(score)} sur 100 ({classement} sur {nb}), {lecture}. "
                 f"Ce score situe le département sur l'offre et l'accessibilité des soins de premier recours ; "
                 f"il ne mesure pas l'état de santé de la population.") if pd.notna(score) else f"{nom} : score non calculé (données insuffisantes)."

    constats = []
    if pd.notna(apl):
        c = f"Accessibilité aux généralistes (APL DREES {APL_MILLESIME}) : {_fr(apl, 2)} consultations par habitant et par an"
        if pd.notna(apl_nat):
            c += f", {_sens(apl, apl_nat, True)} ({_fr(apl_nat, 2)})"
        if pd.notna(part_apl) and pd.notna(pop):
            c += (f" ; {_entier(part_apl * pop)} habitants ({_pct(part_apl, 0)}) vivent dans une commune sous le repère de sous-densité 2,5"
                  if part_apl > 0 else " ; aucune commune sous le repère de sous-densité 2,5")
        constats.append(c + ".")
    if pd.notna(med):
        c = f"Densité : {_entier(med)} médecins généralistes pour 100 000 habitants (RPPS 2026)"
        if pd.notna(med_nat):
            c += f", médiane nationale {_entier(med_nat)}"
        constats.append(c + ".")
    if pd.notna(part15):
        c = f"Éloignement : {_pct(part15)} des habitants à plus de 15 minutes en voiture d'un généraliste (INSEE 2025)"
        if pd.notna(pop15):
            c += f", soit {_entier(pop15)} personnes"
        if pd.notna(part15_nat):
            c += f" ; médiane nationale {_pct(part15_nat)}"
        constats.append(c + ".")
    else:
        constats.append("Éloignement : temps d'accès INSEE non disponible pour ce département (hors champ de la base).")
    if pd.notna(p65):
        c = f"Population : {_pct(p65 / 100)} de 65 ans et plus (recensement 2021)"
        if pd.notna(p65_nat):
            c += f", médiane {_pct(p65_nat / 100)}"
        constats.append(c + ".")

    leviers_txt = ""
    publics = []
    if recos:
        lignes = []
        for x in recos[:4]:
            titre = str(x.get("title") or x.get("titre") or "").strip()
            pub = str(x.get("public") or "").strip()
            if pub and pub not in publics:
                publics.append(pub)
            if titre:
                lignes.append(f"- {titre}" + (f" (public : {pub.lower()})" if pub else ""))
        if lignes:
            leviers_txt = "\n".join(lignes)

    url = build_fiche_url("dept", dept_code=code)
    subject = f"Sant'active · {nom} ({code}) : diagnostic d'accès aux soins et pistes d'action"
    body = (
        f"Bonjour,\n\n"
        f"Je vous transmets le diagnostic Sant'active du département {nom} ({code}, {region}), établi à partir de "
        f"données publiques (DREES, INSEE, Assurance Maladie, FINESS).\n\n"
        f"SITUATION\n{situation}\n\n"
        f"CONSTATS\n" + "\n".join(f"- {c}" for c in constats[:4]) + "\n\n"
        + (f"PUBLICS À CONSIDÉRER\n" + ", ".join(publics[:4]) + ".\n\n" if publics else "")
        + (f"PISTES D'ACTION À ÉTUDIER\n{leviers_txt}\n\n" if leviers_txt else "")
        + f"DIAGNOSTIC COMPLET EN LIGNE\n{url}\n\n"
        f"{_LIMITES}\n\n"
        f"Bien cordialement,\n\n{_SIGNATURE}"
    )
    return {"fiche_url": url, "email_subject": subject, "email_body": body, "share_title": f"Partager la fiche · {nom}"}


def region_share_context(region_name: str, region_code: str, region_depts: pd.DataFrame, summary: dict[str, Any],
                         priorities: pd.DataFrame | None = None, leviers: list[dict] | None = None,
                         master: pd.DataFrame | None = None) -> dict[str, str]:
    """URL, objet et corps d'e-mail pour une fiche région : disparités, départements à examiner, leviers."""
    nb = len(region_depts)
    crit = region_depts[region_depts["zone_short"] == "Critique"].sort_values("score_global")
    fav = region_depts[region_depts["zone_short"] == "Favorable"]
    pop = _num(region_depts["population_num"].sum())
    apl = pd.to_numeric(region_depts["apl_dept"], errors="coerce")
    part15 = pd.to_numeric(region_depts.get("acces_mg_part_sup_15"), errors="coerce") if "acces_mg_part_sup_15" in region_depts else pd.Series(dtype=float)
    pop15 = pd.to_numeric(region_depts.get("acces_mg_pop_sup_15"), errors="coerce") if "acces_mg_pop_sup_15" in region_depts else pd.Series(dtype=float)
    part_apl = pd.to_numeric(region_depts.get("part_pop_apl_inf_2_5"), errors="coerce")
    sc = pd.to_numeric(region_depts["score_global"], errors="coerce")
    noms = region_depts.set_index("dept")["Nom du département"]

    situation = (f"{region_name} compte {nb} département{'s' if nb > 1 else ''} : {len(crit)} en zone critique"
                 + (f" ({', '.join(crit['Nom du département'].astype(str).head(4))})" if len(crit) else "")
                 + f", {len(fav)} en zone favorable ; scores de {_fr(sc.min())} à {_fr(sc.max())} sur 100.")
    constats = []
    if apl.notna().any():
        lo = region_depts.loc[apl.idxmin()]; hi = region_depts.loc[apl.idxmax()]
        constats.append(f"Accessibilité aux généralistes (APL DREES {APL_MILLESIME}) : de {_fr(apl.min(), 2)} ({lo['Nom du département']}) "
                        f"à {_fr(apl.max(), 2)} ({hi['Nom du département']}) consultations par habitant et par an"
                        + (f" ; {_entier((part_apl * pd.to_numeric(region_depts['population_num'], errors='coerce')).sum())} habitants vivent dans une commune sous le repère 2,5" if part_apl.notna().any() else "") + ".")
    if len(part15) and part15.notna().any():
        hi = region_depts.loc[part15.idxmax()]
        constats.append(f"Éloignement : {_entier(pop15.sum())} habitants à plus de 15 minutes en voiture d'un généraliste (INSEE 2025), "
                        f"jusqu'à {_pct(part15.max())} de la population ({hi['Nom du département']}).")
    tension = str(summary.get("tension_principale", "")).strip()
    if tension and not tension.startswith("Données insuffisantes"):
        constats.append(f"Problématique dominante identifiée : {tension[0].lower() + tension[1:] if tension else ''}.")

    prio_txt = ""
    if priorities is not None and not priorities.empty and "score_priorite" in priorities:
        top = priorities.sort_values("score_priorite", ascending=False).head(3)
        prio_txt = "\n".join(f"- {row['Nom du département']} : priorité {int(_num(row['score_priorite']))}/100, fragilité {row.get('fragilite', '')}"
                             for _, row in top.iterrows())
    lev_txt = ""
    if leviers:
        lignes = []
        for lev in leviers[:3]:
            t = str(lev.get("intitule") or lev.get("titre") or lev.get("title") or "").strip()
            d = ", ".join(lev.get("depts") or [])
            if t:
                lignes.append(f"- {t}" + (f" ({d})" if d else ""))
        lev_txt = "\n".join(lignes)

    url = build_fiche_url("region", region_code=str(region_code))
    subject = f"Sant'active · {region_name} : disparités d'accès aux soins et départements à examiner"
    body = (
        f"Bonjour,\n\n"
        f"Je vous transmets la synthèse régionale Sant'active de la région {region_name}, établie à partir de données publiques "
        f"(DREES, INSEE, Assurance Maladie, FINESS).\n\n"
        f"SITUATION\n{situation} Population : {_entier(pop)} habitants (recensement 2021).\n\n"
        f"CONSTATS\n" + "\n".join(f"- {c}" for c in constats[:3]) + "\n\n"
        + (f"DÉPARTEMENTS À EXAMINER EN PRIORITÉ\n{prio_txt}\n\n" if prio_txt else "")
        + (f"PISTES D'ACTION À ÉTUDIER\n{lev_txt}\n\n" if lev_txt else "")
        + f"SYNTHÈSE COMPLÈTE EN LIGNE\n{url}\n\n"
        f"{_LIMITES}\n\n"
        f"Bien cordialement,\n\n{_SIGNATURE}"
    )
    return {"fiche_url": url, "email_subject": subject, "email_body": body, "share_title": f"Partager la fiche · {region_name}"}


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
  <button id="copy-{key}" type="button" class="act" title="Copier l’adresse de cette fiche">
    <svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"/></svg>
    <span>Copier le lien</span></button>
  <a href={mailto_js} class="act" title="Ouvrir un e-mail prérempli dans votre messagerie (rien n’est envoyé automatiquement)">
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
    (copier le lien · e-mail · PDF · comparer)."""
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
                                   help="Télécharger le rapport territorial (PDF, 3 à 5 pages)")
            else:
                st.button("PDF indisponible", disabled=True, use_container_width=True,
                          help=pdf_error or "Génération impossible", key=f"{key_prefix}_pdf_na")
        if extra_col is not None:
            with cols[3]:
                extra_col()
