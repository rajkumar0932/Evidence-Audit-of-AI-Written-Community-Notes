"""Second judge from a different model family (Google Gemini, free tier) on the claims the primary
judge scored. Same judge prompt, schema, quote verification and re-ask rule as 05_judge.py.

Free-tier quotas are small, so this scores a subset: by default every Rated-Helpful (CRH) note,
plus any notes in the human-labelling key if it exists.

  uv run python scripts/05c_judge_gemini.py [--model gemini-3.5-flash] [--strata CRH] [--limit N]

Reads GEMINI_API_KEY from the git-ignored .env. Paces requests, honours retry delays, stops cleanly
when the daily quota is exhausted, and caches per note so a later run continues where it stopped.
Output: data/interim/judge_runs/verdicts_main_<model>.jsonl (judged subset only)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import threading
import time

import httpx
import pandas as pd

from common import ROOT

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_spec = importlib.util.spec_from_file_location("judge_api", ROOT / "scripts" / "05_judge.py")
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)

CACHE = J.RUNS / "gemini_cache"
CACHE.mkdir(parents=True, exist_ok=True)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class QuotaExhausted(Exception):
    pass


def api_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("GEMINI_API_KEY missing from .env")


class Pacer:
    def __init__(self, interval: float):
        self.interval, self.lock, self.next_t = interval, threading.Lock(), 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next_t)
            self.next_t = t + self.interval
        time.sleep(max(0.0, t - now))


def call(client: httpx.Client, key: str, model: str, params: dict, pacer: Pacer, tries: int = 6):
    """Anthropic-style params (system, messages, output_config.format.schema) -> Gemini generateContent."""
    body = {"systemInstruction": {"parts": [{"text": params["system"]}]},
            "contents": [{"role": "user", "parts": [{"text": params["messages"][0]["content"]}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "responseJsonSchema": params["output_config"]["format"]["schema"],
                                 "maxOutputTokens": 16000}}
    for attempt in range(tries):
        pacer.wait()
        try:
            r = client.post(API.format(model=model), json=body, headers={"x-goog-api-key": key}, timeout=300)
        except httpx.HTTPError as e:
            time.sleep(10 * (attempt + 1))
            err = f"http_error: {e!r}"
            continue
        if r.status_code == 429:
            text = r.text
            if re.search(r"PerDay", text):
                raise QuotaExhausted(text[:300])
            m = re.search(r'"retryDelay":\s*"(\d+)', text)
            time.sleep(int(m.group(1)) + 2 if m else 30 * (attempt + 1))
            err = "rate_limited"
            continue
        if r.status_code >= 500:
            time.sleep(15 * (attempt + 1))
            err = f"server_{r.status_code}"
            continue
        if r.status_code != 200:
            return None, f"http_{r.status_code}: {r.text[:200]}", {}
        d = r.json()
        u = d.get("usageMetadata", {})
        usage = {"in": u.get("promptTokenCount", 0), "out": u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)}
        cands = d.get("candidates") or []
        if not cands:
            return None, f"blocked: {d.get('promptFeedback')}", usage
        parts = [p for p in cands[0].get("content", {}).get("parts", []) if "text" in p and not p.get("thought")]
        try:
            return json.loads(parts[-1]["text"]), None, usage
        except (IndexError, json.JSONDecodeError):
            return None, f"bad_json (finish {cands[0].get('finishReason')})", usage
    return None, err, {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--strata", default="CRH", help="comma-separated statuses to include (CRH,CRNH,NMR)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rpm", type=float, default=8)
    a = ap.parse_args()
    key, pacer = api_key(), Pacer(60 / a.rpm)

    notes = J.load_notes("main")
    want = set(a.strata.split(","))
    sel = notes[notes.stratum.str.split("|").str[1].isin(want)]
    key_csv = J.RUNS.parent / "labeling" / "key.csv"
    if key_csv.exists():
        labelled = set(pd.read_csv(key_csv, dtype={"noteId": str}).noteId)
        sel = pd.concat([notes[notes.noteId.isin(labelled)], sel]).drop_duplicates("noteId")
    claims = {json.loads(l)["noteId"]: json.loads(l)["claims"]
              for l in J.claims_path("main").read_text(encoding="utf-8").split("\n")}
    by_note = J.load_sources()
    phash = J.prompt("judge")[1][:8]
    todo = [n for n in sel.itertuples() if n.noteId in claims]
    if a.limit:
        todo = todo[: a.limit]
    print(f"model {a.model}; {len(todo)} notes selected ({a.strata} + labelled)", flush=True)

    recs, n_calls = [], 0
    with httpx.Client() as client:
        try:
            for i, n in enumerate(todo, 1):
                path = CACHE / f"judge-{J.slug(a.model)}-{phash}_{n.noteId}.json"
                if path.exists():
                    recs.append(json.loads(path.read_text(encoding="utf-8")))
                    continue
                in_scope = [c for c in claims[n.noteId] if c["type"] != "about_post"]
                sources = J.note_sources(n, by_note)
                meta = {"noteId": n.noteId, "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources]}
                if not in_scope or not sources:
                    recs.append({**meta, "verdicts": [], "skip": "no_checkable_claims" if not in_scope else "no_retrieved_sources"})
                    continue
                data, err, usage = call(client, key, a.model, J.judge_params(in_scope, sources, a.model, "high"), pacer)
                n_calls += 1
                if err:
                    print(f"  {n.noteId}: {err}", flush=True)
                    continue
                rec = {**meta, "usage": usage, "source_issues": data.get("source_issues", []),
                       "verdicts": J.check_verdicts(data, in_scope, sources)}
                bad = {v["claim_id"] for v in rec["verdicts"] if v["quote_verified"] is False or v["label"] == "MISSING"}
                if bad:
                    sub = [c for c in in_scope if c["id"] in bad]
                    extra = ("In an earlier pass, the quote given for each of these claims was not found verbatim in the "
                             "source named, or no verdict was given. Re-check each claim. Copy the deciding passage "
                             "exactly as it appears in the source, or use NOT_IN_SOURCE if no passage establishes the "
                             "claim.\n\n")
                    d2, _, _ = call(client, key, a.model, J.judge_params(sub, sources, a.model, "high", extra), pacer)
                    n_calls += 1
                    redo = {v["claim_id"]: v for v in J.check_verdicts(d2 or {}, sub, sources)}
                    for k, v in enumerate(rec["verdicts"]):
                        if v["claim_id"] in bad:
                            nv = redo.get(v["claim_id"])
                            ok = nv and nv["label"] != "MISSING" and nv["quote_verified"] is not False
                            rec["verdicts"][k] = {**(nv if ok else (nv or v)), "reasked": True,
                                                  **({} if ok else {"label": "UNVERIFIED"})}
                path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
                recs.append(rec)
                if i % 10 == 0:
                    print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(todo)} notes, {n_calls} calls", flush=True)
        except QuotaExhausted as e:
            print(f"Daily free quota for {a.model} exhausted after {n_calls} calls: re-run tomorrow, or pass "
                  f"--model gemini-3.5-flash-lite to continue on another model's quota.\n{e}", flush=True)
    out = J.RUNS / f"verdicts_main_{J.slug(a.model)}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    print(f"{len(recs)} notes -> {out.name}", flush=True)


if __name__ == "__main__":
    main()
