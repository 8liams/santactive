"""Audit comparatif de la migration du score (28 octobre 2026).

Quatre combinaisons, pondérations et règles inchangées :
  V1  temps interne  + APL 2023   (production jusqu'au 28 octobre 2026)
  V2  temps INSEE    + APL 2023   (effet propre du temps INSEE)
  V3  temps interne  + APL 2024   (effet propre de l'APL 2024)
  V4  temps INSEE    + APL 2024   (nouvelle production)

Temps INSEE = médiane pondérée par la population du temps de trajet en voiture
vers le généraliste le plus proche (Insee 2025, carreaux 200 m, Metric-OSRM),
colonne acces_mg_t_med. Pour chaque variante : score global, rang, zone
(terciles), quadrant de priorisation (app/indices.py), leviers recommandés
(app/leviers.py via fiche_departement._generate_recommendations).

Sorties :
  data_corrections/references/audit_migration/audit_migration_departements.csv
  data_corrections/references/audit_migration/audit_migration_resume.md
Usage : python3 scripts/analyse/audit_migration_score.py
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data_corrections" / "references" / "audit_migration"


def _clear_caches() -> None:
    for name in ("app.indices", "app.leviers"):
        mod = sys.modules.get(name)
        if mod is None:
            continue
        for attr in dir(mod):
            if attr.startswith("_CACHE") or attr.endswith("_CACHE"):
                obj = getattr(mod, attr)
                if isinstance(obj, dict):
                    obj.clear()


def main() -> None:
    warnings.filterwarnings("ignore")
    os.chdir(ROOT)
    from app.data_loading import load_all_data
    from app.indices import calculer_indices
    from app.scoring import compute_scores
    from app.pages.fiche_departement import _generate_recommendations

    master, pros, immo, etabs, temps, env, patho, delais, presence = load_all_data()
    data = {"master": master, "pros": pros, "immo": immo, "etabs": etabs, "temps": temps, "env": env,
            "patho": patho, "delais": delais, "presence": presence, "drees": None, "geojson": None}
    assert "temps_acces_interne_median" in master.columns, "lancer avec SANTACTIVE_TEMPS_SOURCE=insee (défaut)"
    apl23 = pd.read_csv(ROOT / "static/data/apl_mg_departemental_2023.csv", dtype={"dept": str}).set_index("dept")["apl_moyen_pondere"]
    apl24 = pd.read_csv(ROOT / "static/data/apl_mg_departemental_2024.csv", dtype={"dept": str}).set_index("dept")["apl_moyen_pondere"]
    temps_int = master.set_index("dept")["temps_acces_interne_median"]
    temps_insee = master.set_index("dept")["acces_mg_t_med"]

    variants = {"V1": (temps_int, apl23, "temps interne + APL 2023"), "V2": (temps_insee, apl23, "temps INSEE + APL 2023"),
                "V3": (temps_int, apl24, "temps interne + APL 2024"), "V4": (temps_insee, apl24, "temps INSEE + APL 2024")}
    out = master[["dept", "Nom du département", "Nom de la région", "population_num"]].copy()
    out["temps_interne"] = temps_int.values
    out["temps_insee"] = temps_insee.values
    out["part_sup_15_insee"] = master["acces_mg_part_sup_15"].values
    out["apl_2023"] = apl23.reindex(out["dept"]).values
    out["apl_2024"] = apl24.reindex(out["dept"]).values
    recos = {}
    for k, (t, a, _) in variants.items():
        m = master.copy()
        m["temps_acces_median"] = t.reindex(m["dept"]).values
        m["apl_dept"] = a.reindex(m["dept"]).values
        m["apl_moyen_pondere"] = m["apl_dept"]
        sc = compute_scores(m)
        _clear_caches()
        ind = calculer_indices(sc, patho)
        d2 = dict(data); d2["master"] = sc
        rk = {}
        for _, r in sc.iterrows():
            try:
                rk[r["dept"]] = "|".join(x.get("kind", x.get("titre", "?")) for x in _generate_recommendations(r, sc, d2))
            except Exception as e:  # pragma: no cover
                rk[r["dept"]] = f"erreur:{type(e).__name__}"
        recos[k] = rk
        s = sc.set_index("dept")
        out[f"score_{k}"] = s["score_global"].reindex(out["dept"]).values
        out[f"rang_{k}"] = s["rang_national"].reindex(out["dept"]).values
        out[f"zone_{k}"] = s["zone_short"].reindex(out["dept"]).values
        out[f"quadrant_{k}"] = ind["quadrant"].reindex(out["dept"]).values
        out[f"recos_{k}"] = out["dept"].map(rk)
        _clear_caches()
    for k in ("V2", "V3", "V4"):
        out[f"d_score_{k}"] = out[f"score_{k}"] - out["score_V1"]
        out[f"d_rang_{k}"] = out[f"rang_{k}"] - out["rang_V1"]
    OUT.mkdir(parents=True, exist_ok=True)
    out.round(3).to_csv(OUT / "audit_migration_departements.csv", index=False)

    # ── Résumé ───────────────────────────────────────────────────────────────
    L = []
    P = L.append
    P("# Audit de la migration du score — 28 octobre 2026\n")
    P("Pondérations inchangées (APL 30 %, temps 20 %, généralistes 20 %, structures 15 %, 65 ans et plus 10 %, foncier 5 %) ; "
      "terciles 33 / 34 / 33 par construction. V1 = production jusqu'au 28 octobre ; V4 = nouvelle production.\n")
    P("## 1. Contrôles de l'indicateur de temps INSEE\n")
    ti, tn = out["temps_interne"], out["temps_insee"]
    P(f"- Couverture : {int(tn.notna().sum())} départements sur {len(out)} (absents : "
      + ", ".join(out.loc[tn.isna(), "Nom du département"].astype(str)) + " ; hors champ Filosofi, poids redistribué sur les autres dimensions).")
    P(f"- Distribution médiane pondérée INSEE : min {tn.min():.1f}, médiane {tn.median():.1f}, max {tn.max():.1f} min ; "
      f"interne : min {ti.min():.1f}, médiane {ti.median():.1f}, max {ti.max():.1f} min.")
    P(f"- Corrélation de Spearman interne / INSEE : {ti.corr(tn, method='spearman'):.2f} ; INSEE médiane / part > 15 min : "
      f"{tn.corr(out['part_sup_15_insee'], method='spearman'):.2f}.")
    P("- Sens : plus la médiane est élevée, plus le score de la dimension est bas (inchangé). La part de population à plus de "
      "15 min reste un indicateur complémentaire de fragilité (affichée, pas dans le score).\n")
    P("## 2. APL 2023 → 2024\n")
    a23, a24 = out["apl_2023"], out["apl_2024"]
    d = a24 - a23
    P(f"- Même définition DREES (APL aux médecins généralistes tous âges, population standardisée, hors Mayotte) ; "
      f"{int(a24.notna().sum())} départements renseignés.")
    P(f"- Variation moyenne {d.mean():+.2f} consult./hab. (médiane {d.median():+.2f}, de {d.min():+.2f} à {d.max():+.2f}) ; "
      f"corrélation 2023 / 2024 : {a23.corr(a24):.3f} ; {int((d < 0).sum())} départements en baisse, {int((d > 0).sum())} en hausse.")
    top = out.reindex(d.abs().sort_values(ascending=False).index).head(6)
    P("- Plus fortes variations : " + " ; ".join(f"{r['Nom du département']} {r['apl_2023']:.2f} → {r['apl_2024']:.2f}" for _, r in top.iterrows()) + ".\n")
    for k, (_, _, lib) in variants.items():
        if k == "V1":
            continue
        P(f"## 3.{k[1]} {lib} (par rapport à V1)\n")
        dr = out[f"d_rang_{k}"].abs()
        P(f"- Corrélation des scores {out['score_V1'].corr(out[f'score_{k}']):.3f} ; écart de rang médian {dr.median():.0f}, moyen {dr.mean():.1f}, "
          f"max {dr.max():.0f} ; {int((dr >= 10).sum())} départements bougent de 10 rangs ou plus.")
        zc = out[(out[f"zone_{k}"] != out["zone_V1"]) & out[f"zone_{k}"].notna()]
        P(f"- Changements de zone : {len(zc)} — " + (", ".join(f"{r['Nom du département']} ({r['zone_V1']} → {r[f'zone_{k}']})" for _, r in zc.iterrows()) or "aucun") + ".")
        qa1 = set(out.loc[out["quadrant_V1"] == "A", "dept"]); qak = set(out.loc[out[f"quadrant_{k}"] == "A", "dept"])
        nom = out.set_index("dept")["Nom du département"]
        P(f"- Territoires prioritaires (quadrant A) : {len(qak)} (V1 : {len(qa1)}) ; entrent : "
          + (", ".join(nom[c] for c in sorted(qak - qa1)) or "aucun") + " ; sortent : " + (", ".join(nom[c] for c in sorted(qa1 - qak)) or "aucun") + ".")
        rc = [c for c in out["dept"] if recos["V1"].get(c) != recos[k].get(c)]
        P(f"- Recommandations (leviers) modifiées : {len(rc)} départements" + (" : " + ", ".join(nom[c] for c in rc[:12]) + (" …" if len(rc) > 12 else "") if rc else "") + ".")
        t2 = out.reindex(out[f"d_rang_{k}"].abs().sort_values(ascending=False).index).head(8)
        P("- Plus affectés : " + " ; ".join(f"{r['Nom du département']} {int(r[f'd_rang_{k}']):+d} rangs ({r['score_V1']:.0f} → {r[f'score_{k}']:.0f})" for _, r in t2.iterrows()) + ".\n")
    P("## 4. Limites de comparabilité\n")
    P("- L'indicateur interne mesurait une médiane communale non pondérée (0 = généraliste présent) ; l'INSEE une médiane pondérée par "
      "la population des carreaux habités : les deux ne sont pas des mesures de la même grandeur, les écarts de rang sont attendus.")
    P("- Guadeloupe, Guyane et Mayotte n'ont pas de temps INSEE : leur score repose sur cinq dimensions (poids redistribué), ce qui "
      "était déjà le cas pour toute dimension absente.")
    P("- L'APL 2024 intègre l'évolution réelle de l'offre entre 2023 et 2024 : une partie des mouvements de rang reflète le terrain, pas la méthode.")
    P("- Les anciens indicateurs restent disponibles (colonnes temps_acces_interne_median, apl_mg_departemental_2023.csv, "
      "SANTACTIVE_TEMPS_SOURCE=interne, SANTACTIVE_APL_MILLESIME=2023) pour l'audit, sans être présentés comme actifs.")
    (OUT / "audit_migration_resume.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
