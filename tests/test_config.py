from floodcastminxiong.config import get_settings


def test_settings_load_cwa_rest_api_and_key(monkeypatch):
    monkeypatch.setenv("CWA_API_KEY", "test-key")
    monkeypatch.setenv("CWA_REST_API_URL", "https://example.test/cwa")

    settings = get_settings()

    assert settings.cwa_api_key == "test-key"
    assert settings.cwa_rest_api_url == "https://example.test/cwa"
