import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock

import pytest


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


_install_torch_stub()

from app.domain.game.room import GameRoom, Player
from app.interfaces.websocket.game_handler import GameWebSocketHandler


class FakeManager:
    def __init__(self):
        self.connections = {"p1": object(), "p2": object(), "p3": object()}
        self.sent = []

    async def send_to_player(self, player_id, data):
        self.sent.append((player_id, data))


class FakeService:
    def __init__(self, room):
        self.room = room

    async def _get_player_room(self, player_id):
        if player_id in {p.id for p in self.room.players}:
            return self.room
        return None


def make_handler(player_id="p1"):
    players = [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="玩家3", is_ai=False, is_online=True),
    ]
    room = GameRoom.create("room_voice", players)
    manager = FakeManager()
    service = FakeService(room)
    handler = GameWebSocketHandler(AsyncMock(), player_id, manager, service)
    return handler, manager


@pytest.mark.asyncio
async def test_voice_state_broadcasts_to_room_players():
    handler, manager = make_handler("p1")

    await handler._handle_message(json.dumps({"action": "voice_state", "enabled": True}))

    recipients = [player_id for player_id, _ in manager.sent]
    assert recipients == ["p1", "p2", "p3"]
    assert all(data["event"] == "voice_state" for _, data in manager.sent)
    assert all(data["player"] == "p1" for _, data in manager.sent)
    assert all(data["enabled"] is True for _, data in manager.sent)
    assert all("room_state" in data for _, data in manager.sent)


@pytest.mark.asyncio
async def test_voice_signal_forwards_only_to_target_room_player():
    handler, manager = make_handler("p1")
    payload = {"type": "offer", "sdp": "v=0"}

    await handler._handle_message(
        json.dumps(
            {
                "action": "voice_signal",
                "target_player": "p2",
                "signal_type": "offer",
                "payload": payload,
            }
        )
    )

    assert len(manager.sent) == 1
    target, data = manager.sent[0]
    assert target == "p2"
    assert data == {
        "event": "voice_signal",
        "player": "p1",
        "target_player": "p2",
        "signal_type": "offer",
        "payload": payload,
    }


@pytest.mark.asyncio
async def test_voice_signal_rejects_non_room_target():
    handler, manager = make_handler("p1")

    await handler._handle_message(
        json.dumps(
            {
                "action": "voice_signal",
                "target_player": "outside",
                "signal_type": "offer",
                "payload": {"type": "offer", "sdp": "v=0"},
            }
        )
    )

    assert manager.sent == [("p1", {"event": "error", "msg": "语音信令目标不在当前房间"})]


@pytest.mark.asyncio
async def test_voice_signal_rejects_invalid_type_and_large_payload():
    handler, manager = make_handler("p1")

    await handler._handle_message(
        json.dumps(
            {
                "action": "voice_signal",
                "target_player": "p2",
                "signal_type": "bad",
                "payload": {"type": "offer", "sdp": "v=0"},
            }
        )
    )

    large_payload = {"candidate": "x" * (16 * 1024)}
    await handler._handle_message(
        json.dumps(
            {
                "action": "voice_signal",
                "target_player": "p2",
                "signal_type": "ice_candidate",
                "payload": large_payload,
            }
        )
    )

    assert manager.sent[0] == ("p1", {"event": "error", "msg": "不支持的语音信令类型"})
    assert manager.sent[1] == ("p1", {"event": "error", "msg": "语音信令内容过大"})
