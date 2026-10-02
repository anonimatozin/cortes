import hashlib
import json
import time

import requests

from .config import ENV, QUEUE_DIR

URL = "https://open-api.affiliate.shopee.com.br/graphql"
APP_ID = ENV.get("SHOPEE_APP_ID", "")
SECRET = ENV.get("SHOPEE_SECRET", "")
SUBID = ENV.get("SHOPEE_SUBID", "cortes")
ENABLED = ENV.get("SHOPEE_ENABLED", "auto")
CACHE_PATH = QUEUE_DIR / "shopee_cache.json"
CATALOG_PATH = QUEUE_DIR / "shopee_catalog.txt"

Q_PRODUCT = """
query ($keyword: String, $page: Int, $limit: Int, $sortType: Int) {
  productOffer(keyword: $keyword, page: $page, limit: $limit, sortType: $sortType) {
    edges { node { id name productName price commissionRate productUrl url offerLink imageUrl image } }
    pageInfo { hasNextPage }
  }
}
"""

Q_OFFER = """
query ($keyword: String, $page: Int, $limit: Int, $sortType: Int) {
  shopeeOfferV2(keyword: $keyword, page: $page, limit: $limit, sortType: $sortType) {
    nodes { offerName commissionRate offerLink imageUrl }
    pageInfo { hasNextPage }
  }
}
"""

Q_SHORT = """
mutation ($originUrl: String!, $subIds: [String!]) {
  generateShortLink(originUrl: $originUrl, subIds: $subIds) { shortLink }
}
"""


def on():
    if ENABLED == "off":
        return False
    return bool(APP_ID and SECRET) or bool(catalog())


def catalog():
    if not CATALOG_PATH.exists():
        return []
    out = []
    for line in CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[1].startswith("http"):
            continue
        out.append({
            "keyword": parts[0],
            "link": parts[1],
            "name": parts[2] if len(parts) > 2 and parts[2] else parts[0],
            "price": parts[3] if len(parts) > 3 else "",
            "commission": float(parts[4]) if len(parts) > 4 and parts[4] else 0.0,
            "source": "catalogo",
        })
    return out


def _post(query, variables=None, timeout=30):
    body = {"query": query}
    if variables:
        body["variables"] = variables
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    ts = str(int(time.time()))
    sig = hashlib.sha256((APP_ID + ts + raw + SECRET).encode("utf-8")).hexdigest()
    headers = {
        "Authorization": f"SHA256 Credential={APP_ID}, Timestamp={ts}, Signature={sig}",
        "Content-Type": "application/json",
    }
    r = requests.post(URL, headers=headers, data=raw.encode("utf-8"), timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(f"Shopee: {data['errors'][0].get('message', 'erro')}")
    return data.get("data") or {}


def _norm_rate(v):
    try:
        f = float(v)
        return f * 100 if 0 < f < 1 else f
    except (TypeError, ValueError):
        return 0.0


def _norm_item(node, source):
    name = (node.get("productName") or node.get("name") or node.get("offerName") or "").strip()
    link = (node.get("offerLink") or node.get("productUrl") or node.get("url") or "").strip()
    price = node.get("price") or node.get("priceMin") or ""
    return {
        "name": name,
        "link": link,
        "price": str(price),
        "commission": round(_norm_rate(node.get("commissionRate")), 2),
        "image": (node.get("imageUrl") or node.get("image") or "").strip(),
        "source": source,
    }


def search(keyword, limit=10):
    if not on() or not keyword:
        return []
    for query, key, source in ((Q_PRODUCT, "productOffer", "produto"), (Q_OFFER, "shopeeOfferV2", "oferta")):
        try:
            data = _post(query, {"keyword": keyword, "page": 1, "limit": limit, "sortType": 2})
        except Exception:
            continue
        node = data.get(key) or {}
        items = node.get("edges") or node.get("nodes") or []
        out = []
        for it in items:
            n = it.get("node") if isinstance(it, dict) and "node" in it else it
            if not isinstance(n, dict):
                continue
            item = _norm_item(n, source)
            if item["name"] and item["link"]:
                out.append(item)
        if out:
            return out
    return []


def short_link(origin_url, subid=None):
    if not on() or not origin_url:
        return ""
    try:
        data = _post(Q_SHORT, {"originUrl": origin_url, "subIds": [subid or SUBID]})
        return (data.get("generateShortLink") or {}).get("shortLink") or ""
    except Exception:
        return ""


def _cache():
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def keyword_for(title, description=""):
    from .select import _chat

    payload = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": (
                "Você escolhe UMA palavra-chave de produto da Shopee Brasil que combine com o "
                "tema de um vídeo curto e com o público que assiste. Responda só JSON: "
                '{"keyword": "2 a 4 palavras, generico, sem marca", "produto": "nome curto do produto"}'
            )},
            {"role": "user", "content": f"Titulo: {title}\nDescricao: {(description or '')[:400]}"},
        ],
    }
    txt = _chat(payload)
    txt = txt[txt.find("{"): txt.rfind("}") + 1]
    data = json.loads(txt)
    return (str(data.get("keyword") or "").strip(), str(data.get("produto") or "").strip())


def pick_for_video(title, description="", keywords=None):
    if not on():
        return None
    cache = _cache()
    key = (title or "").strip().lower()
    if key in cache:
        return cache[key]

    item = None
    if APP_ID and SECRET:
        try:
            item = _from_api(title, description, keywords)
        except Exception:
            item = None
    if item is None:
        item = _from_catalog(title, description, keywords)
    if item:
        cache[key] = item
        _save_cache(cache)
    return item


def _from_api(title, description="", keywords=None):
    keyword = ""
    try:
        keyword, _ = keyword_for(title, description)
    except Exception:
        keyword = ""
    if not keyword:
        for w in (keywords or []):
            if w and len(w) < 30:
                keyword = w
                break
    if not keyword:
        return None

    items = search(keyword)
    if not items:
        items = search(keyword.split()[0])

    best = None
    for it in items:
        score = it["commission"] * 10
        low = it["name"].lower()
        for w in keyword.lower().split():
            if w in low:
                score += 5
        if best is None or score > best[0]:
            best = (score, it)
    if not best:
        return None

    item = dict(best[1])
    item["keyword"] = keyword
    if item["link"] and ("shopee" in item["link"] or "shp.ee" in item["link"]):
        link = short_link(item["link"])
        if link:
            item["short"] = link
    return item


STOP = {
    "de", "da", "do", "das", "dos", "que", "com", "sem", "para", "por", "uma", "uno",
    "the", "and", "corte", "shorts", "video", "videos", "pra", "porque", "mais",
    "seu", "sua", "isso", "aqui", "assim", "quando", "muito", "tudo", "todos",
}


def _tokens(text):
    import re
    return [w for w in re.findall(r"[a-z0-9à-ú]+", (text or "").lower()) if len(w) > 2 and w not in STOP]


def _from_catalog(title, description="", keywords=None):
    items = catalog()
    if not items:
        return None
    text = set(_tokens(f"{title} {description} {' '.join(keywords or [])}"))
    best = None
    for it in items:
        kw = _tokens(it["keyword"])
        score = 0
        if kw and all(w in text for w in kw):
            score += 6
        score += 3 * sum(1 for w in kw if w in text)
        score += sum(1 for w in _tokens(it["name"]) if w in text)
        if score and (best is None or score > best[0]):
            best = (score, it)
    if not best or best[0] < 3:
        return None
    return dict(best[1])


def block(item, style="full"):
    if not item:
        return ""
    name = item.get("name") or item.get("produto") or ""
    link = item.get("short") or item.get("link") or ""
    if not link:
        return ""
    line = f"🛒 {name}" if name else "🛒 Produto indicado"
    if item.get("price"):
        line += f" — R$ {str(item['price']).strip()}"
    if item.get("commission") and style == "full":
        try:
            line += f" (comissão {float(item['commission']):.1f}%)"
        except (TypeError, ValueError):
            pass
    return f"{line}\n{link}"
