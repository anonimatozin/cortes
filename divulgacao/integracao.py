"""Ponto de integração OPCIONAL com o pipeline principal (cortes.py).

DESATIVADO POR PADRÃO: enquanto `ativo: false` (config.yaml) / `DIVULGACAO_ATIVO=off`,
qualquer chamada devolve None na hora, sem gerar arquivo nem custo de API.

Para ligar, são 2 passos:

  1. em divulgacao/config.yaml -> `ativo: true`  (ou DIVULGACAO_ATIVO=on no .env)

  2. em cortes.py, logo DEPOIS da linha
         render.write_sidecar(info["path"], clip)
     (hoje na linha ~299, dentro do laço `for i, c in enumerate(chosen, start=1):`),
     acrescente UMA linha:
         from divulgacao.integracao import apos_exportacao; apos_exportacao(clip)

Nada é apagado, renomeado ou movido; a chamada é protegida por try/except: uma
falha de divulgação NUNCA derruba a renderização.
"""

from . import config, hashtags


def ligado():
    """Mestre + flag do módulo de hashtags."""
    return bool(config.ATIVO and config.MODULOS.get("hashtags", True))


def apos_exportacao(clip, job=None, on_log=None):
    """Roda o Módulo 1 para um corte recém-exportado. Devolve o metadata ou None."""
    on_log = on_log or config.log
    if not ligado():
        return None
    caminho = (clip or {}).get("path")
    if not caminho:
        return None
    try:
        metadata = hashtags.gerar(caminho, on_log=on_log)
    except Exception as exc:
        on_log(f"  [divulgacao] nao rodou neste corte: {exc}")
        return None

    # anota o link do vídeo quando já existe publicação anterior (não há link ainda)
    if job:
        metadata.setdefault("job", job.get("id"))
    return metadata
