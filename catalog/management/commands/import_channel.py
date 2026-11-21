"""Load data/channel.json (made by sync.py) into the database.

  python manage.py import_channel             add anything missing, refresh views/durations
  python manage.py import_channel --if-empty  only when the database has no lessons yet (used on startup)

It never changes titles, lesson numbers, hidden flags or video files you edited in
the admin, and never deletes anything.
"""
import json
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.data import CHANNEL_FILE
from catalog.models import Course, CourseLesson, Lesson
from sync import categorize, lesson_number


class Command(BaseCommand):
    help = "Import courses and lessons from data/channel.json"

    def add_arguments(self, parser):
        parser.add_argument("--if-empty", action="store_true", help="skip if lessons already exist")

    @transaction.atomic
    def handle(self, *args, if_empty=False, **opts):
        first_import = not Lesson.objects.exists()
        if if_empty and not first_import:
            self.stdout.write("Database already has lessons, nothing to do.")
            return
        if not CHANNEL_FILE.exists():
            self.stderr.write(f"{CHANNEL_FILE} not found (run sync.py first)")
            return
        d = json.loads(CHANNEL_FILE.read_text(encoding="utf-8"))
        playlists, latest, shorts = d.get("playlists", []), d.get("latest", []), d.get("shorts", [])

        # ---- courses (kept in the channel's playlist order)
        t0 = timezone.now()
        known_courses = set(Course.objects.values_list("id", flat=True))
        new_courses = [Course(id=p["id"], title=p["title"], category=categorize(p["title"]),
                              created_at=t0 + timedelta(seconds=i))
                       for i, p in enumerate(playlists) if p["id"] not in known_courses]
        Course.objects.bulk_create(new_courses)

        # ---- lessons
        info = {}
        for p in playlists:
            for v in p["videos"]:
                info.setdefault(v["id"], v)
        for v in latest + shorts:
            info.setdefault(v["id"], v)
        short_ids = {v["id"] for v in shorts}
        # upload order: newest = highest (latest/shorts lists are newest first)
        order = {v["id"]: len(latest) - i for i, v in enumerate(latest)}
        order |= {v["id"]: len(shorts) - i for i, v in enumerate(shorts)}

        existing = {l.id: l for l in Lesson.objects.all()}
        to_create, to_update = [], []
        for vid, v in info.items():
            if vid in existing:
                l = existing[vid]
                if (v.get("views"), v.get("duration") or l.duration) != (l.views, l.duration):
                    l.views, l.duration = v.get("views"), v.get("duration") or l.duration
                    l.updated_at = timezone.now()
                    to_update.append(l)
            else:
                to_create.append(Lesson(
                    id=vid, title=v["title"], num=lesson_number(v["title"]), duration=v.get("duration"),
                    views=v.get("views"), youtube_id=vid, kind=Lesson.SHORT if vid in short_ids else Lesson.VIDEO,
                    upload_order=order.get(vid), added_at=None if first_import else timezone.now()))
        if not first_import:   # lessons new since last time go on top of "Latest", oldest first
            top = max((l.upload_order or 0 for l in existing.values()), default=0)
            for i, l in enumerate(sorted((l for l in to_create if l.upload_order), key=lambda l: l.upload_order)):
                l.upload_order = top + 1 + i
        Lesson.objects.bulk_create(to_create, batch_size=500)
        Lesson.objects.bulk_update(to_update, ["views", "duration", "updated_at"], batch_size=500)

        # ---- which lessons are in which course
        have = set(CourseLesson.objects.values_list("course_id", "lesson_id"))
        links = [CourseLesson(course_id=p["id"], lesson_id=v["id"], position=i + 1)
                 for p in playlists for i, v in enumerate(p["videos"]) if (p["id"], v["id"]) not in have]
        CourseLesson.objects.bulk_create(links, batch_size=500, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(new_courses)} new courses, {len(to_create)} new lessons, {len(links)} course links; "
            f"refreshed views/durations of {len(to_update)} lessons."))
