"""Courses and lessons, editable at /admin/.

Lessons imported from YouTube keep their YouTube video ID as their ID, so every
existing link (/watch/<id>) keeps working. Lessons added in the admin get a new
random 11-character ID in the same format.

Uploaded video files and pictures go to MEDIA_ROOT (media/ on your Mac). When a
video is uploaded, its duration and a thumbnail are filled in automatically
(needs ffmpeg; skipped quietly where it isn't installed).
"""
import secrets
import shutil
import subprocess

from django.core.files.base import ContentFile

from django.db import models
from django.db.models import Max
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

CATEGORY_CHOICES = [
    ("quran", "Qur'an & Tafsir · القرآن والتفسير"),
    ("hadith", "Hadith & Sunnah · الحديث والسنة"),
    ("seerah", "Seerah & Shamail · السيرة والشمائل"),
    ("fiqh", "Fiqh & Aqeedah · الفقه والعقيدة"),
    ("seasons", "Ramadan & Seasons · رمضان والمواسم"),
    ("reflections", "Reflections · خواطر وتزكية"),
    ("other", "Other · متنوع"),
]


def new_lesson_id() -> str:
    return secrets.token_urlsafe(8)  # 11 characters, like a YouTube video ID


def new_course_id() -> str:
    return "c-" + secrets.token_urlsafe(6)


class Course(models.Model):
    id = models.CharField("ID", max_length=64, primary_key=True, default=new_course_id,
                          help_text="Used in the address /course/&lt;ID&gt;. Imported courses use the YouTube playlist ID.")
    title = models.CharField(max_length=300)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="other")
    hidden = models.BooleanField(default=False, help_text="Hide this course from the website without deleting it.")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/course/{self.pk}"


class Lesson(models.Model):
    VIDEO, SHORT = "video", "short"

    id = models.CharField("ID", max_length=11, primary_key=True, default=new_lesson_id,
                          help_text="Used in the address /watch/&lt;ID&gt;.")
    title = models.CharField(max_length=300)
    kind = models.CharField(max_length=10, choices=[(VIDEO, "Lesson"), (SHORT, "Short clip")], default=VIDEO)
    num = models.PositiveIntegerField("Lesson number", null=True, blank=True,
                                      help_text="Lessons in a course are sorted by this number.")
    duration = models.PositiveIntegerField("Duration (seconds)", null=True, blank=True)
    video_file = models.FileField("Video file", upload_to="videos/", blank=True,
                                  help_text="Upload an MP4 (H.264). The site plays it instead of YouTube.")
    video_url = models.URLField("…or video address", max_length=500, blank=True,
                                help_text="Instead of uploading: the address of a copy stored elsewhere (e.g. Cloudflare R2).")
    thumbnail = models.ImageField("Picture", upload_to="thumbnails/", blank=True,
                                  help_text="Optional. Empty: taken from the uploaded video, or YouTube's picture.")
    youtube_id = models.CharField("YouTube ID", max_length=11, blank=True,
                                  help_text="The video on YouTube, if it exists there.")
    views = models.PositiveIntegerField(null=True, blank=True, editable=False)
    hidden = models.BooleanField(default=False, help_text="Hide this lesson from the website without deleting it.")
    upload_order = models.PositiveIntegerField(null=True, blank=True, db_index=True,
                                               help_text="Higher = newer in “Latest lessons”. Filled in automatically; "
                                                         "empty = not listed in Latest.")
    added_at = models.DateTimeField(null=True, blank=True, default=timezone.now,
                                    help_text="Lessons added in the last 14 days get a “New” badge.")
    updated_at = models.DateTimeField(auto_now=True)
    courses = models.ManyToManyField(Course, through="CourseLesson", related_name="lessons", blank=True)

    class Meta:
        ordering = ["-upload_order", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/watch/{self.pk}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.upload_order is None:
            self.upload_order = (Lesson.objects.aggregate(m=Max("upload_order"))["m"] or 0) + 1
        super().save(*args, **kwargs)
        if self.video_file and (not self.duration or not self.thumbnail):
            self.fill_from_video()

    def playback_url(self) -> str:
        return self.video_file.url if self.video_file else self.video_url

    def fill_from_video(self) -> None:
        """Duration + thumbnail from the uploaded file (ffprobe/ffmpeg)."""
        try:
            path = self.video_file.path   # only for files stored on this computer/server
        except (NotImplementedError, ValueError):
            return
        if not (shutil.which("ffprobe") and shutil.which("ffmpeg")):
            return
        changed = []
        try:
            if not self.duration:
                out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                     capture_output=True, text=True, timeout=60).stdout.strip()
                if out:
                    self.duration = round(float(out))
                    changed.append("duration")
            if not self.thumbnail:
                at = str(min(10, (self.duration or 0) * 0.1))
                jpg = subprocess.run(["ffmpeg", "-v", "error", "-ss", at, "-i", path, "-frames:v", "1",
                                      "-vf", "scale=640:-2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                                     capture_output=True, timeout=120).stdout
                if jpg:
                    self.thumbnail.save(f"{self.pk}.jpg", ContentFile(jpg), save=False)
                    changed.append("thumbnail")
        except (subprocess.SubprocessError, ValueError, OSError):
            pass
        if changed:
            super().save(update_fields=changed + ["updated_at"])


class CourseLesson(models.Model):
    """A lesson inside a course. One lesson can be part of several courses."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="memberships")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="memberships")
    position = models.PositiveIntegerField(default=0, blank=True,
                                           help_text="Order inside the course when lessons have no lesson number. Empty = at the end.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course", "position"]
        constraints = [models.UniqueConstraint(fields=["course", "lesson"], name="unique_lesson_per_course")]
        verbose_name = "course membership"

    def __str__(self):
        return f"{self.course} → {self.lesson}"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.position:
            self.position = (CourseLesson.objects.filter(course_id=self.course_id)
                             .aggregate(m=Max("position"))["m"] or 0) + 1
        super().save(*args, **kwargs)


@receiver(post_delete, sender=Lesson)
def delete_lesson_files(sender, instance, **kwargs):
    """Deleting a lesson also deletes its uploaded video and picture (not YouTube's)."""
    for f in (instance.video_file, instance.thumbnail):
        if f:
            f.delete(save=False)
