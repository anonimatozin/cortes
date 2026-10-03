#!/usr/bin/env python3
"""Confere o ambiente do editor de video: Python, FFmpeg, libass, NVENC e pacotes opcionais.

Uso: python scripts/doctor.py
"""
import importlib.util
import shutil
import subprocess
import sys


def run(cmd):
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return res.returncode, (res.stdout or "") + (res.stderr or "")
    except FileNotFoundError:
        return 127, ""


def line(status, name, detail=""):
    print(f"[{status:<5}] {name:<24} {detail}")


def main():
    problems = 0
    v = sys.version_info
    ok = (3, 10) <= (v.major, v.minor) <= (3, 12)
    line("OK" if ok else "AVISO", "python", f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else " (MediaPipe pede 3.10-3.12)"))

    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            line("OK", tool, path)
        else:
            line("FALHA", tool, "nao encontrado. Instale: winget install Gyan.FFmpeg (build full)")
            problems += 1

    if shutil.which("ffmpeg"):
        _, out = run(["ffmpeg", "-hide_banner", "-filters"])
        for flt in ("ass", "subtitles", "sidechaincompress", "loudnorm", "silencedetect"):
            has = any(f" {flt} " in ln for ln in out.splitlines())
            line("OK" if has else "FALHA", f"filtro {flt}", "" if has else "build sem esse filtro (use a build full)")
            problems += 0 if has else 1
        code, _ = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                       "color=c=black:s=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"])
        line("OK" if code == 0 else "INFO", "NVENC (GPU)", "disponivel" if code == 0 else "indisponivel -> usar libx264")

    for mod, why in (("faster_whisper", "transcricao (recomendado)"), ("whisperx", "transcricao com alinhamento"),
                     ("cv2", "OpenCV (rastrear rosto)"), ("mediapipe", "deteccao de rosto"),
                     ("scenedetect", "cortes de cena")):
        has = importlib.util.find_spec(mod) is not None
        line("OK" if has else "INFO", mod, why if has else f"nao instalado - {why}")

    for tool, why in (("node", "Remotion (opcional)"),):
        path = shutil.which(tool)
        line("OK" if path else "INFO", tool, path or f"nao encontrado - {why}")

    print("\nAmbiente OK para o basico." if problems == 0 else f"\n{problems} problema(s) acima precisam ser resolvidos.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
