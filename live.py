"""Live broadcast status: your own Cloudflare Stream live input first, then YouTube.

Cloudflare Stream (optional, set in .env locally / App settings on Azure):
  CF_STREAM_CUSTOMER  customer-xxxx.cloudflarestream.com   (not secret)
  CF_LIVE_INPUT_ID    the live input's ID                   (not secret)
  CF_API_TOKEN        only if the status check needs a token (secret, never commit)
  → status:  https://<customer>/<input>/lifecycle            {"live": true/false}
  → video:   https://<customer>/<input>/manifest/video.m3u8  (HLS, played with hls.js)
OWN_LIVE_HLS can point at any other HLS stream instead.

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

def cloudflare() -> dict | None:
    """Cloudflare live input addresses, or None when not configured."""
    host = (os.environ.get("CF_STREAM_CUSTOMER") or "").strip().rstrip("/")
    input_id = (os.environ.get("CF_LIVE_INPUT_ID") or "").strip()
    if not (host and input_id):
        return None
    if not host.startswith("http"):
        host = "https://" + (host if "." in host else f"{host}.cloudflarestream.com")
    return {"lifecycle": f"{host}/{input_id}/lifecycle", "hls": f"{host}/{input_id}/manifest/video.m3u8"}


def own_stream_configured() -> bool:
    return bool(cloudflare() or os.environ.get("OWN_LIVE_HLS"))


CACHE_SECONDS = int(os.environ.get("LIVE_CHECK_SECONDS", 20 if own_stream_configured() else 45))
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


def cloudflare_live(cf: dict) -> bool | None:
    """Ask Cloudflare's lifecycle endpoint. True/False, or None if it couldn't answer."""
    import json
    headers = {"User-Agent": "academy-site"}
    if os.environ.get("CF_API_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['CF_API_TOKEN']}"
    try:
        with urllib.request.urlopen(urllib.request.Request(cf["lifecycle"], headers=headers), timeout=6) as r:
            return bool(json.loads(r.read()).get("live"))
    except Exception:
        return None


def own_live() -> str | None:
    """HLS address of your own stream if it is on air right now, else None."""
    cf = cloudflare()
    if cf:
        live = cloudflare_live(cf)
        if live is None:              # status endpoint unavailable: fall back to probing the video
            live = own_stream_live(cf["hls"])
        return cf["hls"] if live else None
    hls = os.environ.get("OWN_LIVE_HLS")
    return hls if hls and own_stream_live(hls) else None


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
        own = own_live()
        if own:  # your own broadcast wins over YouTube
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
