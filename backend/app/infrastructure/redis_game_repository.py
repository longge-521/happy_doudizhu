# backend/app/infrastructure/redis_game_repository.py
"""Redis 游戏状态仓储：房间状态、玩家映射、匹配队列的 CRUD"""
import json
import logging
from typing import Optional, List
from app.domain.game.room import GameRoom

logger = logging.getLogger("happy_doudizhu")

ROOM_KEY_PREFIX = "game:room:"
PLAYER_ROOM_PREFIX = "game:player_room:"
MATCH_QUEUE_KEY = "game:match_queue"
POP_MATCH_PLAYERS_SCRIPT = """
local count = tonumber(ARGV[1])
local len = redis.call('LLEN', KEYS[1])
if count == 3 then
    if len >= 3 then
        local players = redis.call('LRANGE', KEYS[1], 0, 2)
        redis.call('LTRIM', KEYS[1], 3, -1)
        return players
    else
        return {}
    end
else
    local pop_count = math.min(count, len)
    if pop_count > 0 then
        local players = redis.call('LRANGE', KEYS[1], 0, pop_count - 1)
        redis.call('LTRIM', KEYS[1], pop_count, -1)
        return players
    else
        return {}
    end
end
"""
ROOM_TTL = 7200       # 房间状态 2 小时过期
PLAYER_ROOM_TTL = 3600  # 玩家映射 1 小时过期


class RedisGameRepository:
    """基于 Redis 的游戏状态持久化适配器"""

    def __init__(self, redis_client, presence_service=None, message_bus=None, outbox_service=None):
        self._redis = redis_client
        self._presence = presence_service
        self._bus = message_bus
        self._outbox = outbox_service

    # ── 房间状态 ──

    async def save_room(self, room: GameRoom) -> None:
        from app.infrastructure.config import settings
        
        key = f"{ROOM_KEY_PREFIX}{room.room_id}"
        
        if settings.DISTRIBUTED_MODE:
            from app.infrastructure.game.redis_outbox import RedisOutboxService
            from app.infrastructure.game.context import current_outbox_events, current_command_id
            import time
            
            outbox_service = RedisOutboxService(self._redis)
            events = current_outbox_events.get() or []
            
            fencing_token = getattr(room, "envelope_fencing_token", 0) or 0
            old_version = getattr(room, "envelope_version", 0) or 0
            owner_id = getattr(room, "envelope_owner", "") or ""
            cmd_id = current_command_id.get()
            
            new_version = old_version + 1
            
            envelope = {
                "room_id": room.room_id,
                "room_version": new_version,
                "owner_instance_id": owner_id,
                "fencing_token": fencing_token,
                "phase": room.phase.name if hasattr(room.phase, "name") else str(room.phase),
                "state": room.to_dict(),
                "updated_at": time.time()
            }
            
            envelope_json = json.dumps(envelope, ensure_ascii=False)
            
            res = await outbox_service.save_events_with_envelope(
                room_id=room.room_id,
                events=events,
                envelope_json=envelope_json,
                fencing_token=fencing_token,
                old_version=old_version,
                owner_id=owner_id,
                command_id=cmd_id
            )
            
            if res < 0:
                logger.error(
                    f"[RedisGameRepository] CAS write failed for room {room.room_id}: "
                    f"code={res}, fencing_token={fencing_token}, version={old_version}, owner={owner_id}"
                )
                if res == -1:
                    raise RuntimeError("Fencing token conflict - lease lost")
                elif res == -2:
                    raise RuntimeError("Room version CAS conflict - concurrent write detected")
                elif res == -3:
                    logger.warning(f"[RedisGameRepository] Duplicate command {cmd_id} detected. Skipped.")
                    return
                else:
                    raise RuntimeError(f"Lua CAS write failed with error code {res}")
            
            room.envelope_version = new_version
            
            # 即时 Outbox Relay 投递，将待发送事件分发给目标实例网关
            if self._presence and self._bus and self._outbox:
                for ev in events:
                    try:
                        presence = await self._presence.get_presence(ev.target_player_id)
                        if presence:
                            target_inst = presence.get("instance_id")
                            if target_inst:
                                await self._bus.publish_event(target_inst, ev)
                                await self._outbox.acknowledge_event(room.room_id, ev.event_id)
                    except Exception as relay_err:
                        logger.error(f"[OutboxRelay] Failed to relay event {ev.event_id}: {relay_err}")
        else:
            data = json.dumps(room.to_dict(), ensure_ascii=False)
            await self._redis.set(key, data, ex=ROOM_TTL)

    async def get_room(self, room_id: str) -> Optional[GameRoom]:
        key = f"{ROOM_KEY_PREFIX}{room_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        
        parsed = json.loads(data)
        if isinstance(parsed, dict) and "state" in parsed and "room_version" in parsed:
            room = GameRoom.from_dict(parsed["state"])
            room.envelope_version = parsed["room_version"]
            room.envelope_fencing_token = parsed.get("fencing_token")
            room.envelope_owner = parsed.get("owner_instance_id")
            return room
            
        room = GameRoom.from_dict(parsed)
        room.envelope_version = 0
        room.envelope_fencing_token = 0
        room.envelope_owner = ""
        return room

    async def delete_room(self, room_id: str) -> None:
        keys_to_del = [
            f"{ROOM_KEY_PREFIX}{room_id}",
            f"game:room_commands:{room_id}",
            f"game:room_outbox:{room_id}"
        ]
        await self._redis.delete(*keys_to_del)

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

    def _get_queue_key(self, base_score: int, play_mode: str = "classic") -> str:
        return f"{MATCH_QUEUE_KEY}:{play_mode}:{base_score}"

    async def add_to_match_queue(self, player_id: str, base_score: int = 10, play_mode: str = "classic") -> None:
        key = self._get_queue_key(base_score, play_mode)
        await self._redis.lrem(key, 0, player_id)
        await self._redis.rpush(key, player_id)

    async def remove_from_match_queue(self, player_id: str, base_score: int = 10, play_mode: str = "classic") -> int:
        return await self._redis.lrem(self._get_queue_key(base_score, play_mode), 1, player_id)

    async def pop_match_players(self, count: int = 3, base_score: int = 10, play_mode: str = "classic") -> List[str]:
        """原子性地从队列头部弹出 count 个玩家"""
        key = self._get_queue_key(base_score, play_mode)
        raw_players = await self._redis.eval(POP_MATCH_PLAYERS_SCRIPT, 1, key, count)
        players = []
        for pid in raw_players:
            if isinstance(pid, bytes):
                pid = pid.decode("utf-8")
            players.append(pid)
        return players

    async def get_match_queue_length(self, base_score: int = 10, play_mode: str = "classic") -> int:
        res = await self._redis.llen(self._get_queue_key(base_score, play_mode))
        return res

    async def pop_no_shuffle_deck(self) -> Optional[List[int]]:
        key = "game:noshuffle:deck_pool"
        raw = await self._redis.lpop(key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        import json
        return json.loads(raw)

    async def push_no_shuffle_deck(self, deck: List[int]) -> None:
        key = "game:noshuffle:deck_pool"
        import json
        await self._redis.rpush(key, json.dumps(deck))
        # 保留最新的100叠牌，修剪老数据，防止 Redis 内存暴涨
        await self._redis.ltrim(key, -100, -1)

    # ── 匹配元数据 ──

    async def save_match_player_meta(self, player_id: str, nickname: str, base_score: int) -> None:
        key = f"game:match_player:{player_id}"
        await self._redis.set(key, json.dumps({"nickname": nickname, "base_score": base_score}), ex=600)

    async def get_match_player_meta(self, player_id: str) -> Optional[dict]:
        key = f"game:match_player:{player_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

    async def delete_match_player_meta(self, player_id: str) -> None:
        key = f"game:match_player:{player_id}"
        await self._redis.delete(key)

    # ── 延时调度 ──

    async def schedule_game_task(self, task) -> None:
        if self._outbox:
            from app.infrastructure.game.redis_scheduler import RedisSchedulerService
            scheduler = RedisSchedulerService(self._redis)
            await scheduler.schedule_task(task)

    async def cancel_game_task(self, task_id: str) -> None:
        if self._outbox:
            from app.infrastructure.game.redis_scheduler import RedisSchedulerService
            scheduler = RedisSchedulerService(self._redis)
            await scheduler.cancel_task(task_id)

    async def publish_game_command(self, shard_id: int, command) -> None:
        if self._bus:
            await self._bus.publish_command(shard_id, command)
