"""Feasibility scan of the public Community Notes dump (stdlib only).

Answers, for a recent window:
  * how many notes AI writers (enrollmentState == apiEarnedIn) vs humans wrote,
  * how those notes are distributed over currentStatus (CRH / CRNH / NMR),
  * what fraction cite at least one source outside X (i.e. machine-fetchable),
  * which domains dominate the citations.

Usage:
    python -I scripts/00_feasibility.py data/raw/2026-11-12 --days 90
"""
import argparse
import collections
import csv
import io
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

csv.field_size_limit(sys.maxsize if sys.maxsize < 2**31 else 2**31 - 1)

URL_RE = re.compile(r"https?://[^\s\"'<>]+")
SHORT = {"CURRENTLY_RATED_HELPFUL": "CRH", "CURRENTLY_RATED_NOT_HELPFUL": "CRNH", "NEEDS_MORE_RATINGS": "NMR", "MISSING": "none"}
X_HOSTS = {"x.com", "twitter.com", "t.co", "mobile.twitter.com", "mobile.x.com", "fxtwitter.com", "vxtwitter.com"}


def tsv_rows(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".tsv"):
                continue
            with z.open(name) as fh:
                reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
                header = next(reader)
                for row in reader:
                    if len(row) == len(header):
                        yield dict(zip(header, row))


def host_of(url: str) -> str:
    try:
        h = urlparse(url.rstrip(".,);]")).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dump_dir", type=Path)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    ai_ids = {r["participantId"] for r in tsv_rows(args.dump_dir / "userEnrollment-00000.zip") if r["enrollmentState"].startswith("api")}
    print(f"AI writer accounts (apiEarnedIn): {len(ai_ids)}")

    # The dump directory is named after its publication date, so the window is
    # anchored there and filtered while streaming (no need to hold ~3M notes).
    dump_date = datetime.strptime(args.dump_dir.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    cutoff = int(dump_date.timestamp() * 1000) - args.days * 86_400_000
    recent = {}
    total = newest = 0
    for zp in sorted(args.dump_dir.glob("notes-*.zip")):
        for r in tsv_rows(zp):
            total += 1
            ts = int(r["createdAtMillis"])
            newest = max(newest, ts)
            if ts >= cutoff:
                recent[r["noteId"]] = (r["noteAuthorParticipantId"], ts, r.get("isCollaborativeNote", "0"), r["summary"], r["classification"])
    print(f"total notes in dump: {total:,}; newest note: {datetime.fromtimestamp(newest / 1000, timezone.utc):%Y-%m-%d %H:%M} UTC")
    print(f"notes in last {args.days} days: {len(recent):,}")

    status = {}
    for zp in sorted(args.dump_dir.glob("noteStatusHistory-*.zip")):
        for r in tsv_rows(zp):
            if r["noteId"] in recent:
                status[r["noteId"]] = r["currentStatus"]

    ai_volume = collections.Counter(v[0] for v in recent.values() if v[0] in ai_ids)
    top6 = {pid for pid, _ in ai_volume.most_common(6)}

    def group(pid: str, collab: str) -> str:
        if collab == "1":
            return "collaborative"
        if pid in top6:
            return "AI-top6"
        if pid in ai_ids:
            return "AI-other"
        return "human"

    table = collections.Counter()
    checkable = collections.Counter()
    domains = collections.defaultdict(collections.Counter)
    for nid, (pid, ts, collab, summary, cls) in recent.items():
        g = group(pid, collab)
        st = status.get(nid, "MISSING")
        table[(g, st)] += 1
        hosts = [host_of(u) for u in URL_RE.findall(summary)]
        if any(h and h not in X_HOSTS for h in hosts):
            checkable[(g, st)] += 1
        for h in set(hosts):
            domains[g][h] += 1

    print("\nAI writer volume (top 10 accounts, recent window):")
    for pid, n in ai_volume.most_common(10):
        print(f"  {pid[:12]}...  {n:,}")

    groups = ["AI-top6", "AI-other", "human", "collaborative"]
    statuses = ["CURRENTLY_RATED_HELPFUL", "CURRENTLY_RATED_NOT_HELPFUL", "NEEDS_MORE_RATINGS", "MISSING"]
    print("\nnotes by group x currentStatus   [share citing >=1 non-X source]")
    for g in groups:
        cells = []
        for s in statuses:
            n = table[(g, s)]
            c = checkable[(g, s)]
            cells.append(f"{SHORT[s]}={n:>8,} [{(c / n if n else 0):5.1%}]")
        print(f"  {g:<14} " + "  ".join(cells))

    for g in groups:
        print(f"\ntop cited domains, {g}:")
        tot = sum(1 for v in recent.values() if group(v[0], v[2]) == g) or 1
        for h, n in domains[g].most_common(12):
            print(f"  {h:<32} {n:>8,}  ({n / tot:5.1%} of notes)")


if __name__ == "__main__":
    main()
