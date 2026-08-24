"""Regressao T13: rotacao de backups + recovery de state corrompido."""
import json

import bot


def test_rotacao_mantem_7_baks(tmp_path):
    sf = tmp_path / "state.json"
    monkeypatched = sf
    old_file = bot.STATE_FILE
    bot.STATE_FILE = monkeypatched
    try:
        for i in range(9):  # simula 9 trocas de dia
            bot._rotate_state_backup()
            sf.write_text(json.dumps({"dia": i}))
        baks = list(tmp_path.glob("state.json.bak-*"))
        assert len(baks) == 7
    finally:
        bot.STATE_FILE = old_file


def test_corrompido_recupera_do_bak(tmp_path, monkeypatch):
    sf = tmp_path / "state.json"
    bak1 = tmp_path / "state.json.bak-1"
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    bak1.write_text(json.dumps({"date": today, "sent_today": 7, "blacklist": ["z@s.whatsapp.net"],
                                "contacts": {}, "history": {}, "reminders": []}))
    sf.write_text("{corrompido!!!" )
    monkeypatch.setattr(bot, "STATE_FILE", sf)
    bot._state.clear()
    bot._state.update({"date": ""})
    bot._load_state()
    assert bot._state.get("sent_today") == 7
    assert bot._state.get("blacklist") == ["z@s.whatsapp.net"]


def test_sem_bak_comeca_limpo(tmp_path, monkeypatch):
    sf = tmp_path / "state.json"
    sf.write_text("lixo{{{")
    monkeypatch.setattr(bot, "STATE_FILE", sf)
    bot._state.clear()
    bot._state.update({"date": ""})
    bot._load_state()
    assert bot._state["sent_today"] == 0
