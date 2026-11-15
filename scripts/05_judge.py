"""Claim decomposition and quote-anchored support verdicts with the Claude API.

Subcommands
  pilot [--limit N]              decompose + judge the 40 pilot notes synchronously and write
                                 data/interim/judge_runs/pilot_report.md for reading
  submit decompose               Message Batch (50% price): split every main-sample note into claims
  collect decompose              wait for it; write claims_main.jsonl
  submit judge [--model M]       Message Batch: verdicts for every in-scope claim against the note's sources
  collect judge [--model M]      wait for it; verify every quote mechanically, re-ask failures once,
                                 write verdicts_main_<model>.jsonl
  status                         batch states

The judge sees only the claims and the retrieved source texts: never the author group or status.
Claims are always produced by the primary model so that every judge scores the same claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import anthropic
import pandas as pd
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from common import INTERIM, ROOT

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROMPTS = ROOT / "prompts"
SRC_DIR = INTERIM / "sources"
RUNS = INTERIM / "judge_runs"
RUNS.mkdir(parents=True, exist_ok=True)
STATE = RUNS / "batches.json"

PRIMARY = "claude-haiku-5-5"  # stage-2 amendment: run via scripts/05b_judge_cli.py
PRICE = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
CLAIM_TYPES = ["about_post", "number_date", "attribution_quote", "causal", "characterisation", "event"]
LABELS = ["SUPPORTED", "PARTIAL", "NOT_IN_SOURCE", "CONTRADICTED"]
QUOTED = {"SUPPORTED", "PARTIAL", "CONTRADICTED"}
MAX_SOURCE_CHARS = 100_000
MIN_SOURCE_CHARS = 200

DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "type": {"type": "string", "enum": CLAIM_TYPES}},
        "required": ["text", "type"], "additionalProperties": False}}},
    "required": ["claims"], "additionalProperties": False,
}
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {"type": "array", "items": {
            "type": "object",
            "properties": {"claim_id": {"type": "string"}, "label": {"type": "string", "enum": LABELS},
                           "source_id": {"type": "string"}, "quote": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["claim_id", "label", "source_id", "quote", "reason"], "additionalProperties": False}},
        "source_issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"source_id": {"type": "string"},
                           "issue": {"type": "string",
                                     "enum": ["error_page", "paywall_or_login", "unrelated_page", "truncated", "other"]},
                           "detail": {"type": "string"}},
            "required": ["source_id", "issue", "detail"], "additionalProperties": False}},
    },
    "required": ["verdicts", "source_issues"], "additionalProperties": False,
}


def prompt(name: str) -> tuple[str, str]:
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def load_dotenv() -> None:
    """Read KEY=value lines from the git-ignored .env at the repo root into the environment."""
    import os
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def client() -> anthropic.Anthropic:
    load_dotenv()
    try:
        return anthropic.Anthropic()
    except anthropic.AnthropicError as e:
        sys.exit(f"No Claude API credentials: {e}\nPut ANTHROPIC_API_KEY=sk-ant-... in {ROOT / '.env'}")


# ------------------------------------------------------------------ inputs
def load_notes(split: str) -> pd.DataFrame:
    return pd.read_parquet(INTERIM / f"sample_{split}.parquet")


def load_sources() -> dict[str, list[dict]]:
    """noteId -> retrieved sources (text >= MIN_SOURCE_CHARS), from the fetch cache."""
    by_note: dict[str, list[dict]] = {}
    for p in SRC_DIR.glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("n_chars", 0) >= MIN_SOURCE_CHARS:
            by_note.setdefault(rec["noteId"], []).append(rec)
    return by_note


def pick_text(rec: dict) -> tuple[str, bool]:
    full, main = rec.get("text_full") or "", rec.get("text") or ""
    text = full or main
    if len(text) <= MAX_SOURCE_CHARS:
        return text, False
    if 2000 <= len(main) <= MAX_SOURCE_CHARS:
        return main, False
    return text[:MAX_SOURCE_CHARS], True


def retrieved_label(rec: dict) -> str:
    snap = str(rec.get("snapshot") or "")
    day = f"{snap[:4]}-{snap[4:6]}-{snap[6:8]}" if snap[:8].isdigit() else snap[:10]
    return {"wiki_rev": f"Wikipedia revision of {day}",
            "wayback_before": f"archived copy of {day}",
            "wayback_after": f"archived copy of {day}",
            "cited_archive": f"archived copy of {day}",
            "live": "live copy (not time-pinned)"}.get(rec.get("method"), str(rec.get("method")))


def note_sources(note, by_note: dict) -> list[dict]:
    order = {u: i for i, u in enumerate(json.loads(note.urls))}
    recs = sorted(by_note.get(note.noteId, []), key=lambda r: order.get(r["url"], 99))
    out = []
    for i, rec in enumerate(recs, 1):
        text, truncated = pick_text(rec)
        out.append({"id": f"S{i}", "key": rec["key"], "url": rec["url"], "method": rec.get("method"),
                    "snapshot": rec.get("snapshot", ""), "retrieved": retrieved_label(rec),
                    "chars": len(text), "truncated": truncated, "text": text})
    return out


# ------------------------------------------------------------------ requests
def decompose_params(note_text: str, model: str = PRIMARY) -> dict:
    system, _ = prompt("decompose")
    return {"model": model, "max_tokens": 16000, "system": system,
            "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": DECOMPOSE_SCHEMA}},
            "messages": [{"role": "user", "content": f"<note>\n{note_text}\n</note>"}]}


def judge_params(claims: list[dict], sources: list[dict], model: str, effort: str, extra: str = "") -> dict:
    system, _ = prompt("judge")
    src = "\n".join(f'<source id="{s["id"]}" url="{s["url"]}" retrieved="{s["retrieved"]}">\n{s["text"]}\n</source>'
                    for s in sources)
    cl = "\n".join(f'{c["id"]}: {c["text"]}' for c in claims)
    body = f"<sources>\n{src}\n</sources>\n\n<claims>\n{cl}\n</claims>\n\n{extra}Return exactly one verdict for every claim id above."
    return {"model": model, "max_tokens": 16000, "system": system,
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
            "messages": [{"role": "user", "content": body}]}


def parse(msg) -> tuple[dict | None, str | None]:
    if msg.stop_reason in ("refusal", "max_tokens"):
        return None, msg.stop_reason
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        return json.loads(text), None
    except json.JSONDecodeError:
        return None, "bad_json"


def usage(msg) -> dict:
    u = msg.usage
    return {"in": u.input_tokens or 0, "out": u.output_tokens or 0,
            "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}


def cost(usages: list[dict], model: str, batch: bool) -> float:
    pin, pout = PRICE.get(model, PRICE[PRIMARY])
    f = 0.5 if batch else 1.0
    return f * sum((u["in"] + 1.25 * u["cache_write"] + 0.1 * u["cache_read"]) * pin + u["out"] * pout
                   for u in usages) / 1e6


# ------------------------------------------------------------------ quote verification
_QMAP = {**{ord(c): "'" for c in "‘’‚‛´`′"},
         **{ord(c): '"' for c in "“”„‟″"},
         **{ord(c): "-" for c in "‐‑‒–—―−"}}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_QMAP).replace("�", "")
    return re.sub(r"\s+", " ", s).strip().casefold()


def quote_found(quote: str, text: str) -> bool:
    """Exact match after normalisation; long quotes may differ in <=10% of 6-word shingles."""
    q = norm(quote).strip(" \"'")  # quote marks wrapped around a passage are not part of it
    if len(q) < 8:
        return False
    t = norm(text)
    if q in t:
        return True
    words = q.split()
    if len(words) < 8:
        return False
    shingles = [" ".join(words[i:i + 6]) for i in range(len(words) - 5)]
    return sum(s in t for s in shingles) / len(shingles) >= 0.9


def check_verdicts(data: dict, claims: list[dict], sources: list[dict]) -> list[dict]:
    texts = {s["id"]: s["text"] for s in sources}
    got = {}
    for v in data.get("verdicts", []):
        got.setdefault(v["claim_id"], v)
    out = []
    for c in claims:
        v = got.get(c["id"])
        if v is None:
            out.append({"claim_id": c["id"], "label": "MISSING", "label_raw": None, "source_id": "", "quote": "",
                        "reason": "", "quote_verified": None})
            continue
        ok = None
        if v["label"] in QUOTED:
            ok = v["source_id"] in texts and quote_found(v["quote"], texts[v["source_id"]])
        out.append({**v, "label_raw": v["label"], "quote_verified": ok})
    return out


def finalise(client_: anthropic.Anthropic, rec: dict, claims: list[dict], sources: list[dict], model: str,
             effort: str) -> dict:
    """Re-ask once for verdicts whose quote is not in the cited source; still failing -> UNVERIFIED."""
    bad = [v for v in rec["verdicts"] if v["quote_verified"] is False or v["label"] == "MISSING"]
    if bad:
        ids = {v["claim_id"] for v in bad}
        sub = [c for c in claims if c["id"] in ids]
        extra = ("In an earlier pass, the quote given for each of these claims was not found verbatim in the "
                 "source named, or no verdict was given. Re-check each claim. Copy the deciding passage exactly as "
                 "it appears in the source, or use NOT_IN_SOURCE if no passage establishes the claim.\n\n")
        msg = client_.messages.create(**judge_params(sub, sources, model, effort, extra))
        rec["usage_reask"] = usage(msg)
        data, err = parse(msg)
        redo = {v["claim_id"]: v for v in check_verdicts(data, sub, sources)} if data else {}
        for i, v in enumerate(rec["verdicts"]):
            if v["claim_id"] in ids:
                nv = redo.get(v["claim_id"])
                if nv and nv["label"] != "MISSING" and nv["quote_verified"] is not False:
                    rec["verdicts"][i] = {**nv, "reasked": True}
                else:
                    keep = nv or v
                    rec["verdicts"][i] = {**keep, "label": "UNVERIFIED", "reasked": True}
    return rec


# ------------------------------------------------------------------ pilot (synchronous)
def run_pilot(limit: int, model: str, effort: str) -> None:
    c = client()
    notes = load_notes("pilot")
    if limit:
        notes = notes.head(limit)
    by_note = load_sources()

    def one(note):
        m1 = c.messages.create(**decompose_params(note.summary))
        d, err = parse(m1)
        claims = [{"id": f"c{i}", **cl} for i, cl in enumerate((d or {}).get("claims", []), 1)]
        rec = {"noteId": note.noteId, "stratum": note.stratum, "summary": note.summary, "claims": claims,
               "decompose_error": err, "usage_decompose": usage(m1)}
        in_scope = [cl for cl in claims if cl["type"] != "about_post"]
        sources = note_sources(note, by_note)
        rec["sources"] = [{k: v for k, v in s.items() if k != "text"} for s in sources]
        if not in_scope or not sources:
            rec["skip"] = "no_checkable_claims" if not in_scope else "no_retrieved_sources"
            return rec
        m2 = c.messages.create(**judge_params(in_scope, sources, model, effort))
        data, err = parse(m2)
        rec.update(usage_judge=usage(m2), judge_error=err, source_issues=(data or {}).get("source_issues", []),
                   verdicts=check_verdicts(data or {}, in_scope, sources))
        return finalise(c, rec, in_scope, sources, model, effort)

    with ThreadPoolExecutor(max_workers=4) as pool:
        recs = list(pool.map(one, notes.itertuples()))
    out = RUNS / f"pilot_{slug(model)}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    write_pilot_report(recs, model)
    us = [r["usage_decompose"] for r in recs] + [r[k] for r in recs for k in ("usage_judge", "usage_reask") if k in r]
    print(f"pilot done: {len(recs)} notes -> {out.name}; cost ~${cost(us, model, batch=False):.2f}")


def write_pilot_report(recs: list[dict], model: str) -> None:
    labels = pd.Series([v["label"] for r in recs for v in r.get("verdicts", [])]).value_counts()
    lines = [f"# Pilot report ({model})", "",
             f"prompt sha256: decompose `{prompt('decompose')[1][:12]}`, judge `{prompt('judge')[1][:12]}`", "",
             "Verdict labels: " + ", ".join(f"{k} {v}" for k, v in labels.items()), ""]
    for r in recs:
        lines += [f"## {r['noteId']}  ({r['stratum']})", "", "> " + r["summary"].replace("\n", " "), ""]
        for s in r.get("sources", []):
            lines.append(f"- **{s['id']}** {s['retrieved']}, {s['chars']:,} chars{' (truncated)' if s['truncated'] else ''}: {s['url']}")
        for iss in r.get("source_issues", []):
            lines.append(f"- source issue {iss['source_id']}: {iss['issue']}: {iss['detail']}")
        if r.get("skip"):
            lines.append(f"- *skipped: {r['skip']}*")
        lines.append("")
        verdicts = {v["claim_id"]: v for v in r.get("verdicts", [])}
        for cl in r["claims"]:
            v = verdicts.get(cl["id"])
            if not v:
                lines.append(f"- `{cl['id']}` [{cl['type']}] {cl['text']}  -> *(not judged)*")
                continue
            check = {True: "quote verified", False: "QUOTE NOT FOUND", None: "no quote"}[v.get("quote_verified")]
            lines.append(f"- `{cl['id']}` [{cl['type']}] {cl['text']}")
            lines.append(f"  - **{v['label']}** {v.get('source_id', '')} ({check}{', re-asked' if v.get('reasked') else ''}): {v.get('reason', '')}")
            if v.get("quote"):
                lines.append(f"  - quote: \"{v['quote']}\"")
        lines.append("")
    (RUNS / f"pilot_report_{slug(model)}.md").write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------------ batches (main sample)
def state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def claims_path(split: str) -> "Path":
    return RUNS / f"claims_{split}.jsonl"


def submit(stage: str, split: str, model: str, effort: str) -> None:
    c, notes = client(), load_notes(split)
    reqs = []
    if stage == "decompose":
        for n in notes.itertuples():
            reqs.append(Request(custom_id=f"dec-{n.noteId}",
                                params=MessageCreateParamsNonStreaming(**decompose_params(n.summary))))
    else:
        claims = {json.loads(l)["noteId"]: json.loads(l) for l in claims_path(split).read_text(encoding="utf-8").splitlines()}
        by_note = load_sources()
        for n in notes.itertuples():
            in_scope = [cl for cl in claims[n.noteId]["claims"] if cl["type"] != "about_post"]
            sources = note_sources(n, by_note)
            if in_scope and sources:
                reqs.append(Request(custom_id=f"jdg-{n.noteId}",
                                    params=MessageCreateParamsNonStreaming(**judge_params(in_scope, sources, model, effort))))
    batch = c.messages.batches.create(requests=reqs)
    s = state()
    s[f"{stage}|{split}|{slug(model)}"] = {"id": batch.id, "n": len(reqs), "effort": effort,
                                          "submitted": time.strftime("%Y-%m-%d %H:%M:%S"),
                                          "prompt_sha256": prompt(stage)[1]}
    save_state(s)
    print(f"submitted {stage} batch {batch.id} with {len(reqs)} requests")


def wait(c: anthropic.Anthropic, batch_id: str):
    while True:
        b = c.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            return b
        rc = b.request_counts
        print(f"[{time.strftime('%H:%M:%S')}] {b.processing_status}: processing {rc.processing}, succeeded {rc.succeeded}, errored {rc.errored}", flush=True)
        time.sleep(60)


def collect(stage: str, split: str, model: str) -> None:
    c = client()
    meta = state()[f"{stage}|{split}|{slug(model)}"]
    b = wait(c, meta["id"])
    results = {r.custom_id: r for r in c.messages.batches.results(b.id)}
    notes = load_notes(split).set_index("noteId")
    usages, failed = [], []
    if stage == "decompose":
        lines = []
        for cid, r in results.items():
            nid = cid.split("-", 1)[1]
            if r.result.type != "succeeded":
                failed.append(nid)
                continue
            d, err = parse(r.result.message)
            usages.append(usage(r.result.message))
            claims = [{"id": f"c{i}", **cl} for i, cl in enumerate((d or {}).get("claims", []), 1)]
            lines.append(json.dumps({"noteId": nid, "claims": claims, "error": err}, ensure_ascii=False))
        claims_path(split).write_text("\n".join(lines), encoding="utf-8")
        print(f"claims for {len(lines)} notes -> {claims_path(split).name}; failed {len(failed)}")
    else:
        claims = {json.loads(l)["noteId"]: json.loads(l) for l in claims_path(split).read_text(encoding="utf-8").splitlines()}
        by_note = load_sources()
        recs, reask = [], 0
        for cid, r in results.items():
            nid = cid.split("-", 1)[1]
            note = notes.loc[nid]
            note_t = type("N", (), {"noteId": nid, "urls": note.urls})
            in_scope = [cl for cl in claims[nid]["claims"] if cl["type"] != "about_post"]
            sources = note_sources(note_t, by_note)
            if r.result.type != "succeeded":
                failed.append(nid)
                continue
            data, err = parse(r.result.message)
            usages.append(usage(r.result.message))
            rec = {"noteId": nid, "judge_error": err, "source_issues": (data or {}).get("source_issues", []),
                   "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources],
                   "verdicts": check_verdicts(data or {}, in_scope, sources)}
            if any(v["quote_verified"] is False or v["label"] == "MISSING" for v in rec["verdicts"]):
                reask += 1
                rec = finalise(c, rec, in_scope, sources, model, meta["effort"])
            recs.append(rec)
        out = RUNS / f"verdicts_{split}_{slug(model)}.jsonl"
        out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in recs), encoding="utf-8")
        sync_cost = cost([x["usage_reask"] for x in recs if "usage_reask" in x], model, batch=False)
        print(f"verdicts for {len(recs)} notes -> {out.name}; re-asked {reask}; failed {len(failed)}; "
              f"re-ask cost ~${sync_cost:.2f}")
    if failed:
        (RUNS / f"failed_{stage}_{split}_{slug(model)}.txt").write_text("\n".join(failed), encoding="utf-8")
    print(f"batch cost ~${cost(usages, model, batch=True):.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "submit", "collect", "status"])
    ap.add_argument("stage", nargs="?", choices=["decompose", "judge"])
    ap.add_argument("--split", default="main")
    ap.add_argument("--model", default=PRIMARY)
    ap.add_argument("--effort", default="high")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "pilot":
        run_pilot(a.limit, a.model, a.effort)
    elif a.cmd == "status":
        c = client()
        for k, v in state().items():
            b = c.messages.batches.retrieve(v["id"])
            print(k, v["id"], b.processing_status, b.request_counts)
    elif a.cmd == "submit":
        submit(a.stage, a.split, PRIMARY if a.stage == "decompose" else a.model, a.effort)
    else:
        collect(a.stage, a.split, PRIMARY if a.stage == "decompose" else a.model)


if __name__ == "__main__":
    main()
