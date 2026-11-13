"""Stream the public ratings shards and keep only ratings of notes in the frame.

The shards (noteRatings/ratings-0000N.zip, ~1.4 GB each) are sorted by noteId, so only the
shards whose noteId range overlaps the study window are read. Each shard is inflated on the
fly from HTTP, so nothing large touches the disk.

Outputs
  data/interim/ratings_by_note.csv     per (noteId, ratingSourceBucketed): counts of ratings,
                                       helpfulness levels and every rating tag (no rater IDs)
  data/interim/ratings_sample_rows.csv per-rating rows for sampled notes only (no rater IDs)

Run (background, ~10 min at 4 MB/s):  uv run python scripts/03_stream_ratings.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import struct
import sys
import time
import zlib

import httpx
import pandas as pd

from common import DUMP_DATE, INTERIM

BASE = f"https://ton.twimg.com/birdwatch-public-data/{DUMP_DATE.replace('-', '/')}/noteRatings/ratings-{{:05d}}.zip"
TAGS = ["helpfulGoodSources", "helpfulClear", "helpfulAddressesClaim", "helpfulImportantContext",
        "helpfulUnbiasedLanguage", "helpfulOther", "notHelpfulIncorrect", "notHelpfulSourcesMissingOrUnreliable",
        "notHelpfulIrrelevantSources", "notHelpfulMissingKeyPoints", "notHelpfulHardToUnderstand",
        "notHelpfulArgumentativeOrBiased", "notHelpfulSpamHarassmentOrAbuse", "notHelpfulOpinionSpeculation",
        "notHelpfulNoteNotNeeded", "notHelpfulOther"]
LEVELS = {b"HELPFUL": 1, b"SOMEWHAT_HELPFUL": 2, b"NOT_HELPFUL": 3}
UA = {"User-Agent": "cn-evidence-audit/0.1 (research; Apart AI x Epistemics sprint)"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def first_note_id(client: httpx.Client, shard: int) -> int | None:
    """noteId of the first rating in a shard, from a ranged read of its first 128 KB."""
    for attempt in range(4):
        try:
            r = client.get(BASE.format(shard), headers={**UA, "Range": "bytes=0-131071"}, timeout=180)
            if r.status_code == 404:
                return None
            b = r.content
            nlen, xlen = struct.unpack("<HH", b[26:30])
            lines = zlib.decompressobj(-15).decompress(b[30 + nlen + xlen:]).split(b"\n")
            return int(lines[1].split(b"\t", 1)[0])
        except (httpx.HTTPError, struct.error, ValueError, IndexError) as e:
            log(f"probe shard {shard} failed ({e!r}); retry {attempt + 1}")
    raise RuntimeError(f"cannot probe shard {shard}")


def stream_lines(client: httpx.Client, url: str):
    """Yield TSV lines (bytes) of the single member of a remote zip, inflating as it downloads."""
    with client.stream("GET", url, headers=UA, timeout=httpx.Timeout(60, read=600)) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        head, data_started, inflater, rem = b"", False, zlib.decompressobj(-15), b""
        got, next_report = 0, 100 * 2**20
        for chunk in r.iter_bytes(2**20):
            got += len(chunk)
            if got >= next_report:
                log(f"  downloaded {got / 2**20:,.0f} / {total / 2**20:,.0f} MB")
                next_report += 100 * 2**20
            if not data_started:
                head += chunk
                if len(head) < 30:
                    continue
                sig, = struct.unpack("<I", head[:4])
                method, = struct.unpack("<H", head[8:10])
                nlen, xlen = struct.unpack("<HH", head[26:30])
                if sig != 0x04034B50 or method != 8:
                    raise RuntimeError(f"unexpected zip header sig={sig:#x} method={method}")
                if len(head) < 30 + nlen + xlen:
                    continue
                chunk, data_started = head[30 + nlen + xlen:], True
            out = inflater.decompress(chunk)
            if out:
                parts = (rem + out).split(b"\n")
                rem = parts.pop()
                yield from parts
            if inflater.eof:
                break
        if rem:
            yield rem


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", type=int, nargs="*", help="shard numbers to read (default: auto from noteId ranges)")
    args = ap.parse_args()

    frame = pd.read_parquet(INTERIM / "frame.parquet", columns=["noteId"])
    ids = {n.encode() for n in frame.noteId}
    lo = min(int(n) for n in frame.noteId)
    sample = set()
    for name in ("sample_main.parquet", "sample_pilot.parquet"):
        p = INTERIM / name
        if p.exists():
            sample |= {n.encode() for n in pd.read_parquet(p, columns=["noteId"]).noteId}
    log(f"frame notes: {len(ids):,}; sampled notes: {len(sample):,}")

    client = httpx.Client(follow_redirects=True, http2=False)
    if args.shards:
        shards = args.shards
    else:
        # Shards are sorted by noteId: walk back from the last shard until one starts before the window.
        last = 0
        while first_note_id(client, last + 1) is not None:
            last += 1
        shards, s = [], last
        while s >= 0:
            shards.insert(0, s)
            fid = first_note_id(client, s)
            log(f"shard {s} starts at noteId {fid}")
            if fid <= lo:
                break
            s -= 1
    log(f"reading shards {shards}")

    agg: dict = collections.defaultdict(lambda: [0] * (4 + len(TAGS)))
    raw_rows = []
    for shard in shards:
        for attempt in range(3):
            try:
                seen = matched = 0
                shard_agg: dict = collections.defaultdict(lambda: [0] * (4 + len(TAGS)))
                shard_raw = []
                lines = stream_lines(client, BASE.format(shard))
                header = next(lines).split(b"\t")
                col = {name.decode(): i for i, name in enumerate(header)}
                i_bucket, i_level, i_ts = col["ratingSourceBucketed"], col["helpfulnessLevel"], col["createdAtMillis"]
                tag_idx = [col[t] for t in TAGS]
                for line in lines:
                    seen += 1
                    nid = line[: line.find(b"\t")]
                    if nid not in ids:
                        continue
                    matched += 1
                    f = line.split(b"\t")
                    a = shard_agg[(nid, f[i_bucket])]
                    a[0] += 1
                    lv = LEVELS.get(f[i_level])
                    if lv:
                        a[lv] += 1
                    for j, ti in enumerate(tag_idx):
                        if f[ti] == b"1":
                            a[4 + j] += 1
                    if nid in sample:
                        shard_raw.append([nid.decode(), f[i_ts].decode(), f[i_bucket].decode(), f[i_level].decode()]
                                         + [f[ti].decode() for ti in tag_idx])
                log(f"shard {shard}: {seen:,} ratings read, {matched:,} for frame notes")
                for k, v in shard_agg.items():
                    tot = agg[k]
                    for j, x in enumerate(v):
                        tot[j] += x
                raw_rows += shard_raw
                break
            except (httpx.HTTPError, RuntimeError, zlib.error) as e:
                log(f"shard {shard} attempt {attempt + 1} failed: {e!r}")
                if attempt == 2:
                    sys.exit(f"giving up on shard {shard}")
                time.sleep(15)

    with open(INTERIM / "ratings_by_note.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["noteId", "bucket", "n", "n_helpful", "n_somewhat", "n_not_helpful", *TAGS])
        for (nid, bucket), v in agg.items():
            w.writerow([nid.decode(), bucket.decode(), *v])
    with open(INTERIM / "ratings_sample_rows.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["noteId", "createdAtMillis", "bucket", "helpfulnessLevel", *TAGS])
        w.writerows(raw_rows)
    rated = {k[0] for k in agg}
    log(f"done: {len(rated):,} frame notes have >=1 rating; {len(raw_rows):,} rating rows kept for sampled notes")


if __name__ == "__main__":
    main()
