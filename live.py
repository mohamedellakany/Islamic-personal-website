"""Live broadcast status for the YouTube channel.

youtube.com/channel/<id>/live points at the current (or next scheduled) broadcast:
  live      → canonical link is a watch?v= URL and the page says "isLive":true
  upcoming  → canonical link is a watch?v= URL and the page says "isUpcoming":true
  offline   → canonical link is the channel itself
Status is cached for CACHE_SECONDS and refreshed in a background thread, so
page loads never wait on YouTube.
"""
import os
import re
import threading
import time
import urllib.request

CACHE_SECONDS = int(os.environ.get("LIVE_CHECK_SECONDS", 20 if os.environ.get("OWN_LIVE_HLS") else 45))
HTTP_TIMEOUT = 10
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/130 Safari/537.36",
           "Accept-Language": "ar,en;q=0.8", "Cookie": "SOCS=CAI"}

_state = {"state": "unknown", "source": "youtube", "video_id": None, "title": None, "starts_at": None,
          "hls": None, "checked_at": 0, "error": None, "refreshing": False}


def own_stream_live(hls_url: str) -> bool:
    """Your own stream (e.g. Cloudflare Stream): live when its HLS playlist answers."""
    try:
        # some streaming servers redirect once with a cookie check, so keep cookies across redirects
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        with opener.open(urllib.request.Request(hls_url, headers={"User-Agent": "academy-site"}), timeout=6) as r:
            return r.status == 200 and b"#EXTM3U" in r.read(4096)
    except Exception:
        return False


_lock = threading.Lock()


def parse(html: str) -> dict:
    canon = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})"', html)
    if not canon:
        return {"state": "offline", "video_id": None, "title": None, "starts_at": None}
    title = re.search(r'<meta name="title" content="([^"]*)"', html)
    start = re.search(r'"scheduledStartTime":"(\d+)"', html)
    if '"isLive":true' in html and '"isUpcoming":true' not in html:
        state = "live"
    elif '"isUpcoming":true' in html:
        state = "upcoming"
    else:  # a just-finished broadcast can still be linked here for a while
        state = "offline"
    return {"state": state, "video_id": canon.group(1) if state != "offline" else None,
            "title": title.group(1) if title and state != "offline" else None,
            "starts_at": int(start.group(1)) if start and state == "upcoming" else None}


def _refresh(channel_id: str) -> None:
    try:
        own = os.environ.get("OWN_LIVE_HLS")
        if own and own_stream_live(own):  # your own broadcast wins over YouTube
            with _lock:
                _state.update(state="live", source="own", hls=own, video_id=None, title=None,
                              starts_at=None, checked_at=time.time(), error=None)
            return
        req = urllib.request.Request(f"https://www.youtube.com/channel/{channel_id}/live", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            html = r.read().decode("utf-8", "replace")
        result = parse(html)
        with _lock:
            _state.update(result, source="youtube", hls=None, checked_at=time.time(), error=None)
    except Exception as ex:
        with _lock:  # keep the last known state, retry on the next cycle
            _state.update(checked_at=time.time(), error=f"{type(ex).__name__}: {ex}")
    finally:
        _state["refreshing"] = False


def status(channel_id: str | None, wait: float = 0) -> dict:
    """Current live status. Triggers a background refresh when stale; `wait` lets the
    very first call block briefly so a cold start already knows if the channel is live."""
    if channel_id and time.time() - _state["checked_at"] > CACHE_SECONDS and not _state["refreshing"]:
        _state["refreshing"] = True
        t = threading.Thread(target=_refresh, args=(channel_id,), daemon=True)
        t.start()
        if wait and _state["checked_at"] == 0:
            t.join(wait)
    with _lock:
        return {k: _state[k] for k in ("state", "source", "video_id", "title", "starts_at", "hls", "checked_at", "error")}
