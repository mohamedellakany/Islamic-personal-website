// Progress tracking is stored per-visitor in localStorage (no accounts needed).
const KEY = "mk-progress-v1";
const store = () => { try { return JSON.parse(localStorage.getItem(KEY)) || { done: {}, last: null }; } catch { return { done: {}, last: null }; } };
const save = (s) => localStorage.setItem(KEY, JSON.stringify(s));
const L = window.I18N || {};

function doneIn(pl) { return store().done[pl] || []; }
function allDone() { return new Set(Object.values(store().done).flat()); }

function toggleDone(vid, pl) {
  const s = store(); const key = pl || "_";
  const list = new Set(s.done[key] || []);
  list.has(vid) ? list.delete(vid) : list.add(vid);
  s.done[key] = [...list]; save(s); render();
  return list.has(vid);
}

function saveLast(item) { const s = store(); s.last = item; save(s); }

function resetProgress(pl) { const s = store(); delete s.done[pl]; save(s); render(); }

function render() {
  const all = allDone();
  // progress bars + texts
  document.querySelectorAll("[data-progress]").forEach((el) => {
    const n = doneIn(el.dataset.progress).length, total = +el.dataset.count || 1;
    const bar = el.classList.contains("bar") ? el : el.querySelector(".bar");
    if (bar) bar.querySelector("i").style.width = Math.min(100, (n / total) * 100) + "%";
    const txt = el.querySelector(".progress-text");
    if (txt) txt.textContent = n ? `${L.completed} ${n} ${L.of} ${total}` : L.not_started;
  });
  document.querySelectorAll("[data-progress-text]").forEach((el) => {
    const n = doneIn(el.dataset.progressText).length;
    el.textContent = n ? `${L.completed} ${n} ${L.of} ${el.dataset.count}` : L.not_started;
  });
  // lesson lists + video cards
  document.querySelectorAll(".lesson-list li[data-vid]").forEach((li) => li.classList.toggle("done", all.has(li.dataset.vid)));
  document.querySelectorAll(".vid[data-vid]").forEach((a) => a.classList.toggle("is-done", all.has(a.dataset.vid)));
  // mark-complete button
  const mark = document.getElementById("mark");
  if (mark) {
    const on = all.has(mark.dataset.vid);
    mark.textContent = on ? L.marked : L.mark;
    mark.classList.toggle("done", on); mark.classList.toggle("gold", !on);
  }
  // course page: resume at first unfinished lesson
  const resume = document.getElementById("resume");
  if (resume) {
    const done = new Set(doneIn(resume.dataset.pl));
    const next = [...document.querySelectorAll(".lesson-list li[data-vid]")].find((li) => !done.has(li.dataset.vid));
    if (next && done.size) {
      resume.href = next.querySelector("a").href;
      resume.textContent = `▶ ${L.continue} · ${L.lesson} ${next.querySelector(".n").textContent}`;
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  render();
  document.getElementById("mark")?.addEventListener("click", (e) => toggleDone(e.target.dataset.vid, e.target.dataset.pl));

  // Home hero: "continue where you left off"
  // Only shown when that lesson still exists; a deleted/hidden one is forgotten and
  // the card keeps showing the latest lesson. The picture is swapped in once loaded.
  const last = store().last, link = document.getElementById("hero-link");
  if (last && last.vid && link) {
    fetch(`/api/lesson/${encodeURIComponent(last.vid)}` + (last.pl ? `?list=${encodeURIComponent(last.pl)}` : ""))
      .then((r) => (r.status === 404 ? null : r.ok ? r.json() : undefined))
      .then((info) => {
        if (info === null) { const s = store(); s.last = null; save(s); return; }   // lesson is gone
        if (!info) return;                                                           // network error: leave as is
        const img = new Image();
        img.onload = () => {
          link.href = info.url;
          document.getElementById("hero-img").src = info.thumb;
          document.getElementById("hero-label").textContent = L.continue;
          document.getElementById("hero-title").textContent = info.title;
        };
        img.src = info.thumb;
      })
      .catch(() => {});
  }
});

/* =====================================================================
   MOTION — smooth navigation, language switch, in-place filtering
   ===================================================================== */
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const html = document.documentElement;
const loader = () => document.getElementById("loader");

// ---- 1. Page-to-page navigation --------------------------------------
function isInternalNav(a, e) {
  return a && a.href && a.origin === location.origin && !a.target && !a.hasAttribute("download") &&
    !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && e.button === 0 &&
    !(a.pathname === location.pathname && a.search === location.search && a.hash);
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (!isInternalNav(a, e) || e.defaultPrevented) return;

  // language switch: remember scroll, tag the transition as "lang"
  if (a.hasAttribute("data-lang-switch")) {
    sessionStorage.setItem("vt-type", "lang");
    sessionStorage.setItem("vt-scroll", String(scrollY));
  }

  // the clicked thumbnail morphs into the course banner / video player on the next page
  const img = !a.closest(".logo") && a.querySelector("img");
  if (img && html.classList.contains("vt")) {
    document.querySelectorAll("[data-vt-media]").forEach((el) => (el.style.viewTransitionName = "none"));
    img.style.viewTransitionName = "media";
  }

  loader()?.classList.remove("done");
  loader()?.classList.add("go");

  // browsers without cross-page transitions: quick fade-out before leaving
  if (html.classList.contains("no-vt") && !reduceMotion) {
    e.preventDefault();
    html.classList.add(a.hasAttribute("data-lang-switch") ? "lang-leaving" : "leaving");
    setTimeout(() => (location.href = a.href), 170);
  }
});

// old page: label the outgoing transition
addEventListener("pageswap", (e) => {
  if (e.viewTransition && sessionStorage.getItem("vt-type") === "lang") e.viewTransition.types.add("lang");
});

// new page (before first paint): label incoming transition + restore scroll for language switch
function arrive(e) {
  const type = sessionStorage.getItem("vt-type"), y = sessionStorage.getItem("vt-scroll");
  if (e?.viewTransition && type) e.viewTransition.types.add(type);
  sessionStorage.removeItem("vt-type");
  sessionStorage.removeItem("vt-scroll");
  if (y === null) return;
  history.scrollRestoration = "manual";
  const go = () => scrollTo({ top: +y, behavior: "instant" });
  go();
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", go) : go();
}
addEventListener("pagereveal", arrive);
if (html.classList.contains("no-vt")) document.addEventListener("DOMContentLoaded", () => arrive());

// back/forward cache: reset anything we changed before leaving
addEventListener("pageshow", (e) => {
  loader()?.classList.replace("go", "done");
  html.classList.remove("leaving", "lang-leaving");
  if (e.persisted) {
    document.querySelectorAll("img[style*='view-transition-name']").forEach((i) => (i.style.viewTransitionName = ""));
    document.querySelectorAll("[data-vt-media]").forEach((el) => (el.style.viewTransitionName = "media"));
  }
});

// ---- 2. Category filtering in place ----------------------------------
function initFilter(box) {
  const tabs = box.querySelector(".tabs"), grid = box.querySelector("[data-filter-grid]");
  const cards = [...grid.children], limit = +grid.dataset.limit || Infinity;
  const more = box.querySelector("[data-filter-more]"), empty = box.querySelector("[data-filter-empty]");
  const syncUrl = box.hasAttribute("data-filter-url");

  // sliding pill behind the active tab
  const ind = document.createElement("span");
  ind.className = "tab-ind";
  tabs.prepend(ind);
  tabs.classList.add("has-ind");
  const moveInd = (instant) => {
    const on = tabs.querySelector("a.on");
    if (!on) return;
    if (instant) ind.style.transition = "none";
    ind.style.width = on.offsetWidth + "px";
    ind.style.height = on.offsetHeight + "px";
    ind.style.transform = `translate(${on.offsetLeft}px, ${on.offsetTop}px)`;
    if (instant) requestAnimationFrame(() => (ind.style.transition = ""));
  };
  moveInd(true);
  addEventListener("resize", () => moveInd(true));
  document.fonts?.ready.then(() => moveInd(true));

  const apply = (cat) => {
    let shown = 0;
    cards.forEach((c) => {
      const match = !cat || c.dataset.cat === cat;
      const show = match && shown < limit;
      if (show) shown++;
      c.hidden = !show;
    });
    if (empty) empty.hidden = shown > 0;
    tabs.querySelectorAll("a").forEach((t) => t.classList.toggle("on", t.dataset.cat === cat));
    if (more) more.href = "/courses" + (cat ? `?cat=${cat}` : "");
    moveInd();
  };

  const run = (cat) => {
    if (reduceMotion) return apply(cat);
    if (document.startViewTransition && window.ViewTransition && "types" in ViewTransition.prototype) {
      // temporary names: each card glides to its new spot, the pill slides to the new tab
      cards.forEach((c, i) => {
        c.classList.remove("rv", "in");
        c.style.viewTransitionName = `card-${i}`; c.style.viewTransitionClass = "card";
      });
      ind.style.viewTransitionName = "tab-ind";
      const vt = document.startViewTransition({ update: () => apply(cat), types: ["filter"] });
      vt.finished.finally(() => {
        cards.forEach((c) => (c.style.viewTransitionName = ""));
        ind.style.viewTransitionName = "";
      });
    } else {
      grid.classList.add("fading");
      setTimeout(() => { apply(cat); grid.classList.remove("fading"); }, 180);
    }
  };

  tabs.addEventListener("click", (e) => {
    const t = e.target.closest("a[data-cat]");
    if (!t || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    if (t.classList.contains("on")) return;
    run(t.dataset.cat);
    if (syncUrl) history.pushState({ cat: t.dataset.cat }, "", t.href);
  });

  if (syncUrl) addEventListener("popstate", () => run(new URLSearchParams(location.search).get("cat") || ""));
}

// ---- 3. Scroll reveal + count-up --------------------------------------
function initReveal() {
  const items = document.querySelectorAll(".course:not([hidden]), .vid, .short, .lesson-list:not(.compact) li, .ayah, .band, .pn a, .about-text");
  // items already on screen are left alone (the page transition handles their entrance)
  let pending = [...items].filter((el) => el.getBoundingClientRect().top >= innerHeight);
  pending.forEach((el) => el.classList.add("rv"));
  let ticking = false;
  const check = () => {
    ticking = false;
    let i = 0;
    // reveal anything that is in view OR was jumped past (so nothing stays invisible)
    pending = pending.filter((el) => {
      if (el.getBoundingClientRect().top > innerHeight - 40) return true;
      el.style.transitionDelay = Math.min(i++ * 60, 360) + "ms";
      el.classList.add("in");
      return false;
    });
    if (!pending.length) removeEventListener("scroll", onScroll);
  };
  const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(check); } };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);
  check();
  // once revealed, return the element to its normal styles so hover effects stay snappy
  document.addEventListener("transitionend", (e) => {
    if (e.propertyName === "transform" && e.target.classList?.contains("in")) {
      e.target.classList.remove("rv", "in");
      e.target.style.transitionDelay = "";
    }
  });
}

function countUp() {
  document.querySelectorAll(".stats b").forEach((b) => {
    const m = b.textContent.match(/[\d.]+/);
    if (!m) return;
    const target = parseFloat(m[0]), dec = (m[0].split(".")[1] || "").length, t0 = performance.now();
    const step = (now) => {
      const p = Math.min(1, Math.max(0, (now - t0) / 1200)), eased = 1 - Math.pow(1 - p, 3);
      b.textContent = b.textContent.replace(/[\d.]+/, (target * eased).toFixed(dec));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

// ---- 4. Current-page highlight in nav, mobile menu close ---------------
function markNav() {
  document.querySelectorAll(".nav a").forEach((a) => {
    if (a.pathname !== "/" && location.pathname.startsWith(a.pathname) && a.origin === location.origin) a.classList.add("here");
  });
  document.querySelectorAll(".nav a").forEach((a) => a.addEventListener("click", () => document.body.classList.remove("nav-open")));
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-filter]").forEach(initFilter);
  markNav();
  if (!reduceMotion) { initReveal(); countUp(); }
});

/* =====================================================================
   LIVE BROADCAST — header badge, site banner, live page auto-switching
   ===================================================================== */
const liveRoot = () => document.getElementById("live-root");

function show(id, on) { const el = document.getElementById(id); if (el) el.hidden = !on; }

// ---- own stream (e.g. Cloudflare Stream → HLS) ----
let hls = null;
function startOwn(url) {
  const v = document.getElementById("own-player");
  if (!v || !url) return;
  stopOwn();
  if (v.canPlayType("application/vnd.apple.mpegurl")) {
    v.src = url;                                   // Safari / iPhone play HLS natively
  } else if (window.Hls && Hls.isSupported()) {
    hls = new Hls({ liveSyncDurationCount: 3, lowLatencyMode: true });
    hls.loadSource(url);
    hls.attachMedia(v);
    hls.on(Hls.Events.ERROR, (_, d) => { if (d.fatal) setTimeout(() => startOwn(url), 3000); });
  } else {
    setTimeout(() => startOwn(url), 500);          // hls.js still loading
    return;
  }
  v.muted = true;                                  // browsers only autoplay muted video
  v.play().catch(() => {});
  document.getElementById("unmute").hidden = false;
}
function stopOwn() {
  if (hls) { hls.destroy(); hls = null; }
  const v = document.getElementById("own-player");
  if (v) { v.removeAttribute("src"); v.load(); }
}
function useOwnLayout(own) {
  show("own-wrap", own);
  show("live-player", !own);
  document.querySelector(".live-grid")?.classList.toggle("no-chat", own);
}

function applyLive(s) {
  // header badge + banner on every page
  document.querySelectorAll(".live-link").forEach((a) => a.classList.toggle("on", s.state === "live"));
  const banner = document.getElementById("live-banner");
  if (banner) banner.hidden = s.state !== "live";

  const root = liveRoot();
  if (!root || s.state === "unknown") return;
  const prev = root.dataset.state, prevVid = root.dataset.video, prevSrc = root.dataset.source;
  root.dataset.state = s.state;
  root.dataset.video = s.video_id || "";
  root.dataset.source = s.source || "youtube";
  root.dataset.hls = s.hls || "";
  show("live-on", s.state === "live");
  show("live-soon", s.state === "upcoming");
  show("live-off", s.state === "offline");
  show("live-state-pill", s.state === "live");

  const own = s.state === "live" && s.source === "own";
  if (own) {
    if (prev !== "live" || prevSrc !== "own") {
      useOwnLayout(true);
      document.getElementById("live-player").src = "about:blank";
      document.getElementById("live-video-title").textContent = "";
      startOwn(s.hls);
    }
    return;
  }
  if (prevSrc === "own") { stopOwn(); useOwnLayout(false); }
  if (s.state === "live" && (prev !== "live" || prevVid !== s.video_id || prevSrc === "own")) {
    // only (re)load the player when the broadcast actually changes — never on every poll
    document.getElementById("live-player").src = `https://www.youtube-nocookie.com/embed/${s.video_id}?autoplay=1&rel=0`;
    document.getElementById("live-chat").src = `https://www.youtube.com/live_chat?v=${s.video_id}&embed_domain=${root.dataset.host}`;
    document.getElementById("live-video-title").textContent = s.title || "";
  }
  if (s.state !== "live" && prev === "live") {
    document.getElementById("live-player").src = "about:blank";  // stop playback when the stream ends
    document.getElementById("live-chat").src = "about:blank";
  }
  if (s.state === "upcoming") {
    root.dataset.starts = s.starts_at || "";
    document.getElementById("soon-title").textContent = s.title || "";
    document.getElementById("remind-link").href = `https://www.youtube.com/watch?v=${s.video_id}`;
  }
}

async function pollLive() {
  if (document.hidden) return;
  try {
    const r = await fetch("/api/live", { cache: "no-store" });
    if (r.ok) applyLive(await r.json());
  } catch { /* offline or server asleep: try again next tick */ }
}

function tickCountdown() {
  const root = liveRoot(), box = document.getElementById("countdown");
  if (!root || !box || root.dataset.state !== "upcoming" || !root.dataset.starts) return;
  let left = Math.max(0, +root.dataset.starts - Date.now() / 1000);
  const parts = { d: Math.floor(left / 86400), h: Math.floor(left % 86400 / 3600), m: Math.floor(left % 3600 / 60), s: Math.floor(left % 60) };
  for (const [u, n] of Object.entries(parts)) box.querySelector(`[data-u=${u}]`).textContent = String(n).padStart(2, "0");
  if (left === 0) pollLive();  // start time reached: check right away
}

document.addEventListener("DOMContentLoaded", () => {
  // live page checks every 20s, other pages every 60s (only while the tab is visible)
  setInterval(pollLive, liveRoot() ? 20000 : 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollLive(); });
  if (liveRoot()) {
    const r = liveRoot();
    if (r.dataset.state === "live" && r.dataset.source === "own") startOwn(r.dataset.hls);
    pollLive(); setInterval(tickCountdown, 1000); tickCountdown();
  }
  document.getElementById("unmute")?.addEventListener("click", (e) => {
    const v = document.getElementById("own-player");
    v.muted = false; v.play().catch(() => {});
    e.currentTarget.hidden = true;
  });

  document.getElementById("copy-link")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    try { await navigator.clipboard.writeText(btn.dataset.url); }
    catch { prompt("", btn.dataset.url); }
    btn.textContent = L.copied;
    setTimeout(() => (btn.textContent = L.copy), 2000);
  });
});
