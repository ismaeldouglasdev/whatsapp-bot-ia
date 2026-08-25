"""Regressao do circuit breaker da IA: cooldown por classe, skip, ordenacao."""
import asyncio
import json
import time

import pytest

import bot


class FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body
        self.headers = {"Content-Type": "application/json"}

    async def text(self):
        return self._body


class Ctx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class BoomCtx:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, script):
        self.script = list(script)
        self.attempted = []

    def post(self, url, json=None, **k):
        self.attempted.append(json["model"])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            return BoomCtx(item)
        return Ctx(FakeResp(*item))


def ok_body(content="oi"):
    return json.dumps({"choices": [{"message": {"content": content}}]})


def reset():
    bot._model_cooldown.clear()
    bot._ia_stats.clear()
    bot.AI_MODELS = "modelo-a,modelo-b"


def test_429_responde_no_segundo_e_coolldown_90s():
    reset()
    s = FakeSession([(429, '{"error":"rate"}'), (200, ok_body("resposta b"))])
    out = asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))
    assert out == "resposta b"
    assert s.attempted == ["modelo-a", "modelo-b"]
    restante = bot._model_cooldown["modelo-a"] - time.time()
    assert 80 <= restante <= 90


def test_proxima_chamada_pula_modelo_em_cooldown():
    reset()
    s1 = FakeSession([(429, "err"), (200, ok_body("b1"))])
    asyncio.run(bot.ask_ai(s1, "chat", "oi", use_history=False))
    s2 = FakeSession([(200, ok_body("b2"))])
    out = asyncio.run(bot.ask_ai(s2, "chat", "oi", use_history=False))
    assert out == "b2"
    assert s2.attempted == ["modelo-b"]


def test_timeout_vira_cooldown_120s():
    reset()
    s = FakeSession([asyncio.TimeoutError(), (200, ok_body("ok"))])
    asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))
    restante = bot._model_cooldown["modelo-a"] - time.time()
    assert 110 <= restante <= 120


def test_402_vira_cooldown_300s():
    reset()
    s = FakeSession([(402, "credits"), (200, ok_body("ok"))])
    asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))
    restante = bot._model_cooldown["modelo-a"] - time.time()
    assert 290 <= restante <= 300


def test_todos_falham_levanta_ai_unavailable():
    reset()
    s = FakeSession([(429, "e1"), (402, "e2")])
    with pytest.raises(bot.AiUnavailable):
        asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))


def test_ordenacao_saudavel_primeiro():
    reset()
    bot._ia_stats["modelo-b"] = {"ok": 0, "fail": 3}
    s = FakeSession([(200, ok_body("via-a"))])
    out = asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))
    assert out == "via-a"
    assert s.attempted == ["modelo-a"]


def test_ordenacao_prefere_mais_rapido_com_saude_igual():
    reset()
    # ambos 100% ok, mas B respondeu 3x mais rápido no histórico
    bot._ia_stats["modelo-a"] = {"ok": 4, "fail": 0, "last_ms": 9000}
    bot._ia_stats["modelo-b"] = {"ok": 4, "fail": 0, "last_ms": 1500}
    s = FakeSession([(200, ok_body("rapido"))])
    out = asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))
    assert s.attempted[0] == "modelo-b"
    assert out == "rapido"


def test_saude_pesa_mais_que_velocidade():
    reset()
    # A rápido mas instável (50%), B lento porém sólido (100%)
    bot._ia_stats["modelo-a"] = {"ok": 2, "fail": 2, "last_ms": 800}
    bot._ia_stats["modelo-b"] = {"ok": 6, "fail": 0, "last_ms": 6000}
    s = FakeSession([(200, ok_body("via-b"))])
    asyncio.run(bot.ask_ai(s, "chat", "oi", use_history=False))
    assert s.attempted[0] == "modelo-b"
