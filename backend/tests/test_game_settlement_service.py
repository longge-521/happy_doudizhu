from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.game.settlement_service import (
    GameSettlementService,
    SettlementConflictError,
)
from app.domain.game.room import GameRoom, Player
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.database.models import (
    Base,
    GameRecordORM,
    GameSettlementORM,
    PlayerProfileORM,
)


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
        repo.get_or_create_profile("p1", "玩家一")
        repo.get_or_create_profile("p2", "玩家二")

    return Session, session_scope


def make_room(room_id: str) -> GameRoom:
    room = GameRoom.create(
        room_id,
        [
            Player(id="p1", nickname="玩家一"),
            Player(id="p2", nickname="玩家二"),
            Player(id="ai_bot_1", nickname="机器人", is_ai=True),
        ],
    )
    room.landlord = "p1"
    room.multiplier = 2
    return room


def make_result():
    return {
        "scores": {"p1": 40, "p2": -40, "ai_bot_1": 0},
        "multiplier": 2,
    }


def test_settlement_is_idempotent(settlement_context):
    Session, session_scope = settlement_context
    service = GameSettlementService(session_scope=session_scope)
    room = make_room("room_once")
    result = make_result()

    first = service.settle(room, result)
    second = service.settle(room, result)

    assert first == "completed"
    assert second == "already_completed"
    with Session() as db:
        settlement = db.query(GameSettlementORM).filter_by(room_id=room.room_id).one()
        player_one = db.query(PlayerProfileORM).filter_by(player_id="p1").one()
        player_two = db.query(PlayerProfileORM).filter_by(player_id="p2").one()
        assert settlement.status == "completed"
        assert settlement.attempts == 1
        assert db.query(GameRecordORM).filter_by(room_id=room.room_id).count() == 2
        assert player_one.beans == 10040
        assert player_one.total_games == 1
        assert player_two.beans == 9960
        assert player_two.total_games == 1


def test_settlement_rejects_conflicting_result(settlement_context):
    Session, session_scope = settlement_context
    service = GameSettlementService(session_scope=session_scope)
    room = make_room("room_conflict")
    service.settle(room, make_result())

    with pytest.raises(SettlementConflictError):
        service.settle(
            room,
            {
                "scores": {"p1": 80, "p2": -80, "ai_bot_1": 0},
                "multiplier": 4,
            },
        )

    with Session() as db:
        settlement = db.query(GameSettlementORM).filter_by(room_id=room.room_id).one()
        assert settlement.status == "completed"
        assert settlement.attempts == 1


def test_settlement_rolls_back_player_changes_on_failure(
    monkeypatch, settlement_context
):
    Session, session_scope = settlement_context
    service = GameSettlementService(session_scope=session_scope)
    room = make_room("room_failure")

    def fail_rank_update(*args, **kwargs):
        raise RuntimeError("db failure")

    monkeypatch.setattr(
        SQLGameRepository,
        "update_rank_stats",
        fail_rank_update,
    )

    with pytest.raises(RuntimeError, match="db failure"):
        service.settle(room, make_result())

    with Session() as db:
        settlement = db.query(GameSettlementORM).filter_by(room_id=room.room_id).one()
        player_one = db.query(PlayerProfileORM).filter_by(player_id="p1").one()
        player_two = db.query(PlayerProfileORM).filter_by(player_id="p2").one()
        assert settlement.status == "failed"
        assert settlement.attempts == 1
        assert "db failure" in settlement.last_error
        assert len(settlement.last_error) <= 500
        assert db.query(GameRecordORM).filter_by(room_id=room.room_id).count() == 0
        assert player_one.beans == 10000
        assert player_one.total_games == 0
        assert player_two.beans == 10000
        assert player_two.total_games == 0
