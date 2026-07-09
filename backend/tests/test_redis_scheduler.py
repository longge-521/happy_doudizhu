import pytest
import time
from redis.asyncio import Redis
from app.infrastructure.config import settings
from app.infrastructure.game.redis_scheduler import RedisSchedulerService
from app.application.game.schemas import ScheduledTaskSchema

def get_local_redis():
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=settings.REDIS_DB
    )

@pytest.mark.asyncio
async def test_redis_scheduler_service():
    local_redis = get_local_redis()
    try:
        service = RedisSchedulerService(local_redis)
        
        # 清理
        await local_redis.delete(service._zset_key)
        await local_redis.delete(service._hash_key)
        
        # 1. 构造一个延时任务，补齐 Pydantic 必填字段
        task = ScheduledTaskSchema(
            task_id="task_test_delay_100",
            room_id="room_test_scheduler",
            task_type="test_action",
            due_at=time.time() + 10,
            expected_room_version=1,
            created_at=time.time(),
            payload={"action": "test"}
        )
        
        # 调度写入
        await service.schedule_task(task)
        
        # 验证写入
        zscore = await local_redis.zscore(service._zset_key, task.task_id)
        assert zscore == task.due_at
        
        hval = await local_redis.hget(service._hash_key, task.task_id)
        assert hval is not None
        
        # 2. 撤销任务
        await service.cancel_task(task.task_id)
        
        zscore = await local_redis.zscore(service._zset_key, task.task_id)
        assert zscore is None
        hval = await local_redis.hget(service._hash_key, task.task_id)
        assert hval is None
    finally:
        await local_redis.aclose()

@pytest.mark.asyncio
async def test_lua_scheduler_polling():
    local_redis = get_local_redis()
    try:
        service = RedisSchedulerService(local_redis)
        
        # 清理
        await local_redis.delete(service._zset_key)
        await local_redis.delete(service._hash_key)
        
        now = time.time()
        
        # 写入一个已过期任务 (due_at = now - 5)
        task_expired = ScheduledTaskSchema(
            task_id="task_expired_1",
            room_id="room_test_scheduler",
            task_type="action_expired",
            due_at=now - 5,
            expected_room_version=1,
            created_at=now - 10,
            payload={}
        )
        # 写入一个未过期任务 (due_at = now + 50)
        task_pending = ScheduledTaskSchema(
            task_id="task_pending_2",
            room_id="room_test_scheduler",
            task_type="action_pending",
            due_at=now + 50,
            expected_room_version=1,
            created_at=now - 1,
            payload={}
        )
        
        await service.schedule_task(task_expired)
        await service.schedule_task(task_pending)
        
        # 运行 Lua 扫表脚本
        lua_script = """
        local zset_key = KEYS[1]
        local hash_key = KEYS[2]
        local now = tonumber(ARGV[1])
        
        local tids = redis.call('zrangebyscore', zset_key, 0, now)
        local results = {}
        if #tids > 0 then
            for _, tid in ipairs(tids) do
                local detail = redis.call('hget', hash_key, tid)
                if detail then
                    table.insert(results, detail)
                    redis.call('hdel', hash_key, tid)
                end
            end
            redis.call('zremrangebyscore', zset_key, 0, now)
        end
        return results
        """
        
        results = await local_redis.eval(lua_script, 2, service._zset_key, service._hash_key, now)
        assert len(results) == 1
        
        parsed = ScheduledTaskSchema.model_validate_json(results[0])
        assert parsed.task_id == "task_expired_1"
        assert parsed.task_type == "action_expired"
        
        # 验证未过期的任务依然存留在 Redis 中
        zscore = await local_redis.zscore(service._zset_key, "task_pending_2")
        assert zscore is not None
        
        # 清理
        await local_redis.delete(service._zset_key)
        await local_redis.delete(service._hash_key)
    finally:
        await local_redis.aclose()
