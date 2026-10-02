import json
import re
import subprocess

from .config import RESEARCH_CACHE, RESEARCH_LIMIT

_cache = None


def _load_cache():
    global _cache
    if _cache is None:
        if RESEARCH_CACHE.exists():
            try:
                _cache = json.loads(RESEARCH_CACHE.read_text(encoding="utf-8"))
            except Exception:
                _cache = {}
        else:
            _cache = {}
    return _cache


def _save_cache():
    if _cache is not None:
        RESEARCH_CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _search(query, limit):
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    entries = (info or {}).get("entries") or []
    return [e.get("title") for e in entries if e.get("title")]


def related_titles(query, limit=None):
    limit = limit or RESEARCH_LIMIT
    if not query:
        return []
    cache = _load_cache()
    key = f"{query.lower()}|{limit}"
    if key in cache:
        return cache[key]
    try:
        titles = _search(query, limit)
    except Exception:
        titles = []
    cache[key] = titles
    _save_cache()
    return titles


def probe_video(url):
    try:
        r = subprocess.run(
            ["yt-dlp", "--skip-download", "--dump-json", "--no-warnings", "--no-playlist", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        if r.returncode != 0:
            return {}
        info = json.loads(r.stdout.splitlines()[0])
    except Exception:
        return {}
    return {
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "url": info.get("webpage_url") or url,
        "tags": [str(t) for t in (info.get("tags") or [])][:25],
        "category": info.get("category") or "",
        "description": (info.get("description") or "")[:600],
    }


def build_context(meta):
    query = (meta.get("title") or meta.get("channel") or "").split("|")[0][:70].strip()
    titles = related_titles(query) if query else []
    return {
        "title": meta.get("title", ""),
        "channel": meta.get("channel", ""),
        "url": meta.get("webpage_url") or meta.get("url", ""),
        "tags": meta.get("tags") or [],
        "related": titles,
    }


_HASHTAG = re.compile(r"^#[A-Za-z0-9_À-ÿ]+$")


def clean_hashtags(tags, max_n=5):
    out = []
    for t in tags or []:
        t = str(t).strip().replace(" ", "")
        if not t.startswith("#"):
            t = "#" + t
        t = t[:32]
        if _HASHTAG.match(t) and t.lower() not in {h.lower() for h in out}:
            out.append(t)
        if len(out) >= max_n:
            break
    return out


def clean_tags(tags, max_n=18):
    out, seen = [], set()
    for t in tags or []:
        t = str(t).strip()[:45]
        if not t or " " in t and len(t) > 30:
            continue
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= max_n:
            break
    return out


def credit_block(ctx, style="full"):
    channel = (ctx.get("channel") or "").strip()
    title = (ctx.get("title") or "").strip()
    url = (ctx.get("url") or "").strip()
    if not channel and not title:
        return ""
    if style == "channel":
        return f"\n\nCréditos: {channel}" if channel else ""
    line = f"Créditos: {channel}" if channel else "Créditos"
    if title:
        line += f' — "{title}"'
    if url:
        line += f"\n{url}"
    return "\n\n" + line
