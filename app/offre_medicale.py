"""Offre médicale départementale : effectifs officiels (DREES/RPPS) et présence locale.

Deux jeux de données, jamais mélangés :
- jeu A, `data["drees"]` : effectifs de professionnels (personnes distinctes,
  actifs au 1er janvier 2026, lieu de l'activité la plus récente), densités
  officielles DREES (population INSEE 2026) ;
- jeu B, `data["presence"]` : nombre de villes du département où la spécialité
  est recensée dans le fichier retraité par l'équipe (présence, pas effectif).

Les densités « /100k » de Sant'active rapportent l'effectif DREES à la
population municipale INSEE 2021 du projet, pour rester comparables aux autres
indicateurs ; la densité DREES (population 2026) est affichée à côté.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from .scoring import to_num

# Postes DREES (14) → libellé affiché et mots-clés de présence (fichier équipe)
POSTES_DREES: dict[str, tuple[str, list[str]]] = {
    "01-Médecine générale":       ("Médecins généralistes",       ["médecin généraliste"]),
    "06-Cardiologie":             ("Cardiologues",                ["cardiologue"]),
    "07-Dermatologie":            ("Dermatologues",               ["dermatologue"]),
    "03-Ophtalmologie":           ("Ophtalmologues",              ["ophtalmolog"]),
    "04-Oto-rhino-laryngologie":  ("ORL",                         ["oto-rhino"]),
    "08-Gastro-entérologie":      ("Gastro-entérologues",         ["gastro"]),
    "09-Gynécologie":             ("Gynécologues",                ["gynécologue"]),
    "10-Pédiatrie":               ("Pédiatres",                   ["pédiatre"]),
    "11-Pneumologie":             ("Pneumologues",                ["pneumologue"]),
    "12-Psychiatrie":             ("Psychiatres",                 ["psychiatre"]),
    "05-Anesthésie-Réanimation":  ("Anesthésistes-réanimateurs",  ["anesthésiste"]),
    "02-Chirurgie":               ("Chirurgiens (hors dentistes)", ["chirurgien "]),
    "13-Plateaux techniques":     ("Plateaux techniques (radiologie, biologie…)", ["radiologue", "biologiste"]),
    "14-Autre spécialité":        ("Autres spécialités",          []),
}
AUTRES_PROFESSIONS: dict[str, tuple[str, list[str], str]] = {
    "pharmaciens":           ("Pharmaciens",           ["pharmacien"],          "RPPS 2026"),
    "chirurgiens_dentistes": ("Chirurgiens-dentistes", ["chirurgien-dentiste"], "RPPS 2026"),
    "sages_femmes":          ("Sages-femmes",          ["sage-femme"],          "RPPS 2026"),
}
# Pathologies CNAM → poste DREES associé (badge « lié aux pathologies »)
PATHO_VERS_POSTE = {
    "ardio": "06-Cardiologie", "sychiatr": "12-Psychiatrie", "espira": "11-Pneumologie",
    "foie": "08-Gastro-entérologie",
}


def _presence(presence: pd.DataFrame | None, dept: str, mots: list[str]):
    """Nombre de villes du département où l'une des spécialités est recensée."""
    if presence is None or presence.empty or not mots:
        return float("nan")
    p = presence[presence["dept"].astype(str) == dept]
    lib = p["specialite_libelle"].astype(str).str.lower()
    mask = pd.Series(False, index=p.index)
    for m in mots:
        mask |= lib.str.startswith(m.lower()) | lib.str.contains(m.lower(), regex=False)
    return float(p.loc[mask, "nb_villes"].max()) if mask.any() else 0.0


def table_offre(r: pd.Series, data: dict) -> pd.DataFrame | None:
    """Lignes du tableau : effectif, densités, médiane nationale, écart, présence."""
    drees = data.get("drees") or {}
    med = drees.get("medecins")
    if med is None or med.empty:
        return None
    dept = str(r.get("dept", "")).zfill(2)
    pop = to_num(r.get("population_num"))
    master = data["master"]
    pop_ref = master.set_index("dept")["population_num"].astype(float)
    presence = data.get("presence")

    rows = []
    ens = med[med["exercice"] == "0-Ensemble"]
    for poste, (label, mots) in POSTES_DREES.items():
        sub = ens[ens["specialites"] == poste].drop_duplicates("dept").set_index("dept")
        if sub.empty:
            continue
        eff = to_num(sub["effectif"].get(dept))
        dens_nat = (sub["effectif"].reindex(pop_ref.index) / pop_ref * 100_000)
        rows.append({
            "groupe": "Médecins (DREES · RPPS au 1er janvier 2026)",
            "label": label, "effectif": eff,
            "pour_100k": eff / pop * 100_000 if pd.notna(eff) and pop > 0 else float("nan"),
            "densite_drees": to_num(sub["densite_drees"].get(dept)),
            "mediane_nat": float(dens_nat.median(skipna=True)),
            "presence_villes": _presence(presence, dept, mots),
            "poste": poste,
        })
    # Détail du mode d'exercice des généralistes (offre de ville)
    mg = med[(med["specialites"] == "01-Médecine générale") & (med["dept"] == dept)]
    modes = {str(x["exercice"]): to_num(x["effectif"]) for _, x in mg.iterrows()}

    autres = drees.get("autres")
    if autres is not None and not autres.empty:
        a = autres[(autres["secteur_activite"].astype(str).str.startswith("00"))
                   & (autres["exercice"] == "0-Ensemble")]
        for prof, (label, mots, src) in AUTRES_PROFESSIONS.items():
            sub = a[a["profession"] == prof].set_index("dept")
            if sub.empty:
                continue
            eff = to_num(sub["effectif"].get(dept))
            dens_nat = sub["effectif"].reindex(pop_ref.index) / pop_ref * 100_000
            rows.append({
                "groupe": "Autres professions de santé (DREES)",
                "label": f"{label} ({src})", "effectif": eff,
                "pour_100k": eff / pop * 100_000 if pd.notna(eff) and pop > 0 else float("nan"),
                "densite_drees": to_num(sub["densite_drees"].get(dept)),
                "mediane_nat": float(dens_nat.median(skipna=True)),
                "presence_villes": _presence(presence, dept, mots), "poste": prof,
            })
    idel = drees.get("idel")
    if idel is not None and not idel.empty:
        sub = idel.set_index("dept")
        eff = to_num(sub["effectif"].get(dept))
        dens_nat = sub["effectif"].reindex(pop_ref.index) / pop_ref * 100_000
        rows.append({
            "groupe": "Autres professions de santé (DREES)",
            "label": "Infirmières libérales (SNDS 2023)", "effectif": eff,
            "pour_100k": eff / pop * 100_000 if pd.notna(eff) and pop > 0 else float("nan"),
            "densite_drees": float("nan"), "mediane_nat": float(dens_nat.median(skipna=True)),
            "presence_villes": _presence(presence, dept, ["infirmier"]), "poste": "idel",
        })
    df = pd.DataFrame(rows)
    df.attrs["modes_mg"] = modes
    return df


def _top_pathos_postes(r: pd.Series, data: dict) -> set[str]:
    """Postes DREES associés aux pathologies à prévalence élevée du département."""
    from .pathologies import dept_prevalences

    prev = dept_prevalences(data.get("patho"), data["master"]["dept"])
    dept = str(r.get("dept", "")).zfill(2)
    if prev.empty or dept not in prev.index:
        return set()
    med = prev.median()
    postes = set()
    for frag, poste in PATHO_VERS_POSTE.items():
        cols = [c for c in prev.columns if frag in c.lower()]
        if cols and pd.notna(prev.loc[dept, cols[0]]) and prev.loc[dept, cols[0]] > med[cols[0]] * 1.10:
            postes.add(poste)
    return postes


def _fmt(v, spec: str, suffix: str = "") -> str:
    return f"{v:{spec}}{suffix}".replace(",", " ") if pd.notna(v) else "N/D"


def render_offre_medicale_drees(r: pd.Series, data: dict) -> bool:
    """Tableau d'offre médicale à partir des effectifs DREES. False si indisponible."""
    df = table_offre(r, data)
    if df is None or df.empty:
        return False
    dept_nom = html.escape(str(r.get("Nom du département", "")))
    postes_patho = _top_pathos_postes(r, data)
    modes = df.attrs.get("modes_mg", {})

    st.markdown(
        '<div class="section-header">'
        '<div class="section-eyebrow">OFFRE MÉDICALE</div>'
        '<h2 class="section-title">Combien de <em>professionnels,</em> et où ?</h2>'
        '<p class="section-lead">Effectifs officiels DREES (RPPS, actifs au '
        '1<sup>er</sup> janvier 2026, personnes distinctes) rapportés à la population '
        'INSEE 2021 du projet, comparés à la médiane des 100 départements analysés. '
        'La colonne « présence locale » compte les villes du département où la '
        'spécialité est recensée dans le fichier territorial de l\'équipe : '
        'c\'est une couverture, pas un effectif.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    grid = "grid-template-columns:2.6fr 0.8fr 0.8fr 0.9fr 0.8fr 0.7fr 0.9fr;"
    hcell = ('font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;'
             'color:rgba(255,255,255,0.5);text-align:right;')
    out = (
        '<div class="sa-tbl-scroll"><div style="min-width:640px;border:1px solid #E8E6DD;'
        'border-radius:6px;overflow:hidden;">'
        f'<div style="display:grid;{grid}padding:10px 16px;background:#0A1938;gap:0 8px;">'
        f'<div style="{hcell}text-align:left;">Profession</div>'
        f'<div style="{hcell}">Effectif</div><div style="{hcell}">/100k (2021)</div>'
        f'<div style="{hcell}">Densité DREES</div><div style="{hcell}">Méd. dépts</div>'
        f'<div style="{hcell}">Écart</div><div style="{hcell}">Présence locale</div>'
        '</div>'
    )
    i = 0
    for groupe, g in df.groupby("groupe", sort=False):
        out += (f'<div style="padding:8px 16px;background:#F3F2EC;font-size:10px;font-weight:700;'
                f'letter-spacing:0.1em;text-transform:uppercase;color:#6B6B68;'
                f'border-bottom:1px solid #E8E6DD;">{html.escape(groupe)}</div>')
        for _, row in g.iterrows():
            ecart = ((row["pour_100k"] - row["mediane_nat"]) / row["mediane_nat"] * 100
                     if pd.notna(row["pour_100k"]) and row["mediane_nat"] > 0 else float("nan"))
            col = ("#1B5E3F" if pd.notna(ecart) and ecart >= 10
                   else "#A51C30" if pd.notna(ecart) and ecart <= -10 else "#6B6B68")
            badge = ""
            if row["poste"] in postes_patho:
                badge = ('<span style="font-size:10px;background:#FEF3F2;color:#A51C30;'
                         'border:1px solid #FECDCA;border-radius:3px;padding:1px 6px;'
                         'margin-left:8px;font-weight:600;">prévalence élevée</span>')
            detail = ""
            if row["poste"] == "01-Médecine générale" and modes:
                lib = to_num(modes.get("1-Libéral")); mix = to_num(modes.get("2-Mixte"))
                detail = (f'<div style="font-size:11px;color:#9C9A92;">dont libéraux : '
                          f'{_fmt(lib, ".0f")} · mixtes : {_fmt(mix, ".0f")} · '
                          f'salariés : {_fmt(to_num(modes.get("3-Salarié hospitalier")) + to_num(modes.get("4-Autre Salarié")), ".0f")}</div>')
            eff_str = _fmt(row["effectif"], ",.0f") if pd.notna(row["effectif"]) else "&lt; 10"
            pres = row["presence_villes"]
            pres_str = f"{int(pres)} ville{'s' if pres > 1 else ''}" if pd.notna(pres) else "n.d."
            bg = "white" if i % 2 == 0 else "#FAFAF8"
            out += (
                f'<div style="display:grid;{grid}padding:10px 16px;background:{bg};'
                f'border-bottom:1px solid #E8E6DD;gap:0 8px;align-items:center;">'
                f'<div style="font-size:13px;color:#0A1938;font-weight:500;">{html.escape(row["label"])}{badge}{detail}</div>'
                f'<div style="font-size:13px;text-align:right;">{eff_str}</div>'
                f'<div style="font-size:13px;text-align:right;">{_fmt(row["pour_100k"], ".1f")}</div>'
                f'<div style="font-size:13px;color:#6B6B68;text-align:right;">{_fmt(row["densite_drees"], ".1f")}</div>'
                f'<div style="font-size:13px;color:#9C9A92;text-align:right;">{_fmt(row["mediane_nat"], ".1f")}</div>'
                f'<div style="font-size:13px;font-weight:600;color:{col};text-align:right;">'
                f'{(("+" if ecart >= 0 else "") + f"{ecart:.0f} %") if pd.notna(ecart) else "n.s."}</div>'
                f'<div style="font-size:12px;color:#6B6B68;text-align:right;">{pres_str}</div>'
                '</div>'
            )
            i += 1
    out += "</div></div>"
    st.markdown(out, unsafe_allow_html=True)
    st.markdown(
        '<div style="margin-top:10px;padding:12px 16px;background:#F3F2EC;border-radius:4px;'
        'font-size:12px;color:#6B6B68;line-height:1.6;">'
        '<strong style="color:#2B2B2B;">Lecture.</strong> Effectif = professionnels '
        'actifs occupés au 1<sup>er</sup> janvier 2026, comptés une fois au lieu de leur '
        'activité la plus récente (DREES, RPPS ; infirmières libérales : SNDS 2023). '
        '« &lt; 10 » = secret statistique. « /100k (2021) » = effectif / population '
        'municipale INSEE 2021 du projet ; « Densité DREES » = densité officielle '
        '(population INSEE 2026). L\'écart compare la densité 2021 à la médiane des '
        '100 départements analysés. Aucun « besoin » n\'est déduit de ce tableau : '
        'voir la simulation de capacité fondée sur l\'APL.'
        '</div>',
        unsafe_allow_html=True,
    )
    return True
