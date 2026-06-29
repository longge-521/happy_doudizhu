import pytest
from unittest.mock import MagicMock, patch, ANY
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.testclient import TestClient
from app.infrastructure.audit_route import AuditLogRoute

def test_audit_route_success_and_failure():
    app_test = FastAPI()
    router = APIRouter(route_class=AuditLogRoute)
    
    @router.post("/test-send", summary="SEND_MESSAGE", description="site_message")
    async def mock_send(payload: dict):
        return {"status": "success", "id": 999}
        
    @router.post("/test-fail", summary="READ_MESSAGE", description="site_message")
    async def mock_fail():
        raise HTTPException(status_code=400, detail="Mock bad request")
        
    app_test.include_router(router)
    
    # Mock record_log 避免数据库依赖
    with patch("app.application.audit_log.audit_log_app_service.AuditLogAppService.record_log") as mock_record:
        client = TestClient(app_test)
        
        # 1. 测试成功调用时的拦截与 ID 提取
        response_ok = client.post("/test-send", json={"sender": "user_123", "content": "hello"})
        assert response_ok.status_code == 200
        assert response_ok.json()["id"] == 999
        
        mock_record.assert_any_call(
            request=ANY,
            action="SEND_MESSAGE",
            resource_type="site_message",
            resource_id="999",
            status="success",
            details=None,
            operator="user_123",
            request_params=ANY,
            execution_time=ANY,
            method=ANY
        )
        
        # 2. 测试抛出 HTTPException 时的失败日志拦截
        response_err = client.post("/test-fail")
        assert response_err.status_code == 400
        
        mock_record.assert_any_call(
            request=ANY,
            action="READ_MESSAGE",
            resource_type="site_message",
            resource_id=None,
            status="failed",
            details="Mock bad request",
            operator="system",
            request_params=ANY,
            execution_time=ANY,
            method=ANY
        )

def test_audit_route_query_debounce():
    app_test = FastAPI()
    router = APIRouter(route_class=AuditLogRoute)
    
    @router.get("/test-query-msg", summary="QUERY_MESSAGES", description="site_message")
    async def mock_query():
        return {"status": "success", "data": []}
        
    @router.get("/test-query-logs", summary="QUERY_AUDIT_LOGS", description="audit_log")
    async def mock_query_logs():
        return {"status": "success", "data": []}
        
    app_test.include_router(router)
    
    # Mock record_log 和 is_query_debounced
    with patch("app.application.audit_log.audit_log_app_service.AuditLogAppService.record_log") as mock_record, \
         patch("app.infrastructure.redis_client.is_query_debounced") as mock_debounce:
        
        client = TestClient(app_test)
        
        # 1. 模拟第一次请求不防抖（mock_debounce 返回 False）
        mock_debounce.return_value = False
        response1 = client.get("/test-query-msg?keyword=test")
        assert response1.status_code == 200
        assert mock_record.call_count == 1
        
        # 2. 模拟第二次请求防抖（mock_debounce 返回 True）
        mock_debounce.return_value = True
        response2 = client.get("/test-query-msg?keyword=test")
        assert response2.status_code == 200
        # 审计记录次数依然为 1，说明被过滤了
        assert mock_record.call_count == 1
        
        # 3. 测试 QUERY_AUDIT_LOGS 支持正常拦截审计及防抖保护
        mock_record.reset_mock()
        mock_debounce.return_value = False
        response_logs1 = client.get("/test-query-logs")
        assert response_logs1.status_code == 200
        assert mock_record.call_count == 1  # 第一次，不防抖，正常记录
        
        mock_debounce.return_value = True
        response_logs2 = client.get("/test-query-logs")
        assert response_logs2.status_code == 200
        assert mock_record.call_count == 1  # 第二次，高频重复被防抖，跳过写入

