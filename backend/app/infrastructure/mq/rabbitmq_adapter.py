import os
import json
import uuid
import logging
import asyncio
import aio_pika
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("hmp_ws_service")

class RabbitMQAdapter:
    """处理具体的 aio_pika 连接管理、通道声明以及重连逻辑，提供向外暴露的简单发送/消费接口。"""
    
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.host = os.getenv("MQ_HOST", "127.0.0.1")
        self.port = int(os.getenv("MQ_PORT", "5672"))
        self.user = os.getenv("MQ_USER", "admin")
        self.password = os.getenv("MQ_PASSWORD", "123456")
        self.exchange_name = os.getenv("MQ_EXCHANGE_NAME", "hmp_ws_service_site_messages_exchange")
        self._consumer_tasks = []

    async def connect(self):
        """建立 RabbitMQ 异步长连接"""
        logger.info("正在建立 RabbitMQ 异步长连接 (Adapter)...")
        self.connection = await aio_pika.connect_robust(
            host=self.host,
            port=self.port,
            login=self.user,
            password=self.password,
            heartbeat=60
        )
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=1)
        logger.info("RabbitMQ robust 连接建立成功 (Adapter)。")

    async def close(self):
        """释放所有 MQ 资源"""
        for task in self._consumer_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumer_tasks.clear()

        if self.channel and not self.channel.is_closed:
            try:
                await self.channel.close()
            except Exception:
                pass
        self.channel = None

        if self.connection and not self.connection.is_closed:
            try:
                await self.connection.close()
            except Exception:
                pass
        self.connection = None

    @property
    def is_connected(self) -> bool:
        return (
            self.connection is not None 
            and not self.connection.is_closed 
            and self.channel is not None 
            and not self.channel.is_closed
        )

    async def publish(self, routing_key: str, message: dict, exchange_name: Optional[str] = None):
        """向指定的队列或交换机发布消息，支持在 MQ 不可用时抛出异常"""
        if not self.is_connected:
            raise ConnectionError("RabbitMQ is not connected or channel is closed")
        
        body = json.dumps(message, ensure_ascii=False)
        msg = aio_pika.Message(
            body=body.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        
        if exchange_name:
            # 声明扇出交换机
            exchange = await self.channel.declare_exchange(
                exchange_name, aio_pika.ExchangeType.FANOUT, durable=True
            )
            await exchange.publish(msg, routing_key=routing_key)
            logger.debug(f"RabbitMQAdapter: Message published to exchange {exchange_name} (routing_key={routing_key}): {body}")
        else:
            await self.channel.default_exchange.publish(
                msg,
                routing_key=routing_key
            )
            logger.debug(f"RabbitMQAdapter: Message published to direct queue {routing_key}: {body}")

    async def start_consuming_broadcast(self, exchange_name: str, callback: Callable[[dict], Awaitable[None]]):
        """订阅广播模式：在交换机上声明一个专属临时独占排他队列，所有在线实例均能收到消息克隆。"""
        if not self.is_connected:
            raise ConnectionError("RabbitMQ is not connected or channel is closed")

        # 1. 声明 Fanout Exchange
        exchange = await self.channel.declare_exchange(
            exchange_name, aio_pika.ExchangeType.FANOUT, durable=True
        )
        
        # 2. 声明一个带有唯一 UUID 命名且非排他的持久化临时队列 (durable=True, exclusive=False, auto_delete=True)
        # - 设置 durable=True 规避新版 RabbitMQ (>=4.0) 禁用 transient_nonexcl_queues 的报错；
        # - 设置 exclusive=False 规避 aio-pika robust 断线重连时旧连接未释放导致的 RESOURCE_LOCKED 锁死问题；
        # - 设置 auto_delete=True 确保在所有消费者断开（实例正常关闭/退出）时队列能被自动删除。
        queue_name = f"hmp_ws_broadcast_{uuid.uuid4().hex}"
        queue = await self.channel.declare_queue(
            queue_name, durable=True, exclusive=False, auto_delete=True
        )
        
        # 3. 将队列绑定到该交换机上
        await queue.bind(exchange)
        logger.info(f"Broadcast consumer: Temporary Queue '{queue.name}' bound to Exchange '{exchange_name}'")

        async def _consume_loop():
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            data = json.loads(message.body.decode('utf-8'))
                            await callback(data)
                        except Exception as e:
                            logger.error(f"Error processing consumed broadcast message: {e}")

        task = asyncio.create_task(_consume_loop())
        self._consumer_tasks.append(task)
        logger.info(f"Started consuming broadcast from exchange: {exchange_name}")
