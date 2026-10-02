# -*- coding: utf-8 -*-
"""Teste de ponta a ponta do módulo divulgacao, com um corte de exemplo.

Roda SEM rede e SEM chave de API (IA e YouTube desligados): valida os caminhos
críticos, os limites e a escrita dos arquivos de saída.

Como rodar (de qualquer pasta):
    python -m divulgacao.teste.teste_ponta_a_ponta
ou:
    divulgacao\\rodar_teste.cmd

O teste usa DIVULGACAO_MODO_TESTE=1: tudo sai em %TEMP%\\divulgacao_teste e
NENHUM arquivo real do projeto é tocado.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# ---- tempos que ser ANTES de importar divulgacao.config --------------------
PASTO_TESTE = Path(tempfile.gettempdir()) / "divulgacao_teste"
os.environ["DIVULGACAO_MODO_TESTE"] = "1"
os.environ["DIVULGACAO_IA"] = "off"
os.environ["DIVULGACAO_ATIVO"] = "off"
os.environ["DIVULGACAO_YT_ATIVO"] = "off"
os.environ["DIVULGACAO_YT_AUTOCOMPLETE"] = "off"
os.environ["DIVULGACAO_NICHO"] = "games"
shutil.rmtree(PASTO_TESTE, ignore_errors=True)

RAIZ = Path(__file__).resolve().parents[2]  # ...\cortes
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from divulgacao import cli, config, grupos, hashtags, integracao, registro  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

FALHAS = []
CONTA = {"ok": 0}


def check(cond, mensagem):
    if cond:
        CONTA["ok"] += 1
        print(f"  [OK]   {mensagem}", flush=True)
    else:
        FALHAS.append(mensagem)
        print(f"  [FALHA] {mensagem}", flush=True)
    return bool(cond)


def secao(nome):
    print(f"\n== {nome} " + "=" * max(0, 60 - len(nome)), flush=True)


# ---------------------------------------------------------------- exemplos
TRANSCRICAO = {
    "language": "pt",
    "segments": [
        {"start": 0.0, "end": 4.0, "text": "Cara, você não vai acreditar no que aconteceu no servidor ontem."},
        {"start": 4.0, "end": 9.0, "text": "A gente construiu uma fábrica inteira de diamantes em duas horas."},
        {"start": 9.0, "end": 14.5, "text": "E o pior é que o spawn ficou todo destruído no final."},
        {"start": 14.5, "end": 20.0, "text": "Se você já passou vergonha assim, comenta aí embaixo."},
        {"start": 20.0, "end": 26.0, "text": "Porque dessa vez o time inteiro caiu no mesmo buraco."},
        {"start": 26.0, "end": 32.0, "text": "A gente perdeu tudo, tudo que a gente tinha juntado naquela temporada."},
    ],
}

SIDE_CAR = {
    "index": 1,
    "path": str(PASTO_TESTE / "exemplo" / "01_EXEMPLO_A_FABRICA_DE_DIAMANTES.mp4"),
    "start": 4.0,
    "end": 26.0,
    "duration": 22.0,
    "title": "A fábrica de diamantes que destruiu o spawn",
    "description": "Time inteiro caiu no mesmo buraco e perdeu a temporada toda.",
    "hashtags": ["#minecraft", "#gamer"],
    "tags": ["minecraft", "gameplay", "survival"],
    "status": "ready",
}

GRUPOS_CSV = """nome,link,tema,aceita_divulgacao,regras,ultima_postagem
Minecraft BR,https://www.facebook.com/groups/exemplo01,minecraft,sim,Maximo 1 post por dia,
Clube Survival,https://www.facebook.com/groups/exemplo02,minecraft,sim,Sem link externo,
Games em Geral,https://www.facebook.com/groups/exemplo03,games,não,Proibido divulgar,
Podcast do Zeca,https://www.facebook.com/groups/exemplo04,podcast,sim,Nada de politica,
"""


def criar_exemplos():
    pasta = PASTO_TESTE / "exemplo"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "transcript_exemplo.json").write_text(
        json.dumps(TRANSCRICAO, ensure_ascii=False, indent=1), encoding="utf-8")
    (pasta / "01_EXEMPLO_A_FABRICA_DE_DIAMANTES.json").write_text(
        json.dumps(SIDE_CAR, ensure_ascii=False, indent=1), encoding="utf-8")
    config.GRUPOS_CSV.write_text(GRUPOS_CSV, encoding="utf-8")
    config.TIKTOK_TRENDING.write_text(
        "// lista de exemplo do teste\n#minecraft\n#gameplay\n", encoding="utf-8")
    return (pasta / "01_EXEMPLO_A_FABRICA_DE_DIAMANTES.json",
            pasta / "transcript_exemplo.json")


# --------------------------------------------------------------- testes
def teste_ambiente():
    secao("1. ambiente")
    check(config.MODO_TESTE, "MODO_TESTE ligado (nada fora da pasta temporária)")
    check(str(config.SAIDA_DIR).startswith(str(PASTO_TESTE)),
          f"saída em pasta temporária: {config.SAIDA_DIR}")
    check(config.NICHO == "games", f"nicho lido do ambiente: {config.NICHO}")
    check(config.ATIVO is False, "integração DESLIGADA por padrão (ativo=false)")
    check(not integracao.ligado(), "integracao.ligado() == False")
    check(config.MODULOS["hashtags"] and config.MODULOS["grupos"]
          and config.MODULOS["registro"], "os três módulos vêm habilitados")
    check(config.HASHTAGS_MIN <= 4 <= config.HASHTAGS_MAX,
          f"faixa de hashtags {config.HASHTAGS_MIN}..{config.HASHTAGS_MAX} inclui o mix 1+2+1")


def teste_hashtags(sidecar, transcript):
    secao("2. Módulo 1 — hashtags e tags")
    rc = cli.main(["hashtags", "--corte", str(sidecar), "--transcript", str(transcript),
                   "--nicho", "games", "--sem-youtube"])
    check(rc == 0, "CLI hashtags devolveu 0")

    caminho = hashtags.caminho_metadata("01_EXEMPLO_A_FABRICA_DE_DIAMANTES")
    check(caminho.exists(), f"metadata.json gravado em {caminho}")
    if not caminho.exists():
        return None
    m = json.loads(caminho.read_text(encoding="utf-8"))

    hs = m["hashtags"]
    check(config.HASHTAGS_MIN <= len(hs) <= config.HASHTAGS_MAX,
          f"{len(hs)} hashtags (pediu {config.HASHTAGS_MIN}..{config.HASHTAGS_MAX}): {' '.join(hs)}")
    comp = m["composicao"]
    check(comp.get("amplo", 0) >= 1, f"1 ampla: {comp}")
    check(comp.get("nicho", 0) >= 1, f"1 de nicho: {comp}")
    check(comp.get("especifico", 0) >= 1, f"1 específica: {comp}")
    check(len(set(h.lower() for h in hs)) == len(hs), "sem hashtag repetida")
    check(all(h.startswith("#") and " " not in h for h in hs), "formato #sem espaço")
    check(len(m["tags_youtube"]) <= config.TAGS_MAX_CHARS,
          f"tags do YouTube com {len(m['tags_youtube'])} de {config.TAGS_MAX_CHARS} caracteres")
    check(len(m["tags_youtube_lista"]) >= 3,
          f"{len(m['tags_youtube_lista'])} tags do YouTube: {m['tags_youtube'][:80]}")
    check(bool(m["hashtags_tiktok"]) and len(m["hashtags_tiktok"]) >= len(hs),
          f"hashtags do TikTok separadas: {m['hashtags_tiktok']}")
    check(len(m["candidatas"]) >= 10, f"{len(m['candidatas'])} candidatas pontuadas")
    check(m["fontes"]["ia"] is False, "IA desligada -> usou o fallback (como esperado no teste)")
    check(m["titulo"] and m["descricao"], "título e descrição preenchidos")
    check(m["origem"].endswith(".json"),
          f"transcrição de origem registrada: {Path(m['origem']).name}")
    return m


def teste_grupos(metadata):
    secao("3. Módulo 2 — grupos (sem automação de postagem)")
    rc = cli.main(["grupos", "--nicho", "games", "--buscas", "--textos",
                   "--plano", "14", "--corte", metadata["corte"]])
    check(rc == 0, "CLI grupos devolveu 0")
    check(config.BUSCAS_MD.exists(), f"buscas geradas: {config.BUSCAS_MD.name}")
    check(config.GRUPOS_CSV.exists(), "grupos.csv presente")

    lista = grupos.carregar()
    check(len(lista) == 4, f"{len(lista)} grupos lidos do CSV")
    check(sum(1 for g in lista if grupos.aceita(g)) == 3, "3 grupos aceitam divulgação")

    estado_path = config.ESTADO_GRUPOS_JSON
    check(estado_path.exists(), f"estado gravado: {estado_path.name}")
    if not estado_path.exists():
        return {"textos": {}}
    estado = json.loads(estado_path.read_text(encoding="utf-8"))
    textos = estado["textos"]
    aceitantes = [g for g in lista if grupos.aceita(g)]
    check(len(textos) == len(aceitantes),
          f"{len(textos)} textos gerados (1 por grupo que aceita)")
    check(all(g["link"] not in textos for g in lista if not grupos.aceita(g)),
          "grupo que NÃO aceita não recebe texto")
    textos_valores = [t["texto"] for t in textos.values() if t.get("texto")]
    check(len(set(textos_valores)) == len(textos_valores), "nenhum texto repetido")
    check(all("inscreva" not in t.lower() and "link na bio" not in t.lower()
              for t in textos_valores), "sem spam de 'inscreva-se/link na bio'")
    check(all(t.endswith("?") or "?" in t.split("\n")[-2] or "?" in t
              for t in textos_valores), "textos terminam com pergunta/contexto")

    check(config.PLANO_MD.exists(), f"plano gerado: {config.PLANO_MD.name}")
    plano = config.PLANO_MD.read_text(encoding="utf-8")
    import re as _re
    dias_marcados = [l for l in plano.splitlines()
                     if l.startswith("### ") and _re.match(r"^### \d+\. ", l)]
    por_dia = {}
    dia_atual = None
    for linha in plano.splitlines():
        if linha.startswith("## ") and _re.match(r"^## \d{4}-\d{2}-\d{2} ", linha):
            dia_atual = linha[3:13]
            por_dia[dia_atual] = 0
        elif linha.startswith("### ") and dia_atual:
            por_dia[dia_atual] += 1
    check(por_dia, f"plano com {len(por_dia)} dia(s) com publicação")
    check(all(v <= config.GRUPOS_MAX_POR_DIA for v in por_dia.values()),
          f"nunca passa de {config.GRUPOS_MAX_POR_DIA} grupos por dia: {por_dia}")
    check(len(dias_marcados) <= len(aceitantes),
          "não agenda mais grupos do que a fila permite")

    # marca um como postado e confere o cooldown de 7 dias
    primeiro = aceitantes[0]["link"]
    grupos.marcar_postado(primeiro)
    estado = json.loads(config.ESTADO_GRUPOS_JSON.read_text(encoding="utf-8"))
    check(estado["textos"][primeiro]["status"] == "postado", "postado registrado no estado")
    csv_pos = grupos.carregar()
    alvo = next(g for g in csv_pos if g["link"] == primeiro)
    check(alvo["ultima_postagem"] == config.hoje(), "ultima_postagem atualizado no CSV")

    antes = len(estado["textos"])
    grupos.gerar_textos(metadata=metadata, on_log=lambda *_: None)
    depois = json.loads(config.ESTADO_GRUPOS_JSON.read_text(encoding="utf-8"))
    check(len(depois["textos"]) == antes,
          "cooldown de 7 dias impede novo texto para o grupo já postado")
    return estado


def teste_registro(metadata):
    secao("4. Módulo 3 — registro e prioridades")
    registro.registrar(metadata["corte"], hashtags=metadata["hashtags"],
                       plataforma="youtube", views=1200, curtidas=90)
    registro.registrar(metadata["corte"], hashtags=metadata["hashtags"],
                       plataforma="tiktok", grupo="", views=800, curtidas=150)
    registro.registrar(metadata["corte"], hashtags=metadata["hashtags"][:2],
                       plataforma="facebook", grupo="Minecraft BR", views=300, curtidas=25)
    registro.registrar(metadata["corte"], hashtags=metadata["hashtags"][1:],
                       plataforma="facebook", grupo="Clube Survival", views=450, curtidas=40)

    linhas = registro.carregar()
    check(len(linhas) == 4, f"{len(linhas)} linhas no resultados.csv")
    check(all(k in linhas[0] for k in registro.CABECALHO),
          f"colunas esperadas: {registro.CABECALHO}")

    # atualização não duplica
    registro.atualizar_views(metadata["corte"], plataforma="youtube", views=1500, curtidas=100)
    linhas = registro.carregar()
    check(len(linhas) == 4, "atualizar views não duplica linha")
    check(linhas[0]["views"] == 1500, f"views atualizadas: {linhas[0]['views']}")

    rc = cli.main(["registro", "relatorio"])
    check(rc == 0, "CLI registro relatorio devolveu 0")
    check(config.RELATORIO_MD.exists(), f"relatório: {config.RELATORIO_MD.name}")
    check(config.PRIORIDADES_JSON.exists(), f"prioridades: {config.PRIORIDADES_JSON.name}")

    pesos = json.loads(config.PRIORIDADES_JSON.read_text(encoding="utf-8"))
    check(bool(pesos["hashtags"]), f"{len(pesos['hashtags'])} hashtag(s) com peso")
    check(all(0.0 <= v <= 1.0 for v in pesos["hashtags"].values()), "pesos entre 0 e 1")
    check(metadata["hashtags"][0].lower() in pesos["hashtags"]
          or metadata["hashtags"][0][1:].lower() in pesos["hashtags"],
          "a hashtag do corte entrou no ranking")

    # o módulo 1 passa a considerar os pesos do relatório
    check(bool(hashtags.prioridades()), "Módulo 1 lê os pesos do Módulo 3")


def teste_integracao(sidecar):
    secao("5. ponto de integração (desligado por padrão)")
    clip = json.loads(sidecar.read_text(encoding="utf-8"))
    antes = len(list(config.SAIDA_DIR.glob("*/metadata.json")))
    saida = integracao.apos_exportacao(clip)
    depois = len(list(config.SAIDA_DIR.glob("*/metadata.json")))
    check(saida is None, "apos_exportacao() devolveu None com o mestre desligado")
    check(antes == depois, "nenhum arquivo novo criado com a integração desligada")

    # erro no clip nunca pode estourar para fora
    check(integracao.apos_exportacao({"path": "nao_existe.mp4"}) is None,
          "integração engole erro e não derruba o pipeline")


def teste_limpeza():
    secao("6. resumo")
    print(f"  {CONTA['ok']} checagens ok, {len(FALHAS)} falha(s)", flush=True)
    return 0 if not FALHAS else 1


def main():
    print(f"modo teste: {PASTO_TESTE}", flush=True)
    sidecar, transcript = criar_exemplos()
    teste_ambiente()
    metadata = teste_hashtags(sidecar, transcript)
    if metadata:
        teste_grupos(metadata)
        teste_registro(metadata)
    else:
        check(False, "metadata não foi gerado — testes seguintes pulados")
    teste_integracao(sidecar)
    rc = teste_limpeza()
    if rc:
        print("\nFALHAS:", flush=True)
        for f in FALHAS:
            print(f"  - {f}", flush=True)
    else:
        print("\nTUDO OK. Saídas em:", PASTO_TESTE, flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
