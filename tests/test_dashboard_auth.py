"""Regressao T8: painel fail-closed sem token."""
import bot


class FakeReq:
    def __init__(self, headers=None, query=None):
        self.headers = headers or {}
        self.query = query or {}


def test_vazio_nega_sempre(monkeypatch):
    monkeypatch.setattr(bot, "DASHBOARD_TOKEN", "")
    assert bot._check_dashboard_auth(FakeReq()) is False
    assert bot._check_dashboard_auth(FakeReq(query={"token": ""})) is False


def test_bearer_valido(monkeypatch):
    monkeypatch.setattr(bot, "DASHBOARD_TOKEN", "tok")
    assert bot._check_dashboard_auth(FakeReq(headers={"Authorization": "Bearer tok"})) is True


def test_query_valida(monkeypatch):
    monkeypatch.setattr(bot, "DASHBOARD_TOKEN", "tok")
    assert bot._check_dashboard_auth(FakeReq(query={"token": "tok"})) is True


def test_errado_nega(monkeypatch):
    monkeypatch.setattr(bot, "DASHBOARD_TOKEN", "tok")
    assert bot._check_dashboard_auth(FakeReq(query={"token": "nope"})) is False
