import json
import re

from .config import GROQ_API_KEY, GROQ_MODEL, HASHTAGS_MAX, MAX_CLIP_SEC, MIN_CLIP_SEC
from .select import _chat, _extract_json

CATEGORIES = [
    "Gameplay", "Momento engraçado", "Meme", "Discussão/debate", "Entrevista",
    "Podcast", "História/relato", "Reação", "Treta/polêmica", "Curiosidade",
    "Tecnologia", "Esportes", "Stream", "Outro",
]

SYSTEM = (
    "Você é um especialista em edição de vídeos curtos, criação de conteúdo viral e SEO "
    "para YouTube Shorts, TikTok e Instagram Reels. Analisa cada conteúdo e define "
    "automaticamente como ele deve ser editado, apresentado e publicado em um canal de cortes. "
    "O canal publica tipos de conteúdo diferentes: NUNCA use o mesmo estilo para todos os vídeos. "
    "REGRA PRINCIPAL: a edição serve ao conteúdo. Nada de efeitos, memes, zoom ou sons só porque "
    "estão em alta; cada elemento precisa aumentar retenção, destacar informação, melhorar uma "
    "piada ou facilitar o acompanhamento. Não invente informações que não estejam no conteúdo. "
    "Responda SEMPRE em JSON válido, em português."
)

SCHEMA = """{
  "tipo": "uma das categorias da lista",
  "tipos_secundarios": ["categoria", "categoria"],
  "dinamismo": "baixo | medio | alto",
  "momento_principal": "o que acontece de mais forte no trecho",
  "hook": "como os 3 primeiros segundos devem prender, em CAPS",
  "estrutura": {
    "hook": "...", "desenvolvimento": "...", "principal": "...", "conclusao": "..."
  },
  "edicao": {
    "cortes": "onde cortar/acelerar",
    "zooms": "onde dar zoom",
    "efeitos": "efeitos com função explicita ou 'nenhum'",
    "legendas": "estilo de legenda adequado ao conteudo"
  },
  "titulos": ["opcao 1", "opcao 2", "opcao 3"],
  "descricao": "descricao especifica do corte, 2-3 frases, sem hashtags e sem creditos",
  "tags": {
    "principais": ["termo", "termo"],
    "secundarias": ["termo", "termo"],
    "descoberta": ["pesquisa que alguem faria", "pesquisa"]
  },
  "hashtags": ["#assunto", "#conteudo", "#plataforma", "#nicho"],
  "plataformas": {"youtube": "...", "tiktok": "...", "instagram": "..."},
  "capa": "descricao visual da capa"
}"""

MAX_TITLE = 70


def _norm_list(v, max_n, strip_hash=False):
    out, seen = [], set()
    for item in (v if isinstance(v, list) else [v]):
        s = str(item or "").strip()
        if not s:
            continue
        if strip_hash:
            s = s.replace(" ", "")
            if not s.startswith("#"):
                s = "#" + s
            s = s[:32]
        else:
            s = re.sub(r"\s+", " ", s)[:60]
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= max_n:
            break
    return out


def plan(text, duration, ctx, hint=""):
    """Analisa o trecho e devolve o plano editorial (ou {} se falhar)."""
    if not GROQ_API_KEY or not text:
        return {}
    user = (
        f"Video original: {ctx.get('title','')}\n"
        f"Canal: {ctx.get('channel','')}\n"
        f"Nicho/tags do autor: {', '.join((ctx.get('tags') or [])[:15])}\n"
        f"Videos parecidos na pesquisa: {'; '.join((ctx.get('related') or [])[:6])}\n"
        f"Duracao do trecho: {duration:.0f}s (alvo {int(MIN_CLIP_SEC)}-{int(MAX_CLIP_SEC)}s).\n"
        + (f"Gancho ja definido: {hint}\n" if hint else "")
        + f"Categorias possiveis: {', '.join(CATEGORIES)}.\n\n"
        f"Trecho para analisar:\n{text[:4000]}\n\n"
        "Analise o conteudo e responda no formato do schema: classifique o tipo, defina o estilo "
        "de edicao adequado (que NAO pode ser igual para todo video), a estrutura do short "
        "(hook, desenvolvimento, momento principal, conclusao), a quantidade de legendas, "
        "3 opcoes de titulo curto e sem clickbait enganoso, uma descricao especifica, "
        "tags em principais/secundarias/descoberta, hashtags especificas (nunca dezenas, "
        "maximo 5) e a recomendacao separada para YouTube Shorts, TikTok e Instagram Reels. "
        "Se o conteudo misturar categorias, escolha a principal e informe as secundarias."
    )
    try:
        content = _chat({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
                {"role": "system", "content": SCHEMA},
            ],
            "temperature": 0.5,
            "max_tokens": 2200,
            "response_format": {"type": "json_object"},
        })
        data = _extract_json(content)
    except Exception:
        return {}

    tipo = str(data.get("tipo") or "").strip()[:40] or "Outro"
    din = str(data.get("dinamismo") or "").lower()
    if "alt" in din:
        din = "alto"
    elif "baix" in din:
        din = "baixo"
    else:
        din = "medio"

    titulos = [t for t in _norm_list(data.get("titulos"), 3) if t][:3]
    ed = data.get("edicao") or {}
    est = data.get("estrutura") or {}
    plat = data.get("plataformas") or {}

    return {
        "tipo": tipo,
        "tipos_secundarios": _norm_list(data.get("tipos_secundarios"), 3),
        "dinamismo": din,
        "momento_principal": str(data.get("momento_principal") or "")[:200],
        "hook": str(data.get("hook") or "").strip().upper()[:45],
        "estrutura": {k: str(est.get(k) or "")[:200] for k in ("hook", "desenvolvimento", "principal", "conclusao")},
        "edicao": {k: str(ed.get(k) or "")[:250] for k in ("cortes", "zooms", "efeitos", "legendas")},
        "titulos": [t[:MAX_TITLE] for t in titulos],
        "descricao": re.sub(r"\s+", " ", str(data.get("descricao") or "")).strip()[:480],
        "tags": {
            "principais": _norm_list((data.get("tags") or {}).get("principais"), 10),
            "secundarias": _norm_list((data.get("tags") or {}).get("secundarias"), 10),
            "descoberta": _norm_list((data.get("tags") or {}).get("descoberta"), 10),
        },
        "hashtags": _norm_list(data.get("hashtags"), HASHTAGS_MAX, strip_hash=True),
        "plataformas": {k: str(plat.get(k) or "")[:400] for k in ("youtube", "tiktok", "instagram")},
        "capa": str(data.get("capa") or "")[:250],
    }


def all_tags(edit):
    if not edit:
        return []
    t = edit.get("tags") or {}
    return (t.get("principais") or []) + (t.get("secundarias") or []) + (t.get("descoberta") or [])


def zoom_profile(dinamismo):
    return {"baixo": (1.00, 0.035, 70), "medio": (1.07, 0.06, 76), "alto": (1.15, 0.09, 84)}.get(dinamismo or "medio", (1.07, 0.06, 76))
