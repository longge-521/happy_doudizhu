import logging
import asyncio
from typing import Optional, Tuple, List
from fastapi import Request
from sqlalchemy.orm import Session
from app.domain.audit_log.audit_log import AuditLog
from app.infrastructure.database.audit_log_repository import SQLAuditLogRepository
from app.infrastructure.database.session import SessionLocal

logger = logging.getLogger("hmp_ws_service")

class AuditLogAppService:
    """审计日志应用服务层，实现审计日志与业务的事务隔离及异步记录。"""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def _get_repository(self, db_session: Session) -> SQLAuditLogRepository:
        return SQLAuditLogRepository(db_session)

    async def record_log(
        self,
        request: Request,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[str] = None,
        operator: Optional[str] = None,
        request_params: Optional[str] = None,
        execution_time: Optional[float] = None,
        method: Optional[str] = None
    ) -> Optional[AuditLog]:
        """
        记录 HTTP 请求触发的审计日志。
        自动从 Request 对象中提取 IP 地址和 User-Agent。
        在独立 Session 中提交，实现事务隔离，报错不会影响主流程。
        """
        ip_address = request.client.host if request.client else None
        
        # 处理 Nginx 等反向代理的真实 IP 提取
        headers = request.headers
        forwarded_for = headers.get("x-forwarded-for")
        if forwarded_for:
            ip_address = forwarded_for.split(",")[0].strip()
        else:
            real_ip = headers.get("x-real-ip")
            if real_ip:
                ip_address = real_ip

        user_agent = headers.get("user-agent")

        # 使用 to_thread 将阻塞的 DB 操作放入线程池运行
        return await asyncio.to_thread(
            self._write_log_sync,
            operator=operator,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            details=details,
            request_params=request_params,
            execution_time=execution_time,
            method=method
        )

    async def record_ws_log(
        self,
        client_ip: Optional[str],
        user_agent: Optional[str],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[str] = None,
        operator: Optional[str] = None,
        request_params: Optional[str] = None,
        execution_time: Optional[float] = None,
        method: Optional[str] = None
    ) -> Optional[AuditLog]:
        """
        专门针对 WebSocket 等非标准 HTTP Request 场景记录审计日志。
        """
        return await asyncio.to_thread(
            self._write_log_sync,
            operator=operator,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=client_ip,
            user_agent=user_agent,
            status=status,
            details=details,
            request_params=request_params,
            execution_time=execution_time,
            method=method
        )

    def _write_log_sync(self, **kwargs) -> Optional[AuditLog]:
        """
        同步写入数据库，并在独立 Session 事务中立即提交，包含容错机制。
        """
        db = SessionLocal()
        try:
            repo = self._get_repository(db)
            audit_log = AuditLog(**kwargs)
            saved_log = repo.save(audit_log)
            db.commit()
            return saved_log
        except Exception as e:
            logger.error(f"Failed to record audit log in separate transaction: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    async def get_logs_page(self, filters: dict, page: int, limit: int) -> Tuple[List[AuditLog], int]:
        """
        分页查询审计日志记录列表。
        在工作线程内部独立创建私有数据库连接会话，规避跨线程共享 SQLAlchemy Session 引发的死锁和线程不安全隐患。
        """
        return await asyncio.to_thread(self._get_logs_page_sync, filters, page, limit)

    def _get_logs_page_sync(self, filters: dict, page: int, limit: int) -> Tuple[List[AuditLog], int]:
        """
        同步获取审计日志，运行在后台工作线程中。
        """
        db = SessionLocal()
        try:
            repo = self._get_repository(db)
            return repo.find_paginated(filters, page, limit)
        finally:
            db.close()
