import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from main import app
from app.infrastructure import auth
from app.infrastructure.config import settings
from app.infrastructure.auth import create_game_auth_token
from app.interfaces.websocket.game_routes import GameWSConnectionManager

client = TestClient(app)


@pytest.fixture
def mock_game_service():
    service = AsyncMock()
    service.get_room_state = AsyncMock(return_value=None)
    return service


@pytest.fixture(autouse=True)
def setup_app_state(monkeypatch, mock_game_service):
    from app.infrastructure.game.memory_adapters import MemoryPresenceService, MemoryMessageBus
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(app.state, "game_service", mock_game_service, raising=False)
    monkeypatch.setattr(app.state, "game_ws_manager", GameWSConnectionManager(), raising=False)
    monkeypatch.setattr(app.state, "presence_service", MemoryPresenceService(), raising=False)
    monkeypatch.setattr(app.state, "game_message_bus", MemoryMessageBus(), raising=False)


@pytest.mark.asyncio
async def test_create_websocket_ticket_requires_auth():
    response = client.post("/api/game/auth/ticket")
    assert response.status_code == 401 or response.status_code == 403


@pytest.mark.asyncio
async def test_create_websocket_ticket_success_and_saves_to_redis():
    token = create_game_auth_token("player_ticket_123")
    
    with patch("app.infrastructure.redis_client.redis_client.set", new_callable=AsyncMock) as mock_set:
        response = client.post(
            "/api/game/auth/ticket",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "ticket" in data
        assert data["expires_in"] == 30
        
        ticket_id = data["ticket"]
        mock_set.assert_called_once()
        args, kwargs = mock_set.call_args
        assert args[0] == f"game:ws_ticket:{ticket_id}"
        assert args[1] == "player_ticket_123"
        assert kwargs.get("ex") == 30


@pytest.mark.asyncio
async def test_game_websocket_authenticates_with_valid_ticket(monkeypatch):
    # 模拟在 DISTRIBUTED_MODE 下，使用 ticket 握手连接
    monkeypatch.setattr(settings, "DISTRIBUTED_MODE", True)
    
    # 模拟 presence
    presence_service = AsyncMock()
    app.state.presence_service = presence_service
    presence_service.increment_epoch.return_value = 1
    presence_service.get_presence.return_value = None
    presence_service.set_presence.return_value = None
    
    from app.infrastructure.redis_client import redis_client
    
    with patch.object(redis_client, "get", new_callable=AsyncMock) as mock_get, \
         patch.object(redis_client, "delete", new_callable=AsyncMock) as mock_del:
        
        # 模拟票据存在，且属于当前玩家
        mock_get.return_value = b"player_ticket_123"
        
        from starlette.websockets import WebSocketDisconnect
        # 因为我们 Mock 了所有的 WS handler 运行，所以它建立完连接会走内部流程
        # 我们这里通过与 websocket_connect 握手验证它是否通过了 auth 段
        client_local = TestClient(app)
        with client_local.websocket_connect("/ws/game/player_ticket_123?ticket=ticket-abc") as websocket:
            pass
            
        mock_get.assert_called_once_with("game:ws_ticket:ticket-abc")
        mock_del.assert_called_once_with("game:ws_ticket:ticket-abc")


@pytest.mark.asyncio
async def test_game_websocket_rejects_expired_or_invalid_ticket(monkeypatch):
    monkeypatch.setattr(settings, "DISTRIBUTED_MODE", True)
    
    from app.infrastructure.redis_client import redis_client
    with patch.object(redis_client, "get", new_callable=AsyncMock) as mock_get:
        # 模拟票据过期或不存在
        mock_get.return_value = None
        
        from starlette.websockets import WebSocketDisconnect
        client_local = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client_local.websocket_connect("/ws/game/player_ticket_123?ticket=ticket-invalid") as websocket:
                websocket.receive_text()
        assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_game_websocket_rejects_mismatched_player_ticket(monkeypatch):
    monkeypatch.setattr(settings, "DISTRIBUTED_MODE", True)
    
    from app.infrastructure.redis_client import redis_client
    with patch.object(redis_client, "get", new_callable=AsyncMock) as mock_get:
        # 模拟票据属于别的人
        mock_get.return_value = b"another_player"
        
        from starlette.websockets import WebSocketDisconnect
        client_local = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client_local.websocket_connect("/ws/game/player_ticket_123?ticket=ticket-abc") as websocket:
                websocket.receive_text()
        assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_game_websocket_rejects_raw_token_in_distributed_mode(monkeypatch):
    monkeypatch.setattr(settings, "DISTRIBUTED_MODE", True)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "GAME_AUTH_SECRET", "a" * 32)
    
    # 直接使用 auth_token 连接，在分布式生产模式下应该直接被拒绝并关闭
    from starlette.websockets import WebSocketDisconnect
    client_local = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client_local.websocket_connect("/ws/game/player_ticket_123?auth_token=some_token") as websocket:
            websocket.receive_text()
    assert exc_info.value.code == 1008
