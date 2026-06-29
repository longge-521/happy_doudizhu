# backend/tests/test_game_app_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GameRoom, Player, GamePhase


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.get_player_room = AsyncMock(return_value=None)
    repo.get_match_queue_length = AsyncMock(return_value=0)
    repo.add_to_match_queue = AsyncMock()
    repo.remove_from_match_queue = AsyncMock()
    repo.set_player_room = AsyncMock()
    repo.save_room = AsyncMock()
    repo.get_room = AsyncMock(return_value=None)
    repo.pop_match_players = AsyncMock(return_value=[])
    repo.delete_room = AsyncMock()
    repo.remove_player_room = AsyncMock()
    return repo


@pytest.fixture
def service(mock_repo):
    return GameAppService(mock_repo)


class TestGameAppService:

    @pytest.mark.asyncio
    async def test_join_match_adds_to_queue(self, service, mock_repo):
        """加入匹配应添加到队列"""
        mock_repo.pop_match_players.return_value = ["p1"]  # 不够3人
        result = await service.join_match("p1", "玩家1", auto_ai=False)
        mock_repo.add_to_match_queue.assert_called_once_with("p1", base_score=10)

    @pytest.mark.asyncio
    async def test_join_match_already_in_room(self, service, mock_repo):
        """已在房间中的玩家不能再匹配"""
        mock_repo.get_player_room.return_value = "room_existing"
        result = await service.join_match("p1", "玩家1")
        assert result.get("error") is not None

    @pytest.mark.asyncio
    async def test_cancel_match(self, service, mock_repo):
        """取消匹配应从队列移除"""
        from unittest.mock import call
        result = await service.cancel_match("p1")
        expected_calls = [call("p1", base_score=bs) for bs in [10, 20, 80, 300, 900, 2700, 6000]]
        mock_repo.remove_from_match_queue.assert_has_calls(expected_calls, any_order=False)
        assert mock_repo.remove_from_match_queue.call_count == 7

    @pytest.mark.asyncio
    async def test_match_ai_for_player_pulls_others(self, service, mock_repo):
        """match_ai_for_player 应该把队列里的其他等待玩家也一并拉入"""
        mock_repo.get_player_room.return_value = None
        mock_repo.remove_from_match_queue.return_value = 1
        
        # 模拟队列里还有另外一个真人 p2
        mock_repo.pop_match_players.return_value = ["p2"]
        
        # 拦截 fill_with_ai 看看传入的参数是否包含 A 和 B 两个人
        with patch.object(service, 'fill_with_ai', AsyncMock(return_value={"status": "room_created"})) as mock_fill:
            result = await service.match_ai_for_player("p1", "玩家1", base_score=10)
            mock_fill.assert_called_once_with(["p1", "p2"], base_score=10)
            assert result == {"status": "room_created"}
