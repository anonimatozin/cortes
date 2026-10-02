"""Linha de comando do módulo divulgacao.

Exemplos (a partir da raiz do projeto):
  python -m divulgacao doctor
  python -m divulgacao hashtags --corte 01_2tlZdonG59o_ALGO
  python -m divulgacao hashtags --todos
  python -m divulgacao grupos --buscas
  python -m divulgacao grupos --textos --plano 14
  python -m divulgacao grupos --postado "https://facebook.com/groups/xyz"
  python -m divulgacao registro add --corte 01_xxx --plataforma youtube --views 120
  python -m divulgacao registro relatorio
  python -m divulgacao tudo
"""

import argparse
import json
import sys
from pathlib import Path

from . import config, grupos, registro


def _log(msg):
    config.log(msg)


def _resolver_todos_cortes(apenas_sem_metadata=True, forcar=False):
    """Todos os cortes exportados que têm sidecar .json em clips/."""
    alvos = []
    for sidecar in sorted(config.CLIPS_DIR.glob("*.json")):
        if sidecar.name.startswith("."):
            continue
        try:
            dados = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            continue
        caminho = dados.get("path") or str(sidecar.with_suffix(".mp4"))
        if not Path(caminho).exists() and not sidecar.with_suffix(".mp4").exists():
            continue
        if not apenas_sem_metadata or forcar:
            alvos.append(caminho)
            continue
        from . import hashtags
        if hashtags.caminho_metadata(sidecar.stem).exists():
            continue
        alvos.append(caminho)
    return alvos


# ------------------------------------------------------------------- comandos
def cmd_doctor(args):
    ok = True

    def check(nome, fn):
        nonlocal ok
        try:
            detalhe = fn()
            _log(f"[OK ] {nome}" + (f" -> {detalhe}" if detalhe else ""))
        except Exception as exc:
            ok = False
            _log(f"[ERRO] {nome} -> {exc}")

    check("python", lambda: sys.version.split()[0])
    check("modo teste", lambda: "LIGADO (saida na pasta temporaria)" if config.MODO_TESTE else "desligado")
    check("integracao com cortes.py",
          lambda: "LIGADA" if config.ATIVO else "desligada (ativo: false no config.yaml)")
    check("yaml", lambda: __import__("yaml").__version__)
    check("pytrends (opcional)", lambda: __import__("pytrends").__version__
          if config.TRENDS_ATIVO else "desligado (config)")
    check("GROQ_API_KEY (IA)",
          lambda: "configurada" if config.GROQ_API_KEY else "vazia -> módulo roda com fallback")
    check("YOUTUBE_API_KEY",
          lambda: "configurada" if config.YOUTUBE_API_KEY else
          ("sem chave; usando OAuth do projeto" if (config.RAIZ / "tokens" / "youtube.json").exists()
           else "vazia -> sem dados reais de tags"))
    check("google-api-python-client", lambda: __import__("googleapiclient").__version__
          if hasattr(__import__("googleapiclient"), "__version__") else "instalado")
    check("transcricoes (source/)",
          lambda: f"{len(list(config.SOURCE_DIR.glob('*.transcript.json')))} arquivo(s)")
    check("cortes exportados (clips/)",
          lambda: f"{len(list(config.CLIPS_DIR.glob('*.json')))} sidecar(s)")
    check("grupos.csv",
          lambda: (f"{len(grupos.carregar())} grupo(s), "
                   f"{sum(1 for g in grupos.carregar() if grupos.aceita(g))} aceitam")
          if config.GRUPOS_CSV.exists() else "AUSENTE -> rode: python -m divulgacao grupos --buscas")
    check("tiktok_trending.txt",
          lambda: f"{len(config.TIKTOK_TRENDING.read_text(encoding='utf-8').splitlines())} linha(s)"
          if config.TIKTOK_TRENDING.exists() else "AUSENTE (sem problema, só perde o bônus do TikTok)")
    check("resultados.csv",
          lambda: f"{len(registro.carregar())} linha(s)" if config.RESULTADOS_CSV.exists()
          else "AUSENTE (criado no primeiro registro)")
    _log(f"flags: hashtags={config.MODULOS['hashtags']} grupos={config.MODULOS['grupos']} "
         f"registro={config.MODULOS['registro']} | nicho={config.NICHO}")
    for aviso in config.AVISOS:
        _log(f"[AVISO] {aviso}")
    return 0 if ok else 1


def cmd_hashtags(args):
    from . import hashtags

    if not config.MODULOS.get("hashtags", True):
        _log("módulo desligado (modulos.hashtags: false no config.yaml)")
        return 1

    nicho = args.nicho or config.NICHO
    if args.todos:
        alvos = _resolver_todos_cortes(apenas_sem_metadata=not args.force, forcar=args.force)
        if not alvos:
            _log("nenhum corte novo em clips/ (use --force para refazer todos)")
            return 0
        _log(f"{len(alvos)} corte(s) para processar")
        feitos, erros = 0, 0
        for alvo in alvos:
            try:
                hashtags.gerar(alvo, transcript=args.transcript, nicho=nicho,
                               usar_youtube=not args.sem_youtube, on_log=_log)
                feitos += 1
            except Exception as exc:
                erros += 1
                _log(f"  ERRO em {Path(alvo).name}: {exc}")
        _log(f"pronto: {feitos} ok, {erros} erro(s)")
        return 0 if feitos else 1

    if not args.corte:
        _log("informe --corte <id do corte> ou --todos")
        return 2
    try:
        hashtags.gerar(args.corte, transcript=args.transcript, nicho=nicho,
                       usar_youtube=not args.sem_youtube, on_log=_log)
    except Exception as exc:
        _log(f"ERRO: {exc}")
        return 1
    return 0


def cmd_grupos(args):
    if not config.MODULOS.get("grupos", True):
        _log("módulo desligado (modulos.grupos: false no config.yaml)")
        return 1

    if not args.buscas and not args.textos and not args.plano and not args.postado \
            and not args.status:
        args.buscas = args.textos = True
        args.plano = config.GRUPOS_DIAS_PLANO

    if args.buscas:
        grupos.gerar_buscas(args.nicho, on_log=_log)

    if args.status:
        grupos.status(on_log=_log)
        return 0

    if args.postado:
        grupos.marcar_postado(args.postado, data=args.data, on_log=_log)
        return 0

    metadata = None
    if args.corte:
        from . import hashtags
        metadata = hashtags.carregar_metadata(args.corte)
        if metadata is None:
            metadata = hashtags.gerar(args.corte, nicho=args.nicho, on_log=_log)

    if args.textos:
        grupos.gerar_textos(metadata=metadata, on_log=_log)

    if args.plano:
        try:
            grupos.montar_plano(dias=int(args.plano), on_log=_log)
        except ValueError:
            _log("--plano precisa de um número de dias")
            return 2
    return 0


def cmd_registro(args):
    if not config.MODULOS.get("registro", True):
        _log("módulo desligado (modulos.registro: false no config.yaml)")
        return 1

    if args.acao == "relatorio":
        registro.relatorio(on_log=_log)
        return 0
    if args.acao == "add":
        if not args.corte:
            _log("--corte é obrigatório")
            return 2
        registro.registrar(args.corte, hashtags=args.hashtags, plataforma=args.plataforma,
                           grupo=args.grupo, data=args.data, views=args.views,
                           curtidas=args.curtidas)
        _log(f"registrado: {args.corte} ({args.plataforma or 'sem plataforma'})")
        registro.relatorio(on_log=_log)
        return 0
    if args.acao == "views":
        if not args.corte:
            _log("--corte é obrigatório")
            return 2
        registro.atualizar_views(args.corte, plataforma=args.plataforma, grupo=args.grupo,
                                 views=args.views, curtidas=args.curtidas, data=args.data)
        _log(f"views atualizadas: {args.corte} -> {args.views}")
        registro.relatorio(on_log=_log)
        return 0
    return 2


def cmd_tudo(args):
    """Pipeline completo: hashtags dos cortes novos -> plano de grupos -> relatório."""
    rc = cmd_hashtags(argparse.Namespace(corte=None, todos=True, transcript=None,
                                         nicho=args.nicho, sem_youtube=args.sem_youtube,
                                         force=False))
    if config.MODULOS.get("grupos", True):
        grupos.gerar_buscas(args.nicho, on_log=_log)
        grupos.gerar_textos(on_log=_log)
        grupos.montar_plano(on_log=_log)
    if config.MODULOS.get("registro", True) and config.RESULTADOS_CSV.exists():
        registro.relatorio(on_log=_log)
    return rc


def cmd_limpar_cache(args):
    n = 0
    for p in config.CACHE_DIR.glob("*"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    _log(f"{n} arquivo(s) de cache removido(s)")
    return 0


# ------------------------------------------------------------------- parser
def montar_parser():
    p = argparse.ArgumentParser(prog="divulgacao",
                                description="Hashtags, divulgação em grupos e registro de resultados")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="chega dependências, chaves e arquivos")

    h = sub.add_parser("hashtags", help="Módulo 1: pesquisa de hashtags e tags")
    h.add_argument("--corte", default=None, help="id do corte (stem) ou caminho do .mp4/.json")
    h.add_argument("--todos", action="store_true", help="processa todos os cortes sem metadata")
    h.add_argument("--transcript", default=None, help="id do vídeo fonte se não achar sozinho")
    h.add_argument("--nicho", default=None)
    h.add_argument("--sem-youtube", action="store_true", help="não consulta a API (só IA/local)")
    h.add_argument("--force", action="store_true", help="refaz mesmo com metadata pronto")

    g = sub.add_parser("grupos", help="Módulo 2: buscas, textos e plano (sem postagem)")
    g.add_argument("--nicho", default=None)
    g.add_argument("--buscas", action="store_true", help="gera buscas_grupos.md")
    g.add_argument("--textos", action="store_true", help="gera 1 texto por grupo elegível")
    g.add_argument("--plano", nargs="?", const=str(config.GRUPOS_DIAS_PLANO), default=None,
                   help="monta plano_divulgacao.md com N dias (padrão 14)")
    g.add_argument("--postado", default=None, metavar="LINK", help="marca o grupo como postado hoje")
    g.add_argument("--data", default=None, help="data do post no formato aaaa-mm-dd")
    g.add_argument("--status", action="store_true", help="mostra o estado da fila")
    g.add_argument("--corte", default=None, help="usa o metadata deste corte nos textos")

    r = sub.add_parser("registro", help="Módulo 3: CSV de resultados e relatório")
    rsub = r.add_subparsers(dest="acao")
    rsub.add_parser("relatorio", help="gera relatorio_resultados.md e prioridades.json")
    for acao in ("add", "views"):
        a = rsub.add_parser(acao)
        a.add_argument("--corte", required=True)
        a.add_argument("--plataforma", default="", help="youtube|tiktok|instagram|facebook")
        a.add_argument("--grupo", default="", help="nome/link do grupo (se foi por grupo)")
        a.add_argument("--hashtags", default="", help='ex.: "#a #b #c"')
        a.add_argument("--views", type=int, default=0)
        a.add_argument("--curtidas", type=int, default=0)
        a.add_argument("--data", default=None, help="aaaa-mm-dd (padrão: hoje)")

    t = sub.add_parser("tudo", help="hashtags dos cortes novos + plano de grupos + relatório")
    t.add_argument("--nicho", default=None)
    t.add_argument("--sem-youtube", action="store_true")

    sub.add_parser("limpar-cache", help="apaga o cache do YouTube/cota")
    return p


def main(argv=None):
    config.unidade_do_sistema()
    parser = montar_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    handlers = {
        "doctor": cmd_doctor,
        "hashtags": cmd_hashtags,
        "grupos": cmd_grupos,
        "registro": cmd_registro,
        "tudo": cmd_tudo,
        "limpar-cache": cmd_limpar_cache,
    }
    if args.cmd == "registro" and not getattr(args, "acao", None):
        _log("use: python -m divulgacao registro {add|views|relatorio}")
        return 2
    try:
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        _log("interrompido")
        return 130
    except Exception as exc:
        _log(f"ERRO: {exc}")
        return 1
