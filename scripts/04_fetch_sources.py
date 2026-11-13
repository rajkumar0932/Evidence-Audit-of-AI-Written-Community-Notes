"""Retrieve every source cited by sampled notes, pinned to the time the note was written.

  wiki  -> the Wikipedia revision that was live at note creation (MediaWiki API, oldid)
  web   -> Wayback snapshot closest BEFORE note creation; else first one within 7 days AFTER;
           else a live fetch (flagged unpinned)
  x_post / x_other / nontext -> not retrieved (counted in the checkability funnel)

Resumable: each result is cached as data/interim/sources/<key>.json; finished keys are skipped.
Writes data/interim/sources_index.csv (one row per note x URL).

Run:  uv run python scripts/04_fetch_sources.py            (all sampled notes, ~1-3 h)
      uv run python scripts/04_fetch_sources.py --limit 12 (smoke test)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

import httpx
import pandas as pd
import trafilatura
from lxml import html as lxml_html

from common import INTERIM, host_of, url_class

SRC_DIR = INTERIM / "sources"
SRC_DIR.mkdir(parents=True, exist_ok=True)
MAX_CHARS = 300_000
RESEARCH_UA = "cn-evidence-audit/0.1 (research; Apart AI x Epistemics sprint)"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|igshid|mc_cid|mc_eid|ref_src|ref_url|s|t|si|smid|cmpid)$", re.I)


class Limiter:
    """Global minimum interval between requests to one service; slows down on 429s."""

    def __init__(self, interval: float):
        self.interval, self.lock, self.next_t = interval, threading.Lock(), 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next_t)
            self.next_t = t + self.interval
        time.sleep(max(0.0, t - now))

    def slow_down(self) -> None:
        with self.lock:
            self.interval = min(self.interval * 1.5, 12.0)


ARCHIVE, WIKI = Limiter(1.5), Limiter(0.25)
_live: dict[str, Limiter] = {}
_live_lock = threading.Lock()


def live_limiter(host: str) -> Limiter:
    with _live_lock:
        return _live.setdefault(host, Limiter(1.0))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get(client: httpx.Client, url: str, limiter: Limiter, ua: str, tries: int = 5, **kw) -> httpx.Response | None:
    for attempt in range(tries):
        limiter.wait()
        try:
            r = client.get(url, headers={"User-Agent": ua}, **kw)
        except httpx.HTTPError:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code in (429, 503, 509):
            limiter.slow_down()
            time.sleep(min(30 * 2**attempt, 300))
            continue
        return r
    return None


# ------------------------------------------------------------------ text extraction
def clean(text: str) -> str:
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()[:MAX_CHARS]


def decompress(content: bytes, encoding: str = "") -> bytes:
    """Archived payloads are sometimes stored still compressed (zstd/gzip/brotli)."""
    encoding = (encoding or "").lower()
    try:
        if content[:4] == b"\x28\xb5\x2f\xfd" or "zstd" in encoding:
            import zstandard
            return zstandard.ZstdDecompressor().decompressobj().decompress(content)
        if content[:2] == b"\x1f\x8b" or "gzip" in encoding:
            import gzip
            return gzip.decompress(content)
        if "br" in encoding.split(","):
            import brotli
            return brotli.decompress(content)
    except Exception:  # corrupt or truncated payload: keep the raw bytes, extraction will show it
        return content
    return content


def visible_text(raw: bytes) -> str:
    try:
        doc = lxml_html.fromstring(raw)
    except (ValueError, lxml_html.etree.ParserError):
        return ""
    for bad in doc.xpath("//script|//style|//noscript|//svg"):
        bad.drop_tree()
    return clean(doc.text_content())


def body_to_text(content: bytes, ctype: str, url: str, encoding: str = "") -> dict:
    """Return main text (trafilatura) and full visible text; the judge can fall back to the latter."""
    content = decompress(content, encoding)
    ctype = (ctype or "").lower()
    if "pdf" in ctype or content[:5] == b"%PDF-":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(content))
            text = clean("\n".join((p.extract_text() or "") for p in reader.pages[:40]))
            return {"fmt": "pdf", "text": text, "text_full": text}
        except Exception as e:  # malformed PDFs raise many exception types
            return {"fmt": f"pdf_error:{type(e).__name__}", "text": "", "text_full": ""}
    if "text/plain" in ctype:
        text = clean(content.decode("utf-8", "replace"))
        return {"fmt": "text", "text": text, "text_full": text}
    main = clean(trafilatura.extract(content, url=url, include_tables=True, include_comments=False,
                                     favor_recall=True, deduplicate=False) or "")
    full = visible_text(content)
    return {"fmt": "html", "text": main if len(main) >= 300 else full, "text_full": full}


# ------------------------------------------------------------------ Wikipedia
def fetch_wiki(client: httpx.Client, url: str, note_ms: int) -> dict:
    p = urlparse(url)
    lang = p.netloc.lower().replace("www.", "").split(".")[0]
    if lang == "m":
        lang = "en"
    if p.path.startswith("/wiki/"):
        title = unquote(p.path[len("/wiki/"):])
    else:
        title = dict(parse_qsl(p.query)).get("title", "")
    title = title.replace("_", " ")
    if not title:
        return {"method": "wiki_rev", "error": "no_title"}
    api = f"https://{lang}.wikipedia.org/w/api.php"
    iso = datetime.fromtimestamp(note_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = get(client, api, WIKI, RESEARCH_UA, params={
        "action": "query", "format": "json", "formatversion": "2", "prop": "revisions", "titles": title,
        "rvlimit": "1", "rvdir": "older", "rvstart": iso, "rvprop": "ids|timestamp", "redirects": "1"})
    if r is None or r.status_code != 200:
        return {"method": "wiki_rev", "error": f"query_http_{getattr(r, 'status_code', 'none')}"}
    pages = r.json().get("query", {}).get("pages", [])
    revs = pages[0].get("revisions") if pages else None
    if not revs:
        return {"method": "wiki_rev", "error": "no_revision_before_note"}
    rev = revs[0]
    r = get(client, api, WIKI, RESEARCH_UA, params={
        "action": "parse", "format": "json", "formatversion": "2", "oldid": str(rev["revid"]), "prop": "text",
        "disableeditsection": "1", "disablelimitreport": "1"})
    if r is None or r.status_code != 200 or "parse" not in r.json():
        return {"method": "wiki_rev", "error": "parse_failed", "revid": rev["revid"]}
    doc = lxml_html.fromstring(r.json()["parse"]["text"])
    for bad in doc.xpath("//style|//script|//sup[contains(@class,'reference')]|//*[contains(@class,'mw-editsection')]"):
        bad.drop_tree()
    text = clean(doc.text_content())
    return {"method": "wiki_rev", "pinned": True, "snapshot": rev["timestamp"], "revid": rev["revid"],
            "fmt": "html", "text": text, "text_full": text}


# ------------------------------------------------------------------ web (Wayback first)
def canonical(url: str) -> str:
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


def cdx(client: httpx.Client, url: str, **params) -> list[list[str]]:
    # Bounded time ranges + short timeouts: unbounded CDX scans of heavily archived pages
    # (e.g. ballotpedia, PMC) timed out repeatedly and stalled workers for ~28 min each.
    r = get(client, "https://web.archive.org/cdx/search/cdx", ARCHIVE, RESEARCH_UA, tries=2, timeout=30,
            params={"url": url, "output": "json", "filter": "statuscode:200", "fl": "timestamp,original,mimetype",
                    **params})
    if r is None or r.status_code != 200 or not r.text.strip():
        return []
    try:
        rows = r.json()
    except json.JSONDecodeError:
        return []
    return rows[1:] if rows and rows[0] and rows[0][0] == "timestamp" else rows


WAYBACK_CITED = re.compile(r"^https?://web\.archive\.org/web/(\d{4,14})[a-z_]*/(.+)$", re.I)


SNAP_IN_URL = re.compile(r"/web/(\d{14})")


def archive_get(client: httpx.Client, snap: str, original: str) -> httpx.Response | None:
    return get(client, f"https://web.archive.org/web/{snap}id_/{original}", ARCHIVE, RESEARCH_UA, tries=3,
               timeout=httpx.Timeout(20, read=60), follow_redirects=True)


def orig_encoding(r: httpx.Response) -> str:
    return r.headers.get("x-archive-orig-content-encoding", "") or r.headers.get("content-encoding", "")


def find_snapshot(client: httpx.Client, url: str, ts: str, ts_after: str, ts_year_before: str):
    """(method, snapshot_ts) for the capture closest BEFORE ts, else the first one within 7 days after."""
    after = None
    r = get(client, "https://archive.org/wayback/available", ARCHIVE, RESEARCH_UA, tries=2, timeout=30,
            params={"url": url, "timestamp": ts})
    if r is not None and r.status_code == 200:
        try:
            closest = r.json().get("archived_snapshots", {}).get("closest") or {}
        except json.JSONDecodeError:
            closest = {}
        if closest.get("available") and str(closest.get("status")) == "200":
            snap = closest["timestamp"]
            if snap <= ts:
                return "wayback_before", snap
            if snap <= ts_after:
                after = snap
    # The closest capture is after the note (or unknown): look for any capture in the year before.
    rows = cdx(client, url, **{"from": ts_year_before, "to": ts, "limit": "-1", "fastLatest": "true"})
    if rows:
        return "wayback_before", rows[-1][0]
    if after:
        return "wayback_after", after
    rows = cdx(client, url, **{"from": ts, "to": ts_after, "limit": "1"})
    return ("wayback_after", rows[0][0]) if rows else (None, None)


def fetch_web(client: httpx.Client, url: str, note_ms: int) -> dict:
    m = WAYBACK_CITED.match(url)
    if m:  # the note itself cites an archived copy: that copy is already fixed in time
        r = archive_get(client, m.group(1), m.group(2))
        if r is not None and r.status_code == 200:
            body = body_to_text(r.content, r.headers.get("content-type", ""), m.group(2), orig_encoding(r))
            return {"method": "cited_archive", "pinned": True, "snapshot": m.group(1), **body}
    t = datetime.fromtimestamp(note_ms / 1000, timezone.utc)
    ts, ts_after = t.strftime("%Y%m%d%H%M%S"), (t + timedelta(days=7)).strftime("%Y%m%d%H%M%S")
    ts_year_before = (t - timedelta(days=365)).strftime("%Y%m%d%H%M%S")
    started = time.monotonic()
    for cand in dict.fromkeys([url, canonical(url)]):
        if time.monotonic() - started > 180:  # per-task budget: fall back to a live fetch
            break
        method, snap = find_snapshot(client, cand, ts, ts_after, ts_year_before)
        if not method:
            continue
        r = archive_get(client, snap, cand)
        if r is not None and r.status_code == 200 and r.content:
            body = body_to_text(r.content, r.headers.get("content-type", ""), cand, orig_encoding(r))
            got = SNAP_IN_URL.search(str(r.url))  # Wayback may redirect to a neighbouring capture
            snap = got.group(1) if got else snap
            if len(body["text"]) >= 200:
                return {"method": "wayback_before" if snap <= ts else "wayback_after", "pinned": True,
                        "snapshot": snap, **body}
    r = get(client, url, live_limiter(host_of(url)), BROWSER_UA, tries=2,
            timeout=httpx.Timeout(20, read=45), follow_redirects=True)
    if r is None:
        return {"method": "live", "pinned": False, "error": "unreachable"}
    if r.status_code != 200:
        return {"method": "live", "pinned": False, "error": f"http_{r.status_code}", "final_url": str(r.url)}
    body = body_to_text(r.content, r.headers.get("content-type", ""), str(r.url))
    return {"method": "live", "pinned": False, "final_url": str(r.url), **body}


# ------------------------------------------------------------------ driver
def task_key(url: str, note_ms: int) -> str:
    return hashlib.sha1(f"{url}|{note_ms}".encode()).hexdigest()[:20]


def run_one(client: httpx.Client, task: dict) -> dict:
    out_path = SRC_DIR / f"{task['key']}.json"
    if out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    t0 = time.time()
    try:
        res = fetch_wiki(client, task["url"], task["note_ms"]) if task["cls"] == "wiki" else \
            fetch_web(client, task["url"], task["note_ms"])
    except Exception as e:  # one bad page must not stop an overnight run
        res = {"method": "error", "error": f"{type(e).__name__}: {e}"[:300]}
    res = {**task, **res, "n_chars": len(res.get("text", "")), "secs": round(time.time() - t0, 1),
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if "error" not in res or res.get("text"):
        out_path.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only the first N fetchable tasks (smoke test)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    notes = pd.concat([pd.read_parquet(INTERIM / f) for f in ("sample_pilot.parquet", "sample_main.parquet")])
    tasks, seen = [], set()
    for n in notes.itertuples():
        for url in json.loads(n.urls):
            key = task_key(url, n.created_ms)
            if key in seen:
                continue
            seen.add(key)
            tasks.append({"key": key, "noteId": n.noteId, "split": n.split, "url": url, "cls": url_class(url),
                          "note_ms": int(n.created_ms)})
    fetchable = [t for t in tasks if t["cls"] in ("web", "wiki")]
    if args.limit:
        fetchable = fetchable[: args.limit]
    log(f"{len(tasks)} note-URL pairs; {len(fetchable)} to retrieve "
        f"({sum(t['cls'] == 'wiki' for t in fetchable)} wiki, {sum(t['cls'] == 'web' for t in fetchable)} web)")

    results = {t["key"]: {**t, "method": "skip", "pinned": False, "n_chars": 0}
               for t in tasks if t["cls"] not in ("web", "wiki")}
    with httpx.Client(http2=False, timeout=httpx.Timeout(30, read=60)) as client, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, client, t): t for t in fetchable}
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            results[res["key"]] = res
            if i % 25 == 0 or i == len(futures):
                done = [r for r in results.values() if r.get("method") not in ("skip",)]
                ok = sum(r.get("n_chars", 0) >= 200 for r in done)
                pinned = sum(bool(r.get("pinned")) and r.get("n_chars", 0) >= 200 for r in done)
                log(f"{i}/{len(futures)} done; text>=200 chars: {ok}; pinned: {pinned}; "
                    f"archive interval {ARCHIVE.interval:.1f}s")

    idx = pd.DataFrame([{k: v for k, v in r.items() if k not in ("text", "text_full")} for r in results.values()])
    idx.to_csv(INTERIM / "sources_index.csv", index=False)
    fetched = idx[idx.cls.isin(["web", "wiki"])]
    if len(fetched):
        log("method counts:\n" + fetched.method.value_counts().to_string())
        log(f"text >= 200 chars: {(fetched.n_chars >= 200).mean():.1%}; pinned with text: "
            f"{(fetched.pinned.fillna(False).astype(bool) & (fetched.n_chars >= 200)).mean():.1%}")


if __name__ == "__main__":
    main()
