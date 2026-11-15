"""Paper figures (PDF + PNG) in paper/figures/. Each figure is drawn only when its inputs exist.

  fig_checkability   share of notes whose evidence can be retrieved / fully retrieved / time-pinned
  fig_unsupported    share of notes with >=1 claim their own sources do not support, by group x status, 95% CI
  fig_roc            rater "sources do not support note" tag share vs verified UNSUPPORTED (ROC)
  fig_claim_types    which kinds of claims are unsupported

Palette validated with the dataviz validator (light, all-pairs): blue / orange / aqua. Aqua is below 3:1
contrast on white, so every bar carries a printed value label and each figure has a table in the paper.
Run:  uv run python scripts/10_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score, roc_curve  # noqa: E402

from common import INTERIM, RELEASE, ROOT  # noqa: E402

OUT = ROOT / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
GROUPS = ["cw", "ai_other", "human"]
NAMES = {"cw": "X's Community Writer", "ai_other": "Other AI writers", "human": "Human writers"}
COLOR = {"cw": "#2a78d6", "ai_other": "#eb6834", "human": "#1baf7a"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False, "savefig.bbox": "tight", "savefig.dpi": 200,
})


def save(fig, name: str) -> None:
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}")
    plt.close(fig)
    print(f"wrote paper/figures/{name}.pdf/.png")


def grouped_bars(ax, cats: list[str], values: dict, lo: dict | None = None, hi: dict | None = None) -> None:
    """Bars by group within each category, a 2px-equivalent gap between bars, value printed on each."""
    width, gap = 0.26, 0.02
    x = np.arange(len(cats))
    for i, g in enumerate(GROUPS):
        xs = x + (i - 1) * (width + gap)
        v = np.array([values[g].get(c, np.nan) for c in cats], float)
        ax.bar(xs, v, width, color=COLOR[g], label=NAMES[g], zorder=2)
        if lo is not None:
            l = np.array([lo[g].get(c, np.nan) for c in cats], float)
            h = np.array([hi[g].get(c, np.nan) for c in cats], float)
            ax.errorbar(xs, v, yerr=[v - l, h - v], fmt="none", ecolor=INK2, elinewidth=1, capsize=2.5, zorder=3)
            tops = h
        else:
            tops = v
        for xi, vi, ti in zip(xs, v, tops):
            if not np.isnan(vi):
                ax.text(xi, ti + 0.015, f"{vi:.0%}", ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.set_xticks(x, cats)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))


def fig_checkability() -> None:
    p = RELEASE / "retrieval_funnel.csv"
    if not p.exists():
        return
    f = pd.read_csv(p).set_index("group")
    cats = {"share_notes_any_text": "≥1 source\nretrievable as text",
            "share_notes_all_retrieved": "all sources\nretrievable",
            "share_notes_all_pinned": "all sources retrievable\nand time-pinned"}
    values = {g: {lab: f.loc[g, col] for col, lab in cats.items()} for g in GROUPS}
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    grouped_bars(ax, list(cats.values()), values)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("share of sampled notes")
    ax.legend(loc="upper right", ncol=3, fontsize=8, bbox_to_anchor=(1, 1.13))
    save(fig, "fig_checkability")


def fig_unsupported() -> None:
    p = RELEASE / "results.json"
    if not p.exists():
        return
    cells = json.loads(p.read_text(encoding="utf-8"))["primary"]["cells"]
    order = {"CRH": "Rated Helpful", "CRNH": "Rated Not Helpful", "NMR": "Needs More Ratings"}
    est, lo, hi = ({g: {} for g in GROUPS} for _ in range(3))
    for key, c in cells.items():
        g, st = key.split("|")
        u = c["unsupported"]
        if u["est"] is not None:
            est[g][order[st]], lo[g][order[st]], hi[g][order[st]] = u["est"], u["lo"], u["hi"]
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    grouped_bars(ax, list(order.values()), est, lo, hi)
    ax.set_ylim(0, min(1.0, max(max(h.values(), default=0) for h in hi.values()) + 0.12))
    ax.set_ylabel("notes with ≥1 claim their own\nsources do not support")
    ax.legend(loc="upper right", ncol=3, fontsize=8, bbox_to_anchor=(1, 1.13))
    save(fig, "fig_unsupported")


def fig_roc() -> None:
    p = RELEASE / "note_outcomes.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
    col = "share_notHelpfulIrrelevantSources"
    d = d[(d.n_ratings >= 5) & d.unsupported.notna() & d[col].notna()]
    if d.unsupported.nunique() < 2:
        return
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    ax.plot([0, 1], [0, 1], color=GRID, lw=1.5, zorder=1)
    for g in GROUPS:
        dg = d[d.group == g]
        if dg.unsupported.nunique() < 2:
            continue
        fpr, tpr, _ = roc_curve(dg.unsupported.astype(int), dg[col])
        auc = roc_auc_score(dg.unsupported.astype(int), dg[col])
        ax.plot(fpr, tpr, color=COLOR[g], lw=2, label=f"{NAMES[g]} (AUROC {auc:.2f})", zorder=2)
    ax.set_xlabel("false positive rate")
    ax.set_ylabel("true positive rate")
    ax.grid(axis="both")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left", fontsize=7.5)
    save(fig, "fig_roc")


def fig_claim_types() -> None:
    runs = INTERIM / "judge_runs"
    cp, vp = runs / "claims_main.jsonl", runs / "verdicts_main_claude-haiku-5-5.jsonl"
    if not (cp.exists() and vp.exists()):
        return
    claims = {(r := json.loads(l))["noteId"]: {c["id"]: c["type"] for c in r["claims"]}
              for l in cp.read_text(encoding="utf-8").split("\n") if l.strip()}
    group = pd.read_csv(RELEASE / "sample_ids.csv", dtype={"noteId": str}).set_index("noteId").group
    rows = []
    for l in vp.read_text(encoding="utf-8").split("\n"):
        r = json.loads(l)
        for v in r["verdicts"]:
            if v["label"] in ("NOT_IN_SOURCE", "CONTRADICTED"):
                rows.append({"group": group[r["noteId"]], "type": claims[r["noteId"]].get(v["claim_id"], "?")})
    if not rows:
        return
    t = pd.DataFrame(rows).groupby(["type", "group"]).size().unstack(fill_value=0)
    share = t / t.sum()
    cats = share.sum(axis=1).sort_values(ascending=False).index.tolist()
    values = {g: share[g].to_dict() if g in share else {} for g in GROUPS}
    fig, ax = plt.subplots(figsize=(6.2, 2.9))
    nice = {"number_date": "number\nor date", "attribution_quote": "attribution\nor quote",
            "characterisation": "characterisation", "event": "event", "causal": "causal"}
    grouped_bars(ax, [nice.get(c, c) for c in cats],
                 {g: {nice.get(c, c): v for c, v in values[g].items()} for g in GROUPS})
    ax.set_ylabel("share of a group's\nunsupported claims")
    ax.legend(loc="upper right", ncol=3, fontsize=8, bbox_to_anchor=(1, 1.13))
    save(fig, "fig_claim_types")


if __name__ == "__main__":
    fig_checkability()
    fig_unsupported()
    fig_roc()
    fig_claim_types()
