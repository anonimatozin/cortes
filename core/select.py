import json
import re
import time

import requests

from .config import GROQ_API_KEY, GROQ_MODEL, HASHTAGS_MAX, MAX_CLIP_SEC, MIN_CLIP_SEC
from . import research

SYSTEM = (
    "Voce e um editor de shorts virais. Voce recebe trechos de um video e decide quais "
    "funcionam como um corte autonomo de 25 a 58 segundos para YouTube Shorts, TikTok e Reels. "
    "Criterios: tem gancho forte nos 3 primeiros segundos, tem virada/payoff, faz sentido sem "
    "contexto, gera reacao (risada, choque, suspense, indignacao), e a estrutura se fecha "
    "(hook -> desenvolvimento -> momento principal -> conclusao). Trechos chatos, genericos ou "
    "que dependem de ver o video todo recebem nota baixa. A edicao serve ao conteudo: nada de "
    "efeito que nao tenha funcao de retencao. Responda SEMPRE em JSON valido, em portugues."
)

SCHEMA = """{
  "clips": [
    {
      "i": 0,
      "score": 0,
      "hook": "frase de gancho em CAPS, max 45 caracteres",
      "title": "titulo do shorts, max 70 caracteres, com emoji no inicio",
      "description": "2-3 frases de contexto, sem hashtags e sem creditos",
      "hashtags": ["#palavrachave", "#outra"],
      "tags": ["tag1", "tag2"],
      "reason": "por que esse corte rende"
    }
  ]
}"""

RESEARCH_RULES = (
    "REGRAS DE TAGS E HASHTAGS (obrigatorio):\n"
    "1. So use hashtags que aparecem na pesquisa de videos relacionados ou que sejam "
    "palavras-chave reais do nicho. Nada inventado, nada generico como #fyp ou #viral.\n"
    "2. Hashtags: 3 a 5, sem espacos, sem duplicata, em portugues (ou ingles se o video for ingles).\n"
    "3. Tags do YouTube: 6 a 14, frases curtas de 1-3 palavras que alguem realmente pesquisaria.\n"
    "4. description: NAO inclua hashtags nem creditos; so as frases de contexto.\n"
)


def _chat(payload, retries=5):
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(min(60, 6 * (2 ** attempt)))
                continue
            break
        if r.status_code in (429, 500, 502, 503, 504):
            last = RuntimeError(f"Groq {r.status_code}: {r.text[:150]}")
            time.sleep(min(60, 6 * (2 ** attempt)))
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise last or RuntimeError("Groq esgotou as tentativas")


def _extract_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"JSON nao encontrado: {text[:200]}")
    return json.loads(text[start : end + 1])


def _score_batch(batch, ctx):
    lines = [f"[{i}] {c['start']:.1f}s-{c['end']:.1f}s :: {c['text'][:900]}" for i, c in enumerate(batch)]
    related = "\n".join(f"  - {t}" for t in (ctx.get("related") or [])[:10]) or "  (nenhum)"
    src_tags = ", ".join((ctx.get("tags") or [])[:20]) or "(sem)"
    user = (
        f"Video original: {ctx.get('title','')}\n"
        f"Canal: {ctx.get('channel','')}\n"
        f"Nicho/tags do autor: {src_tags}\n"
        f"Duracao alvo do corte: {int(MIN_CLIP_SEC)}-{int(MAX_CLIP_SEC)}s.\n\n"
        f"Videos parecidos que apareceram na pesquisa (use como base de vocabulario):\n{related}\n\n"
        "Avalie APENAS os trechos listados e devolva score 0-100 para cada um.\n"
        + RESEARCH_RULES + "\n"
        + "\n".join(lines)
    )
    content = _chat(
        {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
                {"role": "system", "content": SCHEMA},
            ],
            "temperature": 0.4,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }
    )
    data = _extract_json(content)
    out = {}
    for item in data.get("clips", []):
        try:
            i = int(item["i"])
        except (KeyError, TypeError, ValueError):
            continue
        if i < 0 or i >= len(batch):
            continue
        out[i] = {
            "score": int(item.get("score", 0)),
            "hook": str(item.get("hook", "")).strip()[:60],
            "title": str(item.get("title", "")).strip()[:100],
            "description": str(item.get("description", "")).strip()[:480],
            "hashtags": research.clean_hashtags(item.get("hashtags") or [], HASHTAGS_MAX),
            "tags": research.clean_tags(item.get("tags") or [], 14),
            "reason": str(item.get("reason", ""))[:300],
        }
    return out


def _fallback(cands, ctx, limit):
    out = []
    for c in sorted(cands, key=lambda x: x.get("pre_score", 0), reverse=True):
        if any(not (c["start"] >= g[1] or c["end"] <= g[0]) for g in [(x["start"], x["end"]) for x in out]):
            continue
        text = re.sub(r"\s+", " ", c["text"]).strip()
        sentence = re.split(r"(?<=[.!?])\s", text)[0][:70].strip()
        c["ai"] = {
            "score": int(min(99, max(35, c.get("pre_score", 0) * 10))),
            "hook": sentence.upper()[:45],
            "title": f"{sentence}",
            "description": text[:300],
            "hashtags": ["#cortes", "#shorts"],
            "tags": research.clean_tags((ctx.get("tags") or []) + ["cortes", "shorts"], 14),
            "reason": "sem IA configurada - usado ranking por energia",
        }
        out.append(c)
        if len(out) >= limit:
            break
    return sorted(out, key=lambda x: x["start"])


def select_best(cands, ctx, limit, on_progress=None):
    if not cands:
        return []
    if not GROQ_API_KEY:
        if on_progress:
            on_progress("  AVISO: GROQ_API_KEY vazia, usando ranking por energia (sem IA)")
        return _fallback(cands, ctx, limit)

    indexed = list(enumerate(cands))
    results = {}
    for bstart in range(0, len(indexed), 10):
        batch = [c for _, c in indexed[bstart : bstart + 10]]
        try:
            local = _score_batch(batch, ctx)
        except Exception as exc:
            if on_progress:
                on_progress(f"  lote falhou ({exc}), seguindo")
            continue
        for li, meta in local.items():
            results[bstart + li] = meta
        if on_progress:
            on_progress(f"  avaliados {min(bstart + 10, len(indexed))}/{len(indexed)}")
        if bstart + 10 < len(indexed):
            time.sleep(2)

    seed_tags = research.clean_tags(ctx.get("tags") or [], 10)
    for idx, cand in enumerate(cands):
        meta = results.get(idx, {"score": 0, "hook": "", "title": "", "description": "", "hashtags": [], "tags": [], "reason": "sem avaliacao"})
        if not meta["score"]:
            meta["score"] = max(0, int(cand.get("pre_score", 0) * 10))
        if not meta.get("hashtags"):
            meta["hashtags"] = ["#cortes", "#shorts"]
        if not meta.get("tags"):
            meta["tags"] = list(seed_tags)
        cand["ai"] = meta

    ranked = sorted(cands, key=lambda c: c["ai"]["score"], reverse=True)
    picked, gaps = [], []
    for cand in ranked:
        if cand["ai"]["score"] < 35:
            continue
        if any(not (cand["start"] >= g[1] or cand["end"] <= g[0]) for g in gaps):
            continue
        picked.append(cand)
        gaps.append((cand["start"], cand["end"]))
        if len(picked) >= limit:
            break

    return sorted(picked, key=lambda c: c["start"])
