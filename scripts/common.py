"""Shared constants and helpers for the Community Notes evidence audit."""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DUMP_DATE = "2026-11-12"
DUMP_DIR = ROOT / "data" / "raw" / DUMP_DATE
INTERIM = ROOT / "data" / "interim"
RELEASE = ROOT / "data" / "release"
for _d in (INTERIM, RELEASE):
    _d.mkdir(parents=True, exist_ok=True)


def utc_ms(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


# Main window: >= 12 days before the dump so statuses have time to settle.
MAIN_START, MAIN_END = utc_ms("2026-08-14"), utc_ms("2026-11-01")
# Pilot window: prompt development only, never analysed.
PILOT_START, PILOT_END = utc_ms("2026-11-01"), utc_ms("2026-11-10")

SEED = 20261113
N_PER_CELL = 110
N_PILOT = 40
GROUPS = ("cw", "ai_other", "human")
STATUSES = ("CURRENTLY_RATED_HELPFUL", "NEEDS_MORE_RATINGS")
STATUS_SHORT = {
    "CURRENTLY_RATED_HELPFUL": "CRH",
    "CURRENTLY_RATED_NOT_HELPFUL": "CRNH",
    "NEEDS_MORE_RATINGS": "NMR",
    "MISSING": "none",
}

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def tsv_rows(zip_path: Path, stats: dict | None = None):
    """Yield dict rows from every .tsv member of a dump zip, without extracting it."""
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
                    elif stats is not None:
                        stats["malformed"] = stats.get("malformed", 0) + 1


# ---------------------------------------------------------------- URLs
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
TRAILING = ".,;:!?)]}>'\"”’"

X_HOSTS = {"x.com", "twitter.com", "t.co", "mobile.twitter.com", "mobile.x.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com"}
NONTEXT_HOSTS = {
    "youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com", "instagram.com", "facebook.com", "m.facebook.com",
    "fb.watch", "fb.com", "tiktok.com", "vm.tiktok.com", "threads.net", "threads.com", "bsky.app", "t.me", "rumble.com",
    "vimeo.com", "twitch.tv", "linkedin.com", "reddit.com", "old.reddit.com", "truthsocial.com", "pinterest.com",
    "dailymotion.com", "odysee.com", "bitchute.com", "snapchat.com", "imgur.com", "i.imgur.com", "flickr.com",
}


def extract_urls(text: str) -> list[str]:
    out = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(TRAILING)
        if u and u not in out:
            out.append(u)
    return out


def host_of(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower().split("@")[-1].split(":")[0]
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def url_class(url: str) -> str:
    """x_post | x_other | wiki | nontext | web."""
    h = host_of(url)
    if h in X_HOSTS:
        return "x_post" if "/status/" in urlparse(url).path else "x_other"
    if h.endswith("wikipedia.org"):
        return "wiki"
    if h in NONTEXT_HOSTS or any(h.endswith("." + n) for n in NONTEXT_HOSTS):
        return "nontext"
    return "web"


def fmt_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")
