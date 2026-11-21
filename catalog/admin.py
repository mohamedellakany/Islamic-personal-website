"""The admin page at /admin/: add, edit, hide and organize courses and lessons."""
import re

from django import forms
from django.contrib import admin, messages
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from academy.jinja2 import dur, thumb
from .models import Course, CourseLesson, Lesson


# ---------------------------------------------------------------- duration typed as 25:30 or 1:05:00
class DurationField(forms.CharField):
    def prepare_value(self, value):
        return dur(value) if isinstance(value, int) else value

    def to_python(self, value):
        value = (value or "").strip()
        if not value:
            return None
        if not re.fullmatch(r"\d+(:\d{1,2}){0,2}", value):
            raise forms.ValidationError("Use minutes:seconds (25:30) or hours:minutes:seconds (1:05:00).")
        secs = 0
        for part in value.split(":"):
            secs = secs * 60 + int(part)
        return secs


class LessonForm(forms.ModelForm):
    duration = DurationField(required=False, label="Duration", help_text="e.g. 25:30 or 1:05:00")

    class Meta:
        model = Lesson
        fields = "__all__"


# ---------------------------------------------------------------- lessons
class CourseLessonInline(admin.TabularInline):
    model = CourseLesson
    fields = ["course", "position"]
    autocomplete_fields = ["course"]
    extra = 0
    verbose_name = "course"
    verbose_name_plural = "In these courses"

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if obj else 1


class OwnVideoFilter(admin.SimpleListFilter):
    title = "video file"
    parameter_name = "own"

    def lookups(self, request, model_admin):
        return [("yes", "Own copy (not YouTube)"), ("no", "YouTube only")]

    def queryset(self, request, qs):
        if self.value() == "yes":
            return qs.exclude(video_file="", video_url="")
        if self.value() == "no":
            return qs.filter(video_file="", video_url="")
        return qs


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    form = LessonForm
    inlines = [CourseLessonInline]
    list_display = ["title", "num", "course_list", "kind", "length", "source", "hidden", "added_at"]
    list_display_links = ["title"]
    list_filter = ["kind", "hidden", OwnVideoFilter, "courses"]
    search_fields = ["title", "id", "youtube_id"]
    list_per_page = 50
    readonly_fields = ["preview", "id", "views"]
    actions = ["hide", "show"]
    fieldsets = [
        (None, {"fields": ["preview", "title", "kind", "num", "duration"]}),
        ("Video", {"fields": ["video_file", "video_url", "thumbnail", "youtube_id"],
                   "description": "Upload a video file (or paste its address) to play your own copy. "
                                  "Without one, the YouTube video is used. Duration and picture are "
                                  "filled in automatically from an uploaded file when left empty."}),
        ("Visibility", {"fields": ["hidden", "added_at", "upload_order"]}),
        ("Info", {"fields": ["id", "views"], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("courses")

    @admin.display(description="Courses")
    def course_list(self, obj):
        names = [c.title for c in obj.courses.all()]
        return ", ".join(n[:40] for n in names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "") or "—"

    @admin.display(description="Length", ordering="duration")
    def length(self, obj):
        return dur(obj.duration) or "—"

    @admin.display(description="Plays from")
    def source(self, obj):
        if obj.video_file:
            return "Uploaded file"
        return "Video address" if obj.video_url else ("YouTube" if obj.youtube_id else "—")

    @admin.display(description="Picture")
    def preview(self, obj):
        if not obj.pk:
            return "Shown after saving."
        src = thumb({"thumb": obj.thumbnail.url if obj.thumbnail else "", "yt": obj.youtube_id})
        return format_html('<a href="/watch/{}" target="_blank"><img src="{}" style="height:90px;border-radius:6px"></a>',
                           obj.pk, src)

    @admin.action(description="Hide selected lessons from the website")
    def hide(self, request, qs):
        n = qs.update(hidden=True, updated_at=timezone.now())
        self.message_user(request, f"{n} lessons hidden.", messages.SUCCESS)

    @admin.action(description="Show selected lessons on the website")
    def show(self, request, qs):
        n = qs.update(hidden=False, updated_at=timezone.now())
        self.message_user(request, f"{n} lessons visible.", messages.SUCCESS)


# ---------------------------------------------------------------- courses
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "n_lessons", "hidden", "lessons_link"]
    list_filter = ["category", "hidden"]
    search_fields = ["title", "id"]
    list_per_page = 100
    ordering = ["title"]
    actions = ["hide", "show"]

    def get_fields(self, request, obj=None):
        return ["title", "category", "hidden"] + (["id", "lessons_link", "first_lessons"] if obj else [])

    def get_readonly_fields(self, request, obj=None):
        return ["id", "lessons_link", "first_lessons"] if obj else []

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n=Count("memberships"))

    @admin.display(description="Lessons", ordering="_n")
    def n_lessons(self, obj):
        return obj._n

    @admin.display(description="Manage lessons")
    def lessons_link(self, obj):
        url = reverse("admin:catalog_lesson_changelist") + f"?courses__id__exact={obj.pk}"
        return format_html('<a href="{}">Open the lessons of this course →</a>', url)

    @admin.display(description="First lessons")
    def first_lessons(self, obj):
        rows = obj.memberships.select_related("lesson").order_by("position")[:8]
        return format_html("<ol>{}</ol>", format_html_join("", "<li>{}</li>", ((m.lesson.title,) for m in rows)))

    @admin.action(description="Hide selected courses from the website")
    def hide(self, request, qs):
        self.message_user(request, f"{qs.update(hidden=True, updated_at=timezone.now())} courses hidden.", messages.SUCCESS)

    @admin.action(description="Show selected courses on the website")
    def show(self, request, qs):
        self.message_user(request, f"{qs.update(hidden=False, updated_at=timezone.now())} courses visible.", messages.SUCCESS)
