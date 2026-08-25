"""Regressao do watchdog: decisao de disparo + restart capado."""
import asyncio
import time

import bot


def reset(**kw):
    bot._conn_bad_streak = kw.get("streak", 3)
    bot._watchdog_restarts.clear()
    bot._watchdog_suspended_until = 0.0
    bot.WATCHDOG_AUTORESTART = kw.get("auto", True)


def test_dispara_com_streak_3():
    reset()
    assert bot._watchdog_should_fire(time.time()) is True


def test_nao_dispara_autorestart_off():
    reset(auto=False)
    assert bot._watchdog_should_fire(time.time()) is False


def test_gap_minimo_bloqueia():
    reset()
    bot._watchdog_restarts.append(time.time() - 60)  # ha 1min < gap 300s
    assert bot._watchdog_should_fire(time.time()) is False


def test_cap_3_por_hora_bloqueia():
    reset()
    agora = time.time()
    for i in range(3):
        bot._watchdog_restarts.append(agora - 600 * (i + 1))
    assert bot._watchdog_should_fire(agora) is False


def test_suspensao_bloqueia():
    reset()
    bot._watchdog_suspended_until = time.time() + 1000
    assert bot._watchdog_should_fire(time.time()) is False


def test_restart_chama_docker_uma_vez(monkeypatch):
    reset()
    chamadas = []

    def fake_run(*a, **k):
        chamadas.append(a[0] if a else k.get("cmd"))
        class R:
            stdout = "Up 2 hours"
            returncode = 0
        return R()

    monkeypatch.setattr(bot.subprocess, "run", fake_run)
    asyncio.run(bot._watchdog_restart())
    docker_calls = [c for c in chamadas if c and c[0] == "docker" and c[1] == "restart"]
    assert len(docker_calls) == 1
    assert len(bot._watchdog_restarts) == 1


def test_precheck_false_aborta(monkeypatch):
    reset()
    chamadas = []

    def fake_run(*a, **k):
        chamadas.append(a[0] if a else None)

        class R:
            stdout = "Restarting (exit)"  # sem "Up"
            returncode = 0
        return R()

    monkeypatch.setattr(bot.subprocess, "run", fake_run)
    asyncio.run(bot._watchdog_restart())
    assert not any(c and len(c) > 1 and c[1] == "restart" for c in chamadas)


def test_boot_backoff_exponencial_cap_30():
    seq = []
    atual = bot._POLL_BACKOFF_START_S
    for _ in range(6):
        atual = bot._next_poll_interval(atual, fetched=False)
        seq.append(atual)
    assert seq == [4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_sucesso_volta_ritmo_normal():
    assert bot._next_poll_interval(16.0, fetched=True) == 30.0


def test_find_recent_ignora_midia_antiga():
    import time as _t
    from unittest.mock import patch
    recs = {"messages": {"records": [
        {"key": {"id": "VELHO"}, "messageType": "videoMessage",
         "message": {}, "messageTimestamp": int(_t.time()) - 3600},
    ]}}
    class R:
        status = 200
        async def json(self, **k): return recs
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
    class S:
        def post(self, *a, **k): return R()
    bot._media_seen.clear()
    got = asyncio.run(bot._find_recent_media(S(), "x@s.whatsapp.net"))
    assert got is None  # midia de 1h atras ignorada
