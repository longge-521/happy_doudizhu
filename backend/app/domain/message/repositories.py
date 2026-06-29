from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.message.entities import SiteMessage

class MessageRepository(ABC):
    """站内信仓储抽象接口（契约定义），基础设施层应实现该类。"""
    
    @abstractmethod
    def save(self, message: SiteMessage) -> SiteMessage:
        """保存站内信实体，用于创建或更新"""
        pass

    @abstractmethod
    def find_by_id(self, message_id: int) -> Optional[SiteMessage]:
        """根据 ID 查找站内信对象"""
        pass

    @abstractmethod
    def find_by_receiver(self, receiver: str, status: str = "all") -> List[SiteMessage]:
        """查找指定接收者的站内信，根据 status 状态过滤 ('all', 'unread', 'read')"""
        pass

    @abstractmethod
    def mark_all_as_read(self, receiver: str) -> int:
        """一键已读：将指定接收者所有未读消息标为已读，返回修改的条数"""
        pass
