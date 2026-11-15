"""Claim decomposition and quote-anchored verdicts, run through Claude Code's headless mode
(`claude -p`) on the user's existing subscription: no API key and no per-token charge.

Same prompts, schemas, quote verification and output files as 05_judge.py, so 06/07/10 work unchanged
(pass --model claude-haiku-5-5 to them).

  pilot [--limit N]              40 pilot notes -> judge_runs/pilot_report_<model>.md
  run decompose [--split main]   claims for every note       -> judge_runs/claims_<split>.jsonl
  run judge     [--split main]   verdicts for every note     -> judge_runs/verdicts_<split>_<model>.jsonl

Every call is cached per note (judge_runs/cli_cache/), so an interrupted run resumes where it stopped.
Calls run from an empty working directory with tools, MCP servers, skills and settings disabled, so the
model sees only the system prompt and the note's claims and sources.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common import ROOT

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_spec = importlib.util.spec_from_file_location("judge_api", ROOT / "scripts" / "05_judge.py")
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)

MODEL = "claude-haiku-5-5"
CACHE = J.RUNS / "cli_cache"
CACHE.mkdir(parents=True, exist_ok=True)
NEUTRAL_CWD = Path(os.environ.get("TEMP", str(ROOT.parent))) / "cn-judge-cwd"
NEUTRAL_CWD.mkdir(parents=True, exist_ok=True)
STOP = threading.Event()  # set when the subscription usage limit is reached


def claude_bin() -> str:
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    found = sorted(glob.glob(str(Path.home() / ".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe")))
    if found:
        return found[-1]
    return "claude"


BIN = claude_bin()


def call(params: dict, tries: int = 3) -> tuple[dict | None, str | None, dict]:
    """Run one request through `claude -p`. Returns (structured output, error, usage)."""
    schema = params["output_config"]["format"]["schema"]
    args = [BIN, "-p", "--model", params["model"], "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
            "--setting-sources", "", "--system-prompt", params["system"], "--json-schema", json.dumps(schema),
            "--effort", params["output_config"].get("effort", "medium"), "--output-format", "json",
            "--no-session-persistence"]
    body = params["messages"][0]["content"]
    err = "not_run"
    for attempt in range(tries):
        if STOP.is_set():
            return None, "stopped_usage_limit", {}
        try:
            p = subprocess.run(args, input=body.encode("utf-8"), capture_output=True, timeout=600, cwd=NEUTRAL_CWD)
            out = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
        except subprocess.TimeoutExpired:
            err = "timeout"
            continue
        except json.JSONDecodeError:
            err = f"bad_output: {p.stdout[:200]!r} {p.stderr[:200]!r}"
            time.sleep(5 * (attempt + 1))
            continue
        u = out.get("usage") or {}
        usage = {"in": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
                 "cache_read": u.get("cache_read_input_tokens") or 0, "out": u.get("output_tokens") or 0,
                 "api_equiv_usd": out.get("total_cost_usd") or 0, "models": list((out.get("modelUsage") or {}).keys())}
        if out.get("is_error") or out.get("subtype") != "success":
            msg = str(out.get("result") or out.get("subtype"))
            if "limit" in msg.lower() and ("usage" in msg.lower() or "reset" in msg.lower()):
                STOP.set()
                return None, f"usage_limit: {msg[:200]}", usage
            err = f"cli_error: {msg[:200]}"
            time.sleep(10 * (attempt + 1))
            continue
        data = out.get("structured_output")
        if data is None:
            try:
                data = json.loads(out.get("result") or "")
            except json.JSONDecodeError:
                err = "no_structured_output"
                continue
        return data, None, usage
    return None, err, {}


def cached(stage: str, key: str, fn):
    path = CACHE / f"{stage}_{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rec = fn()
    if not rec.get("error"):
        path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return rec


def decompose(note, model: str) -> dict:
    def go():
        data, err, usage = call(J.decompose_params(note.summary, model))
        claims = [{"id": f"c{i}", **c} for i, c in enumerate((data or {}).get("claims", []), 1)]
        return {"noteId": note.noteId, "claims": claims, "error": err, "usage": usage}
    return cached(f"decompose-{J.slug(model)}-{J.prompt('decompose')[1][:8]}", note.noteId, go)


def judge(note, claims: list[dict], by_note: dict, model: str, effort: str) -> dict:
    in_scope = [c for c in claims if c["type"] != "about_post"]
    sources = J.note_sources(note, by_note)
    meta = {"noteId": note.noteId, "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources]}
    if not in_scope or not sources:
        return {**meta, "skip": "no_checkable_claims" if not in_scope else "no_retrieved_sources", "verdicts": []}

    def go():
        data, err, usage = call(J.judge_params(in_scope, sources, model, effort))
        if err:
            return {**meta, "error": err}
        rec = {**meta, "usage": usage, "source_issues": data.get("source_issues", []),
               "verdicts": J.check_verdicts(data, in_scope, sources)}
        bad = [v for v in rec["verdicts"] if v["quote_verified"] is False or v["label"] == "MISSING"]
        if bad:  # one re-ask for quotes not found verbatim; still failing -> UNVERIFIED
            ids = {v["claim_id"] for v in bad}
            sub = [c for c in in_scope if c["id"] in ids]
            extra = ("In an earlier pass, the quote given for each of these claims was not found verbatim in the "
                     "source named, or no verdict was given. Re-check each claim. Copy the deciding passage exactly "
                     "as it appears in the source, or use NOT_IN_SOURCE if no passage establishes the claim.\n\n")
            d2, e2, u2 = call(J.judge_params(sub, sources, model, effort, extra))
            rec["usage_reask"] = u2
            redo = {v["claim_id"]: v for v in J.check_verdicts(d2 or {}, sub, sources)}
            for i, v in enumerate(rec["verdicts"]):
                if v["claim_id"] in ids:
                    nv = redo.get(v["claim_id"])
                    ok = nv and nv["label"] != "MISSING" and nv["quote_verified"] is not False
                    rec["verdicts"][i] = {**(nv if ok else (nv or v)), "reasked": True,
                                          **({} if ok else {"label": "UNVERIFIED"})}
        return rec
    return cached(f"judge-{J.slug(model)}-{effort}-{J.prompt('judge')[1][:8]}", note.noteId, go)


def run_parallel(items, fn, workers: int, label: str) -> list:
    out, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(fn, it) for it in items]
        for i, f in enumerate(as_completed(futs), 1):
            out.append(f.result())
            if i % 20 == 0 or i == len(futs):
                errs = sum(1 for r in out if r.get("error"))
                print(f"[{time.strftime('%H:%M:%S')}] {label}: {i}/{len(futs)} done, {errs} errors, "
                      f"{(time.time() - t0) / i:.1f}s/note", flush=True)
            if STOP.is_set():
                print("Subscription usage limit reached: stopping. Re-run the same command after the reset; "
                      "finished notes are cached.", flush=True)
                for g in futs:
                    g.cancel()
                break
    return out


def api_equiv(recs: list[dict]) -> float:
    return sum((r.get(k) or {}).get("api_equiv_usd", 0) for r in recs for k in ("usage", "usage_reask"))


def cmd_pilot(limit: int, model: str, effort: str, workers: int) -> None:
    notes = J.load_notes("pilot")
    if limit:
        notes = notes.head(limit)
    by_note = J.load_sources()

    def one(note):
        d = decompose(note, model)
        rec = judge(note, d["claims"], by_note, model, effort)
        return {**rec, "stratum": note.stratum, "summary": note.summary, "claims": d["claims"],
                "decompose_error": d.get("error"), "usage_decompose": d.get("usage", {})}

    recs = run_parallel(list(notes.itertuples()), one, workers, "pilot")
    (J.RUNS / f"pilot_{J.slug(model)}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs),
                                                         encoding="utf-8")
    J.write_pilot_report(recs, model)
    labels = [v["label"] for r in recs for v in r.get("verdicts", [])]
    ver = [v["quote_verified"] for r in recs for v in r.get("verdicts", []) if v.get("quote_verified") is not None]
    print(f"pilot: {len(recs)} notes, {len(labels)} verdicts {dict((l, labels.count(l)) for l in set(labels))}; "
          f"quotes verified {sum(ver)}/{len(ver)}; API-equivalent ${api_equiv(recs) + sum(api_equiv([{'usage': r['usage_decompose']}]) for r in recs):.2f}")
    print(f"report: {J.RUNS / f'pilot_report_{J.slug(model)}.md'}")


def cmd_run(stage: str, split: str, model: str, effort: str, workers: int) -> None:
    notes = J.load_notes(split)
    if stage == "decompose":
        recs = run_parallel(list(notes.itertuples()), lambda n: decompose(n, model), workers, "decompose")
        done = [r for r in recs if not r.get("error")]
        J.claims_path(split).write_text("\n".join(json.dumps({k: r[k] for k in ("noteId", "claims")} | {"error": None},
                                                             ensure_ascii=False) for r in done), encoding="utf-8")
        print(f"claims for {len(done)}/{len(notes)} notes -> {J.claims_path(split).name}")
    else:
        claims = {json.loads(l)["noteId"]: json.loads(l)["claims"]
                  for l in J.claims_path(split).read_text(encoding="utf-8").splitlines()}
        by_note = J.load_sources()
        todo = [n for n in notes.itertuples() if n.noteId in claims]
        recs = run_parallel(todo, lambda n: judge(n, claims[n.noteId], by_note, model, effort), workers, "judge")
        done = [r for r in recs if not r.get("error")]
        out = J.RUNS / f"verdicts_{split}_{J.slug(model)}.jsonl"
        out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in done), encoding="utf-8")
        reasked = sum(1 for r in done if "usage_reask" in r)
        print(f"verdicts for {len(done)}/{len(todo)} notes -> {out.name}; re-asked {reasked}")
    print(f"API-equivalent cost of this run (covered by the subscription): ${api_equiv(recs):.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "run"])
    ap.add_argument("stage", nargs="?", choices=["decompose", "judge"])
    ap.add_argument("--split", default="main")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default="high")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    print(f"claude binary: {BIN}\nmodel: {a.model}, judge effort: {a.effort}", flush=True)
    if a.cmd == "pilot":
        cmd_pilot(a.limit, a.model, a.effort, a.workers)
    else:
        cmd_run(a.stage, a.split, a.model, a.effort, a.workers)


if __name__ == "__main__":
    main()
