import pytest
import time
import asyncio
from redis.asyncio import Redis
from app.infrastructure.config import settings
from app.infrastructure.game.redis_lease import RedisLeaseManager

def get_local_redis():
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        db=settings.REDIS_DB
    )

@pytest.mark.asyncio
async def test_redis_lease_manager():
    local_redis = get_local_redis()
    try:
        manager = RedisLeaseManager(local_redis)
        shard_id = 9
        instance_a = "inst_test_a"
        instance_b = "inst_test_b"
        
        # 清理
        await local_redis.delete(manager._shard_key(shard_id))
        
        # 1. 尝试抢占
        token = await manager.acquire_shard_lease(shard_id, instance_a)
        assert token is not None
        assert token > 0
        
        # 2. 别人抢占应该失败
        token_b = await manager.acquire_shard_lease(shard_id, instance_b)
        assert token_b is None
        
        # 3. 续约
        renewed = await manager.renew_shard_lease(shard_id, instance_a, token)
        assert renewed is True
        
        # 4. 用错误的 token 续约应该失败
        renewed = await manager.renew_shard_lease(shard_id, instance_a, 9999)
        assert renewed is False
        
        # 5. 房间租约锁定
        room_locked = await manager.acquire_room_lease("room_test_9", shard_id, token)
        assert room_locked is True
        
        # 清理
        await local_redis.delete(manager._shard_key(shard_id))
        await local_redis.delete(manager._room_key("room_test_9"))
    finally:
        await local_redis.aclose()
