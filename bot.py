#!/usr/bin/env python3
"""
Bot WhatsApp com IA — Evolution API v2 + 9router (LLM local gratuito).

Fluxo:
  WhatsApp → Evolution API (:8083) → webhook POST :8084/webhook
    → guardrails (rate limits, horário, opt-out, warm-up)
    → histórico → 9router (:20131) → resposta humanizada no WhatsApp.

Config por variáveis de ambiente (defaults conservadores abaixo).
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

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
STATE_FILE = Path(os.environ.get("STATE_FILE", str(Path(__file__).parent / "state.json")))

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "Você é um assistente virtual amigável no WhatsApp. Responda em português "
    "do Brasil, de forma curta e direta (mensagens de WhatsApp devem ser "
    "concisas). Se não souber algo, admita. Nunca invente links. Nunca peça "
    "dados sensíveis (senha, cartão, CPF).",
)

# --- Guardrails: anti-ban ---------------------------------------------------
WARMUP = os.environ.get("WARMUP", "true").lower() == "true"

DAILY_SEND_CAP = int(os.environ.get("DAILY_SEND_CAP", "25" if WARMUP else "150"))
HOURLY_SEND_CAP = int(os.environ.get("HOURLY_SEND_CAP", "6" if WARMUP else "25"))
PER_CHAT_HOURLY_CAP = int(os.environ.get("PER_CHAT_HOURLY_CAP", "4" if WARMUP else "8"))
NEW_CONTACT_DAILY_CAP = int(os.environ.get("NEW_CONTACT_DAILY_CAP", "3" if WARMUP else "5"))
MIN_REPLY_GAP_S = int(os.environ.get("MIN_REPLY_GAP_S", "20"))
MAX_REPLY_CHARS = int(os.environ.get("MAX_REPLY_CHARS", "900"))
ALLOW_LINKS = os.environ.get("ALLOW_LINKS", "false").lower() == "true"
ACTIVE_HOURS = os.environ.get("ACTIVE_HOURS", "8-23")  # "8-23" ou "off"
CONTACT_MATURITY_IN = int(os.environ.get("CONTACT_MATURITY_IN", "5"))  # msgs recebidas
CONTACT_MATURITY_DAYS = float(os.environ.get("CONTACT_MATURITY_DAYS", "3"))

OPT_OUT_RE = re.compile(r"^\s*/?(sair|parar|stop|descadastrar|remover)\s*$", re.I)
OPT_IN_RE = re.compile(r"^\s*/?(voltar|start|optin)\s*$", re.I)
LINK_RE = re.compile(r"https?://\S+|www\.\S+", re.I)

log = logging.getLogger("wabot")

# ---------------------------------------------------------------------------
# Estado persistente (contadores diários, blacklist, contatos)
# ---------------------------------------------------------------------------
_state: dict = {"date": "", "sent_today": 0, "blacklist": [], "contacts": {}}


def _load_state() -> None:
    if STATE_FILE.exists():
        try:
            _state.update(json.loads(STATE_FILE.read_text()))
        except Exception as exc:  # noqa: BLE001
            log.error("state.json corrompido (%s) — começando limpo", exc)
    today = datetime.now().strftime("%Y-%m-%d")
    if _state.get("date") != today:  # reset diário
        _state["date"] = today
        _state["sent_today"] = 0
    _state.setdefault("blacklist", [])
    _state.setdefault("contacts", {})


def _save_state() -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state, ensure_ascii=False))
    tmp.replace(STATE_FILE)


def _contact(jid: str) -> dict:
    return _state["contacts"].setdefault(
        jid, {"first_seen": time.time(), "total_in": 0, "total_out": 0}
    )


def _is_new_contact(jid: str) -> bool:
    c = _contact(jid)
    age_days = (time.time() - c["first_seen"]) / 86400
    return c["total_in"] < CONTACT_MATURITY_IN and age_days < CONTACT_MATURITY_DAYS


# ---------------------------------------------------------------------------
# Rate limiting (janelas deslizantes em memória)
# ---------------------------------------------------------------------------
_global_hour: deque = deque()
_chat_hour: dict[str, deque] = defaultdict(deque)
_last_sent: dict[str, float] = {}


def _prune(dq: deque, window_s: float) -> None:
    cutoff = time.time() - window_s
    while dq and dq[0] < cutoff:
        dq.popleft()


def _rate_block_reason(chat_jid: str) -> str | None:
    """Retorna o motivo do bloqueio ou None se pode enviar."""
    now = time.time()

    if _state["sent_today"] >= DAILY_SEND_CAP:
        return f"teto diário ({DAILY_SEND_CAP})"
    _prune(_global_hour, 3600)
    if len(_global_hour) >= HOURLY_SEND_CAP:
        return f"teto horário global ({HOURLY_SEND_CAP})"

    ch = _chat_hour[chat_jid]
    _prune(ch, 3600)
    if len(ch) >= PER_CHAT_HOURLY_CAP:
        return f"teto horário do chat ({PER_CHAT_HOURLY_CAP})"

    if _is_new_contact(chat_jid):
        day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        sent_today_to_chat = sum(1 for ts in ch if ts >= day_start)
        if sent_today_to_chat >= NEW_CONTACT_DAILY_CAP:
            return f"contato novo (cap {NEW_CONTACT_DAILY_CAP}/dia)"

    gap = now - _last_sent.get(chat_jid, 0)
    if gap < MIN_REPLY_GAP_S:
        return f"gap mínimo ({MIN_REPLY_GAP_S}s)"

    return None


def _register_send(chat_jid: str) -> None:
    now = time.time()
    _global_hour.append(now)
    _chat_hour[chat_jid].append(now)
    _last_sent[chat_jid] = now
    _contact(chat_jid)["total_out"] += 1
    _state["sent_today"] += 1
    _save_state()


# ---------------------------------------------------------------------------
# Humanização e sanitização
# ---------------------------------------------------------------------------
def humanize_delay_ms(text: str) -> int:
    """Simula digitação: ~30ms/caractere + base, com jitter ±20%."""
    base = 1200 + min(len(text) * 30, 4500)
    jitter = int(base * 0.2)
    return random.randint(base - jitter, base + jitter)


def sanitize_reply(text: str) -> str:
    if not ALLOW_LINKS:
        text = LINK_RE.sub("(link removido)", text)
    text = text.strip()
    if len(text) > MAX_REPLY_CHARS:
        cut = text.rfind("\n", 0, MAX_REPLY_CHARS)
        if cut < MAX_REPLY_CHARS // 2:
            cut = text.rfind(" ", 0, MAX_REPLY_CHARS)
        text = text[: cut if cut > 0 else MAX_REPLY_CHARS].rstrip() + "…"
    return text


def _in_active_hours() -> bool:
    if ACTIVE_HOURS.lower() == "off":
        return True
    try:
        start_h, end_h = (int(x) for x in ACTIVE_HOURS.split("-"))
        return start_h <= datetime.now().hour < end_h
    except ValueError:
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


RESPOND_IN_GROUPS = os.environ.get("RESPOND_IN_GROUPS", "false").lower() == "true"


def was_mentioned(data: dict) -> bool:
    msg = data.get("message") or {}
    ctx = ((msg.get("extendedTextMessage") or {}).get("contextInfo")) or {}
    mentioned = ctx.get("mentionedJidArray") or ctx.get("mentionedJid") or []
    if isinstance(mentioned, str):
        mentioned = [mentioned]
    return bool(mentioned)


# ---------------------------------------------------------------------------
# Dedup + histórico
# ---------------------------------------------------------------------------
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_TURNS))
_seen_ids: dict[str, float] = {}
_SEEN_MAX = 500


def _seen_once(msg_id: str) -> bool:
    now = time.time()
    if msg_id in _seen_ids:
        return False
    _seen_ids[msg_id] = now
    while len(_seen_ids) > _SEEN_MAX:
        del _seen_ids[next(iter(_seen_ids))]  # remove o mais antigo (FIFO)
    cutoff = now - 3600
    for k in [k for k, ts in _seen_ids.items() if ts < cutoff]:
        del _seen_ids[k]
    return True


async def ask_ai(session: aiohttp.ClientSession, chat_jid: str, user_text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += list(_history[chat_jid])
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


async def send_whatsapp(
    session: aiohttp.ClientSession, number: str, text: str, delay_ms: int
) -> None:
    url = f"{EVOLUTION_URL}/message/sendText/{INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY}
    payload = {"number": number, "text": text, "delay": delay_ms, "linkPreview": False}
    async with session.post(
        url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
    ) as resp:
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

    if key.get("fromMe") or not remote_jid or remote_jid.startswith("status@"):
        return web.json_response({"ok": True, "skipped": "fromMe/status"})

    if not _seen_once(msg_id):
        return web.json_response({"ok": True, "skipped": "duplicate"})

    text = extract_text(data.get("message"))
    push_name = data.get("pushName") or remote_jid.split("@")[0]
    _contact(remote_jid)["total_in"] += 1

    if is_group(remote_jid):
        if not RESPOND_IN_GROUPS or not was_mentioned(data):
            log.info("[grupo ignorado] %s: %r", push_name, (text or "")[:60])
            return web.json_response({"ok": True, "skipped": "group"})

    if not text:
        log.info("[%s] mensagem sem texto", push_name)
        return web.json_response({"ok": True, "skipped": "no-text"})
    _save_state()

    # --- Opt-out / opt-in (LGPD + boa prática) ------------------------------
    if OPT_OUT_RE.match(text):
        if remote_jid not in _state["blacklist"]:
            _state["blacklist"].append(remote_jid)
            _save_state()
            await _try_send(
                request, remote_jid, "Tudo bem! Você não receberá mais mensagens minhas. 🙏"
            )
        return web.json_response({"ok": True, "action": "optout"})

    if OPT_IN_RE.match(text) and remote_jid in _state["blacklist"]:
        _state["blacklist"].remove(remote_jid)
        _save_state()
        await _try_send(request, remote_jid, "Que bom te ver de volta! ✅")
        return web.json_response({"ok": True, "action": "optin"})

    if remote_jid in _state["blacklist"]:
        log.info("[blacklist] %s", push_name)
        return web.json_response({"ok": True, "skipped": "blacklisted"})

    # --- Guardrails anti-ban -------------------------------------------------
    if not _in_active_hours():
        log.info("[fora do horário %s] %s", ACTIVE_HOURS, push_name)
        return web.json_response({"ok": True, "skipped": "inactive-hours"})

    reason = _rate_block_reason(remote_jid)
    if reason:
        log.warning("[RATE LIMIT: %s] mensagem de %s ignorada", reason, push_name)
        return web.json_response({"ok": True, "skipped": f"rate:{reason}"})

    log.info("[%s] %s", push_name, text[:120])

    # --- IA + resposta -------------------------------------------------------
    try:
        answer = await ask_ai(request.app["http"], remote_jid, text)
    except Exception as exc:  # noqa: BLE001
        log.error("erro na IA: %s", exc)
        return web.json_response({"ok": False, "error": str(exc)}, status=502)

    answer = sanitize_reply(answer)
    _history[remote_jid].append({"role": "user", "content": text})
    _history[remote_jid].append({"role": "assistant", "content": answer})

    ok = await _try_send(request, remote_jid, answer)
    if ok:
        _register_send(remote_jid)
        log.info(
            "→ respondido (%d chars) | enviados hoje: %d/%d",
            len(answer), _state["sent_today"], DAILY_SEND_CAP,
        )
    return web.json_response({"ok": ok})


async def _try_send(request: web.Request, remote_jid: str, text: str) -> bool:
    try:
        await send_whatsapp(
            request.app["http"],
            remote_jid.split("@")[0],
            text,
            humanize_delay_ms(text),
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("erro ao enviar: %s", exc)
        return False


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response(
        {
            "ok": True,
            "instance": INSTANCE,
            "model": AI_MODEL,
            "warmup": WARMUP,
            "enviados_hoje": _state["sent_today"],
            "cap_diario": DAILY_SEND_CAP,
            "blacklist": len(_state["blacklist"]),
            "chats_ativos": len(_history),
        }
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def http_session_ctx(app: web.Application):
    app["http"] = aiohttp.ClientSession()
    yield
    await app["http"].close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    _load_state()
    app = web.Application()
    app.cleanup_ctx.append(http_session_ctx)
    app.router.add_post("/webhook", handle_webhook)
    app.router.add_get("/health", handle_health)

    log.info(
        "Bot subindo :%s | instância=%s modelo=%s | WARMUP=%s caps: %d/dia %d/h %d/chat/h",
        BOT_PORT, INSTANCE, AI_MODEL, WARMUP,
        DAILY_SEND_CAP, HOURLY_SEND_CAP, PER_CHAT_HOURLY_CAP,
    )
    web.run_app(app, host="0.0.0.0", port=BOT_PORT, print=None)


if __name__ == "__main__":
    main()
