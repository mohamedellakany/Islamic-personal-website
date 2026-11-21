from django.contrib import admin
from django.urls import path

from catalog import views

admin.site.site_header = "Dr. Moustafa Kamel Academy · Admin"
admin.site.site_title = "Academy admin"
admin.site.index_title = "Manage courses and lessons"
admin.site.site_url = "/"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("courses", views.courses, name="courses"),
    path("course/<str:pid>", views.course, name="course"),
    path("watch/<str:vid>", views.watch, name="watch"),
    path("latest", views.latest, name="latest"),
    path("shorts", views.shorts, name="shorts"),
    path("search", views.search, name="search"),
    path("about", views.about, name="about"),
    path("live", views.live_page, name="live_page"),
    path("api/live", views.api_live, name="api_live"),
    path("api/lesson/<str:vid>", views.api_lesson, name="api_lesson"),
    path("live/qr.png", views.live_qr, name="live_qr"),
    path("live/poster", views.live_poster, name="live_poster"),
    path("healthz", views.healthz, name="healthz"),
    path("lang/<str:code>", views.set_lang, name="set_lang"),
    path("media/<path:path>", views.media, name="media"),
]

handler404 = "catalog.views.not_found"
