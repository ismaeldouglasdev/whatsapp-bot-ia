"""Regressao T10: historico persistente (TTL 7d, cap) + comando .reset."""
import asyncio
import json
import time

import bot


def setup_tmp_state(tmp_path, monkeypatch):
    sf = tmp_path / "state.json"
    monkeypatch.setattr(bot, "STATE_FILE", sf)
    return sf


def test_roundtrip_persistencia(tmp_path, monkeypatch):
    sf = setup_tmp_state(tmp_path, monkeypatch)
    bot._state.clear()
    bot._state.update({"date": "", "sent_today": 0, "blacklist": [], "contacts": {},
                       "history": {}, "reminders": []})
    bot._hist_append("a@s.whatsapp.net", "user", "ola")
    bot._hist_append("a@s.whatsapp.net", "assistant", "oi!")
    bot._save_state()
    # simula restart: state zerado e recarregado do disco
    bot._state.clear()
    bot._state.update({"date": ""})
    bot.STATE_FILE = sf
    bot._load_state()
    hist = bot._hist_get("a@s.whatsapp.net")
    assert [m["content"] for m in hist] == ["ola", "oi!"]


def test_poda_7_dias_no_load(tmp_path, monkeypatch):
    sf = setup_tmp_state(tmp_path, monkeypatch)
    velho = time.time() - 8 * 86400
    novo = time.time()
    sf.write_text(json.dumps({
        "history": {
            "a@s.whatsapp.net": [
                {"role": "user", "content": "antigo", "ts": velho},
                {"role": "user", "content": "novo", "ts": novo},
            ],
            "b@s.whatsapp.net": [{"role": "user", "content": "so-antigo", "ts": velho}],
        }
    }))
    bot._state.clear()
    bot._state.update({"date": ""})
    bot.STATE_FILE = sf
    bot._load_state()
    assert [m["content"] for m in bot._hist_get("a@s.whatsapp.net")] == ["novo"]
    assert "b@s.whatsapp.net" not in bot._state["history"]


def test_cap_history_turns():
    bot._state.clear()
    bot._state.update({"history": {}})
    for i in range(bot.HISTORY_TURNS + 5):
        bot._hist_append("c@s.whatsapp.net", "user", f"m{i}")
    h = bot._hist_get("c@s.whatsapp.net")
    assert len(h) == bot.HISTORY_TURNS
    assert h[-1]["content"] == f"m{bot.HISTORY_TURNS + 4}"


def test_reset_limpa_so_do_chat(monkeypatch):
    bot._state.clear()
    bot._state.update({"sent_today": 0, "contacts": {}, "blacklist": [],
                       "history": {}, "_chat_hour": {}, "reminders": []})
    bot._chat_hour.clear(); bot._last_sent.clear()
    bot._hist_append("x@s.whatsapp.net", "user", "ctx x")
    bot._hist_append("y@s.whatsapp.net", "user", "ctx y")

    captured = []

    async def fake_send(session, number, text, delay_ms):
        captured.append(text)

    monkeypatch.setattr(bot, "send_whatsapp", fake_send)

    class FakeReq:
        class app(dict):
            pass
        app = {"http": None}

    asyncio.run(bot._cmd_reset(FakeReq(), "x@s.whatsapp.net", ""))
    assert "x@s.whatsapp.net" not in bot._state["history"]
    assert bot._hist_get("y@s.whatsapp.net")[0]["content"] == "ctx y"
    assert captured and "limpo" in captured[0]
