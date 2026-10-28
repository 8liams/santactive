"""Contours simplifiés des cinq DROM pour les cartouches de l'accueil.

geo.api.gouv.fr ne fournit plus le contour des départements ; on reconstitue
chaque contour par union des communes (shapely), simplifié (≈ 300 m), et on
l'enregistre une fois pour toutes dans static/geo/contours_dom.json (≈ 40 Ko).

Usage : python3 scripts/donnees/generer_contours_dom.py
"""
from __future__ import annotations

import json
from pathlib import Path

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "static" / "geo" / "contours_dom.json"
DOM = {"971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte"}


def main() -> None:
    feats = []
    for code, nom in DOM.items():
        r = requests.get(f"https://geo.api.gouv.fr/departements/{code}/communes",
                         params={"format": "geojson", "geometry": "contour", "fields": "code"}, timeout=60)
        r.raise_for_status()
        polys = [shape(f["geometry"]).buffer(0) for f in r.json()["features"] if f.get("geometry")]
        union = unary_union(polys).simplify(0.003, preserve_topology=True)
        feats.append({"type": "Feature", "properties": {"code": code, "nom": nom}, "geometry": mapping(union)})
        print(f"{code} {nom}: {len(polys)} communes → {union.geom_type}")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
    print(f"Écrit : {OUT} ({OUT.stat().st_size / 1e3:.0f} Ko)")


if __name__ == "__main__":
    main()
