import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from .config import (TOKENS_DIR, TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET,
                     TIKTOK_MODE, TIKTOK_PRIVACY, TIKTOK_REDIRECT_URI)

BASE = "https://open.tiktokapis.com"
AUTHORIZE = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = f"{BASE}/v2/oauth/token/"
INIT_URL = f"{BASE}/v2/post/publish/inbox/video/init/"
DIRECT_INIT_URL = f"{BASE}/v2/post/publish/video/init/"
STATUS_URL = f"{BASE}/v2/post/publish/status/fetch/"
SCOPES = "video.upload,user.info.basic,video.publish"

TOKEN_PATH = TOKENS_DIR / "tiktok.json"
CHUNK = 10 * 1024 * 1024


def configured():
    return bool(TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET)


def _save(tok):
    TOKEN_PATH.write_text(json.dumps(tok, ensure_ascii=False, indent=1), encoding="utf-8")


def _load():
    if TOKEN_PATH.exists():
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    return None


def _token_request(payload):
    r = requests.post(TOKEN_URL, data={**payload, "client_key": TIKTOK_CLIENT_KEY,
                                       "client_secret": TIKTOK_CLIENT_SECRET}, timeout=60)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"OAuth TikTok falhou HTTP {r.status_code}: {r.text[:300]}")
    err = data.get("error")
    if isinstance(err, dict):
        if err.get("code") not in (None, "ok", 0):
            raise RuntimeError(f"OAuth TikTok falhou: {json.dumps(data)[:400]}")
    elif isinstance(err, str) and err:
        raise RuntimeError(
            f"OAuth TikTok falhou: {err} - {data.get('error_description', '')[:300]}"
        )
    elif r.status_code != 200:
        raise RuntimeError(f"OAuth TikTok falhou HTTP {r.status_code}: {json.dumps(data)[:400]}")
    return data


def _refresh(tok):
    data = _token_request({
        "grant_type": "refresh_token",
        "refresh_token": tok.get("refresh_token", ""),
    })
    new = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", tok.get("refresh_token")),
        "open_id": data.get("open_id", tok.get("open_id")),
        "expires_at": time.time() + int(data.get("expires_in", 86400)),
        "scopes": data.get("scope", ""),
    }
    _save(new)
    return new


def _access_token():
    tok = _load()
    if not tok:
        raise RuntimeError("TikTok nao autorizado. Rode: python cortes.py auth --tiktok")
    if time.time() > tok.get("expires_at", 0) - 60:
        tok = _refresh(tok)
    return tok


def _pkce_new():
    import hashlib

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    challenge = hashlib.sha256(verifier.encode("ascii")).hexdigest()
    path = TOKENS_DIR / "tiktok_pkce.json"
    path.write_text(json.dumps({"verifier": verifier}), encoding="utf-8")
    return verifier, challenge


def _pkce_load():
    path = TOKENS_DIR / "tiktok_pkce.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("verifier", "")
        except Exception:
            return ""
    return ""


def auth(interactive=True):
    if not configured():
        raise RuntimeError(
            "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET vazios no .env.\n"
            "1) https://developers.tiktok.com -> Manage apps -> Create app\n"
            "2) adicione o produto Content Posting API e habilite o modo Upload\n"
            f"3) Redirect URI exatamente: {TIKTOK_REDIRECT_URI}"
        )

    state = secrets.token_urlsafe(16)
    _, challenge = _pkce_new()
    qs = urllib.parse.urlencode({
        "client_key": TIKTOK_CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    url = f"{AUTHORIZE}?{qs}"
    parsed = urllib.parse.urlparse(TIKTOK_REDIRECT_URI)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    found = {}

    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and q.get("code"):
                found["code"] = q["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("Conectado. Pode fechar esta aba.".encode("utf-8"))

        def log_message(self, *args):
            pass

    server = HTTPServer((host, port), Handler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    print(f"Abra para autorizar:\n{url}", flush=True)
    if interactive:
        webbrowser.open(url)
    t.join(timeout=900)
    server.server_close()
    if not found.get("code"):
        raise RuntimeError(
            "Nao veio o codigo do TikTok (timeout ou redirect_uri diferente do app).\n"
            "Abra a URL acima, autorize, copie o parametro ?code= da barra de endereco "
            "e rode: python cortes.py auth --tiktok --code SEU_CODIGO"
        )

    data = _token_request({
        "grant_type": "authorization_code",
        "code": found["code"],
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "code_verifier": _pkce_load(),
    })
    tok = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "open_id": data.get("open_id"),
        "expires_at": time.time() + int(data.get("expires_in", 86400)),
        "scopes": data.get("scope", ""),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save(tok)
    return tok


def auth_with_code(code):
    if not configured():
        raise RuntimeError("TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET vazios no .env")
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": TIKTOK_REDIRECT_URI,
    }
    verifier = _pkce_load()
    if verifier:
        payload["code_verifier"] = verifier
    data = _token_request(payload)
    tok = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "open_id": data.get("open_id"),
        "expires_at": time.time() + int(data.get("expires_in", 86400)),
        "scopes": data.get("scope", ""),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save(tok)
    return tok


def _post(url, payload, token):
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
        json=payload,
        timeout=120,
    )
    data = r.json()
    err = (data.get("error") or {}).get("code")
    if err and err != "ok":
        raise RuntimeError(f"TikTok {err}: {(data.get('error') or {}).get('message','')}")
    return data.get("data") or {}


def can_direct():
    try:
        scopes = _access_token().get("scopes") or ""
    except Exception:
        return False
    return "video.publish" in scopes


def upload_draft(path, on_progress=None):
    return _send(path, INIT_URL, None, on_progress=on_progress)


def upload_direct(path, title, privacy_level=None, on_progress=None):
    if not can_direct():
        raise RuntimeError("sem escopo video.publish (Direct Post nao habilitado no app)")
    post_info = {
        "title": (title or "").strip()[:2200] or "corte",
        "privacy_level": privacy_level or TIKTOK_PRIVACY,
        "disable_duet": False,
        "disable_comment": False,
        "disable_stitch": False,
        "video_cover_timestamp_ms": 1000,
    }
    return _send(path, DIRECT_INIT_URL, post_info, on_progress=on_progress)


def _send(path, init_url, post_info, on_progress=None):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    token = _access_token()["access_token"]
    size = os.path.getsize(path)
    # TikTok exige floor(size/chunk_size): o ultimo chunk absorve o resto (oversized).
    # ceil (chunks uniformes) devolve 400 invalid_params "total chunk count is invalid".
    # janela 10-20MB (floor==1): 1 chunk declarado de 10MB mas o blob manda o arquivo
    # inteiro -> "The chunk size is invalid"; ai usamos 1 chunk autoconsistente (size).
    if size < 2 * CHUNK:
        chunk_size = size
        chunks = 1
    else:
        chunk_size = CHUNK
        chunks = max(1, size // CHUNK)

    source_info = {
        "source": "FILE_UPLOAD",
        "video_size": size,
        "chunk_size": chunk_size,
        "total_chunk_count": chunks,
    }
    payload = {"source_info": source_info}
    if post_info:
        payload["post_info"] = post_info
    data = _post(init_url, payload, token)
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")
    if not upload_url or not publish_id:
        raise RuntimeError(f"init sem upload_url: {json.dumps(data)[:300]}")

    with open(path, "rb") as fh:
        for i in range(chunks):
            start = i * chunk_size
            fh.seek(start)
            blob = fh.read(size - start if i == chunks - 1 else chunk_size)
            if not blob:
                raise RuntimeError(f"chunk {i} vazio (size={size} chunks={chunks})")
            end = start + len(blob) - 1
            for attempt in range(3):
                try:
                    r = requests.put(
                        upload_url,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(len(blob)),
                            "Content-Range": f"bytes {start}-{end}/{size}",
                        },
                        data=blob,
                        timeout=600,
                    )
                    if r.status_code in (200, 201, 206):
                        break
                    if r.status_code >= 500:
                        time.sleep(3 * (attempt + 1))
                        continue
                    raise RuntimeError(f"upload chunk {i} -> {r.status_code}: {r.text[:200]}")
                except requests.RequestException as exc:
                    if attempt == 2:
                        raise RuntimeError(f"upload chunk {i} falhou: {exc}") from exc
                    time.sleep(3 * (attempt + 1))
            if on_progress:
                on_progress(f"  chunk {i + 1}/{chunks}")

    status = fetch_status(publish_id, token)
    return {"publish_id": publish_id, "status": status.get("status", ""), "id": publish_id}


def fetch_status(publish_id, token=None):
    token = token or _access_token()["access_token"]
    return _post(STATUS_URL, {"publish_id": publish_id}, token)
