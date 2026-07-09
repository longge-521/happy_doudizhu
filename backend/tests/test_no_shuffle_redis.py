# backend/tests/test_no_shuffle_redis.py
import pytest
from unittest.mock import AsyncMock, patch
from app.infrastructure.redis_game_repository import RedisGameRepository

@pytest.mark.asyncio
async def test_match_queue_key_isolation():
    mock_redis = AsyncMock()
    repo = RedisGameRepository(mock_redis)
    
    # 传入 play_mode 并验证 key 变化
    with patch.object(repo, "_redis") as mock_r:
        await repo.add_to_match_queue("p1", base_score=20, play_mode="no_shuffle")
        # 验证 rpush 写入的队列键名格式为：game:match_queue:no_shuffle:20
        mock_r.rpush.assert_called_once_with("game:match_queue:no_shuffle:20", "p1")

@pytest.mark.asyncio
async def test_push_and_pop_deck_pool():
    mock_redis = AsyncMock()
    repo = RedisGameRepository(mock_redis)
    
    # 模拟 pop 返回数据
    import json
    mock_redis.lpop.return_value = json.dumps(list(range(54))).encode("utf-8")
    
    deck = await repo.pop_no_shuffle_deck()
    assert deck == list(range(54))
    mock_redis.lpop.assert_called_once_with("game:noshuffle:deck_pool")
    
    # 测试 push
    await repo.push_no_shuffle_deck(list(range(54)))
    mock_redis.rpush.assert_called_once()
    # 限制长度为100叠牌，修剪老数据
    mock_redis.ltrim.assert_called_once_with("game:noshuffle:deck_pool", -100, -1)
