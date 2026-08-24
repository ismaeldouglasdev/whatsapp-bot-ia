"""Regressao T11: .resumo/.traduz/.lembrar/.piada."""
import asyncio

import pytest

import bot


class FakeReq:
    def __init__(self):
        self.app = {"http": None}


def reset_state():
    bot._state.clear()
    bot._state.update({"sent_today": 0, "contacts": {}, "blacklist": [],
                       "history": {}, "reminders": [], "date": ""})
    bot._chat_hour.clear()
    bot._last_sent.clear()


def captor():
    enviadas = []

    async def fake_try_send(req, jid, text):
        enviadas.append(text)
        return True

    return enviadas, fake_try_send


def test_menu_contem_os_4_novos():
    for cmd in (".resumo", ".traduz", ".lembrar", ".piada", ".reset"):
        assert cmd in bot.MENU_TEXT


def test_quoted_text_conversation_e_extended():
    d1 = {"message": {"extendedTextMessage": {"contextInfo": {
        "quotedMessage": {"conversation": "texto citado"}}}}}
    assert bot._quoted_text(d1) == "texto citado"
    d2 = {"message": {"extendedTextMessage": {"contextInfo": {
        "quotedMessage": {"extendedTextMessage": {"text": "citado ext"}}}}}}
    assert bot._quoted_text(d2) == "citado ext"
    assert bot._quoted_text(None) is None


def test_lembrar_formato_invalido(monkeypatch):
    reset_state()
    enviadas, fake = captor()
    monkeypatch.setattr(bot, "_try_send", fake)
    asyncio.run(bot._cmd_lembrar(FakeReq(), "x@s.whatsapp.net", "25:99 nada"))
    assert any("Formato" in t for t in enviadas)


def test_lembrar_valido_agenda(monkeypatch):
    reset_state()
    enviadas, fake = captor()
    monkeypatch.setattr(bot, "_try_send", fake)
    asyncio.run(bot._cmd_lembrar(FakeReq(), "x@s.whatsapp.net", "23:59 pagar boleto"))
    assert any("Anotado" in t for t in enviadas)
    rs = bot._state["reminders"]
    assert len(rs) == 1 and rs[0]["jid"] == "x@s.whatsapp.net" and "boleto" in rs[0]["text"]


def test_lembrar_cap_5_por_chat(monkeypatch):
    reset_state()
    enviadas, fake = captor()
    monkeypatch.setattr(bot, "_try_send", fake)
    base = __import__("time").time() + 7200
    for i in range(5):
        bot._state["reminders"].append({"jid": "x@s.whatsapp.net", "ts": base + i * 3600, "text": f"r{i}"})
    asyncio.run(bot._cmd_lembrar(FakeReq(), "x@s.whatsapp.net", "23:59 sexto"))
    assert any("5 lembretes ativos" in t for t in enviadas)
    assert len([r for r in bot._state["reminders"] if r["jid"] == "x@s.whatsapp.net"]) == 5


def test_resumo_exige_citacao_longa(monkeypatch):
    reset_state()
    enviadas, fake = captor()
    monkeypatch.setattr(bot, "_try_send", fake)
    bot._last_data["x@s.whatsapp.net"] = {"message": {"conversation": "curto"}}
    chamou = {"n": 0}

    async def fake_ask(*a, **k):
        chamou["n"] += 1
        return "- ponto"

    monkeypatch.setattr(bot, "ask_ai", fake_ask)
    asyncio.run(bot._cmd_resumo(FakeReq(), "x@s.whatsapp.net", ""))
    assert any("cite" in t.lower() for t in enviadas)
    assert chamou["n"] == 0


def test_resumo_com_quote_longa_resume(monkeypatch):
    reset_state()
    enviadas, fake = captor()
    monkeypatch.setattr(bot, "_try_send", fake)
    bot._last_data["x@s.whatsapp.net"] = {"message": {"extendedTextMessage": {
        "text": "msg atual",
        "contextInfo": {"quotedMessage": {"conversation": "x" * 500}}}}}

    async def fake_ask(*a, **k):
        return "- ponto 1\n- ponto 2"

    monkeypatch.setattr(bot, "ask_ai", fake_ask)
    asyncio.run(bot._cmd_resumo(FakeReq(), "x@s.whatsapp.net", ""))
    assert any(t.startswith("📝") for t in enviadas)
