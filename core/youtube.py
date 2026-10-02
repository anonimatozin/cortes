import json
import time
from pathlib import Path

from .config import CATEGORY_ID, CRED_DIR, PRIVACY, QUEUE_DIR, TOKENS_DIR

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
CLIENT_SECRET = CRED_DIR / "client_secret.json"
TOKEN_PATH = TOKENS_DIR / "youtube.json"
USAGE_PATH = QUEUE_DIR / "usage.json"

QUOTA_PER_UPLOAD = 1600
DAILY_QUOTA = 10000


def _load_usage():
    if USAGE_PATH.exists():
        d = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        if d.get("day") == time.strftime("%Y-%m-%d"):
            return d
    return {"day": time.strftime("%Y-%m-%d"), "units": 0, "uploads": 0}


def _save_usage(d):
    USAGE_PATH.write_text(json.dumps(d, indent=1), encoding="utf-8")


def quota_left():
    return DAILY_QUOTA - _load_usage()["units"]


def charge(units):
    usage = _load_usage()
    usage["units"] += units
    _save_usage(usage)
    return DAILY_QUOTA - usage["units"]


def _creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def auth(interactive=True):
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f"Coloque o OAuth Client (JSON) em: {CLIENT_SECRET}\n"
            "Google Cloud Console -> APIs & Services -> Credentials -> OAuth client ID -> Desktop app"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent") if interactive else flow.run_console()
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_service():
    from googleapiclient.discovery import build

    creds = _creds()
    if not creds or not creds.valid:
        creds = auth(interactive=True)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


class QuotaError(RuntimeError):
    pass


def upload(path, title, description, tags, privacy=None, category=None, retry=3):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    service = get_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": (tags or [])[:30],
            "categoryId": str(category or CATEGORY_ID),
        },
        "status": {
            "privacyStatus": privacy or PRIVACY,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
            "publicStatsVisible": True,
        },
    }
    media = MediaFileUpload(str(path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)

    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    last_err = None
    for attempt in range(retry):
        try:
            while response is None:
                progress, response = request.next_chunk()
                if progress:
                    pass
            break
        except Exception as exc:
            last_err = exc
            text = str(exc)
            if isinstance(exc, HttpError) and (
                "quotaExceeded" in text or "rateLimitExceeded" in text or "uploadLimitExceeded" in text
            ):
                raise QuotaError(f"cota real do YouTube atingida: {text[:200]}") from exc
            time.sleep(5 * (attempt + 1))
            request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    else:
        raise RuntimeError(f"Upload falhou: {last_err}")

    usage = _load_usage()
    usage["units"] += QUOTA_PER_UPLOAD
    usage["uploads"] += 1
    _save_usage(usage)

    return {
        "id": response.get("id"),
        "url": f"https://youtube.com/shorts/{response.get('id')}",
        "title": body["snippet"]["title"],
    }


def delete(video_id):
    service = get_service()
    service.videos().delete(id=video_id).execute()
    return True


def update_snippet(video_id, title, description, tags, category=None):
    service = get_service()
    body = {
        "id": video_id,
        "snippet": {
            "title": title[:100],
            "description": (description or "")[:4900],
            "tags": (tags or [])[:30],
            "categoryId": str(category or CATEGORY_ID),
        },
    }
    resp = service.videos().update(part="snippet", body=body).execute()
    return resp.get("id", video_id)


def get_privacy(video_id):
    service = get_service()
    resp = service.videos().list(part="status", id=video_id).execute()
    items = resp.get("items") or []
    if not items:
        return None
    return items[0].get("status", {}).get("privacyStatus")


def set_privacy(video_id, privacy):
    service = get_service()
    body = {"id": video_id, "status": {"privacyStatus": privacy}}
    resp = service.videos().update(part="status", body=body).execute()
    return resp.get("id", video_id)
