import json
import logging
from fastapi import Request, Response
from fastapi.routing import APIRoute
from app.application.audit_log.audit_log_app_service import AuditLogAppService

logger = logging.getLogger("hmp_ws_service")

class AuditLogRoute(APIRoute):
    """
    自定义 APIRoute，用于拦截标记了 summary（审计动作名）和 description（资源类型）的 HTTP 路由，
    并自动且异步记录审计日志。
    """
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()
        
        async def custom_route_handler(request: Request) -> Response:
            action = self.summary
            resource_type = self.description
            
            # 仅拦截我们需要审计的动作范围，其他路由直接放行
            # QUERY_AUDIT_LOGS 亦将通过 Redis 防抖来防止死循环暴增
            auditable_actions = {
                "SEND_MESSAGE", "READ_MESSAGE", "READ_ALL_MESSAGES", "DELETE_FILE",
                "QUERY_MESSAGES", "QUERY_UPLOADED_FILES", "QUERY_AUDIT_LOGS"
            }
            if not action or action not in auditable_actions:
                return await original_route_handler(request)
            
            operator = None
            resource_id = None
            
            # 1. 尝试从 URL 路径参数自动提取资源 ID
            if "message_id" in request.path_params:
                resource_id = str(request.path_params["message_id"])
            elif "file_id" in request.path_params:
                resource_id = str(request.path_params["file_id"])
                
            # 2. 尝试从 Query 提取 operator 
            if action == "READ_ALL_MESSAGES":
                operator = request.query_params.get("receiver")
                
            # 通用提取参数与备份 Body
            request_params = {}
            if request.path_params:
                request_params["path"] = dict(request.path_params)
            if request.query_params:
                query_dict = dict(request.query_params)
                if "token" in query_dict:
                    query_dict["token"] = "******"
                request_params["query"] = query_dict
                
            if request.method in ("POST", "PUT", "PATCH"):
                try:
                    body_bytes = await request.body()
                    async def receive():
                        return {"type": "http.request", "body": body_bytes, "more_body": False}
                    request._receive = receive
                    
                    if body_bytes:
                        try:
                            body_json = json.loads(body_bytes.decode("utf-8"))
                            request_params["body"] = body_json
                            # 如果是发送站内信，提取发送者作为操作者
                            if action == "SEND_MESSAGE" and isinstance(body_json, dict):
                                operator = body_json.get("sender")
                        except Exception:
                            request_params["body"] = body_bytes.decode("utf-8", errors="ignore")
                except Exception as e:
                    logger.warning(f"AuditLogRoute failed to parse body bytes: {e}")
            
            # 3. 针对查询接口引入 Redis 异步防抖判定
            skip_audit = False
            if action and action.startswith("QUERY_"):
                import hashlib
                from app.infrastructure.redis_client import is_query_debounced
                
                # 组装参数 hash
                param_str = json.dumps(request_params, sort_keys=True, ensure_ascii=False)
                param_hash = hashlib.md5(param_str.encode("utf-8")).hexdigest()
                debounce_key = f"hmp:audit:debounce:{operator or 'system'}:{action}:{param_hash}"
                
                # 尝试进行防抖锁定
                skip_audit = await is_query_debounced(debounce_key, expire_seconds=3)

            # 4. 执行业务逻辑并计时
            import time
            start_time = time.time()
            try:
                response = await original_route_handler(request)
                execution_time = round((time.time() - start_time) * 1000, 2)
                
                status = "success"
                details = None
                if response.status_code >= 400:
                    status = "failed"
                    details = f"HTTP status code: {response.status_code}"
                    
                # 5. 对于 SEND_MESSAGE 成功逻辑，安全拉取 response 里的 ID
                if status == "success" and action == "SEND_MESSAGE":
                    try:
                        response_body = b""
                        if hasattr(response, "body_iterator"):
                            async for chunk in response.body_iterator:
                                response_body += chunk
                            
                            # 必须重构 Response 以防原响应流被耗尽失效
                            response = Response(
                                content=response_body,
                                status_code=response.status_code,
                                headers=dict(response.headers),
                                media_type=response.media_type
                            )
                        else:
                            # 静态 Response 或 JSONResponse 直接读取 body
                            response_body = response.body
                        
                        res_json = json.loads(response_body.decode("utf-8"))
                        if res_json.get("status") == "success" or "id" in res_json:
                            resource_id = str(res_json.get("id"))
                    except Exception as e:
                        logger.warning(f"AuditLogRoute failed to parse response body: {e}")
                        
                # 异步入库审计日志
                if not skip_audit:
                    audit_service = AuditLogAppService()
                    await audit_service.record_log(
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        status=status,
                        details=details,
                        operator=operator or "system",
                        request_params=json.dumps(request_params, ensure_ascii=False) if request_params else None,
                        execution_time=execution_time,
                        method=request.method
                    )
                
                return response
                
            except Exception as e:
                execution_time = round((time.time() - start_time) * 1000, 2)
                logger.error(f"AuditLogRoute captured endpoint execution error: {e}")
                
                # 提取 HTTPException detail
                err_details = str(e)
                if hasattr(e, "detail"):
                    err_details = getattr(e, "detail")
                    
                if not skip_audit:
                    audit_service = AuditLogAppService()
                    await audit_service.record_log(
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        status="failed",
                        details=err_details,
                        operator=operator or "system",
                        request_params=json.dumps(request_params, ensure_ascii=False) if request_params else None,
                        execution_time=execution_time,
                        method=request.method
                    )
                raise e
                
        return custom_route_handler
