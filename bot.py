#!/usr/bin/env python3
"""
Bot WhatsApp com IA — Evolution API v2 + 9router (LLM local gratuito).

Fluxo:
  WhatsApp → Evolution API (:8083) → webhook POST :8084/webhook
    → filtra (fromMe, grupos, dedup) → monta histórico → 9router (:20131)
    → POST /message/sendText de volta no WhatsApp.

Config por variáveis de ambiente (defaults abaixo). Ex.:
  AI_MODEL=9router/ollama/gpt-oss:120b RESPOND_IN_GROUPS=false ./bot.py
"""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict, defaultdict, deque

import aiohttp
from aiohttp import web

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
EVOLUTION_URL = os.environ.get("EVOLUTION_URL", "http://localhost:8083")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "evolution_bot_2026_key")
INSTANCE = os.environ.get("EVOLUTION_INSTANCE", "bot_ia")

AI_URL = os.environ.get("AI_URL", "http://localhost:20131/v1/chat/completions")
AI_MODEL = os.environ.get("AI_MODEL", "9router/ollama/gpt-oss:120b")
AI_TIMEOUT_S = int(os.environ.get("AI_TIMEOUT_S", "90"))

BOT_PORT = int(os.environ.get("BOT_PORT", "8084"))
HISTORY_TURNS = int(os.environ.get("HISTORY_TURNS", "12"))
RESPOND_IN_GROUPS = os.environ.get("RESPOND_IN_GROUPS", "false").lower() == "true"
REPLY_DELAY_MS = int(os.environ.get("REPLY_DELAY_MS", "1200"))  # simula "digitando"

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "Você é um assistente virtual amigável no WhatsApp. Responda em português "
    "do Brasil, de forma curta e direta (mensagens de WhatsApp devem ser "
    "concisas). Se não souber algo, admita. Nunca invente links.",
)

log = logging.getLogger("wabot")

# ---------------------------------------------------------------------------
# Estado em memória
# ---------------------------------------------------------------------------
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))
_seen_ids: OrderedDict[str, float] = OrderedDict()  # dedup de webhooks repetidos
_SEEN_MAX = 500


def _seen_once(msg_id: str) -> bool:
    """True se é a primeira vez que vemos esse id de mensagem."""
    now = time.time()
    if msg_id in _seen_ids:
        return False
    _seen_ids[msg_id] = now
    while len(_seen_ids) > _SEEN_MAX:
        _seen_ids.popitem(last=False)
    # limpa entradas > 1h
    cutoff = now - 3600
    for k in [k for k, ts in _seen_ids.items() if ts < cutoff]:
        del _seen_ids[k]
    return True


# ---------------------------------------------------------------------------
# Extração de texto do payload Evolution v2
# ---------------------------------------------------------------------------
_TEXT_KEYS = (
    ("conversation",),
    ("extendedTextMessage", "text"),
    ("imageMessage", "caption"),
    ("videoMessage", "caption"),
    ("documentMessage", "caption"),
    ("documentWithCaptionMessage", "message", "caption"),
)


def extract_text(message: dict | None) -> str | None:
    if not isinstance(message, dict):
        return None
    for path in _TEXT_KEYS:
        node: object = message
        for key in path:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(key)
        if isinstance(node, str) and node.strip():
            return node.strip()
    return None


def is_group(remote_jid: str) -> bool:
    return remote_jid.endswith("@g.us")


def was_mentioned(data: dict) -> bool:
    """Heurística: menção do bot em grupo (contextInfo.mentionedJid* contém o próprio jid)."""
    msg = data.get("message") or {}
    ext = msg.get("extendedTextMessage") or {}
    ctx = ext.get("contextInfo") or {}
    mentioned = ctx.get("mentionedJidArray") or ctx.get("mentionedJid") or []
    if isinstance(mentioned, str):
        mentioned = [mentioned]
    # O jid real da instância só existe após conexão; aceita qualquer menção
    # quando RESPOND_IN_GROUPS=true (o filtro fino fica para versão futura).
    return bool(mentioned)


# ---------------------------------------------------------------------------
# Chamadas externas
# ---------------------------------------------------------------------------
async def ask_ai(session: aiohttp.ClientSession, chat_jid: str, user_text: str) -> str:
    hist = list(_history[chat_jid])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += hist
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    async with session.post(
        AI_URL, json=payload, timeout=aiohttp.ClientTimeout(total=AI_TIMEOUT_S)
    ) as resp:
        body = await resp.json(content_type=None)
        if resp.status != 200:
            raise RuntimeError(f"IA HTTP {resp.status}: {str(body)[:200]}")
        content = (body["choices"][0]["message"] or {}).get("content") or ""
        content = content.strip()
        if not content:
            raise RuntimeError(f"IA respondeu vazio: {str(body)[:200]}")
        return content


async def send_whatsapp(session: aiohttp.ClientSession, number: str, text: str) -> None:
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY}
    payload = {
        "number": number,
        "text": text,
        "delay": REPLY_DELAY_MS,
        "linkPreview": False,
    }
    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        body = await resp.json(content_type=None)
        if resp.status not in (200, 201):
            raise RuntimeError(f"sendText HTTP {resp.status}: {str(body)[:300]}")


# ---------------------------------------------------------------------------
# Handler do webhook
# ---------------------------------------------------------------------------
async def handle_webhook(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid json"}, status=400)

    event = payload.get("event", "")
    if event != "messages.upsert":
        return web.json_response({"ok": True, "ignored": event})

    data = payload.get("data") or {}
    key = data.get("key") or {}
    msg_id = key.get("id") or ""
    remote_jid = key.get("remoteJid") or ""
    from_me = bool(key.get("fromMe"))

    if from_me or not remote_jid or remote_jid.startswith("status@"):
        return web.json_response({"ok": True, "skipped": "fromMe/status"})

    if not _seen_once(msg_id):
        return web.json_response({"ok": True, "skipped": "duplicate"})

    text = extract_text(data.get("message"))
    push_name = data.get("pushName") or remote_jid.split("@")[0]

    if is_group(remote_jid):
        if not RESPOND_IN_GROUPS or not was_mentioned(data):
            log.info("[grupo ignorado] %s: %r", push_name, (text or "")[:60])
            return web.json_response({"ok": True, "skipped": "group"})

    if not text:
        log.info("[%s] mensagem sem texto (tipo não suportado)", push_name)
        try:
            async with aiohttp.ClientSession() as sess:
                await send_whatsapp(
                    sess,
                    remote_jid.split("@")[0],
                    "Por enquanto eu só entendo mensagens de texto 😅",
                )
        except Exception as exc:  # noqa: BLE001
            log.error("falha ao avisar sem-texto: %s", exc)
        return web.json_response({"ok": True, "skipped": "no-text"})

    log.info("[%s] %s", push_name, text[:120])

    try:
        answer = await ask_ai(request.app["http"], remote_jid, text)
    except Exception as exc:  # noqa: BLE001
        log.error("erro na IA: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=502)

    # guarda no histórico só depois de resposta bem-sucedida
    _history[remote_jid].append({"role": "user", "content": text})
    _history[remote_jid].append({"role": "assistant", "content": answer})

    try:
        await send_whatsapp(request.app["http"], remote_jid.split("@")[0], answer)
        log.info("→ respondido (%d chars)", len(answer))
    except Exception as exc:  # noqa: BLE001
        log.error("erro ao enviar resposta: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=502)

    return web.json_response({"ok": True})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(
        {"ok": True, "instance": INSTANCE, "model": AI_MODEL, "chats_ativos": len(_history)}
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def http_session_ctx(app: web.Application):
    """Cria/fecha o ClientSession dentro do loop de eventos."""
    app["http"] = aiohttp.ClientSession()
    yield
    await app["http"].close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    app = web.Application()
    app.cleanup_ctx.append(http_session_ctx)
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/health", handle_health)

    log.info("Bot WhatsApp subindo em 0.0.0.0:%s (instância=%s, modelo=%s)", BOT_PORT, INSTANCE, AI_MODEL)
    web.run_app(app, host="0.0.0.0", port=BOT_PORT, print=None)


if __name__ == "__main__":
    main()
