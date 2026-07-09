import pytest
import time
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.infrastructure.auth import create_game_auth_token
from app.infrastructure.config import settings
from app.interfaces.websocket.game_routes import GameWSConnectionManager
from app.application.game.schemas import GameEventSchema

@pytest.mark.asyncio
async def test_game_kickout_logic_mock(monkeypatch):
    """通过 Mock 核心分布式组件，验证重复登录 Kickout 路由逻辑分支的正确性"""
    # 隔离环境
    monkeypatch.setattr(settings, "APP_ENV", "development")
    monkeypatch.setattr(settings, "DISTRIBUTED_MODE", True)
    
    # Mock Presence Service
    mock_presence = MagicMock()
    mock_presence.increment_epoch = AsyncMock(side_effect=[1, 2])
    mock_presence.get_presence = AsyncMock(side_effect=[
        None,
        {"player_id": "test_player_mock_kick", "instance_id": "inst-other", "connection_epoch": 1}
    ])
    mock_presence.set_presence = AsyncMock()
    mock_presence.remove_presence = AsyncMock()
    
    # Mock Message Bus
    mock_bus = MagicMock()
    mock_bus.publish_event = AsyncMock()
    
    # Mock Game Service
    mock_game_service = AsyncMock()
    mock_game_service._get_player_room = AsyncMock(return_value=None)
    mock_game_service.get_room_state = AsyncMock(return_value={})
    
    # 使用 monkeypatch 隔离对全局 app.state 的修改，防止污染其他测试文件
    from main import app
    monkeypatch.setattr(app.state, "presence_service", mock_presence, raising=False)
    monkeypatch.setattr(app.state, "game_message_bus", mock_bus, raising=False)
    monkeypatch.setattr(app.state, "game_ws_manager", GameWSConnectionManager(), raising=False)
    monkeypatch.setattr(app.state, "game_service", mock_game_service, raising=False)
    
    client = TestClient(app)
    player_id = "test_player_mock_kick"
    token = create_game_auth_token(player_id)
    
    # 1. 模拟第一位玩家连接建立 (epoch=1, get_presence=None)
    with client.websocket_connect(f"/ws/game/{player_id}?auth_token={token}") as ws1:
        mock_presence.increment_epoch.assert_called_with(player_id)
        mock_presence.set_presence.assert_called_with(player_id, settings.INSTANCE_ID, 1)
        
        # 2. 模拟跨实例的第二个连接连进来 (epoch=2, get_presence 发现连接在 inst-other)
        with client.websocket_connect(f"/ws/game/{player_id}?auth_token={token}") as ws2:
            mock_bus.publish_event.assert_called()
            called_args = mock_bus.publish_event.call_args[0]
            assert called_args[0] == "inst-other"
            
            event_arg = called_args[1]
            assert isinstance(event_arg, GameEventSchema)
            assert event_arg.event == "kick"
            assert event_arg.target_player_id == player_id
            assert event_arg.target_connection_epoch == 1
