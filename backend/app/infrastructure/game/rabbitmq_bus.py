import json
import asyncio
import logging
import aio_pika
from typing import Callable, Awaitable, Optional
from app.domain.game.interfaces import IGameMessageBus
from app.application.game.schemas import GameCommandSchema, GameEventSchema
from app.infrastructure.config import settings

logger = logging.getLogger("happy_doudizhu")

class RabbitMQMessageBus(IGameMessageBus):
    """基于 RabbitMQ 的分布式消息总线实现。"""

    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.event_exchange_name = "ddz.game.events"
        self.command_exchange_name = "ddz.game.commands"
        self._shard_consumers = {}

    async def connect(self) -> None:
        """建立 RabbitMQ 异步长连接与 Channel"""
        logger.info("[RabbitMQMessageBus] Connecting to RabbitMQ...")
        self.connection = await aio_pika.connect_robust(
            host=settings.MQ_HOST,
            port=settings.MQ_PORT,
            login=settings.MQ_USER,
            password=settings.MQ_PASSWORD,
            heartbeat=60
        )
        self.channel = await self.connection.channel()
        
        # 声明 Exchange
        await self.channel.declare_exchange(
            self.event_exchange_name, 
            aio_pika.ExchangeType.DIRECT, 
            durable=True
        )
        await self.channel.declare_exchange(
            self.command_exchange_name, 
            aio_pika.ExchangeType.DIRECT, 
            durable=True
        )
        logger.info("[RabbitMQMessageBus] Connected successfully and exchanges declared.")

    async def close(self) -> None:
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        self.connection = None
        self.channel = None

    async def publish_command(self, shard_id: int, command: GameCommandSchema) -> None:
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("RabbitMQMessageBus is not connected")
        
        body = command.model_dump_json()
        message = aio_pika.Message(
            body=body.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        exchange = await self.channel.get_exchange(self.command_exchange_name)
        routing_key = f"shard.{shard_id}"
        await exchange.publish(message, routing_key=routing_key)
        logger.debug(f"[RabbitMQMessageBus] Command published to {routing_key}: {body}")

    async def subscribe_commands(
        self, 
        shard_id: int, 
        callback: Callable[[GameCommandSchema], Awaitable[None]]
    ) -> None:
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("RabbitMQMessageBus is not connected")
            
        queue_name = f"ddz.game.commands.shard.{shard_id}"
        routing_key = f"shard.{shard_id}"
        
        arguments = {"x-single-active-consumer": True}
        queue = await self.channel.declare_queue(
            queue_name, 
            durable=True, 
            arguments=arguments
        )
        exchange = await self.channel.get_exchange(self.command_exchange_name)
        await queue.bind(exchange, routing_key=routing_key)
        
        async def _consume_loop():
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        try:
                            data_str = message.body.decode("utf-8")
                            command = GameCommandSchema.model_validate_json(data_str)
                            await callback(command)
                        except Exception as e:
                            logger.error(f"[ShardConsumer-{shard_id}] Error: {e}")

        task = asyncio.create_task(_consume_loop())
        self._shard_consumers[shard_id] = (task, queue)
        logger.info(f"[RabbitMQMessageBus] Subscribed to shard {shard_id}")

    async def unsubscribe_commands(self, shard_id: int) -> None:
        item = self._shard_consumers.pop(shard_id, None)
        if item:
            task, queue = item
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info(f"[RabbitMQMessageBus] Unsubscribed from shard {shard_id}")

    async def publish_event(self, instance_id: str, event: GameEventSchema) -> None:
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("RabbitMQMessageBus is not connected")

        body = event.model_dump_json()
        message = aio_pika.Message(
            body=body.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        exchange = await self.channel.get_exchange(self.event_exchange_name)
        routing_key = f"instance.{instance_id}"
        await exchange.publish(message, routing_key=routing_key)
        logger.debug(f"[RabbitMQMessageBus] Event published to {routing_key}: {body}")
