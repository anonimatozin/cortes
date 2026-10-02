import json
import re
from pathlib import Path

from .config import BRAND, GROQ_MODEL, SOURCE_DIR, VIDEO_HEIGHT, VIDEO_WIDTH

CAP_FONT = "Anton"
PRIMARY = "&H0000FFFF"
SECONDARY = "&H00FFFFFF"
OUTLINE_C = "&H00000000"

PER_LINE = 16
MAX_LINES = 2


def _ts(t):
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _header(cap_size=76):
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    return [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {w}",
        f"PlayResY: {h}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{CAP_FONT},{cap_size},{PRIMARY},{SECONDARY},{OUTLINE_C},&H80000000,-1,0,0,0,100,100,1,0,1,8,3,2,55,55,470,1",
        f"Style: Hook,{CAP_FONT},84,&H0000FFFF,&H00FFFFFF,{OUTLINE_C},&H80000000,-1,0,0,0,100,100,0,0,1,7,3,8,45,45,300,1",
        f"Style: Brand,{CAP_FONT},38,{PRIMARY},&H0000FFFF,{OUTLINE_C},&H80000000,-1,0,0,0,100,100,3,0,1,4,0,7,55,55,130,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def _esc(t):
    return t.replace("{", "(").replace("}", ")").replace("\n", " ")


def _clean(word):
    return re.sub(r"\s+", " ", word).strip() or " "


def group_words(words, start, end, max_chars=26, max_dur=2.6, max_gap=0.6, max_words=4):
    inside = [w for w in words if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]
    inside.sort(key=lambda w: w["start"])
    groups, cur = [], []
    for w in inside:
        if not cur:
            cur = [w]
            continue
        text = "".join(x["word"] for x in cur) + w["word"]
        gap = w["start"] - cur[-1]["end"]
        dur = w["end"] - cur[0]["start"]
        if gap > max_gap or len(cur) >= max_words or len(text.strip()) > max_chars or dur > max_dur:
            groups.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def _karaoke(group, clip_start, base):
    parts, prev = [], base
    for w in group:
        rel = max(0.0, w["start"] - clip_start)
        delta = max(0, int(round((rel - prev) * 100)))
        prev = max(prev, rel)
        parts.append(f"{{\\k{delta}}}{_esc(_clean(w['word']))}")
    return " ".join(parts)


def build(words, clip_start, clip_end, hook="", brand=None, size=None):
    lines = _header(int(size) if size else 76)
    duration = max(0.1, clip_end - clip_start)
    brand = BRAND if brand is None else brand

    if brand:
        lines.append(f"Dialogue: 0,{_ts(0)},{_ts(duration)},Brand,,0,0,0,,{_esc(brand)}")

    if hook:
        h_end = min(4.0, duration)
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(h_end)},Hook,,0,0,0,,{{\\fad(200,350)}}{_esc(hook.upper())}")

    groups = group_words(words, clip_start, clip_end)
    for i, g in enumerate(groups):
        text = re.sub(r"\s+", " ", "".join(w["word"] for w in g)).strip()
        if not text:
            continue
        rel_start = max(0.0, g[0]["start"] - clip_start)
        rel_end = min(duration, g[-1]["end"] - clip_start + 0.4)
        if i + 1 < len(groups):
            nxt = max(0.0, groups[i + 1][0]["start"] - clip_start)
            rel_end = min(rel_end, nxt - 0.05)
        if rel_end - rel_start < 0.1:
            continue

        body = _karaoke(g, clip_start, rel_start)
        lines.append(f"Dialogue: 2,{_ts(rel_start)},{_ts(rel_end)},Cap,,0,0,0,,{body}")

    return "\n".join(lines) + "\n"


def _synth_words(grupos, trads):
    out = []
    for g, tr in zip(grupos, trads):
        toks = [t for t in str(tr).split() if t]
        if not toks:
            continue
        span0 = float(g[0]["start"])
        span1 = float(g[-1]["end"])
        total = max(1e-3, span1 - span0)
        pesos = [max(2, len(t)) for t in toks]
        soma = sum(pesos)
        acc = span0
        for i, (t, p) in enumerate(zip(toks, pesos)):
            dur = total * p / soma
            end = span1 if i == len(toks) - 1 else acc + dur
            out.append({"word": (" " if out else "") + t,
                        "start": round(acc, 3), "end": round(end, 3)})
            acc = end
    return out


def traduzir_words(words, clip_start, clip_end, cache_key, on_log=None):
    """Traduz as legendas de um trecho para PT-BR preservando o timing.

    Agrupa as palavras como no render, manda as linhas pra IA traduzir de uma vez
    e redistribui o tempo de cada linha entre as palavras traduzidas (peso por
    tamanho). Cache em source/<cache_key>.cap_pt.json; se a IA falhar, devolve
    as palavras originais (o vídeo sai no idioma de sempre).
    """
    from .select import _chat, _extract_json

    def log(msg):
        if on_log:
            on_log(msg)

    cache = Path(SOURCE_DIR) / f"{cache_key}.cap_pt.json"
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if (abs(float(d.get("start", -1)) - clip_start) < 0.01
                    and abs(float(d.get("end", -1)) - clip_end) < 0.01
                    and d.get("words")):
                return d["words"]
        except Exception:
            pass

    grupos, linhas = [], []
    for g in group_words(words, clip_start, clip_end):
        txt = re.sub(r"\s+", " ", "".join(w["word"] for w in g)).strip()
        if txt:
            grupos.append(g)
            linhas.append(txt)
    if not linhas:
        return words

    try:
        content = _chat({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": (
                    "Voce traduz legendas de videos curtos do ingles para portugues do Brasil. "
                    "Natural e direto, sentido identico, frases curtas de legenda. Mantenha nomes "
                    "proprios e nomes de jogo/personagem (Minecraft, Wemmbu, End, Unstable SMP, "
                    "Spoke, Minitech etc) e siglas. Responda SO em JSON valido no formato "
                    '{"linhas": ["traducao 1", "traducao 2", ...]} com exatamente a mesma '
                    "quantidade de linhas recebidas."
                )},
                {"role": "user", "content": json.dumps({"linhas": linhas}, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
        })
        data = _extract_json(content)
        trads = [str(x) for x in (data.get("linhas") or [])]
    except Exception as exc:
        log(f"  [legenda] traducao falhou, seguindo no idioma original: {exc}")
        return words

    if len(trads) != len(linhas):
        log(f"  [legenda] veio {len(trads)} linhas para {len(linhas)} — completando com o original")
        while len(trads) < len(linhas):
            trads.append(linhas[len(trads)])
        trads = trads[:len(linhas)]

    out = _synth_words(grupos, trads)
    if not out:
        return words
    try:
        cache.write_text(
            json.dumps({"start": clip_start, "end": clip_end, "words": out}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
    log(f"  [legenda] {len(linhas)} linhas traduzidas para PT")
    return out
