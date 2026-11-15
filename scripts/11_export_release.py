"""Export claim-level verdicts for the public release (no note text; claims, labels, quotes, sources).

Output: data/release/verdicts_<model>.csv, one row per claim
Run:    uv run python scripts/11_export_release.py [--model claude-haiku-5-5]
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from common import INTERIM, RELEASE


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-5-5")
    a = ap.parse_args()
    slug = "".join(ch if ch.isalnum() else "-" for ch in a.model.lower())
    runs = INTERIM / "judge_runs"
    claims = {(r := json.loads(l))["noteId"]: r["claims"]
              for l in (runs / "claims_main.jsonl").read_text(encoding="utf-8").split("\n") if l.strip()}
    strata = pd.read_csv(RELEASE / "sample_ids.csv", dtype={"noteId": str}).set_index("noteId").stratum
    rows = []
    for l in (runs / f"verdicts_main_{slug}.jsonl").read_text(encoding="utf-8").split("\n"):
        r = json.loads(l)
        verdicts = {v["claim_id"]: v for v in r.get("verdicts", [])}
        src = {s["id"]: s for s in r.get("sources", [])}
        for c in claims.get(r["noteId"], []):
            v = verdicts.get(c["id"], {})
            s = src.get(v.get("source_id", ""), {})
            rows.append({"noteId": r["noteId"], "stratum": strata.get(r["noteId"]), "claim_id": c["id"],
                         "claim": c["text"], "claim_type": c["type"],
                         "label": v.get("label", "about_post" if c["type"] == "about_post" else r.get("skip", "")),
                         "quote_verified": v.get("quote_verified"), "reasked": v.get("reasked", False),
                         "source_url": s.get("url", ""), "source_retrieval": s.get("retrieved", ""),
                         "quote": v.get("quote", ""), "reason": v.get("reason", "")})
    out = RELEASE / f"verdicts_{slug}.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"{len(rows)} claims -> {out}")


if __name__ == "__main__":
    main()
