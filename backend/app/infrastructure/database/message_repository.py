import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from app.domain.message.entities import SiteMessage
from app.domain.message.repositories import MessageRepository
from app.infrastructure.database.models import SiteMessageORM
from app.infrastructure.database.generic_repository import GenericSQLRepository

class SQLMessageRepository(GenericSQLRepository[SiteMessage, SiteMessageORM], MessageRepository):
    """MessageRepository 契约的 MySQL 具体实现"""

    def __init__(self, db: Session):
        super().__init__(db, SiteMessageORM, SiteMessage)

    def save(self, message: SiteMessage) -> SiteMessage:
        if message.id is not None:
            orm_msg = self.db.query(SiteMessageORM).filter(SiteMessageORM.id == message.id).first()
            if orm_msg:
                orm_msg.sender = message.sender
                orm_msg.receiver = message.receiver
                orm_msg.content = message.content
                orm_msg.is_read = message.is_read
                orm_msg.created_at = message.created_at
                orm_msg.updated_at = message.updated_at
                orm_msg.read_at = message.read_at
                self.db.flush()  # 仅刷新变更缓存，不提交事务
                return self._to_domain(orm_msg)
        
        orm_msg = SiteMessageORM(
            sender=message.sender,
            receiver=message.receiver,
            content=message.content,
            is_read=message.is_read,
            created_at=message.created_at,
            updated_at=message.updated_at,
            read_at=message.read_at
        )
        self.db.add(orm_msg)
        self.db.flush()  # 写入数据库获取主键自增 ID，但不提交事务
        self.db.refresh(orm_msg)
        message.id = orm_msg.id
        return message

    def find_by_receiver(self, receiver: str, status: str = "all") -> List[SiteMessage]:
        query = self.db.query(SiteMessageORM).filter(SiteMessageORM.receiver == receiver)
        if status == "unread":
            query = query.filter(SiteMessageORM.is_read == 0)
        elif status == "read":
            query = query.filter(SiteMessageORM.is_read == 1)
        
        orm_messages = query.order_by(SiteMessageORM.created_at.desc()).all()
        return [self._to_domain(msg) for msg in orm_messages]

    def mark_all_as_read(self, receiver: str) -> int:
        now = datetime.datetime.now()
        updated_count = self.db.query(SiteMessageORM).filter(
            SiteMessageORM.receiver == receiver,
            SiteMessageORM.is_read == 0
        ).update({
            SiteMessageORM.is_read: 1,
            SiteMessageORM.updated_at: now,
            SiteMessageORM.read_at: now
        }, synchronize_session=False)
        return updated_count
