"""Regressao: `.s` na propria mensagem de midia (legenda) converte imagem → figurinha.

Cobre o fix em bot.py: quando imagem + `.s` chegam NA MESMA mensagem via webhook,
o `.s` handler deve usar o cache da mensagem atual (msg_id) em vez de falhar com
"stickerk-miss" depois de `_find_recent_media` nao encontrar nada.

Fluxo real simulado:
  webhook POST /webhook  →  handle_webhook
    1. has_img=True, media_b64 presente (Evolution injeta base64 em message.base64)
    2. media baixada/cacheadas sob msg_id via _media_cache_put
    3. text='.s' → branch def fix: `if not alvo and msg_id and has_img`
       → _media_cache_get(msg_id) encontrado → alvo definido
    4. make_sticker_raw(b64) → send_sticker (mockado) → resposta {"ok":True,"action":"sticker-s"}
"""
import asyncio
import base64
import io

from aiohttp import web
from PIL import Image

import bot


def _png_b64() -> str:
    """Gera um PNG real 512x512 valido para make_sticker_raw processar."""
    img = Image.new("RGBA", (512, 512), (200, 30, 30, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


class FakeSession:
    """Mock de aiohttp.ClientSession: POST atendido sem rede, refletindo status."""

    def __init__(self):
        self.calls = []

    class _Resp:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        async def json(self, content_type=None):
            return self._body

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        # sendSticker e getBase64 -> 201 ok
        return _AsyncCtx(self._Resp(201, {"ok": True}))


class _AsyncCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class FakeReq:
    def __init__(self, payload, session=None):
        self.query = {"token": bot.WEBHOOK_TOKEN or "teste-token"}
        self.headers = {}
        self.remote = "127.0.0.1"
        self._payload = payload
        self.app = {"http": session or FakeSession()}

    async def json(self):
        return self._payload


def _payload_img_com_legenda_s(msg_id="MSG_IMG_S_001", jid="5511999999999@s.whatsapp.net"):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"id": msg_id, "remoteJid": jid, "fromMe": False},
            "message": {
                "imageMessage": {
                    "mimetype": "image/png",
                    "caption": ".s",
                },
                "base64": _png_b64(),
            },
            "pushName": "tester",
        },
    }


def run(req):
    return asyncio.run(bot.handle_webhook(req))


def setup(monkeypatch):
    monkeypatch.setattr(bot, "WEBHOOK_TOKEN", "teste-token")
    # zera caches globais para isolamento
    monkeypatch.setattr(bot, "_seen_ids", {})
    monkeypatch.setattr(bot, "_media_seen", set())
    monkeypatch.setattr(bot, "_media_cache", {})
    monkeypatch.setattr(bot, "_sticker_intent", {})
    monkeypatch.setattr(
        bot, "_state",
        {"date": "", "sent_today": 0, "blacklist": [], "contacts": {}},
    )


def _resp_body(resp) -> dict:
    raw = resp.body.read() if hasattr(resp.body, "read") else resp.body
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode()
    import json
    return json.loads(raw) if isinstance(raw, str) else raw


def test_s_legenda_usa_cache_da_mensagem_atual(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(bot, "_register_send", lambda *a, **k: None)
    session = FakeSession()
    req = FakeReq(_payload_img_com_legenda_s(), session=session)
    resp = run(req)
    # handler deve responder sticker-s (e NAO sticker-miss)
    assert resp.status == 200
    body = _resp_body(resp)
    assert body.get("action") == "sticker-s", f"esperado sticker-s, veio {body}"
    # sendSticker deve ter sido chamado
    send_urls = [u for u, _ in session.calls if "sendSticker" in u]
    assert send_urls, "send_sticker nao foi chamado"


def test_s_sem_midia_no_cache_retorna_sticker_miss(monkeypatch):
    """Sem imagem/video na mensagem e sem cache, cai no sticker-miss (nao crasha)."""
    setup(monkeypatch)
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "MSG_TXT_002", "remoteJid": "5511999999999@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": ".s"},
            "pushName": "tester",
        },
    }
    req = FakeReq(payload)
    resp = run(req)
    assert resp.status == 200
    assert _resp_body(resp).get("action") == "sticker-miss"


def test_extract_media_url_video_message():
    """extract_media_url DEVE achar mediaUrl dentro de videoMessage (fix regressao).

    Antes, extract_media_url so checava imageMessage.mediaUrl — o webhook de video
    traz mediaUrl dentro de videoMessage, entao o download de video falhava
    ("video download result=False") e o .s nunca achava a midia.
    """
    assert bot.extract_media_url(
        {"message": {"videoMessage": {"mediaUrl": "http://minio:9000/x/v.mp4"}}}
    ) == "http://minio:9000/x/v.mp4"
    assert bot.extract_media_url(
        {"message": {"imageMessage": {"mediaUrl": "http://minio:9000/x/i.jpg"}}}
    ) == "http://minio:9000/x/i.jpg"
    assert bot.extract_media_url(
        {"message": {"documentMessage": {"mediaUrl": "http://minio:9000/x/d.pdf"}}}
    ) == "http://minio:9000/x/d.pdf"
    assert bot.extract_media_url({"message": {"conversation": ".s"}}) is None


def test_s_legenda_usa_cache_video(monkeypatch):
    """Legenda .s em videoMessage usa o cache da mensagem atual (mesmo fix)."""
    setup(monkeypatch)
    monkeypatch.setattr(bot, "_register_send", lambda *a, **k: None)
    if not bot._video_sticker_ok:
        import pytest
        pytest.skip("ffmpeg indisponivel para figurinha de video")
    session = FakeSession()
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "MSG_VID_S_003", "remoteJid": "5511999999999@s.whatsapp.net", "fromMe": False},
            "message": {
                "videoMessage": {
                    "mimetype": "video/mp4",
                    "caption": ".s",
                    "base64": "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDE=",
                },
            },
            "pushName": "tester",
        },
    }
    req = FakeReq(payload, session=session)
    resp = run(req)
    # O handler DEVE localizar o video no cache da mensagem atual e tentar a
    # conversao — a falha de conversao (502) prova isso. Retornar sticker-miss
    # (200, "no media found") indicaria que o fix regrediu.
    assert resp.status != 200 or _resp_body(resp).get("action") != "sticker-miss"


def test_s_texto_separado_acha_cache_do_chat(monkeypatch):
    """Video mandado ANTES (msg_id proprio via LID) e .s como TEXTO depois (via telefone).

    O usuario manda o video e so depois escreve .s. O .s nao e midia nem citacao:
    sem o lookup por chat (chat-scoped cache), ele nao acharia o video recém baixado.
    """
    setup(monkeypatch)
    monkeypatch.setattr(bot, "_register_send", lambda *a, **k: None)
    monkeypatch.setattr(bot, "_jid_alt", {"144852201267289@lid": "5511999999999@s.whatsapp.net"})
    # video chega primeiro, via LID
    video_msg_id = "MSG_VID_001"
    bot._media_cache_put(video_msg_id, "video", "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDE=", "144852201267289@lid")
    # .s chega depois como TEXTO via telefone
    session = FakeSession()
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"id": "MSG_TXT_003", "remoteJid": "5511999999999@s.whatsapp.net", "fromMe": False},
            "message": {"conversation": ".s"},
            "pushName": "tester",
        },
    }
    req = FakeReq(payload, session=session)
    resp = run(req)
    # o handler DEVE achar a midia cacheada do chat (mesmo vindo via LID) e converter
    assert resp.status != 200 or _resp_body(resp).get("action") != "sticker-miss"
