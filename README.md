# Dr. Moustafa Kamel Academy — website

Python (Django) site for the YouTube channel https://www.youtube.com/@dr.moustafakamel508.
Layout: "Academy" (courses + progress). Palette: "Manuscript" (green, gold, cream).

## 1. Development (your Mac)
```bash
cd ~/Downloads/Apps/dr-moustafa-kamel-site
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time / after requirements change
bash dev.sh                                                         # start; Ctrl+C to stop
.venv/bin/python manage.py createsuperuser                          # first time only: your local admin login
```
Opens on http://127.0.0.1:5000 (or the next free port) and reloads when you save a file.
The first start creates the database `data/db.sqlite3` and loads every lesson from `data/channel.json`.
Refresh views/durations and pick up anything missing from YouTube:
`.venv/bin/python sync.py && .venv/bin/python manage.py import_channel` (~70s; never overwrites your admin edits).

## 2. Publish (Azure)
```bash
bash deploy/azure_deploy.sh                                  # upload code, restart
bash deploy/azure_admin.sh                                   # once: set the /admin login (asks for a password)
git add -A && git commit -m "…" && git push                  # save to GitHub
```
Live site: https://drmoustafakamel-academy.azurewebsites.net · admin: `/admin/` · status: `/healthz`

On Azure the database is `/home/data/db.sqlite3`: it survives deploys and restarts, and on the very first
start it is filled from `data/channel.json`. Lessons you add or edit in the admin live **only** there,
so deploying from your Mac never overwrites them (your local `data/db.sqlite3` is a separate copy for testing).

## Admin (`/admin/`)
- **Lessons:** add, edit, hide/show, search, filter by course, type, or "own copy vs YouTube only".
  A lesson can be in several courses ("In these courses" at the bottom of the lesson page).
- **Video file:** upload an MP4 (H.264) and the site plays it instead of YouTube. Duration and picture are filled
  in automatically (ffmpeg). Files go to `media/` on your Mac (never committed). **…or video address:** paste the
  address of a copy stored elsewhere (e.g. Cloudflare R2). Neither = YouTube.
- **Duration:** type `25:30` or `1:05:00`. **Lesson number:** sets the order inside the course.
- **Hide instead of delete** a YouTube lesson: a deleted one can come back from the hourly YouTube check.
- New lessons get a "New" badge for 14 days and go to the top of "Latest lessons".
- Changes show on the site within a few seconds.

## 3. Your own live stream (Cloudflare Stream)
1. Cloudflare dashboard → Stream → **Live inputs** → Create (turn on "Automatically record" if wanted).
2. `cp .env.example .env` and fill in `CF_STREAM_CUSTOMER` (customer-xxxx.cloudflarestream.com) and
   `CF_LIVE_INPUT_ID`. `.env` is never committed. `CF_API_TOKEN` only if the status check asks for one.
3. Test locally: `bash dev.sh` (shows "Live source: Cloudflare…"), go live, open `/live`.
4. Turn it on for the public site: `bash deploy/cloudflare_live.sh` (`--off` to remove).

Broadcast with any RTMPS app (OBS, Prism Live Studio, …) using the input's RTMPS URL + stream key
(keep the key secret). While the input is live, `/live` plays it (hls.js) instead of YouTube, with the
on-air banner, badge and QR code; when it stops the page returns to YouTube/offline by itself.
The site asks Cloudflare `https://<customer>/<input>/lifecycle` every ~20s (falls back to probing the
HLS manifest). `OWN_LIVE_HLS` can point at any other HLS stream instead.

## Files
- `academy/` — Django settings, URLs, and the Jinja setup the templates use (`url()`, `static()`, filters).
- `catalog/models.py` — Course, Lesson, CourseLesson (the database tables). `catalog/admin.py` — the admin page.
- `catalog/views.py` — pages: `/`, `/courses?cat=`, `/course/<id>`, `/watch/<id>?list=`, `/latest`, `/shorts`, `/search?q=`, `/about`, `/live`, `/lang/<ar|en>`.
- `catalog/data.py` — builds the catalog from the database (cached in memory), search, saves new YouTube uploads.
- `catalog/management/commands/` — `import_channel` (channel.json → database), `ensure_admin` (Azure login).
- `sync.py` — fetches the channel catalog with yt-dlp into `data/channel.json`, assigns topics, parses lesson numbers.
- `templates/` — Jinja pages; `static/style.css`, `static/app.js` (progress saved in the visitor's browser).
- `designs.html` — the original 3 design concepts.

## Notes
- Arabic is the default (RTL); the EN button switches the interface to English.
- Search ignores Arabic diacritics and hamza/ta-marbuta variants, and accepts Arabic or Latin digits.
- Production runs `gunicorn academy.wsgi` (Azure's startup command is set by `deploy/azure_deploy.sh`).

## Motion & transitions (`static/app.js`, bottom of `static/style.css`)
- Page-to-page: View Transitions API crossfade; header stays fixed; the clicked thumbnail morphs into the course banner / video player.
- Language switch: blur crossfade, keeps the scroll position.
- Category tabs (home + /courses): filter in place with cards gliding to new positions and a sliding pill; URL + Back button stay in sync on /courses.
- Links are prefetched on hover (Speculation Rules) for near-instant navigation; gold loading bar on top.
- Scroll reveal, count-up stats, nav underline, animated mobile menu.
- Browsers without View Transitions get simple fades; `prefers-reduced-motion` turns all motion off.

## Running it from your IDE
1. Open the folder and set the interpreter to `.venv/bin/python` (VS Code: Cmd+Shift+P → "Python: Select Interpreter").
2. Run `manage.py` with the arguments `runserver` and the environment variable `DJANGO_DEBUG=1`, or just use `bash dev.sh`.

If a port gets stuck: `lsof -ti tcp:5000 | xargs kill` (use `kill -9` if it won't stop). On a Mac, port 5000 is
sometimes taken by AirPlay Receiver; `dev.sh` simply picks the next free port.


## Live YouTube feed (`feed.py`)
Every hour the site reads the channel's public RSS feed (latest ~15 uploads) and **saves new videos to the
database**: they appear in Latest + their course with a "New" badge (Shorts go to Shorts), and you can edit them
in the admin. Set `YOUTUBE_FEED=0` to switch this off. Lesson durations aren't in the feed: add them in the admin, or
run `sync.py` + `manage.py import_channel` occasionally.
Check status at `/healthz`.

## Live broadcast (`live.py`)
`/live` shows the YouTube live stream + live chat automatically when the channel is on air, a countdown when a
stream is scheduled, and an offline message otherwise (checked every ~45s; pages update without refresh).
A red "Live" badge and a site-wide banner appear on every page while on air.
QR code: `/live/qr.png` (add `?download=1&size=24` for a large file), printable A4 poster: `/live/poster`.
Set `SITE_URL` if you move to a custom domain; `LIVE_CHANNEL_ID` can point at another channel for testing.

## Deploy
- **Azure App Service (free F1)** — live at https://drmoustafakamel-academy.azurewebsites.net
  ```bash
  brew install azure-cli
  bash deploy/azure_deploy.sh            # first run creates everything; later runs just update
  ```
  Tries several regions automatically if one refuses the free plan.
- **Any Ubuntu VM (Oracle/Azure/other)** — `bash deploy/deploy.sh <IP>` then on the server `bash deploy/setup_server.sh`
  (gunicorn + nginx + daily sync timer).

To refresh data and redeploy: `.venv/bin/python sync.py && bash deploy/azure_deploy.sh`
