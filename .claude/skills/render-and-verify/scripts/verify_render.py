#!/usr/bin/env python3
"""Checa tecnicamente um video final (ffprobe + ffmpeg). Sai com codigo 1 se algo reprovar.

Verifica: resolucao, fps, duracao, codecs (h264/aac), pix_fmt yuv420p, presenca de audio,
loudness integrado (LUFS), pico, frames pretos e imagem congelada nos primeiros segundos.

Uso:
    python verify_render.py clipe.mp4
    python verify_render.py clipe.mp4 --width 1080 --height 1920 --fps 30 --min-dur 15 --max-dur 59
    python verify_render.py clipe.mp4 --json relatorio.json
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from fractions import Fraction


def need(tool):
    exe = shutil.which(tool)
    if not exe:
        sys.exit(f"ERRO: {tool} nao encontrado no PATH.")
    return exe


def probe(path):
    res = subprocess.run([need("ffprobe"), "-v", "error", "-print_format", "json",
                          "-show_format", "-show_streams", path],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        sys.exit(f"Arquivo ilegivel: {res.stderr.strip()}")
    return json.loads(res.stdout)


def ffmpeg_stderr(args):
    res = subprocess.run([need("ffmpeg"), "-hide_banner", "-nostats", *args],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return res.stderr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--min-dur", type=float, default=5.0)
    ap.add_argument("--max-dur", type=float, default=180.0)
    ap.add_argument("--lufs-min", type=float, default=-17.0)
    ap.add_argument("--lufs-max", type=float, default=-11.0)
    ap.add_argument("--peak-max", type=float, default=-0.5, help="pico maximo em dBTP")
    ap.add_argument("--head", type=float, default=5.0, help="janela inicial analisada (s)")
    ap.add_argument("--json", help="salvar relatorio neste arquivo")
    args = ap.parse_args()

    data = probe(args.video)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    dur = float(data["format"].get("duration", 0) or 0)
    checks = []

    def add(name, ok, detail, warn=False):
        checks.append({"check": name, "status": "OK" if ok else ("AVISO" if warn else "FALHA"), "detail": detail})

    if not v:
        add("video", False, "sem stream de video")
    else:
        w, h = int(v["width"]), int(v["height"])
        add("resolucao", (w, h) == (args.width, args.height), f"{w}x{h} (esperado {args.width}x{args.height})")
        try:
            fps = float(Fraction(v.get("avg_frame_rate", "0/1")))
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        add("fps", abs(fps - args.fps) < 0.6, f"{fps:.2f} (esperado {args.fps})", warn=True)
        add("codec_video", v.get("codec_name") == "h264", str(v.get("codec_name")), warn=True)
        add("pix_fmt", v.get("pix_fmt") == "yuv420p", str(v.get("pix_fmt")) + " (yuv420p toca em qualquer celular)", warn=True)
    add("duracao", args.min_dur <= dur <= args.max_dur, f"{dur:.2f}s (faixa {args.min_dur}-{args.max_dur}s)")

    if not a:
        add("audio", False, "sem stream de audio")
    else:
        add("codec_audio", a.get("codec_name") == "aac", str(a.get("codec_name")), warn=True)
        err = ffmpeg_stderr(["-i", args.video, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
        summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""
        lufs = re.search(r"I:\s+(-?[\d.]+)\s+LUFS", summary)
        peak = re.search(r"Peak:\s+(-?[\d.]+)\s+dBFS", summary)
        if lufs:
            val = float(lufs.group(1))
            add("loudness", args.lufs_min <= val <= args.lufs_max, f"{val} LUFS (faixa {args.lufs_min} a {args.lufs_max})", warn=True)
        else:
            add("loudness", False, "nao foi possivel medir (audio vazio?)", warn=True)
        if peak:
            val = float(peak.group(1))
            add("pico", val <= args.peak_max, f"{val} dBFS (maximo {args.peak_max})", warn=True)

    if v:
        window = min(args.head, dur)
        err = ffmpeg_stderr(["-t", str(window), "-i", args.video, "-an",
                             "-vf", "blackdetect=d=0.3:pix_th=0.10,freezedetect=n=-60dB:d=2", "-f", "null", "-"])
        blacks = re.findall(r"black_start:([\d.]+)", err)
        freezes = re.findall(r"freeze_start: ([\d.]+)", err)
        add("preto_no_inicio", not blacks, f"preto a partir de {blacks[0]}s" if blacks else f"sem preto nos primeiros {window:.0f}s", warn=True)
        add("imagem_congelada_no_inicio", not freezes,
            f"imagem parada a partir de {freezes[0]}s (hook estatico?)" if freezes else f"movimento ok nos primeiros {window:.0f}s", warn=True)

    failed = [c for c in checks if c["status"] == "FALHA"]
    warns = [c for c in checks if c["status"] == "AVISO"]
    for c in checks:
        print(f"[{c['status']:<5}] {c['check']:<28} {c['detail']}")
    print(f"\nResultado: {'REPROVADO' if failed else 'APROVADO'} | {len(failed)} falha(s), {len(warns)} aviso(s)")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"file": args.video, "passed": not failed, "checks": checks}, f, indent=2, ensure_ascii=False)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
