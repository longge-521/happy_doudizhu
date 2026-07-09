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
        self.settlement_exchange_name = "ddz.game.settlement"
        self._shard_consumers = {}
        self._settlement_consumer_task = None

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
        await self.channel.declare_exchange(
            self.settlement_exchange_name,
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

    async def publish_settlement_task(self, room_id: str, result_payload: dict) -> None:
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("RabbitMQMessageBus is not connected")
        
        payload_data = {
            "room_id": room_id,
            "payload": result_payload
        }
        body = json.dumps(payload_data)
        message = aio_pika.Message(
            body=body.encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        exchange = await self.channel.get_exchange(self.settlement_exchange_name)
        await exchange.publish(message, routing_key="settle")
        logger.info(f"[RabbitMQMessageBus] Published settlement task for room {room_id}")

    async def subscribe_settlement_tasks(
        self,
        callback: Callable[[str, dict], Awaitable[None]]
    ) -> None:
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("RabbitMQMessageBus is not connected")
            
        # 声明死信交换机和死信队列
        dlx_name = "ddz.game.settlement.dlx"
        dlq_name = "ddz.game.settlement.dlq"
        dlx = await self.channel.declare_exchange(dlx_name, type="direct", durable=True)
        dlq = await self.channel.declare_queue(dlq_name, durable=True)
        await dlq.bind(dlx, routing_key="settle_dlq")
        
        # 声明主队列，指定 x-dead-letter 属性
        queue_name = "ddz.game.settlement"
        try:
            queue = await self.channel.declare_queue(
                queue_name, 
                durable=True,
                arguments={
                    "x-dead-letter-exchange": dlx_name,
                    "x-dead-letter-routing-key": "settle_dlq"
                }
            )
        except Exception as e:
            if "PRECONDITION_FAILED" in str(e):
                logger.critical(
                    f"\n"
                    f"========================================================================\n"
                    f"❌ RabbitMQ 队列声明冲突 (PRECONDITION_FAILED) ❌\n"
                    f"原因: 检测到本地已经存在旧的 '{queue_name}' 队列，但是它没有绑定死信参数。\n"
                    f"解决办法: 请登录 RabbitMQ 管理端 (通常是 http://localhost:15672) 手动删除或清空\n"
                    f"          '{queue_name}' 队列，然后重新启动服务以应用新的死信重试队列属性。\n"
                    f"========================================================================\n"
                )
            raise e
        exchange = await self.channel.get_exchange(self.settlement_exchange_name)
        await queue.bind(exchange, routing_key="settle")
        
        async def _settlement_consume_loop():
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    try:
                        data_str = message.body.decode("utf-8")
                        data = json.loads(data_str)
                        room_id = data.get("room_id")
                        payload = data.get("payload", {})
                        
                        try:
                            await callback(room_id, payload)
                            await message.ack()
                        except Exception as inner_err:
                            headers = dict(message.headers or {})
                            retry_count = int(headers.get("x-retry-count", 0))
                            logger.warning(
                                f"[SettlementConsumer] Attempt {retry_count} failed for room {room_id}: {inner_err}"
                            )
                            
                            if retry_count < 3:
                                # 递增重试次数并重新发布（带退避）
                                new_headers = {**headers, "x-retry-count": retry_count + 1}
                                await asyncio.sleep(3.0)  # 退避 3 秒
                                
                                new_message = aio_pika.Message(
                                    body=message.body,
                                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                    headers=new_headers
                                )
                                settle_exchange = await self.channel.get_exchange(self.settlement_exchange_name)
                                await settle_exchange.publish(new_message, routing_key="settle")
                                await message.ack()
                            else:
                                logger.error(
                                    f"[SettlementConsumer] Retries exhausted for room {room_id}. Sending to DLQ."
                                )
                                await message.nack(requeue=False)  # 拒绝重投，自动滑入死信队列
                    except Exception as outer_err:
                        logger.error(f"[SettlementConsumer] Fatal message parse error: {outer_err}")
                        await message.nack(requeue=False)

        self._settlement_consumer_task = asyncio.create_task(_settlement_consume_loop())
        logger.info("[RabbitMQMessageBus] Subscribed to settlement queue")

    async def replay_dead_letter_queue(self) -> int:
        """重放死信队列中所有的结算任务。返回重放的任务数量。"""
        if not self.channel or self.channel.is_closed:
            raise ConnectionError("RabbitMQMessageBus is not connected")
            
        dlq_name = "ddz.game.settlement.dlq"
        dlq = await self.channel.declare_queue(dlq_name, durable=True)
        
        replayed = 0
        while True:
            # 使用 get 获取单条消息，no_ack=False
            message = await dlq.get(fail=False)
            if not message:
                break
                
            try:
                # 剥离或重置重试计数
                headers = dict(message.headers or {})
                headers["x-retry-count"] = 0
                
                new_message = aio_pika.Message(
                    body=message.body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers=headers
                )
                settle_exchange = await self.channel.get_exchange(self.settlement_exchange_name)
                await settle_exchange.publish(new_message, routing_key="settle")
                await message.ack()
                replayed += 1
            except Exception as e:
                logger.error(f"[RabbitMQMessageBus] Failed to replay DLQ message: {e}")
                await message.nack(requeue=True)
                break
                
        return replayed

