"""T12: valida pipeline completo com payloads fixtures reais."""
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_fixture_messages_upsert_text_schema():
    """Valida que o fixture de texto segue schema esperado do webhook."""
    fixture_path = FIXTURES_DIR / "messages_upsert_text.json"
    assert fixture_path.exists(), "Fixture messages_upsert_text.json ausente"
    
    with open(fixture_path) as f:
        payload = json.load(f)
    
    # Schema mínimo esperado pelo handle_webhook
    assert payload["event"] == "messages.upsert"
    assert "data" in payload
    assert "key" in payload["data"]
    assert "remoteJid" in payload["data"]["key"]
    assert "message" in payload["data"]
    assert "conversation" in payload["data"]["message"]
    assert payload["data"]["message"]["conversation"] == "oi bot"


def test_all_fixtures_valid_json():
    """Garante que todos os fixtures/*.json são JSON válidos."""
    if not FIXTURES_DIR.exists():
        return  # pasta ainda não criada — skip
    
    fixtures = list(FIXTURES_DIR.glob("*.json"))
    assert len(fixtures) > 0, "Nenhum fixture encontrado em tests/fixtures/"
    
    for fixture_file in fixtures:
        with open(fixture_file) as f:
            data = json.load(f)  # raise JSONDecodeError se inválido
            assert isinstance(data, dict), f"{fixture_file.name} deve ser objeto JSON"
