"""Regressao T4: deps declaradas + guard de figurinha de video sem ffmpeg."""
import asyncio
from pathlib import Path

import bot


def test_requirements_declara_pillow_e_pin_aiohttp():
    txt = Path(bot.__file__).parent.joinpath("requirements.txt").read_text()
    assert "Pillow>=10" in txt
    assert "aiohttp>=3.9,<4" in txt


def test_video_sticker_guard_desativa_sem_ffmpeg(monkeypatch):
    monkeypatch.setattr(bot, "_video_sticker_ok", False)
    try:
        asyncio.run(bot.make_video_sticker_raw("data:video/mp4;base64,AAAA"))
        raise AssertionError("deveria ter levantado RuntimeError")
    except RuntimeError as exc:
        assert "desativadas" in str(exc)


def test_flag_default_ativa():
    assert bot._video_sticker_ok is True
