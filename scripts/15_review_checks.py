"""Additional analyses requested in internal review (16 Nov 2026). Exploratory unless stated.

Output: data/release/review_checks.json
Run:    uv run python scripts/15_review_checks.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score, roc_auc_score

from common import INTERIM, RELEASE, SEED

rng = np.random.default_rng(SEED + 99)
RUNS = INTERIM / "judge_runs"
LAB = {"SUPPORTED", "PARTIAL", "NOT_IN_SOURCE", "CONTRADICTED"}
UNS = {"NOT_IN_SOURCE", "CONTRADICTED"}


def verdict_table(slug: str) -> pd.DataFrame:
    rows = []
    for l in (RUNS / f"verdicts_main_{slug}.jsonl").read_text(encoding="utf-8").split("\n"):
        if l.strip():
            r = json.loads(l)
            for v in r.get("verdicts", []):
                rows.append({"noteId": r["noteId"], "claim_id": v["claim_id"], "label": v["label"]})
    return pd.DataFrame(rows)


def per_note(v: pd.DataFrame) -> pd.DataFrame:
    v = v[v.label.isin(LAB)]
    g = v.groupby("noteId").label
    return pd.DataFrame({"n": g.size(), "sup_share": g.apply(lambda s: (s == "SUPPORTED").mean()),
                         "uns_share": g.apply(lambda s: s.isin(UNS).mean()),
                         "uns_any": g.apply(lambda s: s.isin(UNS).any())})


def boot_diff(a, b, n=10000):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a.mean() - b.mean()
    bs = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean() for _ in range(n)]
    pool = np.concatenate([a, b]); perm = []
    for _ in range(n):
        rng.shuffle(pool)
        perm.append(pool[: len(a)].mean() - pool[len(a):].mean())
    p = max((np.abs(perm) >= abs(d)).mean(), 1 / n)
    return {"diff": round(float(d), 4), "lo": round(float(np.percentile(bs, 2.5)), 4),
            "hi": round(float(np.percentile(bs, 97.5)), 4), "p_perm": round(float(p), 4), "n_a": len(a), "n_b": len(b)}


def main() -> None:
    out = {}
    ids = pd.read_csv(RELEASE / "sample_ids.csv", dtype={"noteId": str})
    main_ids = ids[ids.split == "main"].set_index("noteId")
    oc = pd.read_csv(RELEASE / "note_outcomes.csv", dtype={"noteId": str}).set_index("noteId")
    haiku = per_note(verdict_table("claude-haiku-5-5"))
    haiku = haiku.join(main_ids[["group", "stratum"]], how="inner")

    # 1. claim-level support: mean per-note share (notes are the resampling unit) + pooled share
    crh = haiku[haiku.stratum.str.endswith("|CRH")]
    out["claim_support_CRH"] = {
        g: {"notes": int(len(d)), "mean_per_note": round(float(d.sup_share.mean()), 4),
            "pooled_share": round(float((d.sup_share * d.n).sum() / d.n.sum()), 4)}
        for g, d in crh.groupby("group")}
    out["claim_support_CRH_test_cw_minus_human"] = boot_diff(crh[crh.group == "cw"].sup_share, crh[crh.group == "human"].sup_share)
    out["claim_support_CRH_test_ai_other_minus_human"] = boot_diff(crh[crh.group == "ai_other"].sup_share, crh[crh.group == "human"].sup_share)
    a = crh[crh.group == "ai_other"].sup_share.values
    bs = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(10000)]
    out["claim_support_CRH_ai_other_ci"] = [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]

    # 2. claims per note by writer (all sampled notes; judged = checkable claims with a verdict)
    claims = {(r := json.loads(l))["noteId"]: r["claims"] for l in (RUNS / "claims_main.jsonl").read_text(encoding="utf-8").split("\n") if l.strip()}
    cpn = pd.DataFrame([{"noteId": n, "claims": len(c), "in_scope": sum(x["type"] != "about_post" for x in c)} for n, c in claims.items()]).set_index("noteId").join(main_ids.group)
    cpn["judged"] = haiku.n.reindex(cpn.index).fillna(0)
    out["claims_per_note"] = cpn.groupby("group")[["claims", "in_scope", "judged"]].mean().round(2).to_dict(orient="index")
    out["claims_per_judged_note_by_group"] = haiku.groupby("group").n.mean().round(2).to_dict()
    out["claim_accounting"] = {"claims": int(cpn.claims.sum()), "about_post": int((cpn.claims - cpn.in_scope).sum()),
                               "in_scope_in_unjudged_notes": int(cpn[cpn.judged == 0].in_scope.sum()),
                               "verdicts": int(verdict_table("claude-haiku-5-5").shape[0])}

    # 3. H3 extras
    h = oc[(oc.n_ratings >= 5) & oc.unsupported.notna() & oc.share_notHelpfulIrrelevantSources.notna()].join(haiku[["uns_share"]], how="left")
    out["H3_n"] = int(len(h))
    out["H3_notes_with_zero_tag"] = int((h.share_notHelpfulIrrelevantSources == 0).sum())
    rho, p = spearmanr(h.share_notHelpfulIrrelevantSources, h.uns_share, nan_policy="omit")
    out["H3_spearman_tag_vs_unsupported_claim_share"] = {"rho": round(float(rho), 3), "p": round(float(p), 4)}
    maj = (h.uns_share >= 0.5).astype(int)
    out["H3_auroc_majority_unsupported"] = round(float(roc_auc_score(maj, h.share_notHelpfulIrrelevantSources)), 3)
    out["H3_auroc_excluding_zero_tag_notes"] = round(float(roc_auc_score(
        h[h.share_notHelpfulIrrelevantSources > 0].unsupported.astype(int),
        h[h.share_notHelpfulIrrelevantSources > 0].share_notHelpfulIrrelevantSources)), 3)

    # 4. ceiling: how well does a second judge's note-level score predict the primary label?
    gem = per_note(verdict_table("gemini-3-5-flash-lite"))
    j = haiku[["uns_any"]].join(gem[["uns_share", "uns_any"]], rsuffix="_gem", how="inner")
    out["ceiling_gemini_predicts_haiku"] = {"notes": int(len(j)),
                                            "auroc": round(float(roc_auc_score(j.uns_any.astype(int), j.uns_share)), 3),
                                            "kappa_binary": round(float(cohen_kappa_score(j.uns_any, j.uns_any_gem)), 3)}

    # 5. power: SE implied by the H1 interval and the gap detectable with 80% power
    res = json.loads((RELEASE / "results.json").read_text(encoding="utf-8"))
    h1 = res["primary"]["H1_cw_minus_human_CRH"]
    se = (h1["hi"] - h1["lo"]) / 3.92
    out["power"] = {"se_points": round(se * 100, 1), "detectable_gap_80pct_points": round((1.96 + 0.84) * se * 100, 1)}

    # 6. checkability weighted to the population (strata weights)
    sizes = pd.read_csv(RELEASE / "strata_sizes.csv").set_index("stratum").population
    idx = pd.read_csv(INTERIM / "sources_index.csv", dtype={"noteId": str})
    idx = idx[idx.split == "main"]
    idx["ok"] = idx.n_chars >= 200
    pn = idx.groupby("noteId").agg(n=("url", "size"), ok=("ok", "sum")).join(main_ids.stratum)
    pn["all"] = pn.ok == pn.n
    pn["w"] = pn.stratum.map(sizes) / pn.stratum.map(pn.stratum.value_counts())
    out["checkability_weighted"] = {"any_text": round(float((pn.w * (pn.ok > 0)).sum() / pn.w.sum()), 3),
                                    "all_retrieved": round(float((pn.w * pn["all"]).sum() / pn.w.sum()), 3),
                                    "unweighted_all_retrieved": round(float(pn["all"].mean()), 3),
                                    "notes_without_any_text_source": int((pn.ok == 0).sum())}

    # 7. retrieval success by route (successful = >=200 chars of text)
    f = idx[idx.cls.isin(["web", "wiki"])]
    out["retrieval_by_route"] = {"fetchable": int(len(f)), "retrieved": int(f.ok.sum()), "failed": int((~f.ok).sum()),
                                 "retrieved_by_method": f[f.ok].method.value_counts().to_dict(),
                                 "strictly_before_note": int(f[f.ok & f.method.isin(["wayback_before", "wiki_rev", "cited_archive"])].shape[0])}

    # 8. age of pre-note snapshots (days between snapshot and note)
    ages, after = [], []
    for p in (INTERIM / "sources").glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("split") != "main" or r.get("n_chars", 0) < 200 or not r.get("snapshot"):
            continue
        s = str(r["snapshot"])
        try:
            snap = datetime.strptime(s[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc) if s[:8].isdigit() else \
                datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            continue
        note = datetime.fromtimestamp(r["note_ms"] / 1000, timezone.utc)
        days = (note - snap).total_seconds() / 86400
        (ages if r["method"] in ("wayback_before", "wiki_rev") else after if r["method"] == "wayback_after" else []).append(days)
    ages, after = np.array(ages), np.array(after)
    out["snapshot_age_days_before_note"] = {"n": int(len(ages)), "median": round(float(np.median(ages)), 1),
                                            "p75": round(float(np.percentile(ages, 75)), 1),
                                            "p90": round(float(np.percentile(ages, 90)), 1),
                                            "within_1_day": round(float((ages <= 1).mean()), 3)}
    out["snapshot_days_after_note"] = {"n": int(len(after)), "median": round(float(np.median(-after)), 1)}

    # 9. a worked example: a human-written Helpful note's claim judged NOT_IN_SOURCE or CONTRADICTED
    (RELEASE / "review_checks.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
