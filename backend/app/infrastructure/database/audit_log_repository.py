from typing import List, Tuple
from sqlalchemy.orm import Session
from app.domain.audit_log.audit_log import AuditLog
from app.domain.audit_log.repositories import AuditLogRepository
from app.infrastructure.database.models import AuditLogORM
from app.infrastructure.database.generic_repository import GenericSQLRepository

class SQLAuditLogRepository(GenericSQLRepository[AuditLog, AuditLogORM], AuditLogRepository):
    """AuditLogRepository 契约的 MySQL 具体实现"""

    def __init__(self, db: Session):
        super().__init__(db, AuditLogORM, AuditLog)

    def save(self, audit_log: AuditLog) -> AuditLog:
        orm_log = AuditLogORM(
            operator=audit_log.operator,
            action=audit_log.action,
            resource_type=audit_log.resource_type,
            resource_id=audit_log.resource_id,
            ip_address=audit_log.ip_address,
            user_agent=audit_log.user_agent,
            status=audit_log.status,
            details=audit_log.details,
            created_at=audit_log.created_at,
            request_params=audit_log.request_params,
            execution_time=audit_log.execution_time,
            method=audit_log.method
        )
        self.db.add(orm_log)
        self.db.flush()  # 写入数据库获取主键自增 ID，但不提交事务
        self.db.refresh(orm_log)
        audit_log.id = orm_log.id
        return audit_log

    def find_paginated(
        self, 
        filters: dict, 
        page: int, 
        limit: int
    ) -> Tuple[List[AuditLog], int]:
        query = self.db.query(AuditLogORM)
        
        # 组装条件过滤
        if filters.get("operator"):
            query = query.filter(AuditLogORM.operator == filters["operator"])
        if filters.get("action"):
            query = query.filter(AuditLogORM.action == filters["action"])
        if filters.get("status"):
            query = query.filter(AuditLogORM.status == filters["status"])
            
        total = query.count()
        
        # 倒序分页查询
        offset = (page - 1) * limit
        orm_logs = query.order_by(AuditLogORM.created_at.desc()).offset(offset).limit(limit).all()
        
        domain_logs = [self._to_domain(log) for log in orm_logs]
        return domain_logs, total
