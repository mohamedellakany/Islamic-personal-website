"""Live YouTube feed: picks up new uploads between full syncs (sync.py).

YouTube's public RSS feed lists the channel's latest ~15 uploads. Every hour we
read it, find videos the site doesn't know yet, decide whether each is a Short,
and work out which course (playlist) it belongs to. app.py merges the result
into the catalog. Only the standard library is used; failures are silent and
the site simply keeps showing the last good data.
"""
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from sync import lesson_number

REFRESH_SECONDS = 60 * 60          # how often to re-read the feed
FIRST_FETCH_TIMEOUT = 4            # first request after start waits at most this long
HTTP_TIMEOUT = 8
FEED_URL = "https://www.youtube.com/feeds/videos.xml?{kind}_id={id}"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
      "media": "http://search.yahoo.com/mrss/"}
UA = {"User-Agent": "Mozilla/5.0 (academy-site feed reader)", "Accept-Language": "ar",
      "Cookie": "SOCS=CAI"}  # skip the EU cookie-consent redirect

_state = {"fetched_at": 0, "items": [], "version": 0, "error": None, "refreshing": False}
_lock = threading.Lock()
_short_cache: dict[str, bool] = {}


# ------------------------------------------------------------------ fetching
def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return r.read()


def _parse(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        if not vid:
            continue
        stats = e.find("media:group/media:community/media:statistics", NS)
        out.append({
            "id": vid,
            "title": (e.findtext("a:title", namespaces=NS) or "").strip(),
            "published": e.findtext("a:published", namespaces=NS) or "",
            "views": int(stats.get("views")) if stats is not None and stats.get("views", "").isdigit() else None,
        })
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def is_short(vid: str) -> bool:
    """youtube.com/shorts/<id> answers 200 for Shorts and redirects for normal videos."""
    if vid not in _short_cache:
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(urllib.request.Request(f"https://www.youtube.com/shorts/{vid}", headers=UA),
                             timeout=HTTP_TIMEOUT) as r:
                _short_cache[vid] = r.status == 200
        except urllib.error.HTTPError as ex:   # 3xx lands here because we refuse to follow it
            _short_cache[vid] = False if 300 <= ex.code < 400 else None
        except Exception:
            return False                        # unknown: don't cache, try again next time
    return bool(_short_cache[vid])


# ------------------------------------------------------------------ course matching
def _words(title: str) -> set[str]:
    t = re.sub(r"[ً-ْـ]", "", title.lower())
    t = re.sub("[إأآٱ]", "ا", t).replace("ة", "ه").replace("ى", "ي")
    return {w for w in re.findall(r"[^\W\d_]{2,}", t)}


def guess_playlist(video: dict, playlists: list[dict]) -> str | None:
    """Match a numbered lesson to the series whose last lesson number is just below it
    and whose titles look alike (e.g. '٧٨- كيف نقرأ سورة …' → the Tafsir course)."""
    num = lesson_number(video["title"])
    if num is None:
        return None
    words, best, best_score = _words(video["title"]), None, 0.0
    for p in playlists:
        numbered = [v for v in p["videos"] if v.get("num") is not None]
        if not numbered:
            continue
        last = max(numbered, key=lambda v: v["num"])
        if not (0 < num - last["num"] <= 3):
            continue
        ref = _words(last["title"])
        score = len(words & ref) / max(1, len(words | ref))
        if score > best_score:
            best, best_score = p["id"], score
    return best if best_score >= 0.25 else None


# ------------------------------------------------------------------ refresh
def _refresh(base: dict) -> None:
    try:
        channel_id = base["channel"]["id"]
        known = {v["id"] for p in base["playlists"] for v in p["videos"]}
        known |= {v["id"] for v in base.get("latest", []) + base.get("shorts", [])}
        fresh = [v for v in _parse(_get(FEED_URL.format(kind="channel", id=channel_id))) if v["id"] not in known]

        if fresh:
            # Playlists the channel is actively adding to (they hold recent uploads).
            recent = {v["id"] for v in base.get("latest", [])[:40]}
            active = [p for p in base["playlists"] if any(v["id"] in recent for v in p["videos"])]
            in_playlist: dict[str, str] = {}
            for p in active[:8]:
                try:
                    for v in _parse(_get(FEED_URL.format(kind="playlist", id=p["id"]))):
                        in_playlist.setdefault(v["id"], p["id"])
                except Exception:
                    pass
            for v in fresh:
                v["short"] = is_short(v["id"])
                v["num"] = lesson_number(v["title"])
                v["playlist"] = None if v["short"] else (in_playlist.get(v["id"]) or guess_playlist(v, base["playlists"]))
                v["new"] = True

        with _lock:
            changed = [v["id"] for v in fresh] != [v["id"] for v in _state["items"]]
            _state.update(items=fresh, fetched_at=time.time(), error=None)
            if changed:
                _state["version"] += 1
    except Exception as ex:
        with _lock:
            _state.update(fetched_at=time.time(), error=f"{type(ex).__name__}: {ex}")
    finally:
        _state["refreshing"] = False


def new_videos(base: dict) -> tuple[int, list[dict]]:
    """Return (version, new items). Refreshes in the background when stale;
    the very first call waits briefly so a fresh start already shows new lessons."""
    first = _state["fetched_at"] == 0
    if time.time() - _state["fetched_at"] > REFRESH_SECONDS and not _state["refreshing"]:
        _state["refreshing"] = True
        t = threading.Thread(target=_refresh, args=(base,), daemon=True)
        t.start()
        if first:
            t.join(FIRST_FETCH_TIMEOUT)
    with _lock:
        return _state["version"], list(_state["items"])


def status() -> dict:
    with _lock:
        return {"fetched_at": int(_state["fetched_at"]), "new_videos": len(_state["items"]),
                "titles": [v["title"] for v in _state["items"]], "error": _state["error"],
                "refresh_seconds": REFRESH_SECONDS}
