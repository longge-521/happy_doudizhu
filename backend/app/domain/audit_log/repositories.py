from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.domain.audit_log.audit_log import AuditLog

class AuditLogRepository(ABC):
    """审计日志仓储抽象接口（契约定义），基础设施层应实现该类。"""
    
    @abstractmethod
    def save(self, audit_log: AuditLog) -> AuditLog:
        """保存审计日志记录，用于创建"""
        pass

    @abstractmethod
    def find_paginated(
        self, 
        filters: dict, 
        page: int, 
        limit: int
    ) -> Tuple[List[AuditLog], int]:
        """分页查找审计日志，并支持过滤条件筛选。返回 (日志列表, 总记录数)"""
        pass
