import asyncio
import time
import pytest
from app.application.game.schemas import GameCommandSchema, GameEventSchema, ScheduledTaskSchema
from app.infrastructure.game.memory_adapters import (
    MemoryMessageBus,
    MemoryPresenceService,
    MemoryLeaseManager,
    MemoryOutboxService,
    MemorySchedulerService
)

@pytest.mark.asyncio
async def test_memory_message_bus():
    bus = MemoryMessageBus()
    received_commands = []

    async def cb(cmd: GameCommandSchema):
        received_commands.append(cmd)

    await bus.subscribe_commands(shard_id=1, callback=cb)

    cmd = GameCommandSchema(
        command_id="cmd-1",
        action="test_action",
        room_id="room-1",
        player_id="player-1",
        connection_epoch=1,
        created_at=time.time(),
        trace_id="t-1",
        source_instance_id="inst-1"
    )

    # 发布到订阅的分片 1
    await bus.publish_command(shard_id=1, command=cmd)
    
    # 因为是用 asyncio.create_task 后台执行，等待事件循环运行一下
    await asyncio.sleep(0.05)
    
    assert len(received_commands) == 1
    assert received_commands[0].command_id == "cmd-1"

    # 发布到未订阅的分片 2
    await bus.publish_command(shard_id=2, command=cmd)
    await asyncio.sleep(0.05)
    assert len(received_commands) == 1

@pytest.mark.asyncio
async def test_memory_presence_service():
    service = MemoryPresenceService()
    
    # 初始状态无 Presence
    presence = await service.get_presence("p1")
    assert presence is None

    # 设置 Presence
    await service.set_presence("p1", instance_id="inst-1", epoch=1)
    presence = await service.get_presence("p1")
    assert presence is not None
    assert presence["instance_id"] == "inst-1"
    assert presence["connection_epoch"] == 1

    # 递增 epoch
    new_epoch = await service.increment_epoch("p1")
    assert new_epoch == 2

    # 删除 Presence
    # 期望 epoch 错误，删除失败
    deleted = await service.remove_presence("p1", expected_epoch=999)
    assert deleted is False

    # 期望 epoch 匹配，删除成功
    deleted = await service.remove_presence("p1", expected_epoch=1)
    assert deleted is True
    assert await service.get_presence("p1") is None

@pytest.mark.asyncio
async def test_memory_lease_manager():
    manager = MemoryLeaseManager()
    
    # 获取分片租约
    token1 = await manager.acquire_shard_lease(shard_id=1, instance_id="inst-1")
    assert token1 is not None

    # 续约
    renewed = await manager.renew_shard_lease(shard_id=1, instance_id="inst-1", token=token1)
    assert renewed is True

    # 错误的 token 续约失败
    renewed_bad = manager.renew_shard_lease(shard_id=1, instance_id="inst-1", token=999)
    assert await renewed_bad is False

    # 获取房间租约
    room_lease = await manager.acquire_room_lease(room_id="r1", shard_id=1, token=token1)
    assert room_lease is True

@pytest.mark.asyncio
async def test_memory_outbox_service():
    service = MemoryOutboxService()
    
    evt = GameEventSchema(
        event_id="evt-1",
        event="test_evt",
        room_id="r1",
        room_version=1,
        target_player_id="p1",
        target_connection_epoch=1,
        created_at=time.time(),
        trace_id="t-1"
    )

    await service.save_event(room_id="r1", event=evt)
    pending = await service.get_pending_events(room_id="r1")
    assert len(pending) == 1
    assert pending[0].event_id == "evt-1"

    # 确认事件，移出 Outbox
    await service.acknowledge_event(room_id="r1", event_id="evt-1")
    pending_after = await service.get_pending_events(room_id="r1")
    assert len(pending_after) == 0

@pytest.mark.asyncio
async def test_memory_scheduler_service():
    bus = MemoryMessageBus()
    scheduler = MemorySchedulerService(bus)
    received_cmds = []

    async def cb(cmd: GameCommandSchema):
        received_cmds.append(cmd)

    await bus.subscribe_commands(shard_id=0, callback=cb)

    # 调度 0.1 秒后到期的任务
    task = ScheduledTaskSchema(
        task_id="t-123",
        due_at=time.time() + 0.1,
        room_id="r1",
        task_type="ai_thinking",
        expected_room_version=2,
        payload={"action": "call"},
        created_at=time.time()
    )

    await scheduler.schedule_task(task)
    
    # 还没到期，应该没有任何消息发布
    await asyncio.sleep(0.02)
    assert len(received_cmds) == 0

    # 等待到期并发布
    await asyncio.sleep(0.12)
    assert len(received_cmds) == 1
    assert received_cmds[0].command_id == "t-123"
    assert received_cmds[0].action == "ai_thinking"

    # 测试取消任务
    task2 = ScheduledTaskSchema(
        task_id="t-456",
        due_at=time.time() + 0.1,
        room_id="r1",
        task_type="ai_thinking",
        expected_room_version=2,
        payload={"action": "call"},
        created_at=time.time()
    )
    await scheduler.schedule_task(task2)
    await scheduler.cancel_task("t-456")
    
    await asyncio.sleep(0.15)
    # 仍然只有之前的一个命令，说明第二个已经被成功取消
    assert len(received_cmds) == 1
