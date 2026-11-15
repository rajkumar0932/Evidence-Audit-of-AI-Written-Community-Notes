"""Pre-registered analysis (PREREGISTRATION.md sections 5-8).

Inputs: sample, retrieved-source cache, claims, verdicts, ratings.
Outputs:
  data/release/note_outcomes.csv   one row per sampled note: counts of claims by verdict, outcomes, checkability,
                                   rater-tag shares (no note text)
  data/release/results.json        cell estimates with 95% bootstrap CIs, H1/H2a/H2b/H3 tests, Holm-adjusted
                                   p-values, checkability (D1), sensitivity analyses

Run:  uv run python scripts/07_analysis.py [--model claude-opus-5-5] [--second claude-sonnet-5-5]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.metrics import roc_auc_score

from common import INTERIM, RELEASE, SEED

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LABELS = {"SUPPORTED", "PARTIAL", "NOT_IN_SOURCE", "CONTRADICTED"}
N_BOOT = N_PERM = 10_000
SRC_TAGS = ["notHelpfulIrrelevantSources", "helpfulGoodSources", "notHelpfulSourcesMissingOrUnreliable",
            "notHelpfulIncorrect"]


def slug(model: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in model.lower()).strip("-")


def jsonl(path: Path) -> dict:
    if not path.exists():
        return {}
    return {(r := json.loads(l))["noteId"]: r for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


# ------------------------------------------------------------------ per-note outcomes
def source_stats(src_dir: Path) -> pd.DataFrame:
    rows = []
    for p in src_dir.glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        rows.append({"noteId": r["noteId"], "ok": r.get("n_chars", 0) >= 200, "pinned": bool(r.get("pinned")),
                     "wiki": r.get("cls") == "wiki"})
    s = pd.DataFrame(rows)
    if s.empty:
        return pd.DataFrame(columns=["n_retrieved", "n_retrieved_pinned", "cites_wiki"])
    g = s.groupby("noteId")
    return pd.DataFrame({"n_retrieved": g.ok.sum(), "n_retrieved_pinned": (s.ok & s.pinned).groupby(s.noteId).sum(),
                         "cites_wiki": g.wiki.any()})


def outcomes(notes: pd.DataFrame, claims: dict, verdicts: dict, src: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for n in notes.itertuples():
        cl = claims.get(n.noteId, {}).get("claims", [])
        in_scope = [c for c in cl if c["type"] != "about_post"]
        labels = [v["label"] for v in verdicts.get(n.noteId, {}).get("verdicts", [])]
        k = {lab: labels.count(lab) for lab in ("SUPPORTED", "PARTIAL", "NOT_IN_SOURCE", "CONTRADICTED", "UNVERIFIED", "MISSING")}
        judged = sum(k[lab] for lab in LABELS)
        rows.append({"noteId": n.noteId, "stratum": n.stratum, "group": n.group, "status": n.stratum.split("|")[1],
                     "author": n.author, "n_urls": n.n_urls, "note_chars": len(n.summary),
                     "n_claims": len(cl), "n_in_scope": len(in_scope), "n_about_post": len(cl) - len(in_scope),
                     "n_judged": judged, **{f"n_{lab.lower()}": v for lab, v in k.items()}})
    df = pd.DataFrame(rows).merge(src, left_on="noteId", right_index=True, how="left")
    df[["n_retrieved", "n_retrieved_pinned"]] = df[["n_retrieved", "n_retrieved_pinned"]].fillna(0).astype(int)
    df["cites_wiki"] = df.cites_wiki.fillna(False).astype(bool)
    df["checkable"] = df.n_judged > 0
    df["all_sources_retrieved"] = df.n_retrieved >= df.n_urls
    df["all_retrieved_pinned"] = (df.n_retrieved > 0) & (df.n_retrieved_pinned == df.n_retrieved)
    bad = df.n_not_in_source + df.n_contradicted
    df["unsupported"] = np.where(df.checkable, bad > 0, np.nan)
    df["unsupported_partial"] = np.where(df.checkable, (bad + df.n_partial) > 0, np.nan)
    df["unsupported_unverified"] = np.where(df.checkable | (df.n_unverified > 0), (bad + df.n_unverified) > 0, np.nan)
    df["contradicted"] = np.where(df.checkable, df.n_contradicted > 0, np.nan)
    df["claim_support_rate"] = np.where(df.checkable, df.n_supported / df.n_judged.clip(lower=1), np.nan)
    if not ratings.empty:
        r = ratings.groupby("noteId")[["n", *SRC_TAGS]].sum()
        df = df.merge(r.rename(columns={"n": "n_ratings"}), left_on="noteId", right_index=True, how="left")
        df["n_ratings"] = df.n_ratings.fillna(0).astype(int)
        for t in SRC_TAGS:
            df[f"share_{t}"] = df[t] / df.n_ratings.where(df.n_ratings > 0)
        df = df.drop(columns=SRC_TAGS)
    return df


# ------------------------------------------------------------------ statistics
def boot_mean(x, rng) -> dict:
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return {"n": 0, "est": None, "lo": None, "hi": None}
    m = x[rng.integers(0, len(x), (N_BOOT, len(x)))].mean(axis=1)
    return {"n": int(len(x)), "est": round(float(x.mean()), 4), "lo": round(float(np.percentile(m, 2.5)), 4),
            "hi": round(float(np.percentile(m, 97.5)), 4)}


def diff_test(a, b, rng, alternative: str = "two-sided") -> dict:
    """mean(a) - mean(b): bootstrap CI and permutation p-value."""
    a, b = (np.asarray(v, float) for v in (a, b))
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return {"est": None}
    d = a.mean() - b.mean()
    boots = (a[rng.integers(0, len(a), (N_BOOT, len(a)))].mean(1) - b[rng.integers(0, len(b), (N_BOOT, len(b)))].mean(1))
    pool = np.concatenate([a, b])
    perm = np.empty(N_PERM)
    for i in range(N_PERM):
        rng.shuffle(pool)
        perm[i] = pool[: len(a)].mean() - pool[len(a):].mean()
    p = (np.abs(perm) >= abs(d)).mean() if alternative == "two-sided" else (perm >= d).mean()
    return {"est": round(float(d), 4), "lo": round(float(np.percentile(boots, 2.5)), 4),
            "hi": round(float(np.percentile(boots, 97.5)), 4), "p": round(float(max(p, 1 / N_PERM)), 5),
            "n_a": int(len(a)), "n_b": int(len(b)), "alternative": alternative}


def status_gap(df: pd.DataFrame, sizes: pd.DataFrame, col: str, rng) -> dict:
    """H2a: weighted average over groups of the WITHIN-group gap mean(col|CRNH) - mean(col|CRH).

    Weights are each group's CRH+CRNH population. (Pooling CRNH and CRH separately by population would
    confound the gap with group composition: cw dominates CRH but has only 78 CRNH notes.)
    p: one-sided permutation of status within group. CI: bootstrap within strata.
    """
    w = sizes.set_index("stratum").population
    d0 = df[df.status.isin(["CRH", "CRNH"]) & df[col].notna()]
    parts = []
    for g, dg in d0.groupby("group"):
        nh = (dg.status == "CRNH").to_numpy()
        if nh.any() and (~nh).any():
            parts.append((float(w.get(f"{g}|CRH", 0) + w.get(f"{g}|CRNH", 0)), dg[col].to_numpy(float), nh))
    if not parts:
        return {"est": None}

    def stat(ps) -> float:
        num = sum(om * (y[m].mean() - y[~m].mean()) for om, y, m in ps)
        return num / sum(om for om, _, _ in ps)

    obs = stat(parts)
    perm = np.array([stat([(om, y, rng.permutation(m)) for om, y, m in parts]) for _ in range(N_PERM)])
    boots = np.empty(N_BOOT)
    for i in range(N_BOOT):
        ps = []
        for om, y, m in parts:
            a, b = y[m], y[~m]
            ya = a[rng.integers(0, len(a), len(a))]
            yb = b[rng.integers(0, len(b), len(b))]
            ps.append((om, np.concatenate([ya, yb]), np.r_[np.ones(len(ya), bool), np.zeros(len(yb), bool)]))
        boots[i] = stat(ps)
    return {"est": round(float(obs), 4), "lo": round(float(np.percentile(boots, 2.5)), 4),
            "hi": round(float(np.percentile(boots, 97.5)), 4),
            "p_one_sided": round(float(max((perm >= obs).mean(), 1 / N_PERM)), 5),
            "groups": [g for g, dg in d0.groupby("group")]}


def auroc(df: pd.DataFrame, score_col: str, rng, threshold: float = 0.65) -> dict:
    d = df[(df.n_ratings >= 5) & df.unsupported.notna() & df[score_col].notna()]
    y, s = d.unsupported.astype(int).values, d[score_col].values
    if len(d) < 10 or y.min() == y.max():
        return {"n": int(len(d)), "auroc": None}
    a = roc_auc_score(y, s)
    boots = []
    for _ in range(N_BOOT // 5):
        i = rng.integers(0, len(d), len(d))
        if y[i].min() != y[i].max():
            boots.append(roc_auc_score(y[i], s[i]))
    boots = np.array(boots)
    return {"n": int(len(d)), "n_unsupported": int(y.sum()), "auroc": round(float(a), 4),
            "lo": round(float(np.percentile(boots, 2.5)), 4), "hi": round(float(np.percentile(boots, 97.5)), 4),
            "p_auroc_ge_threshold": round(float(max((boots >= threshold).mean(), 1 / len(boots))), 5)}


def holm(pvals: dict) -> dict:
    items = sorted((p, k) for k, p in pvals.items() if p is not None)
    out, running = {}, 0.0
    m = len(items)
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = round(running, 5)
    return out


def h2b(df: pd.DataFrame) -> dict:
    d = df[df.unsupported.notna()].copy()
    d["y"] = d.unsupported.astype(int)
    d["log_chars"] = np.log1p(d.note_chars)
    try:
        m = smf.logit("y ~ C(status, Treatment('CRH')) * C(group, Treatment('human')) + n_urls + log_chars",
                      data=d).fit(disp=0)
    except Exception as e:  # separation or too few events in a cell
        return {"error": f"{type(e).__name__}: {e}"[:200]}
    term = "C(status, Treatment('CRH'))[T.CRNH]:C(group, Treatment('human'))[T.cw]"
    ci = m.conf_int()
    return {"n": int(m.nobs), "term": term,
            "coef": round(float(m.params.get(term, np.nan)), 4),
            "lo": round(float(ci.loc[term, 0]), 4) if term in ci.index else None,
            "hi": round(float(ci.loc[term, 1]), 4) if term in ci.index else None,
            "p": round(float(m.pvalues.get(term, np.nan)), 5),
            "pseudo_r2": round(float(m.prsquared), 4)}


# ------------------------------------------------------------------ main
def analyse(df: pd.DataFrame, sizes: pd.DataFrame, rng) -> dict:
    res = {"cells": {}}
    for stratum, d in df.groupby("stratum"):
        res["cells"][stratum] = {
            "notes": int(len(d)),
            "unsupported": boot_mean(d.unsupported, rng),
            "contradicted": boot_mean(d.contradicted, rng),
            "claim_support_rate": boot_mean(d.claim_support_rate, rng),
            "checkable_share": round(float(d.checkable.mean()), 4),
            "all_sources_retrieved_share": round(float(d.all_sources_retrieved.mean()), 4),
            "median_claims": float(d.n_claims.median()), "about_post_claims": int(d.n_about_post.sum())}
    cw, hu = df[df.stratum == "cw|CRH"], df[df.stratum == "human|CRH"]
    res["H1_cw_minus_human_CRH"] = diff_test(cw.unsupported, hu.unsupported, rng)
    res["H2a_CRNH_minus_CRH_within_group"] = status_gap(df, sizes, "unsupported", rng)
    res["H2b_interaction"] = h2b(df)
    if "share_notHelpfulIrrelevantSources" in df:
        res["H3_auroc_irrelevant_sources_tag"] = auroc(df, "share_notHelpfulIrrelevantSources", rng)
        res["H3_secondary"] = {t: auroc(df, f"share_{t}", rng) for t in SRC_TAGS[1:]}
        res["H3_CRH_only"] = auroc(df[df.status == "CRH"], "share_notHelpfulIrrelevantSources", rng)
    res["holm"] = holm({"H1": res["H1_cw_minus_human_CRH"].get("p"),
                        "H2a": res["H2a_CRNH_minus_CRH_within_group"].get("p_one_sided"),
                        "H3": res.get("H3_auroc_irrelevant_sources_tag", {}).get("p_auroc_ge_threshold")})
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--second", default="")
    ap.add_argument("--runs-dir", default=str(INTERIM / "judge_runs"))
    ap.add_argument("--release-dir", default=str(RELEASE))
    a = ap.parse_args()
    runs, release = Path(a.runs_dir), Path(a.release_dir)
    rng = np.random.default_rng(SEED)

    notes = pd.read_parquet(INTERIM / "sample_main.parquet")
    sizes = pd.read_csv(RELEASE / "strata_sizes.csv")
    claims = jsonl(runs / "claims_main.jsonl")
    ratings_path = INTERIM / "ratings_by_note.csv"
    ratings = pd.read_csv(ratings_path, dtype={"noteId": str}) if ratings_path.exists() else pd.DataFrame()
    src = source_stats(INTERIM / "sources")
    df = outcomes(notes, claims, jsonl(runs / f"verdicts_main_{slug(a.model)}.jsonl"), src, ratings)
    df.drop(columns=["author"]).to_csv(release / "note_outcomes.csv", index=False)

    res = {"model": a.model, "primary": analyse(df, sizes, rng)}
    # D1: checkability, per group (population-weighted over statuses) and per cell
    w = sizes.set_index("stratum").population
    res["D1_checkability"] = {
        g: {k: round(float((d[k] * d.stratum.map(w)).sum() / d.stratum.map(w).sum()), 4)
            for k in ("checkable", "all_sources_retrieved", "all_retrieved_pinned")}
        for g, d in df.groupby("group")}

    sens = {}
    for name, col, mask in (("partial_as_unsupported", "unsupported_partial", None),
                            ("unverified_as_unsupported", "unsupported_unverified", None),
                            ("all_sources_retrieved", "unsupported", df.all_sources_retrieved),
                            ("pinned_sources_only", "unsupported", df.all_retrieved_pinned),
                            ("excluding_wikipedia_citers", "unsupported", ~df.cites_wiki)):
        d = df if mask is None else df[mask]
        d = d.assign(unsupported=d[col])
        sens[name] = {"H1": diff_test(d[d.stratum == "cw|CRH"].unsupported, d[d.stratum == "human|CRH"].unsupported, rng),
                      "H2a": status_gap(d, sizes, "unsupported", rng)}
    loo = {}
    for author in sorted(df[df.group == "cw"].author.unique()):
        d = df[(df.stratum == "cw|CRH") & (df.author != author)]
        loo[author[:10]] = boot_mean(d.unsupported, rng)["est"]
    sens["leave_one_cw_account_out_cw_CRH_unsupported"] = loo
    if a.second:
        d2 = outcomes(notes, claims, jsonl(runs / f"verdicts_main_{slug(a.second)}.jsonl"), src, ratings)
        sens[f"second_judge_{a.second}"] = analyse(d2, sizes, rng)
    res["sensitivity"] = sens
    (release / "results.json").write_text(json.dumps(res, indent=2, default=lambda o: None), encoding="utf-8")

    p = res["primary"]
    print("UNSUPPORTED (>=1 checkable claim not in source / contradicted), by cell:")
    for k, v in p["cells"].items():
        u = v["unsupported"]
        est = "n/a" if u["est"] is None else f"{u['est']:.1%} [{u['lo']:.1%}, {u['hi']:.1%}]"
        print(f"  {k:<14} notes {v['notes']:>3}  checkable {u['n']:>3}  {est}")
    for k in ("H1_cw_minus_human_CRH", "H2a_CRNH_minus_CRH_within_group", "H2b_interaction", "H3_auroc_irrelevant_sources_tag"):
        print(f"{k}: {p.get(k)}")
    print("Holm:", p["holm"])
    print(f"wrote {release / 'note_outcomes.csv'} and {release / 'results.json'}")


if __name__ == "__main__":
    main()
