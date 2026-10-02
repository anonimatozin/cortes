"""Configuração do módulo divulgacao.

Ordem de prioridade (o último vence):
  1. valores padrão do código
  2. divulgacao/config.yaml
  3. .env da raiz do projeto e divulgacao/.env
  4. variáveis de ambiente com prefixo DIVULGACAO_

Nada aqui importa `core.*`: o módulo precisa funcionar sozinho e também em modo
de teste (DIVULGACAO_MODO_TESTE=1), onde os arquivos saem numa pasta temporária.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parent

AVISOS = []


def log(msg):
    print(f"[divulgacao] {msg}", flush=True)


def _ler_env(caminho):
    env = {}
    try:
        texto = Path(caminho).read_text(encoding="utf-8")
    except OSError:
        return env
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _carregar_env():
    env = _ler_env(RAIZ / ".env")
    env.update(_ler_env(PASTA / ".env"))
    for k, v in os.environ.items():
        if k.startswith("DIVULGACAO_"):
            env[k[len("DIVULGACAO_"):]] = v
        elif k in env:
            env[k] = v
    return env


def _carregar_yaml():
    caminho = PASTA / "config.yaml"
    if not caminho.exists():
        return {}
    try:
        import yaml
    except ImportError:
        AVISOS.append("pyyaml nao instalado (pip install pyyaml) -> usando padroes")
        return {}
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        AVISOS.append(f"config.yaml invalido ({exc}) -> usando padroes")
        return {}
    return dados if isinstance(dados, dict) else {}


ENV = _carregar_env()
YAML = _carregar_yaml()


def cfg(caminho, padrao=None):
    """Lê um valor aninhado do config.yaml usando 'chave.subchave'."""
    atual = YAML
    for parte in caminho.split("."):
        if not isinstance(atual, dict) or parte not in atual:
            return padrao
        atual = atual[parte]
    return padrao if atual is None else atual


def _bool(valor, padrao=False):
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "true", "on", "sim", "yes", "ligado")


def _int(valor, padrao):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao


def _float(valor, padrao):
    try:
        return float(str(valor).strip())
    except (TypeError, ValueError):
        return padrao


def _texto(valor, padrao=""):
    if valor is None:
        return padrao
    return str(valor).strip()


# ---------------------------------------------------------------- modo teste
MODO_TESTE = _bool(ENV.get("MODO_TESTE"), False)
BASE_DADOS = (Path(tempfile.gettempdir()) / "divulgacao_teste") if MODO_TESTE else PASTA

# ------------------------------------------------------------------- pastas
SAIDA_DIR = BASE_DADOS / "saida"
CACHE_DIR = BASE_DADOS / "cache"
ESTADO_DIR = BASE_DADOS / "estado"
LOG_DIR = BASE_DADOS / "logs"

GRUPOS_CSV = BASE_DADOS / "grupos.csv"
PLANO_MD = BASE_DADOS / "plano_divulgacao.md"
BUSCAS_MD = BASE_DADOS / "buscas_grupos.md"
TIKTOK_TRENDING = BASE_DADOS / "tiktok_trending.txt"
RESULTADOS_CSV = BASE_DADOS / "resultados.csv"
RELATORIO_MD = BASE_DADOS / "relatorio_resultados.md"

PRIORIDADES_JSON = CACHE_DIR / "prioridades.json"
ESTADO_GRUPOS_JSON = ESTADO_DIR / "grupos_estado.json"
COTA_YOUTUBE_JSON = CACHE_DIR / "cota_youtube.json"

for _d in (SAIDA_DIR, CACHE_DIR, ESTADO_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------- pastas do projeto real
CLIPS_DIR = RAIZ / "clips"
SOURCE_DIR = RAIZ / "source"
JOBS_PATH = RAIZ / "queue" / "jobs.json"

# -------------------------------------------------------------------- flags
ATIVO = _bool(ENV.get("ATIVO"), _bool(cfg("ativo"), False))

MODULOS = {
    nome: _bool(ENV.get(f"MODULO_{nome.upper()}"), _bool(cfg(f"modulos.{nome}"), True))
    for nome in ("hashtags", "grupos", "registro")
}

NICHO = _texto(ENV.get("NICHO"), _texto(cfg("nicho"), "podcast"))

# ----------------------------------------------------------------------- IA
GROQ_API_KEY = ENV.get("GROQ_API_KEY", "")
GROQ_MODEL = _texto(ENV.get("GROQ_MODEL") or cfg("ia.modelo"), "openai/gpt-oss-120b")
IA_MODO = _texto(ENV.get("IA") or cfg("ia.modo"), "auto").lower()  # auto | on | off
IA_CANDIDATAS = _int(ENV.get("IA_CANDIDATAS") or cfg("ia.candidatas"), 30)
IA_TEMPERATURA = _float(ENV.get("IA_TEMPERATURA") or cfg("ia.temperatura"), 0.5)

# ------------------------------------------------------------------ YouTube
YOUTUBE_API_KEY = ENV.get("YOUTUBE_API_KEY", "")
YT_ATIVO = _bool(ENV.get("YT_ATIVO"), _bool(cfg("hashtags.youtube.ativo"), True))
YT_MAX_VIDEOS = _int(ENV.get("YT_MAX_VIDEOS") or cfg("hashtags.youtube.max_videos"), 40)
YT_ORDEM = _texto(ENV.get("YT_ORDEM") or cfg("hashtags.youtube.ordem"), "relevance")
YT_PUBLICADO_DIAS = _int(ENV.get("YT_PUBLICADO_DIAS") or cfg("hashtags.youtube.publicado_dias"), 400)
YT_COTA_DIA = _int(ENV.get("YT_COTA_DIA") or cfg("hashtags.youtube.cota_dia"), 9000)
YT_CACHE_DIAS = _int(ENV.get("YT_CACHE_DIAS") or cfg("hashtags.youtube.cache_dias"), 7)
YT_AUTOCOMPLETE = _bool(ENV.get("YT_AUTOCOMPLETE"), _bool(cfg("hashtags.youtube.autocomplete"), True))

# ------------------------------------------------------------------- TikTok
TIKTOK_ATIVO = _bool(ENV.get("TIKTOK_ATIVO"), _bool(cfg("hashtags.tiktok.ativo"), True))
TRENDS_ATIVO = _bool(ENV.get("TRENDS"), _bool(cfg("hashtags.trends.ativo"), False))

# ----------------------------------------------------------------- hashtags
HASHTAGS_MIN = _int(ENV.get("HASHTAGS_MIN") or cfg("hashtags.min"), 3)
HASHTAGS_MAX = _int(ENV.get("HASHTAGS_MAX") or cfg("hashtags.max"), 5)
TAGS_MAX_CHARS = _int(ENV.get("TAGS_MAX_CHARS") or cfg("hashtags.tags_max_chars"), 500)

# ------------------------------------------------------------------- grupos
GRUPOS_MAX_POR_DIA = max(1, _int(ENV.get("GRUPOS_MAX_POR_DIA") or cfg("grupos.max_por_dia"), 2))
GRUPOS_DIAS_ENTRE = max(1, _int(ENV.get("GRUPOS_DIAS_ENTRE") or cfg("grupos.dias_entre_posts"), 7))
GRUPOS_DIAS_PLANO = max(1, _int(ENV.get("GRUPOS_DIAS_PLANO") or cfg("grupos.dias_plano"), 14))
GRUPOS_TAMANHO_TEXTO = max(120, _int(ENV.get("GRUPOS_TAMANHO_TEXTO") or cfg("grupos.tamanho_texto"), 400))

# ----------------------------------------------------------------- registro
REG_MIN_AMOSTRAS = max(1, _int(ENV.get("REG_MIN_AMOSTRAS") or cfg("registro.min_amostras"), 2))
REG_MAX_LINHAS = max(3, _int(ENV.get("REG_MAX_LINHAS") or cfg("registro.max_linhas"), 20))


# ------------------------------------------------------------------ utilidades
def hoje():
    return time.strftime("%Y-%m-%d")


def agora():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def dia_mas(dias):
    """Data ISO de hoje + N dias (dias negativos voltam no tempo)."""
    import datetime
    d = datetime.date.today() + datetime.timedelta(days=int(dias))
    return d.isoformat()


def ia_disponivel():
    """IA ligada e com chave."""
    if IA_MODO == "off":
        return False
    if not GROQ_API_KEY:
        return False
    return True


def unidade_do_sistema():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
