"""Territoire de référence global : France entière, une région ou un département.

Le territoire est conservé pendant la navigation (session) et dans l'URL
(paramètre ``t`` : ``fr``, ``r53`` pour une région, ``d18`` pour un
département) afin que les liens partagés rouvrent le même contexte. Il n'est
jamais un filtre bloquant : chaque page l'utilise comme point de départ
(pré-sélection, mise en évidence) et laisse l'utilisateur en changer.

Règles :
- ouvrir une fiche département ou région fait suivre le territoire de
  référence (on explore ce que l'on regarde) ;
- « France entière » remet le contexte national ;
- le territoire de référence est distinct du périmètre d'une comparaison ou
  d'une analyse (celui-ci peut le dépasser ou s'en écarter).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

SESSION_KEY = "territoire"
PARAM = "t"


@dataclass(frozen=True)
class Territoire:
    kind: str            # "fr" | "region" | "dept"
    code: str = ""       # code région ou code département (vide pour "fr")

    @property
    def param(self) -> str:
        if self.kind == "region":
            return f"r{self.code}"
        if self.kind == "dept":
            return f"d{self.code}"
        return "fr"

    @property
    def is_national(self) -> bool:
        return self.kind == "fr"


FRANCE = Territoire("fr")


def parse(value: str | None) -> Territoire | None:
    """``fr`` → France ; ``r53`` → région 53 ; ``d18`` → département 18."""
    if not value:
        return None
    v = str(value).strip()
    if v == "fr":
        return FRANCE
    if len(v) >= 2 and v[0] in ("r", "d"):
        code = v[1:]
        if v[0] == "d":
            code = code.zfill(2) if len(code) < 2 else code
        return Territoire("region" if v[0] == "r" else "dept", code)
    return None


def get() -> Territoire:
    t = st.session_state.get(SESSION_KEY)
    return t if isinstance(t, Territoire) else FRANCE


def set_territoire(t: Territoire, *, sync_url: bool = True) -> bool:
    """Enregistre le territoire ; retourne True s'il a changé."""
    changed = get() != t
    st.session_state[SESSION_KEY] = t
    if sync_url:
        try:
            if st.query_params.get(PARAM) != t.param:
                st.query_params[PARAM] = t.param
        except Exception:
            pass
    return changed


def init_from_url() -> None:
    """URL prioritaire (lien partagé), sinon session, sinon France entière."""
    raw = st.query_params.get(PARAM)
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    t = parse(raw)
    if t is not None:
        st.session_state[SESSION_KEY] = t
    elif SESSION_KEY not in st.session_state:
        st.session_state[SESSION_KEY] = FRANCE


def follow_dept(code: str) -> None:
    """La fiche d'un département devient le territoire de référence."""
    set_territoire(Territoire("dept", str(code).zfill(2)))


def follow_region(code: str) -> None:
    set_territoire(Territoire("region", str(code)))


# ── Lecture dans les données ──────────────────────────────────────────────────

def label(t: Territoire, master: pd.DataFrame) -> str:
    if t.kind == "dept":
        row = master[master["dept"] == t.code]
        return f"{row.iloc[0]['Nom du département']} ({t.code})" if not row.empty else f"Département {t.code}"
    if t.kind == "region":
        row = master[master["Code région"].astype(str) == t.code]
        return str(row.iloc[0]["Nom de la région"]) if not row.empty else f"Région {t.code}"
    return "France entière"


def nom_court(t: Territoire, master: pd.DataFrame) -> str:
    if t.kind == "dept":
        row = master[master["dept"] == t.code]
        return str(row.iloc[0]["Nom du département"]) if not row.empty else t.code
    if t.kind == "region":
        row = master[master["Code région"].astype(str) == t.code]
        return str(row.iloc[0]["Nom de la région"]) if not row.empty else t.code
    return "France entière"


def region_code(t: Territoire, master: pd.DataFrame) -> str | None:
    """Code région du territoire (celle du département si c'est un département)."""
    if t.kind == "region":
        return t.code
    if t.kind == "dept":
        row = master[master["dept"] == t.code]
        return str(row.iloc[0]["Code région"]) if not row.empty else None
    return None


def dept_codes(t: Territoire, master: pd.DataFrame) -> list[str]:
    """Départements du périmètre : tous, ceux de la région, ou le seul département."""
    if t.kind == "dept":
        return [t.code]
    if t.kind == "region":
        return master.loc[master["Code région"].astype(str) == t.code, "dept"].astype(str).tolist()
    return master["dept"].astype(str).tolist()


def row(t: Territoire, master: pd.DataFrame) -> pd.Series | None:
    """Ligne du master pour un département de référence (None sinon)."""
    if t.kind != "dept":
        return None
    r = master[master["dept"] == t.code]
    return r.iloc[0] if not r.empty else None


def options(master: pd.DataFrame) -> list[tuple[str, str]]:
    """Options du sélecteur : (valeur ``t``, libellé) — France, régions, départements."""
    opts = [("fr", "France entière")]
    regs = (master[["Code région", "Nom de la région"]].dropna().drop_duplicates()
            .sort_values("Nom de la région"))
    opts += [(f"r{c}", f"Région · {n}") for c, n in zip(regs["Code région"].astype(str), regs["Nom de la région"])]
    deps = master[["dept", "Nom du département"]].dropna().sort_values("Nom du département")
    opts += [(f"d{c}", f"{n} ({c})") for c, n in zip(deps["dept"].astype(str), deps["Nom du département"])]
    return opts
