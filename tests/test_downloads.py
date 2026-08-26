import time

import bot


def test_detect_platform_varios_links():
    casos = [
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://vm.tiktok.com/ZMabc123/", "tiktok"),
        ("https://vt.tiktok.com/ZSxyz/", "tiktok"),
        ("https://www.instagram.com/reel/Cxyz123/", "instagram"),
        ("https://instagram.com/p/Dabc/", "instagram"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        ("https://www.youtube.com/shorts/abc123", "youtube"),
        ("https://www.youtube.com/watch?v=abc", "youtube"),
    ]
    for url, esperado in casos:
        det = bot._detect_platform(f"olha isso {url} muito bom")
        assert det and det[0] == esperado, f"{url} -> {det}"


def test_detect_platform_rejeita_nao_suportados():
    assert bot._detect_platform("https://noticias.com.br/materia") is None
    assert bot._detect_platform("bom dia galera") is None
    assert bot._detect_platform("") is None


def test_dl_state_expira():
    bot._DL_STATE.clear()
    bot._DL_STATE["chat1"] = {"plataforma": "tiktok", "url": "x", "ts": time.time() - 400}
    bot._dl_state_prune()
    assert "chat1" not in bot._DL_STATE


def test_dl_menu_formato():
    msg = bot._dl_menu_send("tiktok")
    assert "TikTok" in msg and "1" in msg and "2" in msg


def test_comandos_dl_registrados():
    for cmd in ("dl", "dlvideo", "dlaudio"):
        assert bot.COMMANDS.get(cmd), f"comando {cmd} ausente no COMMANDS"
