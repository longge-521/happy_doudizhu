import datetime
from typing import Optional

class SiteMessage:
    """站内信领域实体，不依赖任何第三方框架（如 ORM）的纯 Python 领域模型。"""
    def __init__(
        self,
        sender: str,
        receiver: str,
        content: str,
        id: Optional[int] = None,
        is_read: int = 0,
        created_at: Optional[datetime.datetime] = None,
        updated_at: Optional[datetime.datetime] = None,
        read_at: Optional[datetime.datetime] = None
    ):
        self.id = id
        self.sender = sender
        self.receiver = receiver
        self.content = content
        self.is_read = is_read
        self.created_at = created_at or datetime.datetime.now()
        self.updated_at = updated_at or datetime.datetime.now()
        self.read_at = read_at

    def mark_as_read(self):
        """将当前站内信标记为已读（领域行为）"""
        self.is_read = 1
        self.read_at = datetime.datetime.now()

