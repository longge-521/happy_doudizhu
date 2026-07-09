import pytest
from unittest.mock import AsyncMock

from app.infrastructure.redis_game_repository import RedisGameRepository


@pytest.mark.asyncio
async def test_redis_game_repository_pop_match_players_strict_3():
    # 测试在 count == 3（3人开局）时，必须达到 3 人才弹出的严格机制
    
    # 模拟 redis 实例
    redis_mock = AsyncMock()
    repo = RedisGameRepository(redis_mock)
    
    # 1. 模拟 Redis 长度少于 3 (实际只有 2 个人)
    # POP_MATCH_PLAYERS_SCRIPT 执行结果应该是空的 table/list
    redis_mock.eval.return_value = []
    
    res = await repo.pop_match_players(count=3, base_score=10)
    assert res == []
    
    # 验证传入的参数是 3
    redis_mock.eval.assert_called_once()
    args, kwargs = redis_mock.eval.call_args
    assert args[3] == 3
    
    # 2. 模拟 Redis 长度充足 (有 3 个人)
    redis_mock.eval.reset_mock()
    redis_mock.eval.return_value = [b"player1", b"player2", b"player3"]
    
    res = await repo.pop_match_players(count=3, base_score=10)
    assert res == ["player1", "player2", "player3"]


@pytest.mark.asyncio
async def test_redis_game_repository_pop_match_players_flexible_less_than_3():
    # 测试在 count < 3 时，有多少弹多少的柔性捎带机制
    redis_mock = AsyncMock()
    repo = RedisGameRepository(redis_mock)
    
    redis_mock.eval.return_value = [b"player_single"]
    
    res = await repo.pop_match_players(count=2, base_score=10)
    assert res == ["player_single"]
    
    redis_mock.eval.assert_called_once()
    args, _ = redis_mock.eval.call_args
    assert args[3] == 2
