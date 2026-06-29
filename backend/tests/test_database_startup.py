from app.infrastructure.database import session


def test_auto_init_db_disabled_in_production_by_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("AUTO_INIT_DB", raising=False)

    assert session.should_auto_init_db() is False


def test_auto_init_db_enabled_outside_production_by_default(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("AUTO_INIT_DB", raising=False)

    assert session.should_auto_init_db() is True


def test_auto_init_db_can_be_explicitly_overridden(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTO_INIT_DB", "true")
    assert session.should_auto_init_db() is True

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTO_INIT_DB", "false")
    assert session.should_auto_init_db() is False
