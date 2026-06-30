# backend/tests/test_game_app_service.py
import pytest
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch


def _install_torch_stub():
    if "torch" in sys.modules:
        return

    class _FakeModule:
        def __init__(self, *args, **kwargs):
            pass

        def eval(self):
            return self

        def load_state_dict(self, *args, **kwargs):
            return None

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    torch_module = ModuleType("torch")
    nn_module = ModuleType("torch.nn")
    functional_module = ModuleType("torch.nn.functional")

    nn_module.Module = _FakeModule
    nn_module.LSTM = _FakeModule
    nn_module.Linear = _FakeModule
    functional_module.relu = lambda x: x

    torch_module.nn = nn_module
    torch_module.cat = lambda tensors, dim=-1: tensors[0]
    torch_module.load = lambda *args, **kwargs: {}
    torch_module.no_grad = lambda: _NoGrad()
    torch_module.Tensor = object

    sys.modules["torch"] = torch_module
    sys.modules["torch.nn"] = nn_module
    sys.modules["torch.nn.functional"] = functional_module


def _install_douzero_adapter_stub():
    if "app.domain.game.douzero_adapter" in sys.modules:
        return

    adapter_module = ModuleType("app.domain.game.douzero_adapter")
    adapter_module.card_id_to_douzero = lambda card_id: card_id
    adapter_module.douzero_to_card_ids = lambda action, hand: list(action)
    adapter_module.get_obs_for_douzero = lambda *args, **kwargs: {}
    sys.modules["app.domain.game.douzero_adapter"] = adapter_module


_install_torch_stub()
_install_douzero_adapter_stub()

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


@pytest.mark.asyncio
async def test_ai_calls_landlord_with_strong_hand(service, mock_repo):
    """AI 手牌足够强时，叫地主阶段应主动叫地主。"""
    room = GameRoom.create(
        "room_ai_call",
        [
            Player(id="ai_bot_1", nickname="AI", is_ai=True),
            Player(id="p1", nickname="玩家1"),
            Player(id="p2", nickname="玩家2"),
        ],
    )
    room.phase = GamePhase.CALLING
    room.current_turn = "ai_bot_1"
    room.bottom_cards = [4, 5, 6]
    room.hands = {
        "ai_bot_1": [52, 53, 0, 1, 2, 3, 44, 45, 46, 47, 40, 41, 42, 43, 36, 37, 38],
        "p1": [7, 8, 9],
        "p2": [10, 11, 12],
    }

    with patch("app.application.game.game_app_service.asyncio.sleep", new_callable=AsyncMock):
        result = await service.handle_ai_turn(room)

    assert result["score"] > 0
    assert room.landlord == "ai_bot_1"
    assert room._first_bidder == "ai_bot_1"
    mock_repo.save_room.assert_awaited_once_with(room)


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
