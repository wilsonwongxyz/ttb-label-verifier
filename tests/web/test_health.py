from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_healthz() -> None:
    response = TestClient(create_app(Settings(provider="fixture"))).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
