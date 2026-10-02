import json

from .config import SOURCE_DIR


def download(url):
    import yt_dlp

    out_tmpl = str(SOURCE_DIR / "%(id)s.%(ext)s")
    opts = {
        "outtmpl": out_tmpl,
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "writethumbnail": False,
        "progress": False,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        if not path.endswith(".mp4") and info.get("ext") == "mp4":
            path = str(SOURCE_DIR / f"{info['id']}.mp4")

    meta = {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration": info.get("duration"),
        "url": url,
        "webpage_url": info.get("webpage_url") or url,
        "path": path,
        "tags": info.get("tags") or [],
    }
    (SOURCE_DIR / f"{meta['id']}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return meta
