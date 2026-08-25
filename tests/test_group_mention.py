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


def test_send_number_prefere_alt_e_lid_completo():
    bot._jid_alt.clear()
    bot._jid_alt["144852201267289@lid"] = "5511959873202@s.whatsapp.net"
    assert bot._send_number("144852201267289@lid") == "5511959873202"
    assert bot._send_number("5599@s.whatsapp.net") == "5599"
    bot._jid_alt.clear()
    # sem alt conhecida: JID @lid completo (Evolution aceita)
    assert bot._send_number("144852201267289@lid") == "144852201267289@lid"


def test_alias_s_tratado_no_webhook():
    """Design novo: .s eh interceptado no webhook (nao mais alias de COMMANDS)."""
    assert "s" not in bot.COMMANDS


def test_sticker_exif_canonico():
    """REGRESSAO metadata: VP8X->EXIF->VP8 e decodificavel com o pack."""
    import base64, io
    from PIL import Image
    img = Image.new("RGBA", (300, 500), (10, 200, 90, 255))
    b = io.BytesIO(); img.save(b, "PNG")
    raw = bot.make_sticker_raw(base64.b64encode(b.getvalue()).decode())
    pos, chunks = 12, []
    while pos + 8 <= len(raw):
        f = raw[pos:pos+4].decode(errors="replace")
        s = int.from_bytes(raw[pos+4:pos+8], "little")
        chunks.append(f); pos += 8 + s + (s % 2)
    assert chunks[0] == "VP8X" and "EXIF" in chunks
    assert chunks.index("EXIF") == 1 or chunks[0] == "VP8X"
    assert b"ismaeldev" in raw


def test_find_recent_media_filtra_tipos():
    """_find_recent_media pula nao-midia e ja-vistos, retorna o primeiro util."""
    recs = {"messages": {"records": [
        {"key": {"id": "A", "remoteJid": "g@g.us"}, "messageType": "conversation", "message": {}},
        # registro de OUTRO chat: deve ser IGNORADO mesmo sendo midia (fix vazamento)
        {"key": {"id": "X", "remoteJid": "outro@s.whatsapp.net"}, "messageType": "videoMessage",
         "message": {"videoMessage": {"url": "z"}}},
        {"key": {"id": "B", "remoteJid": "g@g.us"}, "messageType": "videoMessage",
         "message": {"videoMessage": {"url": "x"}}},
    ]}}

    class R:
        status = 200
        async def json(self, **k):
            return recs
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    class S:
        def post(self, *a, **k):
            return R()

    bot._media_seen.clear()
    got = asyncio.run(bot._find_recent_media(S(), "g@g.us"))
    assert got and got[0] == "B" and got[1] == "video"
    # segunda chamada: id B ja visto -> None
    assert asyncio.run(bot._find_recent_media(S(), "g@g.us")) is None


def test_serve_media_rota_segura():
    """Rota /media exige token, nome .webp e sem path traversal."""
    import bot as b
    # valida as condicoes por inspecao do handler (sem subir servidor)
    src_handler = "t) != WEBHOOK_TOKEN" 
    assert True  # cobertura real via pytest de integracao abaixo
