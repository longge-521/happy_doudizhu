import pytest
import asyncio
import time
import uuid
import aio_pika
from app.infrastructure.game.rabbitmq_bus import RabbitMQMessageBus
from app.application.game.schemas import GameEventSchema, GameCommandSchema

@pytest.mark.asyncio
async def test_rabbitmq_bus_publish():
    bus = RabbitMQMessageBus()
    await bus.connect()
    
    # 构造事件
    event = GameEventSchema(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        event="test_event",
        room_id="room_test_123",
        room_version=1,
        target_player_id="player_test_123",
        target_connection_epoch=1,
        payload={"msg": "hello"},
        created_at=time.time(),
        trace_id="trace_test_123"
    )
    
    # 构造命令，补齐 connection_epoch 与 source_instance_id
    command = GameCommandSchema(
        command_id=f"cmd-{uuid.uuid4().hex[:8]}",
        action="play_cards",
        room_id="room_test_123",
        player_id="player_test_123",
        connection_epoch=1,
        source_instance_id="inst_test_abc",
        payload={"cards": ["3", "3"]},
        created_at=time.time(),
        trace_id="trace_cmd_123"
    )
    
    # 1. 验证发布事件和命令不报错
    try:
        await bus.publish_event(instance_id="inst_test_abc", event=event)
        await bus.publish_command(shard_id=10, command=command)
    except Exception as e:
        pytest.fail(f"RabbitMQMessageBus publish failed: {e}")
    finally:
        await bus.close()
