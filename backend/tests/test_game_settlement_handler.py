from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.game.room import GameRoom, Player
from app.interfaces.websocket.game_handler import GameWebSocketHandler
from app.interfaces.websocket.game_routes import GameWSConnectionManager


def make_room() -> GameRoom:
    room = GameRoom.create(
        "room_handler_settlement",
        [
            Player(id="p1", nickname="玩家一"),
            Player(id="p2", nickname="玩家二"),
            Player(id="ai_bot_1", nickname="机器人", is_ai=True),
        ],
    )
    room.landlord = "p1"
    room.multiplier = 2
    return room


def make_handler(settlement_service):
    game_service = MagicMock()
    game_service.cleanup_room = AsyncMock()
    game_service._repo = MagicMock()
    game_service._repo.save_room = AsyncMock()
    handler = GameWebSocketHandler(
        MagicMock(),
        "p1",
        GameWSConnectionManager(),
        game_service,
        settlement_service=settlement_service,
    )
    return handler, game_service


@pytest.mark.asyncio
async def test_game_over_cleans_room_after_successful_settlement():
    settlement_service = MagicMock()
    settlement_service.settle.return_value = "completed"
    handler, game_service = make_handler(settlement_service)
    room = make_room()
    result = {"scores": {"p1": 40, "p2": -40}, "multiplier": 2}

    completed = await handler._on_game_over(room, result)

    assert completed is True
    settlement_service.settle.assert_called_once_with(room, result)
    game_service.cleanup_room.assert_awaited_once_with(
        room.room_id,
        ["p1", "p2", "ai_bot_1"],
    )
    game_service._repo.save_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_game_over_keeps_room_when_settlement_fails():
    settlement_service = MagicMock()
    settlement_service.settle.side_effect = RuntimeError("mysql unavailable")
    handler, game_service = make_handler(settlement_service)
    room = make_room()
    result = {"scores": {"p1": 40, "p2": -40}, "multiplier": 2}

    completed = await handler._on_game_over(room, result)

    assert completed is False
    game_service.cleanup_room.assert_not_awaited()
    game_service._repo.save_room.assert_awaited_once_with(room)
