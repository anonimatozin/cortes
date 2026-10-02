"""MÓDULO 3 — registro de resultados.

  resultados.csv  -> corte, hashtags, plataforma, grupo, data, views, curtidas
  relatorio_* .md -> o que trouxe resultado
  prioridades.json -> pesos que o Módulo 1 passa a considerar nas próximas rodadas

Nada aqui chama API de rede: views/curtidas são informadas por você (ou coladas
do YouTube Studio / TikTok / Facebook) para comparar de forma honesta.
"""

import csv
import json
import re

from . import config

CABECALHO = ["corte", "hashtags", "plataforma", "grupo", "data", "views", "curtidas"]


def _delimitador(texto):
    primeira = texto.splitlines()[0] if texto.splitlines() else ""
    return ";" if primeira.count(";") > primeira.count(",") else ","


def _int(valor, padrao=0):
    if valor is None:
        return padrao
    if isinstance(valor, int):
        return valor
    txt = str(valor).strip().lower().replace(" ", "")
    if not txt:
        return padrao
    multiplicador = 1
    if txt.endswith(("k", "mil")):
        multiplicador, txt = 1000, txt.rstrip("k").replace("mil", "")
    elif txt.endswith("m"):
        multiplicador, txt = 1000000, txt[:-1]
    txt = txt.rstrip("k").replace("mil", "") if multiplicador > 1 else txt
    if "," in txt:
        partes = txt.split(",")
        if len(partes) == 2 and len(partes[1]) in (1, 2):
            txt = txt.replace(",", ".")
        else:
            txt = txt.replace(",", "").replace(".", "")
    else:
        txt = txt.replace(".", "")
    try:
        return int(float(txt) * multiplicador)
    except ValueError:
        return padrao


def carregar():
    caminho = config.RESULTADOS_CSV
    if not caminho.exists():
        return []
    texto = caminho.read_text(encoding="utf-8-sig")
    if not texto.strip():
        return []
    leitor = csv.DictReader(texto.splitlines(), delimiter=_delimitador(texto))
    linhas = []
    for raw in leitor:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        row.setdefault("corte", "")
        row.setdefault("hashtags", "")
        row.setdefault("plataforma", "")
        row.setdefault("grupo", "")
        row.setdefault("data", "")
        row["views"] = _int(row.get("views"))
        row["curtidas"] = _int(row.get("curtidas"))
        linhas.append(row)
    return linhas


def salvar(linhas):
    caminho = config.RESULTADOS_CSV
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECALHO, delimiter=",")
        w.writeheader()
        for r in linhas:
            w.writerow({k: r.get(k, "") for k in CABECALHO})
    tmp.replace(caminho)
    return caminho


def registrar(corte, hashtags=None, plataforma="", grupo="", data=None, views=0, curtidas=0):
    """Acrescenta (ou atualiza) uma linha do resultados.csv."""
    if isinstance(hashtags, (list, tuple)):
        hashtags = " ".join(str(h) for h in hashtags if h)
    data = data or config.hoje()
    linhas = carregar()
    chave = (str(corte).strip().lower(), str(plataforma).strip().lower(),
             str(grupo).strip().lower())
    for r in linhas:
        if (r["corte"].lower(), r["plataforma"].lower(), r["grupo"].lower()) == chave:
            r["hashtags"] = hashtags or r["hashtags"]
            r["data"] = data
            r["views"] = max(_int(r["views"]), _int(views))
            r["curtidas"] = max(_int(r["curtidas"]), _int(curtidas))
            salvar(linhas)
            return r
    nova = {"corte": str(corte), "hashtags": str(hashtags or ""),
            "plataforma": str(plataforma), "grupo": str(grupo), "data": data,
            "views": _int(views), "curtidas": _int(curtidas)}
    linhas.append(nova)
    salvar(linhas)
    return nova


def atualizar_views(corte, plataforma="", grupo="", views=None, curtidas=None, data=None):
    """Sobrescreve views/curtidas de uma linha já registrada."""
    linhas = carregar()
    chave = (str(corte).strip().lower(), str(plataforma).strip().lower(),
             str(grupo).strip().lower())
    for r in linhas:
        if (r["corte"].lower(), r["plataforma"].lower(), r["grupo"].lower()) == chave:
            if views is not None:
                r["views"] = _int(views)
            if curtidas is not None:
                r["curtidas"] = _int(curtidas)
            r["data"] = data or config.hoje()
            salvar(linhas)
            return r
    return registrar(corte, plataforma=plataforma, grupo=grupo, views=views or 0,
                     curtidas=curtidas or 0, data=data)


def registrar_de_metadata(metadata, plataforma="", grupo="", views=0, curtidas=0):
    """Atalho: registra o corte com as hashtags que o Módulo 1 escolheu."""
    return registrar(
        corte=metadata.get("corte", ""),
        hashtags=metadata.get("hashtags") or [],
        plataforma=plataforma,
        grupo=grupo,
        views=views,
        curtidas=curtidas,
    )


def _hashtags_da_linha(linha):
    brutas = re.split(r"[\s,;]+", linha.get("hashtags") or "")
    return [h if h.startswith("#") else f"#{h}" for h in brutas if h.strip()]


def _agregar(linhas, campo):
    mapa = {}
    for r in linhas:
        if campo == "hashtags":
            chaves = _hashtags_da_linha(r)
        else:
            chave = (r.get("grupo") or "").strip()
            if not chave:
                chave = r.get("plataforma") or "(sem grupo)"
            chaves = [chave]
        for k in chaves:
            reg = mapa.setdefault(k, {"chave": k, "amostras": 0, "views": 0, "curtidas": 0})
            reg["amostras"] += 1
            reg["views"] += r["views"]
            reg["curtidas"] += r["curtidas"]
    for reg in mapa.values():
        reg["views_medio"] = reg["views"] // max(1, reg["amostras"])
        reg["curtidas_media"] = reg["curtidas"] // max(1, reg["amostras"])
    return sorted(mapa.values(), key=lambda x: (-x["views"], -x["amostras"]))


def priorizar(linhas):
    """Converte o histórico em pesos 0..1 que o Módulo 1 soma na nota."""
    hashtags = _agregar(linhas, "hashtags")
    grupos = _agregar(linhas, "grupo")
    validas = [h for h in hashtags if h["amostras"] >= config.REG_MIN_AMOSTRAS]
    maior = max([h["views_medio"] for h in validas], default=0) or 1
    pesos_hashtags = {}
    for h in validas:
        pesos_hashtags[h["chave"].lower()] = round(min(1.0, h["views_medio"] / maior), 3)

    validos = [g for g in grupos if g["amostras"] >= config.REG_MIN_AMOSTRAS and not g["chave"].startswith("(")]
    maior_g = max([g["views_medio"] for g in validos], default=0) or 1
    pesos_grupos = {}
    for g in validos:
        pesos_grupos[g["chave"].lower()] = round(min(1.0, g["views_medio"] / maior_g), 3)

    dados = {
        "atualizado_em": config.agora(),
        "base": str(config.RESULTADOS_CSV),
        "amostras": len(linhas),
        "min_amostras": config.REG_MIN_AMOSTRAS,
        "hashtags": pesos_hashtags,
        "grupos": pesos_grupos,
        "ranking_hashtags": hashtags,
        "ranking_grupos": grupos,
    }
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.PRIORIDADES_JSON.write_text(
        json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


def _tabela(itens, cabecalho):
    linhas = [f"| {cabecalho[0]} | {cabecalho[1]} | {cabecalho[2]} | {cabecalho[3]} |",
              "|---|---:|---:|---:|"]
    for it in itens:
        linhas.append(f"| {it['chave']} | {it['amostras']} | {it['views']} | {it['views_medio']} |")
    if len(itens) < 2:
        linhas.append("| _(sem dados suficientes)_ | | | |")
    return linhas


def relatorio(on_log=None):
    """Gera relatorio_resultados.md + prioridades.json. Devolve o dict de pesos."""
    on_log = on_log or config.log
    linhas = carregar()
    priorizar(linhas)

    hashtags = _agregar(linhas, "hashtags")
    grupos = [g for g in _agregar(linhas, "grupo") if not g["chave"].startswith("(")]
    mapa_plat = {}
    for r in linhas:
        chave = (r.get("plataforma") or "(sem)").strip() or "(sem)"
        reg = mapa_plat.setdefault(chave, {"chave": chave, "amostras": 0,
                                           "views": 0, "curtidas": 0})
        reg["amostras"] += 1
        reg["views"] += r["views"]
        reg["curtidas"] += r["curtidas"]
    for reg in mapa_plat.values():
        reg["views_medio"] = reg["views"] // max(1, reg["amostras"])
        reg["curtidas_media"] = reg["curtidas"] // max(1, reg["amostras"])
    plataformas = sorted(mapa_plat.values(), key=lambda x: -x["views"])
    top_h = hashtags[: config.REG_MAX_LINHAS]
    top_g = grupos[: config.REG_MAX_LINHAS]

    total_views = sum(r["views"] for r in linhas)
    md = [
        f"# Relatório de resultados — {config.agora()}",
        "",
        f"- linhas registradas: **{len(linhas)}**",
        f"- views somadas: **{total_views:,}**".replace(",", "."),
        f"- mínimo de amostras para recomendar: {config.REG_MIN_AMOSTRAS}",
        "",
        "## Hashtags que mais trouxeram resultado",
        "",
        *_tabela(top_h, ("hashtag", "amostras", "views", "views/média")),
        "",
        "## Grupos que mais trouxeram resultado",
        "",
        *_tabela(top_g, ("grupo", "amostras", "views", "views/média")),
        "",
        "## Plataformas",
        "",
        *_tabela([p for p in plataformas[:10]], ("grupo/plataforma", "amostras", "views", "views/média")),
        "",
        "## O que priorizar nas próximas execuções",
        "",
    ]
    boas = [h for h in hashtags if h["amostras"] >= config.REG_MIN_AMOSTRAS][:5]
    ruins = [h for h in hashtags if h["amostras"] >= config.REG_MIN_AMOSTRAS][-3:]
    if boas:
        md.append("- **priorizar hashtags:** " + ", ".join(h["chave"] for h in boas))
    if ruins:
        md.append("- **evitar/revisar:** " + ", ".join(h["chave"] for h in ruins))
    if not hashtags:
        md.append("- sem dados ainda. Registre views com: "
                  "`python -m divulgacao registro add --corte <id> --plataforma youtube --views 120`")
    if top_g:
        md.append("- **priorizar grupos:** " + ", ".join(g["chave"] for g in top_g[:3]))
    md += ["", f"Pesos gravados em `{config.PRIORIDADES_JSON}` "
              "e somados na nota do Módulo 1 na próxima rodada.", ""]

    config.RELATORIO_MD.write_text("\n".join(md), encoding="utf-8")
    on_log(f"  relatorio: {len(linhas)} linhas -> {config.RELATORIO_MD}")
    on_log(f"  {len(hashtags)} hashtag(s) e {len(grupos)} grupo(s) com peso salvo")
    return {"linhas": len(linhas), "hashtags": len(hashtags), "grupos": len(grupos)}
