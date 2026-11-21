"""Public pages of the website (Jinja templates in templates/)."""
import io
import mimetypes
import os
import re

import qrcode
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils._os import safe_join
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme

import feed
import live
from academy.jinja2 import thumb
from .data import data, norm, search_index
from .i18n import CATEGORIES, T
from .models import Lesson


def lang_of(request) -> str:
    lang = request.COOKIES.get("lang", "ar")
    return lang if lang in T else "ar"


def render(request, template: str, status: int = 200, **ctx) -> HttpResponse:
    """Render a Jinja template with the values every page needs (language, live status, …)."""
    d, lang = data(), lang_of(request)
    total = len({v["id"] for p in d["playlists"] for v in p["videos"]} | {v["id"] for v in d["latest"]})
    match = request.resolver_match
    base = {"t": T[lang], "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "CATS": CATEGORIES,
            "live": live_status(), "live_url": live_url(request), "endpoint": match.url_name if match else None,
            "ch": d.get("channel", {}), "total_videos": total, "has_data": bool(d["playlists"])}
    html = render_to_string(template, {**base, **ctx}, request=request)
    return HttpResponse(html, status=status)


def without_shorts(videos: list) -> list:
    return [v for v in videos if v.get("duration") is None or v["duration"] > 60]


# ---------------------------------------------------------------- pages
def index(request):
    d = data()
    latest = without_shorts(d["latest"])[:8] or [v for p in d["playlists"][:4] for v in p["videos"][-2:]]
    cats = {}
    for p in d["playlists"]:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    return render(request, "index.html", courses=sorted(d["playlists"], key=lambda p: -p["count"]), latest=latest,
                  shorts=d["shorts"][:12], hero=latest[0] if latest else None,
                  cat_counts=cats, n_playlists=len(d["playlists"]))


def courses(request):
    cat = request.GET.get("cat")
    pls = sorted(data()["playlists"], key=lambda p: -p["count"])
    return render(request, "courses.html", courses=pls, cat=cat if cat in CATEGORIES else None)


def course(request, pid):
    p = data()["by_pl"].get(pid)
    if not p:
        raise Http404
    return render(request, "course.html", p=p)


def find_video(request, vid: str):
    """Return (video, course) for an id: the course from ?list= first, then any course, then Latest/Shorts."""
    d = data()
    pid = request.GET.get("list")
    if pid and pid in d["by_pl"]:
        for v in d["by_pl"][pid]["videos"]:
            if v["id"] == vid:
                return v, d["by_pl"][pid]
    for p in d["playlists"]:
        for v in p["videos"]:
            if v["id"] == vid:
                return v, p
    for v in d["latest"] + d["shorts"]:
        if v["id"] == vid:
            return v, None
    return None, None


def watch(request, vid):
    if not re.fullmatch(r"[\w-]{11}", vid):
        raise Http404
    v, p = find_video(request, vid)
    if not v:   # deleted or hidden (new YouTube uploads are saved to the database by the hourly check)
        raise Http404
    prev_v = next_v = None
    if p:
        ids = [x["id"] for x in p["videos"]]
        i = ids.index(vid)
        prev_v = p["videos"][i - 1] if i > 0 else None
        next_v = p["videos"][i + 1] if i + 1 < len(ids) else None
    return render(request, "watch.html", v=v, p=p, prev_v=prev_v, next_v=next_v)


def api_lesson(request, vid):
    """Used by the home page "continue where you left off" card: is the lesson still there?"""
    v, p = find_video(request, vid)
    if not v:
        return JsonResponse({"ok": False}, status=404)
    pid = request.GET.get("list") if p and request.GET.get("list") == p["id"] else (p["id"] if p else None)
    return JsonResponse({"ok": True, "title": v["title"], "thumb": thumb(v, "hq"),
                         "url": f"/watch/{v['id']}" + (f"?list={pid}" if pid else "")},
                        json_dumps_params={"ensure_ascii": False})


def latest(request):
    return render(request, "latest.html", videos=without_shorts(data()["latest"])[:120])


def shorts(request):
    return render(request, "shorts.html", shorts=data()["shorts"][:120])


def search(request):
    q = request.GET.get("q", "").strip()[:200]
    results, found_courses = [], []
    if q:
        terms = norm(q).split()
        found_courses = [p for p in sorted(data()["playlists"], key=lambda p: -p["count"])
                         if all(t in norm(p["title"]) for t in terms)][:12]
        results = [(v, p) for text, v, p in search_index() if all(t in text for t in terms)][:120]
    return render(request, "search.html", q=q, results=results, found_courses=found_courses)


def about(request):
    return render(request, "about.html")


def not_found(request, exception=None):
    return render(request, "base.html", status=404, not_found=True)


def set_lang(request, code):
    back = request.META.get("HTTP_REFERER")
    if not back or not url_has_allowed_host_and_scheme(back, {request.get_host()}, request.is_secure()):
        back = "/"
    resp = redirect(back)
    resp.set_cookie("lang", code if code in T else "ar", max_age=60 * 60 * 24 * 365)
    return resp


# ---------------------------------------------------------------- live broadcast
def channel_id():
    # LIVE_CHANNEL_ID lets you test with another channel that is currently live
    return os.environ.get("LIVE_CHANNEL_ID") or data().get("channel", {}).get("id")


def live_status(wait: float = 0) -> dict:
    return live.status(channel_id(), wait=wait)


def live_url(request) -> str:
    """Public address of the live page (SITE_URL overrides, e.g. for a custom domain)."""
    base = os.environ.get("SITE_URL") or request.build_absolute_uri("/")
    return base.rstrip("/") + "/live"


def live_page(request):
    s = live_status(wait=4)
    return render(request, "live.html", s=s, latest=without_shorts(data()["latest"])[:4], cid=channel_id(),
                  host=request.get_host().split(":")[0])


def api_live(request):
    resp = JsonResponse(live_status())
    resp["Cache-Control"] = "no-store"
    return resp


def live_qr(request):
    try:
        size = int(request.GET.get("size", 12))
    except ValueError:
        size = 12
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=max(4, min(size, 40)), border=2)
    qr.add_data(live_url(request))
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="#0f4c3a", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    resp = FileResponse(buf, content_type="image/png", as_attachment="download" in request.GET,
                        filename="live-lecture-qr.png")
    resp["Cache-Control"] = "max-age=86400"
    return resp


def live_poster(request):
    return render(request, "poster.html")


def healthz(request):
    """Quick check that the site, database, YouTube feed and live status are working."""
    d = data()
    cf = live.cloudflare()
    return JsonResponse({
        "ok": True, "courses": len(d["playlists"]), "latest": len(d["latest"]), "shorts": len(d["shorts"]),
        "lessons_in_db": Lesson.objects.count(),
        "own_video_files": Lesson.objects.exclude(video_file="", video_url="").count(),
        "feed": feed.status(), "live": live_status(),
        "cloudflare": {"configured": bool(cf), "lifecycle": cf and cf["lifecycle"],
                       "token_set": bool(os.environ.get("CF_API_TOKEN"))},
    }, json_dumps_params={"ensure_ascii": False})


# ---------------------------------------------------------------- uploaded files
def _chunks(f, length: int, size: int = 1024 * 1024):
    with f:
        while length > 0:
            data = f.read(min(size, length))
            if not data:
                break
            length -= len(data)
            yield data


def media(request, path):
    """Serve uploaded videos/pictures with HTTP Range support, so videos can be
    skipped forward/back (Safari and iPhones won't play video without it)."""
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except SuspiciousFileOperation:
        raise Http404
    if not os.path.isfile(full):
        raise Http404
    size = os.path.getsize(full)
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", request.headers.get("Range", "").strip())
    if m and (m[1] or m[2]):
        start, end = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (max(0, size - int(m[2])), size - 1)
        end = min(end, size - 1)
        if start > end:
            resp = HttpResponse(status=416)
            resp["Content-Range"] = f"bytes */{size}"
            return resp
        f = open(full, "rb")
        f.seek(start)
        resp = StreamingHttpResponse(_chunks(f, end - start + 1), status=206, content_type=ctype)
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(end - start + 1)
    else:
        resp = FileResponse(open(full, "rb"), content_type=ctype)
    resp["Accept-Ranges"] = "bytes"
    resp["Cache-Control"] = "public, max-age=3600"
    return resp
