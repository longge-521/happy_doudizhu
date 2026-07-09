import json
import logging
from typing import List, Optional
from app.domain.game.interfaces import IOutboxService
from app.application.game.schemas import GameEventSchema
from app.infrastructure.redis_client import redis_client

logger = logging.getLogger("happy_doudizhu")

class RedisOutboxService(IOutboxService):
    """基于 Redis 的分布式 CAS 房间快照提交与 Outbox 持久化信箱。"""

    def __init__(self, client=None):
        self._client = client or redis_client

    @staticmethod
    def _room_key(room_id: str) -> str:
        return f"game:room:{room_id}"

    @staticmethod
    def _commands_key(room_id: str) -> str:
        return f"game:room_commands:{room_id}"

    @staticmethod
    def _outbox_key(room_id: str) -> str:
        return f"game:room_outbox:{room_id}"

    async def save_event(self, room_id: str, event: GameEventSchema) -> None:
        await self.save_events(room_id, [event])

    async def save_events(self, room_id: str, events: List[GameEventSchema]) -> None:
        """仅将事件压入 Redis Outbox（不修改快照的独立广播模式）"""
        if not events:
            return
        outbox_key = self._outbox_key(room_id)
        payload = {}
        for ev in events:
            payload[ev.event_id] = ev.model_dump_json()
        try:
            await self._client.hset(outbox_key, mapping=payload)
        except Exception as e:
            logger.error(f"[RedisOutboxService] Failed to push events to outbox: {e}")

    async def save_events_with_envelope(
        self,
        room_id: str,
        events: List[GameEventSchema],
        envelope_json: str,
        fencing_token: int,
        old_version: int,
        owner_id: str,
        command_id: Optional[str] = None
    ) -> int:
        """
        在一个原子 Lua 脚本事务中同时完成：fencing所有权校验、房间版本CAS、命令去重、新状态保存和Outbox事件写入。
        返回值含义：
          1  - 成功
          -1 - fencing token 冲突（有更新的主接管）
          -2 - 房间版本 CAS 冲突（脏写拦截）
          -3 - 命令幂等重复
        """
        room_key = self._room_key(room_id)
        commands_key = self._commands_key(room_id)
        outbox_key = self._outbox_key(room_id)

        # 构造待写入的 outbox 事件映射
        events_map = {}
        for ev in events:
            events_map[ev.event_id] = ev.model_dump_json()
        events_json = json.dumps(events_map)

        lua_script = """
        local room_key = KEYS[1]
        local commands_key = KEYS[2]
        local outbox_key = KEYS[3]
        
        local f_token = tonumber(ARGV[1])
        local old_version = tonumber(ARGV[2])
        local owner_id = ARGV[3]
        local cmd_id = ARGV[4]
        local envelope_json = ARGV[5]
        local events_json = ARGV[6]
        
        -- 1. 校验快照 Fencing 与 Version CAS
        local current = redis.call('get', room_key)
        if current then
            local data = cjson.decode(current)
            if data.fencing_token and tonumber(data.fencing_token) > f_token then
                return -1
            end
            if data.room_version and tonumber(data.room_version) ~= old_version then
                return -2
            end
        end
        
        -- 2. 校验命令幂等
        if cmd_id and cmd_id ~= "" then
            if redis.call('sismember', commands_key, cmd_id) == 1 then
                return -3
            end
        end
        
        -- 3. 校验通过，原子存入房间信封
        redis.call('set', room_key, envelope_json)
        
        -- 4. 写入命令去重（2小时过期）
        if cmd_id and cmd_id ~= "" then
            redis.call('sadd', commands_key, cmd_id)
            redis.call('expire', commands_key, 7200)
        end
        
        -- 5. 写入事件至 Outbox (Hash)
        if events_json and events_json ~= "" then
            local events = cjson.decode(events_json)
            for eid, val in pairs(events) do
                redis.call('hset', outbox_key, eid, val)
            end
        end
        
        return 1
        """
        try:
            result = await self._client.eval(
                lua_script,
                3,
                room_key,
                commands_key,
                outbox_key,
                fencing_token,
                old_version,
                owner_id,
                command_id or "",
                envelope_json,
                events_json
            )
            return int(result)
        except Exception as e:
            logger.error(f"[RedisOutboxService] Lua save_events_with_envelope failed for {room_id}: {e}")
            # 若连接出错等异常，返回 -9 代表基础故障，防止覆盖错误状态
            return -9

    async def get_pending_events(self, room_id: str) -> List[GameEventSchema]:
        outbox_key = self._outbox_key(room_id)
        try:
            data = await self._client.hvals(outbox_key)
            result = []
            for item in data:
                result.append(GameEventSchema.model_validate_json(item))
            return result
        except Exception as e:
            logger.error(f"[RedisOutboxService] Failed to get pending events for {room_id}: {e}")
            return []

    async def acknowledge_event(self, room_id: str, event_id: str) -> None:
        outbox_key = self._outbox_key(room_id)
        try:
            await self._client.hdel(outbox_key, event_id)
        except Exception as e:
            logger.error(f"[RedisOutboxService] Failed to ack event {event_id} in {room_id}: {e}")
