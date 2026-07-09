import time
import json
import logging
from typing import Dict, Any, Optional
from app.domain.game.interfaces import IPresenceService
from app.infrastructure.redis_client import redis_client

logger = logging.getLogger("happy_doudizhu")
PRESENCE_TTL_SECONDS = 60

class RedisPresenceService(IPresenceService):
    """基于 Redis 的分布式 Presence 共享服务。"""

    def __init__(self, client=None):
        self._client = client or redis_client

    @staticmethod
    def _presence_key(player_id: str) -> str:
        return f"game:presence:{player_id}"

    @staticmethod
    def _epoch_key(player_id: str) -> str:
        return f"game:connection_epoch:{player_id}"

    async def get_presence(self, player_id: str) -> Optional[Dict[str, Any]]:
        key = self._presence_key(player_id)
        try:
            data = await self._client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"[RedisPresenceService] Failed to get presence for {player_id}: {e}")
        return None

    async def set_presence(self, player_id: str, instance_id: str, epoch: int) -> None:
        key = self._presence_key(player_id)
        payload = {
            "player_id": player_id,
            "instance_id": instance_id,
            "connection_epoch": epoch,
            "connected_at": time.time(),
            "last_seen_at": time.time()
        }
        try:
            # 存入 JSON string，TTL 为 60 秒
            await self._client.set(
                key,
                json.dumps(payload),
                ex=PRESENCE_TTL_SECONDS,
            )
        except Exception as e:
            logger.error(f"[RedisPresenceService] Failed to set presence for {player_id}: {e}")

    async def refresh_presence(self, player_id: str, instance_id: str, epoch: int) -> bool:
        key = self._presence_key(player_id)
        lua_script = """
        local current = redis.call('get', KEYS[1])
        if not current then
            return 0
        end
        local data = cjson.decode(current)
        if data.instance_id ~= ARGV[1]
            or data.connection_epoch ~= tonumber(ARGV[2]) then
            return 0
        end
        data.last_seen_at = tonumber(ARGV[3])
        redis.call(
            'set',
            KEYS[1],
            cjson.encode(data),
            'EX',
            tonumber(ARGV[4])
        )
        return 1
        """
        try:
            result = await self._client.eval(
                lua_script,
                1,
                key,
                instance_id,
                epoch,
                time.time(),
                PRESENCE_TTL_SECONDS,
            )
            return bool(result == 1)
        except Exception as e:
            logger.error(f"[RedisPresenceService] Failed to refresh presence for {player_id}: {e}")
            raise

    async def increment_epoch(self, player_id: str) -> int:
        key = self._epoch_key(player_id)
        try:
            new_epoch = await self._client.incr(key)
            return int(new_epoch)
        except Exception as e:
            logger.error(f"[RedisPresenceService] Failed to increment epoch for {player_id}: {e}")
            return 1

    async def remove_presence(self, player_id: str, expected_epoch: int) -> bool:
        key = self._presence_key(player_id)
        # Lua 脚本，当 connection_epoch == expected_epoch 时删除键
        lua_script = """
        local current = redis.call('get', KEYS[1])
        if current then
            local data = cjson.decode(current)
            if data.connection_epoch == tonumber(ARGV[1]) then
                redis.call('del', KEYS[1])
                return 1
            end
        end
        return 0
        """
        try:
            result = await self._client.eval(lua_script, 1, key, expected_epoch)
            return bool(result == 1)
        except Exception as e:
            logger.error(f"[RedisPresenceService] Failed to remove presence for {player_id}: {e}")
            return False
