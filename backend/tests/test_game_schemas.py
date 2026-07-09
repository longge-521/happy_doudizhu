import time
from app.application.game.schemas import GameCommandSchema, GameEventSchema, ScheduledTaskSchema

def test_game_command_schema():
    payload = {"nickname": "Tester", "base_score": 80}
    cmd = GameCommandSchema(
        command_id="cmd-123",
        action="join_match",
        room_id="room-456",
        player_id="player-789",
        connection_epoch=2,
        payload=payload,
        created_at=time.time(),
        trace_id="trace-abc",
        source_instance_id="inst-xyz"
    )
    assert cmd.command_id == "cmd-123"
    assert cmd.payload["nickname"] == "Tester"
    assert cmd.schema_version == "1.0"

def test_game_event_schema():
    event = GameEventSchema(
        event_id="evt-123",
        event="cards_played",
        room_id="room-456",
        room_version=10,
        target_player_id="player-789",
        target_connection_epoch=2,
        payload={"cards": [3, 4, 5]},
        created_at=time.time(),
        trace_id="trace-abc"
    )
    assert event.event_id == "evt-123"
    assert event.room_version == 10
    assert event.payload["cards"] == [3, 4, 5]

def test_scheduled_task_schema():
    task = ScheduledTaskSchema(
        task_id="task-123",
        due_at=time.time() + 10,
        room_id="room-456",
        task_type="ai_thinking",
        expected_room_version=5,
        payload={"bot_id": "ai_1"},
        created_at=time.time()
    )
    assert task.task_id == "task-123"
    assert task.task_type == "ai_thinking"
    assert task.expected_room_version == 5
