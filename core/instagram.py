import json
import time
from pathlib import Path

import requests

from . import hosting
from .config import IG_ACCESS_TOKEN, IG_APP_ID, IG_APP_SECRET, API_VERSION, TOKENS_DIR

BASE = f"https://graph.instagram.com/{API_VERSION}"
TOKEN_PATH = TOKENS_DIR / "instagram.json"
PUBLISH_LIMIT = 100


def configured():
    return bool(IG_APP_ID and IG_APP_SECRET and IG_ACCESS_TOKEN)


def _save(tok):
    TOKEN_PATH.write_text(json.dumps(tok, ensure_ascii=False, indent=1), encoding="utf-8")


def _load():
    if TOKEN_PATH.exists():
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    return None


def _token():
    tok = _load() or {}
    now = time.time()
    base = tok.get("access_token") or IG_ACCESS_TOKEN
    if not base:
        raise RuntimeError("IG_ACCESS_TOKEN vazio no .env (veja como configurar em docs)")
    if tok.get("access_token") and now < tok.get("expires_at", 0) - 7 * 86400:
        return tok["access_token"]

    new = dict(tok)
    new["access_token"] = base
    new["expires_at"] = tok.get("expires_at") or (now + 60 * 86400)
    try:
        r = requests.get(
            f"{BASE}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": base},
            timeout=60,
        )
        d = r.json()
        if d.get("access_token"):
            new["access_token"] = d["access_token"]
            new["expires_at"] = now + int(d.get("expires_in", 5184000))
    except Exception:
        pass
    if new["expires_at"] < now:
        new["access_token"] = IG_ACCESS_TOKEN or base
        new["expires_at"] = now + 60 * 86400
    new["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save(new)
    return new["access_token"]


def me():
    token = _token()
    r = requests.get(f"{BASE}/me", params={"fields": "id,user_id,username,account_type", "access_token": token}, timeout=60)
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Instagram: {data['error'].get('message')}")
    return data


def _ig_id():
    tok = _load()
    if tok and tok.get("ig_id"):
        return tok["ig_id"]
    info = me()
    ig = info.get("user_id") or info.get("id")
    tok = _load() or {"access_token": _token(), "expires_at": 0}
    tok["ig_id"] = ig
    tok["username"] = info.get("username", "")
    _save(tok)
    return ig


def _call(method, path, payload=None):
    token = _token()
    data = dict(payload or {})
    data["access_token"] = token
    url = f"{BASE}{path}"
    r = requests.request(method, url, data=data, timeout=120)
    out = r.json()
    if out.get("error"):
        raise RuntimeError(f"Instagram {out['error'].get('code')}: {out['error'].get('message')}")
    return out


def publish(path, caption="", on_progress=None):
    ig = _ig_id()
    if on_progress:
        on_progress("  gerando URL temporaria do video...")
    url = hosting.upload(path, on_progress)

    if on_progress:
        on_progress("  criando container do Reels...")
    container = _call("POST", f"/{ig}/media", {
        "media_type": "REELS",
        "video_url": url,
        "caption": (caption or "")[:2200],
        "share_to_feed": "true",
    })
    cid = container.get("id")
    if not cid:
        raise RuntimeError(f"container sem id: {json.dumps(container)[:200]}")

    if on_progress:
        on_progress("  aguardando a Meta processar o video...")
    deadline = time.time() + 300
    status = ""
    while time.time() < deadline:
        info = _call("GET", f"/{cid}", {"fields": "status_code"})
        status = info.get("status_code", "")
        if status in ("FINISHED", "PUBLISHED"):
            break
        if status == "ERROR":
            raise RuntimeError("container do Reels caiu em ERROR (formato ou regra de conteudo)")
        time.sleep(6)
    else:
        raise RuntimeError(f"timeout esperando o container (ultimo status {status})")

    if on_progress:
        on_progress("  publicando...")
    res = _call("POST", f"/{ig}/media_publish", {"creation_id": cid})
    media_id = res.get("id", "")
    permalink = ""
    try:
        extra = _call("GET", f"/{media_id}", {"fields": "permalink"})
        permalink = extra.get("permalink", "")
    except Exception:
        pass
    return {"id": media_id, "url": permalink, "title": "", "caption": caption}


def delete(media_id):
    r = requests.delete(f"{BASE}/{media_id}", params={"access_token": _token()}, timeout=60)
    out = r.json()
    if out.get("error"):
        raise RuntimeError(f"Instagram delete {out['error'].get('code')}: {out['error'].get('message')}")
    return True


def doctor():
    if not configured():
        return "IG_APP_ID/IG_APP_SECRET/IG_ACCESS_TOKEN vazios no .env"
    info = me()
    return f"{info.get('username','')} ({info.get('account_type','')})"
