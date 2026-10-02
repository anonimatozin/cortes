import base64
import json
import math
import shutil
from pathlib import Path

from .config import CLIPS_DIR, GROQ_API_KEY, GROQ_MODEL, IMAGE_MODEL, IMAGE_PROVIDER, IMAGE_STYLE, LANGUAGE
from .select import _chat, _extract_json

FPS = 30
MAX_W = 620
MAX_H = 620

PLAN_SCHEMA = """{
  "visuals": [
    {
      "rel": 12.0,
      "prompt": "descricao visual em ingles, sem texto na imagem",
      "pos": "right",
      "dur": 3.5
    }
  ]
}"""


def plan_visuals(text, duration, hook, max_n=2):
    if not GROQ_API_KEY:
        return []
    if duration < 12:
        return []
    user = (
        f"Trecho de video ({duration:.0f}s) para virar um Short vertical.\n"
        f"Trecho: {text[:1800]}\n\n"
        "Escolha ate 2 momentos onde uma IMAGEM ilustraria o que esta sendo falado "
        "e prende a atencao. Cada um deve durar 2.5 a 4.5 segundos e comecar entre "
        "2s e " + f"{max(6.0, duration - 6):.0f}s. pos deve ser left, right ou top. "
        "prompt em ingles, descricao concreta e visual, estilo: " + IMAGE_STYLE + ". Sem texto, sem letras, sem legenda na imagem."
    )
    try:
        content = _chat({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Voce dirige o design visual de Shorts. Responda so em JSON valido."},
                {"role": "user", "content": user},
                {"role": "system", "content": PLAN_SCHEMA},
            ],
            "temperature": 0.6,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        })
        data = _extract_json(content)
    except Exception:
        return []
    out = []
    for v in data.get("visuals", [])[:max_n]:
        try:
            rel = float(v.get("rel", 0))
            dur = float(v.get("dur", 3.2))
        except (TypeError, ValueError):
            continue
        pos = str(v.get("pos", "right")).lower()
        if pos not in ("left", "right", "top"):
            pos = "right"
        rel = min(max(rel, 1.5), max(2.0, duration - dur - 1.0))
        out.append({
            "rel": round(rel, 2),
            "prompt": str(v.get("prompt", ""))[:400],
            "pos": pos,
            "dur": round(min(max(dur, 2.0), 5.0), 2),
        })
    return out


def generate(prompt, out_path, size=(1024, 1024)):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if IMAGE_PROVIDER == "gemini":
        return _gemini(prompt, out_path, size)
    raise RuntimeError(f"IMAGE_PROVIDER={IMAGE_PROVIDER} nao suportado (configure .env)")


def _gemini(prompt, out_path, size):
    import requests

    from .config import GEMINI_API_KEY

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY vazia no .env (imagem de IA desativada)")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{IMAGE_MODEL}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt + ". No text, no letters, no watermark."}]}]}
    r = requests.post(url, params={"key": GEMINI_API_KEY}, json=body, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"imagem falhou {r.status_code}: {r.text[:300]}")
    parts = r.json()["candidates"][0]["content"]["parts"]
    for p in parts:
        if p.get("inlineData") or p.get("inline_data"):
            data = (p.get("inlineData") or p.get("inline_data"))["data"]
            out_path.write_bytes(base64.b64decode(data))
            return out_path
    raise RuntimeError(f"resposta sem imagem: {json.dumps(parts)[:300]}")


def _ease_out(p):
    return 1 - (1 - p) ** 3


def animate(img_path, out_dir, duration, pos, canvas_pad=1.18):
    from PIL import Image

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    src = Image.open(img_path).convert("RGBA")
    scale = min(MAX_W / src.width, MAX_H / src.height, 1.0)
    w, h = max(8, int(src.width * scale)), max(8, int(src.height * scale))
    cw, ch = int(w * canvas_pad), int(h * canvas_pad)
    cw += cw % 2
    ch += ch % 2

    base = src.resize((w, h), Image.LANCZOS)
    frames = max(6, int(round(duration * FPS)))
    in_f = int(round(0.45 * FPS))
    out_f = int(round(0.30 * FPS))
    out_start = max(in_f + 1, frames - out_f)

    for i in range(frames):
        p_in = min(1.0, i / max(1, in_f))
        if p_in < 1.0:
            s = 0.55 + (_ease_out(p_in) * 0.53)
            alpha = p_in
        else:
            s, alpha = 1.08 if i < in_f + 4 else 1.0, 1.0
        if i >= out_start:
            q = (i - out_start) / max(1, frames - out_start)
            alpha *= max(0.0, 1 - q)
            s *= 1 - 0.05 * q

        float_y = math.sin((i / FPS) * 2.1) * 5 if p_in >= 1.0 else 0.0
        nw, nh = max(2, int(w * s)), max(2, int(h * s))
        layer = base.resize((nw, nh), Image.LANCZOS)
        if alpha < 0.999:
            a = layer.getchannel("A").point(lambda v, a=alpha: int(v * a))
            layer.putalpha(a)

        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        x = (cw - nw) // 2
        y = int((ch - nh) // 2 + float_y)
        canvas.alpha_composite(layer, (max(0, x), max(0, y)))
        canvas.save(out_dir / f"f{i:04d}.png", optimize=False)

    return {"pattern": str(out_dir / "f%04d.png"), "frames": frames, "size": (cw, ch)}


def prepare(clip_index, clip_dir, visuals):
    assets = CLIPS_DIR / "assets" / f"clip_{clip_index}"
    assets.mkdir(parents=True, exist_ok=True)
    out = []
    for i, v in enumerate(visuals, start=1):
        if not v.get("prompt"):
            continue
        img = assets / f"v{i}.png"
        seq = assets / f"seq{i}"
        try:
            if not img.exists():
                generate(v["prompt"], img)
            anim = animate(img, seq, v["dur"], v["pos"])
        except Exception as exc:
            print(f"  [visual {i}] pulou: {exc}", flush=True)
            continue
        out.append({
            "pattern": anim["pattern"],
            "start": v["rel"],
            "end": v["rel"] + v["dur"],
            "pos": v["pos"],
            "dur": v["dur"],
            "prompt": v["prompt"],
            "image": str(img),
        })
    return out
