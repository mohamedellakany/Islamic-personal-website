"""Fetch the YouTube channel catalog (playlists, videos, shorts) into data/channel.json.

Run:  .venv/bin/python sync.py            (full sync)
      .venv/bin/python sync.py --quick    (skip the full uploads/shorts lists)
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yt_dlp

CHANNEL = "https://www.youtube.com/@dr.moustafakamel508"
OUT = Path(__file__).parent / "data" / "channel.json"

YDL_OPTS = {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True, "logger": None, "skip_download": True,
            "extractor_args": {"youtube": {"lang": ["ar"]}}}  # original Arabic titles, not auto-translated

# Map playlist titles to a topic category used for filters/colors.
CATEGORY_RULES = [
    ("seasons", r"رمضان|شعبان|رجب|ربيع|العيد|التراويح|الحج|ذي الحجة|Ramadan"),
    ("hadith", r"البخاري|السنة النبوية|حديث|الحديث|البيقونية|البيقونيه|يتحدث عن نفسه|Bukhari|Hadith"),
    ("seerah", r"شمائل|السيرة|الهجرة|الاسراء|الإسراء|رسول الله|المبشرين|الصحابة|موسى|صاحب الخلق|Seerah"),
    ("quran", r"قر[آا]ن|سورة|سور |تفسير|تجويد|التجويد|حفظ|Qur|Tafsir"),
    ("fiqh", r"فقه|الفقه|الزكاة|المعاملات|المستثمر|التوحيد|عقيدة|Aqeeda|Fiqh|Zakat"),
    ("reflections", r"خواطر|خاطرة|تزكية|القدوة|معالم|الأخلاق|أخلاق|النفوس|أسماء الله|خطب|دروس العشاء|دروس السبت|الزوجي"),
]


def categorize(title: str) -> str:
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, title):
            return cat
    return "other"


def lesson_number(title: str):
    """Leading lesson number like '77- ...' or '٩٣٨- ...' (Arabic-Indic digits)."""
    t = title.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).strip()
    m = re.match(r"^\(?(\d{1,4})(?:\s*[-–ـ):.]|\s+\D)", t)
    if not m or 1990 <= int(m.group(1)) <= 2100:  # ignore years like "2022 رمضان"
        return None
    return int(m.group(1))


def slim_video(e: dict) -> dict | None:
    vid = e.get("id")
    if not vid or len(vid) != 11:
        return None
    title = e.get("title") or ""
    if title in ("[Private video]", "[Deleted video]"):
        return None
    return {
        "id": vid,
        "title": title,
        "duration": e.get("duration"),
        "views": e.get("view_count"),
        "num": lesson_number(title),
    }


def extract(url: str) -> dict:
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        return ydl.extract_info(url, download=False) or {}


def subscriber_count():
    """Separate English request: yt-dlp can't parse the Arabic-localized count ("3.12 ألف")."""
    opts = {**YDL_OPTS, "playlistend": 1}
    opts.pop("extractor_args")
    with yt_dlp.YoutubeDL(opts) as ydl:
        return (ydl.extract_info(f"{CHANNEL}/videos", download=False) or {}).get("channel_follower_count")


def fetch_playlist(p: dict) -> dict:
    try:
        info = extract(f"https://www.youtube.com/playlist?list={p['id']}")
        videos = [v for v in (slim_video(e) for e in info.get("entries") or []) if v]
    except Exception as ex:  # keep going if a single playlist fails
        print(f"  ! {p['title']}: {ex}", file=sys.stderr)
        videos = []
    print(f"  ✓ {p['title']} ({len(videos)})")
    return {**p, "videos": videos, "count": len(videos)}


def main(quick: bool = False):
    t0 = time.time()
    print("Fetching channel info + playlists…")
    pl_info = extract(f"{CHANNEL}/playlists")
    playlists = [
        {"id": e["id"], "title": e.get("title") or "", "category": categorize(e.get("title") or "")}
        for e in pl_info.get("entries") or []
        if e.get("id", "").startswith("PL")
    ]
    print(f"Found {len(playlists)} playlists")

    with ThreadPoolExecutor(max_workers=6) as pool:
        playlists = list(pool.map(fetch_playlist, playlists))

    latest, shorts, subs = [], [], pl_info.get("channel_follower_count")
    if not quick:
        print("Fetching uploads + shorts…")
        uploads = extract(f"{CHANNEL}/videos")
        subs = subs or uploads.get("channel_follower_count") or subscriber_count()
        latest = [v for v in (slim_video(e) for e in (uploads.get("entries") or [])) if v]
        shorts = [v for v in (slim_video(e) for e in (extract(f"{CHANNEL}/shorts").get("entries") or [])) if v]

    # video id -> playlist id, so lesson pages know their series
    owner = {}
    for p in playlists:
        for v in p["videos"]:
            owner.setdefault(v["id"], p["id"])
    for v in latest:
        v["playlist"] = owner.get(v["id"])

    data = {
        "channel": {
            "id": pl_info.get("channel_id") or pl_info.get("uploader_id"),
            "name": "Dr. Moustafa Kamel",
            "name_ar": "د. مصطفى كامل",
            "url": CHANNEL,
            "avatar": re.sub(r"=s\d+.*$", "=s176-c-k-c0x00ffffff-no-rj", next((t["url"] for t in reversed(pl_info.get("thumbnails") or []) if "avatar" in (t.get("id") or "")), "")) or None,
            "subscribers": subs,
            "description": pl_info.get("description"),
        },
        "playlists": playlists,
        "latest": latest,
        "shorts": shorts,
        "synced_at": int(time.time()),
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {OUT} — {len(playlists)} playlists, {len(latest)} uploads, {len(shorts)} shorts in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
