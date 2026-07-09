import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.domain.game.room import GameRoom, Player, GamePhase
from app.application.game.schemas import GameCommandSchema, ScheduledTaskSchema
from app.infrastructure.game.memory_adapters import MemoryMessageBus
from main import dispatch_game_command

@pytest.fixture
def mock_app():
    app = MagicMock()
    app.state.game_message_bus = MemoryMessageBus()
    app.state.presence_service = MagicMock()
    app.state.presence_service.get_presence = AsyncMock(return_value=None)
    app.state.game_repository = MagicMock()
    app.state.game_service = MagicMock()
    app.state.game_service.cleanup_room = AsyncMock()
    app.state.game_service._repo = app.state.game_repository
    app.state.game_settlement_service = MagicMock()
    return app

@pytest.mark.asyncio
async def test_dispatch_command_publishes_settlement_task(mock_app):
    # 测试游戏结束后，dispatch_game_command 动作能够发布结算任务到可靠结算队列，而不是同步处理
    bus = mock_app.state.game_message_bus
    repo = mock_app.state.game_repository
    
    # 模拟房间快照
    room = GameRoom.create("test_settle_room_1", [
        Player(id="p1", nickname="玩家1"),
        Player(id="p2", nickname="玩家2"),
        Player(id="ai_bot_1", nickname="机器人", is_ai=True)
    ])
    room.phase = GamePhase.PLAYING
    
    # 使用 AsyncMock 模拟 get_room
    repo.get_room = AsyncMock(return_value=room)
    repo.save_room = AsyncMock()
    
    # 叫地主和发牌状态设定
    room.landlord = "p1"
    
    # 记录结算回调触发次数
    received = []
    async def cb(room_id, payload):
        received.append((room_id, payload))
        
    await bus.subscribe_settlement_tasks(cb)
    
    # 构造能够触发 game_over 结果 of 动作命令
    # 这里模拟 play_cards 动作
    command = GameCommandSchema(
        command_id="cmd-12345",
        action="play_cards",
        room_id="test_settle_room_1",
        player_id="p1",
        connection_epoch=1,
        payload={"cards": [3, 3, 3, 3]}, # 炸弹打完手牌变空
        created_at=12345.0,
        trace_id="trace-123",
        source_instance_id="inst-1"
    )
    
    # 模拟房间的动作处理，使其直接返回 game_over，补齐所有序列化必需的字段
    mock_result = {
        "success": True, 
        "game_over": True, 
        "winner": "p1", 
        "winner_side": "landlord", 
        "multiplier": 2, 
        "all_hands": {"p1": [], "p2": [3, 4], "ai_bot_1": [5]},
        "scores": {"p1": 100, "p2": -100}
    }
    with patch.object(room, "play_cards", return_value=mock_result):
        await dispatch_game_command(mock_app, command)
        
    # 验证是否写入了 Redis 保存
    repo.save_room.assert_awaited_once_with(room)
    
    # 异步等待一下内存消息总线的模拟投递
    await asyncio.sleep(0.1)
    
    # 验证可靠队列已接收到结算任务，且同步路径没有被执行（cleanup_room 必须是由结算回调消费者调起的，在这里未被触发）
    assert len(received) == 1
    assert received[0][0] == "test_settle_room_1"
    assert received[0][1]["game_over"] is True

@pytest.mark.asyncio
async def test_scheduler_poller_intercepts_match_ai():
    # 测试 scheduler_poller 扫描时，如果是 match_ai 大厅级延迟任务，直接在 poller 侧执行，不发往分片
    from main import scheduler_poller
    import time
    
    app_mock = MagicMock()
    app_mock.state.game_message_bus = AsyncMock()
    app_mock.state.game_service = MagicMock()
    app_mock.state.game_service.match_ai_for_player = AsyncMock()
    
    task = ScheduledTaskSchema(
        task_id="ai-match-p1",
        due_at=time.time() - 1, # 已经到期
        room_id="match-p1",
        task_type="match_ai",
        expected_room_version=0,
        created_at=time.time() - 5,
        payload={"player_id": "p1", "nickname": "玩家1", "base_score": 10}
    )
    
    # 使用 AsyncMock 模拟 eval，保证 await redis_client.eval 返回包含任务序列化的 list
    mock_eval = AsyncMock(return_value=[task.model_dump_json().encode("utf-8")])
    
    with patch("app.infrastructure.redis_client.redis_client.eval", new=mock_eval):
        # 运行 poller
        poller_task = asyncio.create_task(scheduler_poller(app_mock))
        await asyncio.sleep(0.2)
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass
            
    # 确认是否直接调用了 match_ai_for_player
    app_mock.state.game_service.match_ai_for_player.assert_awaited_once_with("p1", "玩家1", 10)
    # 确认没有通过 MQ 往 Shard 队列发命令
    app_mock.state.game_message_bus.publish_command.assert_not_called()
