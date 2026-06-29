import pytest
from unittest.mock import AsyncMock, patch
from app.infrastructure.redis_client import is_query_debounced, redis_client
from redis.exceptions import ConnectionError

@pytest.mark.asyncio
async def test_redis_debounce_success_flow():
    # 模拟第一次写入成功（返回 True，即 key 不存在）
    # 模拟第二次写入失败（返回 None/False，即 key 已存在）
    with patch.object(redis_client, 'set', new_callable=AsyncMock) as mock_set, \
         patch.object(redis_client, 'expire', new_callable=AsyncMock) as mock_expire:
        mock_set.side_effect = [True, None]
        
        test_key = "hmp:test:debounce:user:action"
        
        # 第一次请求：应该返回 False（不防抖）
        res1 = await is_query_debounced(test_key, expire_seconds=3)
        assert res1 is False
        mock_expire.assert_not_called()
        
        # 第二次请求：应该返回 True（防抖过滤）
        res2 = await is_query_debounced(test_key, expire_seconds=3)
        assert res2 is True
        
        assert mock_set.call_count == 2
        # 第二次请求触发防抖：必须调用 expire 顺延时间
        mock_expire.assert_called_once_with(test_key, 3)

@pytest.mark.asyncio
async def test_redis_debounce_degrade_flow():
    # 模拟 Redis 连接失败，抛出异常
    with patch.object(redis_client, 'set', new_callable=AsyncMock) as mock_set:
        mock_set.side_effect = ConnectionError("Connection refused")
        
        test_key = "hmp:test:debounce:user:action"
        
        # 应该优雅降级返回 False（不防抖）
        res = await is_query_debounced(test_key, expire_seconds=3)
        assert res is False
