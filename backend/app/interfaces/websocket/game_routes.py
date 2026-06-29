# backend/app/interfaces/websocket/game_routes.py
"""斗地主游戏 WebSocket 端点"""
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, Depends

logger = logging.getLogger("hmp_ws_service")
router = APIRouter(tags=["Game WebSocket"])


class GameWSConnectionManager:
    """管理游戏 WebSocket 连接。按 player_id 维护连接映射。"""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.connections[player_id] = websocket
        logger.info(f"游戏WS: 玩家 '{player_id}' 已连接. 在线: {len(self.connections)}")

    def disconnect(self, player_id: str):
        self.connections.pop(player_id, None)
        logger.info(f"游戏WS: 玩家 '{player_id}' 已断开. 在线: {len(self.connections)}")

    async def send_to_player(self, player_id: str, data: dict):
        import json
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception as e:
                logger.error(f"游戏WS: 发送给 '{player_id}' 失败: {e}")
                self.disconnect(player_id)

    async def broadcast_to_room(self, player_ids: List[str], data: dict):
        for pid in player_ids:
            await self.send_to_player(pid, data)


def get_game_ws_manager(websocket: WebSocket) -> GameWSConnectionManager:
    return websocket.app.state.game_ws_manager


def get_game_service(websocket: WebSocket):
    return websocket.app.state.game_service


@router.websocket("/ws/game/{player_id}")
async def game_websocket_endpoint(
    websocket: WebSocket,
    player_id: str,
    manager: GameWSConnectionManager = Depends(get_game_ws_manager),
    game_service = Depends(get_game_service),
):
    # Token 校验
    from app.infrastructure.auth import verify_game_auth_token, verify_ws_token
    if not verify_ws_token(websocket.query_params):
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized")
        return
    game_auth_token = websocket.query_params.get("auth_token")
    if not game_auth_token:
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized")
        return
    try:
        token_player_id = verify_game_auth_token(game_auth_token)
    except Exception:
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized")
        return
    if token_player_id != player_id:
        await websocket.accept()
        await websocket.close(code=1008, reason="Forbidden")
        return

    from app.interfaces.websocket.game_handler import GameWebSocketHandler
    handler = GameWebSocketHandler(websocket, player_id, manager, game_service)
    await handler.run()
