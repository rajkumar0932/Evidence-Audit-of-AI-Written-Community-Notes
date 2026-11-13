"""Build the sampling frame: every note created in the main + pilot windows, with
author group, current status, and the classes of the URLs it cites.

Outputs
  data/interim/frame.parquet          one row per note (main + pilot windows)
  data/release/ai_accounts.csv        AI writer accounts with monthly volumes (for the CW mapping check)
  data/release/frame_summary.csv      group x status counts and URL-class shares (population figures)

Run:  uv run python scripts/01_build_frame.py
"""
from __future__ import annotations

import collections
import json

import pandas as pd

from common import (DUMP_DIR, INTERIM, MAIN_END, MAIN_START, PILOT_END, PILOT_START, RELEASE, STATUS_SHORT,
                    extract_urls, fmt_ms, tsv_rows, url_class)

MISLEADING = ["misleadingFactualError", "misleadingManipulatedMedia", "misleadingOutdatedInformation",
              "misleadingMissingImportantContext", "misleadingUnverifiedClaimAsFact", "misleadingSatire", "misleadingOther"]


def main() -> None:
    stats: dict = {}
    enroll = {r["participantId"]: r["enrollmentState"] for r in tsv_rows(DUMP_DIR / "userEnrollment-00000.zip", stats)}
    ai_ids = {pid for pid, st in enroll.items() if st.startswith("api")}
    print(f"AI writer accounts (apiEarnedIn): {len(ai_ids)}")

    rows = []
    for zp in sorted(DUMP_DIR.glob("notes-*.zip")):
        for r in tsv_rows(zp, stats):
            ts = int(r["createdAtMillis"])
            if not (MAIN_START <= ts < PILOT_END):
                continue
            urls = extract_urls(r["summary"])
            classes = [url_class(u) for u in urls]
            rows.append({
                "noteId": r["noteId"],
                "author": r["noteAuthorParticipantId"],
                "created_ms": ts,
                "tweetId": r["tweetId"],
                "window": "main" if ts < MAIN_END else "pilot",
                "classification": r["classification"],
                **{m: int(r.get(m) or 0) for m in MISLEADING},
                "trustworthySources": int(r.get("trustworthySources") or 0),
                "isMediaNote": int(r.get("isMediaNote") or 0),
                "isCollaborativeNote": int(r.get("isCollaborativeNote") or 0),
                "summary": r["summary"],
                "urls": json.dumps(urls),
                "n_urls": len(urls),
                **{f"n_{c}": classes.count(c) for c in ("x_post", "x_other", "wiki", "nontext", "web")},
            })
    print(f"malformed rows skipped while reading dumps: {stats.get('malformed', 0)}")
    df = pd.DataFrame(rows)
    print(f"notes in main+pilot windows: {len(df):,}  (main {int((df.window == 'main').sum()):,}, pilot {int((df.window == 'pilot').sum()):,})")

    status = {}
    for r in tsv_rows(DUMP_DIR / "noteStatusHistory-00000.zip", stats):
        status[r["noteId"]] = (r["currentStatus"], r["firstNonNMRStatus"], r["timestampMillisOfFirstNonNMRStatus"],
                               r["timestampMillisOfCurrentStatus"], r["lockedStatus"], r["currentDecidedBy"])
    keep = set(df.noteId)
    status = {k: v for k, v in status.items() if k in keep}
    cols = ["status", "first_non_nmr_status", "ts_first_non_nmr", "ts_current_status", "locked_status", "decided_by"]
    st = pd.DataFrame.from_dict(status, orient="index", columns=cols)
    df = df.merge(st, left_on="noteId", right_index=True, how="left")
    df["status"] = df["status"].fillna("MISSING").replace("", "MISSING")

    # Author groups. The Community Writer runs six accounts with quota-capped, near-identical volumes;
    # take the six highest-volume API accounts in the main window and verify the mapping by hand.
    main_ai = df[(df.window == "main") & df.author.isin(ai_ids)]
    vol = main_ai.author.value_counts()
    cw_ids = set(vol.index[:6])
    df["group"] = "human"
    df.loc[df.author.isin(ai_ids), "group"] = "ai_other"
    df.loc[df.author.isin(cw_ids), "group"] = "cw"
    df.loc[df.isCollaborativeNote == 1, "group"] = "collaborative"

    # AI account table, with per-month volumes, so the CW mapping can be checked for stability.
    month = pd.to_datetime(main_ai.created_ms, unit="ms", utc=True).dt.strftime("%Y-%m")
    by_month = main_ai.groupby([main_ai.author, month]).size().unstack(fill_value=0)
    crh = main_ai[main_ai.status == "CURRENTLY_RATED_HELPFUL"].author.value_counts()
    acc = pd.DataFrame({"n_notes_main": vol, "n_crh_main": crh}).fillna(0).astype(int)
    acc = acc.join(by_month).sort_values("n_notes_main", ascending=False).reset_index(names="participantId")
    acc.insert(1, "cw_candidate", acc.participantId.isin(cw_ids))
    acc.to_csv(RELEASE / "ai_accounts.csv", index=False)
    print("\nAI accounts by main-window volume (top 10):")
    print(acc.head(10).to_string(index=False, formatters={"participantId": lambda s: s[:12] + "..."}))

    # Example notes per CW candidate for the manual alias check (open each on X while logged in).
    examples = (df[df.group == "cw"].sort_values("created_ms", ascending=False).groupby("author").head(3)
                [["author", "noteId", "tweetId", "created_ms"]])
    examples["note_url"] = "https://x.com/i/birdwatch/n/" + examples.noteId
    examples["post_url"] = "https://x.com/i/status/" + examples.tweetId
    examples["created_utc"] = examples.created_ms.map(fmt_ms)
    examples.drop(columns="created_ms").to_csv(RELEASE / "cw_mapping_check.csv", index=False)

    # Is "no status row" deletion or publication lag? Look at it by creation week.
    week = pd.to_datetime(df.created_ms, unit="ms").dt.to_period("W").astype(str)  # naive UTC
    wk = (df.status == "MISSING").groupby(week).mean()
    print("\nshare of notes with no status row, by creation week:")
    print(wk.map(lambda x: f"{x:.1%}").to_string())

    df.to_parquet(INTERIM / "frame.parquet", index=False)

    main = df[df.window == "main"]
    summ = (main.assign(status_short=main.status.map(STATUS_SHORT),
                        any_url=main.n_urls > 0,
                        any_text_source=(main.n_web + main.n_wiki) > 0,
                        x_only=(main.n_urls > 0) & (main.n_web + main.n_wiki + main.n_nontext == 0))
            .groupby(["group", "status_short"])
            .agg(notes=("noteId", "size"), any_url=("any_url", "mean"),
                 any_text_source=("any_text_source", "mean"), x_only=("x_only", "mean")).reset_index())
    summ.to_csv(RELEASE / "frame_summary.csv", index=False)
    print("\nmain window, group x status (shares are of notes in the cell):")
    print(summ.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"\nwrote {INTERIM / 'frame.parquet'}  ({len(df):,} rows)")


if __name__ == "__main__":
    main()
