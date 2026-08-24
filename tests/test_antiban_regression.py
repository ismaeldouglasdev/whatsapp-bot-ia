"""GUARDA DE REGRESSAO: caps anti-ban congelados.

Qualquer alteracao nestes defaults QUEBRA este teste deliberadamente.
Mudanca legitima de caps exige revisao humana explicita (anti-ban).
"""
import inspect

import bot


def test_caps_congelados():
    src = inspect.getsource(bot)
    assert 'DAILY_SEND_CAP = int(os.environ.get("DAILY_SEND_CAP", "25" if WARMUP else "150"))' in src
    assert 'HOURLY_SEND_CAP = int(os.environ.get("HOURLY_SEND_CAP", "6" if WARMUP else "25"))' in src
    assert 'PER_CHAT_HOURLY_CAP = int(os.environ.get("PER_CHAT_HOURLY_CAP", "4" if WARMUP else "8"))' in src
    assert 'NEW_CONTACT_DAILY_CAP = int(os.environ.get("NEW_CONTACT_DAILY_CAP", "3" if WARMUP else "5"))' in src
    assert 'MIN_REPLY_GAP_S = int(os.environ.get("MIN_REPLY_GAP_S", "20"))' in src


def test_rate_block_reason_ordem_de_bloqueio():
    """A ordem diaria->horario-global->por-chat->novo-contato->gap deve permanecer."""
    import re as _re
    fn_src = _re.search(r"def _rate_block_reason.*?(?=\ndef |\nclass )", inspect.getsource(bot), _re.DOTALL)
    assert fn_src, "_rate_block_reason desapareceu"
    body = fn_src.group(0)
    pos = [body.index(k) for k in ("teto diário", "teto horário global", "teto horário do chat", "contato novo", "gap mínimo")]
    assert pos == sorted(pos), "ordem de bloqueio dos guardrails mudou"
