import json
import time
from pathlib import Path

from .config import QUEUE_DIR

JOBS_PATH = QUEUE_DIR / "jobs.json"


def load_jobs():
    if JOBS_PATH.exists():
        try:
            data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("jobs"), list):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"jobs": []}


def save_jobs(data):
    tmp = JOBS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(JOBS_PATH)


def get_job(job_id):
    data = load_jobs()
    for j in data["jobs"]:
        if j["id"] == job_id:
            return j
    return None


def upsert_job(job):
    data = load_jobs()
    for i, j in enumerate(data["jobs"]):
        if j["id"] == job["id"]:
            data["jobs"][i] = job
            break
    else:
        data["jobs"].append(job)
    save_jobs(data)
    return job


def new_job(url, meta=None):
    job = {
        "id": str(int(time.time() * 1000)),
        "url": url,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": "queued",
        "meta": meta or {},
        "clips": [],
        "error": None,
    }
    return upsert_job(job)


def find_job_by_url(url):
    data = load_jobs()
    for j in data["jobs"]:
        if j.get("url") == url:
            return j
    return None


UPLOADS_PATH = QUEUE_DIR / "uploads.json"


def load_uploads():
    if UPLOADS_PATH.exists():
        try:
            return json.loads(UPLOADS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def add_upload(rec):
    items = load_uploads()
    items.append(rec)
    tmp = UPLOADS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(UPLOADS_PATH)
    return rec


def mark_deleted(video_id):
    items = load_uploads()
    for it in items:
        if it.get("id") == video_id:
            it["deleted"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_uploads(items)


def save_uploads(items):
    tmp = UPLOADS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(UPLOADS_PATH)
    return items
