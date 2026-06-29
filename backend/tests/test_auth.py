from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from app.infrastructure import auth


def _client_with_token_dependency():
    app = FastAPI()

    @app.get("/test")
    def test_route(valid: bool = Depends(auth.verify_token)):
        return {"status": "ok"}

    return TestClient(app)


def test_verify_token_no_token_env(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    monkeypatch.delenv("APP_ENV", raising=False)

    response = _client_with_token_dependency().get("/test")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_token_requires_token_in_production(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    monkeypatch.setenv("APP_ENV", "production")

    response = _client_with_token_dependency().get("/test")
    assert response.status_code == 401


def test_verify_token_with_token_env(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "secure-secret-token")
    monkeypatch.delenv("APP_ENV", raising=False)

    client = _client_with_token_dependency()

    response = client.get("/test")
    assert response.status_code == 401

    response = client.get("/test", headers={"Authorization": "wrong-token"})
    assert response.status_code == 401

    response = client.get("/test", headers={"Authorization": "Bearer secure-secret-token"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    response = client.get("/test?token=secure-secret-token")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_ws_token(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "ws-secret-token")
    monkeypatch.delenv("APP_ENV", raising=False)

    assert auth.verify_ws_token({"token": "ws-secret-token"}) is True
    assert auth.verify_ws_token({"token": "wrong-token"}) is False
    assert auth.verify_ws_token({}) is False

    monkeypatch.setattr(auth, "API_TOKEN", "")
    assert auth.verify_ws_token({"token": "whatever"}) is True
    assert auth.verify_ws_token({}) is True


def test_verify_ws_token_requires_token_in_production(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    monkeypatch.setenv("APP_ENV", "production")

    assert auth.verify_ws_token({"token": "whatever"}) is False
    assert auth.verify_ws_token({}) is False


def test_game_auth_secret_required_in_production(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("GAME_AUTH_SECRET", raising=False)
    monkeypatch.delenv("API_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="GAME_AUTH_SECRET or API_TOKEN"):
        auth.create_game_auth_token("player123")
