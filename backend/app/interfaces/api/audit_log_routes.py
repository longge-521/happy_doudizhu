import logging
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.infrastructure.database.session import get_db
from app.infrastructure.auth import verify_token
from app.application.audit_log.audit_log_app_service import AuditLogAppService
from app.infrastructure.audit_route import AuditLogRoute

logger = logging.getLogger("hmp_ws_service")
router = APIRouter(prefix="/api/audit-logs", tags=["AuditLogs"], dependencies=[Depends(verify_token)], route_class=AuditLogRoute)

def get_audit_service(db: Session = Depends(get_db)) -> AuditLogAppService:
    return AuditLogAppService(db)

@router.get("", summary="QUERY_AUDIT_LOGS", description="audit_log")
async def get_audit_logs(
    page: int = Query(1, ge=1, description="当前页码"),
    limit: int = Query(10, ge=1, le=100, description="每页记录数"),
    operator: Optional[str] = Query(None, description="按操作人/账号筛选"),
    action: Optional[str] = Query(None, description="按操作动作筛选"),
    status: Optional[str] = Query(None, description="按执行状态筛选(success/failed)"),
    service: AuditLogAppService = Depends(get_audit_service)
):
    try:
        filters = {}
        if operator:
            filters["operator"] = operator
        if action:
            filters["action"] = action
        if status:
            filters["status"] = status

        logs, total = await service.get_logs_page(filters, page, limit)
        
        result_data = []
        for log in logs:
            request_params = None
            if log.request_params:
                try:
                    request_params = json.loads(log.request_params)
                except Exception:
                    request_params = log.request_params

            result_data.append({
                "id": log.id,
                "operator": log.operator,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "status": log.status,
                "details": log.details,
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
                "request_params": request_params,
                "execution_time": log.execution_time,
                "method": log.method
            })
            
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": result_data
        }
    except Exception as e:
        logger.error(f"Failed to query audit logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to query audit logs")
