"""Judge validation without human labels (pre-registration deviation, 15 Nov 2026):

  1. cross-family agreement: primary judge (claude-haiku-5-5) vs gemini-3.5-flash-lite on shared claims
  2. stronger reference: primary judge vs claude-opus-5-5 on the notes behind the 90 stratified
     validation claims (weighted precision / recall of UNSUPPORTED on those 90 claims)
  3. headline robustness: H1 (cw vs human among CRH notes) and H3 (rater tag AUROC) recomputed
     with each judge's verdicts

Output: data/release/judge_agreement.json
Run:    uv run python scripts/12_judge_agreement.py
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, roc_auc_score

from common import INTERIM, RELEASE, SEED

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RUNS = INTERIM / "judge_runs"
LABELS = ["SUPPORTED", "PARTIAL", "NOT_IN_SOURCE", "CONTRADICTED"]
UNSUP = {"NOT_IN_SOURCE", "CONTRADICTED"}
JUDGES = {"haiku": "claude-haiku-5-5", "gemini": "gemini-3-5-flash-lite", "opus": "claude-opus-5-5"}


def verdicts(slug: str) -> pd.DataFrame:
    p = RUNS / f"verdicts_main_{slug}.jsonl"
    if not p.exists():
        return pd.DataFrame(columns=["noteId", "claim_id", "label"])
    rows = [{"noteId": r["noteId"], "claim_id": v["claim_id"], "label": v["label"]}
            for l in p.read_text(encoding="utf-8").split("\n") if l.strip()
            for r in [json.loads(l)] for v in r.get("verdicts", [])]
    return pd.DataFrame(rows)


def kappa(a, b):
    return round(float(cohen_kappa_score(a, b)), 3) if len(a) > 1 and len(set(a) | set(b)) > 1 else None


def compare(a: pd.DataFrame, b: pd.DataFrame, groups: pd.Series) -> dict:
    m = a.merge(b, on=["noteId", "claim_id"], suffixes=("_a", "_b"))
    m = m[m.label_a.isin(LABELS) & m.label_b.isin(LABELS)]
    if m.empty:
        return {"n": 0}
    m["ai"] = m.noteId.map(groups).isin(["cw", "ai_other"])
    ua, ub = m.label_a.isin(UNSUP), m.label_b.isin(UNSUP)

    def block(d, ua, ub):
        return {"n_claims": int(len(d)), "agreement_4class": round(float((d.label_a == d.label_b).mean()), 3),
                "kappa_4class": kappa(d.label_a, d.label_b),
                "agreement_unsupported": round(float((ua == ub).mean()), 3), "kappa_unsupported": kappa(ua, ub)}

    out = {"all": block(m, ua, ub),
           "ai_authored": block(m[m.ai], ua[m.ai], ub[m.ai]),
           "human_authored": block(m[~m.ai], ua[~m.ai], ub[~m.ai]),
           "confusion_rows_primary_cols_other": pd.crosstab(m.label_a, m.label_b).to_dict(orient="index")}
    na = m.groupby("noteId").apply(lambda d: d.label_a.isin(UNSUP).any(), include_groups=False)
    nb = m.groupby("noteId").apply(lambda d: d.label_b.isin(UNSUP).any(), include_groups=False)
    out["note_level_unsupported"] = {"n_notes": int(len(na)), "agreement": round(float((na == nb).mean()), 3),
                                     "kappa": kappa(na, nb), "rate_primary": round(float(na.mean()), 3),
                                     "rate_other": round(float(nb.mean()), 3)}
    return out


def reference_on_validation(prim: pd.DataFrame, ref: pd.DataFrame) -> dict:
    """Weighted precision/recall of the primary judge's UNSUPPORTED against the reference judge,
    on the 90 stratified validation claims (weights = inverse selection probability)."""
    key = pd.read_csv(INTERIM / "labeling" / "key.csv", dtype={"noteId": str})
    m = key.merge(ref, on=["noteId", "claim_id"]).rename(columns={"label": "ref"})
    m = m[m.ref.isin(LABELS) & m.judge_label.isin(LABELS)]
    if m.empty:
        return {"n": 0}
    j, r, w = m.judge_label.isin(UNSUP), m.ref.isin(UNSUP), m.weight
    tp = (w * (j & r)).sum()
    return {"n_claims": int(len(m)), "kappa_4class": kappa(m.judge_label, m.ref), "kappa_unsupported": kappa(j, r),
            "precision_unsupported_w": round(float(tp / (w * j).sum()), 3),
            "recall_unsupported_w": round(float(tp / (w * r).sum()), 3),
            "agreement_by_primary_label": m.assign(agree=m.judge_label == m.ref)
                                          .groupby("judge_label").agree.mean().round(3).to_dict()}


def headline(v: pd.DataFrame, outcomes: pd.DataFrame, rng) -> dict:
    """Note-level UNSUPPORTED among CRH notes by group, the cw - human gap, and the H3 AUROC, for one judge."""
    v = v[v.label.isin(LABELS)]
    unsup = v.groupby("noteId").label.apply(lambda s: s.isin(UNSUP).any())
    d = outcomes[["noteId", "stratum", "group", "status", "n_ratings", "share_notHelpfulIrrelevantSources"]].copy()
    d["u"] = d.noteId.map(unsup)
    crh = d[(d.status == "CRH") & d.u.notna()]
    rates = crh.groupby("group").u.agg(["mean", "size"]).round(3).to_dict(orient="index")
    a = crh[crh.group == "cw"].u.astype(float).values
    b = crh[crh.group == "human"].u.astype(float).values
    boots = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean() for _ in range(5000)]
    h = d[(d.n_ratings >= 5) & d.u.notna() & d.share_notHelpfulIrrelevantSources.notna()]
    auc = roc_auc_score(h.u.astype(int), h.share_notHelpfulIrrelevantSources) if h.u.nunique() == 2 else None
    return {"CRH_unsupported_by_group": rates,
            "H1_cw_minus_human": {"est": round(float(a.mean() - b.mean()), 3),
                                  "lo": round(float(np.percentile(boots, 2.5)), 3),
                                  "hi": round(float(np.percentile(boots, 97.5)), 3)},
            "H3_auroc": None if auc is None else round(float(auc), 3), "H3_n": int(len(h))}


def main() -> None:
    rng = np.random.default_rng(SEED)
    groups = pd.read_csv(RELEASE / "sample_ids.csv", dtype={"noteId": str}).set_index("noteId").group
    outcomes = pd.read_csv(RELEASE / "note_outcomes.csv", dtype={"noteId": str})
    v = {k: verdicts(s) for k, s in JUDGES.items()}
    res = {"haiku_vs_gemini": compare(v["haiku"], v["gemini"], groups),
           "haiku_vs_opus": compare(v["haiku"], v["opus"], groups),
           "gemini_vs_opus": compare(v["gemini"], v["opus"], groups),
           "haiku_vs_opus_on_90_validation_claims": reference_on_validation(v["haiku"], v["opus"]),
           "headline_by_judge": {k: headline(v[k], outcomes, rng) for k in ("haiku", "gemini") if len(v[k])}}
    (RELEASE / "judge_agreement.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for k, r in res.items():
        print(f"\n== {k}")
        print(json.dumps(r if k != "headline_by_judge" else r, indent=1, default=str)[:1500])


if __name__ == "__main__":
    main()
