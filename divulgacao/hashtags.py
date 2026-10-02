"""MÓDULO 1 — pesquisa de hashtags e tags.

Fluxo:
  1. lê a transcrição do trecho que virou corte;
  2. a IA gera 30 candidatas (tema, jogo, personagem, emoção, público) + tags;
  3. YouTube Data API v3: busca vídeos do nicho, lê snippet.tags e estatísticas
     e mede quais tags aparecem nos vídeos ACIMA DA MÉDIA do canal;
  4. autocomplete do YouTube traz variações de busca (melhor esforço);
  5. `tiktok_trending.txt` é lido como lista colada pelo usuário — NUNCA scraping;
  6. nota = frequência nos vídeos fortes x relevância ao corte x baixa concorrência;
  7. grava divulgacao/saida/<corte>/metadata.json.

Toda chamada de API é protegida por cache e por teto de cota diário: se a cota
acabar ou a rede cair, o módulo devolve as candidatas da IA/planilha e avisa.
"""

import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, llm

ACENTOS = {"Á": "A", "À": "A", "Ã": "A", "Â": "A", "Ä": "A", "á": "a", "à": "a", "ã": "a", "â": "a", "ä": "a",
           "É": "E", "È": "E", "Ê": "E", "Ë": "E", "é": "e", "è": "e", "ê": "e", "ë": "e",
           "Í": "I", "Ì": "I", "Î": "I", "Ï": "I", "í": "i", "ì": "i", "î": "i", "ï": "i",
           "Ó": "O", "Ò": "O", "Õ": "O", "Ô": "O", "Ö": "O", "ó": "o", "ò": "o", "õ": "o", "ô": "o", "ö": "o",
           "Ú": "U", "Ù": "U", "Û": "U", "Ü": "U", "ú": "u", "ù": "u", "û": "u", "ü": "u",
           "Ç": "C", "ç": "c", "Ñ": "N", "ñ": "n", "Ý": "Y", "ý": "y"}

HASHTAG_RE = re.compile(r"^#[A-Za-z0-9_À-ÿ]+$")
NAO_USAR = {"fyp", "foryou", "viral", "like", "follow", "share", "trending", "explore"}

# mesmos escopos do token que o projeto já gravou em tokens/youtube.json
_SCOPES_OAUTH = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


class CotaExcedidaError(RuntimeError):
    pass


# --------------------------------------------------------------- utilitários
def _norm(txt):
    """Minúsculas, sem acento, só letras/números — base de comparação."""
    txt = str(txt or "").lower()
    txt = "".join(ACENTOS.get(c, c) for c in txt)
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", txt)


def limpar_hashtag(txt, max_n=32):
    txt = str(txt or "").strip()
    if not txt:
        return ""
    if not txt.startswith("#"):
        txt = "#" + txt
    txt = txt.replace(" ", "").replace("-", "")
    txt = txt[:max_n + 1]
    if not HASHTAG_RE.match(txt):
        return ""
    if _norm(txt) in NAO_USAR:
        return ""
    return txt


def _bate(cand, tag):
    """'computador' casa com 'quem inventou o computador'."""
    if not cand or not tag:
        return False
    if cand == tag:
        return True
    if len(cand) >= 4 and (cand in tag or tag in cand):
        return True
    return False


# ------------------------------------------------------- entrada: transcrição
def _resolver_caminho(alvo):
    alvo = Path(alvo)
    if alvo.exists():
        return alvo
    for ext in (".json", ".mp4"):
        cand = config.CLIPS_DIR / f"{alvo.stem}{ext}"
        if cand.exists():
            return cand
    for pasta in (config.CLIPS_DIR, Path.cwd()):
        try:
            for arq in pasta.glob(f"*{alvo.name}*"):
                return arq
        except OSError:
            continue
    return alvo


def _transcript_do_jobs(caminho_clip):
    """Acha o id do vídeo original pelo jobs.json (caminho do clipe gravado lá)."""
    try:
        dados = json.loads(config.JOBS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    alvo = str(Path(caminho_clip).resolve())
    for job in dados.get("jobs", []):
        for c in job.get("clips", []):
            try:
                if str(Path(c.get("path", "")).resolve()) == alvo:
                    return (job.get("meta") or {}).get("id")
            except OSError:
                continue
    return None


def encontrar_transcricao(caminho_clip, explicito=None):
    """Localiza source/<id>.transcript.json a partir do arquivo do corte."""
    if explicito:
        p = Path(explicito)
        if p.exists():
            return p
        p = config.SOURCE_DIR / f"{explicito}.transcript.json"
        if p.exists():
            return p

    stem_clip = Path(caminho_clip).stem
    video_id = _transcript_do_jobs(caminho_clip)
    if video_id:
        p = config.SOURCE_DIR / f"{video_id}.transcript.json"
        if p.exists():
            return p

    candidatos = sorted(config.SOURCE_DIR.glob("*.transcript.json"),
                        key=lambda p: len(p.stem), reverse=True)
    for p in candidatos:
        base = p.stem.replace(".transcript", "")
        if base and base in stem_clip:
            return p
    return None


def texto_do_corte(transcript, inicio=0.0, fim=None):
    """Junta os segmentos do trecho. Sem início/fim, usa a transcrição inteira."""
    segments = transcript.get("segments") or []
    if inicio in (None, 0, 0.0) and fim in (None, 0, 0.0, float("inf")):
        partes = [s.get("text", "") for s in segments]
    else:
        fim = float("inf") if fim in (None, 0, 0.0) else float(fim)
        partes = [s.get("text", "") for s in segments
                  if float(s.get("end", 0)) > float(inicio) and float(s.get("start", 0)) < fim]
    return re.sub(r"\s+", " ", " ".join(partes)).strip()


def carregar_corte(alvo, transcript=None):
    """Devolve o dicionário-base do corte (id, caminho, trecho, metadados)."""
    caminho = _resolver_caminho(alvo)
    sidecar = caminho.with_suffix(".json") if caminho.suffix.lower() != ".json" else caminho
    dados = {}
    if sidecar.exists():
        try:
            dados = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            dados = {}

    tpath = encontrar_transcricao(caminho, transcript)
    if tpath is None:
        raise FileNotFoundError(
            f"transcricao nao encontrada para {caminho.name}. "
            f"Passe --transcript <id do video> (source/*.transcript.json)"
        )
    try:
        tr = json.loads(tpath.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"transcricao ilegivel: {tpath.name} ({exc})")

    inicio = float(dados.get("start") or 0.0)
    fim = float(dados.get("end") or 0.0)
    texto = texto_do_corte(tr, inicio, fim)
    if not texto:
        texto = texto_do_corte(tr)

    return {
        "id": caminho.stem,
        "caminho": str(caminho),
        "transcript": str(tpath),
        "inicio": inicio,
        "fim": fim,
        "texto": texto,
        "titulo": (dados.get("title") or "").strip(),
        "descricao": (dados.get("description") or "").strip(),
        "hashtags_base": dados.get("hashtags") or [],
        "tags_base": dados.get("tags") or [],
        "hook": (dados.get("hook") or "").strip(),
    }


# ------------------------------------------------------------- 2. candidatas IA
SISTEMA_IA = (
    "Voce e um especialista em SEO de videos curtos (Shorts, TikTok, Reels) em portugues do Brasil. "
    "Voce conhece as hashtags que realmente funcionam por nicho e evita as genericas. "
    "Responda SEMPRE em JSON valido, sem comentarios fora do JSON."
)

ESQUEMA_IA = """{
  "candidatas": [
    {"tag": "#exemplo", "tipo": "amplo|nicho|especifico", "relevancia": 0.0, "por_que": "motivo curto"}
  ],
  "tags": ["tag do youtube", "outra tag"],
  "titulo": "titulo do corte (max 70 caracteres)",
  "descricao": "descricao de 2-3 frases, sem hashtags"
}

REGRAS:
- candidatas: exatamente NUM candidatas, sem espaco, sem caractere invalido, em portugues (ingles so se o texto for ingles).
- distribuicao dos tipos: ~8 "amplo" (genero/nicho), ~14 "nicho" (assunto especifico do nicho), ~8 "especifico" (do proprio corte: personagem, jogo, momento, frase).
- relevancia: 0.0 a 1.0, o quanto a hashtag descreve ESTE corte.
- proibido: #fyp, #viral, #like, #follow, #trending, hashtags de 1 letra.
- tags: 8 a 14 frases curtas de 1-3 palavras que alguem realmente pesquisaria no YouTube.
- titulo e descricao: use o texto do corte; se ja houver titulo/descricao validos, repita-os."""


def candidatas_ia(corte, nicho, on_log=None):
    """Gera as candidatas com a IA. Devolve dict ou None se a IA estiver off."""
    if not llm.disponivel():
        return None
    texto = corte["texto"][:6000]
    num = config.IA_CANDIDATAS
    user = (
        f"Nicho configurado: {nicho}\n"
        f"Titulo atual: {corte.get('titulo') or '(sem)'}\n"
        f"Descricao atual: {corte.get('descricao') or '(sem)'}\n"
        f"Tags do autor (se houver): {', '.join(corte.get('tags_base') or []) or '(sem)'}\n"
        f"Hashtags que o pipeline ja usou: {', '.join(corte.get('hashtags_base') or []) or '(sem)'}\n\n"
        f"Texto do corte:\n\"\"\"\n{texto}\n\"\"\"\n\n"
        f"Gere exatamente {num} candidatas. " + ESQUEMA_IA.replace("NUM", str(num))
    )
    try:
        dados = llm.chat_json(user, system=SISTEMA_IA, max_tokens=3000)
    except Exception as exc:
        if on_log:
            on_log(f"  IA falhou ({exc}) -> seguindo sem candidatas da IA")
        return None
    if not isinstance(dados, dict) or not dados.get("candidatas"):
        if on_log:
            on_log("  IA devolveu vazio -> seguindo sem candidatas da IA")
        return None
    return dados


def _candidatas_fallback(corte, nicho, num):
    """Sem IA: monta candidatas a partir do nicho + tags do autor + título."""
    base = []
    for t in corte.get("hashtags_base") or []:
        h = limpar_hashtag(t)
        if h:
            base.append((h, "nicho", 0.7, "hashtag usada pelo pipeline"))
    for t in corte.get("tags_base") or []:
        h = limpar_hashtag(t)
        if h:
            base.append((h, "nicho", 0.6, "tag do autor"))
    for palavra in re.findall(r"[A-Za-zÀ-ÿ]{4,}", corte.get("titulo") or ""):
        h = limpar_hashtag(palavra)
        if h:
            base.append((h, "especifico", 0.65, "palavra do titulo"))

    genero = {
        "podcast": ["#podcast", "#cortes", "#conversa", "#entrevista", "#viral", "#brasil"],
        "games": ["#games", "#gamer", "#gameplay", "#jogos", "#clip", "#twitch"],
        "minecraft": ["#minecraft", "#gamer", "#survival", "#gaming", "#clip", "#brasil"],
        "futebol": ["#futebol", "#gol", "#brasil", "#torcida", "#campeonato", "#resumo"],
        "tecnologia": ["#tecnologia", "#ia", "#ciencia", "#curiosidade", "#inovacao", "#futuro"],
        "politica": ["#politica", "#brasil", "#debate", "#noticias", "#eleicoes", "#opiniao"],
        "entretenimento": ["#entretenimento", "#novela", "#tv", "#celebridades", "#humor", "#memes"],
    }
    for tag in genero.get(_norm(nicho) or "podcast", genero["podcast"]):
        base.append((tag, "amplo", 0.5, f"genero do nicho {nicho}"))

    vistas, out = set(), []
    for tag, tipo, rel, origem in base:
        k = _norm(tag)
        if not k or k in vistas:
            continue
        vistas.add(k)
        out.append({"tag": tag, "tipo": tipo, "relevancia": rel, "por_que": origem, "origem": "fallback"})
        if len(out) >= num:
            break
    i = 1
    while len(out) < num:
        sufixo = f"brasil" if i % 2 else "shorts"
        tag = limpar_hashtag(f"corte{i}{sufixo}")
        if tag and _norm(tag) not in vistas:
            vistas.add(_norm(tag))
            out.append({"tag": tag, "tipo": "amplo", "relevancia": 0.3,
                        "por_que": "preenchimento", "origem": "fallback"})
        i += 1
        if i > num + 20:
            break
    return out


# ------------------------------------------------------ 3. dados reais (YouTube)
def _servico_oauth():
    """Lê o token que o projeto já usa (tokens/youtube.json) — nunca abre navegador."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, "google-api-python-client nao instalado"
    token = config.RAIZ / "tokens" / "youtube.json"
    if not token.exists():
        return None, "sem YOUTUBE_API_KEY e sem tokens/youtube.json (rode: python cortes.py auth)"
    try:
        creds = Credentials.from_authorized_user_file(str(token), _SCOPES_OAUTH)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.write_text(creds.to_json(), encoding="utf-8")
        if not creds.valid:
            return None, "token do YouTube invalido (rode: python cortes.py auth)"
        return build("youtube", "v3", credentials=creds, cache_discovery=False), "oauth"
    except Exception as exc:
        return None, f"OAuth do YouTube falhou ({exc})"


def _servico_youtube():
    if not config.YT_ATIVO:
        return None, "desligado no config"
    if config.YOUTUBE_API_KEY:
        try:
            from googleapiclient.discovery import build
        except ImportError:
            return None, "google-api-python-client nao instalado"
        try:
            return build("youtube", "v3", developerKey=config.YOUTUBE_API_KEY,
                         cache_discovery=False), "chave"
        except Exception as exc:
            return None, f"falha ao montar cliente do YouTube ({exc})"
    return _servico_oauth()


def _cota_ler():
    try:
        d = json.loads(config.COTA_YOUTUBE_JSON.read_text(encoding="utf-8"))
        if d.get("dia") == config.hoje():
            return d
    except Exception:
        pass
    return {"dia": config.hoje(), "unidades": 0}


def _cota_gastar(unidades):
    d = _cota_ler()
    d["unidades"] = int(d.get("unidades", 0)) + int(unidades)
    config.COTA_YOUTUBE_JSON.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d["unidades"]


def _cache_youtube(chave):
    caminho = config.CACHE_DIR / f"youtube_{_norm(chave)[:40]}.json"
    try:
        d = json.loads(caminho.read_text(encoding="utf-8"))
        salvo = datetime.fromisoformat(d["salvo_em"])
        if (datetime.now() - salvo).total_seconds() < config.YT_CACHE_DIAS * 86400:
            return d.get("dados")
    except Exception:
        pass
    return None


def _cache_salvar(chave, dados):
    caminho = config.CACHE_DIR / f"youtube_{_norm(chave)[:40]}.json"
    caminho.write_text(
        json.dumps({"salvo_em": datetime.now().isoformat(timespec="seconds"), "dados": dados},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def autocomplete_youtube(termos, on_log=None):
    """Sugestões oficiais do endpoint de autocomplete (melhor esforço, sem cota)."""
    if not config.YT_AUTOCOMPLETE:
        return []
    import requests

    vistos, out = set(), []
    for termo in termos[:8]:
        termo = str(termo or "").strip()
        if not termo:
            continue
        try:
            r = requests.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "ds": "yt", "hl": "pt", "gl": "BR", "q": termo},
                timeout=8,
            )
            if r.status_code != 200:
                continue
            sugestoes = r.json()[1]
        except Exception:
            continue
        for s in sugestoes:
            k = _norm(s)
            if k and k not in vistos:
                vistos.add(k)
                out.append(str(s))
    if not out and on_log:
        on_log("  autocomplete indisponivel (seguindo)")
    return out


def _trends_google(termos):
    """Google Trends via pytrends — não oficial, pode quebrar. Desligado por padrão."""
    if not config.TRENDS_ATIVO:
        return []
    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError:
        return []
    try:
        pt = TrendReq(hl="pt-BR", tz=180)
        pt.build_payload(termos[:5][:8], timeframe="today 3-m", geo="BR")
        dados = pt.interest_over_time()
        if dados.empty:
            return []
        medias = dados[termos[:5]].mean().sort_values(ascending=False)
        return [t for t, v in medias.items() if v > 0]
    except Exception:
        return []


def dados_youtube(nicho, on_log=None):
    """Busca vídeos do nicho e mede a frequência das tags nos que ficaram acima da média."""
    if not config.YT_ATIVO:
        return {"disponivel": False, "motivo": "desligado no config", "frequencia": {},
                "videos": [], "fortes": 0, "total": 0, "autocomplete": [], "avisos": []}

    cacheado = _cache_youtube(f"{nicho}|{config.YT_ORDEM}|{config.YT_PUBLICADO_DIAS}|{config.YT_MAX_VIDEOS}")
    if cacheado is not None:
        if on_log:
            on_log(f"  YouTube: cache local ({cacheado.get('total', 0)} videos, custo 0 cota)")
        cacheado = dict(cacheado)
        cacheado["cache"] = True
        return cacheado

    service, origem = _servico_youtube()
    avisos = []
    if service is None:
        if on_log:
            on_log(f"  YouTube: {origem}")
        return {"disponivel": False, "motivo": origem, "frequencia": {},
                "videos": [], "fortes": 0, "total": 0,
                "autocomplete": autocomplete_youtube([nicho], on_log), "avisos": [origem]}

    if _cota_ler()["unidades"] + 101 > config.YT_COTA_DIA:
        raise CotaExcedidaError(f"cota diaria do modulo atingida ({config.YT_COTA_DIA} unidades)")

    from googleapiclient.errors import HttpError

    atraso = (datetime.now(timezone.utc) - timedelta(days=config.YT_PUBLICADO_DIAS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

    try:
        busca = service.search().list(
            part="snippet", q=nicho, type="video", order=config.YT_ORDEM,
            publishedAfter=atraso, maxResults=min(50, config.YT_MAX_VIDEOS),
            relevanceLanguage="pt", regionCode="BR",
        ).execute()
    except HttpError as exc:
        texto = str(exc)
        if "quotaExceeded" in texto or "rateLimitExceeded" in texto:
            raise CotaExcedidaError(f"cota do YouTube: {texto[:160]}") from exc
        avisos.append(f"search.list falhou: {texto[:160]}")
        return {"disponivel": False, "motivo": avisos[-1], "frequencia": {},
                "videos": [], "fortes": 0, "total": 0,
                "autocomplete": autocomplete_youtube([nicho], on_log), "avisos": avisos}
    _cota_gastar(100)

    itens = (busca.get("items") or [])
    ids = [i["id"]["videoId"] for i in itens if i.get("id", {}).get("videoId")]
    if not ids:
        avisos.append("nenhum video encontrado para o nicho")
    videos = []
    if ids:
        try:
            detalhes = service.videos().list(
                part="snippet,statistics", id=",".join(ids), maxResults=len(ids)
            ).execute()
        except HttpError as exc:
            texto = str(exc)
            if "quotaExceeded" in texto:
                raise CotaExcedidaError(f"cota do YouTube: {texto[:160]}") from exc
            avisos.append(f"videos.list falhou: {texto[:160]}")
            detalhes = {}
        _cota_gastar(1 + (len(ids) // 50))
        for v in detalhes.get("items") or []:
            sn = v.get("snippet") or {}
            st = v.get("statistics") or {}
            try:
                views = int(st.get("viewCount") or 0)
            except ValueError:
                views = 0
            videos.append({
                "id": v.get("id"),
                "titulo": sn.get("title", ""),
                "canal": sn.get("channelTitle", ""),
                "canal_id": sn.get("channelId", ""),
                "views": views,
                "curtidas": int(st.get("likeCount") or 0 or 0),
                "tags": [str(t) for t in (sn.get("tags") or [])][:30],
            })

    # videos "fortes" = acima da média do PRÓPRIO canal (fallback: mediana global)
    por_canal = {}
    for v in videos:
        por_canal.setdefault(v["canal_id"], []).append(v["views"])
    medias = {c: sum(x) / len(x) for c, x in por_canal.items() if x}
    ordenados = sorted(v["views"] for v in videos)
    mediana = ordenados[len(ordenados) // 2] if ordenados else 0
    for v in videos:
        limiar = medias.get(v["canal_id"]) if len(por_canal.get(v["canal_id"], [])) >= 2 else mediana
        v["forte"] = v["views"] >= max(1, limiar or mediana)

    frequencia = {}
    for v in videos:
        if not v["forte"]:
            continue
        for tag in v["tags"]:
            k = _norm(tag)
            if not k:
                continue
            reg = frequencia.setdefault(k, {"rotulo": tag.strip(), "fortes": 0, "total": 0})
            reg["fortes"] += 1
    for v in videos:
        for tag in v["tags"]:
            k = _norm(tag)
            if k in frequencia:
                frequencia[k]["total"] += 1

    termos = [nicho] + [t.strip() for t in sorted(
        frequencia, key=lambda k: frequencia[k]["fortes"], reverse=True)[:5]]
    termos += [v["titulo"][:40] for v in sorted(videos, key=lambda x: -x["views"])[:3]]
    autocompletar = autocomplete_youtube(termos, on_log)
    tendencias = _trends_google([nicho])

    dados = {
        "disponivel": True,
        "origem": origem,
        "nicho": nicho,
        "videos": [{k: v[k] for k in ("id", "titulo", "canal", "views", "forte")}
                   for v in videos],
        "total": len(videos),
        "fortes": sum(1 for v in videos if v["forte"]),
        "frequencia": frequencia,
        "autocomplete": autocompletar,
        "trends": tendencias,
        "avisos": avisos,
    }
    _cache_salvar(f"{nicho}|{config.YT_ORDEM}|{config.YT_PUBLICADO_DIAS}|{config.YT_MAX_VIDEOS}", dados)
    if on_log:
        on_log(f"  YouTube: {dados['total']} videos, {dados['fortes']} fortes, "
               f"{len(frequencia)} tags distintas ({origem})")
    return dados


# ------------------------------------------------------------ 5. TikTok (manual)
def tendencias_tiktok(on_log=None):
    """Lê tiktok_trending.txt — lista colada/exportada pelo usuário. Sem scraping."""
    if not config.TIKTOK_ATIVO:
        return []
    caminho = config.TIKTOK_TRENDING
    if not caminho.exists():
        if on_log:
            on_log(f"  TikTok: {caminho.name} nao encontrado (crie a lista para usar)")
        return []
    out, vistas = [], set()
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("//") or linha.startswith(";"):
            continue
        bruto = re.split(r"[,\t|;]", linha)[0]
        h = limpar_hashtag(bruto)
        if not h:
            continue
        k = _norm(h)
        if k in vistas:
            continue
        vistas.add(k)
        out.append(h)
    if on_log:
        on_log(f"  TikTok: {len(out)} hashtags da lista local")
    return out


# ------------------------------------------------------------- 6. pontuação
def pontuar(candidatas, dados, tendencias, prioridades=None):
    """nota = frequência nos fortes x relevância x (1 - concorrência)."""
    prioridades = prioridades or {}
    videos = dados.get("videos") or []
    fortes = [v for v in videos if v.get("forte")]
    total = max(1, len(videos))
    n_fortes = max(1, len(fortes))
    freq_map = dados.get("frequencia") or {}
    autocomplete = {_norm(a) for a in (dados.get("autocomplete") or [])}
    trending = {_norm(t) for t in tendencias}

    saida = []
    for c in candidatas:
        tag = limpar_hashtag(c.get("tag"))
        if not tag:
            continue
        k = _norm(tag)
        relevancia = max(0.0, min(1.0, _num(c.get("relevancia"), 0.6)))
        origem = c.get("origem") or "ia"
        rotulo = None

        fortes_com = total_com = 0
        for key, reg in freq_map.items():
            if _bate(k, key):
                fortes_com = max(fortes_com, reg["fortes"])
                total_com = max(total_com, reg["total"])
                rotulo = rotulo or reg["rotulo"]

        if dados.get("disponivel") and videos:
            freq = fortes_com / n_fortes
            conc = total_com / total
        else:
            freq, conc = 0.5, 0.0  # neutro quando não há dado real

        if k in autocomplete or any(k in a or a in k for a in autocomplete if len(a) >= 5):
            relevancia = min(1.0, relevancia + 0.1)
            origem += "+autocomplete"
        if k in trending or any(k in t or t in k for t in trending if len(t) >= 5):
            relevancia = min(1.0, relevancia + 0.15)
            origem += "+tiktok"

        peso = max(0.0, min(1.0, _num(prioridades.get(tag) or prioridades.get(k), 0.0)))
        nota = (0.4 + 0.6 * freq) * relevancia * (1.0 - 0.5 * conc) * (1.0 + peso)

        saida.append({
            "tag": tag,
            "tipo": c.get("tipo") or "nicho",
            "relevancia": round(relevancia, 3),
            "frequencia_fortes": round(freq, 3),
            "concorrencia": round(conc, 3),
            "concorrencia_qtd": total_com,
            "frequencia_qtd": fortes_com,
            "prioridade_resultados": round(peso, 3),
            "nota": round(nota, 4),
            "origem": origem,
            "por_que": str(c.get("por_que") or "")[:120],
            "tag_youtube": rotulo,
        })

    saida.sort(key=lambda x: x["nota"], reverse=True)
    vistos = set()
    limpo = []
    for item in saida:
        k = _norm(item["tag"])
        if k in vistos:
            continue
        vistos.add(k)
        limpo.append(item)
    return limpo


def _num(valor, padrao=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def compor_hashtags(pontuadas, min_n=None, max_n=None):
    """Monta a mistura pedida: 1 ampla, 2 de nicho, 1 específica (3 a 5 no total)."""
    min_n = min_n or config.HASHTAGS_MIN
    max_n = max_n or config.HASHTAGS_MAX
    max_n = max(min_n, min(max_n, 5))

    por_tipo = {"amplo": [], "nicho": [], "especifico": []}
    for p in pontuadas:
        tipo = p["tipo"] if p["tipo"] in por_tipo else "nicho"
        por_tipo[tipo].append(p)

    ordem = (
        por_tipo["amplo"][:1]
        + por_tipo["nicho"][:2]
        + por_tipo["especifico"][:1]
        + por_tipo["nicho"][2:4]
        + por_tipo["amplo"][1:3]
        + por_tipo["especifico"][1:3]
    )
    escolhidas, vistas = [], set()
    for item in ordem:
        k = _norm(item["tag"])
        if k in vistas:
            continue
        vistas.add(k)
        escolhidas.append(item)
        if len(escolhidas) >= max_n:
            break
    if len(escolhidas) < min_n:
        for item in pontuadas:
            k = _norm(item["tag"])
            if k in vistas:
                continue
            vistas.add(k)
            escolhidas.append(item)
            if len(escolhidas) >= min_n:
                break
    return escolhidas


def montar_tags_youtube(pontuadas, dados, extras=None, max_chars=None, max_n=30):
    """Campo 'tags' do YouTube: frases curtas reais, no máximo 500 caracteres."""
    max_chars = max_chars or config.TAGS_MAX_CHARS
    candidatas = []
    for key, reg in sorted((dados.get("frequencia") or {}).items(),
                           key=lambda kv: kv[1]["fortes"], reverse=True):
        candidatas.append(reg["rotulo"])
    for t in extras or []:
        candidatas.append(str(t))
    for p in pontuadas:
        if p.get("tag_youtube"):
            candidatas.append(p["tag_youtube"])

    vistas, escolhidas = set(), []
    for t in candidatas:
        t = str(t).strip()
        if not t or len(t) > 45:
            continue
        k = _norm(t)
        if not k or k in vistas or k in NAO_USAR:
            continue
        vistas.add(k)
        escolhidas.append(t)
        if len(escolhidas) >= max_n:
            break

    final, usado = [], 0
    for t in escolhidas:
        adicional = len(t) + (2 if final else 0)
        if usado + adicional > max_chars:
            break
        final.append(t)
        usado += adicional
    return final


# ------------------------------------------------------------------ 7. gravação
def caminho_metadata(corte_id):
    return config.SAIDA_DIR / str(corte_id) / "metadata.json"


def salvar(metadata):
    destino = caminho_metadata(metadata["corte"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(metadata, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def carregar_metadata(corte_id):
    caminho = caminho_metadata(corte_id)
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def prioridades():
    try:
        d = json.loads(config.PRIORIDADES_JSON.read_text(encoding="utf-8"))
        return d.get("hashtags") or {}
    except Exception:
        return {}


def gerar(alvo, transcript=None, nicho=None, usar_youtube=None, on_log=None):
    """Ponto de entrada do Módulo 1. Devolve o metadata e grava metadata.json."""
    on_log = on_log or config.log
    nicho = nicho or config.NICHO
    corte = carregar_corte(alvo, transcript)
    on_log(f"hashtags: {corte['id']} (nicho={nicho}, {len(corte['texto'])} caracteres de transcricao)")

    dados_ia = candidatas_ia(corte, nicho, on_log)
    if dados_ia:
        candidatas = []
        for c in (dados_ia.get("candidatas") or [])[:config.IA_CANDIDATAS * 2]:
            candidatas.append({
                "tag": c.get("tag"),
                "tipo": str(c.get("tipo") or "nicho").lower(),
                "relevancia": _num(c.get("relevancia"), 0.6),
                "por_que": c.get("por_que"),
                "origem": "ia",
            })
        tags_ia = [str(t) for t in (dados_ia.get("tags") or [])]
        titulo_ia = str(dados_ia.get("titulo") or "").strip()
        descricao_ia = str(dados_ia.get("descricao") or "").strip()
        on_log(f"  IA: {len(candidatas)} candidatas")
    else:
        candidatas = _candidatas_fallback(corte, nicho, config.IA_CANDIDATAS)
        tags_ia, titulo_ia, descricao_ia = [], "", ""
        on_log(f"  sem IA: {len(candidatas)} candidatas (fallback)")

    usar_youtube = config.YT_ATIVO if usar_youtube is None else usar_youtube
    avisos = []
    if usar_youtube:
        try:
            yt = dados_youtube(nicho, on_log)
        except CotaExcedidaError as exc:
            yt = {"disponivel": False, "motivo": str(exc), "frequencia": {},
                  "videos": [], "fortes": 0, "total": 0, "autocomplete": [], "avisos": [str(exc)]}
            on_log(f"  YouTube: {exc} -> sem dados reais nesta rodada")
    else:
        yt = {"disponivel": False, "motivo": "desligado pelo usuario", "frequencia": {},
              "videos": [], "fortes": 0, "total": 0, "autocomplete": [], "avisos": []}
    avisos.extend(yt.get("avisos") or [])

    if yt.get("autocomplete"):
        vistos = {_norm(c["tag"]) for c in candidatas}
        for sug in yt["autocomplete"]:
            if len(candidatas) >= config.IA_CANDIDATAS + 20:
                break
            if _norm(sug) and _norm(sug) not in vistos:
                vistos.add(_norm(sug))
                candidatas.append({"tag": sug.replace(" ", ""), "tipo": "nicho",
                                   "relevancia": 0.45, "por_que": "autocomplete do YouTube",
                                   "origem": "autocomplete"})

    tendencias = tendencias_tiktok(on_log)
    pontuadas = pontuar(candidatas, yt, tendencias, prioridades())
    escolhidas = compor_hashtags(pontuadas)

    tags_yt = montar_tags_youtube(
        pontuadas, yt,
        extras=list(tags_ia) + [str(t) for t in (corte.get("tags_base") or [])],
    )
    if len(tags_yt) < 3:
        # sem API (ou API vazia): usa as hashtags escolhidas como palavras-chave
        vistos = {_norm(t) for t in tags_yt}
        for h in hashtags:
            t = h.lstrip("#")
            if _norm(t) and _norm(t) not in vistos:
                vistos.add(_norm(t))
                tags_yt.append(t)
            if len(tags_yt) >= 8:
                break

    hashtags = [p["tag"] for p in escolhidas]
    hashtags_tiktok = list(hashtags)
    for h in tendencias:
        if len(hashtags_tiktok) >= min(8, config.HASHTAGS_MAX + 3):
            break
        if _norm(h) not in {_norm(x) for x in hashtags_tiktok}:
            hashtags_tiktok.append(h)

    titulo = corte.get("titulo") or titulo_ia or (corte["hook"] or corte["texto"][:60])[:70]
    descricao = corte.get("descricao") or descricao_ia or corte["texto"][:400]

    metadata = {
        "corte": corte["id"],
        "gerado_em": config.agora(),
        "nicho": nicho,
        "titulo": titulo[:100],
        "descricao": descricao[:4900],
        "hashtags": hashtags,
        "hashtags_tiktok": hashtags_tiktok,
        "tags_youtube": ", ".join(tags_yt),
        "tags_youtube_lista": tags_yt,
        "tags_youtube_chars": len(", ".join(tags_yt)),
        "composicao": dict(Counter(p["tipo"] for p in escolhidas)),
        "candidatas": pontuadas,
        "fontes": {
            "youtube": {
                "disponivel": bool(yt.get("disponivel")),
                "motivo": yt.get("motivo", ""),
                "videos": yt.get("total", 0),
                "fortes": yt.get("fortes", 0),
                "tags_distintas": len(yt.get("frequencia") or {}),
                "autocomplete": (yt.get("autocomplete") or [])[:15],
            },
            "tiktok": tendencias,
            "ia": bool(dados_ia),
        },
        "origem": corte["transcript"],
        "inicio": corte["inicio"],
        "fim": corte["fim"],
        "avisos": avisos,
    }
    destino = salvar(metadata)
    on_log(f"  {len(hashtags)} hashtags: {' '.join(hashtags)}")
    on_log(f"  {len(tags_yt)} tags do YouTube ({metadata['tags_youtube_chars']} de "
           f"{config.TAGS_MAX_CHARS} caracteres)")
    on_log(f"  salvo em {destino}")
    return metadata
