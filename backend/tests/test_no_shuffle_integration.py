# backend/tests/test_no_shuffle_integration.py
import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GameRoom, Player, GamePhase

@pytest.mark.asyncio
async def test_join_match_and_deal_from_pool():
    mock_repo = AsyncMock()
    service = GameAppService(mock_repo)
    
    # 模拟不洗牌池有一叠牌
    mock_repo.get_player_room.return_value = None
    mock_repo.get_match_queue_length.return_value = 3
    mock_repo.pop_match_players.return_value = ["p1", "p2", "p3"]
    mock_repo.pop_no_shuffle_deck.return_value = list(range(54))
    mock_repo.get_match_player_meta = AsyncMock(return_value=None)
    mock_repo.delete_match_player_meta = AsyncMock()
    
    # 拦截开局 Outbox 注入
    with patch("app.infrastructure.config.settings.DISTRIBUTED_MODE", False):
        result = await service.join_match("p1", "玩家1", auto_ai=True, base_score=20, play_mode="no_shuffle")
        
        # 验证正确弹出了不洗牌历史牌堆
        mock_repo.pop_no_shuffle_deck.assert_called_once()
        assert "room_id" in result


@pytest.mark.asyncio
async def test_play_cards_and_recycle_to_pool():
    mock_repo = AsyncMock()
    service = GameAppService(mock_repo)
    
    # 模拟房间
    room = GameRoom.create(
        "room_recycle_test",
        [
            Player(id="p1", nickname="玩家1", is_ai=False),
            Player(id="p2", nickname="玩家2", is_ai=False),
            Player(id="p3", nickname="玩家3", is_ai=False),
        ],
        base_score=20
    )
    room.play_mode = "no_shuffle"
    room.phase = GamePhase.PLAYING
    room.landlord_id = "p1"
    room.current_turn = "p1"
    # 给 p1 仅留一张 3 (10)，方便一步走完
    room.hands["p1"] = [10]
    room.hands["p2"] = [11, 12, 13]
    room.hands["p3"] = [14, 15, 16]
    room.landlord_cards = [17, 18, 19]
    
    mock_repo.get_room.return_value = room
    mock_repo.save_room.return_value = None
    mock_repo.push_no_shuffle_deck = AsyncMock()
    
    # 拦截分布式事务
    with patch("app.infrastructure.config.settings.DISTRIBUTED_MODE", False):
        # p1 出最后一张 3 (10)
        result = await service.handle_play("p1", [10])
        
        # 验证回收牌是否正常被推入 Redis
        mock_repo.push_no_shuffle_deck.assert_called_once()
        recycled_deck = mock_repo.push_no_shuffle_deck.call_args[0][0]
        # 回收的扑克牌张数应当是 54 张
        assert len(recycled_deck) == 54
        assert result.get("game_over") is True
