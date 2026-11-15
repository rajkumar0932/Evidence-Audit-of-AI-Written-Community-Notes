"""Recompute the paper's headline numbers from the released files, standard library only.

    python verify.py

Reads data/release/note_outcomes.csv, retrieval_funnel.csv, rater_tags_population.csv and
judge_validation.json, and prints every number the report quotes. Bootstrap CIs and permutation
p-values come from scripts/07_analysis.py (they need numpy); point estimates are recomputed here
independently.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

R = Path(__file__).parent / "data" / "release"


def rows(name):
    with open(R / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def num(x):
    return float(x) if x not in ("", "nan", "NaN", None) else None


def main():
    if (R / "retrieval_funnel.csv").exists():
        print("== Checkability (main sample) ==")
        for r in rows("retrieval_funnel.csv"):
            print(f"  {r['group']:<9} notes {r['notes']:>4}  >=1 text {float(r['share_notes_any_text']):.1%}  "
                  f"all retrieved {float(r['share_notes_all_retrieved']):.1%}  "
                  f"all retrieved+pinned {float(r['share_notes_all_pinned']):.1%}")

    if (R / "rater_tags_population.csv").exists():
        print("== Rater tags, all main-window notes ==")
        for r in rows("rater_tags_population.csv"):
            if r["status"] == "CRH":
                print(f"  {r['group']:<9} CRH notes {r['notes']:>6}  'cites high-quality sources' "
                      f"{float(r['share_ratings_helpfulGoodSources']):.1%} of ratings")

    if (R / "note_outcomes.csv").exists():
        print("== UNSUPPORTED (>=1 checkable claim NOT_IN_SOURCE or CONTRADICTED) ==")
        cells = defaultdict(list)
        full = defaultdict(list)
        for r in rows("note_outcomes.csv"):
            u = num(r["unsupported"])
            if u is not None:
                cells[r["stratum"]].append(u)
                if r["all_sources_retrieved"] == "True":
                    full[r["stratum"]].append(u)
        for k in sorted(cells):
            v, f = cells[k], full[k]
            fs = f"{sum(f) / len(f):.1%} (n={len(f)})" if f else "n/a"
            print(f"  {k:<14} {sum(v) / len(v):.1%} (n={len(v)})   all-sources-retrieved subset: {fs}")
        a, b = cells.get("cw|CRH", []), cells.get("human|CRH", [])
        if a and b:
            print(f"  H1 point estimate cw|CRH - human|CRH: {sum(a) / len(a) - sum(b) / len(b):+.1%}")

    if (R / "judge_validation.json").exists():
        v = json.loads((R / "judge_validation.json").read_text(encoding="utf-8"))
        print("== Judge vs blind human labels ==")
        for k in ("all", "ai_authored", "human_authored"):
            print(f"  {k:<15} {v[k]}")


if __name__ == "__main__":
    main()
