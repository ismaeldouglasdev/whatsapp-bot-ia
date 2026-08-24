"""Regressao T5: webhook fail-closed por token de URL/header."""
import asyncio

from aiohttp import web

import bot


class FakeReq:
    def __init__(self, query=None, headers=None):
        self.query = query or {}
        self.headers = headers or {}
        self.remote = "127.0.0.1"
        self.json_called = False

    async def json(self):
        self.json_called = True
        return {"event": "messages.upsert", "data": {"key": {"fromMe": True, "id": "x", "remoteJid": "y@s.whatsapp.net"}}}


def run(req):
    return asyncio.run(bot.handle_webhook(req))


def setup(monkeypatch, token):
    monkeypatch.setattr(bot, "WEBHOOK_TOKEN", token)


def test_sem_token_configurado_fechado_403(monkeypatch):
    setup(monkeypatch, "")
    req = FakeReq(query={"token": ""})
    resp = run(req)
    assert resp.status == 403 and not req.json_called


def test_token_errado_403(monkeypatch):
    setup(monkeypatch, "segredo")
    req = FakeReq(query={"token": "errado"})
    resp = run(req)
    assert resp.status == 403 and not req.json_called


def test_token_query_ok_processa(monkeypatch):
    setup(monkeypatch, "segredo")
    req = FakeReq(query={"token": "segredo"})
    resp = run(req)
    assert resp.status == 200 and req.json_called


def test_token_header_ok_processa(monkeypatch):
    setup(monkeypatch, "segredo")
    req = FakeReq(headers={"X-Webhook-Token": "segredo"})
    resp = run(req)
    assert resp.status == 200 and req.json_called
