import time
import json
import logging
from typing import Optional
from app.domain.game.interfaces import ILeaseManager
from app.infrastructure.redis_client import redis_client

logger = logging.getLogger("happy_doudizhu")

class RedisLeaseManager(ILeaseManager):
    """基于 Redis 的分布式分片与房间租约管理器。"""

    def __init__(self, client=None):
        self._client = client or redis_client

    @staticmethod
    def _shard_key(shard_id: int) -> str:
        return f"game:shard_owner:{shard_id}"

    @staticmethod
    def _room_key(room_id: str) -> str:
        return f"game:room_owner:{room_id}"

    async def acquire_shard_lease(self, shard_id: int, instance_id: str) -> Optional[int]:
        """尝试获取分片的所有权租约。若成功返回新 fencing token，失败返回 None。"""
        key = self._shard_key(shard_id)
        now = time.time()
        # Lua 脚本，原子抢占/续租，并使用 Redis 的 INCR 生成单调递增 token
        lua_script = """
        local current = redis.call('get', KEYS[1])
        local now = tonumber(ARGV[1])
        local instance_id = ARGV[2]
        local expire_in = tonumber(ARGV[3])
        
        if current then
            local data = cjson.decode(current)
            if tonumber(data.expire_at) > now and data.instance_id ~= instance_id then
                -- 仍处于有效期内且非本实例持有，抢占失败
                return nil
            end
        end
        
        -- 可以抢占或续租
        local token = redis.call('incr', 'game:fencing_token_seq')
        local payload = {
            instance_id = instance_id,
            expire_at = now + expire_in,
            fencing_token = token
        }
        redis.call('set', KEYS[1], cjson.encode(payload))
        return token
        """
        try:
            # 租约有效期 10 秒
            result = await self._client.eval(lua_script, 1, key, now, instance_id, 10)
            if result:
                return int(result)
        except Exception as e:
            logger.error(f"[RedisLeaseManager] Failed to acquire shard lease for {shard_id}: {e}")
        return None

    async def renew_shard_lease(self, shard_id: int, instance_id: str, token: int) -> bool:
        """续租。只有在当前持有者依然是自己，且 fencing_token 匹配时才可以续租。"""
        key = self._shard_key(shard_id)
        now = time.time()
        lua_script = """
        local current = redis.call('get', KEYS[1])
        local now = tonumber(ARGV[1])
        local instance_id = ARGV[2]
        local token = tonumber(ARGV[3])
        local expire_in = tonumber(ARGV[4])
        
        if current then
            local data = cjson.decode(current)
            if data.instance_id == instance_id and tonumber(data.fencing_token) == token then
                data.expire_at = now + expire_in
                redis.call('set', KEYS[1], cjson.encode(data))
                return 1
            end
        end
        return 0
        """
        try:
            result = await self._client.eval(lua_script, 1, key, now, instance_id, token, 10)
            return bool(result == 1)
        except Exception as e:
            logger.error(f"[RedisLeaseManager] Failed to renew shard lease for {shard_id}: {e}")
            return False

    async def acquire_room_lease(self, room_id: str, shard_id: int, token: int) -> bool:
        """记录房间和当前持有它的分片 Worker 的 fencing token 的关联，确保单写。"""
        key = self._room_key(room_id)
        payload = {
            "shard_id": shard_id,
            "fencing_token": token,
            "updated_at": time.time()
        }
        try:
            await self._client.set(key, json.dumps(payload), ex=7200)
            return True
        except Exception as e:
            logger.error(f"[RedisLeaseManager] Failed to acquire room lease for {room_id}: {e}")
            return False
