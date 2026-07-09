import json
import logging
from app.domain.game.interfaces import ISchedulerService
from app.application.game.schemas import ScheduledTaskSchema
from app.infrastructure.redis_client import redis_client

logger = logging.getLogger("happy_doudizhu")

class RedisSchedulerService(ISchedulerService):
    """基于 Redis ZSET + HASH 的分布式高可用延迟任务调度服务。"""

    def __init__(self, client=None):
        self._redis = client or redis_client
        self._zset_key = "game:scheduler:tasks"
        self._hash_key = "game:scheduler:task_details"

    async def schedule_task(self, task: ScheduledTaskSchema) -> None:
        try:
            # 1. 存入 HASH 详情
            await self._redis.hset(self._hash_key, task.task_id, task.model_dump_json())
            # 2. 存入 ZSET 到期索引
            await self._redis.zadd(self._zset_key, {task.task_id: task.due_at})
        except Exception as e:
            logger.error(f"[RedisSchedulerService] Failed to schedule task {task.task_id}: {e}")

    async def cancel_task(self, task_id: str) -> None:
        try:
            await self._redis.hdel(self._hash_key, task_id)
            await self._redis.zrem(self._zset_key, task_id)
        except Exception as e:
            logger.error(f"[RedisSchedulerService] Failed to cancel task {task_id}: {e}")
