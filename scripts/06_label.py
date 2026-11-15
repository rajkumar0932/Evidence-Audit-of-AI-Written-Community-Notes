"""Blind human validation of the LLM judge.

  make  [--n-per-group 50] [--model M]  pick claims stratified by judge label x author group and write a
                                        self-contained page, data/interim/labeling/label.html. Open it in a
                                        browser; labels autosave; press "Export CSV" when done and save the
                                        file as data/release/human_labels.csv
  score [--labels CSV] [--model M]      compare human labels with the judge: Cohen's kappa overall and by
                                        AI vs human authorship, confusion matrix, precision/recall of UNSUPPORTED

The page never shows the author group, the note's status, or the judge's verdict or quote.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

from common import GROUPS, INTERIM, RELEASE, SEED

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_spec = importlib.util.spec_from_file_location("judge", INTERIM.parents[1] / "scripts" / "05_judge.py")
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)

LAB = INTERIM / "labeling"
LAB.mkdir(parents=True, exist_ok=True)
PER_GROUP = {"SUPPORTED": 18, "PARTIAL": 10, "NOT_IN_SOURCE": 14, "CONTRADICTED": 8}
UNSUP = {"NOT_IN_SOURCE", "CONTRADICTED"}


def verdict_rows(model: str) -> pd.DataFrame:
    path = judge.RUNS / f"verdicts_main_{judge.slug(model)}.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        rec = json.loads(line)
        for v in rec["verdicts"]:
            rows.append({"noteId": rec["noteId"], "claim_id": v["claim_id"], "judge_label": v["label"]})
    ids = pd.read_csv(RELEASE / "sample_ids.csv", dtype={"noteId": str})
    return pd.DataFrame(rows).merge(ids[["noteId", "group", "stratum"]], on="noteId")


def make(n_per_group: int, model: str) -> None:
    v = verdict_rows(model)
    v = v[v.judge_label.isin(PER_GROUP)]
    scale = n_per_group / sum(PER_GROUP.values())
    rng = np.random.default_rng(SEED + 7)
    picked = []
    for g in GROUPS:
        pool = v[v.group == g]
        chosen, deficit = [], 0
        for label, k in PER_GROUP.items():
            k = round(k * scale)
            cand = pool[pool.judge_label == label]
            take = min(k, len(cand))
            idx = rng.choice(cand.index, size=take, replace=False) if take else []
            chosen += list(idx)
            deficit += k - take
        rest = pool.index.difference(chosen)
        if deficit and len(rest):
            chosen += list(rng.choice(rest, size=min(deficit, len(rest)), replace=False))
        sel = pool.loc[chosen].copy()
        avail = pool.judge_label.value_counts()
        got = sel.judge_label.value_counts()
        sel["weight"] = sel.judge_label.map(lambda l: avail[l] / got[l])  # inverse selection probability
        picked.append(sel)
    items = pd.concat(picked).sample(frac=1, random_state=SEED).reset_index(drop=True)
    items["item_id"] = [f"A{i:03d}" for i in range(1, len(items) + 1)]

    claims = {json.loads(l)["noteId"]: json.loads(l) for l in
              (judge.RUNS / "claims_main.jsonl").read_text(encoding="utf-8").split("\n")}
    notes = judge.load_notes("main").set_index("noteId")
    by_note = judge.load_sources()
    payload = []
    for it in items.itertuples():
        claim = next(c for c in claims[it.noteId]["claims"] if c["id"] == it.claim_id)
        note = notes.loc[it.noteId]
        srcs = judge.note_sources(type("N", (), {"noteId": it.noteId, "urls": note.urls}), by_note)
        payload.append({"item": it.item_id, "claim": claim["text"],
                        "sources": [{"id": s["id"], "url": s["url"], "retrieved": s["retrieved"], "text": s["text"]}
                                    for s in srcs]})
    items.to_csv(LAB / "key.csv", index=False)  # item -> note, claim, group, judge label (keep closed)
    page = PAGE.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    (LAB / "label.html").write_text(page, encoding="utf-8")
    print(f"{len(items)} items -> {LAB / 'label.html'}")
    print(items.groupby(["group", "judge_label"]).size().unstack(fill_value=0).to_string())


def score(labels_csv: str, model: str) -> None:
    key = pd.read_csv(LAB / "key.csv", dtype={"noteId": str})
    hum = pd.read_csv(labels_csv)
    out = {}
    if hum.labeler.nunique() > 1:  # human-human agreement on items labelled by two people
        wide = hum.pivot_table(index="item_id", columns="labeler", values="label", aggfunc="first").dropna()
        if len(wide) and wide.shape[1] >= 2:
            a, b = wide.columns[:2]
            out["human_human_kappa"] = round(cohen_kappa_score(wide[a], wide[b]), 3)
            out["human_human_n"] = len(wide)
    first = hum.sort_values("labelled_at").groupby("item_id").first().reset_index()
    df = key.merge(first[["item_id", "label"]], on="item_id")
    df = df[df.label != "CANT_TELL"]
    df["ai"] = df.group.isin(["cw", "ai_other"])
    df["h_unsup"], df["j_unsup"] = df.label.isin(UNSUP), df.judge_label.isin(UNSUP)

    def kappa(a: pd.Series, b: pd.Series) -> float | None:
        if len(a) < 2 or len(set(a) | set(b)) < 2:  # undefined for empty or single-class input
            return None
        return round(float(cohen_kappa_score(a, b)), 3)

    def block(d: pd.DataFrame) -> dict:
        if d.empty:
            return {"n": 0}
        w = d.weight
        tp = (w * (d.h_unsup & d.j_unsup)).sum()
        return {"n": len(d),
                "kappa_4class": kappa(d.label, d.judge_label),
                "kappa_unsupported": kappa(d.h_unsup, d.j_unsup),
                "judge_precision_unsupported_w": round(tp / max((w * d.j_unsup).sum(), 1e-9), 3),
                "judge_recall_unsupported_w": round(tp / max((w * d.h_unsup).sum(), 1e-9), 3)}

    out["all"] = block(df)
    out["ai_authored"] = block(df[df.ai])
    out["human_authored"] = block(df[~df.ai])
    out["confusion_rows_human_cols_judge"] = pd.crosstab(df.label, df.judge_label).to_dict()
    (RELEASE / "judge_validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim labelling</title>
<style>
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#deddd8;--accent:#1f5fbf;--mark:#ffe58a}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe7;--muted:#a3a29c;--card:#201f1e;--line:#3a3936;--accent:#7fb0ff;--mark:#6b5a12}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center;z-index:2}
main{max-width:1100px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:14px}
.claim{font-size:19px;font-weight:600}
.labels{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.labels label{border:1px solid var(--line);border-radius:6px;padding:6px 10px;cursor:pointer}
.labels input{margin-right:6px}
input[type=text]{width:100%;padding:7px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
pre{white-space:pre-wrap;word-wrap:break-word;max-height:55vh;overflow:auto;border-top:1px solid var(--line);padding-top:8px;font:13.5px/1.55 ui-monospace,Consolas,monospace}
mark{background:var(--mark);color:inherit}button{padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
.muted{color:var(--muted);font-size:13px}details summary{cursor:pointer}a{color:var(--accent);word-break:break-all}
</style></head><body>
<header>
  <button id="prev">&larr; Prev</button><button id="next">Next &rarr;</button>
  <span id="pos"></span><span class="muted" id="done"></span>
  <input type="text" id="who" placeholder="your initials" style="width:120px">
  <input type="text" id="find" placeholder="highlight words in sources" style="width:220px">
  <button id="export">Export CSV</button>
</header>
<main>
<details class="card"><summary><b>How to label</b> (same rules the AI judge was given)</summary>
<p>Judge the claim <b>only</b> against the source texts below, never from your own knowledge. Keys 1-5 pick a label; Enter or &rarr; goes to the next item.</p>
<ul>
<li><b>1 SUPPORTED</b>: a source states the claim or something that directly entails it, including every specific detail (numbers, dates, names, places, who said what).</li>
<li><b>2 PARTIAL</b>: a source establishes the core, but a specific detail is missing or differs without flatly contradicting.</li>
<li><b>3 NOT_IN_SOURCE</b>: no source states or entails it, even if a source covers the topic, and even if you believe the claim is true.</li>
<li><b>4 CONTRADICTED</b>: a source states something incompatible with the claim.</li>
<li><b>5 CANT_TELL</b>: you cannot decide (for example, the source text is unreadable).</li>
</ul><p>Ignore page furniture: menus, cookie notices, adverts, lists of other articles.</p></details>
<div class="card"><div class="muted" id="iid"></div><div class="claim" id="claim"></div>
<div class="labels" id="labels"></div>
<input type="text" id="passage" placeholder="optional: paste the passage that decided it">
<input type="text" id="comment" placeholder="optional comment" style="margin-top:6px"></div>
<div id="sources"></div>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const ITEMS = JSON.parse(document.getElementById('data').textContent);
const LABELS = ['SUPPORTED','PARTIAL','NOT_IN_SOURCE','CONTRADICTED','CANT_TELL'];
const KEY = 'cn-audit-labels-v1';
let store = {}; try { store = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
let i = 0; try { i = Math.min(+localStorage.getItem(KEY + '-pos') || 0, ITEMS.length - 1); } catch (e) {}
const $ = id => document.getElementById(id);
try { $('who').value = localStorage.getItem(KEY + '-who') || ''; } catch (e) {}
function save(){ try { localStorage.setItem(KEY, JSON.stringify(store)); localStorage.setItem(KEY + '-pos', i); localStorage.setItem(KEY + '-who', $('who').value); } catch (e) {} }
function esc(s){ return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function hl(text){ const q = $('find').value.trim(); let h = esc(text); if (!q) return h;
  for (const w of q.split(/\s+/).filter(w => w.length > 2)) { const re = new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'); h = h.replace(re, '<mark>$1</mark>'); }
  return h; }
function render(){
  const it = ITEMS[i], cur = store[it.item] || {};
  $('pos').textContent = `Item ${i + 1} / ${ITEMS.length}`;
  $('done').textContent = `${Object.values(store).filter(v => v.label).length} labelled`;
  $('iid').textContent = it.item; $('claim').textContent = it.claim;
  $('labels').innerHTML = LABELS.map((l, k) => `<label><input type="radio" name="lab" value="${l}" ${cur.label === l ? 'checked' : ''}>${k + 1} ${l}</label>`).join('');
  $('passage').value = cur.passage || ''; $('comment').value = cur.comment || '';
  $('sources').innerHTML = it.sources.map(s => `<div class="card"><b>${s.id}</b> <span class="muted">${esc(s.retrieved)}</span><br><a href="${encodeURI(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a><pre>${hl(s.text)}</pre></div>`).join('') || '<p class="muted">No source text.</p>';
  document.querySelectorAll('input[name=lab]').forEach(r => r.onchange = () => record());
  save();
}
function record(){ const it = ITEMS[i]; const r = document.querySelector('input[name=lab]:checked');
  store[it.item] = { label: r ? r.value : '', passage: $('passage').value, comment: $('comment').value, at: new Date().toISOString() };
  save(); $('done').textContent = `${Object.values(store).filter(v => v.label).length} labelled`; }
function go(d){ record(); i = Math.max(0, Math.min(ITEMS.length - 1, i + d)); render(); window.scrollTo(0, 0); }
$('prev').onclick = () => go(-1); $('next').onclick = () => go(1);
$('passage').oninput = record; $('comment').oninput = record; $('find').oninput = render; $('who').oninput = save;
document.addEventListener('keydown', e => { if (['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) return;
  if (e.key >= '1' && e.key <= '5') { const r = document.querySelectorAll('input[name=lab]')[+e.key - 1]; r.checked = true; record(); }
  if (e.key === 'ArrowRight' || e.key === 'Enter') go(1); if (e.key === 'ArrowLeft') go(-1); });
$('export').onclick = () => {
  const q = s => '"' + String(s || '').replace(/"/g, '""') + '"';
  const rows = [['item_id','label','passage','comment','labeler','labelled_at'].join(',')]
    .concat(ITEMS.filter(it => store[it.item] && store[it.item].label).map(it => { const v = store[it.item];
      return [it.item, v.label, q(v.passage), q(v.comment), q($('who').value || 'h1'), v.at].join(','); }));
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows.join('\n')], {type: 'text/csv'}));
  a.download = 'human_labels.csv'; a.click(); };
render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "score"])
    ap.add_argument("--n-per-group", type=int, default=50)
    ap.add_argument("--model", default=judge.PRIMARY)
    ap.add_argument("--labels", default=str(RELEASE / "human_labels.csv"))
    a = ap.parse_args()
    make(a.n_per_group, a.model) if a.cmd == "make" else score(a.labels, a.model)


if __name__ == "__main__":
    main()
