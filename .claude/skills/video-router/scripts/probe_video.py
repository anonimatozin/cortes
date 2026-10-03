#!/usr/bin/env python3
"""Resume um video com ffprobe: duracao, resolucao, fps, orientacao, audio.

Uso:
    python probe_video.py entrada.mp4              # imprime JSON no terminal
    python probe_video.py entrada.mp4 -o probe.json
"""
import argparse
import json
import shutil
import subprocess
import sys
from fractions import Fraction


def run_ffprobe(path):
    exe = shutil.which("ffprobe")
    if not exe:
        sys.exit("ERRO: ffprobe nao encontrado no PATH. Instale o FFmpeg 'full' (winget install Gyan.FFmpeg).")
    cmd = [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        sys.exit(f"ERRO ao ler o arquivo: {res.stderr.strip()}")
    return json.loads(res.stdout)


def parse_fps(rate):
    try:
        f = Fraction(rate)
        return round(float(f), 3) if f > 0 else None
    except (ValueError, ZeroDivisionError):
        return None


def summarize(path):
    data = run_ffprobe(path)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    out = {
        "file": path,
        "duration_s": round(float(fmt.get("duration", 0) or 0), 3),
        "size_mb": round(int(fmt.get("size", 0) or 0) / 1_048_576, 2),
        "has_video": video is not None,
        "has_audio": audio is not None,
    }
    if video:
        w, h = int(video["width"]), int(video["height"])
        rotation = 0
        for sd in video.get("side_data_list", []) or []:
            if "rotation" in sd:
                rotation = int(sd["rotation"])
        if abs(rotation) in (90, 270):
            w, h = h, w
        out.update({
            "width": w,
            "height": h,
            "orientation": "vertical" if h > w else ("horizontal" if w > h else "quadrado"),
            "aspect": round(w / h, 4),
            "fps": parse_fps(video.get("avg_frame_rate", "0/1")),
            "video_codec": video.get("codec_name"),
            "pix_fmt": video.get("pix_fmt"),
            "rotation": rotation,
        })
    if audio:
        out.update({
            "audio_codec": audio.get("codec_name"),
            "audio_channels": audio.get("channels"),
            "audio_sample_rate": int(audio.get("sample_rate", 0) or 0),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--output", help="salvar JSON neste arquivo")
    args = ap.parse_args()
    info = summarize(args.video)
    text = json.dumps(info, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
