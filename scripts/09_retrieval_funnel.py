"""Checkability funnel for the main sample (no LLM): what share of cited evidence can be retrieved,
and pinned to the time the note was written.

Output: data/release/retrieval_funnel.csv (URL level and note level, by group)
Run:    uv run python scripts/09_retrieval_funnel.py
"""
from __future__ import annotations

import pandas as pd

from common import INTERIM, RELEASE


def main() -> None:
    idx = pd.read_csv(INTERIM / "sources_index.csv", dtype={"noteId": str})
    ids = pd.read_csv(RELEASE / "sample_ids.csv", dtype={"noteId": str})[["noteId", "group"]]
    idx = idx[idx.split == "main"].merge(ids, on="noteId")
    idx["ok"] = idx.n_chars >= 200
    idx["pinned_ok"] = idx.ok & idx.pinned.fillna(False).astype(bool)
    rows = []
    for g, d in [("all", idx), *idx.groupby("group")]:
        f = d[d.cls.isin(["web", "wiki"])]
        per_note = d.groupby("noteId").agg(n=("url", "size"), ok=("ok", "sum"), pin=("pinned_ok", "sum"))
        rows.append({
            "group": g, "notes": per_note.shape[0], "cited_urls": len(d),
            "x_urls": int(d.cls.isin(["x_post", "x_other"]).sum()), "nontext_urls": int((d.cls == "nontext").sum()),
            "fetchable_urls": len(f), "retrieved_text": int(f.ok.sum()), "retrieved_pinned": int(f.pinned_ok.sum()),
            "share_urls_retrieved": round(d.ok.mean(), 4), "share_urls_pinned": round(d.pinned_ok.mean(), 4),
            "share_notes_any_text": round((per_note.ok > 0).mean(), 4),
            "share_notes_all_retrieved": round((per_note.ok == per_note.n).mean(), 4),
            "share_notes_all_pinned": round(((per_note.ok > 0) & (per_note.pin == per_note.n)).mean(), 4),
            **{f"method_{m}": int((f.method == m).sum()) for m in
               ("wayback_before", "wayback_after", "wiki_rev", "cited_archive", "live")},
        })
    out = pd.DataFrame(rows)
    out.to_csv(RELEASE / "retrieval_funnel.csv", index=False)
    print(out.T.to_string(header=False))


if __name__ == "__main__":
    main()
