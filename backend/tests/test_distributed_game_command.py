import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.game.game_app_service import GameAppService
from app.application.game.schemas import GameCommandSchema, ScheduledTaskSchema
from app.domain.game.room import GamePhase, GameRoom, Player
from app.infrastructure.game.context import current_outbox_events
from main import (
    _distributed_action_events,
    _schedule_distributed_follow_up,
    _scheduled_task_to_command,
    dispatch_game_command,
)


class RecordingRoomRepository:
    def __init__(self, room):
        self.room = room
        self.saved_events = []
        self.save_count = 0
        self.scheduled_tasks = []

    async def get_room(self, room_id):
        assert room_id == self.room.room_id
        return self.room

    async def get_player_room(self, player_id):
        raise AssertionError("分布式 Worker 不应通过玩家映射加载房间")

    async def save_room(self, room):
        self.save_count += 1
        self.saved_events = list(current_outbox_events.get() or [])
        room.envelope_version += 1

    async def cancel_game_task(self, task_id):
        return None

    async def schedule_game_task(self, task):
        self.scheduled_tasks.append(task)


def make_calling_room(current_turn="human"):
    room = GameRoom()
    room.room_id = "room-distributed-test"
    room.players = [
        Player(id="human", nickname="真人", is_ai=False),
        Player(id="ai-1", nickname="机器人1", is_ai=True),
        Player(id="ai-2", nickname="机器人2", is_ai=True),
    ]
    room.phase = GamePhase.CALLING
    room.current_turn = current_turn
    room.turn_deadline = 12345.0
    room.hands = {
        "human": list(range(17)),
        "ai-1": list(range(17, 34)),
        "ai-2": list(range(34, 51)),
    }
    room.envelope_version = 7
    room.envelope_fencing_token = 1
    room.envelope_owner = "old-owner"
    return room


def make_command(action, player_id, payload=None):
    return GameCommandSchema(
        command_id=f"cmd-{action}-{player_id}",
        action=action,
        room_id="room-distributed-test",
        player_id=player_id,
        connection_epoch=1,
        payload=payload or {},
        created_at=time.time(),
        trace_id=f"trace-{action}",
        source_instance_id="gateway-1",
    )


def make_app(service):
    return SimpleNamespace(
        state=SimpleNamespace(
            game_service=service,
            lease_manager=SimpleNamespace(),
            my_held_shards={i: 100 + i for i in range(16)},
            presence_service=SimpleNamespace(
                get_presence=AsyncMock(
                    return_value={"instance_id": "gateway-1", "connection_epoch": 1}
                )
            ),
        )
    )


@pytest.mark.asyncio
async def test_worker_loads_timeout_room_by_room_id_and_emits_player_view_event(monkeypatch):
    room = make_calling_room(current_turn="human")
    repo = RecordingRoomRepository(room)
    service = GameAppService(repo)
    app = make_app(service)
    monkeypatch.setattr(
        "app.infrastructure.config.settings.DISTRIBUTED_MODE", True
    )
    monkeypatch.setattr(
        "app.infrastructure.config.settings.INSTANCE_ID", "worker-1"
    )

    command = make_command(
        "skip_call",
        "human",
        {"expected_room_version": 7, "scheduled": True},
    )

    await dispatch_game_command(app, command)

    assert repo.save_count == 1
    assert repo.saved_events
    assert {event.event for event in repo.saved_events} == {"call_skipped"}
    human_event = next(
        event for event in repo.saved_events if event.target_player_id == "human"
    )
    room_state = human_event.payload["room_state"]
    assert next(player for player in room_state["players"] if player["id"] == "human")[
        "is_self"
    ]
    assert room_state["hand"] == room.get_player_view("human")["hand"]


@pytest.mark.asyncio
async def test_ai_command_commits_once_and_schedules_next_ai_as_new_task(monkeypatch):
    room = make_calling_room(current_turn="ai-1")
    repo = RecordingRoomRepository(room)

    class FakeGameService:
        def __init__(self):
            self._repo = repo
            self.ai_calls = 0

        async def _get_player_room(self, player_id):
            raise AssertionError("分布式 Worker 不应通过玩家映射加载房间")

        async def handle_ai_turn(self, target_room, *, persist=True, thinking_delay=True):
            self.ai_calls += 1
            assert persist is False
            assert thinking_delay is False
            target_room.current_turn = "ai-2"
            return {
                "success": True,
                "room": target_room,
                "ai_player": "ai-1",
                "score": 0,
            }

    service = FakeGameService()
    app = make_app(service)
    monkeypatch.setattr(
        "app.infrastructure.config.settings.DISTRIBUTED_MODE", True
    )
    monkeypatch.setattr(
        "app.infrastructure.config.settings.INSTANCE_ID", "worker-1"
    )

    await dispatch_game_command(app, make_command("trigger_ai", "ai-1"))

    assert service.ai_calls == 1
    assert repo.save_count == 1
    assert len(repo.scheduled_tasks) == 1
    next_task = repo.scheduled_tasks[0]
    assert next_task.task_type == "trigger_ai"
    assert next_task.payload["player_id"] == "ai-2"
    assert next_task.payload["expected_turn_deadline"] == 12345.0
    assert next_task.expected_room_version == 8


@pytest.mark.asyncio
async def test_stale_ai_task_still_runs_when_same_ai_owns_the_turn(monkeypatch):
    room = make_calling_room(current_turn="ai-1")
    room.envelope_version = 9
    repo = RecordingRoomRepository(room)

    class FakeGameService:
        def __init__(self):
            self._repo = repo
            self.ai_calls = 0

        async def handle_ai_turn(self, target_room, *, persist=True, thinking_delay=True):
            self.ai_calls += 1
            target_room.current_turn = "human"
            return {
                "success": True,
                "room": target_room,
                "ai_player": "ai-1",
                "score": 0,
            }

    service = FakeGameService()
    app = make_app(service)
    monkeypatch.setattr(
        "app.infrastructure.config.settings.DISTRIBUTED_MODE", True
    )
    monkeypatch.setattr(
        "app.infrastructure.config.settings.INSTANCE_ID", "worker-1"
    )
    command = make_command(
        "trigger_ai",
        "ai-1",
        {
            "player_id": "ai-1",
            "expected_room_version": 8,
            "expected_turn_deadline": room.turn_deadline,
        },
    )

    await dispatch_game_command(app, command)

    assert service.ai_calls == 1
    assert repo.save_count == 1


@pytest.mark.asyncio
async def test_old_timeout_is_ignored_when_player_has_entered_a_new_turn(monkeypatch):
    room = make_calling_room(current_turn="human")
    room.envelope_version = 9
    room.turn_deadline = 200.0
    repo = RecordingRoomRepository(room)
    service = GameAppService(repo)
    app = make_app(service)
    monkeypatch.setattr(
        "app.infrastructure.config.settings.DISTRIBUTED_MODE", True
    )
    monkeypatch.setattr(
        "app.infrastructure.config.settings.INSTANCE_ID", "worker-1"
    )
    command = make_command(
        "skip_call",
        "human",
        {
            "player_id": "human",
            "expected_room_version": 8,
            "expected_turn_deadline": 100.0,
        },
    )

    await dispatch_game_command(app, command)

    assert repo.save_count == 0


@pytest.mark.asyncio
async def test_autoplay_player_gets_immediate_auto_play_task():
    room = make_calling_room(current_turn="human")
    room.phase = GamePhase.PLAYING
    room.envelope_version = 12
    room.turn_deadline = 300.0
    room.auto_play_players.add("human")
    repo = RecordingRoomRepository(room)

    await _schedule_distributed_follow_up(repo, room)

    assert len(repo.scheduled_tasks) == 1
    task = repo.scheduled_tasks[0]
    assert task.task_type == "trigger_auto_play"
    assert task.payload == {
        "player_id": "human",
        "expected_turn_deadline": 300.0,
    }


@pytest.mark.asyncio
async def test_distributed_game_over_settles_and_cleans_room(monkeypatch):
    room = make_calling_room(current_turn="ai-1")
    room.phase = GamePhase.PLAYING
    repo = RecordingRoomRepository(room)

    class FakeGameService:
        def __init__(self):
            self._repo = repo
            self.cleanup_room = AsyncMock()

        async def handle_ai_turn(self, target_room, *, persist=True, thinking_delay=True):
            target_room.phase = GamePhase.SETTLING
            target_room.hands["ai-1"] = []
            return {
                "success": True,
                "game_over": True,
                "winner": "ai-1",
                "winner_side": "farmer",
                "scores": {"human": -20, "ai-1": 10, "ai-2": 10},
                "multiplier": 1,
                "all_hands": target_room.hands,
            }

    service = FakeGameService()
    app = make_app(service)
    settlement_service = SimpleNamespace(settle=MagicMock(return_value="completed"))
    app.state.game_settlement_service = settlement_service
    monkeypatch.setattr(
        "app.infrastructure.config.settings.DISTRIBUTED_MODE", True
    )
    monkeypatch.setattr(
        "app.infrastructure.config.settings.INSTANCE_ID", "worker-1"
    )

    await dispatch_game_command(app, make_command("trigger_ai", "ai-1"))

    settlement_service.settle.assert_called_once()
    settled_room, settled_result = settlement_service.settle.call_args.args
    assert settled_room is room
    assert settled_result["game_over"] is True
    service.cleanup_room.assert_awaited_once_with(
        room.room_id,
        ["human", "ai-1", "ai-2"],
    )


def test_scheduler_command_keeps_target_player_and_expected_room_version():
    task = ScheduledTaskSchema(
        task_id="trigger_ai_room-distributed-test_ai-1_8",
        room_id="room-distributed-test",
        task_type="trigger_ai",
        due_at=time.time(),
        expected_room_version=8,
        created_at=time.time(),
        payload={"player_id": "ai-1"},
    )

    command = _scheduled_task_to_command(task)

    assert command.player_id == "ai-1"
    assert command.payload["expected_room_version"] == 8
    assert command.command_id == f"sched-{task.task_id}"


def test_game_over_event_does_not_require_cards_played_field():
    room = make_calling_room(current_turn="ai-1")
    room.phase = GamePhase.SETTLING
    result = {
        "success": True,
        "game_over": True,
        "winner": "ai-1",
        "winner_side": "farmer",
        "scores": {"human": -20, "ai-1": 10, "ai-2": 10},
        "multiplier": 1,
        "all_hands": room.hands,
    }

    events = _distributed_action_events(
        "trigger_ai",
        "ai-1",
        result,
        room,
        "PLAYING",
    )

    assert events == [
        {
            "event": "game_over",
            "winner": "ai-1",
            "winner_side": "farmer",
            "scores": result["scores"],
            "multiplier": 1,
            "all_hands": room.hands,
        }
    ]


def test_fifty_k_action_events_keep_play_settlement_game_over_order():
    room = make_calling_room(current_turn="human")
    room.phase = GamePhase.SETTLING
    result = {
        "success": True,
        "cards_played": [8, 28, 40],
        "card_type": "fifty_k_true",
        "remaining": 0,
        "trick_settlement_event": {
            "event": "trick_settled",
            "trick_no": 3,
            "winner_id": "human",
            "trick_cards": [8, 28, 40],
            "score_gained": 35,
            "bean_changes": {"human": 350, "ai-1": -175, "ai-2": -175},
            "bean_balances": {"human": 10350, "ai-1": 9825, "ai-2": 9825},
            "current_scores": {"human": 35, "ai-1": 0, "ai-2": 0},
        },
        "game_over": True,
        "winner": "human",
        "winner_side": "individual",
        "scores": {"human": 35, "ai-1": 0, "ai-2": 0},
        "multiplier": 1,
        "all_hands": room.hands,
        "fifty_k_settlement": {"winner_id": "human"},
    }

    events = _distributed_action_events(
        "play_cards", "human", result, room, "PLAYING"
    )

    assert [event["event"] for event in events] == [
        "cards_played",
        "trick_settled",
        "game_over",
    ]
    assert events[-1]["fifty_k_settlement"] == {"winner_id": "human"}


@pytest.mark.asyncio
async def test_distributed_human_play_uses_application_action_completer(monkeypatch):
    room = make_calling_room(current_turn="human")
    room.phase = GamePhase.PLAYING
    room.hands["human"] = [0, 1]
    repo = RecordingRoomRepository(room)
    service = GameAppService(repo)
    service.complete_action = MagicMock(side_effect=lambda target_room, result: result)
    app = make_app(service)
    monkeypatch.setattr("app.infrastructure.config.settings.DISTRIBUTED_MODE", True)
    monkeypatch.setattr("app.infrastructure.config.settings.INSTANCE_ID", "worker-1")

    await dispatch_game_command(
        app,
        make_command("play_cards", "human", {"cards": [0]}),
    )

    service.complete_action.assert_called_once()
    assert service.complete_action.call_args.args[0] is room
