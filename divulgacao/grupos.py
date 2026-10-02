"""MÓDULO 2 — divulgação em grupos do Facebook.

O QUE ESTE MÓDULO NÃO FAZ (de propósito):
  A Meta aposentou a Groups API em 22/04/2024. Nenhuma ferramenta de terceiros
  publica em grupos automaticamente. Robô de navegador (Selenium etc.) finge ser
  você, viola os termos da Meta e termina em bloqueio de postagem ou banimento.
  Aqui não existe automação de login nem de publicação — apenas preparação.

O QUE ELE FAZ:
  1. gera as buscas certas para você encontrar grupos no Facebook;
  2. lê grupos.csv (nome, link, tema, aceita_divulgacao, regras, ultima_postagem);
  3. escreve UM texto por grupo, natural e diferente, respeitando as regras;
  4. monta plano_divulgacao.md: máx. 2 grupos/dia, 7 dias de intervalo no mesmo
     grupo, texto nunca repetido — você copia e publica (ou usa o agendador de
     notificação do próprio Facebook).
  Ideia melhor: crie uma Página para o canal. Páginas aceitam agendamento,
  inclusive de Reels, e aí sim dá para publicar sem tocar em nada.
"""

import csv
import hashlib
import json
import re
from pathlib import Path

from . import config, llm

COLUNAS = ["nome", "link", "tema", "aceita_divulgacao", "regras", "ultima_postagem"]

BUSCAS_POR_NICHO = {
    "podcast": ["podcast brasil", "cortes de podcast", "podcast humor", "entrevistas podcast",
                "podcast viral", "clip podcast"],
    "games": ["gameplay brasil", "clips de jogos", "gamer brasil", "twitch clips brasil",
              "montagens de jogos", "meme de jogo"],
    "minecraft": ["minecraft brasil", "minecraft gameplay", "minecraft construção",
                  "clips minecraft", "minecraft survival"],
    "futebol": ["futebol brasil", "gols da semana", "resumo de jogo", "torcida",
                "campeonato brasileiro", "futebol memes"],
    "tecnologia": ["tecnologia brasil", "inteligência artificial", "curiosidades técnicas",
                   "notícias de tech", "programação brasil"],
    "politica": ["política brasil", "debate político", "notícias brasileiras",
                 "opinião política", "eleições brasil"],
    "entretenimento": ["entretenimento brasil", "meme brasileiro", "humor brasil",
                       "celebridades brasil", "novelas e TV"],
    "default": ["brasil", "cortes", "vídeos virais", "conteúdo brasileiro",
                "YouTubers brasil", "TikTok brasil"],
}


# --------------------------------------------------------------- leitura CSV
def _delimitador(texto):
    primeira = texto.splitlines()[0] if texto.splitlines() else ""
    return ";" if primeira.count(";") >= primeira.count(",") else ","


def carregar():
    """Lê grupos.csv. Devolve lista de dicts com as 6 colunas (+ extras)."""
    caminho = config.GRUPOS_CSV
    if not caminho.exists():
        return []
    texto = caminho.read_text(encoding="utf-8-sig")
    if not texto.strip():
        return []
    leitor = csv.DictReader(texto.splitlines(), delimiter=_delimitador(texto))
    grupos = []
    for i, linha in enumerate(leitor, start=2):
        registro = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()
                    if k is not None}
        if not any(registro.values()):
            continue
        registro.setdefault("nome", "")
        registro.setdefault("link", "")
        registro.setdefault("tema", "")
        registro.setdefault("aceita_divulgacao", "")
        registro.setdefault("regras", "")
        registro.setdefault("ultima_postagem", "")
        if not registro["nome"] and not registro["link"]:
            config.log(f"  linha {i} do CSV sem nome/link, ignorada")
            continue
        if not registro["link"]:
            registro["link"] = f"(sem link) {registro['nome']}"
        registro.setdefault("_linha", i)
        grupos.append(registro)
    return grupos


def salvar_csv(grupos):
    """Regrava grupos.csv preservando a ordem das colunas."""
    caminho = config.GRUPOS_CSV
    caminho.parent.mkdir(parents=True, exist_ok=True)
    extras = []
    for g in grupos:
        for k in g:
            if not k.startswith("_") and k not in COLUNAS and k not in extras:
                extras.append(k)
    campos = COLUNAS + extras
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter=",", extrasaction="ignore")
        w.writeheader()
        for g in grupos:
            w.writerow({k: g.get(k, "") for k in campos})
    tmp.replace(caminho)
    return caminho


def aceita(grupo):
    return str(grupo.get("aceita_divulgacao", "")).strip().lower() in (
        "sim", "s", "yes", "y", "1", "true", "on")


# --------------------------------------------------------------------- estado
def _carregar_estado():
    try:
        d = json.loads(config.ESTADO_GRUPOS_JSON.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("textos", {})
            d.setdefault("hashes", [])
            d.setdefault("planos", {})
            return d
    except Exception:
        pass
    return {"textos": {}, "hashes": [], "planos": {}}


def _salvar_estado(estado):
    config.ESTADO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.ESTADO_GRUPOS_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(config.ESTADO_GRUPOS_JSON)


def _hash(texto):
    normal = re.sub(r"\s+", " ", str(texto)).strip().lower()
    return hashlib.sha1(normal.encode("utf-8")).hexdigest()[:16]


def _dias_desde(data):
    """Dias desde dd/mm/aaaa ou aaaa-mm-dd. -1 quando não dá para entender."""
    if not data:
        return -1
    data = str(data).strip()
    import datetime
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            d = datetime.datetime.strptime(data.split(" ")[0], formato).date()
            return (datetime.date.today() - d).days
        except ValueError:
            continue
    return -1


# ------------------------------------------------------- buscas sugeridas
def _chave_nicho(nicho):
    """'Minecraft Brasil' -> 'minecraftbrasil' (mesma normalização usada nas chaves)."""
    return re.sub(r"[^a-z0-9]", "", str(nicho or "").lower())


def _buscas(nicho):
    chave = _chave_nicho(nicho) or "default"
    lista = BUSCAS_POR_NICHO.get(chave) or BUSCAS_POR_NICHO["default"]
    extra = BUSCAS_POR_NICHO.get(chave)
    if not extra and nicho:
        lista = [nicho] + BUSCAS_POR_NICHO["default"][:4]
    saida = []
    for q in lista:
        consulta = f'"{q}" grupos'
        link = ("https://www.facebook.com/search/groups/?q="
                + re.sub(r"\s+", "%20", consulta))
        saida.append({"consulta": consulta, "link": link})
    return saida


def gerar_buscas(nicho=None, on_log=None):
    on_log = on_log or config.log
    nicho = nicho or config.NICHO
    itens = _buscas(nicho)
    linhas = [
        f"# Grupos para procurar — nicho: {nicho}",
        "",
        "Cole cada busca no campo de pesquisa do Facebook (aba **Grupos**), entre nos que "
        "fizerem sentido e adicione o link deles em `divulgacao/grupos.csv`.",
        "",
        "| # | Busca sugerida | Atalho |",
        "|---|----------------|--------|",
    ]
    for i, item in enumerate(itens, start=1):
        linhas.append(f"| {i} | {item['consulta']} | [abrir no Facebook]({item['link']}) |")
    linhas += ["", "Depois de colar os links, rode: `python -m divulgacao grupos --textos --plano`", ""]
    config.BUSCAS_MD.write_text("\n".join(linhas), encoding="utf-8")
    on_log(f"  {len(itens)} buscas em {config.BUSCAS_MD}")

    if not config.GRUPOS_CSV.exists():
        salvar_csv([])
        on_log(f"  {config.GRUPOS_CSV.name} criado (só cabeçalho) — cole os links dos grupos")
    return itens


# ------------------------------------------------------------ geração de textos
SISTEMA_GRUPOS = (
    "Voce escreve publicacoes de Facebook para GRUPOS brasileiros. Seu texto parece gente "
    "falando, nunca propaganda. Responda SEMPRE em JSON valido."
)

REGRAS_ESCRITA = """REGRAS DE ESCRITA (obrigatório):
- 2 a 4 frases, no máximo LIMITE caracteres.
- Abra com CONTEXTO real sobre o assunto do vídeo (história, dúvida, curiosidade).
- Feche com UMA pergunta simples que convide a responder.
- Proibido: "inscreva-se", "link na bio", "segue lá", "compartilhe", "olha meu canal",
  cobrança de engajamento, mais de 1 emoji, mais de 2 hashtags.
- Português do Brasil, tom coloquial, sem clichê de vendor.
- O texto precisa ser ÚNICO: nada igual ao que já foi escrito para os outros grupos.
- Se houver link do vídeo, coloque no final numa linha sozinha.
Devolve JSON: {"texto": "..." }"""

TEMPLATES = [
    "Vi um corte sobre {assunto} e fiquei pensando: {detalhe}. "
    "Vocês já tinham visto isso antes?\n{link}",
    "Tava vendo umas coisas sobre {assunto} e esse trecho me pegou: {detalhe}. "
    "O que vocês acham disso?\n{link}",
    "Assunto {assunto} de novo na roda — {detalhe}. "
    "Concordam ou é caso de discordar?\n{link}",
    "Curti um corte que fala de {assunto}: {detalhe}. "
    "Alguém aqui já passou por isso?\n{link}",
    "Pergunta rápida sobre {assunto}: {detalhe}. "
    "Qual é a sua leitura?\n{link}",
]
PERGUNTAS = [
    "Vocês concordam?", "Já tinham visto isso?", "O que vocês acham?",
    "Faz sentido ou não?", "Alguém aqui entende mais disso?",
]


def _assunto_de(metadata):
    titulo = (metadata.get("titulo") or "").strip()
    if titulo:
        return titulo[:80]
    texto = (metadata.get("descricao") or "").strip()
    return (texto.split(".")[0][:80] if texto else config.NICHO)


def _detalhe_de(metadata):
    desc = (metadata.get("descricao") or "").strip()
    if desc:
        return desc.split(".")[0][:160]
    hashtags = " ".join(metadata.get("hashtags") or [])
    return hashtags or "o tema do vídeo"


def _fallback_texto(grupo, metadata, tentativa):
    """Sem IA: template determinístico, único por grupo e por tentativa."""
    assunto = _assunto_de(metadata)
    detalhe = _detalhe_de(metadata)
    i = (int(_hash(grupo.get("link") or grupo.get("nome"))[:8], 16) + tentativa) % len(TEMPLATES)
    texto = TEMPLATES[i].format(assunto=assunto, detalhe=detalhe, link="")
    texto = texto.replace("\n\n", "\n").strip()
    if tentativa:
        texto = f"{texto}\n\n{PERGUNTAS[tentativa % len(PERGUNTAS)]}"
    return texto[:config.GRUPOS_TAMANHO_TEXTO]


def _texto_ia(grupo, metadata, anteriores, tentativa):
    link = (metadata.get("link_video") or "").strip()
    user = (
        f"Grupo: {grupo.get('nome')}\n"
        f"Tema do grupo: {grupo.get('tema') or '(nao informado)'}\n"
        f"Regras do grupo: {grupo.get('regras') or '(nao informadas)'}\n"
        f"Link do video: {link or '(sem link ainda)'}\n\n"
        f"Video:\n  titulo: {metadata.get('titulo','')}\n"
        f"  descricao: {metadata.get('descricao','')}\n"
        f"  hashtags: {' '.join(metadata.get('hashtags') or [])}\n"
        f"  nicho: {metadata.get('nicho', config.NICHO)}\n\n"
        f"Textos ja escritos para OUTROS grupos (naao repita a ideia nem a frase):\n"
        + ("\n".join(f"  - {t[:160]}" for t in anteriores[-5:]) or "  (nenhum)")
        + "\n\nVariacao desta vez: " + ("reformule por completo" if tentativa == 0
                                         else f"reescrita {tentativa + 1}, outra abertura")
        + "\n" + REGRAS_ESCRITA.replace("LIMITE", str(config.GRUPOS_TAMANHO_TEXTO))
    )
    dados = llm.chat_json(user, system=SISTEMA_GRUPOS, max_tokens=700, temperatura=0.8)
    texto = str(dados.get("texto") or "").strip()
    return texto


def _limitar(texto, link):
    texto = re.sub(r"[ \t]+\n", "\n", texto).strip()
    limite = config.GRUPOS_TAMANHO_TEXTO
    if len(texto) > limite:
        corte = texto[:limite].rsplit(" ", 1)[0].rstrip(",.;")
        texto = corte + "…"
    if link and link not in texto:
        texto = f"{texto}\n{link}".strip()
    return texto


def gerar_textos(metadata=None, grupos=None, limite=None, on_log=None):
    """Gera um texto único para cada grupo elegível. Devolve quantos foram criados."""
    on_log = on_log or config.log
    grupos = grupos if grupos is not None else carregar()
    if not grupos:
        on_log("  nenhum grupo em grupos.csv (rode: python -m divulgacao grupos --buscas)")
        return 0
    if metadata is None:
        metadata = _ultimo_metadata()
    if metadata is None:
        on_log("  nenhum metadata.json em saida/ (rode antes: python -m divulgacao hashtags --todos)")
        return 0

    estado = _carregar_estado()
    textos = estado["textos"]
    hashes = set(estado["hashes"])
    pendentes = sum(1 for t in textos.values() if t.get("status") == "pendente")
    limite = limite or max(config.GRUPOS_MAX_POR_DIA * config.GRUPOS_DIAS_PLANO - pendentes, 0)
    if limite <= 0:
        on_log("  fila de textos cheia, nada a gerar")
        return 0

    anteriores = [t["texto"] for t in textos.values() if t.get("texto")]
    criados = 0
    for g in grupos:
        if criados >= limite:
            break
        chave = g["link"]
        existente = textos.get(chave)
        if existente and existente.get("status") in ("pendente", "planejado", "postado"):
            continue
        if not aceita(g):
            continue
        if _dias_desde(g.get("ultima_postagem")) >= 0 and \
                _dias_desde(g.get("ultima_postagem")) < config.GRUPOS_DIAS_ENTRE:
            continue

        texto, origem = None, "fallback"
        link_video = str(metadata.get("link_video") or "").strip()
        if llm.disponivel():
            for tentativa in range(3):
                try:
                    cand = _texto_ia(g, metadata, anteriores, tentativa)
                except Exception as exc:
                    on_log(f"  IA falhou em {g['nome']}: {exc}")
                    break
                if not cand:
                    continue
                cand = _limitar(cand, link_video)
                h = _hash(cand)
                if h in hashes or any(h == _hash(a) for a in anteriores):
                    continue
                texto, origem = cand, "ia"
                hashes.add(h)
                anteriores.append(cand)
                break
        if texto is None:
            for tentativa in range(3):
                cand = _limitar(_fallback_texto(g, metadata, tentativa), link_video)
                h = _hash(cand)
                if h not in hashes and all(h != _hash(a) for a in anteriores):
                    texto, origem = cand, "template"
                    hashes.add(h)
                    anteriores.append(cand)
                    break

        if texto is None:
            on_log(f"  nao consegui texto unico para {g['nome']}")
            continue

        textos[chave] = {
            "nome": g["nome"],
            "tema": g.get("tema", ""),
            "regras": g.get("regras", ""),
            "texto": texto,
            "hash": _hash(texto),
            "origem": origem,
            "corte": metadata.get("corte", ""),
            "gerado_em": config.agora(),
            "status": "pendente",
            "data_planejada": None,
            "data_postagem": g.get("ultima_postagem") or None,
        }
        criados += 1
        on_log(f"  texto pronto [{origem}] {g['nome']} ({len(texto)} chars)")

    estado["hashes"] = sorted(hashes)[-500:]
    _salvar_estado(estado)
    if criados:
        on_log(f"  {criados} texto(s) na fila")
    return criados


def _ultimo_metadata():
    """Pega o metadata.json mais recente de saida/."""
    candidatos = sorted(config.SAIDA_DIR.glob("*/metadata.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidatos:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def _cooldown_ok(grupo, estado, data):
    """Grupo livre nessa data? (7 dias desde o último post E sem plano na janela)."""
    dias = _dias_desde(grupo.get("ultima_postagem"))
    if dias >= 0 and dias < config.GRUPOS_DIAS_ENTRE:
        return False
    reg = estado["textos"].get(grupo["link"]) or {}
    postado = reg.get("data_postagem")
    if postado:
        d = _dias_desde(postado)
        if d >= 0 and d < config.GRUPOS_DIAS_ENTRE:
            return False
    return True


# ------------------------------------------------------------------- plano
def montar_plano(dias=None, on_log=None):
    """Monta plano_divulgacao.md: máx. 2 por dia, 7 dias de intervalo, sem repetição."""
    on_log = on_log or config.log
    dias = dias or config.GRUPOS_DIAS_PLANO
    grupos = carregar()
    por_link = {g["link"]: g for g in grupos}
    estado = _carregar_estado()
    textos = estado["textos"]

    pendentes = [(link, t) for link, t in textos.items()
                 if t.get("status") == "pendente" and t.get("texto")]
    if not pendentes:
        on_log("  nenhum texto pendente (rode: python -m divulgacao grupos --textos)")
        return None

    # respeita o cooldown do CSV mesmo que o texto já exista
    elegiveis, em_cooldown = [], []
    for link, t in pendentes:
        g = por_link.get(link) or {"link": link, "nome": t.get("nome", ""),
                                   "ultima_postagem": t.get("data_postagem") or ""}
        if _cooldown_ok(g, estado, None):
            elegiveis.append((link, t, g))
        else:
            em_cooldown.append((link, t, g))

    plano = {}
    usados_no_dia = {}
    ainda = []
    for i in range(dias):
        data = config.dia_mas(i)
        restantes = config.GRUPOS_MAX_POR_DIA - len(plano.get(data, []))
        if restantes <= 0:
            continue
        for link, t, g in elegiveis:
            if restantes <= 0:
                break
            if link in usados_no_dia:
                continue
            plano.setdefault(data, []).append({"link": link, "texto": t, "grupo": g})
            usados_no_dia[link] = data
            restantes -= 1
    for link, t, g in elegiveis:
        if link not in usados_no_dia:
            ainda.append({"link": link, "texto": t, "grupo": g})

    # grava o estado com o plano e limpa a fila
    for data, itens in plano.items():
        estado["planos"][data] = [x["link"] for x in itens]
        for item in itens:
            reg = textos.get(item["link"])
            if reg:
                reg["status"] = "planejado"
                reg["data_planejada"] = data
    _salvar_estado(estado)

    linhas = [
        f"# Plano de divulgação — gerado em {config.agora()}",
        "",
        f"Limites: **{config.GRUPOS_MAX_POR_DIA} grupos por dia** · "
        f"**{config.GRUPOS_DIAS_ENTRE} dias** entre posts no mesmo grupo · "
        "texto nunca repetido.",
        "",
        "> Publique você mesmo (o Facebook não permite mais postagem por API). "
        "Dica: use o agendador de notificação do Facebook ou crie uma **Página** "
        "para o canal — Páginas aceitam agendamento, inclusive de Reels.",
        "",
    ]
    total = 0
    for i in range(dias):
        data = config.dia_mas(i)
        itens = plano.get(data) or []
        if not itens:
            continue
        total += len(itens)
        linhas += [f"## {data} ({len(itens)} de {config.GRUPOS_MAX_POR_DIA})", ""]
        for n, item in enumerate(itens, start=1):
            g = item["grupo"]
            t = item["texto"]
            regras = (g.get("regras") or "").strip()
            linhas += [
                f"### {n}. {g.get('nome') or t.get('nome')}",
                f"- Grupo: {item['link']}",
                f"- Tema: {g.get('tema') or t.get('tema') or '-'}",
            ]
            if regras:
                linhas.append(f"- Regras do grupo: {regras}")
            linhas += [
                f"- Corte: {t.get('corte') or '-'}",
                "",
                "**Texto para copiar:**",
                "",
                "> " + t["texto"].replace("\n", "\n> "),
                "",
                "_ao publicar, marque como postado:_ "
                f"`python -m divulgacao grupos --postado \"{item['link']}\"`",
                "",
            ]
    if ainda:
        linhas += [f"## Sobraram {len(ainda)} texto(s) para os próximos dias", ""]
        for item in ainda:
            linhas.append(f"- {item['grupo'].get('nome')}: aguardando cooldown/limite")
        linhas.append("")

    if em_cooldown:
        linhas += [f"## Em cooldown ({len(em_cooldown)}) — faltam {config.GRUPOS_DIAS_ENTRE} dias", ""]
        for link, t, g in em_cooldown:
            dias = _dias_desde(g.get("ultima_postagem") or t.get("data_postagem"))
            falta = max(0, config.GRUPOS_DIAS_ENTRE - dias) if dias >= 0 else config.GRUPOS_DIAS_ENTRE
            linhas.append(f"- {g.get('nome') or t.get('nome')}: último post "
                          f"{g.get('ultima_postagem') or t.get('data_postagem') or '?'} "
                          f"(faltam {falta} dia(s))")
        linhas.append("")

    rejeitados = [g for g in grupos if not aceita(g)]
    if rejeitados:
        linhas += [f"## Ignorados ({len(rejeitados)}) — aceita_divulgacao != sim", ""]
        linhas += [f"- {g['nome']}" for g in rejeitados]
        linhas.append("")

    config.PLANO_MD.write_text("\n".join(linhas), encoding="utf-8")
    on_log(f"  plano: {total} publicacao(oes) em {dias} dias -> {config.PLANO_MD}")
    return config.PLANO_MD


def marcar_postado(link, data=None, on_log=None):
    """Você publicou? Marca aqui para o cooldown de 7 dias começar a contar."""
    on_log = on_log or config.log
    data = data or config.hoje()
    estado = _carregar_estado()
    reg = estado["textos"].get(link)
    if reg is None:
        estado["textos"][link] = {"nome": link, "texto": "", "hash": "",
                                  "status": "postado", "data_postagem": data}
    else:
        reg["status"] = "postado"
        reg["data_postagem"] = data
        reg["data_planejada"] = None
    _salvar_estado(estado)

    grupos = carregar()
    alterado = False
    for g in grupos:
        if g["link"] == link:
            g["ultima_postagem"] = data
            alterado = True
    if alterado:
        salvar_csv(grupos)
    on_log(f"  {link} marcado como postado em {data}")
    return data


def status(on_log=None):
    on_log = on_log or config.log
    grupos = carregar()
    estado = _carregar_estado()
    textos = estado["textos"]
    cont = {"pendente": 0, "planejado": 0, "postado": 0}
    for t in textos.values():
        cont[t.get("status", "pendente")] = cont.get(t.get("status", "pendente"), 0) + 1
    on_log(f"  grupos no CSV: {len(grupos)} (aceitam: {sum(1 for g in grupos if aceita(g))})")
    on_log(f"  textos: {cont['pendente']} pendente(s), {cont['planejado']} planejado(s), "
           f"{cont['postado']} postado(s)")
    if config.PLANO_MD.exists():
        on_log(f"  plano: {config.PLANO_MD}")
    return cont
