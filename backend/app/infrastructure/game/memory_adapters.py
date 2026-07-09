import time
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Awaitable, Any
from app.application.game.schemas import GameCommandSchema, GameEventSchema, ScheduledTaskSchema
from app.domain.game.interfaces import (
    IGameMessageBus,
    IPresenceService,
    ILeaseManager,
    IOutboxService,
    ISchedulerService
)

logger = logging.getLogger("happy_doudizhu")

class MemoryMessageBus(IGameMessageBus):
    """单机内存版消息总线实现。"""
    def __init__(self):
        self._subscribers: Dict[int, List[Callable[[GameCommandSchema], Awaitable[None]]]] = {}

    async def publish_command(self, shard_id: int, command: GameCommandSchema) -> None:
        callbacks = self._subscribers.get(shard_id, [])
        for cb in callbacks:
            # 异步执行，模拟 MQ 的消息派发
            asyncio.create_task(cb(command))

    async def subscribe_commands(
        self, 
        shard_id: int, 
        callback: Callable[[GameCommandSchema], Awaitable[None]]
    ) -> None:
        if shard_id not in self._subscribers:
            self._subscribers[shard_id] = []
        self._subscribers[shard_id].append(callback)

    async def unsubscribe_commands(self, shard_id: int) -> None:
        self._subscribers.pop(shard_id, None)

    async def publish_event(self, instance_id: str, event: GameEventSchema) -> None:
        # 在单机模式下，直接调用本地 WebSocket 连接管理器进行推送
        # 本实现只打印 debug 日志。真实的 websocket 推送依然由原 websocket 连接负责。
        logger.debug(
            f"[MemoryMessageBus] Publish event {event.event} "
            f"to instance {instance_id} for player {event.target_player_id}"
        )

class MemoryPresenceService(IPresenceService):
    """单机内存版 Presence 在线及代次管理实现。"""
    def __init__(self):
        self._presences: Dict[str, Dict[str, Any]] = {}
        self._epochs: Dict[str, int] = {}

    async def get_presence(self, player_id: str) -> Optional[Dict[str, Any]]:
        return self._presences.get(player_id)

    async def set_presence(self, player_id: str, instance_id: str, epoch: int) -> None:
        self._presences[player_id] = {
            "player_id": player_id,
            "instance_id": instance_id,
            "connection_epoch": epoch,
            "connected_at": time.time(),
            "last_seen_at": time.time(),
        }
        self._epochs[player_id] = epoch

    async def refresh_presence(self, player_id: str, instance_id: str, epoch: int) -> bool:
        presence = self._presences.get(player_id)
        if (
            presence
            and presence.get("instance_id") == instance_id
            and presence.get("connection_epoch") == epoch
        ):
            presence["last_seen_at"] = time.time()
            return True
        return False

    async def increment_epoch(self, player_id: str) -> int:
        current = self._epochs.get(player_id, 0)
        new_epoch = current + 1
        self._epochs[player_id] = new_epoch
        return new_epoch

    async def remove_presence(self, player_id: str, expected_epoch: int) -> bool:
        presence = self._presences.get(player_id)
        if presence and presence.get("connection_epoch") == expected_epoch:
            self._presences.pop(player_id, None)
            return True
        return False

class MemoryLeaseManager(ILeaseManager):
    """单机内存版租约实现，始终允许抢占并单增 token。"""
    def __init__(self):
        self._shard_tokens: Dict[int, int] = {}
        self._room_owners: Dict[str, str] = {}

    async def acquire_shard_lease(self, shard_id: int, instance_id: str) -> Optional[int]:
        current_token = self._shard_tokens.get(shard_id, 0)
        new_token = current_token + 1
        self._shard_tokens[shard_id] = new_token
        return new_token

    async def renew_shard_lease(self, shard_id: int, instance_id: str, token: int) -> bool:
        return self._shard_tokens.get(shard_id) == token

    async def acquire_room_lease(self, room_id: str, shard_id: int, token: int) -> bool:
        self._room_owners[room_id] = f"shard-{shard_id}"
        return True

class MemoryOutboxService(IOutboxService):
    """单机内存版事件信箱，将事件缓冲存在内存列表。"""
    def __init__(self):
        self._outboxes: Dict[str, List[GameEventSchema]] = {}

    async def save_event(self, room_id: str, event: GameEventSchema) -> None:
        if room_id not in self._outboxes:
            self._outboxes[room_id] = []
        self._outboxes[room_id].append(event)

    async def save_events(self, room_id: str, events: List[GameEventSchema]) -> None:
        if room_id not in self._outboxes:
            self._outboxes[room_id] = []
        self._outboxes[room_id].extend(events)

    async def get_pending_events(self, room_id: str) -> List[GameEventSchema]:
        return self._outboxes.get(room_id, [])

    async def acknowledge_event(self, room_id: str, event_id: str) -> None:
        events = self._outboxes.get(room_id, [])
        self._outboxes[room_id] = [ev for ev in events if ev.event_id != event_id]

class MemorySchedulerService(ISchedulerService):
    """单机内存版超时调度服务，由 asyncio 定时任务进行模拟。"""
    def __init__(self, message_bus: IGameMessageBus):
        self._message_bus = message_bus
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def schedule_task(self, task: ScheduledTaskSchema) -> None:
        await self.cancel_task(task.task_id)

        async def _run_delayed():
            try:
                delay = max(0.0, task.due_at - time.time())
                await asyncio.sleep(delay)
                
                command = GameCommandSchema(
                    command_id=task.task_id,
                    action=task.task_type,
                    room_id=task.room_id,
                    player_id="system",
                    connection_epoch=0,
                    payload=task.payload,
                    created_at=time.time(),
                    trace_id=f"sched-{task.task_id}",
                    source_instance_id="memory-scheduler"
                )
                # 分片 id 固定为 0 进行单实例处理
                await self._message_bus.publish_command(0, command)
            except asyncio.CancelledError:
                pass
            finally:
                self._active_tasks.pop(task.task_id, None)

        loop_task = asyncio.create_task(_run_delayed())
        self._active_tasks[task.task_id] = loop_task

    async def cancel_task(self, task_id: str) -> None:
        loop_task = self._active_tasks.pop(task_id, None)
        if loop_task and not loop_task.done():
            loop_task.cancel()
