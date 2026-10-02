import subprocess

import numpy as np

from .config import MAX_CLIP_SEC, MIN_CLIP_SEC, TARGET_CLIP_SEC

SR = 16000
WIN = 0.5


def envelope(path):
    cmd = [
        "ffmpeg", "-v", "error", "-i", path,
        "-ac", "1", "-ar", str(SR), "-f", "s16le", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = int(WIN * SR) * 2
    acc = []
    raw = b""
    while True:
        chunk = proc.stdout.read(n)
        if not chunk:
            break
        raw += chunk
        if len(raw) >= n:
            take = (len(raw) // n) * n
            block = np.frombuffer(raw[:take], np.int16).astype(np.float32) / 32768.0
            raw = raw[take:]
            frames = block.reshape(-1, int(WIN * SR))
            acc.append(np.sqrt((frames ** 2).mean(axis=1)))
    proc.wait()
    if raw:
        block = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
        acc.append(np.array([np.sqrt((block ** 2).mean())]))
    if not acc:
        return np.zeros(1, dtype=np.float32)
    return np.concatenate(acc)


def energy_at(rms, t):
    i = int(t / WIN)
    if i < 0 or i >= len(rms):
        return 0.0
    return float(rms[i])


def build_candidates(words, segments, rms, duration, target=None, cap=60):
    target = target or TARGET_CLIP_SEC
    if not segments:
        return []

    cands = []
    used = set()
    i = 0
    while i < len(segments) and len(cands) < cap:
        start = segments[i]["start"]
        end = start
        j = i
        while j < len(segments) and end - start < target:
            j += 1
            if j < len(segments):
                end = segments[j]["end"]
        if end - start > duration:
            break
        if MIN_CLIP_SEC <= end - start <= MAX_CLIP_SEC * 1.35:
            key = round(start / 4)
            if key not in used:
                used.add(key)
                cands.append({"start": start, "end": end})
        limit_start = start + target * 0.45
        k = i + 1
        while k < len(segments) and segments[k]["start"] < limit_start:
            k += 1
        i = k if k > i else i + 1

    if not cands:
        cands = [{"start": 0.0, "end": min(duration, target)}]

    for c in cands:
        seg_text = [
            s["text"] for s in segments if s["end"] > c["start"] and s["start"] < c["end"]
        ]
        c["text"] = " ".join(seg_text).strip()
        lo, hi = int(c["start"] / WIN), min(int(c["end"] / WIN) + 1, len(rms))
        window = rms[lo:hi] if hi > lo else np.zeros(1)
        c["energy"] = float(np.percentile(window, 90)) if len(window) else 0.0
        c["peak"] = float(window.max()) if len(window) else 0.0
        c["excite"] = _excite_score(c["text"])

    return cands


def _excite_score(text):
    t = text.lower()
    score = 0.0
    for token, val in (
        ("!", 1.0), ("?", 0.4), ("ahhh", 1.5), ("hahaha", 1.5),
        ("caraca", 1.2), ("não acredito", 1.8), ("maluco", 1.0),
        ("insano", 1.5), ("mitou", 1.2), ("zeus", 0.6), ("grito", 1.0),
        ("morri", 1.2), ("que porra", 1.0), ("meu deus", 1.5),
        ("no way", 1.5), ("let's go", 1.0), ("no fucking", 1.5),
    ):
        score += t.count(token) * val
    return round(score, 2)


def rank_candidates(cands, top=40):
    if not cands:
        return []
    energies = [c["energy"] for c in cands]
    base = np.percentile(energies, 75) or 1.0
    for c in cands:
        dur = max(1.0, c["end"] - c["start"])
        c["pre_score"] = round(
            (c["energy"] / base) * 2.0
            + c["excite"]
            + (2.0 if MIN_CLIP_SEC <= dur <= MAX_CLIP_SEC else 0.0)
            + (1.0 if len(c["text"]) > 120 else 0.0),
            3,
        )
    ordered = sorted(cands, key=lambda c: c["pre_score"], reverse=True)
    picked = ordered[:top]
    return sorted(picked, key=lambda c: c["start"])
