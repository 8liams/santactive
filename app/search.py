"""Recherche fuzzy dans les territoires (régions, départements, communes)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal

import pandas as pd


@dataclass
class SearchResult:
    level: Literal["region", "departement", "commune"]
    code: str               # code INSEE (01, 973, 02010...)
    name: str               # "Aisne", "Vervins", "Hauts-de-France"
    parent_code: str | None # code région pour un dept, code dept pour une commune
    parent_name: str | None
    score: int              # 0-100, pour ordonner les résultats


def _norm(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().strip()


def search_territory(
    query: str,
    master: pd.DataFrame,
    communes: pd.DataFrame | None = None,
    limit: int = 8,
) -> list[SearchResult]:
    """Retourne les territoires correspondant à la requête, triés par pertinence."""
    if not query or len(query) < 2:
        return []

    q = _norm(query)
    results: list[SearchResult] = []
    seen_codes: set[str] = set()

    # ── Régions (dédupliquées à partir du master) ──────────────────────────────
    regions = (
        master[["Code région", "Nom de la région"]]
        .drop_duplicates()
        .dropna()
    )
    for _, r in regions.iterrows():
        name = str(r["Nom de la région"])
        code = str(r["Code région"])
        if q in _norm(name):
            score = 100 if _norm(name).startswith(q) else 70
            key = f"region_{code}"
            if key not in seen_codes:
                seen_codes.add(key)
                results.append(SearchResult(
                    level="region",
                    code=code,
                    name=name,
                    parent_code=None,
                    parent_name=None,
                    score=score,
                ))

    # ── Départements ───────────────────────────────────────────────────────────
    for _, r in master.iterrows():
        name = str(r.get("Nom du département", ""))
        code = str(r.get("dept", ""))
        if not name or not code:
            continue
        if q in _norm(name) or q == code:
            score = 100 if _norm(name).startswith(q) or q == code else 80
            key = f"dept_{code}"
            if key not in seen_codes:
                seen_codes.add(key)
                results.append(SearchResult(
                    level="departement",
                    code=code,
                    name=name,
                    parent_code=str(r.get("Code région", "")),
                    parent_name=str(r.get("Nom de la région", "")),
                    score=score,
                ))

    # ── Communes (si fournies) ─────────────────────────────────────────────────
    if communes is not None and not communes.empty:
        q_upper = q.upper()
        matches = communes[
            communes["commune"].apply(
                lambda c: isinstance(c, str) and q_upper in _norm(c).upper()
            )
        ].head(30)
        for _, r in matches.iterrows():
            commune_name = str(r["commune"])
            dept_code    = str(r.get("code_departement", "")).zfill(2)
            # Code = "NOM_COMMUNE|CODE_DEPT" pour la fiche commune
            uniq_key = f"{commune_name}|{dept_code}"
            key_set  = f"commune_{uniq_key}"
            if key_set in seen_codes:
                continue
            seen_codes.add(key_set)

            dept_row  = master[master["dept"] == dept_code]
            dept_name = dept_row.iloc[0]["Nom du département"] if not dept_row.empty else ""

            results.append(SearchResult(
                level="commune",
                code=uniq_key,
                name=commune_name,
                parent_code=dept_code,
                parent_name=dept_name,
                score=60,
            ))

    results.sort(key=lambda x: (-x.score, x.level))
    return results[:limit]
