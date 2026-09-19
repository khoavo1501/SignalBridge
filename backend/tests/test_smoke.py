from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_healthz():
    client = TestClient(app)
    resp = client.get("/api/v1/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_settings_defaults():
    get_settings.cache_clear()
    s = get_settings()
    assert s.mqtt_topic_filter == "devices/+/+"
    assert s.stale_threshold_s == 10
    assert s.auth_enabled is False
