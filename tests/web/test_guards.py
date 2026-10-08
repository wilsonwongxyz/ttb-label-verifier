from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def client(**settings: object) -> TestClient:
    return TestClient(create_app(Settings(provider="fixture", **settings)))  # type: ignore[arg-type]


def test_no_code_means_open() -> None:
    assert client().get("/").status_code == 200


def test_access_code_gates_pages_but_not_health() -> None:
    c = client(access_code=SecretStr("open-sesame"))
    gate = c.get("/batch", follow_redirects=False)
    assert gate.status_code == 303
    assert gate.headers["location"] == "/access?next=/batch"
    assert c.get("/healthz").status_code == 200
    assert c.get("/static/styles.css").status_code == 200


def test_wrong_code_is_refused() -> None:
    c = client(access_code=SecretStr("open-sesame"))
    response = c.post("/access", data={"code": "nope", "next": "/"})
    assert response.status_code == 401
    assert "isn&#39;t right" in response.text


def test_right_code_sets_a_cookie_and_returns_you() -> None:
    c = client(access_code=SecretStr("open-sesame"))
    response = c.post(
        "/access", data={"code": " open-sesame ", "next": "/batch"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/batch"
    assert "open-sesame" not in response.headers["set-cookie"]
    assert c.get("/batch").status_code == 200


def test_next_cannot_redirect_off_site() -> None:
    c = client(access_code=SecretStr("open-sesame"))
    for target in ("https://evil.example", "//evil.example"):
        response = c.post(
            "/access", data={"code": "open-sesame", "next": target}, follow_redirects=False
        )
        assert response.headers["location"] == "/"


def test_oversized_request_is_rejected_before_reading() -> None:
    c = client(batch_max_bytes=1024)
    response = c.post("/batch", content=b"x" * (6 * 1024 * 1024 + 10))
    assert response.status_code == 413
