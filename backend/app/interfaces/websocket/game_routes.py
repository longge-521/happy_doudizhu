# backend/app/interfaces/websocket/game_routes.py
"""斗地主游戏 WebSocket 端点"""
import asyncio
from contextlib import suppress
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, Depends

logger = logging.getLogger("happy_doudizhu")
router = APIRouter(tags=["Game WebSocket"])
PRESENCE_HEARTBEAT_SECONDS = 20


class GameWSConnectionManager:
    """管理游戏 WebSocket 连接。按 player_id 维护连接映射。"""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.active_ai_rooms = set()

    async def connect(self, websocket: WebSocket, player_id: str):
        await websocket.accept()
        self.connections[player_id] = websocket
        logger.info(f"游戏WS: 玩家 '{player_id}' 已连接. 在线: {len(self.connections)}")

    def disconnect(self, player_id: str, websocket: WebSocket = None) -> bool:
        current = self.connections.get(player_id)
        if current is None or (websocket is not None and current is not websocket):
            return False
        self.connections.pop(player_id, None)
        logger.info(f"游戏WS: 玩家 '{player_id}' 已断开. 在线: {len(self.connections)}")
        return True

    async def send_to_player(self, player_id: str, data: dict):
        import json
        ws = self.connections.get(player_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception as e:
                logger.error(f"游戏WS: 发送给 '{player_id}' 失败: {e}")
                self.disconnect(player_id, ws)

    async def broadcast_to_room(self, player_ids: List[str], data: dict):
        for pid in player_ids:
            await self.send_to_player(pid, data)


def get_game_ws_manager(websocket: WebSocket) -> GameWSConnectionManager:
    return websocket.app.state.game_ws_manager


def get_game_service(websocket: WebSocket):
    return websocket.app.state.game_service


async def _presence_heartbeat(
    presence_service,
    player_id: str,
    instance_id: str,
    connection_epoch: int,
    interval_seconds: float = PRESENCE_HEARTBEAT_SECONDS,
):
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            refreshed = await presence_service.refresh_presence(
                player_id,
                instance_id,
                connection_epoch,
            )
        except Exception:
            logger.warning(
                "游戏WS: Presence 续期暂时失败，稍后重试, player_id=%s, epoch=%s",
                player_id,
                connection_epoch,
            )
            continue
        if not refreshed:
            logger.warning(
                "游戏WS: Presence 续期停止，连接已被替换或记录丢失, player_id=%s, epoch=%s",
                player_id,
                connection_epoch,
            )
            return


@router.websocket("/ws/game/{player_id}")
async def game_websocket_endpoint(
    websocket: WebSocket,
    player_id: str,
    manager: GameWSConnectionManager = Depends(get_game_ws_manager),
    game_service = Depends(get_game_service),
):
    # Token 与 Ticket 校验
    from app.infrastructure.config import settings
    from app.infrastructure.auth import verify_game_auth_token, verify_ws_token
    if not verify_ws_token(websocket.query_params):
        logger.warning("游戏WS拒绝连接: 通用 API token 无效, player_id=%s", player_id)
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized")
        return

    ticket_id = websocket.query_params.get("ticket")
    if ticket_id:
        # 使用一次性票据验证
        from app.infrastructure.redis_client import redis_client
        redis_key = f"game:ws_ticket:{ticket_id}"
        ticket_player_id = await redis_client.get(redis_key)
        if ticket_player_id and isinstance(ticket_player_id, bytes):
            ticket_player_id = ticket_player_id.decode("utf-8")
            
        if not ticket_player_id:
            logger.warning("游戏WS拒绝连接: 票据不存在或已过期, player_id=%s, ticket=%s", player_id, ticket_id)
            await websocket.accept()
            await websocket.close(code=1008, reason="Unauthorized")
            return
            
        if ticket_player_id != player_id:
            logger.warning("游戏WS拒绝连接: 票据绑定的玩家 ID %s 不匹配路径 %s", ticket_player_id, player_id)
            await websocket.accept()
            await websocket.close(code=1008, reason="Forbidden")
            return
            
        # 一次性消费：立刻物理删除票据，防范重放建立连接
        await redis_client.delete(redis_key)
        logger.info("游戏WS: 玩家 '%s' 通过一次性票据验证成功建立连接", player_id)
    else:
        # 未携带 ticket 票据
        # 仅在生产环境下的分布式模式中，强制拦截并要求提供单次消费票据 ticket，消除长期凭证暴露隐患
        if settings.DISTRIBUTED_MODE and settings.is_production:
            logger.warning("游戏WS拒绝连接: 分布式生产环境下强制要求提供一次性票据 ticket, player_id=%s", player_id)
            await websocket.accept()
            await websocket.close(code=1008, reason="Unauthorized")
            return
            
        # 非生产环境或单机模式下退避到原有长期令牌 auth_token 验证，保持老旧单机单元测试及开发调试兼容
        game_auth_token = websocket.query_params.get("auth_token")
        if not game_auth_token:
            logger.warning("游戏WS拒绝连接: 缺少游戏 auth_token, player_id=%s", player_id)
            await websocket.accept()
            await websocket.close(code=1008, reason="Unauthorized")
            return
        try:
            token_player_id = verify_game_auth_token(game_auth_token)
        except Exception:
            logger.warning("游戏WS拒绝连接: 游戏 auth_token 无效或已过期, player_id=%s", player_id)
            await websocket.accept()
            await websocket.close(code=1008, reason="Unauthorized")
            return
        if token_player_id != player_id:
            logger.warning(
                "游戏WS拒绝连接: token 玩家不匹配, path_player_id=%s, token_player_id=%s",
                player_id,
                token_player_id,
            )
            await websocket.accept()
            await websocket.close(code=1008, reason="Forbidden")
            return

    # 3. 在线 Presence 管理与重复登录 kick
    from app.infrastructure.config import settings
    from app.application.game.schemas import GameEventSchema
    import time
    import uuid

    presence_service = websocket.app.state.presence_service
    message_bus = websocket.app.state.game_message_bus

    new_epoch = await presence_service.increment_epoch(player_id)
    old_presence = await presence_service.get_presence(player_id)

    if old_presence:
        old_instance = old_presence.get("instance_id")
        old_epoch = old_presence.get("connection_epoch")
        if old_instance == settings.INSTANCE_ID:
            old_ws = manager.connections.get(player_id)
            if old_ws:
                logger.info("游戏WS: 检测到同一实例重复登录，本地踢出旧连接, player_id=%s", player_id)
                try:
                    await old_ws.close(code=1008, reason="DuplicateLogin")
                except Exception:
                    pass
                manager.disconnect(player_id, old_ws)
        elif old_instance:
            logger.info("游戏WS: 检测到跨实例重复登录，发送 kick 广播给旧实例 %s, player_id=%s", old_instance, player_id)
            kick_event = GameEventSchema(
                event_id=f"kick-{uuid.uuid4().hex[:8]}",
                event="kick",
                room_id="lobby",
                room_version=0,
                target_player_id=player_id,
                target_connection_epoch=old_epoch,
                payload={},
                created_at=time.time(),
                trace_id=f"kick-trace-{player_id}"
            )
            try:
                await message_bus.publish_event(old_instance, kick_event)
            except Exception as e:
                logger.error("游戏WS: 发送 kick 消息中转失败: %s", e)

    await presence_service.set_presence(player_id, settings.INSTANCE_ID, new_epoch)

    from app.interfaces.websocket.game_handler import GameWebSocketHandler
    handler = GameWebSocketHandler(
        websocket, 
        player_id, 
        manager, 
        game_service, 
        connection_epoch=new_epoch,
        scheduler_service=getattr(websocket.app.state, "scheduler_service", None)
    )
    presence_heartbeat_task = asyncio.create_task(
        _presence_heartbeat(
            presence_service,
            player_id,
            settings.INSTANCE_ID,
            new_epoch,
        )
    )
    
    try:
        await handler.run()
    finally:
        presence_heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await presence_heartbeat_task
        logger.info("游戏WS: 玩家连接释放，尝试清理在线状态, player_id=%s, epoch=%s", player_id, new_epoch)
        await presence_service.remove_presence(player_id, new_epoch)
