"""Quick blind human spot-check: 30 of the 90 stratified validation claims (10 per group, seeded),
labelled SUPPORTED (at least the main point is in the sources) / NOT_SUPPORTED / CANT_TELL.

The binary question matches the primary outcome: judge NOT_IN_SOURCE or CONTRADICTED = not supported,
judge SUPPORTED or PARTIAL = supported. The page never shows the author group, status or any judge verdict.
To save time it shows the passages around the claim's key words (full text one click away).

  make    write data/interim/labeling/quick_label.html (open it in a browser)
  score   read the exported human_labels_quick.csv (Downloads or data/release) and compare with each judge

Run:  uv run python scripts/06b_quick_label.py make | score
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from common import INTERIM, RELEASE, SEED

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LAB = INTERIM / "labeling"
RUNS = INTERIM / "judge_runs"
STOP = set("""a an the and or but if then than that this these those there their they them it its is are was were be been
being to of in on at by for from with as into over under about after before between during not no nor
has have had do does did can could would should will shall may might must also only just very more most
said says say according reported report note post claim claims which who whom whose what when where why how
some any all each other such same own both few many much several one two three first second new""".split())


def keywords(claim: str) -> list[str]:
    words = re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", claim, flags=re.UNICODE)
    keep = [w for w in words if (len(w) >= 4 and w.lower() not in STOP) or any(ch.isdigit() for ch in w)]
    seen, out = set(), []
    for w in sorted(keep, key=len, reverse=True):
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out[:8]


def load_judge(name: str) -> pd.DataFrame:
    p = RUNS / f"verdicts_main_{name}.jsonl"
    if not p.exists():
        return pd.DataFrame(columns=["noteId", "claim_id", "label"])
    rows = [{"noteId": r["noteId"], "claim_id": v["claim_id"], "label": v["label"]}
            for l in p.read_text(encoding="utf-8").split("\n") if l.strip()
            for r in [json.loads(l)] for v in r.get("verdicts", [])]
    return pd.DataFrame(rows)


def make() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("judge", Path(__file__).with_name("05_judge.py"))
    J = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(J)
    key = pd.read_csv(LAB / "key.csv", dtype={"noteId": str})
    rng = np.random.default_rng(SEED + 30)
    pick = pd.concat([g.loc[rng.choice(g.index, size=min(10, len(g)), replace=False)] for _, g in key.groupby("group")])
    pick = pick.sample(frac=1, random_state=SEED + 31).reset_index(drop=True)
    pick["qid"] = [f"Q{i:02d}" for i in range(1, len(pick) + 1)]
    claims = {(r := json.loads(l))["noteId"]: {c["id"]: c["text"] for c in r["claims"]}
              for l in (RUNS / "claims_main.jsonl").read_text(encoding="utf-8").split("\n") if l.strip()}
    notes = J.load_notes("main").set_index("noteId")
    by_note = J.load_sources()
    payload = []
    for it in pick.itertuples():
        text = claims[it.noteId][it.claim_id]
        srcs = J.note_sources(type("N", (), {"noteId": it.noteId, "urls": notes.loc[it.noteId].urls}), by_note)
        payload.append({"q": it.qid, "claim": text, "kw": keywords(text),
                        "sources": [{"id": s["id"], "url": s["url"], "text": s["text"]} for s in srcs]})
    pick[["qid", "item_id", "noteId", "claim_id", "group", "weight"]].to_csv(LAB / "quick_key.csv", index=False)
    page = PAGE.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    (LAB / "quick_label.html").write_text(page, encoding="utf-8")
    print(f"{len(pick)} claims -> {LAB / 'quick_label.html'}  (per group: {pick.group.value_counts().to_dict()})")


def score() -> None:
    cands = [RELEASE / "human_labels_quick.csv", Path.home() / "Downloads" / "human_labels_quick.csv"]
    src = next((p for p in cands if p.exists()), None)
    if src is None:
        sys.exit("human_labels_quick.csv not found in data/release or Downloads")
    hum = pd.read_csv(src)
    hum.to_csv(RELEASE / "human_labels_quick.csv", index=False)
    key = pd.read_csv(LAB / "quick_key.csv", dtype={"noteId": str}).merge(hum[["qid", "label"]], on="qid")
    key = key[key.label.isin(["SUPPORTED", "NOT_SUPPORTED"])]
    key["h_unsup"] = key.label == "NOT_SUPPORTED"
    out = {"n_labelled": int(len(hum)), "n_usable": int(len(key)),
           "human_not_supported_share": round(float(key.h_unsup.mean()), 3)}
    for name, slug in (("claude_haiku_primary", "claude-haiku-5-5"), ("claude_opus_reference", "claude-opus-5-5"),
                       ("gemini_second", "gemini-3-5-flash-lite")):
        j = load_judge(slug)
        m = key.merge(j, on=["noteId", "claim_id"])
        m = m[m.label_y.isin(["SUPPORTED", "PARTIAL", "NOT_IN_SOURCE", "CONTRADICTED"])]
        if m.empty:
            continue
        ju = m.label_y.isin(["NOT_IN_SOURCE", "CONTRADICTED"])
        w = m.weight
        tp = (w * (ju & m.h_unsup)).sum()
        out[name] = {"n": int(len(m)), "agreement": round(float((ju == m.h_unsup).mean()), 3),
                     "kappa": round(float(cohen_kappa_score(ju, m.h_unsup)), 3) if len(set(ju) | set(m.h_unsup)) > 1 else None,
                     "precision_unsupported_w": round(float(tp / max((w * ju).sum(), 1e-9)), 3),
                     "recall_unsupported_w": round(float(tp / max((w * m.h_unsup).sum(), 1e-9)), 3)}
    (RELEASE / "human_quick_validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quick claim check</title>
<style>
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#deddd8;--accent:#1f5fbf;--mark:#ffe58a;--ok:#1d7a3d;--no:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe7;--muted:#a3a29c;--card:#201f1e;--line:#3a3936;--accent:#7fb0ff;--mark:#6b5a12;--ok:#5fc27e;--no:#ff8a80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;z-index:2}
main{max-width:1000px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:14px}
.claim{font-size:21px;font-weight:650;margin:4px 0 12px}
.btns{display:flex;gap:10px;flex-wrap:wrap}
.btns button{font-size:17px;padding:10px 16px;border-radius:8px;border:2px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
.btns button.sel{border-color:var(--accent);outline:2px solid var(--accent)}
pre{white-space:pre-wrap;word-wrap:break-word;max-height:50vh;overflow:auto;font:14px/1.6 ui-monospace,Consolas,monospace;margin:8px 0 0}
mark{background:var(--mark);color:inherit;border-radius:2px}
button{font:inherit;padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
.muted{color:var(--muted);font-size:14px}a{color:var(--accent);word-break:break-all}.gap{color:var(--muted)}
</style></head><body>
<header><button id="prev">&larr; Back</button><b id="pos"></b><span class="muted" id="done"></span>
<span style="flex:1"></span><button id="export">Export CSV</button></header>
<main>
<div class="card">
  <div class="muted">Read only the source text below. Does it back up the claim, at least its main point? Use only what the sources say, not what you know.</div>
  <div class="claim" id="claim"></div>
  <div class="btns">
    <button data-l="SUPPORTED">1 &nbsp;Yes, supported</button>
    <button data-l="NOT_SUPPORTED">2 &nbsp;No, not supported</button>
    <button data-l="CANT_TELL">3 &nbsp;Can't tell</button>
  </div>
  <div class="muted" style="margin-top:8px">Keys 1 / 2 / 3 choose and move on. Highlighted words come from the claim.</div>
</div>
<div id="sources"></div>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const ITEMS = JSON.parse(document.getElementById('data').textContent);
const KEY = 'cn-quick-labels-v1';
let store = {}; try { store = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
let i = 0; try { i = Math.min(+localStorage.getItem(KEY + '-pos') || 0, ITEMS.length - 1); } catch (e) {}
const full = {};
const $ = id => document.getElementById(id);
function save(){ try { localStorage.setItem(KEY, JSON.stringify(store)); localStorage.setItem(KEY + '-pos', i); } catch (e) {} }
const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const reOf = kw => kw.length ? new RegExp('(' + kw.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi') : null;
function hl(text, re){ return re ? esc(text).replace(re, '<mark>$1</mark>') : esc(text); }
function snippets(text, re){
  if (!re) return null; const spans = []; let m; const r = new RegExp(re.source, 'gi');
  while ((m = r.exec(text)) && spans.length < 60) { spans.push([Math.max(0, m.index - 260), Math.min(text.length, m.index + m[0].length + 260)]); }
  if (!spans.length) return null;
  const merged = [spans[0]]; for (const s of spans.slice(1)) { const t = merged[merged.length - 1]; if (s[0] <= t[1]) t[1] = Math.max(t[1], s[1]); else merged.push(s); }
  return merged.slice(0, 8).map(([a, b]) => text.slice(a, b));
}
function render(){
  const it = ITEMS[i], cur = store[it.q], re = reOf(it.kw);
  $('pos').textContent = `Claim ${i + 1} of ${ITEMS.length}`;
  $('done').textContent = `${Object.keys(store).length} answered`;
  $('claim').innerHTML = hl(it.claim, re);
  document.querySelectorAll('.btns button').forEach(b => b.classList.toggle('sel', cur === b.dataset.l));
  $('sources').innerHTML = it.sources.map((s, k) => {
    const sn = snippets(s.text, re), showFull = full[it.q + k] || !sn;
    const body = showFull ? hl(s.text, re) : sn.map(x => hl(x, re)).join('\n<span class="gap">  [...]  </span>\n');
    const note = !sn ? '<div class="muted">No highlighted words found in this source; full text shown.</div>' : '';
    const tog = sn ? `<button onclick="full['${it.q}${k}']=!full['${it.q}${k}'];render()">${showFull ? 'Show only highlighted parts' : 'Show full text'}</button>` : '';
    return `<div class="card"><b>${s.id}</b> <a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a> ${tog}${note}<pre>${body}</pre></div>`;
  }).join('') || '<p class="muted">No source text.</p>';
  save();
}
function choose(l){ store[ITEMS[i].q] = l; save(); if (i < ITEMS.length - 1) i++; render(); window.scrollTo(0, 0); }
document.querySelectorAll('.btns button').forEach(b => b.onclick = () => choose(b.dataset.l));
$('prev').onclick = () => { i = Math.max(0, i - 1); render(); };
document.addEventListener('keydown', e => { if (e.key === '1') choose('SUPPORTED'); if (e.key === '2') choose('NOT_SUPPORTED'); if (e.key === '3') choose('CANT_TELL'); if (e.key === 'ArrowLeft') { i = Math.max(0, i - 1); render(); } });
$('export').onclick = () => {
  const rows = ['qid,label'].concat(ITEMS.filter(it => store[it.q]).map(it => it.q + ',' + store[it.q]));
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows.join('\n')], {type: 'text/csv'}));
  a.download = 'human_labels_quick.csv'; a.click(); };
render();
</script></body></html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "score"])
    make() if ap.parse_args().cmd == "make" else score()
