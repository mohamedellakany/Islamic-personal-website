# Dr. Moustafa Kamel Academy — website

Python (Flask) site for the YouTube channel https://www.youtube.com/@dr.moustafakamel508.
Layout: "Academy" (courses + progress). Palette: "Manuscript" (green, gold, cream).

## 1. Development (your Mac)
```bash
cd ~/Downloads/Apps/dr-moustafa-kamel-site
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
bash dev.sh                                                         # start; Ctrl+C to stop
```
Opens on http://127.0.0.1:5000 (or the next free port) and reloads when you save a file.
Refresh lesson data from YouTube: `.venv/bin/python sync.py` (~70s).

## 2. Publish (Azure)
```bash
bash deploy/azure_deploy.sh                                  # upload code + data, restart
.venv/bin/python sync.py && bash deploy/azure_deploy.sh      # refresh lessons, then publish
git add -A && git commit -m "…" && git push                  # save to GitHub
```
Live site: https://drmoustafakamel-academy.azurewebsites.net · status: `/healthz`

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
- `sync.py` — fetches the channel catalog with yt-dlp, assigns each playlist a topic, parses lesson numbers.
- `app.py` — routes: `/`, `/courses?cat=`, `/course/<playlist>`, `/watch/<video>?list=`, `/latest`, `/shorts`, `/search?q=`, `/about`, `/lang/<ar|en>`.
- `templates/` — Jinja pages; `static/style.css`, `static/app.js` (progress saved in the visitor's browser).
- `designs.html` — the original 3 design concepts.

## Notes
- Arabic is the default (RTL); the EN button switches the interface to English.
- Search ignores Arabic diacritics and hamza/ta-marbuta variants, and accepts Arabic or Latin digits.
- For production, run behind gunicorn: `pip install gunicorn && gunicorn -w 2 app:app`.

## Motion & transitions (`static/app.js`, bottom of `static/style.css`)
- Page-to-page: View Transitions API crossfade; header stays fixed; the clicked thumbnail morphs into the course banner / video player.
- Language switch: blur crossfade, keeps the scroll position.
- Category tabs (home + /courses): filter in place with cards gliding to new positions and a sliding pill; URL + Back button stay in sync on /courses.
- Links are prefetched on hover (Speculation Rules) for near-instant navigation; gold loading bar on top.
- Scroll reveal, count-up stats, nav underline, animated mobile menu.
- Browsers without View Transitions get simple fades; `prefers-reduced-motion` turns all motion off.

Running it from your IDE
1. Open the dr-moustafa-kamel-site folder.
2. Set the Python interpreter to the project's virtual environment: dr-moustafa-kamel-site/.venv/bin/python.
   - VS Code: Cmd+Shift+P → "Python: Select Interpreter" → choose .venv.
   - PyCharm: Settings → Project → Python Interpreter → Add → Existing → choose .venv/bin/python.
3. Run app.py, then open http://127.0.0.1:5000.

If the port gets stuck again, run this in a terminal:
lsof -ti tcp:5000 | xargs kill
It finds whatever is using port 5000 and stops it. If it won't stop, use kill -9 instead of kill.

On a Mac, port 5000 is sometimes taken by the system's AirPlay Receiver. In that case, either turn it off (System Settings → General → AirDrop & Handoff → AirPlay Receiver) or use a different port by changing the last line of app.py to app.run(debug=True, port=5001).


## Live YouTube feed (`feed.py`)
Every hour the site reads the channel's public RSS feed (latest ~15 uploads) and merges new videos:
new lessons appear in Latest + their course with a "New" badge, Shorts go to Shorts. Run a full
`sync.py` occasionally (e.g. monthly) to pick up durations, new playlists and anything older than the feed.
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
