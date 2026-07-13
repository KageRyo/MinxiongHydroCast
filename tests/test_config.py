from floodcastminxiong.config import get_settings


def test_settings_load_cwa_rest_api_and_key(monkeypatch):
    monkeypatch.setenv("CWA_API_KEY", "test-key")
    monkeypatch.setenv("CWA_REST_API_URL", "https://example.test/cwa")

    settings = get_settings()

    assert settings.cwa_api_key == "test-key"
    assert settings.cwa_rest_api_url == "https://example.test/cwa"


def test_settings_load_wra_api_endpoints_and_key(monkeypatch):
    monkeypatch.setenv("WRA_API_KEY", "test-key")
    monkeypatch.setenv("WRA_API_URL", "https://example.test/wra")
    monkeypatch.setenv("WRA_OPEN_DATA_API_URL", "https://example.test/open-data")

    settings = get_settings()

    assert settings.wra_api_key == "test-key"
    assert settings.wra_api_url == "https://example.test/wra"
    assert settings.wra_open_data_api_url == "https://example.test/open-data"


def test_settings_load_flood_snapshot_freshness(monkeypatch):
    monkeypatch.setenv("FLOODCASTMINXIONG_FLOOD_MAX_AGE_MINUTES", "120")

    assert get_settings().operations_flood_max_age_minutes == 120
