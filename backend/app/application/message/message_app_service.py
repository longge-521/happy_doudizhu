import asyncio
import logging
from typing import List
from app.domain.message.entities import SiteMessage
from app.domain.message.repositories import MessageRepository
from app.infrastructure.mq.rabbitmq_adapter import RabbitMQAdapter

logger = logging.getLogger("hmp_ws_service")

class MessageAppService:
    """站内信应用服务类，编排事务与业务用例。"""
    
    def __init__(self, repo: MessageRepository, mq_adapter: RabbitMQAdapter):
        self.repo = repo
        self.mq_adapter = mq_adapter

    async def send_message(self, sender: str, receiver: str, content: str) -> SiteMessage:
        """发送站内信：保存到数据库并异步发布至 RabbitMQ Exchange，包含优雅退化机制。"""
        # 1. 实例化领域实体并保存（数据库写入）
        msg = SiteMessage(sender=sender, receiver=receiver, content=content)
        saved_msg = await asyncio.to_thread(self.repo.save, msg)

        # 2. 异步发布到 RabbitMQ 广播交换机
        mq_body = {
            "id": saved_msg.id,
            "sender": saved_msg.sender,
            "receiver": saved_msg.receiver,
            "content": saved_msg.content,
            "is_read": saved_msg.is_read,
            "created_at": saved_msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if saved_msg.created_at else ""
        }

        try:
            if self.mq_adapter and self.mq_adapter.is_connected:
                await self.mq_adapter.publish("", mq_body, exchange_name=self.mq_adapter.exchange_name)
                logger.info(f"MessageAppService: 已发布消息到 MQ Exchange, id={saved_msg.id}")
            else:
                logger.warning(f"MessageAppService: RabbitMQ 暂不可用，已优雅退化 (站内信已保存至 DB, id={saved_msg.id})")
        except Exception as e:
            logger.error(f"MessageAppService: 异步发布 MQ 发生错误 (已优雅退化): {e}")

        return saved_msg

    async def get_messages(self, receiver: str, status: str = "all") -> List[SiteMessage]:
        """获取指定接收者的站内信列表。"""
        return await asyncio.to_thread(self.repo.find_by_receiver, receiver, status)

    async def mark_as_read(self, message_id: int) -> bool:
        """标记某条消息为已读。"""
        def _sync_mark():
            msg = self.repo.find_by_id(message_id)
            if not msg:
                return False
            msg.mark_as_read()
            self.repo.save(msg)
            return True
        return await asyncio.to_thread(_sync_mark)

    async def mark_all_as_read(self, receiver: str) -> int:
        """一键已读：标记某个接收者的所有未读消息为已读。"""
        return await asyncio.to_thread(self.repo.mark_all_as_read, receiver)

