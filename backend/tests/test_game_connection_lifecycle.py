import inspect
from unittest.mock import AsyncMock

import pytest

from app.infrastructure.game.redis_presence import RedisPresenceService
from app.interfaces.websocket import game_routes
from app.interfaces.websocket.game_routes import GameWSConnectionManager


@pytest.mark.asyncio
async def test_presence_can_be_refreshed_only_for_current_connection():
    client = AsyncMock()
    client.eval.side_effect = [1, 0]
    service = RedisPresenceService(client)

    assert hasattr(service, "refresh_presence")
    assert await service.refresh_presence("p1", "inst-1", 7) is True
    assert await service.refresh_presence("p1", "inst-1", 6) is False


@pytest.mark.asyncio
async def test_presence_heartbeat_refreshes_current_connection():
    presence = AsyncMock()
    presence.refresh_presence = AsyncMock(return_value=False)

    assert hasattr(game_routes, "_presence_heartbeat")
    await game_routes._presence_heartbeat(
        presence,
        player_id="p1",
        instance_id="inst-1",
        connection_epoch=7,
        interval_seconds=0,
    )

    presence.refresh_presence.assert_awaited_once_with("p1", "inst-1", 7)


@pytest.mark.asyncio
async def test_presence_heartbeat_retries_after_transient_storage_error():
    presence = AsyncMock()
    presence.refresh_presence = AsyncMock(
        side_effect=[RuntimeError("redis unavailable"), False],
    )

    await game_routes._presence_heartbeat(
        presence,
        player_id="p1",
        instance_id="inst-1",
        connection_epoch=7,
        interval_seconds=0,
    )

    assert presence.refresh_presence.await_count == 2


def test_stale_websocket_disconnect_does_not_remove_replacement():
    manager = GameWSConnectionManager()
    old_websocket = object()
    new_websocket = object()
    manager.connections["p1"] = new_websocket

    assert "websocket" in inspect.signature(manager.disconnect).parameters
    assert manager.disconnect("p1", old_websocket) is False
    assert manager.connections["p1"] is new_websocket
    assert manager.disconnect("p1", new_websocket) is True
    assert "p1" not in manager.connections
