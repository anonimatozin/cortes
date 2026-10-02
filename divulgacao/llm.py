"""Cliente da IA (Groq) usado por todos os submódulos.

Reaproveita a mesma chave do projeto (GROQ_API_KEY no .env da raiz). Se a chave
não existir ou `ia.modo: off`, os chamadores caem num fallback determinístico —
o módulo nunca quebra por falta de IA.
"""

import json
import re
import time

import requests

from . import config


class SemIA(RuntimeError):
    """Chave ausente ou IA desligada."""


def disponivel():
    return config.ia_disponivel()


def chat(user, system=None, json_mode=True, temperatura=None, max_tokens=2000, tentativas=4):
    """Devolve o texto cru da resposta. Lança SemIA se a IA estiver indisponível."""
    if not disponivel():
        raise SemIA("IA indisponivel (chave vazia ou ia.modo=off)")

    mensagens = []
    if system:
        mensagens.append({"role": "system", "content": system})
    mensagens.append({"role": "user", "content": user})

    payload = {
        "model": config.GROQ_MODEL,
        "messages": mensagens,
        "temperature": config.IA_TEMPERATURA if temperatura is None else temperatura,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    ultimo = None
    for tentativa in range(tentativas):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                json=payload,
                timeout=180,
            )
        except requests.RequestException as exc:
            ultimo = RuntimeError(f"Groq sem rede: {exc}")
            time.sleep(min(30, 4 * (2 ** tentativa)))
            continue

        if r.status_code in (429, 500, 502, 503, 504):
            ultimo = RuntimeError(f"Groq {r.status_code}: {r.text[:150]}")
            time.sleep(min(60, 6 * (2 ** tentativa)))
            continue
        if r.status_code == 400 and json_mode:
            # alguns modelos não aceitam response_format; tenta de novo sem
            payload.pop("response_format", None)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise ultimo or RuntimeError("Groq esgotou as tentativas")


def extrair_json(texto):
    texto = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip(), flags=re.M).strip()
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim == -1:
        raise ValueError(f"JSON nao encontrado: {texto[:200]}")
    return json.loads(texto[inicio : fim + 1])


def chat_json(user, system=None, temperatura=None, max_tokens=2000):
    """Devolve o dict da resposta. Lança SemIA/ValueError em caso de falha."""
    cru = chat(user, system=system, json_mode=True, temperatura=temperatura, max_tokens=max_tokens)
    return extrair_json(cru)
