#!/usr/bin/env python3
"""Detecta silencios com FFmpeg e gera a lista de trechos a MANTER (jump cuts).

Uso:
    python detect_silence.py entrada.mp4 -o cuts.json
    python detect_silence.py entrada.mp4 -o cuts.json --noise -32 --min-silence 0.45 --pad 0.08
    python detect_silence.py entrada.mp4 -o cuts.json --render saida_sem_silencio.mp4

O JSON tem: duration, silences[], keep[] (trechos a manter, em segundos).
--pad deixa um respiro (segundos) de cada lado da fala para o corte nao ficar seco.
--render monta um MP4 so com os trechos mantidos (re-encoda com libx264/aac).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


def need(tool):
    exe = shutil.which(tool)
    if not exe:
        sys.exit(f"ERRO: {tool} nao encontrado no PATH.")
    return exe


def get_duration(path):
    res = subprocess.run(
        [need("ffprobe"), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        sys.exit(f"ERRO: nao consegui ler a duracao de {path}")


def detect(path, noise_db, min_silence):
    cmd = [need("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-vn",
           "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", res.stderr)]
    silences = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        silences.append({"start": max(0.0, s), "end": e})
    return silences


def build_keep(silences, duration, pad, min_keep):
    keep, cursor = [], 0.0
    for s in silences:
        s_start = s["start"]
        s_end = s["end"] if s["end"] is not None else duration
        seg_start, seg_end = cursor, min(duration, s_start + pad)
        if seg_end - seg_start >= min_keep:
            keep.append([seg_start, seg_end])
        cursor = max(cursor, s_end - pad)
    if duration - cursor >= min_keep:
        keep.append([cursor, duration])
    merged = []
    for a, b in keep:
        if merged and a <= merged[-1][1] + 0.001:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [{"start": round(a, 3), "end": round(b, 3)} for a, b in merged]


def has_audio_stream(path):
    res = subprocess.run(
        [need("ffprobe"), "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(res.stdout.strip())


def render(path, keep, out_path, fade=0.02):
    """Concatena os trechos com filter_complex_script (evita limite de linha do Windows)."""
    audio = has_audio_stream(path)
    lines = []
    for i, k in enumerate(keep):
        lines.append(f"[0:v]trim=start={k['start']}:end={k['end']},setpts=PTS-STARTPTS[v{i}];")
        if audio:
            dur = k["end"] - k["start"]
            f = min(fade, dur / 4)
            lines.append(
                f"[0:a]atrim=start={k['start']}:end={k['end']},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={f:.3f},afade=t=out:st={max(0, dur - f):.3f}:d={f:.3f}[a{i}];")
    n = len(keep)
    if audio:
        joined = "".join(f"[v{i}][a{i}]" for i in range(n))
        lines.append(f"{joined}concat=n={n}:v=1:a=1[outv][outa]")
        maps = ["-map", "[outv]", "-map", "[outa]", "-c:a", "aac", "-b:a", "192k"]
    else:
        joined = "".join(f"[v{i}]" for i in range(n))
        lines.append(f"{joined}concat=n={n}:v=1:a=0[outv]")
        maps = ["-map", "[outv]"]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write("\n".join(lines))
        script = tf.name
    try:
        cmd = [need("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-i", path,
               "-filter_complex_script", script, *maps,
               "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", out_path]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0:
            sys.exit(f"ERRO no render:\n{res.stderr}")
    finally:
        os.unlink(script)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--output", default="cuts.json")
    ap.add_argument("--noise", type=float, default=-35.0, help="limiar em dB (padrao -35)")
    ap.add_argument("--min-silence", type=float, default=0.4, help="pausa minima em s (padrao 0.4)")
    ap.add_argument("--pad", type=float, default=0.08, help="respiro em s ao redor da fala (padrao 0.08)")
    ap.add_argument("--min-keep", type=float, default=0.25, help="descarta trechos menores que isso")
    ap.add_argument("--render", help="se informado, gera este MP4 sem os silencios")
    args = ap.parse_args()

    duration = get_duration(args.video)
    silences = detect(args.video, args.noise, args.min_silence)
    keep = build_keep(silences, duration, args.pad, args.min_keep)
    kept = sum(k["end"] - k["start"] for k in keep)
    result = {
        "source": args.video,
        "duration": round(duration, 3),
        "params": {"noise_db": args.noise, "min_silence": args.min_silence, "pad": args.pad},
        "silences": silences,
        "keep": keep,
        "kept_seconds": round(kept, 3),
        "removed_seconds": round(duration - kept, 3),
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"{len(silences)} silencios | mantidos {kept:.1f}s de {duration:.1f}s | {args.output}")
    if args.render:
        if not keep:
            sys.exit("Nada para manter; ajuste --noise.")
        render(args.video, keep, args.render)
        print(f"Render: {args.render}")


if __name__ == "__main__":
    main()
