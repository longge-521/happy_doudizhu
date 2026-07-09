import pytest
import asyncio
from app.infrastructure.config import settings

@pytest.fixture(autouse=True)
def setup_test_settings(monkeypatch):
    """
    全局测试配置：
    1. 在所有单元测试运行期间，默认将 API_TOKEN 重置为空，隔离开发者本地 .env 的干扰。
    2. 测试完成后自动清理 Redis 里产生的临时测试数据（如房间、信箱、命令去重、连接代次等）。
    """
    monkeypatch.setattr(settings, "API_TOKEN", "")
    
    yield
    
    # Teardown：清空本用例运行时在 Redis 中留下的脏数据，保持 Redis 绝对洁净
    try:
        from app.infrastructure.redis_client import redis_client
        async def clear_redis_test_keys():
            keys = await redis_client.keys("game:*")
            if keys:
                # 过滤并保留分布式长生存的 shard_owner 与 instance 状态，只清理对局临时数据
                keys_to_del = [k for k in keys if b"shard_owner" not in k and b"instance" not in k]
                if keys_to_del:
                    await redis_client.delete(*keys_to_del)
                    
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(clear_redis_test_keys())
    except Exception:
        pass
