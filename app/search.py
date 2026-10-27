"""Recherche fuzzy dans les territoires (régions, départements, communes)."""

from __future__ import annotations

import re
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


_LEVEL_ORDER = {"region": 0, "departement": 1, "commune": 2}


def _norm(s: str) -> str:
    """Minuscules sans accents ; tirets, apostrophes et espaces multiples → espace."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[-'’\s]+", " ", s).split())


def _score(norm_name: str, q: str) -> int:
    if norm_name == q:
        return 100
    if norm_name.startswith(q):
        return 95
    if any(w.startswith(q) for w in norm_name.split()):
        return 85
    return 70


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
            score = _score(_norm(name), q)
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
        code_ok = q.upper() == code or q.zfill(2) == code
        if q in _norm(name) or code_ok:
            score = 100 if code_ok else _score(_norm(name), q)
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
        # Colonne normalisée pré-calculée si possible (home.py), sinon à la volée
        norm_col = communes["commune_norm"] if "commune_norm" in communes.columns \
            else communes["commune"].map(_norm)
        hit = communes[norm_col.str.contains(q, regex=False, na=False)].copy()
        hit["_norm"] = norm_col[hit.index]
        hit["_s"] = hit["_norm"].map(lambda n: _score(n, q))
        matches = hit.sort_values(["_s", "_norm"], ascending=[False, True]).head(30)
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
                score=int(r["_s"]) - 10,   # une commune ne devance pas un territoire de même score
            ))

    results.sort(key=lambda x: (-x.score, _LEVEL_ORDER.get(x.level, 9), _norm(x.name)))
    return results[:limit]
