"""The catalog the pages use, built from the database and kept in memory.

The structure is the same one the templates have always used (playlists → videos,
latest, shorts). It is rebuilt automatically a few seconds after anything changes
in the admin, and new YouTube uploads are saved to the database by feed.py.
"""
import json
import re
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import connection
from django.db.models import Count, Max
from django.utils import timezone

import feed
from .models import Course, CourseLesson, Lesson

CHANNEL_FILE = Path(settings.BASE_DIR) / "data" / "channel.json"
CHECK_SECONDS = 5      # how often to look for changes made in the admin
NEW_DAYS = 14          # "New" badge for lessons added in the last 14 days

_cache = {"fp": None, "checked": 0.0, "data": None}
_channel = {"mtime": None, "data": {}}


# ---------------------------------------------------------------- channel info (name, avatar, subscribers)
def channel() -> dict:
    if not CHANNEL_FILE.exists():
        return {}
    mtime = CHANNEL_FILE.stat().st_mtime
    if _channel["mtime"] != mtime:
        ch = json.loads(CHANNEL_FILE.read_text(encoding="utf-8")).get("channel", {})
        if ch.get("avatar"):  # small avatar instead of the full-size original
            ch["avatar"] = re.sub(r"=s\d+.*$", "=s176-c-k-c0x00ffffff-no-rj", ch["avatar"])
        _channel.update(mtime=mtime, data=ch)
    return _channel["data"]


# ---------------------------------------------------------------- ordering + search helpers
def ordered(videos: list) -> list:
    """Course order: by lesson number when titles are numbered, else by position."""
    numbered = [v for v in videos if v.get("num") is not None]
    if videos and len(numbered) >= 0.6 * len(videos):
        # unnumbered lessons stay next to the numbered lesson they follow
        keys, prev = [], 0
        for i, v in enumerate(videos):
            prev = v["num"] if v.get("num") is not None else prev
            keys.append((prev, v.get("num") is None, i))
        return [v for _, v in sorted(zip(keys, videos), key=lambda kv: kv[0])]
    return list(videos)


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
DIACRITICS = re.compile(r"[ً-ْٰـ]")


def norm(s: str) -> str:
    """Normalize Arabic for search: diacritics, alef/ya/ta-marbuta variants, digits."""
    s = DIACRITICS.sub("", (s or "").lower().translate(AR_DIGITS))
    s = re.sub("[إأآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"\s+", " ", s)


@lru_cache(maxsize=1)
def search_index():
    d, seen, idx = data(), set(), []
    for p in d["playlists"]:
        for v in p["videos"]:
            if v["id"] not in seen:
                seen.add(v["id"])
                idx.append((norm(v["title"] + " " + p["title"]), v, p))
    for v in d["latest"] + d["shorts"]:
        if v["id"] not in seen:
            seen.add(v["id"])
            idx.append((norm(v["title"]), v, None))
    return idx


# ---------------------------------------------------------------- building
def _fingerprint() -> tuple:
    """Changes whenever a course, lesson or membership is added, edited or deleted."""
    return tuple(tuple(m.objects.aggregate(n=Count("pk"), t=Max("updated_at")).values())
                 for m in (Course, Lesson, CourseLesson))


def _build() -> dict:
    new_since = timezone.now() - timedelta(days=NEW_DAYS)
    lessons = {}
    for l in Lesson.objects.filter(hidden=False).values():
        lessons[l["id"]] = {
            "id": l["id"], "title": l["title"], "duration": l["duration"], "views": l["views"], "num": l["num"],
            "kind": l["kind"], "yt": l["youtube_id"],
            "video_url": default_storage.url(l["video_file"]) if l["video_file"] else l["video_url"],
            "thumb": default_storage.url(l["thumbnail"]) if l["thumbnail"] else "",
            "new": bool(l["added_at"] and l["added_at"] >= new_since), "order": l["upload_order"], "playlist": None,
        }
    courses = {c["id"]: {**c, "videos": []} for c in
               Course.objects.filter(hidden=False).order_by("created_at").values("id", "title", "category")}
    for cid, lid in (CourseLesson.objects.filter(course__hidden=False, lesson__hidden=False)
                     .order_by("course_id", "position", "pk").values_list("course_id", "lesson_id")):
        if cid in courses and lid in lessons:
            courses[cid]["videos"].append(lessons[lid])

    playlists = []
    for p in courses.values():
        if p["videos"]:
            p["videos"] = ordered(p["videos"])
            p["count"] = len(p["videos"])
            playlists.append(p)
            for v in p["videos"]:   # a lesson's "home" course = the first course it appears in
                v["playlist"] = v["playlist"] or p["id"]

    by_order = sorted((v for v in lessons.values() if v["order"] is not None), key=lambda v: -v["order"])
    return {
        "channel": channel(),
        "playlists": playlists,
        "by_pl": {p["id"]: p for p in playlists},
        "latest": [v for v in by_order if v["kind"] == Lesson.VIDEO],
        "shorts": [v for v in by_order if v["kind"] == Lesson.SHORT],
        "all_ids": set(Lesson.objects.values_list("id", flat=True)),   # includes hidden lessons
    }


def data() -> dict:
    now = time.time()
    if _cache["data"] is None or now - _cache["checked"] > CHECK_SECONDS:
        _cache["checked"] = now
        fp = _fingerprint()
        if fp != _cache["fp"] or _cache["data"] is None:
            _cache.update(fp=fp, data=_build())
            search_index.cache_clear()
    d = _cache["data"]
    d["channel"] = channel()
    if d["playlists"]:
        feed.poll(d, save_feed_videos)   # new YouTube uploads, checked hourly in the background
    return d


# ---------------------------------------------------------------- new uploads from the YouTube feed
def save_feed_videos(items: list) -> None:
    """Called by feed.py (in a background thread) with uploads the site doesn't have yet."""
    try:
        for v in sorted(items, key=lambda v: v.get("published") or ""):
            try:
                added = datetime.fromisoformat(v["published"])
            except (KeyError, ValueError):
                added = timezone.now()
            lesson, created = Lesson.objects.get_or_create(id=v["id"], defaults={
                "title": v["title"], "num": v.get("num"), "views": v.get("views"), "youtube_id": v["id"],
                "kind": Lesson.SHORT if v.get("short") else Lesson.VIDEO, "added_at": added,
            })
            if created and v.get("playlist") and Course.objects.filter(id=v["playlist"]).exists():
                CourseLesson.objects.get_or_create(course_id=v["playlist"], lesson=lesson)
        _cache["checked"] = 0   # rebuild on the next request
    finally:
        connection.close()   # this runs in its own thread
