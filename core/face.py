import subprocess
from pathlib import Path

import cv2
import numpy as np

from .config import MODELS_DIR

YUNET = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
HAAR = MODELS_DIR / "haarcascade_frontalface_default.xml"

SAMPLE_FPS = 3.0
PROC_WIDTH = 480


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
    return w, h


def _detector(width, height):
    if YUNET.exists() and YUNET.stat().st_size > 10000:
        try:
            det = cv2.FaceDetectorYN.create(str(YUNET), "", (width, height), 0.55, 0.3, 5000)
            return ("yunet", det)
        except Exception:
            pass
    return ("haar", cv2.CascadeClassifier(str(HAAR)))


def detect(source, start, end, fps=SAMPLE_FPS, width=PROC_WIDTH):
    sw, sh = probe(source)
    pw = width
    ph = max(2, int(round(width * sh / sw / 2)) * 2)
    duration = max(0.2, end - start)

    cmd = [
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-i", str(source), "-vf", f"fps={fps},scale={pw}:{ph}",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = pw * ph
    kind, det = _detector(pw, ph)
    out = []
    idx = 0

    while True:
        buf = proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(ph, pw)
        box = _largest(kind, det, frame)
        if box is not None:
            x, y, w, h = box
            out.append({
                "t": start + idx / fps,
                "fx": (x + w / 2) / pw,
                "fy": (y + h / 2) / ph,
                "fw": w / pw,
                "fh": h / ph,
            })
        idx += 1

    proc.stdout.close()
    proc.wait()
    return out


def _largest(kind, det, frame):
    if kind == "yunet":
        det.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = det.detect(frame)
        if faces is None or len(faces) == 0:
            return None
        f = max(faces, key=lambda r: r[2] * r[3])
        x, y, w, h = f[:4]
        return float(x), float(y), float(w), float(h)
    faces = det.detectMultiScale(frame, scaleFactor=1.12, minNeighbors=5, minSize=(28, 28))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
    return float(x), float(y), float(w), float(h)


def focus_for_clip(source, start, end):
    dets = detect(source, start, end)
    if not dets:
        return {"fx": 0.5, "fy": 0.40, "fh": 0.26, "found": False, "samples": 0}
    duration = max(0.2, end - start)
    out = {
        "fx": float(np.median([d["fx"] for d in dets])),
        "fy": float(np.median([d["fy"] for d in dets])),
        "fh": float(np.median([d["fh"] for d in dets])),
        "found": True,
        "samples": len(dets),
    }
    track = _track(dets, start, duration)
    if len(track) >= 4:
        out["track"] = track
    return out


def _track(dets, start, duration):
    pts = [(max(0.0, min(duration, d["t"] - start)), d["fx"], d["fy"], d["fh"]) for d in dets]
    if len(pts) < 2:
        return []

    med = []
    for i in range(len(pts)):
        win = pts[max(0, i - 1):i + 2]
        med.append((
            pts[i][0],
            float(np.median([p[1] for p in win])),
            float(np.median([p[2] for p in win])),
            float(np.median([p[3] for p in win])),
        ))

    alpha = 0.62
    sx, sy = med[0][1], med[0][2]
    sm = []
    for t, fx, fy, fh in med:
        sx += (fx - sx) * alpha
        sy += (fy - sy) * alpha
        sm.append((t, sx, sy, fh))

    step = max(0.75, duration / 45)
    ts = [p[0] for p in sm]
    grid = []
    t = 0.0
    while t < duration - 1e-6:
        grid.append(t)
        t += step
    grid.append(duration)

    xs = np.interp(grid, ts, [p[1] for p in sm])
    ys = np.interp(grid, ts, [p[2] for p in sm])
    hs = np.interp(grid, ts, [p[3] for p in sm])
    return [[round(float(g), 3), round(float(x), 4), round(float(y), 4), round(float(h), 4)]
            for g, x, y, h in zip(grid, xs, ys, hs)]
