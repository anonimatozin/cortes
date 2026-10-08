import json
import subprocess
import unicodedata
from pathlib import Path

from . import captions
from .config import CLIPS_DIR, FONTS_DIR, TARGET_FACE_H, VIDEO_HEIGHT, VIDEO_WIDTH

ASPECT = VIDEO_WIDTH / VIDEO_HEIGHT


def _probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
    return w, h


def _ff(path):
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _med(vals):
    s = sorted(vals)
    n = len(s)
    return (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0)


def _face_center(track, src_w, src_h, cw, ch):
    mfx = _med([p[1] for p in track])
    mfy = _med([p[2] for p in track])
    cx = min(max(mfx * src_w - cw / 2, 0.0), src_w - cw)
    cy = min(max(mfy * src_h - ch * 0.40, 0.0), src_h - ch)
    fcx = min(max((mfx * src_w - cx) / cw, 0.0), 1.0)
    fcy = min(max((mfy * src_h - cy) / ch, 0.0), 1.0)
    return fcx, fcy


def _lerp(points):
    if not points:
        return "0"
    if len(points) == 1:
        return f"{points[0][1]:.3f}"
    expr = f"{points[-1][1]:.3f}"
    for i in range(len(points) - 2, -1, -1):
        t0, v0 = points[i]
        t1, v1 = points[i + 1]
        span = max(t1 - t0, 1e-6)
        seg = f"{v0:.3f}+({v1 - v0:.3f})*(t-{t0:.3f})/{span:.3f}"
        expr = f"if(lt(t,{t0:.3f}),{v0:.3f},if(lt(t,{t1:.3f}),{seg},{expr}))"
    return expr


def _base_chain(src_w, src_h, reframe, duration, punch_sec=0.5, push=0.06, manual_focus=0.5, zoom=1.0):
    if not reframe:
        cw = int(min(src_w, src_h * ASPECT) // 2 * 2)
        cx = int((src_w - cw) * manual_focus)
        frames = max(30, int(duration * 30))
        pk = max(6, int(punch_sec * 30))
        kk = max(1.0, float(zoom))
        e = f"min(in/{pk},1)"
        ease = f"{e}*{e}*(3-2*{e})"
        z = (
            f"if(lt(in,{pk}),1+({kk:.5f}-1)*{ease},"
            f"{kk:.5f}*(1-{push}*min(max((in-{pk})/{frames - pk},0),1)))"
        )
        zx = "min(max(0.5*iw-iw/zoom/2,0),iw-iw/zoom)"
        zy = "min(max(0.5*ih-ih/zoom*0.40,0),ih-ih/zoom)"
        mid_w, mid_h = VIDEO_WIDTH * 3 // 2, VIDEO_HEIGHT * 3 // 2
        return (
            f"[0:v]crop={cw}:{src_h}:{cx}:0,fps=30,"
            f"scale={mid_w}:{mid_h}:flags=lanczos,"
            f"zoompan=z='{z}':d=1:x='{zx}':y='{zy}':s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps=30,"
            f"format=rgba[v0]"
        )

    fx, fy, fh = reframe["fx"], reframe["fy"], reframe["fh"]
    track = reframe.get("track") or []
    use_track = len(track) >= 4
    fh_ref = fh
    if use_track:
        fhs = sorted(p[3] for p in track)
        fh_ref = fhs[int((len(fhs) - 1) * 0.7)]
    bh_base = min(fh_ref / TARGET_FACE_H, 1.0) * src_h
    bw_base = bh_base * ASPECT
    if bw_base > src_w:
        bw_base = float(src_w)
        bh_base = bw_base / ASPECT
    kmax = max(1.0, min(src_w / bw_base, src_h / bh_base))
    kmax = min(kmax * max(1.0, float(zoom)), max(1.0, float(zoom)) * 2.2)

    cw = int(round(bw_base * kmax))
    ch = int(round(bh_base * kmax))
    cw = min(cw, src_w)
    ch = min(ch, src_h)

    if use_track:
        pts_x, pts_y = [], []
        for t, tfx, tfy, _ in track:
            pts_x.append((float(t), min(max(tfx * src_w - cw / 2, 0.0), src_w - cw)))
            pts_y.append((float(t), min(max(tfy * src_h - ch * 0.40, 0.0), src_h - ch)))
        crop_xy = f":x='{_lerp(pts_x)}':y='{_lerp(pts_y)}'"
        fcx, fcy = _face_center(track, src_w, src_h, cw, ch)
    else:
        cx = int(round(min(max(fx * src_w - cw / 2, 0), src_w - cw)))
        cy = int(round(min(max(fy * src_h - ch * 0.40, 0), src_h - ch)))
        crop_xy = f":{cx}:{cy}"
        fcx = min(max((fx * src_w - cx) / cw, 0.0), 1.0)
        fcy = min(max((fy * src_h - cy) / ch, 0.0), 1.0)

    frames = max(30, int(duration * 30))
    pn = max(6, int(punch_sec * 30))
    dn = max(pn + 10, frames)

    e = f"min(in/{pn},1)"
    ease = f"{e}*{e}*(3-2*{e})"
    z = (
        f"if(lt(in,{pn}),1+({kmax:.5f}-1)*{ease},"
        f"{kmax:.5f}*(1-{push}*min(max((in-{pn})/{dn - pn},0),1)))"
    )
    zx = f"min(max({fcx:.5f}*iw-iw/zoom/2,0),iw-iw/zoom)"
    zy = f"min(max({fcy:.5f}*ih-ih/zoom*0.40,0),ih-ih/zoom)"

    mid_w = VIDEO_WIDTH * 3 // 2
    mid_h = VIDEO_HEIGHT * 3 // 2
    return (
        f"[0:v]crop={cw}:{ch}{crop_xy},fps=30,"
        f"scale={mid_w}:{mid_h}:flags=lanczos,"
        f"zoompan=z='{z}':d=1:x='{zx}':y='{zy}':s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps=30,"
        f"format=rgba[v0]"
    )


def _overlay_expr(ov, pad=70):
    pos = ov.get("pos", "right")
    if pos == "left":
        x, y = f"{pad}", "(H-h)/2"
    elif pos == "top":
        x, y = "(W-w)/2", "H*0.13"
    elif pos == "bottom":
        x, y = "(W-w)/2", "H-h-H*0.26"
    else:
        x, y = f"W-w-{pad}", "(H-h)/2"
    s, e = ov["start"], ov["end"]
    return (
        f"overlay=x='{x}':y='{y}':enable='between(t,{s:.3f},{e:.3f})'"
        f":eof_action=repeat"
    )


def _filter_chain(ass_path, base_chain, overlays):
    parts = [base_chain]
    prev = "v0"
    for i, ov in enumerate(overlays, start=1):
        src = f"o{i}"
        parts.append(f"[{i}:v]format=rgba,setpts=PTS+{ov['start']:.3f}/TB[{src}]")
        parts.append(f"[{prev}][{src}]{_overlay_expr(ov)}[v{i}]")
        prev = f"v{i}"

    parts.append(
        f"[{prev}]format=yuv420p,"
        f"subtitles='{_ff(ass_path)}':fontsdir='{_ff(FONTS_DIR)}'[vout]"
    )
    parts.append("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    return ";".join(parts)


def render_clip(source, start, end, out_path, words, hook="", crop_focus=0.5,
                reframe=None, overlays=None, zoom=1.0, push=0.06, caption_size=None):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.5, end - start)
    overlays = overlays or []

    ass_path = out_path.with_suffix(".ass")
    ass_path.write_text(
        captions.build(words, start, end, hook=hook, size=caption_size), encoding="utf-8"
    )

    crop_filter = _base_chain(*_probe(source), reframe, duration,
                              manual_focus=crop_focus, zoom=zoom, push=push)
    chain = _filter_chain(ass_path, crop_filter, overlays)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}",
        "-i", str(source),
    ]
    for ov in overlays:
        cmd += ["-framerate", "30", "-i", str(ov["pattern"])]
    cmd += [
        "-filter_complex", chain,
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {proc.stderr[-1500:]}")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out_path)],
        capture_output=True, text=True,
    )
    return {
        "path": str(out_path),
        "duration": round(float(probe.stdout.strip() or duration), 2),
        "size": out_path.stat().st_size,
        "ass": str(ass_path),
    }


def clip_filename(index, slug, source_id=""):
    ascii_slug = unicodedata.normalize("NFKD", slug or "").encode("ascii", "ignore").decode("ascii")
    words = [w for w in ascii_slug.upper().split() if w][:7]
    safe = "".join(c for c in "_".join(words) if c.isalnum() or c in "-_").strip("-_")
    prefix = f"{source_id}_" if source_id else ""
    return CLIPS_DIR / f"{index:02d}_{prefix}{safe[:60] or 'clip'}.mp4"


def write_sidecar(out_path, data):
    Path(out_path).with_suffix(".json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )
