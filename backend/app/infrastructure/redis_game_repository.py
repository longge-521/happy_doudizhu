# backend/app/infrastructure/redis_game_repository.py
"""Redis 游戏状态仓储：房间状态、玩家映射、匹配队列的 CRUD"""
import json
import logging
from typing import Optional, List
from app.domain.game.room import GameRoom

logger = logging.getLogger("hmp_ws_service")

ROOM_KEY_PREFIX = "game:room:"
PLAYER_ROOM_PREFIX = "game:player_room:"
MATCH_QUEUE_KEY = "game:match_queue"
ROOM_TTL = 7200       # 房间状态 2 小时过期
PLAYER_ROOM_TTL = 3600  # 玩家映射 1 小时过期


class RedisGameRepository:
    """基于 Redis 的游戏状态持久化适配器"""

    def __init__(self, redis_client):
        self._redis = redis_client

    # ── 房间状态 ──

    async def save_room(self, room: GameRoom) -> None:
        key = f"{ROOM_KEY_PREFIX}{room.room_id}"
        data = json.dumps(room.to_dict(), ensure_ascii=False)
        await self._redis.set(key, data, ex=ROOM_TTL)

    async def get_room(self, room_id: str) -> Optional[GameRoom]:
        key = f"{ROOM_KEY_PREFIX}{room_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        # 如果是 bytes, 需要 decode
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return GameRoom.from_dict(json.loads(data))

    async def delete_room(self, room_id: str) -> None:
        key = f"{ROOM_KEY_PREFIX}{room_id}"
        await self._redis.delete(key)

    # ── 玩家-房间映射 ──

    async def set_player_room(self, player_id: str, room_id: str) -> None:
        key = f"{PLAYER_ROOM_PREFIX}{player_id}"
        await self._redis.set(key, room_id, ex=PLAYER_ROOM_TTL)

    async def get_player_room(self, player_id: str) -> Optional[str]:
        key = f"{PLAYER_ROOM_PREFIX}{player_id}"
        res = await self._redis.get(key)
        if res and isinstance(res, bytes):
            return res.decode("utf-8")
        return res

    async def remove_player_room(self, player_id: str) -> None:
        key = f"{PLAYER_ROOM_PREFIX}{player_id}"
        await self._redis.delete(key)

    # ── 匹配队列 ──

    def _get_queue_key(self, base_score: int) -> str:
        return f"{MATCH_QUEUE_KEY}:{base_score}"

    async def add_to_match_queue(self, player_id: str, base_score: int = 10) -> None:
        key = self._get_queue_key(base_score)
        await self._redis.lrem(key, 0, player_id)
        await self._redis.rpush(key, player_id)

    async def remove_from_match_queue(self, player_id: str, base_score: int = 10) -> int:
        return await self._redis.lrem(self._get_queue_key(base_score), 1, player_id)

    async def pop_match_players(self, count: int = 3, base_score: int = 10) -> List[str]:
        """原子性地从队列头部弹出 count 个玩家"""
        players = []
        key = self._get_queue_key(base_score)
        for _ in range(count):
            pid = await self._redis.lpop(key)
            if pid is None:
                break
            if isinstance(pid, bytes):
                pid = pid.decode("utf-8")
            players.append(pid)
        return players

    async def get_match_queue_length(self, base_score: int = 10) -> int:
        res = await self._redis.llen(self._get_queue_key(base_score))
        return res
