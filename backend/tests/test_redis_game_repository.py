# backend/tests/test_redis_game_repository.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.infrastructure.redis_game_repository import RedisGameRepository
from app.domain.game.room import GameRoom, Player


@pytest.fixture
def mock_redis():
    """创建 mock Redis 客户端"""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.rpush = AsyncMock()
    redis.lrem = AsyncMock()
    redis.llen = AsyncMock(return_value=0)
    redis.expire = AsyncMock()
    return redis


@pytest.fixture
def repo(mock_redis):
    return RedisGameRepository(mock_redis)


@pytest.fixture
def sample_room():
    players = [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="机器人", is_ai=True, is_online=True),
    ]
    room = GameRoom.create("room_test", players)
    room.deal()
    return room


class TestRedisGameRepository:

    @pytest.mark.asyncio
    async def test_save_and_get_room(self, repo, mock_redis, sample_room):
        """保存房间后应能正确读取"""
        await repo.save_room(sample_room)
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "game:room:room_test" in str(call_args)

    @pytest.mark.asyncio
    async def test_set_player_room(self, repo, mock_redis):
        """设置玩家-房间映射"""
        await repo.set_player_room("p1", "room_test")
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_to_match_queue(self, repo, mock_redis):
        """加入匹配队列"""
        await repo.add_to_match_queue("p1")
        mock_redis.lrem.assert_called_once_with("game:match_queue:10", 0, "p1")
        mock_redis.rpush.assert_called_once_with("game:match_queue:10", "p1")

    @pytest.mark.asyncio
    async def test_add_to_match_queue_deduplicates_player_before_append(self, repo, mock_redis):
        await repo.add_to_match_queue("p1", base_score=80)
        mock_redis.lrem.assert_called_once_with("game:match_queue:80", 0, "p1")
        mock_redis.rpush.assert_called_once_with("game:match_queue:80", "p1")

    @pytest.mark.asyncio
    async def test_remove_from_match_queue(self, repo, mock_redis):
        """从匹配队列移除"""
        await repo.remove_from_match_queue("p1")
        mock_redis.lrem.assert_called_once_with("game:match_queue:10", 1, "p1")
