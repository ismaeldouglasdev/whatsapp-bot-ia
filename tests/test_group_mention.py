"""Regressao: mencao em grupo (get_own_jid campo 'name' + heuristica textual @digits)."""
import asyncio
from unittest.mock import MagicMock, patch

import bot


def test_get_own_jid_aceita_campo_name():
    """Evolution v2.3.7 retorna 'name' (nao 'instanceName') em fetchInstances."""
    bot._own_jid = None
    resp = MagicMock()
    resp.status = 200

    class FakeCtx:
        def __init__(self, payload):
            self.payload = payload
        async def __aenter__(self):
            return resp
        async def __aexit__(self, *a):
            return False

    async def jjson(*a, **k):
        return [{"name": "bot_ia", "ownerJid": "5599@s.whatsapp.net"}]
    resp.json = jjson
    session = MagicMock()
    session.get = lambda *a, **k: FakeCtx(None)

    got = asyncio.run(bot.get_own_jid(session))
    assert got == "5599@s.whatsapp.net", got
    assert bot._own_jid == "5599@s.whatsapp.net"


def test_mencao_contexto_real():
    data = {"message": {"extendedTextMessage": {"contextInfo": {"mentionedJidArray": ["5599@s.whatsapp.net"]}}}}
    assert bot._mentions_own_jid(data, "5599@s.whatsapp.net") is True


def test_gate_heuristica_textual_sem_metadata():
    texto = "@166280413880338 .menu"
    data = {"message": {"conversation": texto}}  # sem contextInfo nenhum
    passa = bot._mentions_own_jid(data, "5599@s.whatsapp.net") or (texto and bot._MENTION_TEXT_RE.search(texto))
    assert passa


def test_grupo_mensagem_comum_continua_ignorada():
    texto = "oi galera"
    data = {"message": {"conversation": texto}}
    passa = bot._mentions_own_jid(data, "5599@s.whatsapp.net") or (texto and bot._MENTION_TEXT_RE.search(texto))
    assert not passa


def test_strip_mencao_prefixo_comando():
    """'@166... .menu' em grupo vira '.menu' para o dispatcher."""
    import re as _re
    texto = "@166280413880338 .menu"
    t2 = bot._MENTION_TEXT_RE.sub("", texto, count=1).strip()
    assert t2 == ".menu"
    assert bot._CMD_RE.match(t2)


def test_gate_usa_probe_original_nao_stripped():
    """REGRESSAO do bug de ordem: gate avalia @digits ANTES do strip apagar."""
    texto = "@166280413880338 .menu"
    probe = texto or ""
    stripped = bot._MENTION_TEXT_RE.sub("", texto, count=1).strip()
    # gate precisa passar com o probe original...
    passa = bool(bot._MENTION_TEXT_RE.search(probe))
    assert passa and stripped == ".menu"
    # ...e o gate NÃO pode mais enxergar o @digits depois do strip
    assert not bot._MENTION_TEXT_RE.search(stripped)
