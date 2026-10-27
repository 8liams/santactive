"""Calcul du proxy de délai RDV par département via APL.

Méthodologie :
    La DREES (enquête 2016-2017) a établi que les délais d'attente sont
    corrélés à l'APL : plus l'APL est faible, plus les délais sont longs.
    On utilise cette relation pour estimer le délai départemental à partir
    du délai national et du ratio APL national / APL département.

    délai_estimé_dept = délai_national × (APL_médiane_nationale / APL_dept)

    Le résultat est plafonné à 3× le délai national (évite les valeurs
    aberrantes pour les DOM avec APL très bas).

    IMPORTANT : ces valeurs sont des ESTIMATIONS, pas des mesures directes.
    Les données DREES sont nationales (pas départementales) et datent de
    2016-2017. À remplacer par les données Doctolib départementales dès
    qu'elles seront disponibles en open data.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd


APL_SEUIL_DESERT = 2.5  # repère de sous-densité (zonage médecins généralistes), pas une définition légale


def load_delais_nationaux() -> pd.DataFrame:
    """Charge les délais DREES nationaux depuis le CSV local."""
    path = Path("static") / "data" / "delais_rdv_nationaux.csv"
    if not path.exists():
        return pd.DataFrame(
            columns=["specialite", "delai_median_jours",
                     "delai_moyen_jours", "source"]
        )
    df = pd.read_csv(path, sep=";")
    for col in ["delai_median_jours", "delai_moyen_jours", "delai_d1_jours",
                "delai_q1_jours", "delai_q3_jours", "delai_d9_jours"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_delais_proxy(
    dept_code: str,
    apl_dept: float,
    apl_nationale: float = 2.9,
) -> pd.DataFrame:
    """Calcule les délais estimés pour un département.

    Args:
        dept_code    : code département (pour la traçabilité)
        apl_dept     : APL du département (méthode config.APL_METHODE)
        apl_nationale: médiane des valeurs départementales (même méthode)

    Returns:
        DataFrame avec colonnes :
            specialite, delai_median_jours, delai_estime_jours,
            interpretation, source
    """
    df = load_delais_nationaux()
    if df.empty or pd.isna(apl_dept) or apl_dept <= 0:
        return df

    ratio = apl_nationale / apl_dept

    # Facteur d'ajustement : plafonné à 3.0 pour éviter les aberrations
    ratio_capped = min(ratio, 3.0)

    df = df.copy()
    df["delai_estime_jours"] = (
        df["delai_median_jours"] * ratio_capped
    ).round(0).astype(int)

    # Interprétation lisible
    def _interp(row) -> str:
        nat = row["delai_median_jours"]
        est = row["delai_estime_jours"]
        diff = est - nat
        if abs(diff) <= 3:
            return "conforme à la médiane nationale"
        elif diff > 0:
            return f"+{diff} j vs médiane nationale"
        else:
            return f"{diff} j vs médiane nationale"

    df["interpretation"] = df.apply(_interp, axis=1)
    df["dept"] = dept_code
    df["apl_dept"] = apl_dept
    df["methode"] = (
        f"Estimation : délai national × "
        f"(APL nat. {apl_nationale} / APL dept {apl_dept:.1f})"
    )

    return df


def is_desert_medical(apl: float) -> bool:
    """Retourne True si le département est en désert médical (APL < 2.5)."""
    return pd.notna(apl) and float(apl) < APL_SEUIL_DESERT


# ── Modèle v2 (expérimental) : facteur propre à chaque spécialité ─────────────
# Spécialité du fichier national → poste DREES (densité départementale) ;
# le généraliste reste modulé par l'APL (accessibilité effective), les
# spécialistes par leur densité DREES rapportée à la médiane des départements.
_SPEC_VERS_POSTE = {
    "Pédiatre": "10-Pédiatrie", "Gynécologue": "09-Gynécologie", "Cardiologue": "06-Cardiologie",
    "Dermatologue": "07-Dermatologie", "Ophtalmologue": "03-Ophtalmologie",
    "Radiologue": "13-Plateaux techniques",
}
_FACTEUR_BORNES = (0.7, 3.0)   # un facteur < 1 (offre abondante) est plafonné à 0,7 : non validé


def compute_delais_v2(dept_code: str, data: dict) -> pd.DataFrame:
    """Délais estimés v2 : médiane nationale DREES × facteur propre à la spécialité.

    - généraliste : facteur = APL de référence / APL du département ;
    - spécialistes couverts par la DREES : facteur = densité médiane des
      départements / densité du département (effectifs DREES 2026 rapportés à
      la population INSEE 2021) ;
    - chirurgien-dentiste : densité DREES des dentistes ;
    - rhumatologue (pas de poste DREES) : facteur du généraliste (repli v1).
    Facteur borné à [0,7 ; 3]. EXPÉRIMENTAL : aucune observation départementale
    de délais n'est disponible pour valider la relation densité → délai ; les
    résultats sont des ordres de grandeur, pas des délais observés.
    """
    nat = load_delais_nationaux()
    master = data["master"].set_index("dept")
    if nat.empty or dept_code not in master.index:
        return nat
    r = master.loc[dept_code]
    pop = master["population_num"].astype(float)
    apl_ref = float(pd.to_numeric(master["apl_dept"], errors="coerce").median())
    apl = float(r["apl_dept"]) if pd.notna(r.get("apl_dept")) else float("nan")
    f_gp = (apl_ref / apl) if pd.notna(apl) and apl > 0 else float("nan")

    drees = (data.get("drees") or {})
    med = drees.get("medecins"); autres = drees.get("autres")
    dens = {}
    if med is not None and not med.empty:
        ens = med[med["exercice"] == "0-Ensemble"]
        for spec, poste in _SPEC_VERS_POSTE.items():
            sub = ens[ens["specialites"] == poste].drop_duplicates("dept").set_index("dept")["effectif"]
            d = sub.reindex(pop.index) / pop * 100_000
            dens[spec] = (float(d.get(dept_code, float("nan"))), float(d.median()))
    if autres is not None and not autres.empty:
        a = autres[(autres["secteur_activite"].astype(str).str.startswith("00")) & (autres["exercice"] == "0-Ensemble")
                   & (autres["profession"] == "chirurgiens_dentistes")].drop_duplicates("dept").set_index("dept")["effectif"]
        d = a.reindex(pop.index) / pop * 100_000
        dens["Chirurgien-dentiste"] = (float(d.get(dept_code, float("nan"))), float(d.median()))

    rows = []
    for _, row in nat.iterrows():
        spec = str(row["specialite"])
        if spec == "Médecin généraliste":
            f, base = f_gp, f"APL {apl:.2f} vs {apl_ref:.2f}"
        elif spec in dens and pd.notna(dens[spec][0]) and dens[spec][0] > 0:
            f, base = dens[spec][1] / dens[spec][0], f"{dens[spec][0]:.1f} /100k vs médiane {dens[spec][1]:.1f}"
        else:
            f, base = f_gp, "repli : facteur généraliste (pas de poste DREES)"
        f = min(max(f, _FACTEUR_BORNES[0]), _FACTEUR_BORNES[1]) if pd.notna(f) else float("nan")
        est = round(float(row["delai_median_jours"]) * f) if pd.notna(f) else None
        rows.append({"specialite": spec, "delai_median_jours": row["delai_median_jours"],
                     "delai_estime_v2_jours": est, "facteur_v2": round(f, 2) if pd.notna(f) else None, "base_v2": base})
    return pd.DataFrame(rows)
