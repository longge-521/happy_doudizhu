from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from app.infrastructure import auth
from app.infrastructure.config import settings


def _client_with_token_dependency():
    app = FastAPI()

    @app.get("/test")
    def test_route(valid: bool = Depends(auth.verify_token)):
        return {"status": "ok"}

    return TestClient(app)


def test_verify_token_no_token_env(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "")
    monkeypatch.delenv("APP_ENV", raising=False)

    response = _client_with_token_dependency().get("/test")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_token_requires_token_in_production(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    response = _client_with_token_dependency().get("/test")
    assert response.status_code == 401


def test_verify_token_with_token_env(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "secure-secret-token")
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
    monkeypatch.setattr(settings, "API_TOKEN", "ws-secret-token")
    monkeypatch.delenv("APP_ENV", raising=False)

    assert auth.verify_ws_token({"token": "ws-secret-token"}) is True
    assert auth.verify_ws_token({"token": "wrong-token"}) is False
    assert auth.verify_ws_token({}) is False

    monkeypatch.setattr(settings, "API_TOKEN", "")
    assert auth.verify_ws_token({"token": "whatever"}) is True
    assert auth.verify_ws_token({}) is True


def test_verify_ws_token_requires_token_in_production(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    assert auth.verify_ws_token({"token": "whatever"}) is False
    assert auth.verify_ws_token({}) is False


def test_game_auth_secret_required_in_production(monkeypatch):
    monkeypatch.setattr(settings, "API_TOKEN", "")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", "")
    monkeypatch.setattr(settings, "APP_ENV", "production")

    with pytest.raises(RuntimeError, match="GAME_AUTH_SECRET"):
        auth.create_game_auth_token("player123")


def test_validate_production_settings_rejects_missing_game_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", None)

    with pytest.raises(RuntimeError, match="GAME_AUTH_SECRET"):
        settings.validate_production_settings()


def test_validate_production_settings_accepts_explicit_game_secret(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", "a" * 32)

    settings.validate_production_settings()


def test_development_uses_local_game_secret_fallback(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", None)
    monkeypatch.setattr(settings, "API_TOKEN", None)

    token = auth.create_game_auth_token("player123")

    assert auth.verify_game_auth_token(token) == "player123"
