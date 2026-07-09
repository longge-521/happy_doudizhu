import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import aio_pika
from app.infrastructure.game.rabbitmq_bus import RabbitMQMessageBus

@pytest.mark.asyncio
async def test_settlement_consumer_retries_and_dlq():
    # 模拟 RabbitMQ 消息总线
    bus = RabbitMQMessageBus()
    bus.channel = AsyncMock()
    bus.channel.is_closed = False
    
    # 模拟交换机与队列
    mock_exchange = AsyncMock()
    mock_queue = AsyncMock()
    bus.channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    bus.channel.declare_queue = AsyncMock(return_value=mock_queue)
    bus.channel.get_exchange = AsyncMock(return_value=mock_exchange)
    
    # 记录 callback 执行次数
    call_count = 0
    async def failing_callback(room_id, payload):
        nonlocal call_count
        call_count += 1
        raise ValueError("Simulated DB Transient Error")
        
    # 模拟一条 RabbitMQ 结算消息
    msg_data = {"room_id": "room-1", "payload": {"winner": "p1"}}
    mock_msg = AsyncMock(spec=aio_pika.Message)
    mock_msg.body = json.dumps(msg_data).encode("utf-8")
    mock_msg.headers = {}
    mock_msg.ack = AsyncMock()
    mock_msg.nack = AsyncMock()
    
    # 用 patch 拦截 rabbitmq_bus 内部的 asyncio.sleep 以免延迟测试运行
    with patch("app.infrastructure.game.rabbitmq_bus.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # 1. 模拟第一次失败 (retry_count=0) -> 期望重试发布，并 ack 当前消息
        await bus.subscribe_settlement_tasks(failing_callback)
        
        # 提取 _settlement_consume_loop 内使用的 queue_iter
        # 我们用一个 mock iterator 喂入消息
        class MockQueueIterator:
            def __init__(self, msg):
                self.msg = msg
                self.yielded = False
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
            def __aiter__(self):
                return self
            async def __anext__(self):
                if not self.yielded:
                    self.yielded = True
                    return self.msg
                raise StopAsyncIteration
                
        mock_queue.iterator = MagicMock(return_value=MockQueueIterator(mock_msg))
        
        # 等待消费协程彻底执行完毕
        await bus._settlement_consumer_task
        
        # 验证：
        # - callback 被调用
        # - asyncio.sleep 睡了 3.0 秒
        # - mock_exchange.publish 被调用，发布了 retry_count 为 1 递增后的消息
        # - mock_msg.ack 被调用 (代表老消息从队列移去)
        assert call_count == 1
        mock_sleep.assert_awaited_once_with(3.0)
        mock_exchange.publish.assert_awaited_once()
        mock_msg.ack.assert_awaited_once()
        mock_msg.nack.assert_not_called()

@pytest.mark.asyncio
async def test_settlement_consumer_exhausted_to_dlq():
    # 模拟 RabbitMQ 消息总线，验证重试次数达到 3 次时，直接 nack 丢入 DLQ
    bus = RabbitMQMessageBus()
    bus.channel = AsyncMock()
    bus.channel.is_closed = False
    
    mock_exchange = AsyncMock()
    mock_queue = AsyncMock()
    bus.channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    bus.channel.declare_queue = AsyncMock(return_value=mock_queue)
    bus.channel.get_exchange = AsyncMock(return_value=mock_exchange)
    
    call_count = 0
    async def failing_callback(room_id, payload):
        nonlocal call_count
        call_count += 1
        raise ValueError("Simulated DB Fatal Error")
        
    msg_data = {"room_id": "room-1", "payload": {"winner": "p1"}}
    mock_msg = AsyncMock(spec=aio_pika.Message)
    mock_msg.body = json.dumps(msg_data).encode("utf-8")
    # 已经重试了 3 次！
    mock_msg.headers = {"x-retry-count": 3}
    mock_msg.ack = AsyncMock()
    mock_msg.nack = AsyncMock()
    
    class MockQueueIterator:
        def __init__(self, msg):
            self.msg = msg
            self.yielded = False
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.yielded:
                self.yielded = True
                return self.msg
            raise StopAsyncIteration
            
    mock_queue.iterator = MagicMock(return_value=MockQueueIterator(mock_msg))
    
    await bus.subscribe_settlement_tasks(failing_callback)
    # 等待消费协程彻底执行完毕
    await bus._settlement_consumer_task
    
    # 验证：
    # - callback 被调用
    # - mock_msg.nack(requeue=False) 被调用，踢进死信队列
    # - 没有再次 publish 发送重载消息
    assert call_count == 1
    mock_msg.nack.assert_awaited_once_with(requeue=False)
    mock_msg.ack.assert_not_called()
    mock_exchange.publish.assert_not_called()

@pytest.mark.asyncio
async def test_replay_dead_letter_queue():
    bus = RabbitMQMessageBus()
    bus.channel = AsyncMock()
    bus.channel.is_closed = False
    
    mock_exchange = AsyncMock()
    mock_dlq = AsyncMock()
    bus.channel.declare_queue = AsyncMock(return_value=mock_dlq)
    bus.channel.get_exchange = AsyncMock(return_value=mock_exchange)
    
    # 模拟死信队列中有一条消息，第二次 get() 返回 None 终止循环
    mock_dlq_msg = AsyncMock(spec=aio_pika.Message)
    mock_dlq_msg.body = b"some_body"
    mock_dlq_msg.headers = {"x-retry-count": 3}
    mock_dlq_msg.ack = AsyncMock()
    
    # 让 get 依次返回 消息 和 None
    mock_dlq.get = AsyncMock(side_effect=[mock_dlq_msg, None])
    
    count = await bus.replay_dead_letter_queue()
    
    assert count == 1
    # 验证发布消息到 settle 路由，且 x-retry-count 被重置为 0
    mock_exchange.publish.assert_awaited_once()
    published_msg = mock_exchange.publish.call_args[0][0]
    assert published_msg.headers["x-retry-count"] == 0
    # 验证死信消息被 ack 消费掉了
    mock_dlq_msg.ack.assert_awaited_once()
