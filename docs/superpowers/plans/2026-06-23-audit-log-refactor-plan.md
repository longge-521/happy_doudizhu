# 审计日志非侵入式 APIRoute 重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将审计日志（发送消息、已读、一键已读、删除文件）由接口内手写记录重构为基于 FastAPI APIRoute 的非侵入式自动拦截记录，提高系统健壮性，使业务代码彻底纯净化，并完全规避跨线程共享 SQLAlchemy Session 引发的死锁问题。

**Architecture:** 
1. 新建 `AuditLogRoute` 类继承 `APIRoute`，在 `get_route_handler` 生命周期中自动解析请求参数、Body 备份（对 SEND_MESSAGE 进行 ID 提取），并统一捕获接口异常。
2. 审计日志写库使用独立线程（to_thread）配合私有 Session（SessionLocal()）立即提交，天然线程隔离。
3. 业务路由器 `message_routes.py` 和 `upload_routes.py` 声明 `route_class=AuditLogRoute` 并声明接口 `summary`/`description` 元数据以触发自动拦截，移除全部原手写审计代码。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Python stdlib, Pytest

## Global Constraints
- 遵守 DDD 架构层规范，分层清晰。
- 保证测试代码完全覆盖拦截行为（Request/Response 解析、流式重包装、异常日志捕捉）。
- 全局测试不能受到大文件流或 StreamingResponse 内存隐患影响，实现零拷贝非侵入包装。

---

### Task 1: 编写自定义 APIRoute 并通过单元测试验证核心拦截逻辑

**Files:**
- Create: `app/infrastructure/audit_route.py`
- Test: `tests/test_audit_route.py`

**Interfaces:**
- Consumes: `app/application/audit_log/audit_log_app_service.py` 里的 `AuditLogAppService` (获取 record_log 录入能力)。
- Produces: `app.infrastructure.audit_route.AuditLogRoute` 用于 API 路由自动拦截。

- [ ] **Step 1: 编写测试用例验证拦截器的全套参数解析、ID 提取和异常捕获流程**
  
  在 `tests/test_audit_route.py` 写入以下包含异常和成功情况的测试：
  ```python
  import pytest
  from unittest.mock import MagicMock, patch
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
              request=pytest.any_str,  # 模糊匹配 Request 对象
              action="SEND_MESSAGE",
              resource_type="site_message",
              resource_id="999",
              status="success",
              details=None,
              operator="user_123"
          )
          
          # 2. 测试抛出 HTTPException 时的失败日志拦截
          response_err = client.post("/test-fail")
          assert response_err.status_code == 400
          
          mock_record.assert_any_call(
              request=pytest.any_str,
              action="READ_MESSAGE",
              resource_type="site_message",
              resource_id=None,
              status="failed",
              details="Mock bad request",
              operator="system"
          )
  ```
  *(注: 在 assert_any_call 时可以使用 mock.ANY 匹配 request)*

- [ ] **Step 2: 运行测试以使其因文件不存在或接口未定义而失败**
  
  运行命令：
  ```powershell
  pytest tests/test_audit_route.py -v
  ```
  期望输出：`ModuleNotFoundError: No module named 'app.infrastructure.audit_route'`

- [ ] **Step 3: 编写并实现 `AuditLogRoute` 拦截类**
  
  创建 `app/infrastructure/audit_route.py`，实现拦截拦截与日志触发流程：
  ```python
  import json
  import logging
  from fastapi import Request, Response
  from fastapi.routing import APIRoute
  from starlette.responses import StreamingResponse
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
              auditable_actions = {"SEND_MESSAGE", "READ_MESSAGE", "READ_ALL_MESSAGES", "DELETE_FILE"}
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
                  
              # 3. 发送站内信时，安全备份 Request Body 提取发送者作为操作者
              if action == "SEND_MESSAGE" and request.method == "POST":
                  try:
                      body_bytes = await request.body()
                      async def receive():
                          return {"type": "http.request", "body": body_bytes, "more_body": False}
                      request._receive = receive
                      
                      req_json = json.loads(body_bytes.decode("utf-8"))
                      operator = req_json.get("sender")
                  except Exception as e:
                      logger.warning(f"AuditLogRoute failed to parse request body: {e}")
                      
              # 4. 执行业务逻辑
              try:
                  response = await original_route_handler(request)
                  
                  status = "success"
                  details = None
                  if response.status_code >= 400:
                      status = "failed"
                      details = f"HTTP status code: {response.status_code}"
                      
                  # 5. 对于 SEND_MESSAGE 成功逻辑，安全拉取 response 里的 ID
                  if status == "success" and action == "SEND_MESSAGE":
                      try:
                          response_body = b""
                          async for chunk in response.body_iterator:
                              response_body += chunk
                          
                          # 必须重构 Response 以防原响应流被耗尽失效
                          response = Response(
                              content=response_body,
                              status_code=response.status_code,
                              headers=dict(response.headers),
                              media_type=response.media_type
                          )
                          
                          res_json = json.loads(response_body.decode("utf-8"))
                          if res_json.get("status") == "success" or "id" in res_json:
                              resource_id = str(res_json.get("id"))
                      except Exception as e:
                          logger.warning(f"AuditLogRoute failed to parse response body: {e}")
                          
                  # 异步入库审计日志
                  audit_service = AuditLogAppService()
                  await audit_service.record_log(
                      request=request,
                      action=action,
                      resource_type=resource_type,
                      resource_id=resource_id,
                      status=status,
                      details=details,
                      operator=operator or "system"
                  )
                  
                  return response
                  
              except Exception as e:
                  # 拦截业务抛出的未知运行时异常并记为失败
                  logger.error(f"AuditLogRoute captured endpoint execution error: {e}")
                  
                  # 提取 HTTPException detail
                  err_details = str(e)
                  if hasattr(e, "detail"):
                      err_details = getattr(e, "detail")
                      
                  audit_service = AuditLogAppService()
                  await audit_service.record_log(
                      request=request,
                      action=action,
                      resource_type=resource_type,
                      resource_id=resource_id,
                      status="failed",
                      details=err_details,
                      operator=operator or "system"
                  )
                  raise e
                  
          return custom_route_handler
  ```

- [ ] **Step 4: 重新运行测试以使其通过**
  
  运行命令：
  ```powershell
  pytest tests/test_audit_route.py -v
  ```
  期望输出：`tests/test_audit_route.py PASSED`

- [ ] **Step 5: 提交 Task 1**
  
  ```bash
  git add app/infrastructure/audit_route.py tests/test_audit_route.py
  git commit -m "feat: add non-intrusive AuditLogRoute interceptor class and tests"
  ```

---

### Task 2: 重构 Message 与 Upload 路由接口文件，移除冗余审计代码

**Files:**
- Modify: `app/interfaces/api/message_routes.py`
- Modify: `app/interfaces/api/upload_routes.py`

**Interfaces:**
- Consumes: `app.infrastructure.audit_route.AuditLogRoute` (应用路由类)

- [ ] **Step 1: 运行现有接口业务测试以验证之前的逻辑正常**
  
  运行命令：
  ```powershell
  pytest tests/test_messages.py tests/test_upload_security.py -v
  ```
  期望输出：所有测试均已 PASSED。

- [ ] **Step 2: 重构 `app/interfaces/api/message_routes.py`**
  
  1. 引入 `AuditLogRoute`。
  2. 在 `APIRouter` 初始化中配置 `route_class=AuditLogRoute`。
  3. 接口装饰器中声明审计属性（`summary` 和 `description`）。
  4. 移除大段手写日志逻辑和 `get_audit_service` 依赖：
  
  修改后的文件内容细节：
  ```python
  from app.infrastructure.audit_route import AuditLogRoute

  router = APIRouter(
      prefix="/api/messages",
      tags=["Messages"],
      dependencies=[Depends(verify_token)],
      route_class=AuditLogRoute
  )
  ```
  接口重构如下：
  ```python
  @router.post("/send", summary="SEND_MESSAGE", description="site_message")
  async def send_message_api(request: Request,
                             request_data: MessageSendRequest,
                             service: MessageAppService = Depends(get_message_service)):
      # 清理依赖注入的 audit_service 和全部 record_log 动作，接口内变得极其纯净
      msg = await service.send_message(
          request_data.sender,
          request_data.receiver,
          request_data.content
      )
      return {"status": "success", "message": f"站内信已入库 (id={msg.id})", "id": msg.id}

  @router.post("/{message_id}/read", summary="READ_MESSAGE", description="site_message")
  async def mark_as_read_api(request: Request,
                             message_id: int,
                             service: MessageAppService = Depends(get_message_service)):
      # 清理逻辑，直接抛出业务错误即可
      success = await service.mark_as_read(message_id)
      if not success:
          raise HTTPException(status_code=404, detail="Message not found")
      return {"status": "success", "message": f"Message {message_id} marked as read"}

  @router.post("/read-all", summary="READ_ALL_MESSAGES", description="site_message")
  async def mark_all_as_read_api(request: Request,
                                 receiver: str = Query(...),
                                 service: MessageAppService = Depends(get_message_service)):
      await service.mark_all_as_read(receiver)
      return {"status": "success", "message": f"All messages for {receiver} marked as read"}
  ```

- [ ] **Step 3: 重构 `app/interfaces/api/upload_routes.py`**
  
  1. 引入 `AuditLogRoute`。
  2. 在 `APIRouter` 初始化中配置 `route_class=AuditLogRoute`。
  3. 接口装饰器中声明审计属性（`summary` 和 `description`）。
  4. 移除大段手写日志逻辑和 `get_audit_service` 依赖：
  
  修改后的文件内容细节：
  ```python
  from app.infrastructure.audit_route import AuditLogRoute

  router = APIRouter(
      prefix="/api/uploads",
      tags=["Uploads"],
      dependencies=[Depends(verify_token)],
      route_class=AuditLogRoute
  )
  ```
  接口重构如下：
  ```python
  @router.delete("/{file_id}", summary="DELETE_FILE", description="uploaded_file")
  async def delete_uploaded_file(request: Request,
                                 file_id: int,
                                 db: Session = Depends(get_db)):
      # 移除 audit_service 注入和 try-except 包裹，发生错误直接抛出 HTTP 异常
      repo = SQLUploadedFileRepository(db)
      orm_file = db.query(UploadedFileORM).filter(UploadedFileORM.id == file_id).first()
      if not orm_file:
          raise HTTPException(status_code=404, detail="File record not found")
          
      file_path = orm_file.file_path
      filename = orm_file.filename
      
      base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
      default_upload_dir = os.path.join(base_dir, "uploads")
      config_upload_dir = os.getenv("UPLOAD_DIR", default_upload_dir)
      
      allowed_dirs = [
          os.path.abspath(default_upload_dir),
          os.path.abspath(os.path.join(base_dir, config_upload_dir) if not os.path.isabs(config_upload_dir) else config_upload_dir)
      ]
      
      file_path_abs = os.path.abspath(os.path.join(allowed_dirs[0], file_path) if not os.path.isabs(file_path) else file_path)
      file_path_norm = os.path.normcase(os.path.realpath(file_path_abs))
      
      is_safe = False
      for ad in allowed_dirs:
          ad_norm = os.path.normcase(os.path.realpath(ad))
          try:
              common = os.path.commonpath([ad_norm, file_path_norm])
              if os.path.normcase(common) == ad_norm and file_path_norm != ad_norm:
                  is_safe = True
                  break
          except ValueError:
              continue
              
      if not is_safe:
          logger.warning(f"Path traversal deletion block! Attempted path: {file_path}")
          raise HTTPException(status_code=403, detail="Forbidden: Deletion target path traversal blocked")
          
      if os.path.exists(file_path_abs):
          try:
              os.remove(file_path_abs)
              logger.info(f"Physical file deleted: {file_path_abs}")
          except Exception as fe:
              logger.error(f"Failed to delete physical file {file_path_abs}: {fe}")
              raise HTTPException(status_code=500, detail=f"Failed to delete physical file: {fe}")
      else:
          logger.warning(f"Physical file missing during deletion: {file_path_abs}")
          
      repo.delete_by_id(file_id)
      return {"status": "success", "message": f"文件 '{filename}' 及其数据库记录已删除成功"}
  ```

- [ ] **Step 4: 重新运行业务测试集，验证重构后的 API 业务响应依然完整**
  
  运行命令：
  ```powershell
  pytest tests/test_messages.py tests/test_upload_security.py -v
  ```
  期望输出：所有业务测试全数 PASSED。

- [ ] **Step 5: 提交 Task 2**
  
  ```bash
  git add app/interfaces/api/message_routes.py app/interfaces/api/upload_routes.py
  git commit -m "refactor: simplify endpoints and clean hand-written audit logs in message and upload routes"
  ```

---

### Task 3: 启动服务前后端验证联调

- [ ] **Step 1: 在终端后台拉起服务**
  
  运行：`python main.py`

- [ ] **Step 2: 实机功能验证（前端行为 + 审计结果确认）**
  
  - 访问控制台前端，切换到“站内信系统”发送一条测试消息。
  - 打开“审计日志”页签，验证产生了一条操作人为刚才输入者、动作为 `SEND_MESSAGE`、资源 ID 为刚生成的 ID、状态为 `success` 的审计日志，并且详情 JSON 能正常展示。
  - 切换到大文件上传页签，上传一个文件并删除它，刷新审计日志，确认产生了一条动作为 `DELETE_FILE`、资源类型为 `uploaded_file` 的成功记录。
