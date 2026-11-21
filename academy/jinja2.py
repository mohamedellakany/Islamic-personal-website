"""Jinja environment for the public pages (Django's Jinja2 template backend).

Helpers available in every template:
  url('name', *path_args, **query)  → reverse() of a URL name from academy/urls.py; keyword
                                      arguments become ?query=parameters (None values are dropped)
  static('style.css')               → address of a file in static/
  filters: dur (seconds → 1:02:03), thumb (lesson picture), compact (3120 → 3.1K)
"""
from urllib.parse import urlencode

from django.templatetags.static import static
from django.urls import reverse
from jinja2 import Environment


def url(name: str, *args, **query) -> str:
    path = reverse(name, args=args)
    query = {k: v for k, v in query.items() if v is not None}
    return f"{path}?{urlencode(query)}" if query else path


def dur(sec) -> str:
    if not sec:
        return ""
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def thumb(v, size="mq") -> str:
    """Lesson picture: its own thumbnail, else YouTube's, else a plain placeholder."""
    if isinstance(v, str):   # a bare YouTube ID
        return f"https://i.ytimg.com/vi/{v}/{size}default.jpg"
    if v.get("thumb"):
        return v["thumb"]
    if v.get("yt"):
        return f"https://i.ytimg.com/vi/{v['yt']}/{size}default.jpg"
    return static("img/lesson-placeholder.svg")


def compact(n) -> str:
    if not n:
        return "—"
    return f"{n/1000:.1f}K".replace(".0K", "K") if n >= 1000 else str(n)


def environment(**options) -> Environment:
    env = Environment(**options)
    env.globals.update(url=url, static=static)
    env.filters.update(dur=dur, thumb=thumb, compact=compact)
    return env
