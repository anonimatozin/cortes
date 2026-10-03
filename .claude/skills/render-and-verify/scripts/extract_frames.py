#!/usr/bin/env python3
"""Extrai frames de um video em JPG para o Claude INSPECIONAR visualmente (ver imagem).

Por padrao pega os primeiros 5 s com frequencia alta (onde mora o hook) e depois
meio e fim do video.

Uso:
    python extract_frames.py clipe.mp4 -o frames/
    python extract_frames.py clipe.mp4 -o frames/ --times 0 0.3 0.8 1.5 3 5 12
"""
import argparse
import os
import shutil
import subprocess
import sys


def need(tool):
    exe = shutil.which(tool)
    if not exe:
        sys.exit(f"ERRO: {tool} nao encontrado no PATH.")
    return exe


def duration(path):
    res = subprocess.run([need("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(res.stdout.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("-o", "--outdir", default="frames")
    ap.add_argument("--times", type=float, nargs="*", help="instantes (s) a extrair")
    ap.add_argument("--width", type=int, default=540, help="largura da miniatura (padrao 540)")
    args = ap.parse_args()

    dur = duration(args.video)
    if args.times:
        times = args.times
    else:
        times = [0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, dur / 2, max(0.0, dur - 0.3)]
    times = sorted({round(min(max(0.0, t), max(0.0, dur - 0.05)), 2) for t in times})

    os.makedirs(args.outdir, exist_ok=True)
    made = []
    for t in times:
        out = os.path.join(args.outdir, f"t{t:07.2f}s.jpg")
        res = subprocess.run([need("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
                              "-ss", str(t), "-i", args.video, "-frames:v", "1",
                              "-vf", f"scale={args.width}:-2", "-q:v", "3", out],
                             capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(out):
            made.append(out)
        else:
            print(f"aviso: falhou em t={t}s: {res.stderr.strip()}", file=sys.stderr)
    print(f"{len(made)} frames em {args.outdir}/")
    for m in made:
        print(m)


if __name__ == "__main__":
    main()
