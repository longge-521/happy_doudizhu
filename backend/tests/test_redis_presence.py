import pytest
import asyncio
from app.infrastructure.game.redis_presence import RedisPresenceService
from app.infrastructure.redis_client import redis_client

@pytest.mark.asyncio
async def test_redis_presence_service():
    service = RedisPresenceService(redis_client)
    player_id = "test_player_presence_123"
    
    # 清理已有环境
    await redis_client.delete(service._presence_key(player_id))
    await redis_client.delete(service._epoch_key(player_id))
    
    # 1. 测试初始状态
    presence = await service.get_presence(player_id)
    assert presence is None
    
    # 2. 测试自增 epoch
    epoch1 = await service.increment_epoch(player_id)
    assert epoch1 == 1
    epoch2 = await service.increment_epoch(player_id)
    assert epoch2 == 2
    
    # 3. 设置 presence
    await service.set_presence(player_id, "instance_test_a", epoch2)
    presence = await service.get_presence(player_id)
    assert presence is not None
    assert presence["instance_id"] == "instance_test_a"
    assert presence["connection_epoch"] == epoch2
    
    # 4. 删除 presence - epoch 不匹配时删除应该失败
    removed = await service.remove_presence(player_id, 999)
    assert removed is False
    presence = await service.get_presence(player_id)
    assert presence is not None
    
    # 5. 删除 presence - epoch 匹配时删除成功
    removed = await service.remove_presence(player_id, epoch2)
    assert removed is True
    presence = await service.get_presence(player_id)
    assert presence is None
    
    # 清理
    await redis_client.delete(service._presence_key(player_id))
    await redis_client.delete(service._epoch_key(player_id))
