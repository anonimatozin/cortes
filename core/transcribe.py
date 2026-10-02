import json
import subprocess
import tempfile
import time
from pathlib import Path

from .config import GROQ_API_KEY, LANGUAGE, WHISPER_MODEL

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
CHUNK_SEC = 600
CHUNK_BITRATE = "48k"


def _duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or 0)


def _extract(video, start, dur, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "libmp3lame", "-b:a", CHUNK_BITRATE, str(dst)],
        check=True, capture_output=True,
    )


def _groq_chunk(mp3_path, language, attempt=0):
    import requests

    with open(mp3_path, "rb") as fh:
        files = {"file": (Path(mp3_path).name, fh, "audio/mpeg")}
        data = {
            "model": "whisper-large-v3-turbo",
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
        }
        lang = language or LANGUAGE
        if lang and lang != "auto":
            data["language"] = lang
        r = requests.post(
            GROQ_WHISPER_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            data=data, files=files, timeout=600,
        )
    if r.status_code == 429 and attempt < 5:
        time.sleep(5 * (attempt + 1))
        return _groq_chunk(mp3_path, language, attempt + 1)
    if r.status_code != 200:
        raise RuntimeError(f"Groq whisper {r.status_code}: {r.text[:200]}")
    return r.json()


def _transcribe_groq(video_path, language):
    total = _duration(video_path)
    if not total:
        raise RuntimeError("sem duracao")
    init_lang = language or LANGUAGE
    result = {"language": "" if init_lang == "auto" else init_lang, "segments": [], "words": []}

    with tempfile.TemporaryDirectory() as td:
        start = 0.0
        while start < total:
            dur = min(CHUNK_SEC, total - start)
            part = Path(td) / f"c{int(start):06d}.mp3"
            _extract(video_path, start, dur, part)
            data = _groq_chunk(part, language)
            lang = data.get("language") or result["language"]
            if lang:
                result["language"] = "pt" if lang.lower().startswith("portug") else lang
            for w in data.get("words") or []:
                result["words"].append({
                    "start": round(float(w.get("start", 0)) + start, 3),
                    "end": round(float(w.get("end", 0)) + start, 3),
                    "word": w.get("word", ""),
                    "probability": round(float(w.get("confidence", w.get("probability", 0)) or 0), 3),
                })
            for s in data.get("segments") or []:
                result["segments"].append({
                    "start": round(float(s.get("start", 0)) + start, 3),
                    "end": round(float(s.get("end", 0)) + start, 3),
                    "text": (s.get("text") or "").strip(),
                })
            start += dur
            print(f"     transcrito ate {int(start)}s/{int(total)}s", flush=True)

    result["segments"].sort(key=lambda s: s["start"])
    result["words"].sort(key=lambda w: w["start"])
    return result


def _transcribe_local(video_path, language, model_size):
    import av

    _orig_open = av.open

    def _open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_open(*args, **kwargs)

    av.open = _open

    from faster_whisper import WhisperModel

    lang = language or LANGUAGE
    if lang == "auto":
        lang = None

    model = WhisperModel(model_size or WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        video_path,
        language=lang,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )
    result = {"language": info.language, "segments": [], "words": []}
    for seg in segments:
        result["segments"].append(
            {"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()}
        )
        if seg.words:
            for w in seg.words:
                result["words"].append({
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "word": w.word,
                    "probability": round(w.probability, 3),
                })
    return result


def transcribe(video_path, out_path, model_size=None, language=None, backend=None):
    backend = backend or ("groq" if GROQ_API_KEY else "local")
    result = None
    if backend == "groq":
        try:
            result = _transcribe_groq(video_path, language)
            if not result["words"]:
                raise RuntimeError("Groq devolveu vazio")
        except Exception as exc:
            print(f"  [transcriro] Groq falhou ({exc}), indo pro whisper local", flush=True)
            result = None
    if result is None:
        result = _transcribe_local(video_path, language, model_size)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result
