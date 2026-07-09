# backend/tests/test_game_websocket.py
import json
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from main import app
from app.infrastructure import auth
from app.infrastructure.config import settings
from app.domain.game.room import GameRoom, Player, GamePhase
from app.interfaces.websocket.game_routes import GameWSConnectionManager
from app.interfaces.websocket.game_handler import GameWebSocketHandler


@pytest.fixture
def mock_game_service():
    service = AsyncMock()
    service.get_room_state = AsyncMock(return_value=None)
    service.join_match = AsyncMock(return_value={"status": "waiting", "queue_length": 1})
    service.cancel_match = AsyncMock(return_value={"status": "cancelled"})
    service.handle_call = AsyncMock()
    service.handle_skip_call = AsyncMock()
    service.handle_play = AsyncMock()
    service.handle_pass = AsyncMock()
    service.handle_ai_turn = AsyncMock()
    service.handle_auto_play_turn = AsyncMock()
    service.get_ai_play_hints = AsyncMock(return_value={"candidates": [[0, 1]], "source": "douzero"})
    service.set_auto_play = AsyncMock()
    return service


@pytest.fixture(autouse=True)
def setup_app_state(monkeypatch, mock_game_service):
    # 使用 monkeypatch 模拟 app.state，测试结束后会自动还原
    from app.infrastructure.game.memory_adapters import MemoryPresenceService, MemoryMessageBus
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(app.state, "game_service", mock_game_service, raising=False)
    monkeypatch.setattr(app.state, "game_ws_manager", GameWSConnectionManager(), raising=False)
    monkeypatch.setattr(app.state, "presence_service", MemoryPresenceService(), raising=False)
    monkeypatch.setattr(app.state, "game_message_bus", MemoryMessageBus(), raising=False)


def test_game_websocket_unauthorized(monkeypatch):
    # 设置 API_TOKEN 并测试未授权连接
    monkeypatch.setattr(auth, "API_TOKEN", "secure-token")
    client = TestClient(app)
    from starlette.websockets import WebSocketDisconnect
    with client.websocket_connect("/ws/game/p1?token=wrong_token") as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()
        assert exc_info.value.code == 1008


def test_game_websocket_rejects_missing_or_mismatched_game_token(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    client = TestClient(app)
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws/game/player1") as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()
        assert exc_info.value.code == 1008

    other_token = auth.create_game_auth_token("other-player")
    with client.websocket_connect(f"/ws/game/player1?auth_token={other_token}") as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()
        assert exc_info.value.code == 1008


def test_game_websocket_join_and_cancel_match(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")

    client = TestClient(app)
    with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
        # 发送 join_match
        websocket.send_json({"action": "join_match", "nickname": "Player One"})
        resp = websocket.receive_json()
        assert resp["event"] == "match_waiting"
        assert resp["count"] == 1
        mock_game_service.join_match.assert_called_once_with("player1", "Player One", auto_ai=False, base_score=10, play_mode="classic")

        # 发送 cancel_match
        import time; time.sleep(0.12)
        websocket.send_json({"action": "cancel_match"})
        resp = websocket.receive_json()
        assert resp["event"] == "match_cancelled"
        mock_game_service.cancel_match.assert_called_once_with("player1")


def test_game_websocket_actions(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")

    # 模拟房间及事件广播
    players = [
        Player(id="player1", nickname="P1", is_ai=False, is_online=True),
        Player(id="p2", nickname="P2", is_ai=True, is_online=True),
        Player(id="p3", nickname="P3", is_ai=True, is_online=True),
    ]
    room = GameRoom.create("room123", players)
    room.phase = GamePhase.CALLING

    client = TestClient(app)
    with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
        # 1. 测试叫分
        mock_game_service.handle_call.return_value = {"room": room}
        import time; time.sleep(0.12)
        websocket.send_json({"action": "call_landlord", "score": 3})
        resp = websocket.receive_json()
        assert resp["event"] == "call_made"
        assert resp["player"] == "player1"
        assert resp["score"] == 3
        mock_game_service.handle_call.assert_called_once_with("player1", 3)

        # 2. 测试不叫/不抢
        mock_game_service.handle_skip_call.return_value = {"room": room}
        time.sleep(0.12)
        websocket.send_json({"action": "skip_call"})
        resp = websocket.receive_json()
        assert resp["event"] == "call_skipped"
        assert resp["player"] == "player1"
        mock_game_service.handle_skip_call.assert_called_once_with("player1")

        # 3. 测试出牌
        room.phase = GamePhase.PLAYING
        mock_game_service.handle_play.return_value = {
            "room": room,
            "cards_played": [3, 4],
            "card_type": "pair",
            "remaining": 15,
        }
        time.sleep(0.12)
        websocket.send_json({"action": "play_cards", "cards": [3, 4]})
        resp = websocket.receive_json()
        assert resp["event"] == "cards_played"
        assert resp["player"] == "player1"
        assert resp["cards"] == [3, 4]
        mock_game_service.handle_play.assert_called_once_with("player1", [3, 4])

        # 4. 测试过牌
        mock_game_service.handle_pass.return_value = {"room": room, "new_round": False}
        time.sleep(0.12)
        websocket.send_json({"action": "pass_turn"})
        resp = websocket.receive_json()
        assert resp["event"] == "turn_passed"
        assert resp["player"] == "player1"
        mock_game_service.handle_pass.assert_called_once_with("player1")


def test_game_websocket_join_match_insufficient_beans(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")
    
    # 模拟 Profile 欢乐豆仅 500
    mock_profile = MagicMock()
    mock_profile.beans = 500
    
    client = TestClient(app)
    with patch("app.infrastructure.database.game_repository.SQLGameRepository") as mock_repo_class:
        mock_repo = MagicMock()
        mock_repo.get_or_create_profile.return_value = mock_profile
        mock_repo_class.return_value = mock_repo
        
        with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
            # 申请加入底分为 80 的初级场（需要最低 3000）
            websocket.send_json({"action": "join_match", "nickname": "Player One", "base_score": 80})
            resp = websocket.receive_json()
            assert resp["event"] == "error"
            assert "欢乐豆不足" in resp["msg"]
            mock_game_service.join_match.assert_not_called()


def test_game_websocket_get_ai_hints(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")

    client = TestClient(app)
    with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
        websocket.send_json({"action": "get_ai_hints"})
        resp = websocket.receive_json()

    assert resp["event"] == "ai_hints"
    assert resp["candidates"] == [[0, 1]]
    assert resp["source"] == "douzero"
    mock_game_service.get_ai_play_hints.assert_called_once_with("player1")


def test_game_websocket_set_auto_play(monkeypatch, mock_game_service):
    monkeypatch.setattr(auth, "API_TOKEN", "")
    game_token = auth.create_game_auth_token("player1")
    room = GameRoom.create("room_auto_ws", [Player(id="player1", nickname="P1")])
    mock_game_service.set_auto_play.return_value = {"room": room, "player": "player1", "enabled": True}

    client = TestClient(app)
    with client.websocket_connect(f"/ws/game/player1?auth_token={game_token}") as websocket:
        websocket.send_json({"action": "set_auto_play", "enabled": True})
        resp = websocket.receive_json()

    assert resp["event"] == "auto_play_changed"
    assert resp["player"] == "player1"
    assert resp["enabled"] is True
    mock_game_service.set_auto_play.assert_called_once_with("player1", True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_action"),
    [
        ({"action": "choose_double", "choice": "double"}, "choose_double"),
        ({"action": "landlord_show", "show": False}, "landlord_show"),
        ({"action": "show_cards", "multiplier": 2}, "show_cards"),
        ({"action": "set_auto_play", "enabled": True}, "set_auto_play"),
    ],
)
async def test_distributed_room_writes_are_forwarded_to_shard(
    monkeypatch, mock_game_service, message, expected_action
):
    monkeypatch.setattr(settings, "DISTRIBUTED_MODE", True)
    room = GameRoom.create(
        "room-distributed-ws",
        [
            Player(id="player1", nickname="P1"),
            Player(id="ai-1", nickname="AI1", is_ai=True),
            Player(id="ai-2", nickname="AI2", is_ai=True),
        ],
    )
    mock_game_service._get_player_room = AsyncMock(return_value=room)
    bus = SimpleNamespace(publish_command=AsyncMock())
    websocket = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(game_message_bus=bus)))
    handler = GameWebSocketHandler(
        websocket,
        "player1",
        GameWSConnectionManager(),
        mock_game_service,
        connection_epoch=3,
    )

    await handler._handle_message(json.dumps(message))

    bus.publish_command.assert_awaited_once()
    command = bus.publish_command.await_args.args[1]
    assert command.action == expected_action


def test_settling_room_can_rebuild_game_over_event_after_reconnect():
    room = GameRoom.create(
        "room-settling-reconnect",
        [
            Player(id="landlord", nickname="地主"),
            Player(id="farmer-1", nickname="农民1"),
            Player(id="farmer-2", nickname="农民2"),
        ],
        base_score=20,
    )
    room.landlord = "landlord"
    room.multiplier = 2
    room.phase = GamePhase.SETTLING
    room.hands = {
        "landlord": [1],
        "farmer-1": [],
        "farmer-2": [2],
    }

    event = GameWebSocketHandler._build_settlement_event(room)

    assert event["event"] == "game_over"
    assert event["winner"] == "farmer-1"
    assert event["winner_side"] == "farmer"
    assert event["scores"] == {
        "landlord": -80,
        "farmer-1": 40,
        "farmer-2": 40,
    }
