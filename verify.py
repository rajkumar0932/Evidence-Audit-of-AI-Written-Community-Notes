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

    if (R / "judge_agreement.json").exists():
        a = json.loads((R / "judge_agreement.json").read_text(encoding="utf-8"))
        print("== Judge agreement ==")
        for k in ("haiku_vs_gemini", "haiku_vs_opus"):
            if a.get(k, {}).get("all"):
                print(f"  {k:<16} {a[k]['all']}")
        if a.get("haiku_vs_opus_on_90_validation_claims", {}).get("n_claims"):
            print(f"  vs Opus on 90 validation claims: {a['haiku_vs_opus_on_90_validation_claims']}")
        for j, h in a.get("headline_by_judge", {}).items():
            print(f"  headline under {j:<7} H1 {h['H1_cw_minus_human']}  H3 AUROC {h['H3_auroc']}")

    if (R / "review_checks.json").exists():
        c = json.loads((R / "review_checks.json").read_text(encoding="utf-8"))
        print("== Review checks (exploratory) ==")
        print(f"  claim-level support, CRH, cw - human: {c['claim_support_CRH_test_cw_minus_human']}")
        print(f"  claim-level support, CRH, other AI - human: {c['claim_support_CRH_test_ai_other_minus_human']}")
        print(f"  H3 ceiling (Gemini predicts primary labels): {c['ceiling_gemini_predicts_haiku']}")
        print(f"  H3 zero-tag notes: {c['H3_notes_with_zero_tag']} of {c['H3_n']}; AUROC excluding them: {c['H3_auroc_excluding_zero_tag_notes']}")
        print(f"  power: {c['power']} | weighted checkability: {c['checkability_weighted']}")
        print(f"  claims: {c['claim_accounting']} | retrieval: {c['retrieval_by_route']}")

    if (R / "judge_validation.json").exists():
        v = json.loads((R / "judge_validation.json").read_text(encoding="utf-8"))
        print("== Judge vs blind human labels ==")
        for k in ("all", "ai_authored", "human_authored"):
            print(f"  {k:<15} {v[k]}")


if __name__ == "__main__":
    main()
