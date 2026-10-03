import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "source"
CLIPS_DIR = ROOT / "clips"
QUEUE_DIR = ROOT / "queue"
TOKENS_DIR = ROOT / "tokens"
CRED_DIR = ROOT / "credentials"
LOG_DIR = ROOT / "logs"
FONTS_DIR = ROOT / "fonts"
MODELS_DIR = ROOT / "models"

for d in (SOURCE_DIR, CLIPS_DIR, QUEUE_DIR, TOKENS_DIR, CRED_DIR, LOG_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)

if not FONTS_DIR.exists():
    ref = Path(r"C:\Users\Administrator\Documents\Default Project\video-edit\fonts")
    if ref.exists():
        import shutil
        shutil.copytree(ref, FONTS_DIR)

ENV_PATH = ROOT / ".env"


def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k in env or k.startswith("CORTES")})
    return env


ENV = load_env()

GROQ_API_KEY = ENV.get("GROQ_API_KEY", "")
GROQ_MODEL = ENV.get("GROQ_MODEL", "openai/gpt-oss-120b")
LANGUAGE = ENV.get("LANGUAGE", "pt")
WHISPER_MODEL = ENV.get("WHISPER_MODEL", "small")

CLIPS_PER_VIDEO = int(ENV.get("CLIPS_PER_VIDEO", "3"))
MIN_CLIP_SEC = float(ENV.get("MIN_CLIP_SEC", "25"))
MAX_CLIP_SEC = float(ENV.get("MAX_CLIP_SEC", "58"))
TARGET_CLIP_SEC = float(ENV.get("TARGET_CLIP_SEC", "42"))

FONTE_PRIORIDADE = [k.strip() for k in ENV.get("FONTE_PRIORIDADE", "").split(",") if k.strip()]
PRIVACY = ENV.get("YOUTUBE_PRIVACY", "public")
CATEGORY_ID = ENV.get("YOUTUBE_CATEGORY", "24")
BRAND = ENV.get("BRAND", "CORTES")
VIDEO_WIDTH = int(ENV.get("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT = int(ENV.get("VIDEO_HEIGHT", "1920"))
TARGET_FACE_H = float(ENV.get("TARGET_FACE_H", "0.56"))
REFRAME = ENV.get("REFRAME", "on") != "off"
GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "")
IMAGE_PROVIDER = ENV.get("IMAGE_PROVIDER", "gemini")
IMAGE_MODEL = ENV.get("IMAGE_MODEL", "gemini-2.5-flash-image")
IMAGE_STYLE = ENV.get("IMAGE_STYLE", "flat vector illustration, bold saturated colors, clean background")
IMAGES_ENABLED = ENV.get("IMAGES_ENABLED", "on") != "off"
IMAGES_MAX = max(0, int(ENV.get("IMAGES_MAX", "2")))
RESEARCH_LIMIT = int(ENV.get("RESEARCH_LIMIT", "8"))
RESEARCH_CACHE = QUEUE_DIR / "research_cache.json"
CREDITS_STYLE = ENV.get("CREDITS_STYLE", "full")
HASHTAGS_MAX = int(ENV.get("HASHTAGS_MAX", "5"))
TIKTOK_CLIENT_KEY = ENV.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = ENV.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = ENV.get("TIKTOK_REDIRECT_URI", "http://127.0.0.1:8765/callback")
TIKTOK_PENDING_CAP = int(ENV.get("TIKTOK_PENDING_CAP", "5"))
TIKTOK_MODE = ENV.get("TIKTOK_MODE", "auto")            # auto | inbox | direct
TIKTOK_PRIVACY = ENV.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE") # PUBLIC_TO_EVERYONE | MUTUAL_FOLLOW_FRIENDS | SELF_ONLY
TIKTOK_POLL_SECONDS = max(2, int(ENV.get("TIKTOK_POLL_SECONDS", "5")))
TIKTOK_POLL_TIMEOUT = max(30, int(ENV.get("TIKTOK_POLL_TIMEOUT", "300")))
TIKTOK_BRAND_CONTENT = ENV.get("TIKTOK_BRAND_CONTENT", "off") == "on"
TIKTOK_BRAND_ORGANIC = ENV.get("TIKTOK_BRAND_ORGANIC", "off") == "on"
TIKTOK_IS_AIGC = ENV.get("TIKTOK_IS_AIGC", "off") == "on"
IG_APP_ID = ENV.get("IG_APP_ID", "")
IG_APP_SECRET = ENV.get("IG_APP_SECRET", "")
IG_ACCESS_TOKEN = ENV.get("IG_ACCESS_TOKEN", "")
IG_USERNAME = ENV.get("IG_USERNAME", "")
API_VERSION = ENV.get("IG_API_VERSION", "v26.0")
