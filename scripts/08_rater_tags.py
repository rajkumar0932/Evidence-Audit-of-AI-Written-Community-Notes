"""Population-level rater behaviour (no LLM): how raters tag each group's notes, for every note in the
main window, not only the sample.

Output: data/release/rater_tags_population.csv, one row per group x status, with
  notes, median ratings per note,
  share of all ratings choosing each source-related tag, and
  share of non-helpful ratings (NOT_HELPFUL + SOMEWHAT_HELPFUL) that name a source problem.

Run:  uv run python scripts/08_rater_tags.py
"""
from __future__ import annotations

import pandas as pd

from common import GROUPS, INTERIM, RELEASE, STATUS_SHORT

TAGS = ["helpfulGoodSources", "notHelpfulIrrelevantSources", "notHelpfulSourcesMissingOrUnreliable",
        "notHelpfulIncorrect"]


def main() -> None:
    f = pd.read_parquet(INTERIM / "frame.parquet", columns=["noteId", "group", "status", "window"])
    f = f[(f.window == "main") & f.group.isin(GROUPS) & (f.status != "MISSING")]
    r = pd.read_csv(INTERIM / "ratings_by_note.csv", dtype={"noteId": str})
    r = r.groupby("noteId")[["n", "n_helpful", "n_somewhat", "n_not_helpful", *TAGS]].sum()
    d = f.merge(r, left_on="noteId", right_index=True, how="inner")
    d["status"] = d.status.map(STATUS_SHORT)
    g = d.groupby(["group", "status"])
    out = pd.DataFrame({"notes": g.size(), "median_ratings": g.n.median()})
    tot = g[["n", "n_not_helpful", "n_somewhat", *TAGS]].sum()
    for t in TAGS:
        out[f"share_ratings_{t}"] = tot[t] / tot.n
    # Source-problem tags can only be chosen on NOT_HELPFUL or SOMEWHAT_HELPFUL ratings.
    critical = tot.n_not_helpful + tot.n_somewhat
    out["share_critical_ratings"] = critical / tot.n
    out["source_problem_per_critical_rating"] = (tot.notHelpfulIrrelevantSources +
                                                 tot.notHelpfulSourcesMissingOrUnreliable) / critical
    out = out.reset_index()
    out.to_csv(RELEASE / "rater_tags_population.csv", index=False)
    show = out.copy()
    for c in show.columns[4:]:
        show[c] = show[c].map(lambda x: f"{x:.1%}")
    show.columns = [c.replace("share_ratings_", "") for c in show.columns]
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
