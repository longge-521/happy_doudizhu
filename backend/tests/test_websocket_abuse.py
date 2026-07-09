import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from app.interfaces.websocket.game_handler import GameWebSocketHandler


@pytest.mark.asyncio
async def test_websocket_message_oversized():
    """测试 WebSocket 消息长度超过 32KB 拦截防御"""
    mock_ws = MagicMock()
    mock_manager = MagicMock()
    mock_service = MagicMock()
    
    # 模拟发送消息回调记录
    sent_messages = []
    async def mock_send(msg):
        sent_messages.append(msg)
        
    handler = GameWebSocketHandler(mock_ws, "player123", mock_manager, mock_service)
    handler._send = mock_send
    
    # 构建 33KB 的超长文本
    huge_text = "A" * (33 * 1024)
    await handler._handle_message(huge_text)
    
    assert len(sent_messages) == 1
    assert sent_messages[0]["event"] == "error"
    assert "请求消息过长" in sent_messages[0]["msg"]


@pytest.mark.asyncio
async def test_websocket_action_too_frequent():
    """测试同一连接两次动作间隔不得少于 100ms 的防刷限流限制"""
    mock_ws = MagicMock()
    mock_manager = MagicMock()
    mock_service = MagicMock()
    
    sent_messages = []
    async def mock_send(msg):
        sent_messages.append(msg)
        
    handler = GameWebSocketHandler(mock_ws, "player123", mock_manager, mock_service)
    handler._send = mock_send
    
    # 模拟正常处理转发
    handler._forward_distributed_command = AsyncMock(return_value=True)
    
    # 第一次发送动作请求，允许通过
    import time
    await handler._handle_message('{"action": "call_landlord", "score": 1}')
    
    # 紧接着（在 100ms 内）发送第二次动作请求，触发拦截
    await handler._handle_message('{"action": "call_landlord", "score": 2}')
    
    assert len(sent_messages) == 1
    assert sent_messages[0]["event"] == "error"
    assert "请求过于频繁" in sent_messages[0]["msg"]


@pytest.mark.asyncio
async def test_websocket_malicious_nested_json():
    """测试恶意超级嵌套 JSON 深度拦截防御，防止调用栈溢出"""
    mock_ws = MagicMock()
    mock_manager = MagicMock()
    mock_service = MagicMock()
    
    sent_messages = []
    async def mock_send(msg):
        sent_messages.append(msg)
        
    handler = GameWebSocketHandler(mock_ws, "player123", mock_manager, mock_service)
    handler._send = mock_send
    
    # 构造一个 6 层深的嵌套 JSON
    # {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
    nested_json = '{"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}'
    await handler._handle_message(nested_json)
    
    assert len(sent_messages) == 1
    assert sent_messages[0]["event"] == "error"
    assert "数据层级嵌套过深" in sent_messages[0]["msg"]


@pytest.mark.asyncio
async def test_websocket_oversized_array():
    """测试恶意超长数组列表注入防御拦截"""
    mock_ws = MagicMock()
    mock_manager = MagicMock()
    mock_service = MagicMock()
    
    sent_messages = []
    async def mock_send(msg):
        sent_messages.append(msg)
        
    handler = GameWebSocketHandler(mock_ws, "player123", mock_manager, mock_service)
    handler._send = mock_send
    
    # 构造包含 31 个元素的数组动作
    oversized_list = list(range(31))
    payload = f'{{"action": "play_cards", "cards": {oversized_list}}}'
    
    await handler._handle_message(payload)
    
    assert len(sent_messages) == 1
    assert sent_messages[0]["event"] == "error"
    assert "数据数组元素超出合理范围" in sent_messages[0]["msg"]
