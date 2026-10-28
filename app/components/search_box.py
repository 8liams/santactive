"""Recherche territoriale : composant navigateur (iframe HTML autonome).

Pourquoi un composant maison : `streamlit-searchbox` affiche ses suggestions
dans le flux de la page (la carte est poussée vers le bas) et déclenche un
aller-retour serveur à chaque frappe. Ici :

- l'index (régions, départements, communes) est chargé une fois par le
  navigateur depuis /app/static/data/index_recherche.json (fichier généré par
  scripts/donnees/generer_index_recherche.py, servi par Streamlit) ;
- les suggestions s'affichent dans un menu flottant sous le champ, sans
  déplacer la mise en page (l'iframe est positionnée en absolu et ne grandit
  que lorsque le menu est ouvert) ;
- classement par pertinence (même règle que app/search.py : exact 100, préfixe
  95, début de mot 85, contenu 70 ; les communes −10), 7 résultats maximum,
  navigation au clavier, fermeture à la sélection, à Échap ou au clic
  extérieur ;
- la sélection navigue vers ?view=… (même mécanisme que les liens internes),
  donc aucun rerun Streamlit pendant la frappe.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

_CLOSED_HEIGHT = {"hero": 56, "nav": 40}


def _inline_index(master: pd.DataFrame) -> dict:
    """Régions et départements inclus dans la page (résultats immédiats) ; les
    communes sont chargées à la demande depuis le fichier statique."""
    regions = master[["Code région", "Nom de la région"]].drop_duplicates().dropna()
    depts = master[["dept", "Nom du département", "Code région", "Nom de la région"]].dropna()
    return {
        "regions": [{"c": str(r["Code région"]), "n": str(r["Nom de la région"])} for _, r in regions.iterrows()],
        "departements": [{"c": str(r["dept"]), "n": str(r["Nom du département"]), "pn": str(r["Nom de la région"])}
                         for _, r in depts.iterrows()],
        "noms_departements": dict(zip(depts["dept"].astype(str), depts["Nom du département"].astype(str))),
    }


def render_search_box(master: pd.DataFrame, *, key: str, variant: str = "hero",
                      placeholder: str = "Département, région ou commune…") -> None:
    """Affiche le champ de recherche. `variant` : "hero" (accueil) ou "nav" (barre)."""
    closed = _CLOSED_HEIGHT.get(variant, 48)
    idx = json.dumps(_inline_index(master), ensure_ascii=False)
    html = _TEMPLATE.replace("__INDEX__", idx).replace("__CLOSED__", str(closed)) \
        .replace("__VARIANT__", variant).replace("__PLACEHOLDER__", placeholder.replace('"', "&quot;"))
    with st.container(key=key):
        components.html(html, height=closed)
    st.markdown(
        f"<style>.st-key-{key}{{position:relative;height:{closed}px;min-height:{closed}px;"
        f"flex:0 0 {closed}px;z-index:60;}}"
        f".st-key-{key}>div{{position:absolute;top:0;left:0;right:0;}}"
        f".st-key-{key} iframe{{display:block;width:100%;}}</style>",
        unsafe_allow_html=True,
    )


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<style>
  html, body { margin:0; padding:0; background:transparent; font-family: Marianne, Inter, -apple-system, BlinkMacSystemFont, sans-serif; }
  * { box-sizing:border-box; }
  .wrap { position:relative; }
  .field { position:relative; display:flex; align-items:center; background:#fff; border:1px solid #C9C6BA; border-radius:6px; transition:border-color .15s, box-shadow .15s; }
  .field:focus-within { border-color:#1A3D8F; box-shadow:0 0 0 3px #E8EDF8; }
  .field svg { position:absolute; left:14px; width:18px; height:18px; color:#6B6B68; pointer-events:none; }
  input { width:100%; border:0; outline:0; background:transparent; color:#0A1938; font-family:inherit; }
  input::placeholder { color:#8E8C84; }
  .hero .field { height:54px; } .hero input { padding:0 44px 0 44px; font-size:16px; }
  .nav .field { height:38px; border-radius:5px; } .nav input { padding:0 36px 0 38px; font-size:13px; }
  .nav .field svg { left:12px; width:15px; height:15px; }
  .hint { position:absolute; right:12px; top:50%; transform:translateY(-50%); font-size:11px; color:#9C9A92; border:1px solid #E8E6DD; border-radius:3px; padding:1px 6px; pointer-events:none; }
  .nav .hint { display:none; }
  .menu { position:absolute; left:0; right:0; top:calc(100% + 6px); background:#fff; border:1px solid #E8E6DD; border-radius:6px; box-shadow:0 12px 32px rgba(10,25,56,.14); overflow:hidden; display:none; }
  .menu.open { display:block; }
  .item { display:flex; align-items:center; gap:12px; padding:10px 14px; cursor:pointer; border-bottom:1px solid #F3F2EC; }
  .item:last-child { border-bottom:0; }
  .item.active, .item:hover { background:#F3F6FC; }
  .name { font-size:14px; color:#0A1938; font-weight:500; flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .name b { font-weight:700; color:#1A3D8F; }
  .parent { font-size:12px; color:#6B6B68; white-space:nowrap; }
  .lvl { font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; border-radius:3px; padding:2px 7px; white-space:nowrap; }
  .lvl-region { background:#0A1938; color:#fff; } .lvl-departement { background:#E8EDF8; color:#1A3D8F; } .lvl-commune { background:#F3F2EC; color:#4B4B48; }
  .nav .item { padding:8px 12px; } .nav .name { font-size:13px; } .nav .parent { font-size:11px; }
  .empty, .loading { padding:12px 14px; font-size:13px; color:#6B6B68; }
  .foot { padding:6px 14px; font-size:11px; color:#9C9A92; background:#FAFAF8; border-top:1px solid #F3F2EC; }
</style></head>
<body class="__VARIANT__">
<div class="wrap">
  <div class="field">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input id="q" type="text" autocomplete="off" spellcheck="false" placeholder="__PLACEHOLDER__" aria-label="Rechercher un territoire" aria-autocomplete="list" aria-expanded="false" aria-controls="menu">
    <span class="hint">↵</span>
  </div>
  <div id="menu" class="menu" role="listbox"></div>
</div>
<script>
(function () {
  const INLINE = __INDEX__;
  const CLOSED = __CLOSED__;
  const MAX = 7;
  const q = document.getElementById('q');
  const menu = document.getElementById('menu');
  let communes = null, loading = false, items = [], active = -1;

  const norm = s => (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[-'’\s]+/g, ' ').trim();
  const score = (n, s) => n === s ? 100 : n.startsWith(s) ? 95 : n.split(' ').some(w => w.startsWith(s)) ? 85 : 70;
  const LVL = { region: 0, departement: 1, commune: 2 };
  const LABEL = { region: 'Région', departement: 'Département', commune: 'Commune' };

  const base = (() => {
    try { const p = window.parent.location.pathname; return p.endsWith('/') ? p.slice(0, -1) : p; } catch (e) { return ''; }
  })();

  function loadCommunes() {
    if (communes || loading) return;
    loading = true;
    fetch(base + '/app/static/data/index_recherche.json', { cache: 'force-cache' })
      .then(r => r.json())
      .then(d => { communes = d.communes.map(c => ({ n: c[0], d: c[1], k: norm(c[0]) })); loading = false; render(); })
      .catch(() => { loading = false; communes = []; });
  }

  function search(raw) {
    const s = norm(raw);
    if (s.length < 2) return [];
    const out = [];
    for (const r of INLINE.regions) { const k = norm(r.n); if (k.includes(s)) out.push({ level: 'region', code: r.c, name: r.n, parent: '', sc: score(k, s) }); }
    for (const d of INLINE.departements) {
      const k = norm(d.n); const codeOk = s.toUpperCase() === d.c || s.padStart(2, '0') === d.c;
      if (k.includes(s) || codeOk) out.push({ level: 'departement', code: d.c, name: d.n, parent: d.pn, sc: codeOk ? 100 : score(k, s) });
    }
    if (communes) {
      const hits = [];
      for (const c of communes) if (c.k.includes(s)) { hits.push({ level: 'commune', code: c.n + '|' + c.d, name: c.n, parent: (INLINE.noms_departements[c.d] || c.d), sc: score(c.k, s) - 10 }); if (hits.length > 60) break; }
      out.push(...hits);
    }
    out.sort((a, b) => (b.sc - a.sc) || (LVL[a.level] - LVL[b.level]) || a.name.localeCompare(b.name, 'fr'));
    return out.slice(0, MAX);
  }

  function setHeight(open) {
    const h = open ? CLOSED + 8 + menu.offsetHeight + 8 : CLOSED;
    window.parent.postMessage({ isStreamlitMessage: true, type: 'streamlit:setFrameHeight', height: h }, '*');
  }

  function highlight(name, raw) {
    const s = norm(raw); const k = norm(name); const i = k.indexOf(s);
    if (i < 0 || !s) return esc(name);
    return esc(name.slice(0, i)) + '<b>' + esc(name.slice(i, i + s.length)) + '</b>' + esc(name.slice(i + s.length));
  }
  const esc = t => t.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function render() {
    const raw = q.value;
    if (norm(raw).length < 2) { close(); return; }
    items = search(raw);
    let html = '';
    if (!items.length) html = (loading && !communes) ? '<div class="loading">Chargement des communes…</div>' : '<div class="empty">Aucun territoire trouvé.</div>';
    else html = items.map((it, i) =>
      `<div class="item${i === active ? ' active' : ''}" role="option" data-i="${i}">` +
      `<span class="name">${highlight(it.name, raw)}</span>` +
      (it.parent ? `<span class="parent">${esc(it.parent)}</span>` : '') +
      `<span class="lvl lvl-${it.level}">${LABEL[it.level]}</span></div>`).join('');
    html += '<div class="foot">↑↓ pour naviguer · Entrée pour ouvrir · Échap pour fermer</div>';
    menu.innerHTML = html; menu.classList.add('open'); q.setAttribute('aria-expanded', 'true');
    menu.querySelectorAll('.item').forEach(el => {
      el.addEventListener('mousedown', e => { e.preventDefault(); go(items[+el.dataset.i]); });
      el.addEventListener('mousemove', () => { active = +el.dataset.i; paint(); });
    });
    setHeight(true);
  }
  function paint() { menu.querySelectorAll('.item').forEach((el, i) => el.classList.toggle('active', i === active)); }
  function close() { menu.classList.remove('open'); menu.innerHTML = ''; active = -1; q.setAttribute('aria-expanded', 'false'); setHeight(false); }

  function go(it) {
    if (!it) return;
    const p = it.level === 'region' ? 'view=region&region_code=' : it.level === 'departement' ? 'view=dept&dept_code=' : 'view=commune&commune_code=';
    const url = (window.parent.location.pathname || '/') + '?' + p + encodeURIComponent(it.code);
    close();
    try { window.parent.location.assign(url); } catch (e) { window.location.assign(url); }
  }

  let t = null;
  q.addEventListener('input', () => { loadCommunes(); active = -1; clearTimeout(t); t = setTimeout(render, 60); });
  q.addEventListener('focus', () => { loadCommunes(); if (norm(q.value).length >= 2) render(); });
  q.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); if (!menu.classList.contains('open')) { render(); } active = Math.min(active + 1, items.length - 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); paint(); }
    else if (e.key === 'Enter') { e.preventDefault(); go(items[active >= 0 ? active : 0]); }
    else if (e.key === 'Escape') { close(); q.blur(); }
  });
  q.addEventListener('blur', () => setTimeout(close, 120));
  document.addEventListener('mousedown', e => { if (!e.target.closest('.wrap')) close(); });
})();
</script>
</body></html>"""
