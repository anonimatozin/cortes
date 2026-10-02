from pathlib import Path

import requests

META_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
TIMEOUT = 300
SIZE_LIMIT = 300 * 1024 * 1024

BACKENDS = ["uguu", "catbox"]


def _check(url, size):
    try:
        r = requests.get(url, headers={"User-Agent": META_UA}, stream=True, timeout=60)
        if r.status_code != 200:
            return False, f"status {r.status_code}"
        ctype = (r.headers.get("Content-Type") or "").lower()
        clen = r.headers.get("Content-Length")
        if "html" in ctype or "text" in ctype:
            return False, f"content-type {ctype}"
        if clen and size and abs(int(clen) - size) > max(size * 0.05, 1024 * 1024):
            return False, f"tamanho {clen} != {size}"
        r.close()
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _uguu(path):
    r = requests.post(
        "https://uguu.se/upload.php",
        files={"files[]": (path.name, open(path, "rb"), "video/mp4")},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"uguu: {str(data)[:150]}")
    return data["files"][0]["url"]


def _catbox(path):
    r = requests.post(
        "https://catbox.moe/user/api.php",
        data={"reqtype": "fileupload"},
        files={"fileToUpload": (path.name, open(path, "rb"), "video/mp4")},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"catbox: {url[:150]}")
    return url


_IMPL = {"uguu": _uguu, "catbox": _catbox}


def upload(path, on_progress=None):
    """Sobe o MP4 num host temporario gratis e devolve uma URL que a Meta consegue ler."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size > SIZE_LIMIT:
        raise RuntimeError(f"arquivo grande demais ({size // (1024 * 1024)}MB)")

    erros = []
    for name in BACKENDS:
        if on_progress:
            on_progress(f"  hospedando em {name}...")
        try:
            url = _IMPL[name](path)
        except Exception as exc:
            erros.append(f"{name}: {exc}")
            continue
        good, why = _check(url, size)
        if good:
            return url
        erros.append(f"{name}: URL invalida ({why})")
    raise RuntimeError("nenhum host temporario funcionou: " + " | ".join(erros))
