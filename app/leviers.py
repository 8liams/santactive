"""Catalogue déterministe de leviers d'action et moteur de sélection.

Principe : chaque département est décrit par un PROFIL d'indicateurs observés
(APL pondérée, part de population sous 2,5, densités DREES par spécialité,
prévalences CNAM brutes et standardisées, démographie, communes à plus de
15 min, structures FINESS, typologie). Chaque LEVIER du catalogue déclare des
conditions explicites (requises ou contributives), des exclusions, un public,
des dispositifs documentés et un gabarit de texte alimenté par les valeurs du
profil. Le moteur retient les leviers dont toutes les conditions requises sont
vérifiées, les classe par score de correspondance (part des conditions
contributives satisfaites, pondérée) et limite la redondance par famille.

Aucune IA générative : règles lisibles, reproductibles, testées
(tests/test_leviers.py). Les dispositifs cités sont des cadres nationaux
existants (ACI/MSP, CPTS, assistants médicaux, téléexpertise, SAS, Mon soutien
psy, Mon Bilan Prévention, dépistages organisés, PMI, ICOPE, DAC, HAD, EMPP,
transport solidaire) ; aucun effet chiffré n'est inventé.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from .config import PATHOS_EXCLUDED
from .scoring import to_num

# ── Postes DREES utilisés pour les densités de spécialistes ─────────────────
POSTES = {
    "psychiatrie": "12-Psychiatrie", "pediatrie": "10-Pédiatrie", "gynecologie": "09-Gynécologie",
    "cardiologie": "06-Cardiologie", "ophtalmologie": "03-Ophtalmologie", "dermatologie": "07-Dermatologie",
    "pneumologie": "11-Pneumologie", "gastro": "08-Gastro-entérologie",
}
POSTE_LABELS = {
    "psychiatrie": "psychiatres", "pediatrie": "pédiatres", "gynecologie": "gynécologues",
    "cardiologie": "cardiologues", "ophtalmologie": "ophtalmologues", "dermatologie": "dermatologues",
    "pneumologie": "pneumologues", "gastro": "gastro-entérologues",
}
PATHOS = {
    "diabete": "Diabète", "cardio": "Maladies cardioneurovasculaires", "psy": "Maladies psychiatriques",
    "respi": "Maladies respiratoires chroniques (hors mucoviscidose)", "cancers": "Cancers",
    "neuro": "Maladies neurologiques",
}
PATHO_LABELS = {
    "diabete": "diabète", "cardio": "maladies cardio-neuro-vasculaires", "psy": "troubles psychiatriques",
    "respi": "maladies respiratoires chroniques", "cancers": "cancers", "neuro": "maladies neurologiques",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. PROFILS TERRITORIAUX (vectorisés sur les 100 départements, puis par ligne)
# ══════════════════════════════════════════════════════════════════════════════

_PROFILS_CACHE: dict[int, pd.DataFrame] = {}


def _densites_specialistes(data: dict, master: pd.DataFrame) -> pd.DataFrame:
    """Densités DREES (effectif / population INSEE 2021 × 100 000) par poste et département."""
    drees = (data.get("drees") or {}).get("medecins")
    pop = master.set_index("dept")["population_num"].astype(float)
    out = pd.DataFrame(index=pop.index)
    if drees is None or drees.empty:
        for k in POSTES:
            out[f"dens_{k}"] = float("nan")
        return out
    ens = drees[drees["exercice"] == "0-Ensemble"]
    for k, poste in POSTES.items():
        sub = ens[ens["specialites"] == poste].drop_duplicates("dept").set_index("dept")["effectif"]
        out[f"dens_{k}"] = (sub.reindex(pop.index) / pop * 100_000).astype(float)
    autres = (data.get("drees") or {}).get("autres")
    if autres is not None and not autres.empty:
        a = autres[(autres["secteur_activite"].astype(str).str.startswith("00")) & (autres["exercice"] == "0-Ensemble")]
        sf = a[a["profession"] == "sages_femmes"].drop_duplicates("dept").set_index("dept")["effectif"]
        out["dens_sages_femmes"] = (sf.reindex(pop.index) / pop * 100_000).astype(float)
    else:
        out["dens_sages_femmes"] = float("nan")
    return out


def _structures(data: dict, master: pd.DataFrame) -> pd.DataFrame:
    etabs = data.get("etabs")
    idx = master["dept"]
    out = pd.DataFrame(index=idx)
    if etabs is None or etabs.empty or "categetab" not in etabs.columns:
        out["nb_centres_sante"] = float("nan"); out["nb_had"] = float("nan"); return out
    e = etabs.copy()
    e["dept"] = e["code_departement"].astype(str).str.zfill(2)
    out["nb_centres_sante"] = e[e["categetab"] == "Centre de Santé"].groupby("dept").size().reindex(idx).fillna(0)
    out["nb_had"] = e[e["categetab"] == "Hospitalisation à Domicile"].groupby("dept").size().reindex(idx).fillna(0)
    return out


def profils_departements(data: dict) -> pd.DataFrame:
    """Table 100 départements × indicateurs + percentiles nationaux (rang, 100 = valeur la plus haute)."""
    master: pd.DataFrame = data["master"]
    key = id(master)
    if key in _PROFILS_CACHE:
        return _PROFILS_CACHE[key]
    from .pathologies import dept_prevalences, dept_prevalences_standardisees

    p = master.set_index("dept").copy()
    p = p.join(_densites_specialistes(data, master)).join(_structures(data, master))
    prev = dept_prevalences(data.get("patho"), p.index)
    prev_std = dept_prevalences_standardisees(data.get("patho"), p.index)
    couv = prev_std.attrs.get("couverture") if not prev_std.empty else None
    for k, col in PATHOS.items():
        p[f"prev_{k}"] = prev[col].reindex(p.index) if not prev.empty and col in prev.columns else float("nan")
        if not prev_std.empty and col in prev_std.columns:
            std = prev_std[col].reindex(p.index)
            if couv is not None and col in couv.columns:
                std = std.where(couv[col].reindex(p.index) >= 0.9)   # non comparable sinon
            p[f"prevstd_{k}"] = std
        else:
            p[f"prevstd_{k}"] = float("nan")
    # Patients (Ntop) par pathologie
    from .pathologies import patho_agg
    g = patho_agg(data.get("patho"))
    for k, col in PATHOS.items():
        try:
            p[f"patients_{k}"] = g.xs(col, level="patho_niv1")["Ntop"].reindex(p.index)
        except KeyError:
            p[f"patients_{k}"] = float("nan")
    p["centres_sante_100k"] = p["nb_centres_sante"] / p["population_num"] * 100_000
    p["had_100k"] = p["nb_had"] / p["population_num"] * 100_000
    p["is_dom"] = p.index.isin(["971", "972", "973", "974", "976"])
    # Percentiles nationaux (100 = valeur la plus élevée)
    for c in ([f"dens_{k}" for k in POSTES] + ["dens_sages_femmes", "centres_sante_100k", "had_100k",
              "med_gen_pour_100k", "structures_pour_100k", "pct_plus_65", "pct_moins_25",
              "part_pop_apl_inf_2_5", "part_pop_communes_critiques", "temps_acces_median"]  # communes_critiques_source : conservée telle quelle
             + [f"prevstd_{k}" for k in PATHOS] + [f"prev_{k}" for k in PATHOS]):
        if c in p.columns:
            p[f"pct_{c}"] = pd.to_numeric(p[c], errors="coerce").rank(pct=True) * 100
    # Médianes nationales
    p.attrs["medianes"] = {c: float(pd.to_numeric(p[c], errors="coerce").median())
                           for c in p.columns if p[c].dtype.kind in "fi"}
    _PROFILS_CACHE.clear(); _PROFILS_CACHE[key] = p
    return p


def _communes_eloignees_insee(dept: str, n: int) -> list[tuple[str, int, float]] | None:
    """Communes dont le temps moyen en voiture vers un généraliste dépasse 15 min (INSEE 2025),
    les plus peuplées (population municipale API Géo) : (nom, habitants, minutes). None si le
    département n'est pas couvert (Guadeloupe, Guyane, Mayotte)."""
    from pathlib import Path
    from .commune_opportunity import load_acces_insee_communes
    from .config import DATA_DIR
    ins = load_acces_insee_communes()
    d = ins[ins["dep"].astype(str) == str(dept)]
    if d.empty:
        return None
    loin = d[pd.to_numeric(d["temps_acces"], errors="coerce") > 15]
    if loin.empty:
        return []
    path = DATA_DIR / "communes_population_geoapi.csv"
    if Path(path).exists():
        ref = pd.read_csv(path, dtype={"code_insee": str, "dept": str}).drop_duplicates("code_insee").set_index("code_insee")
        loin = loin.merge(ref[["nom", "population"]], left_on="code_insee", right_index=True, how="left")
    else:
        loin = loin.assign(nom=loin["code_insee"], population=loin["pop_localisee"])
    loin["population"] = pd.to_numeric(loin["population"], errors="coerce").fillna(pd.to_numeric(loin["pop_localisee"], errors="coerce"))
    loin = loin.dropna(subset=["nom"]).sort_values(["population", "temps_acces"], ascending=[False, False])
    return [(str(r["nom"]), int(r["population"]) if pd.notna(r["population"]) else 0, float(r["temps_acces"])) for _, r in loin.head(n).iterrows()]


def _communes_eloignees(dept: str, data: dict, n: int = 4) -> list[tuple[str, int, float]]:
    """Communes à plus de 15 min d'un généraliste les plus peuplées : (nom, habitants, minutes).
    Source INSEE 2025 (temps moyen communal) lorsque le département est couvert ; fichier interne
    sinon (Guadeloupe, Guyane : indicateur historique, 0 = présence)."""
    insee = _communes_eloignees_insee(dept, n)
    if insee is not None:
        return insee
    temps = data.get("temps")
    if temps is None or temps.empty:
        return []
    t = temps[(temps["code_departement"].astype(str).str.zfill(2) == dept) & (temps["temps_acces"] > 15)]
    if t.empty:
        return []
    pop = data.get("_communes_pop")
    if pop is None:
        from pathlib import Path
        from .config import DATA_DIR
        path = DATA_DIR / "communes_population_geoapi.csv"
        if Path(path).exists():
            from .commune_opportunity import norm_commune_name
            ref = pd.read_csv(path, dtype={"dept": str, "code_insee": str})
            ref["key"] = ref["nom"].map(norm_commune_name)
            pop = ref.drop_duplicates(["dept", "key"], keep=False).set_index(["dept", "key"])["population"]
            data["_communes_pop"] = pop
    if pop is None:
        return [(str(r["commune"]), 0, float(r["temps_acces"])) for _, r in t.head(n).iterrows()]
    from .commune_opportunity import norm_commune_name
    rows = []
    for _, r in t.iterrows():
        habitants = pop.get((dept, norm_commune_name(str(r["commune"]))), float("nan"))
        rows.append((str(r["commune"]), int(habitants) if pd.notna(habitants) else 0, float(r["temps_acces"])))
    rows.sort(key=lambda x: (-x[1], -x[2]))
    return rows[:n]


def _villes_hopitaux(dept: str, data: dict, n: int = 3) -> list[str]:
    etabs = data.get("etabs")
    if etabs is None or etabs.empty or "commune" not in etabs.columns:
        return []
    e = etabs[(etabs["code_departement"].astype(str).str.zfill(2) == dept)
              & etabs["categetab"].isin(["Centre Hospitalier (C.H.)", "Centre Hospitalier Régional (C.H.R.)"])]
    return [str(v).title() for v in e["commune"].dropna().unique()[:n]]


_MASCULINS = {"Ain", "Aveyron", "Bas-Rhin", "Calvados", "Cantal", "Cher", "Doubs", "Finistère", "Gard", "Gers",
              "Haut-Rhin", "Jura", "Loir-et-Cher", "Loiret", "Lot", "Lot-et-Garonne", "Maine-et-Loire", "Morbihan",
              "Nord", "Pas-de-Calais", "Puy-de-Dôme", "Rhône", "Tarn", "Tarn-et-Garonne", "Territoire de Belfort",
              "Val-d'Oise", "Val-de-Marne", "Var", "Vaucluse"}
_PLURIELS = {"Alpes-de-Haute-Provence", "Hautes-Alpes", "Alpes-Maritimes", "Ardennes", "Bouches-du-Rhône",
             "Côtes-d'Armor", "Deux-Sèvres", "Hauts-de-Seine", "Landes", "Pyrénées-Atlantiques", "Hautes-Pyrénées",
             "Pyrénées-Orientales", "Vosges", "Yvelines", "Ardennes"}
_SANS_ARTICLE = {"Paris", "Mayotte", "La Réunion"}


def _formes_nom(nom: str) -> dict:
    """Formes « de X », « dans X », « X » sujet, selon le genre et le nombre du département."""
    if nom in _SANS_ARTICLE:
        return {"nom_de": f"de {nom}", "nom_dans": f"à {nom}", "nom_sujet": nom}
    if nom in _PLURIELS:   # sujet au singulier pour l'accord des verbes
        return {"nom_de": f"des {nom}", "nom_dans": f"dans les {nom}", "nom_sujet": f"Le département des {nom}"}
    if nom[0].lower() in "aeiouyéè":
        return {"nom_de": f"de l'{nom}", "nom_dans": f"dans l'{nom}", "nom_sujet": f"L'{nom}"}
    if nom in _MASCULINS:
        return {"nom_de": f"du {nom}", "nom_dans": f"dans le {nom}", "nom_sujet": f"Le {nom}"}
    if "Corse" in nom:
        return {"nom_de": f"de la {nom}", "nom_dans": f"en {nom}", "nom_sujet": f"La {nom}"}
    return {"nom_de": f"de la {nom}", "nom_dans": f"dans la {nom}", "nom_sujet": f"La {nom}"}


def profil(dept: str, data: dict) -> dict:
    """Profil d'un département : valeurs, percentiles, médianes nationales, listes de secteurs."""
    P = profils_departements(data)
    dept = str(dept).zfill(2)
    if dept not in P.index:
        return {}
    row = P.loc[dept]
    p = {k: (to_num(v) if not isinstance(v, (str, bool)) else v) for k, v in row.items()}
    p["dept"] = dept
    p["nom"] = str(row.get("Nom du département", dept))
    p.update(_formes_nom(p["nom"]))
    p["med"] = P.attrs["medianes"]
    p["communes_eloignees"] = _communes_eloignees(dept, data)
    p["villes_hopitaux"] = _villes_hopitaux(dept, data)
    p["typologie"] = str(row.get("typologie", "inconnu"))
    p["is_dom"] = bool(row.get("is_dom", False))
    return p


# ══════════════════════════════════════════════════════════════════════════════
# 2. CATALOGUE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Condition:
    label: str
    test: Callable[[dict], bool | None]   # None = donnée absente (condition ignorée)
    poids: float = 1.0
    requise: bool = False


@dataclass
class Levier:
    id: str
    famille: str
    titre: str
    public: str
    conditions: list[Condition]
    texte: Callable[[dict], dict]
    exclusions: list[Condition] = field(default_factory=list)
    priorite: float = 1.0          # multiplicateur du score de correspondance
    dispositifs: list[str] = field(default_factory=list)
    horizon: str = "Moyen terme"
    kind: str = "generique"        # clé pour action_impact / PDF


def _f(v, spec=".1f", suffix=""):
    """Nombre au format français (virgule décimale, espace fine pour les milliers)."""
    if pd.isna(v):
        return "N/D"
    txt = f"{v:{spec}}".replace(",", "\u202f").replace(".", ",")
    return txt + suffix


def _pc(v) -> str:
    """Part en pourcentage, entier, espace fine avant le signe."""
    return f"{v * 100:.0f}\u202f%" if pd.notna(v) else "N/D"


def _n(v):
    return f"{int(round(v)):,}".replace(",", " ") if pd.notna(v) else "N/D"


def _lt(key, seuil):            # valeur < seuil (None si absente)
    return lambda p: (p.get(key) < seuil) if pd.notna(p.get(key)) else None


def _gt(key, seuil):
    return lambda p: (p.get(key) > seuil) if pd.notna(p.get(key)) else None


def _pct_lt(key, seuil):        # percentile national de `key` < seuil
    return lambda p: (p.get(f"pct_{key}") < seuil) if pd.notna(p.get(f"pct_{key}")) else None


def _pct_gt(key, seuil):
    return lambda p: (p.get(f"pct_{key}") > seuil) if pd.notna(p.get(f"pct_{key}")) else None


def _above_med(key, ratio=1.0):   # valeur > médiane nationale × ratio
    def t(p):
        v, m = p.get(key), p.get("med", {}).get(key)
        return (v > m * ratio) if pd.notna(v) and m is not None and pd.notna(m) else None
    return t


def _below_med(key, ratio=1.0):
    def t(p):
        v, m = p.get(key), p.get("med", {}).get(key)
        return (v < m * ratio) if pd.notna(v) and m is not None and pd.notna(m) else None
    return t


def _rural(p):
    return p.get("typologie") in ("rural", "peri_urbain")


def _src_15(p) -> str:
    """Précision de source pour les comptes « à plus de 15 min » : INSEE 2025 (temps moyen communal
    et habitants des carreaux) ou, hors champ INSEE, indicateur interne historique."""
    return " · INSEE 2025" if p.get("communes_critiques_source", "insee") == "insee" else " · indicateur interne, hors champ INSEE"


def _urbain(p):
    return p.get("typologie") in ("urbain", "urbain_dense")


def _secteurs_eloignes(p, n=3) -> str:
    c = p.get("communes_eloignees") or []
    if not c:
        return ""
    return ", ".join(f"{nom} ({_n(hab)} hab., {int(t)} min)" if hab else f"{nom} ({int(t)} min)"
                     for nom, hab, t in c[:n])


def _specialites_faibles(p, seuil=30) -> list[str]:
    out = []
    for k, lab in POSTE_LABELS.items():
        pc = p.get(f"pct_dens_{k}")
        if pd.notna(pc) and pc < seuil:
            out.append((pc, lab, p.get(f"dens_{k}"), p["med"].get(f"dens_{k}")))
    return [f"{lab} : {_f(d)} pour 100 000 hab. (médiane des départements : {_f(m)})" for _, lab, d, m in sorted(out)]


# ── Gabarits de texte ─────────────────────────────────────────────────────────

def _t_msp(p):
    return {
        "probleme": f"L'accès aux généralistes est insuffisant : {_pc(p['part_pop_apl_inf_2_5'])} des "
                    f"habitants {p['nom_de']} vivent dans une commune sous le repère APL de 2,5 "
                    f"(APL pondéré {_f(p['apl_dept'], '.2f')}, médiane des départements {_f(p['med']['apl_dept'], '.2f')}).",
        "indicateurs": [f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane des départements : {_f(p['med'].get('apl_dept'), '.2f')})",
                        f"{_pc(p['part_pop_apl_inf_2_5'])} de la population sous 2,5",
                        f"{_f(p['med_gen_pour_100k'], '.0f')} généralistes /100k (médiane {_f(p['med']['med_gen_pour_100k'], '.0f')})",
                        f"{_f(p['centres_sante_100k'], '.1f')} centres de santé /100k"],
        "action": "Soutenir des maisons de santé pluriprofessionnelles (MSP) et l'exercice coordonné "
                  "dans les secteurs sous-dotés, avec l'accord conventionnel interprofessionnel (ACI).",
        "pourquoi": "L'exercice regroupé est le cadre le plus attractif pour les jeunes généralistes "
                    "et permet de mutualiser infirmiers, assistants médicaux et protocoles de coopération ; "
                    "il est le point d'appui des dispositifs d'accès (SAS, consultations avancées).",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Diagnostic des projets de santé existants (ARS, CPTS), foncier communal "
                          "ou intercommunal, financement ACI et aides régionales à l'investissement.",
    }


def _t_attractivite(p):
    return {
        "probleme": f"La densité de généralistes {p['nom_de']} ({_f(p['med_gen_pour_100k'], '.0f')} /100k) "
                    f"se situe dans le {p['pct_med_gen_pour_100k']:.0f}ᵉ percentile national.",
        "indicateurs": [f"{_f(p['med_gen_pour_100k'], '.0f')} généralistes pour 100 000 hab. (médiane : {_f(p['med'].get('med_gen_pour_100k'), '.0f')} · DREES 2026)",
                        f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})",
                        f"{_pc(p['part_pop_apl_inf_2_5'])} de la population sous 2,5"],
        "action": "Mobiliser les aides à l'installation et au maintien (zonage ZIP/ZAC, contrat de "
                  "début d'exercice, guichet unique, accueil des internes et docteurs juniors).",
        "pourquoi": "Dans un département où l'offre est faible relativement à la population, le levier "
                    "démographique prime : chaque installation pèse davantage que dans un territoire dense.",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Révision du zonage avec l'ARS, coordination avec la faculté de médecine de "
                          "rattachement, logement et accueil des stagiaires.",
    }


def _t_assistants(p):
    return {
        "probleme": f"Les généralistes {p['nom_de']} sont peu nombreux rapportés aux habitants "
                    f"({_f(p['med_gen_pour_100k'], '.0f')} /100k) et l'APL pondéré ({_f(p['apl_dept'], '.2f')}) "
                    "reste sous la médiane : le temps médical disponible est la contrainte.",
        "indicateurs": [f"{_f(p['med_gen_pour_100k'], '.0f')} généralistes pour 100 000 hab. (médiane : {_f(p['med'].get('med_gen_pour_100k'), '.0f')})",
                        f"APL pondéré {_f(p['apl_dept'], '.2f')} (médiane {_f(p['med']['apl_dept'], '.2f')})"],
        "action": "Développer les assistants médicaux et les protocoles de coopération "
                  "(infirmiers en pratique avancée, pharmaciens) pour augmenter la patientèle "
                  "par médecin sans attendre de nouvelles installations.",
        "pourquoi": "Lorsque l'installation ne suffit pas à court terme, libérer du temps médical "
                    "est le levier le plus rapide sur l'accessibilité potentielle.",
        "secteurs": "",
        "mise_en_oeuvre": "Financement conventionnel des assistants médicaux, appui de la CPAM et des CPTS.",
    }


def _t_sas(p):
    return {
        "probleme": f"{p['nom_sujet']} cumule une population urbaine importante ({_n(p['population_num'])} hab.) "
                    f"et un APL pondéré de {_f(p['apl_dept'], '.2f')} : les demandes de soins non programmés "
                    "se reportent sur les urgences.",
        "indicateurs": [f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})", f"{_f(p['med_gen_pour_100k'], '.0f')} généralistes pour 100 000 hab. (médiane : {_f(p['med'].get('med_gen_pour_100k'), '.0f')})",
                        f"{_f(p['structures_pour_100k'])} structures hospitalières /100k"],
        "action": "Consolider le service d'accès aux soins (SAS) et la régulation des soins non "
                  "programmés, avec des créneaux dédiés en centres et maisons de santé.",
        "pourquoi": "En milieu urbain sous-doté, la régulation territoriale réduit les passages aux "
                    "urgences évitables plus vite qu'une hausse de l'offre.",
        "secteurs": ", ".join(p.get("villes_hopitaux") or []),
        "mise_en_oeuvre": "Pilotage ARS-SAMU-CPTS, effecteurs de ville volontaires, outil de prise de rendez-vous partagé.",
    }


def _t_consult_avancees(p):
    faibles = _specialites_faibles(p)
    return {
        "probleme": f"Plusieurs spécialités sont peu représentées {p['nom_dans']} : " + " ; ".join(faibles[:3]) + ".",
        "indicateurs": faibles[:4],
        "action": "Organiser des consultations avancées de spécialistes hospitaliers dans les "
                  "maisons et centres de santé, et des équipes mobiles de spécialités.",
        "pourquoi": "Déplacer périodiquement le spécialiste vers le territoire évite des trajets "
                    "longs aux patients et s'appuie sur les établissements existants "
                    + (f"({', '.join(p['villes_hopitaux'])})" if p.get("villes_hopitaux") else "") + ".",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Conventions établissement-structures d'exercice coordonné, temps médical partagé, "
                          "locaux de consultation.",
    }


def _t_equipes_mobiles(p):
    return {
        "probleme": f"{_n(p['pop_communes_critiques'])} habitants {p['nom_de']} vivent à plus de 15 minutes en voiture "
                    f"d'un médecin généraliste ({_pc(p['part_pop_communes_critiques'])} de la population ; "
                    f"{int(p['nb_communes_critiques'])} communes dépassent 15 min en moyenne{_src_15(p)}).",
        "indicateurs": [f"{int(p['nb_communes_critiques'])} communes à plus de 15 min en moyenne",
                        f"{_n(p['pop_communes_critiques'])} habitants à plus de 15 min",
                        f"temps médian {_f(p['temps_acces_median'], '.1f')} min (médiane des départements {_f(p['med'].get('temps_acces_median'), '.1f')})"],
        "action": "Déployer des équipes mobiles de soins primaires et de prévention (bus santé, "
                  "permanences itinérantes) sur les secteurs les plus éloignés.",
        "pourquoi": "Quand l'isolement est concentré sur quelques communes peuplées, une offre "
                    "itinérante couvre davantage d'habitants qu'une implantation fixe supplémentaire.",
        "secteurs": _secteurs_eloignes(p, 4),
        "mise_en_oeuvre": "Portage par un centre de santé, une MSP ou un établissement ; calendrier "
                          "de tournées ; coordination avec les communes d'accueil.",
    }


def _t_teleconsultation(p):
    return {
        "probleme": f"{p['nom_dans'][0].upper() + p['nom_dans'][1:]}, {_pc(p['part_pop_apl_inf_2_5'])} des habitants sont sous le repère APL "
                    f"et le temps médian vers un généraliste ({_f(p['temps_acces_median'], '.1f')} min) dépasse la médiane des "
                    f"départements ({_f(p['med'].get('temps_acces_median'), '.1f')} min).",
        "indicateurs": [f"{_pc(p['part_pop_apl_inf_2_5'])} de la population dans une commune sous le repère APL 2,5",
                        f"temps médian {_f(p['temps_acces_median'], '.1f')} min (médiane des départements {_f(p['med'].get('temps_acces_median'), '.1f')})",
                        f"{int(p['nb_communes_critiques'])} communes à plus de 15 min en moyenne{_src_15(p)}"],
        "action": "Installer des points de téléconsultation assistée (pharmacies, MSP, mairies) "
                  "avec un professionnel présent auprès du patient.",
        "pourquoi": "La téléconsultation assistée répond aux soins non programmés et au suivi des "
                    "patients chroniques sans déplacement, tout en restant dans le parcours coordonné.",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Cabines ou chariots connectés, formation des infirmiers et pharmaciens, "
                          "inscription dans le projet de la CPTS.",
    }


def _t_teleexpertise(p):
    faibles = _specialites_faibles(p)
    return {
        "probleme": f"L'accès aux spécialistes est contraint {p['nom_dans']} ({len(faibles)} spécialités "
                    "sous le 30ᵉ percentile national) : " + " ; ".join(faibles[:3]) + ".",
        "indicateurs": faibles[:4],
        "action": "Généraliser la téléexpertise (avis de spécialiste sollicité par le généraliste) "
                  "pour la dermatologie, la cardiologie et l'ophtalmologie en priorité.",
        "pourquoi": "La téléexpertise évite un rendez-vous de spécialiste pour une part des demandes "
                    "et raccourcit les délais là où les spécialistes sont rares.",
        "secteurs": "",
        "mise_en_oeuvre": "Plateforme régionale de téléexpertise, rémunération conventionnelle (requérant et requis).",
    }


def _t_sante_mentale(p):
    dens_txt = (f", avec {_f(p['dens_psychiatrie'])} psychiatres pour 100\u202f000 hab. "
                f"(médiane des départements\u202f: {_f(p['med']['dens_psychiatrie'])})."
                if pd.notna(p.get("dens_psychiatrie")) else "\u202f; la densité de psychiatres n'est pas disponible.")
    return {
        "probleme": f"La prévalence standardisée des troubles psychiatriques atteint {_f(p['prevstd_psy'], '.2f')}\u202f% "
                    f"{p['nom_dans']} (médiane {_f(p['med']['prevstd_psy'], '.2f')}\u202f%)" + dens_txt,
        "indicateurs": [f"{_n(p['patients_psy'])} patients suivis pour troubles psychiatriques (CNAM 2023)"]
                       + ([f"{_f(p['dens_psychiatrie'])} psychiatres /100k"] if pd.notna(p.get("dens_psychiatrie")) else [])
                       + [f"{int(p['nb_chs_psychiatrie'])} sites de centres hospitaliers spécialisés"],
        "action": "Renforcer le premier recours en santé mentale : Mon soutien psy, infirmiers en "
                  "pratique avancée en psychiatrie, équipes mobiles (EMPP) et coordination CPTS–secteur.",
        "pourquoi": "Quand la demande est élevée et les psychiatres peu nombreux, l'enjeu est la "
                    "gradation des prises en charge et le repérage précoce par les généralistes.",
        "secteurs": "",
        "mise_en_oeuvre": "Projet territorial de santé mentale (PTSM), conventions avec le secteur psychiatrique.",
    }


def _t_cardio(p):
    return {
        "probleme": f"Les maladies cardio-neuro-vasculaires touchent {_f(p['prevstd_cardio'], '.2f')} % des assurés "
                    f"{p['nom_de']} à structure d'âge comparable (médiane {_f(p['med']['prevstd_cardio'], '.2f')} %).",
        "indicateurs": [f"{_n(p['patients_cardio'])} patients pris en charge (CNAM 2023)",
                        f"prévalence brute {_f(p['prev_cardio'], '.2f')} %, standardisée {_f(p['prevstd_cardio'], '.2f')} %",
                        f"{_f(p['dens_cardiologie'])} cardiologues /100k"],
        "action": "Déployer Mon Bilan Prévention et des parcours de prévention cardiovasculaire "
                  "(repérage de l'hypertension, du tabagisme et du diabète, activité physique adaptée).",
        "pourquoi": "Une prévalence élevée à âge égal signale des facteurs de risque modifiables ; "
                    "la prévention primaire et secondaire y a le meilleur rendement.",
        "secteurs": "",
        "mise_en_oeuvre": "Pharmaciens et infirmiers pour les bilans, maisons sport-santé, programmes d'éducation thérapeutique.",
    }


def _t_diabete(p):
    return {
        "probleme": f"Le diabète concerne {_f(p['prevstd_diabete'], '.2f')} % des assurés {p['nom_de']} à âge "
                    f"comparable (médiane {_f(p['med']['prevstd_diabete'], '.2f')} %).",
        "indicateurs": [f"{_n(p['patients_diabete'])} patients diabétiques (CNAM 2023)",
                        f"prévalence standardisée {_f(p['prevstd_diabete'], '.2f')} %"],
        "action": "Intensifier le dépistage du diabète et le suivi des complications (rétinopathie, "
                  "pied diabétique) via l'éducation thérapeutique et le programme Sophia.",
        "pourquoi": "Le diabète est la pathologie chronique où le suivi de proximité (pharmacien, infirmier, "
                    "podologue) réduit le plus les complications évitables.",
        "secteurs": "",
        "mise_en_oeuvre": "Dépistage opportuniste en pharmacie et centres de santé, rétinographes itinérants.",
    }


def _t_depistages(p):
    return {
        "probleme": f"{p['nom_sujet']} présente une prévalence de cancers de {_f(p['prevstd_cancers'], '.2f')} % "
                    f"(standardisée, médiane {_f(p['med']['prevstd_cancers'], '.2f')} %) et "
                    f"{_f(p['pct_plus_65'])} % de 65 ans et plus.",
        "indicateurs": [f"{_n(p['patients_cancers'])} patients suivis pour cancer (CNAM 2023)",
                        f"{_f(p['pct_plus_65'])} % de 65 ans et plus"],
        "action": "Renforcer la participation aux dépistages organisés (colorectal 50-74 ans, sein 50-74 ans, "
                  "col de l'utérus 25-65 ans) avec le centre régional de coordination.",
        "pourquoi": "Dans un département âgé et à prévalence élevée, le gain de la participation "
                    "au dépistage organisé est le plus direct sur la mortalité évitable.",
        "secteurs": "",
        "mise_en_oeuvre": "Invitations et relances, mammobile ou unités mobiles sur les communes éloignées, pharmacies relais.",
    }


def _t_perinatalite(p):
    return {
        "probleme": f"{p['nom_sujet']} compte {_f(p['pct_moins_25'])} % de moins de 25 ans (médiane "
                    f"{_f(p['med']['pct_moins_25'])} %) pour {_f(p['dens_sages_femmes'])} sages-femmes et "
                    f"{_f(p['dens_gynecologie'])} gynécologues /100k.",
        "indicateurs": [f"{_f(p['pct_moins_25'])} % de moins de 25 ans",
                        f"{_f(p['dens_sages_femmes'])} sages-femmes /100k (médiane {_f(p['med']['dens_sages_femmes'])})",
                        f"{_f(p['dens_gynecologie'])} gynécologues /100k",
                        f"{_f(p['dens_pediatrie'])} pédiatres /100k"],
        "action": "Renforcer la protection maternelle et infantile (PMI), les sages-femmes de premier "
                  "recours et le suivi de grossesse de proximité.",
        "pourquoi": "Une population jeune avec peu de professionnels de la périnatalité expose à des "
                    "suivis tardifs ; la PMI et les sages-femmes couvrent l'essentiel du suivi à bas risque.",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Conseil départemental (PMI), conventions avec les maternités, sages-femmes libérales en MSP.",
    }


def _t_pediatrie(p):
    return {
        "probleme": f"La part des moins de 25 ans ({_f(p['pct_moins_25'])} %) est élevée {p['nom_dans']} "
                    f"alors que la densité de pédiatres ({_f(p['dens_pediatrie'])} /100k) est dans le "
                    f"{p['pct_dens_pediatrie']:.0f}ᵉ percentile.",
        "indicateurs": [f"{_f(p['pct_moins_25'])} % de moins de 25 ans",
                        f"{_f(p['dens_pediatrie'])} pédiatres /100k (médiane {_f(p['med']['dens_pediatrie'])})"],
        "action": "Structurer la santé de l'enfant en premier recours : généralistes formés, "
                  "consultations pédiatriques avancées, santé scolaire et vaccination.",
        "pourquoi": "Le suivi des enfants repose sur les généralistes quand les pédiatres manquent ; "
                    "la coordination évite les ruptures de suivi (examens obligatoires, vaccination).",
        "secteurs": "",
        "mise_en_oeuvre": "Protocoles de coopération, PMI, médecine scolaire, consultations avancées depuis l'hôpital.",
    }


def _t_autonomie(p):
    seniors = p["population_num"] * p["pct_plus_65"] / 100
    return {
        "probleme": f"{p['nom_sujet']} compte {_n(seniors)} habitants de 65 ans et plus ({_f(p['pct_plus_65'])} %, "
                    f"médiane {_f(p['med']['pct_plus_65'])} %) avec un APL pondéré de {_f(p['apl_dept'], '.2f')}.",
        "indicateurs": [f"{_f(p['pct_plus_65'])} % de 65 ans et plus",
                        f"{_n(seniors)} seniors (INSEE 2021)",
                        f"{_f(p['had_100k'], '.2f')} sites d'hospitalisation à domicile /100k",
                        f"{_n(p['patients_neuro'])} patients suivis pour maladies neurologiques"],
        "action": "Déployer le repérage de la fragilité (ICOPE), les parcours gériatriques et "
                  "l'hospitalisation à domicile en appui des EHPAD et du maintien à domicile.",
        "pourquoi": "Le vieillissement concentre la demande de soins ; repérer la perte d'autonomie "
                    "avant la rupture réduit les hospitalisations évitables.",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Dispositif d'appui à la coordination (DAC), équipes mobiles de gériatrie, HAD.",
    }


def _t_chroniques(p):
    pathos = [(p.get(f"prevstd_{k}"), PATHO_LABELS[k]) for k in ("diabete", "cardio", "respi")
              if pd.notna(p.get(f"prevstd_{k}")) and p.get(f"prevstd_{k}") > p["med"].get(f"prevstd_{k}", 0) * 1.1]
    libs = ", ".join(l for _, l in pathos) or "pathologies chroniques"
    return {
        "probleme": f"{p['nom_sujet']} combine des prévalences élevées à âge comparable ({libs}) et un accès "
                    f"aux généralistes limité (APL pondéré {_f(p['apl_dept'], '.2f')}).",
        "indicateurs": [f"{PATHO_LABELS[k]} : {_f(p.get(f'prevstd_{k}'), '.2f')} % standardisée"
                        for k in ("diabete", "cardio", "respi") if pd.notna(p.get(f"prevstd_{k}"))]
                       + [f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})"],
        "action": "Organiser le télésuivi et l'éducation thérapeutique des patients chroniques "
                  "(infirmiers en pratique avancée, pharmaciens, télésurveillance remboursée).",
        "pourquoi": "Quand les généralistes sont peu disponibles, le suivi délégué et à distance "
                    "sécurise les patients chroniques entre deux consultations.",
        "secteurs": "",
        "mise_en_oeuvre": "Inscription dans les projets CPTS, télésurveillance (droit commun depuis 2023).",
    }


def _t_mobilite(p):
    return {
        "probleme": f"{p['nom_dans'][0].upper() + p['nom_dans'][1:]}, {_n(p['pop_communes_critiques'])} habitants sont à plus de 15 min en voiture "
                    f"d'un généraliste{_src_15(p)} et {_f(p['pct_plus_65'])} % de la population a 65 ans ou plus.",
        "indicateurs": [f"{int(p['nb_communes_critiques'])} communes à plus de 15 min en moyenne",
                        f"{_n(p['pop_communes_critiques'])} habitants à plus de 15 min",
                        f"{_f(p['pct_plus_65'])} % de 65 ans et plus"],
        "action": "Organiser le transport solidaire et des navettes vers les lieux de soins "
                  "(transport à la demande, bénévolat encadré, conventions avec les taxis).",
        "pourquoi": "Pour les personnes âgées sans véhicule, le trajet est le premier motif de "
                    "renoncement ; le transport solidaire est moins coûteux qu'une offre supplémentaire.",
        "secteurs": _secteurs_eloignes(p, 4),
        "mise_en_oeuvre": "Intercommunalités, Département (schéma mobilité), CCAS, associations.",
    }


def _t_mediation(p):
    return {
        "probleme": f"{p['nom_sujet']}, département urbain dense, présente un APL pondéré de {_f(p['apl_dept'], '.2f')} et "
                    f"une prévalence standardisée du diabète de {_f(p['prevstd_diabete'], '.2f')} % "
                    f"(médiane {_f(p['med']['prevstd_diabete'], '.2f')} %).",
        "indicateurs": [f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})", f"diabète standardisé {_f(p['prevstd_diabete'], '.2f')} %",
                        f"{_f(p['centres_sante_100k'])} centres de santé /100k"],
        "action": "Développer la médiation en santé et les centres de santé communautaires dans les "
                  "quartiers où le recours aux soins est faible.",
        "pourquoi": "En zone urbaine dense, la difficulté d'accès tient autant au non-recours qu'à "
                    "l'offre ; la médiation reconnecte les habitants au parcours de soins.",
        "secteurs": "",
        "mise_en_oeuvre": "Contrats locaux de santé, ateliers santé ville, financement ARS/politique de la ville.",
    }


def _t_ville_hopital(p):
    return {
        "probleme": f"{p['nom_sujet']} dispose de {int(p['nb_hopitaux'])} sites hospitaliers (CH, CHR) pour une "
                    f"patientèle chronique importante et un APL pondéré de {_f(p['apl_dept'], '.2f')}.",
        "indicateurs": [f"{int(p['nb_hopitaux'])} sites CH/CHR", f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})",
                        f"{_n(p['patients_cardio'])} patients cardio-neuro-vasculaires"],
        "action": "Structurer la coordination ville-hôpital : dispositif d'appui à la coordination (DAC), "
                  "sorties d'hospitalisation organisées, lettres de liaison et messagerie sécurisée.",
        "pourquoi": "Les relais hospitaliers existent ; le maillon faible est la continuité avec une "
                    "médecine de ville peu disponible.",
        "secteurs": ", ".join(p.get("villes_hopitaux") or []),
        "mise_en_oeuvre": "Convention CPTS-établissements, DAC départemental, outils numériques régionaux.",
    }


def _t_dom(p):
    couv = p.get("couverture_temps")
    note = (f" La couverture du fichier de temps d'accès n'est que de {_pc(couv)} des communes."
            if pd.notna(couv) and couv < 0.9 else "")
    return {
        "probleme": f"{p['nom_sujet']} cumule un APL pondéré de {_f(p['apl_dept'], '.2f')} ({_pc(p['part_pop_apl_inf_2_5'])} de la "
                    f"population sous 2,5) et des contraintes géographiques ultramarines.{note}",
        "indicateurs": [f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})", f"{_pc(p['part_pop_apl_inf_2_5'])} de la population sous le repère APL 2,5",
                        f"{_f(p['med_gen_pour_100k'], '.0f')} généralistes pour 100 000 hab. (médiane : {_f(p['med'].get('med_gen_pour_100k'), '.0f')})",
                        f"{_f(p['pct_moins_25'])} % de moins de 25 ans"],
        "action": "Adapter l'offre aux spécificités ultramarines : télémédecine avec les CHU de référence, "
                  "équipes mobiles (fluviales ou héliportées selon le territoire), centres délocalisés "
                  "de prévention et de soins, formation locale des professionnels.",
        "pourquoi": "Les distances, l'insularité et la jeunesse de la population rendent les "
                    "dispositifs métropolitains insuffisants ; la continuité repose sur le numérique "
                    "et les antennes de proximité.",
        "secteurs": _secteurs_eloignes(p),
        "mise_en_oeuvre": "Projet régional de santé ultramarin, coopération avec les établissements de référence.",
    }


def _t_maintien(p):
    """Aucun levier déclenché : veille, et poches communales d'éloignement si elles
    existent (le score départemental ne doit pas les masquer). Les seuils des
    leviers de proximité (≥ 3 % de la population à plus de 15 min) ne sont pas
    atteints : on le dit, avec les volumes observés."""
    nb = p.get("nb_communes_critiques")
    pop15 = p.get("pop_communes_critiques")
    part15 = p.get("part_pop_communes_critiques")
    poches = pd.notna(nb) and nb > 0
    probleme = (f"{p['nom_sujet']} ne déclenche aucun signal d'alerte départemental parmi les conditions suivies "
                f"(APL pondéré {_f(p['apl_dept'], '.2f')}, {_f(p['med_gen_pour_100k'], '.0f')} généralistes /100k, "
                "prévalences et démographie dans la norme).")
    indicateurs = [f"score Sant’active {_f(p['score_global'])}/100", f"APL pondérée {_f(p['apl_dept'], '.2f')} consult./an/hab. (médiane : {_f(p['med'].get('apl_dept'), '.2f')})"]
    action = ("Maintenir l'offre et anticiper les départs en retraite des généralistes ; partager les "
              "organisations qui fonctionnent avec les départements voisins.")
    if poches:
        probleme += (f" Des poches d'éloignement subsistent : {int(nb)} communes à plus de 15 min d'une offre de "
                     f"médecine générale, soit {_n(pop15)} habitants ({_pc(part15)} de la population), "
                     "sous le seuil de 3 % qui déclenche les leviers de proximité.")
        indicateurs.append(f"{int(nb)} communes > 15 min ({_n(pop15)} hab.)")
        action += (" Pour les communes éloignées, examiner des réponses légères et ciblées (permanences, "
                   "transport à la demande, téléconsultation assistée) à partir du zoom territorial ci-dessous.")
    return {
        "probleme": probleme,
        "indicateurs": indicateurs,
        "action": action,
        "pourquoi": "Une situation favorable se dégrade d'abord par la démographie médicale : "
                    "le suivi des âges des praticiens est le signal à surveiller."
                    + (" Les poches d'éloignement, trop peu peuplées pour un dispositif départemental, "
                       "relèvent d'une réponse communale ou intercommunale." if poches else ""),
        "secteurs": _secteurs_eloignes(p) if poches else "",
        "mise_en_oeuvre": "Observatoire départemental, anticipation des cessations d'activité (DREES, Ordre).",
    }


# ── Le catalogue ──────────────────────────────────────────────────────────────

CATALOGUE: list[Levier] = [
    Levier("msp", "Offre de premier recours", "Maisons de santé et exercice coordonné",
           "Habitants des communes sous le repère APL 2,5", [
               Condition("APL pondéré < 3", _lt("apl_dept", 3.0), requise=True),
               Condition("≥ 20 % de la population sous APL 2,5", _gt("part_pop_apl_inf_2_5", 0.20), 2),
               Condition("territoire rural ou péri-urbain", _rural, 1),
               Condition("peu de centres de santé (percentile < 50)", _pct_lt("centres_sante_100k", 50), 1),
           ], _t_msp, exclusions=[Condition("APL ≥ 3,5", _gt("apl_dept", 3.5))], priorite=1.0,
           dispositifs=["MSP / ACI (accord conventionnel interprofessionnel)", "CPTS"], horizon="Long terme", kind="msp"),
    Levier("attractivite", "Démographie médicale", "Attractivité et installation des généralistes",
           "Habitants des communes sous le repère APL 2,5", [
               Condition("densité de généralistes < 35ᵉ percentile", _pct_lt("med_gen_pour_100k", 35), 2, requise=True),
               Condition("≥ 20 % de la population sous APL 2,5", _gt("part_pop_apl_inf_2_5", 0.20), 1),
           ], _t_attractivite, exclusions=[Condition("APL ≥ 3,8", _gt("apl_dept", 3.8))], priorite=1.0,
           dispositifs=["Zonage ZIP/ZAC", "Contrat de début d'exercice", "Guichet unique installation"],
           horizon="Long terme", kind="attractivite_mg"),
    Levier("assistants", "Démographie médicale", "Assistants médicaux et protocoles de coopération",
           "Patientèle des généralistes", [
               Condition("APL pondéré sous la médiane", _below_med("apl_dept"), 1, requise=True),
               Condition("densité de généralistes sous la médiane", _below_med("med_gen_pour_100k"), 1, requise=True),
           ], _t_assistants, priorite=0.8, dispositifs=["Assistants médicaux (avenant 7)", "IPA"], horizon="Court terme",
           kind="attractivite_mg"),
    Levier("sas", "Accès aux soins non programmés", "Service d'accès aux soins et soins non programmés",
           "Population urbaine", [
               Condition("territoire urbain", _urbain, 1, requise=True),
               Condition("APL pondéré < 3", _lt("apl_dept", 3.0), 1, requise=True),
               Condition("population > 500 000", _gt("population_num", 500_000), 1),
           ], _t_sas, priorite=0.9, dispositifs=["SAS (service d'accès aux soins)"], horizon="Court terme",
           kind="telemedecine"),
    Levier("consult_avancees", "Accès aux spécialistes", "Consultations avancées et équipes mobiles de spécialistes",
           "Patients nécessitant un avis spécialisé", [
               Condition("≥ 2 spécialités sous le 30ᵉ percentile", lambda p: len(_specialites_faibles(p)) >= 2, 2, requise=True),
               Condition("au moins un centre hospitalier", _gt("nb_hopitaux", 0), 1, requise=True),
               Condition("territoire rural ou péri-urbain", _rural, 1),
           ], _t_consult_avancees, priorite=0.95, dispositifs=["Consultations avancées", "Postes partagés ville-hôpital"],
           horizon="Moyen terme", kind="antennes"),
    Levier("equipes_mobiles", "Proximité", "Équipes mobiles de soins primaires et de prévention",
           "Habitants des communes à plus de 15 min", [
               Condition("≥ 3 % de la population à plus de 15 min", _gt("part_pop_communes_critiques", 0.03), 2, requise=True),
               Condition("≥ 15 communes à plus de 15 min", _gt("nb_communes_critiques", 15), 1),
               Condition("territoire rural ou péri-urbain", _rural, 1),
           ], _t_equipes_mobiles, priorite=0.95, dispositifs=["Bus santé", "Permanences itinérantes"],
           horizon="Moyen terme", kind="antennes"),
    Levier("teleconsultation", "Numérique en santé", "Téléconsultation assistée de proximité",
           "Habitants des communes sous le repère APL 2,5", [
               Condition("≥ 25 % de la population sous APL 2,5", _gt("part_pop_apl_inf_2_5", 0.25), 2, requise=True),
               Condition("temps d'accès médian > médiane", _above_med("temps_acces_median"), 1),
               Condition("territoire rural ou péri-urbain", _rural, 1),
           ], _t_teleconsultation, priorite=0.85, dispositifs=["Téléconsultation assistée (pharmacies, MSP)"],
           horizon="Court terme", kind="telemedecine"),
    Levier("teleexpertise", "Numérique en santé", "Téléexpertise entre généralistes et spécialistes",
           "Patients en attente d'un avis spécialisé", [
               Condition("≥ 2 spécialités sous le 30ᵉ percentile", lambda p: len(_specialites_faibles(p)) >= 2, 2, requise=True),
               Condition("dermatologie, cardiologie ou ophtalmologie < 30ᵉ percentile",
                         lambda p: any((p.get(f"pct_dens_{k}") or 100) < 30 for k in ("dermatologie", "cardiologie", "ophtalmologie")), 1),
           ], _t_teleexpertise, priorite=0.8, dispositifs=["Téléexpertise (avenant 9)"], horizon="Court terme",
           kind="telemedecine"),
    Levier("sante_mentale", "Santé mentale", "Premier recours en santé mentale",
           "Personnes présentant des troubles psychiques", [
               Condition("prévalence psychiatrique standardisée > médiane × 1,1", _above_med("prevstd_psy", 1.1), 2),
               Condition("psychiatres < 30ᵉ percentile", _pct_lt("dens_psychiatrie", 30), 2),
               Condition("au moins un des deux signaux",
                         lambda p: (_above_med("prevstd_psy", 1.1)(p) or _pct_lt("dens_psychiatrie", 30)(p)), 0, requise=True),
           ], _t_sante_mentale, priorite=1.0, dispositifs=["Mon soutien psy", "EMPP", "IPA psychiatrie", "PTSM"],
           horizon="Moyen terme", kind="prevention_chroniques"),
    Levier("cardio", "Prévention", "Prévention cardio-neuro-vasculaire",
           "Adultes à risque cardiovasculaire", [
               Condition("prévalence cardio standardisée > médiane × 1,1", _above_med("prevstd_cardio", 1.1), 2, requise=True),
               Condition("cardiologues < 50ᵉ percentile", _pct_lt("dens_cardiologie", 50), 1),
           ], _t_cardio, priorite=0.9, dispositifs=["Mon Bilan Prévention", "Maisons sport-santé"], horizon="Court terme",
           kind="prevention_chroniques"),
    Levier("diabete", "Prévention", "Dépistage et suivi du diabète",
           "Personnes diabétiques ou à risque", [
               Condition("prévalence du diabète standardisée > médiane × 1,15", _above_med("prevstd_diabete", 1.15), 2, requise=True),
           ], _t_diabete, priorite=0.9, dispositifs=["Sophia", "Éducation thérapeutique"], horizon="Court terme",
           kind="prevention_chroniques"),
    Levier("depistages", "Prévention", "Dépistages organisés des cancers",
           "Personnes de 50 à 74 ans", [
               Condition("prévalence des cancers standardisée > médiane × 1,05", _above_med("prevstd_cancers", 1.05), 1, requise=True),
               Condition("part des 65+ > médiane", _above_med("pct_plus_65"), 1),
               Condition("communes à plus de 15 min", _gt("nb_communes_critiques", 5), 1),
           ], _t_depistages, priorite=0.75, dispositifs=["CRCDC", "Mammobile"], horizon="Court terme",
           kind="prevention_chroniques"),
    Levier("perinatalite", "Santé maternelle et infantile", "Protection maternelle et infantile et sages-femmes",
           "Femmes enceintes, jeunes enfants", [
               Condition("part des moins de 25 ans > médiane + 2 pts",
                         lambda p: (p["pct_moins_25"] > p["med"]["pct_moins_25"] + 2) if pd.notna(p.get("pct_moins_25")) else None, 1, requise=True),
               Condition("sages-femmes ou gynécologues < 40ᵉ percentile",
                         lambda p: (_pct_lt("dens_sages_femmes", 40)(p) or _pct_lt("dens_gynecologie", 40)(p)), 2, requise=True),
           ], _t_perinatalite, priorite=0.95, dispositifs=["PMI", "Sages-femmes référentes"], horizon="Moyen terme",
           kind="pediatrie"),
    Levier("pediatrie", "Santé maternelle et infantile", "Santé de l'enfant en premier recours",
           "Enfants et jeunes", [
               Condition("part des moins de 25 ans > médiane", _above_med("pct_moins_25"), 1, requise=True),
               Condition("pédiatres < 30ᵉ percentile", _pct_lt("dens_pediatrie", 30), 2, requise=True),
           ], _t_pediatrie, priorite=0.85, dispositifs=["PMI", "Santé scolaire"], horizon="Moyen terme", kind="pediatrie"),
    Levier("autonomie", "Vieillissement et autonomie", "Repérage de la fragilité et parcours gériatriques",
           "Personnes de 65 ans et plus", [
               Condition("part des 65+ > médiane + 2 pts",
                         lambda p: (p["pct_plus_65"] > p["med"]["pct_plus_65"] + 2) if pd.notna(p.get("pct_plus_65")) else None, 2, requise=True),
               Condition("APL pondéré < 3,5 ou communes éloignées",
                         lambda p: (_lt("apl_dept", 3.5)(p) or _gt("nb_communes_critiques", 10)(p)), 1, requise=True),
               Condition("HAD < 50ᵉ percentile", _pct_lt("had_100k", 50), 1),
           ], _t_autonomie, priorite=0.95, dispositifs=["ICOPE", "DAC", "HAD", "Équipes mobiles de gériatrie"],
           horizon="Moyen terme", kind="seniors_numerique"),
    Levier("chroniques", "Parcours", "Télésuivi et éducation thérapeutique des patients chroniques",
           "Patients chroniques", [
               Condition("≥ 1 prévalence chronique standardisée > médiane × 1,1",
                         lambda p: any((_above_med(f"prevstd_{k}", 1.1)(p) or False) for k in ("diabete", "cardio", "respi")), 2, requise=True),
               Condition("APL pondéré < 3", _lt("apl_dept", 3.0), 1, requise=True),
           ], _t_chroniques, priorite=0.85, dispositifs=["Télésurveillance", "ETP", "IPA"], horizon="Moyen terme",
           kind="prevention_chroniques"),
    Levier("mobilite", "Proximité", "Transport solidaire vers les soins",
           "Personnes âgées des communes éloignées", [
               Condition("≥ 3 % de la population à plus de 15 min", _gt("part_pop_communes_critiques", 0.03), 2, requise=True),
               Condition("part des 65+ > médiane", _above_med("pct_plus_65"), 1, requise=True),
           ], _t_mobilite, priorite=0.8, dispositifs=["Transport à la demande", "Transport solidaire"], horizon="Court terme",
           kind="navettes"),
    Levier("mediation", "Accès et non-recours", "Médiation en santé et centres de santé communautaires",
           "Habitants des quartiers à faible recours aux soins", [
               Condition("territoire urbain dense", lambda p: p.get("typologie") == "urbain_dense", 1, requise=True),
               Condition("APL pondéré < 3,5", _lt("apl_dept", 3.5), 1, requise=True),
               Condition("diabète standardisé > médiane × 1,1", _above_med("prevstd_diabete", 1.1), 2),
           ], _t_mediation, priorite=0.85, dispositifs=["Médiation en santé", "Contrats locaux de santé"],
           horizon="Moyen terme", kind="generique"),
    Levier("ville_hopital", "Coordination", "Coordination ville-hôpital",
           "Patients en parcours complexe", [
               Condition("≥ 2 sites CH/CHR", _gt("nb_hopitaux", 1), 1, requise=True),
               Condition("APL pondéré < 3", _lt("apl_dept", 3.0), 1, requise=True),
               Condition("cardio standardisé > médiane", _above_med("prevstd_cardio"), 1),
           ], _t_ville_hopital, priorite=0.75, dispositifs=["DAC", "Messagerie sécurisée"], horizon="Moyen terme",
           kind="generique"),
    Levier("dom", "Territoires ultramarins", "Dispositifs adaptés aux territoires ultramarins",
           "Population du territoire", [
               Condition("département d'outre-mer", lambda p: bool(p.get("is_dom")), 1, requise=True),
               Condition("APL pondéré < 3 ou ≥ 20 % sous 2,5",
                         lambda p: (_lt("apl_dept", 3.0)(p) or _gt("part_pop_apl_inf_2_5", 0.20)(p)), 2, requise=True),
           ], _t_dom, priorite=1.05, dispositifs=["Télémédecine avec CHU de référence", "Centres délocalisés"],
           horizon="Moyen terme", kind="generique"),
    Levier("maintien", "Veille", "Maintien des acquis et anticipation",
           "Population du territoire", [
               Condition("aucun signal d'alerte", lambda p: True, 0),
           ], _t_maintien, priorite=0.01, horizon="Long terme", kind="maintien"),
]
CATALOGUE_PAR_ID = {l.id: l for l in CATALOGUE}


# ══════════════════════════════════════════════════════════════════════════════
# 3. SÉLECTION
# ══════════════════════════════════════════════════════════════════════════════

def evaluer(levier: Levier, p: dict) -> dict | None:
    """Évalue un levier sur un profil : None si non déclenché, sinon score et détail."""
    if not p:
        return None
    for ex in levier.exclusions:
        if ex.test(p) is True:
            return None
    satisfaites, total, verif = 0.0, 0.0, []
    for c in levier.conditions:
        try:
            ok = c.test(p)
        except (KeyError, TypeError):
            ok = None
        if ok is None:
            if c.requise:
                return None          # donnée indispensable absente → pas de recommandation
            continue
        if c.requise and not ok:
            return None
        if c.poids:
            total += c.poids
            satisfaites += c.poids if ok else 0.0
        verif.append((c.label, bool(ok)))
    score = (satisfaites / total) if total > 0 else 1.0
    if score < 0.34:
        return None
    return {"id": levier.id, "score": round(score * levier.priorite, 3), "conditions": verif}


def selectionner(p: dict, n: int = 4, max_par_famille: int = 2) -> list[dict]:
    """Leviers retenus pour un profil, classés et diversifiés, avec textes rendus."""
    cands = []
    for lev in CATALOGUE:
        if lev.id == "maintien":
            continue
        ev = evaluer(lev, p)
        if ev:
            cands.append((lev, ev))
    cands.sort(key=lambda x: -x[1]["score"])
    retenus, par_famille = [], {}
    for lev, ev in cands:
        if par_famille.get(lev.famille, 0) >= max_par_famille:
            continue
        par_famille[lev.famille] = par_famille.get(lev.famille, 0) + 1
        retenus.append((lev, ev))
        if len(retenus) >= n:
            break
    if not retenus:
        retenus = [(CATALOGUE_PAR_ID["maintien"], {"id": "maintien", "score": 0.0, "conditions": []})]
    out = []
    for lev, ev in retenus:
        txt = lev.texte(p)
        out.append({
            "id": lev.id, "famille": lev.famille, "title": lev.titre, "public": lev.public,
            "kind": lev.kind, "horizon": lev.horizon, "dispositifs": lev.dispositifs,
            "score": ev["score"], "conditions": ev["conditions"], **txt,
            "prose": " ".join(x for x in (txt["probleme"], txt["action"], txt["pourquoi"]) if x),
            "stats": [(v.split(" ")[0], " ".join(v.split(" ")[1:])) for v in txt["indicateurs"][:3]],
        })
    return out


def leviers_region(dept_codes: list[str], data: dict) -> list[dict]:
    """Leviers déclenchés dans les départements d'une région, agrégés par levier."""
    agg: dict[str, dict] = {}
    names = data["master"].set_index("dept")["Nom du département"].to_dict()
    for d in dept_codes:
        p = profil(d, data)
        for lev in CATALOGUE:
            if lev.id == "maintien":
                continue
            ev = evaluer(lev, p)
            if not ev:
                continue
            a = agg.setdefault(lev.id, {"levier": lev, "depts": [], "scores": []})
            a["depts"].append((str(names.get(str(d).zfill(2), d)), ev["score"]))
            a["scores"].append(ev["score"])
            a.setdefault("profils", []).append((ev["score"], p))
    out = []
    for lid, a in agg.items():
        lev = a["levier"]
        # Formulation en clair : constat rédigé du département le plus concerné ;
        # les conditions du catalogue (traçabilité) restent disponibles à part.
        try:
            constat = str(lev.texte(max(a["profils"], key=lambda x: x[0])[1]).get("probleme", "")).strip()
        except Exception:
            constat = ""
        depts = [n for n, _ in sorted(a["depts"], key=lambda x: -x[1])]
        out.append({
            "id": lid, "famille": lev.famille, "intitule": lev.titre, "depts": depts,
            "public_cible": lev.public, "horizon": lev.horizon, "dispositifs": lev.dispositifs,
            "tension": constat or lev.famille,
            "conditions_catalogue": [c.label for c in lev.conditions if c.requise],
            "justification": (f"Règle du catalogue vérifiée dans {len(depts)} département{'s' if len(depts) > 1 else ''} "
                              f"({', '.join(depts[:3])}{'…' if len(depts) > 3 else ''})."),
            "score_moyen": sum(a["scores"]) / len(a["scores"]),
        })
    return out
