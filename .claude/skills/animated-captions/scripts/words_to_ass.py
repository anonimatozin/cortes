#!/usr/bin/env python3
"""Converte timestamps por palavra em legenda ASS estilo 'karaoke' (palavra falada em destaque).

Entradas aceitas (JSON):
  1) lista simples:  [{"word": "ola", "start": 1.02, "end": 1.31}, ...]
  2) formato WhisperX/faster-whisper: {"segments": [{"words": [{"word":..,"start":..,"end":..}]}]}
  Tempos em SEGUNDOS.

Uso:
    python words_to_ass.py palavras.json -o legenda.ass
    python words_to_ass.py palavras.json -o legenda.ass --style hormozi --offset -12.5
    python words_to_ass.py palavras.json -o legenda.ass --width 1920 --height 1080 --size 64

--offset soma segundos a todos os tempos (use o NEGATIVO do inicio do corte, p.ex. -12.5,
quando o clipe comeca em 12.5 s do video original). Palavras fora do clipe sao descartadas.

Para gravar no video (rode na pasta do .ass para evitar problemas de caminho no Windows):
    ffmpeg -i clipe.mp4 -vf "ass=legenda.ass" -c:a copy saida.mp4
"""
import argparse
import json
import sys

STYLES = {
    # cores ASS sao &HBBGGRR& (azul-verde-vermelho)
    "hormozi": {"font": "Arial Black", "primary": "&H00FFFFFF&", "highlight": "&H0000F0FF&",
                "outline": "&H00000000&", "outline_w": 6, "shadow": 0, "upper": True, "scale": 118},
    "minimal": {"font": "Arial", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
                "outline": "&H00000000&", "outline_w": 3, "shadow": 1, "upper": False, "scale": 100},
    "karaoke": {"font": "Arial", "primary": "&H00FFFFFF&", "highlight": "&H0000D7FF&",
                "outline": "&H00000000&", "outline_w": 5, "shadow": 0, "upper": False, "scale": 110},
}


def load_words(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "segments" in data:
        words = [w for seg in data["segments"] for w in seg.get("words", [])]
    elif isinstance(data, dict) and "words" in data:
        words = data["words"]
    else:
        words = data
    clean = []
    for w in words:
        if "start" not in w or "end" not in w:
            continue  # WhisperX as vezes devolve palavras sem tempo (numeros/simbolos)
        text = str(w.get("word", w.get("text", ""))).strip()
        if text:
            clean.append({"word": text, "start": float(w["start"]), "end": float(w["end"])})
    clean.sort(key=lambda x: x["start"])
    return clean


def ts(seconds):
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def group_words(words, max_words, max_chars, max_gap):
    groups, cur = [], []
    for w in words:
        if cur:
            too_many = len(cur) >= max_words
            too_long = len(" ".join(x["word"] for x in cur + [w])) > max_chars
            big_gap = w["start"] - cur[-1]["end"] > max_gap
            ends_sentence = cur[-1]["word"][-1] in ".?!"
            if too_many or too_long or big_gap or ends_sentence:
                groups.append(cur)
                cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_events(groups, st, hold):
    events = []
    for g in groups:
        for i, w in enumerate(g):
            start = w["start"]
            if i + 1 < len(g):
                end = g[i + 1]["start"]
            else:
                end = w["end"] + hold
            if end <= start:
                end = start + 0.05
            parts = []
            for j, x in enumerate(g):
                txt = esc(x["word"].upper() if st["upper"] else x["word"])
                if j == i:
                    parts.append("{\\c" + st["highlight"] + f"\\fscx{st['scale']}\\fscy{st['scale']}" + "}" + txt + "{\\r}")
                else:
                    parts.append(txt)
            events.append((start, end, " ".join(parts)))
    # garante que um grupo nunca sobreponha o proximo
    for k in range(len(events) - 1):
        s, e, t = events[k]
        ns = events[k + 1][0]
        if e > ns:
            events[k] = (s, ns, t)
    return events


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words_json")
    ap.add_argument("-o", "--output", default="legenda.ass")
    ap.add_argument("--style", choices=sorted(STYLES), default="hormozi")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--size", type=int, help="tamanho da fonte (padrao: ~5.5%% da altura)")
    ap.add_argument("--font", help="nome da fonte instalada (sobrescreve o estilo)")
    ap.add_argument("--max-words", type=int, default=3)
    ap.add_argument("--max-chars", type=int, default=20)
    ap.add_argument("--max-gap", type=float, default=0.6, help="pausa (s) que quebra o grupo")
    ap.add_argument("--hold", type=float, default=0.25, help="quanto a ultima palavra fica na tela (s)")
    ap.add_argument("--margin-v", type=int, help="distancia da borda de baixo em px (padrao ~25%% da altura)")
    ap.add_argument("--offset", type=float, default=0.0, help="segundos somados aos tempos (negativo p/ clipes)")
    ap.add_argument("--clip-duration", type=float, help="descarta palavras depois desta duracao (s)")
    args = ap.parse_args()

    words = load_words(args.words_json)
    for w in words:
        w["start"] += args.offset
        w["end"] += args.offset
    words = [w for w in words if w["end"] > 0 and (args.clip_duration is None or w["start"] < args.clip_duration)]
    for w in words:
        w["start"] = max(0.0, w["start"])
    if not words:
        sys.exit("Nenhuma palavra no intervalo. Confira --offset e os tempos do JSON.")

    st = dict(STYLES[args.style])
    if args.font:
        st["font"] = args.font
    margin_v = args.margin_v if args.margin_v is not None else int(args.height * 0.25)
    margin_lr = int(args.width * 0.06)

    groups = group_words(words, args.max_words, args.max_chars, args.max_gap)
    if args.size:
        size = args.size
    else:
        # tamanho base ~5.5% da altura, reduzido se o maior grupo nao couber na largura
        longest = max(len(" ".join(x["word"] for x in g)) for g in groups)
        avail = args.width - 2 * margin_lr
        size = min(int(args.height * 0.055), int(avail / (longest * 0.72)))
    events = build_events(groups, st, args.hold)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {args.width}
PlayResY: {args.height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st['font']},{size},{st['primary']},{st['primary']},{st['outline']},&H80000000&,-1,0,0,0,100,100,0,0,1,{st['outline_w']},{st['shadow']},2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(args.output, "w", encoding="utf-8-sig") as f:
        f.write(header)
        for s, e, text in events:
            f.write(f"Dialogue: 0,{ts(s)},{ts(e)},Default,,0,0,0,,{text}\n")
    print(f"{len(words)} palavras, {len(groups)} grupos, {len(events)} eventos -> {args.output}")


if __name__ == "__main__":
    main()
