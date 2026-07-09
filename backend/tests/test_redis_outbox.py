import pytest
import time
import json
from redis.asyncio import Redis
from app.infrastructure.config import settings
from app.infrastructure.game.redis_outbox import RedisOutboxService
from app.application.game.schemas import GameEventSchema

def get_local_redis():
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=settings.REDIS_DB
    )

@pytest.mark.asyncio
async def test_redis_outbox_service():
    local_redis = get_local_redis()
    try:
        service = RedisOutboxService(local_redis)
        room_id = "room_test_outbox_abc"
        
        # 清理
        await local_redis.delete(service._room_key(room_id))
        await local_redis.delete(service._commands_key(room_id))
        await local_redis.delete(service._outbox_key(room_id))
        
        # 构造事件
        event = GameEventSchema(
            event_id="evt_test_100",
            event="test_event",
            room_id=room_id,
            room_version=1,
            target_player_id="player_1",
            target_connection_epoch=1,
            payload={"data": "hello"},
            created_at=time.time(),
            trace_id="trace_outbox_test"
        )
        
        # 1. 初始化信封写入
        envelope = {
            "room_id": room_id,
            "room_version": 1,
            "owner_instance_id": "inst_1",
            "fencing_token": 10,
            "state": {"room_id": room_id, "score": 10}
        }
        
        res = await service.save_events_with_envelope(
            room_id=room_id,
            events=[event],
            envelope_json=json.dumps(envelope),
            fencing_token=10,
            old_version=0,
            owner_id="inst_1",
            command_id="cmd_first"
        )
        assert res == 1
        
        # 2. 验证快照及 Outbox 存入成功
        data = await local_redis.get(service._room_key(room_id))
        parsed = json.loads(data)
        assert parsed["room_version"] == 1
        assert parsed["state"]["score"] == 10
        
        pending = await service.get_pending_events(room_id)
        assert len(pending) == 1
        assert pending[0].event_id == "evt_test_100"
        
        # 3. 验证命令去重
        res_dup = await service.save_events_with_envelope(
            room_id=room_id,
            events=[],
            envelope_json=json.dumps(envelope),
            fencing_token=10,
            old_version=1,
            owner_id="inst_1",
            command_id="cmd_first"
        )
        assert res_dup == -3
        
        # 4. 验证版本 CAS 拦截
        res_cas = await service.save_events_with_envelope(
            room_id=room_id,
            events=[],
            envelope_json=json.dumps(envelope),
            fencing_token=10,
            old_version=0,
            owner_id="inst_1",
            command_id="cmd_second"
        )
        assert res_cas == -2
        
        # 5. 验证 fencing token 拦截
        res_fence = await service.save_events_with_envelope(
            room_id=room_id,
            events=[],
            envelope_json=json.dumps(envelope),
            fencing_token=5,
            old_version=1,
            owner_id="inst_1",
            command_id="cmd_second"
        )
        assert res_fence == -1
        
        # 6. 确认并清除事件
        await service.acknowledge_event(room_id, "evt_test_100")
        pending = await service.get_pending_events(room_id)
        assert len(pending) == 0
        
        # 清理
        await local_redis.delete(service._room_key(room_id))
        await local_redis.delete(service._commands_key(room_id))
        await local_redis.delete(service._outbox_key(room_id))
    finally:
        await local_redis.close()
