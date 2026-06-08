"""Synthèse vocale du diagnostic territorial (edge-tts)."""

from __future__ import annotations

import asyncio
import io
from typing import Callable

import pandas as pd
import streamlit as st

from .components.delais import APL_SEUIL_DESERT

_AUDIO_VOICE = "fr-FR-DeniseNeural"
_AUDIO_DISCLAIMER = (
    "Ces éléments constituent une aide à la décision "
    "et doivent être complétés par l'expertise locale."
)
_FEMININE_DEPTS = {
    "Manche", "Marne", "Meuse", "Sarthe", "Vienne", "Loire", "Drôme",
    "Savoie", "Corse", "Dordogne", "Charente", "Corrèze", "Creuse",
    "Haute-Loire", "Haute-Marne", "Haute-Saône", "Haute-Vienne",
    "Seine-Maritime", "Seine-et-Marne", "Indre",
}
_LEVER_SHORT_HINTS: list[tuple[str, str]] = [
    ("maison de santé", "l'offre de proximité"),
    ("télémédecine", "les solutions numériques"),
    ("seniors", "les solutions numériques pour les seniors"),
    ("attractivité", "l'attractivité médicale"),
    ("navettes", "les transports sanitaires"),
    ("prévention", "la prévention et le dépistage"),
    ("pédiatrique", "l'offre pédiatrique"),
    ("antennes", "le renforcement des antennes de soins"),
    ("vigilance", "un plan de vigilance territoriale"),
    ("bonnes pratiques", "le maintien des acquis"),
    ("coordination", "la coordination territoriale"),
    ("dépistage", "le dépistage ciblé"),
]


def _territory_label_for_speech(nom: str, *, kind: str = "dept") -> str:
    """Libellé oral « du Cher », « de l'Indre », « de Bretagne »…"""
    nom = nom.strip()
    if not nom:
        return "inconnu" if kind == "dept" else "inconnue"
    if kind == "region":
        if nom[0].upper() in "AEIOUY":
            return f"d'{nom}"
        return f"de {nom}"
    if nom in _FEMININE_DEPTS:
        return f"de la {nom}"
    if nom[0].upper() in "AEIOUY":
        return f"de l'{nom}"
    if "-" in nom or " " in nom or "'" in nom:
        return f"de {nom}"
    return f"du {nom}"


def _ordinal_fr(n: int) -> str:
    return "1re" if n == 1 else f"{n}e"


def _join_names_fr(names: list[str], *, max_names: int = 5) -> str:
    items = [n for n in names if n][:max_names]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} et {items[1]}"
    return ", ".join(items[:-1]) + f" et {items[-1]}"


def _national_score_rank(row: pd.Series, master: pd.DataFrame) -> tuple[int | None, int]:
    """Rang national (1 = score le plus faible / plus fragile)."""
    ranked = (
        master.dropna(subset=["score_global"])
        .sort_values("score_global")
        .reset_index(drop=True)
    )
    matches = ranked.index[ranked["dept"] == row["dept"]].tolist()
    if not matches:
        return None, len(ranked)
    return matches[0] + 1, len(ranked)


def _pop_weighted_mean(depts: pd.DataFrame, col: str) -> float:
    pop = pd.to_numeric(depts["population_num"], errors="coerce")
    vals = pd.to_numeric(depts[col], errors="coerce")
    mask = pop.notna() & vals.notna() & (pop > 0)
    if not mask.any():
        return float("nan")
    return float((vals[mask] * pop[mask]).sum() / pop[mask].sum())


def _region_national_rank(region_code: str, master: pd.DataFrame) -> tuple[int | None, int]:
    scores: list[tuple[str, float]] = []
    for code, group in master.groupby("Code région", sort=False):
        s = _pop_weighted_mean(group, "score_global")
        if pd.notna(s):
            scores.append((str(code), s))
    scores.sort(key=lambda x: x[1])
    total = len(scores)
    for i, (code, _) in enumerate(scores, 1):
        if str(code) == str(region_code):
            return i, total
    return None, total


def _critical_commune_names(data: dict, dept_code: str, *, limit: int = 5) -> list[str]:
    temps = data.get("temps")
    if temps is None or getattr(temps, "empty", True):
        return []
    df = temps[temps["code_departement"].astype(str).str.zfill(2) == dept_code].copy()
    df["temps_acces"] = pd.to_numeric(df["temps_acces"], errors="coerce")
    df = df[df["temps_acces"] > 15].sort_values("temps_acces", ascending=False)
    seen: set[str] = set()
    names: list[str] = []
    for name in df["commune"].dropna().astype(str):
        if name not in seen:
            seen.add(name)
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _top_opportunity_commune_names(
    data: dict,
    row: pd.Series,
    *,
    limit: int = 3,
) -> list[str]:
    dept_code = str(row.get("dept", "")).zfill(2)
    if dept_code in {"75"}:
        return []

    try:
        from .commune_opportunity import (
            build_commune_code_lookup,
            build_commune_opportunity_df,
            top_communes_for_action,
        )
        from .components.maps import _fetch_communes_geojson, fetch_communes_population

        communes_gj = _fetch_communes_geojson(dept_code)
        if not communes_gj:
            return []

        name_to_code, code_to_name = build_commune_code_lookup(
            communes_gj.get("features", [])
        )
        population_by_code = fetch_communes_population(dept_code) or {}

        temps = data.get("temps")
        immo = data.get("immo")
        if temps is None or immo is None:
            return []

        temps_f = temps[temps["code_departement"].astype(str).str.zfill(2) == dept_code]
        immo_f = immo[immo["code_departement"].astype(str).str.zfill(2) == dept_code]
        if temps_f.empty or immo_f.empty:
            return []

        comm_data = build_commune_opportunity_df(
            temps_f,
            immo_f,
            name_to_code,
            code_to_name=code_to_name,
            population_by_code=population_by_code or None,
        )
        top = top_communes_for_action(comm_data, limit=limit)
        if top.empty:
            return []
        return top["commune"].dropna().astype(str).tolist()
    except Exception:
        return []


def _short_lever(title: str) -> str:
    t = title.strip().rstrip(".")
    if not t:
        return ""
    lower = t.lower()
    for hint, short in _LEVER_SHORT_HINTS:
        if hint in lower:
            return short
    chunk = t.split(",")[0].split(".")[0]
    if len(chunk) > 72:
        chunk = chunk[:69].rsplit(" ", 1)[0] + "…"
    return chunk[0].lower() + chunk[1:] if chunk else t.lower()


def _pct_65_sentence(
    pct_val: float | None,
    master: pd.DataFrame,
    *,
    is_regional: bool = False,
) -> str | None:
    if pct_val is None or (isinstance(pct_val, float) and pd.isna(pct_val)):
        return None

    pct_f = float(pct_val)
    nat_med = (
        float(master["pct_plus_65"].median())
        if "pct_plus_65" in master.columns and not is_regional
        else None
    )
    base = f"{pct_f:.1f} % de la population a 65 ans et plus"
    if is_regional and pct_f > 22:
        return f"{base}, ce qui accentue la pression sur la demande de soins."
    if nat_med is not None and pct_f > nat_med + 0.5:
        return f"{base}, ce qui accentue la pression sur la demande de soins."
    return f"{base}."


def _apl_sentence_dept(row: pd.Series) -> str | None:
    apl = row.get("apl_median_dept")
    if apl is None or pd.isna(apl):
        return None
    apl_f = float(apl)
    if apl_f < APL_SEUIL_DESERT:
        level = "très faible" if apl_f < 1.5 else "faible"
        return (
            f"L'accessibilité aux médecins généralistes est {level} : "
            f"l'APL atteint {apl_f:.1f} consultation par habitant, "
            f"sous le seuil de 2,5 et est donc considéré comme désert médical."
        )
    return (
        f"L'APL atteint {apl_f:.1f} consultation par habitant, "
        f"au-dessus du seuil de 2,5."
    )


def build_audio_diagnostic_text(
    row: pd.Series,
    master: pd.DataFrame,
    recommendations: list[dict],
    data: dict,
) -> str:
    """Synthèse vocale départementale enrichie."""
    parts: list[str] = []
    dept_nom = str(row.get("Nom du département", "ce département"))
    dept_code = str(row.get("dept", "")).zfill(2)

    parts.append(
        f"Diagnostic Sant'active pour le département "
        f"{_territory_label_for_speech(dept_nom, kind='dept')}."
    )

    zone = str(row.get("zone_short", "")).strip()
    score = row.get("score_global")
    if zone and zone not in ("", "N/D"):
        if pd.notna(score):
            parts.append(
                f"Le territoire est classé en zone {zone.lower()}, "
                f"avec un score Sant'active de {float(score):.1f} sur 100."
            )
        else:
            parts.append(f"Le territoire est classé en zone {zone.lower()}.")
    elif pd.notna(score):
        parts.append(
            f"Le score Sant'active s'élève à {float(score):.1f} sur 100."
        )

    rang, total = _national_score_rank(row, master)
    if rang is not None:
        parts.append(
            f"Le département est classé {_ordinal_fr(rang)} sur {total} "
            f"au classement national de fragilité sanitaire."
        )

    apl_part = _apl_sentence_dept(row)
    if apl_part:
        parts.append(apl_part)

    nb_comm = row.get("nb_communes_critiques")
    crit_names = _critical_commune_names(data, dept_code, limit=5)
    if pd.notna(nb_comm) and int(nb_comm) > 0:
        n = int(nb_comm)
        names_str = _join_names_fr(crit_names, max_names=5)
        if n == 1:
            base = "Le département compte 1 commune éloignée des soins"
        else:
            base = f"Le département compte {n} communes éloignées des soins"
        if names_str:
            parts.append(f"{base}, notamment {_join_names_fr(crit_names)}.")
        else:
            parts.append(f"{base}.")

    pct_part = _pct_65_sentence(row.get("pct_plus_65"), master)
    if pct_part:
        parts.append(pct_part)

    med = row.get("med_gen_pour_100k")
    med_nat = (
        float(master["med_gen_pour_100k"].median())
        if "med_gen_pour_100k" in master.columns
        else None
    )
    apl = row.get("apl_median_dept")
    if pd.notna(med) and med_nat is not None and pd.notna(med_nat):
        if pd.isna(apl) or float(apl) >= APL_SEUIL_DESERT:
            med_f = float(med)
            if med_f < med_nat * 0.9:
                parts.append(
                    f"La densité de médecins généralistes reste limitée, "
                    f"avec {med_f:.0f} pour 100 000 habitants."
                )

    levers = [
        _short_lever(str(rec.get("title", "")))
        for rec in recommendations[:2]
        if rec.get("title")
    ]
    levers = [lev for lev in levers if lev]
    if len(levers) >= 2:
        parts.append(
            f"Les principaux leviers proposés concernent {levers[0]} "
            f"et {levers[1]}."
        )
    elif len(levers) == 1:
        parts.append(f"Le principal levier proposé concerne {levers[0]}.")

    top_communes = _top_opportunity_commune_names(data, row, limit=3)
    if top_communes:
        joined = _join_names_fr(top_communes)
        if len(top_communes) >= 2:
            parts.append(
                f"Pour prioriser les actions, les communes de {joined} "
                f"ressortent en tête du classement local."
            )
        else:
            parts.append(
                f"Pour prioriser les actions, la commune de {joined} "
                f"ressort en tête du classement local."
            )

    parts.append(_AUDIO_DISCLAIMER)
    return " ".join(parts)


def build_region_audio_diagnostic_text(
    region_name: str,
    region_code: str,
    region_depts: pd.DataFrame,
    master: pd.DataFrame,
    priorities: pd.DataFrame,
    leviers: list[dict],
    summary: dict,
) -> str:
    """Synthèse vocale régionale enrichie."""
    parts: list[str] = []
    nb_depts = len(region_depts)

    parts.append(
        f"Diagnostic Sant'active pour la région "
        f"{_territory_label_for_speech(region_name, kind='region')}."
    )

    score_reg = _pop_weighted_mean(region_depts, "score_global")
    nb_crit = int((region_depts["zone_short"] == "Critique").sum())
    zone_region = (
        "critique" if nb_crit >= nb_depts / 2
        else ("intermédiaire" if nb_crit > 0 else "favorable")
    )

    if pd.notna(score_reg):
        parts.append(
            f"La région présente un profil {zone_region}, "
            f"avec un score Sant'active agrégé de {score_reg:.1f} sur 100."
        )
    else:
        parts.append(f"La région présente un profil {zone_region}.")

    if nb_crit > 0:
        parts.append(
            f"{nb_crit} département{'s' if nb_crit > 1 else ''} "
            f"sur {nb_depts} {' sont' if nb_crit > 1 else ' est'} "
            f"en zone critique."
        )

    rang, total = _region_national_rank(region_code, master)
    if rang is not None:
        parts.append(
            f"La région est classée {_ordinal_fr(rang)} sur {total} "
            f"au classement national de fragilité sanitaire."
        )

    apl_med = region_depts["apl_median_dept"].median()
    if pd.notna(apl_med):
        apl_f = float(apl_med)
        if apl_f < APL_SEUIL_DESERT:
            level = "très faible" if apl_f < 1.5 else "faible"
            parts.append(
                f"L'accessibilité aux médecins généralistes est {level} "
                f"à l'échelle régionale : l'APL médian atteint {apl_f:.1f} "
                f"consultation par habitant, sous le seuil de 2,5."
            )
        else:
            parts.append(
                f"L'APL médian régional atteint {apl_f:.1f} consultation "
                f"par habitant, au-dessus du seuil de 2,5."
            )

    nb_desert = int(
        (pd.to_numeric(region_depts["apl_median_dept"], errors="coerce") < APL_SEUIL_DESERT).sum()
    )
    if nb_desert > 0:
        desert_names = region_depts[
            pd.to_numeric(region_depts["apl_median_dept"], errors="coerce") < APL_SEUIL_DESERT
        ]["Nom du département"].tolist()
        parts.append(
            f"{nb_desert} département{'s' if nb_desert > 1 else ''} "
            f"{' sont' if nb_desert > 1 else ' est'} en situation de désert médical"
            + (f", notamment {_join_names_fr(desert_names, max_names=3)}." if desert_names else ".")
        )

    nb_communes = int(
        pd.to_numeric(region_depts["nb_communes_critiques"], errors="coerce").fillna(0).sum()
    )
    if nb_communes > 0:
        iso_depts = region_depts[
            pd.to_numeric(region_depts["nb_communes_critiques"], errors="coerce").fillna(0) > 0
        ].sort_values("nb_communes_critiques", ascending=False)
        iso_names = iso_depts["Nom du département"].head(3).tolist()
        parts.append(
            f"La région compte {nb_communes} communes éloignées des soins"
            + (f", avec une concentration notable en {_join_names_fr(iso_names)}." if iso_names else ".")
        )

    pct65_med = region_depts["pct_plus_65"].median()
    pct_part = _pct_65_sentence(pct65_med, master, is_regional=True)
    if pct_part:
        parts.append(pct_part)

    tension = summary.get("tension_principale")
    if tension and tension != "Données insuffisantes pour identifier une tension dominante.":
        parts.append(f"Le principal constat porte sur {tension}.")

    lever_labels = [
        _short_lever(str(lev.get("intitule", "")))
        for lev in leviers[:2]
        if lev.get("intitule")
    ]
    lever_labels = [l for l in lever_labels if l]
    if len(lever_labels) >= 2:
        parts.append(
            f"Les principaux leviers proposés concernent {lever_labels[0]} "
            f"et {lever_labels[1]}."
        )
    elif len(lever_labels) == 1:
        parts.append(f"Le principal levier proposé concerne {lever_labels[0]}.")

    if not priorities.empty:
        prio_depts = priorities["Nom du département"].head(3).tolist()
        if len(prio_depts) >= 2:
            parts.append(
                f"Pour prioriser les actions, les départements de "
                f"{_join_names_fr(prio_depts)} ressortent en tête."
            )
        elif len(prio_depts) == 1:
            parts.append(
                f"Pour prioriser les actions, le département "
                f"{prio_depts[0]} ressort en tête."
            )

    parts.append(_AUDIO_DISCLAIMER)
    return " ".join(parts)


async def _synthesize_edge_tts(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


@st.cache_data(show_spinner=False, ttl=3600)
def generate_audio_summary(text: str, voice: str = _AUDIO_VOICE) -> bytes:
    """Génère l'audio MP3 via edge-tts (cache Streamlit sur le texte)."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _synthesize_edge_tts(text, voice)).result(
            timeout=120
        )


def render_audio_diagnostic_button(
    *,
    scope_key: str,
    build_text: Callable[[], str],
) -> None:
    """Bouton + lecteur audio — génération à la demande uniquement."""
    req_key = f"audio_diag_req_{scope_key}"
    btn_key = f"audio_diag_btn_{scope_key}"

    st.markdown(
        '<div style="margin-top:18px;padding-top:16px;border-top:1px solid #E8E6DD;">'
        "</div>",
        unsafe_allow_html=True,
    )

    if st.button(
        "🔊 Écouter le diagnostic",
        key=btn_key,
        type="secondary",
    ):
        st.session_state[req_key] = True

    if not st.session_state.get(req_key):
        return

    audio_text = build_text()

    try:
        with st.spinner("Génération de la synthèse vocale…"):
            audio_bytes = generate_audio_summary(audio_text)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/mp3")
        else:
            raise ValueError("audio vide")
    except Exception:
        st.markdown(
            '<p style="font-size:13px;color:#6B6B68;margin-top:8px;">'
            "Lecture audio indisponible pour le moment. "
            "Réessayez ultérieurement."
            "</p>",
            unsafe_allow_html=True,
        )
