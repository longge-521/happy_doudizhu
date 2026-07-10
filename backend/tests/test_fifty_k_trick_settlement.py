from contextlib import contextmanager
import py_compile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.game.settlement_service import (
    GameSettlementService,
    SettlementConflictError,
    calculate_fifty_k_trick_changes,
)
from app.domain.game.room import GameRoom, Player
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.database.models import Base, PlayerProfileORM


@pytest.fixture
def settlement_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def session_scope():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    with session_scope() as db:
        repo = SQLGameRepository(db)
        for player_id in ("p1", "p2", "p3"):
            repo.get_or_create_profile(player_id, player_id)

    return Session, session_scope


def make_room() -> GameRoom:
    room = GameRoom.create(
        "room_trick",
        [
            Player(id="p1", nickname="p1"),
            Player(id="p2", nickname="p2"),
            Player(id="p3", nickname="p3"),
        ],
        base_score=80,
    )
    room.play_mode = "fifty_k"
    room.multiplier = 2
    return room


def make_trick(score: int = 35) -> dict:
    return {
        "trick_no": 1,
        "winner_id": "p1",
        "trick_cards": [8, 28, 40],
        "score_gained": score,
    }


def test_fifty_k_trick_settlement_migration_can_be_compiled():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c31f510b8a42_add_fifty_k_trick_settlement.py"
    )

    py_compile.compile(str(migration), doraise=True)


def test_trick_formula_uses_score_base_and_multiplier():
    changes = calculate_fifty_k_trick_changes(
        winner_id="p1",
        player_ids=["p1", "p2", "p3"],
        score=35,
        base_score=80,
        multiplier=2,
    )
    assert changes == {"p1": 5600, "p2": -2800, "p3": -2800}
    assert sum(changes.values()) == 0


def test_trick_settlement_is_idempotent_and_does_not_increment_games(settlement_context):
    Session, session_scope = settlement_context
    service = GameSettlementService(session_scope=session_scope)
    room = make_room()

    first = service.settle_fifty_k_trick(room, make_trick())
    second = service.settle_fifty_k_trick(room, make_trick())

    assert first["status"] == "completed"
    assert second["status"] == "already_completed"
    assert second["bean_changes"] == first["bean_changes"]
    assert first["bean_changes"] == {"p1": 5600, "p2": -2800, "p3": -2800}

    with Session() as db:
        profiles = {
            row.player_id: row
            for row in db.query(PlayerProfileORM).filter(
                PlayerProfileORM.player_id.in_(["p1", "p2", "p3"])
            )
        }
        assert profiles["p1"].beans == 15600
        assert profiles["p2"].beans == 7200
        assert profiles["p3"].beans == 7200
        assert all(row.total_games == 0 for row in profiles.values())
        assert all(row.wins == 0 for row in profiles.values())


def test_trick_settlement_rejects_conflicting_replay(settlement_context):
    _, session_scope = settlement_context
    service = GameSettlementService(session_scope=session_scope)
    room = make_room()
    service.settle_fifty_k_trick(room, make_trick())

    with pytest.raises(SettlementConflictError):
        service.settle_fifty_k_trick(room, make_trick(score=30))
