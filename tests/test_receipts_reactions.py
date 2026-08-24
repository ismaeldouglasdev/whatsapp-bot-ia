"""Regressao T9: reacao fire-and-forget em comandos (payload + gates)."""
import asyncio

import bot


class FakeResp:
    def __init__(self, status=200):
        self.status = status


class Ctx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, json=None, **k):
        self.posts.append((url, json))
        return Ctx(FakeResp())


class FakeReq:
    def __init__(self, session):
        self.app = {"http": session}


def reset_state():
    bot._state.clear()
    bot._state.update({"sent_today": 0, "contacts": {}, "blacklist": []})
    bot._chat_hour.clear()
    bot._last_sent.clear()


async def _noop(request, jid, args):
    return None


def test_send_reaction_payload_correto():
    s = FakeSession()
    asyncio.run(bot._send_reaction(s, "g@g.us", "ABC123", "\u2705"))
    url, payload = s.posts[0]
    assert url.endswith("/message/sendReaction/bot_ia")
    assert payload["key"] == {"remoteJid": "g@g.us", "fromMe": False, "id": "ABC123"}
    assert payload["reaction"] == "\u2705"


def test_send_reaction_sem_id_nao_chama():
    s = FakeSession()
    asyncio.run(bot._send_reaction(s, "g@g.us", None, "\u2705"))
    assert s.posts == []


def test_send_reaction_falha_engolida():
    class BoomSession:
        def post(self, *a, **k):
            raise RuntimeError("boom")

    asyncio.run(bot._send_reaction(BoomSession(), "g@g.us", "X", "\u2705"))


def test_dispatch_reage_quando_key_presente(monkeypatch):
    monkeypatch.setattr(bot, "REACTIONS", True)
    monkeypatch.setitem(bot.COMMANDS, "__tst", _noop)
    reset_state()
    monkeypatch.setattr(bot, "_rate_block_reason", lambda jid: None)
    s = FakeSession()
    consumido = asyncio.run(
        bot.dispatch_command(FakeReq(s), "x@s.whatsapp.net", ".__tst", key={"id": "M1"})
    )
    assert consumido is True
    assert any("sendReaction" in u for u, _ in s.posts)


def test_dispatch_sem_reactions_nao_reage(monkeypatch):
    monkeypatch.setattr(bot, "REACTIONS", False)
    monkeypatch.setitem(bot.COMMANDS, "__tst", _noop)
    reset_state()
    monkeypatch.setattr(bot, "_rate_block_reason", lambda jid: None)
    s = FakeSession()
    consumido = asyncio.run(
        bot.dispatch_command(FakeReq(s), "x@s.whatsapp.net", ".__tst", key={"id": "M1"})
    )
    assert consumido is True
    assert s.posts == []
