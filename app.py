"""Dr. Moustafa Kamel — Academy website (Flask).

Run:  .venv/bin/python app.py   →  http://127.0.0.1:5000
Data comes from data/channel.json (create/refresh it with sync.py).
"""
import copy
import json
import re
from functools import lru_cache
from pathlib import Path

import feed
from sync import categorize, lesson_number
from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, url_for

BASE = Path(__file__).parent
DATA_FILE = BASE / "data" / "channel.json"

app = Flask(__name__)

# ---------------------------------------------------------------- i18n
CATEGORIES = {
    "quran":       {"ar": "القرآن والتفسير", "en": "Qur'an & Tafsir", "icon": "ق"},
    "hadith":      {"ar": "الحديث والسنة",   "en": "Hadith & Sunnah", "icon": "ح"},
    "seerah":      {"ar": "السيرة والشمائل", "en": "Seerah & Shamail", "icon": "س"},
    "fiqh":        {"ar": "الفقه والعقيدة",  "en": "Fiqh & Aqeedah",  "icon": "ف"},
    "seasons":     {"ar": "رمضان والمواسم",  "en": "Ramadan & Seasons", "icon": "ر"},
    "reflections": {"ar": "خواطر وتزكية",    "en": "Reflections",     "icon": "خ"},
    "other":       {"ar": "متنوع",           "en": "Other",           "icon": "✦"},
}

T = {
    "ar": {
        "academy": "أكاديمية د. مصطفى كامل", "home": "الرئيسية", "courses": "الدورات", "latest": "أحدث الدروس",
        "shorts": "المقاطع القصيرة", "about": "عن الدكتور", "subscribe": "اشترك مجاناً",
        "pill": "درس جديد كل أسبوع · مقاطع يومية",
        "hero1": "رحلتك في", "hero2": "فهم القرآن والسنة", "hero3": "تبدأ من هنا",
        "hero_p": "دروس منظمة في مسارات واضحة: التجويد والتفسير، شرح صحيح البخاري، شمائل المصطفى ﷺ، وفقه العبادات.",
        "search_ph": "ابحث عن سورة، حديث، أو موضوع… مثال: سورة الملك", "search": "بحث",
        "continue": "تابع من حيث توقفت", "start_here": "ابدأ بأحدث درس",
        "lessons": "درس", "videos_n": "درس ومقطع", "playlists_n": "سلسلة علمية", "subs_n": "مشترك",
        "all_courses": "كل الدورات ←", "view_all": "عرض الكل ←", "more": "المزيد ←",
        "all": "الكل", "completed": "أكملت", "of": "من", "not_started": "لم تبدأ بعد",
        "band_h": "لا يفوتك أي درس جديد", "band_p": "اشترك في القناة وفعّل الجرس ليصلك الدرس الجديد.",
        "yt_sub": "اشترك في يوتيوب", "series": "السلسلة", "lesson": "الدرس",
        "prev": "→ الدرس السابق", "next": "الدرس التالي ←", "mark": "✓ تحديد كمكتمل", "marked": "✓ مكتمل",
        "watch_yt": "شاهد على يوتيوب", "results_for": "نتائج البحث عن", "no_results": "لا توجد نتائج. جرّب كلمة أخرى.",
        "order": "ترتيب", "oldest": "من الأول", "newest": "الأحدث أولاً", "course_lessons": "دروس الدورة",
        "about_h": "عن الدكتور مصطفى كامل", "contact": "تواصل", "ayah": "وَرَتِّلِ الْقُرْآنَ تَرْتِيلًا", "ayah_ref": "سورة المزمل · ٤",
        "footer": "جميع الحقوق محفوظة", "nodata": "لم تتم مزامنة بيانات القناة بعد. شغّل: python sync.py",
        "reset": "إعادة ضبط التقدم", "new": "جديد",
    },
    "en": {
        "academy": "Dr. Moustafa Kamel Academy", "home": "Home", "courses": "Courses", "latest": "Latest lessons",
        "shorts": "Shorts", "about": "About", "subscribe": "Subscribe free",
        "pill": "New lesson weekly · daily Shorts",
        "hero1": "Your journey to", "hero2": "understanding the Qur'an & Sunnah", "hero3": "starts here",
        "hero_p": "Lessons organized into clear paths: Tajwid & Tafsir, Sahih al-Bukhari, the Shamail of the Prophet ﷺ, and the Fiqh of worship.",
        "search_ph": "Search a surah, hadith or topic… e.g. Al-Mulk", "search": "Search",
        "continue": "Continue where you left off", "start_here": "Start with the latest lesson",
        "lessons": "lessons", "videos_n": "lessons & clips", "playlists_n": "series", "subs_n": "subscribers",
        "all_courses": "All courses →", "view_all": "View all →", "more": "More →",
        "all": "All", "completed": "Completed", "of": "of", "not_started": "Not started yet",
        "band_h": "Never miss a new lesson", "band_p": "Subscribe to the channel and turn on notifications.",
        "yt_sub": "Subscribe on YouTube", "series": "Series", "lesson": "Lesson",
        "prev": "← Previous", "next": "Next →", "mark": "✓ Mark complete", "marked": "✓ Completed",
        "watch_yt": "Watch on YouTube", "results_for": "Results for", "no_results": "No results. Try another word.",
        "order": "Order", "oldest": "From the start", "newest": "Newest first", "course_lessons": "Course lessons",
        "about_h": "About Dr. Moustafa Kamel", "contact": "Contact", "ayah": "وَرَتِّلِ الْقُرْآنَ تَرْتِيلًا", "ayah_ref": "Al-Muzzammil · 4",
        "footer": "All rights reserved", "nodata": "Channel data not synced yet. Run: python sync.py",
        "reset": "Reset progress", "new": "New",
    },
}

# ---------------------------------------------------------------- data
_cache = {"mtime": None, "data": None}
_merged = {"key": None, "data": None}


def data() -> dict:
    """Catalog = channel.json (full sync) + new uploads from the live YouTube feed."""
    base = base_data()
    if not base["playlists"]:
        return base
    version, fresh = feed.new_videos(base)
    key = (_cache["mtime"], version)
    if _merged["key"] != key:
        _merged.update(key=key, data=merge_feed(base, fresh) if fresh else base)
        search_index.cache_clear()
    return _merged["data"]


def merge_feed(base: dict, fresh: list) -> dict:
    """Copy the catalog and slot new feed videos into Latest/Shorts and their course."""
    d = copy.deepcopy(base)
    d["by_pl"] = {p["id"]: p for p in d["playlists"]}
    fresh = sorted(fresh, key=lambda v: v["published"], reverse=True)
    item = lambda v: {k: v.get(k) for k in ("id", "title", "views", "num", "playlist", "new")} | {"duration": None}
    d["shorts"] = [item(v) for v in fresh if v["short"]] + d.get("shorts", [])
    d["latest"] = [item(v) for v in fresh if not v["short"]] + d.get("latest", [])
    for v in fresh:
        p = d["by_pl"].get(v.get("playlist"))
        if p and not v["short"]:
            p["videos"] = ordered(p["videos"] + [item(v)])
            p["count"] = len(p["videos"])
    return d


def base_data() -> dict:
    """Load channel.json, reloading automatically when sync.py rewrites it."""
    if not DATA_FILE.exists():
        return {"channel": {}, "playlists": [], "latest": [], "shorts": []}
    mtime = DATA_FILE.stat().st_mtime
    if _cache["mtime"] != mtime:
        d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        for p in d["playlists"]:
            for v in p["videos"]:
                v["num"] = lesson_number(v["title"])
            p["videos"] = ordered(p["videos"])
            p["category"] = categorize(p["title"])
            p["count"] = len(p["videos"])
        d["playlists"] = [p for p in d["playlists"] if p["videos"]]
        if d["channel"].get("avatar"):  # small avatar instead of the full-size original
            d["channel"]["avatar"] = re.sub(r"=s\d+.*$", "=s176-c-k-c0x00ffffff-no-rj", d["channel"]["avatar"])
        d["by_pl"] = {p["id"]: p for p in d["playlists"]}
        _cache.update(mtime=mtime, data=d)
        search_index.cache_clear()
    return _cache["data"]


def ordered(videos: list) -> list:
    """Course order: by lesson number when titles are numbered, else oldest-first."""
    numbered = [v for v in videos if v.get("num") is not None]
    if videos and len(numbered) >= 0.6 * len(videos):
        # unnumbered lessons stay next to the numbered lesson they follow in the playlist
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
    for v in d.get("latest", []):
        if v["id"] not in seen:
            seen.add(v["id"])
            idx.append((norm(v["title"]), v, None))
    return idx


def find_video(vid: str):
    """Return (video, playlist) for an id, searching series first, then uploads/shorts."""
    d = data()
    pid = request.args.get("list")
    if pid and pid in d["by_pl"]:
        for v in d["by_pl"][pid]["videos"]:
            if v["id"] == vid:
                return v, d["by_pl"][pid]
    for p in d["playlists"]:
        for v in p["videos"]:
            if v["id"] == vid:
                return v, p
    for v in d.get("latest", []) + d.get("shorts", []):
        if v["id"] == vid:
            return v, None
    return None, None


# ---------------------------------------------------------------- helpers
@app.context_processor
def inject():
    lang = request.cookies.get("lang", "ar")
    lang = lang if lang in T else "ar"
    d = data()
    total = len({v["id"] for p in d["playlists"] for v in p["videos"]} | {v["id"] for v in d.get("latest", [])})
    return {"t": T[lang], "lang": lang, "dir": "rtl" if lang == "ar" else "ltr", "CATS": CATEGORIES,
            "ch": d.get("channel", {}), "total_videos": total, "has_data": bool(d["playlists"])}


@app.template_filter("dur")
def fmt_duration(sec):
    if not sec:
        return ""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@app.template_filter("thumb")
def thumb(vid, size="mq"):
    return f"https://i.ytimg.com/vi/{vid}/{size}default.jpg"


@app.template_filter("compact")
def compact(n):
    if not n:
        return "—"
    return f"{n/1000:.1f}K".replace(".0K", "K") if n >= 1000 else str(n)


def featured_courses(limit=6):
    pls = sorted(data()["playlists"], key=lambda p: -p["count"])
    return pls[:limit]


# ---------------------------------------------------------------- routes
@app.route("/")
def index():
    d = data()
    latest = [v for v in d.get("latest", []) if v.get("duration") is None or v["duration"] > 60][:8] or \
             [v for p in d["playlists"][:4] for v in p["videos"][-2:]]
    cats = {}
    for p in d["playlists"]:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    return render_template("index.html", courses=featured_courses(limit=None), latest=latest,
                           shorts=d.get("shorts", [])[:12], hero=latest[0] if latest else None,
                           cat_counts=cats, n_playlists=len(d["playlists"]))


@app.route("/courses")
def courses():
    cat = request.args.get("cat")
    pls = sorted(data()["playlists"], key=lambda p: -p["count"])
    return render_template("courses.html", courses=pls, cat=cat if cat in CATEGORIES else None)


@app.route("/course/<pid>")
def course(pid):
    p = data()["by_pl"].get(pid) or abort(404)
    return render_template("course.html", p=p)


@app.route("/watch/<vid>")
def watch(vid):
    if not re.fullmatch(r"[\w-]{11}", vid):
        abort(404)
    v, p = find_video(vid)
    if not v:
        v = {"id": vid, "title": "", "num": None}
    prev_v = next_v = None
    if p:
        ids = [x["id"] for x in p["videos"]]
        i = ids.index(vid)
        prev_v = p["videos"][i - 1] if i > 0 else None
        next_v = p["videos"][i + 1] if i + 1 < len(ids) else None
    return render_template("watch.html", v=v, p=p, prev_v=prev_v, next_v=next_v)


@app.route("/latest")
def latest():
    d = data()
    vids = [v for v in d.get("latest", []) if v.get("duration") is None or v["duration"] > 60]
    return render_template("latest.html", videos=vids[:120])


@app.route("/shorts")
def shorts():
    return render_template("shorts.html", shorts=data().get("shorts", [])[:120])


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        terms = norm(q).split()
        results = [(v, p) for text, v, p in search_index() if all(t in text for t in terms)][:120]
    return render_template("search.html", q=q, results=results)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/healthz")
def healthz():
    """Quick check that the site + live feed are working."""
    d = data()
    return jsonify(ok=True, playlists=len(d["playlists"]), latest=len(d.get("latest", [])), feed=feed.status())


@app.route("/lang/<code>")
def set_lang(code):
    resp = make_response(redirect(request.referrer or url_for("index")))
    resp.set_cookie("lang", code if code in T else "ar", max_age=60 * 60 * 24 * 365)
    return resp


@app.errorhandler(404)
def not_found(_):
    return render_template("base.html", not_found=True), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)
