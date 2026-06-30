from app.infrastructure.database import session
from app.infrastructure.database import schema_migrations


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


def test_init_db_delegates_schema_migrations(monkeypatch):
    calls = []
    fake_engine = object()

    monkeypatch.setattr(session, "engine", fake_engine)
    monkeypatch.setattr(
        session.Base.metadata,
        "create_all",
        lambda bind: calls.append(("create_all", bind)),
    )
    monkeypatch.setattr(
        session,
        "run_schema_migrations",
        lambda bind: calls.append(("migrate", bind)),
        raising=False,
    )

    session.init_db()

    assert calls == [("create_all", fake_engine), ("migrate", fake_engine)]


def test_run_schema_migrations_adds_known_missing_columns(monkeypatch):
    executed_sql = []

    class FakeConnection:
        def execute(self, statement):
            executed_sql.append(str(statement))

    class FakeBegin:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    class FakeInspector:
        def get_columns(self, table_name):
            if table_name == "audit_log":
                return [{"name": "id"}]
            if table_name == "player_profile":
                return [{"name": "player_id"}]
            return []

    monkeypatch.setattr(schema_migrations, "inspect", lambda bind: FakeInspector())

    schema_migrations.run_schema_migrations(FakeEngine())

    assert any("ALTER TABLE audit_log ADD COLUMN request_params" in sql for sql in executed_sql)
    assert any("ALTER TABLE audit_log ADD COLUMN execution_time" in sql for sql in executed_sql)
    assert any("ALTER TABLE audit_log ADD COLUMN method" in sql for sql in executed_sql)
    assert any("ALTER TABLE player_profile ADD COLUMN avatar_url" in sql for sql in executed_sql)
    assert any("ALTER TABLE player_profile ADD COLUMN rank_id" in sql for sql in executed_sql)
    assert any("ALTER TABLE player_profile ADD COLUMN sub_rank" in sql for sql in executed_sql)
    assert any("ALTER TABLE player_profile ADD COLUMN stars" in sql for sql in executed_sql)
