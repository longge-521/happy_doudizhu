import json
import logging
import os
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from app.application.message.message_app_service import MessageAppService
from app.application.upload.upload_app_service import UploadAppService
from app.interfaces.websocket.ws_routes import WSConnectionManager, _is_safe_upload_id
from app.infrastructure.database.session import transactional_session
from app.application.audit_log.audit_log_app_service import AuditLogAppService

logger = logging.getLogger("hmp_ws_service")

class WebSocketHandler:
    """管理单个 WebSocket 长连接的长生命周期协议解析、会话状态及数据收发处理器。"""

    def __init__(
        self,
        websocket: WebSocket,
        client_id: str,
        manager: WSConnectionManager,
        msg_service: MessageAppService,
        upload_service: UploadAppService,
    ):
        self.websocket = websocket
        self.client_id = client_id
        self.manager = manager
        self.msg_service = msg_service
        self.upload_service = upload_service
        self.current_upload_id = None
        
        # 提取客户端连接 IP 和 User-Agent 信息用于审计日志
        self.client_ip = websocket.client.host if websocket.client else None
        forwarded_for = websocket.headers.get("x-forwarded-for")
        if forwarded_for:
            self.client_ip = forwarded_for.split(",")[0].strip()
        else:
            real_ip = websocket.headers.get("x-real-ip")
            if real_ip:
                self.client_ip = real_ip
        self.user_agent = websocket.headers.get("user-agent")
        self.audit_service = AuditLogAppService()

    async def run(self):
        """长连接事件循环，接收文本/二进制数据包并分发处理。"""
        await self.manager.connect(self.websocket, self.client_id)
        await self.manager.broadcast(f"系统提示: 客户端 '{self.client_id}' 已上线。")
        
        try:
            while True:
                message = await self.websocket.receive()
                if "text" in message:
                    await self.handle_text(message["text"])
                elif "bytes" in message:
                    await self.handle_bytes(message["bytes"])
        except WebSocketDisconnect:
            self.manager.disconnect(self.client_id, self.websocket)
            if self.client_id not in self.manager.active_connections:
                await self.manager.broadcast(f"系统提示: 客户端 '{self.client_id}' 已下线。")
        except Exception as e:
            logger.error(f"WebSocket error on client '{self.client_id}': {e}")
            self.manager.disconnect(self.client_id, self.websocket)

    async def handle_text(self, data: str):
        """解析文本 JSON 事件并分发给应用服务。"""
        try:
            msg_data = json.loads(data)
            msg_type = msg_data.get("type", "echo")
            target = msg_data.get("target")
            message_body = msg_data.get("message", "")
            
            if msg_type == "broadcast":
                await self.manager.broadcast(f"广播来自 '{self.client_id}': {message_body}")
            elif msg_type == "send_to" and target:
                if target in self.manager.active_connections:
                    await self.manager.send_personal_message(f"私聊来自 '{self.client_id}': {message_body}", target)
                    await self.websocket.send_text(f"已向 '{target}' 发送: {message_body}")
                else:
                    await self.websocket.send_text(f"发送失败: 客户端 '{target}' 未在线")

            # WebSocket 站内信：统一走 MessageAppService → DB → WS 实时推送
            elif msg_type == "site_message":
                receiver = msg_data.get("target", "") or self.client_id
                content = msg_data.get("content", "")
                if not content:
                    await self.websocket.send_text(json.dumps({
                        "type": "site_message_ack",
                        "status": "error",
                        "message": "缺少 content(消息内容)"
                    }, ensure_ascii=False))
                else:
                    try:
                        from app.infrastructure.database import SQLMessageRepository
                        
                        # 使用临时的短生命周期 session 写入数据库，防止长连接挂载导致连接池耗尽
                        with transactional_session() as db:
                            repo = SQLMessageRepository(db)
                            temp_service = MessageAppService(repo, self.msg_service.mq_adapter)
                            msg = await temp_service.send_message(sender=self.client_id, receiver=receiver, content=content)
                        
                        # 记录成功审计日志
                        await self.audit_service.record_ws_log(
                            client_ip=self.client_ip,
                            user_agent=self.user_agent,
                            action="SEND_MESSAGE",
                            resource_type="site_message",
                            resource_id=str(msg.id) if msg else None,
                            status="success",
                            operator=self.client_id
                        )
                        
                        await self.websocket.send_text(json.dumps({
                            "type": "site_message_ack",
                            "status": "success",
                            "id": msg.id,
                            "message": f"站内信已发送 → {receiver}"
                        }, ensure_ascii=False))
                    except Exception as e:
                        logger.error(f"WS site_message failed: {e}")
                        # 记录失败审计日志
                        await self.audit_service.record_ws_log(
                            client_ip=self.client_ip,
                            user_agent=self.user_agent,
                            action="SEND_MESSAGE",
                            resource_type="site_message",
                            status="failed",
                            details=str(e),
                            operator=self.client_id
                        )
                        await self.websocket.send_text(json.dumps({
                            "type": "site_message_ack",
                            "status": "error",
                            "message": f"发送失败: {e}"
                        }, ensure_ascii=False))
            
            # 纯 WebSocket 大文件上传初始化
            elif msg_type == "upload_start":
                upload_id = msg_data.get("upload_id")
                filename = msg_data.get("filename")
                if not _is_safe_upload_id(upload_id):
                    await self.websocket.send_text(json.dumps({
                        "type": "upload_start_ack",
                        "upload_id": upload_id,
                        "status": "error",
                        "message": "上传会话ID格式不合法，包含危险字符或长度超出限制"
                    }, ensure_ascii=False))
                    self.current_upload_id = None
                    return
                
                # 新增同名文件排重校验
                try:
                    from app.infrastructure.database import SQLUploadedFileRepository
                    with transactional_session() as db:
                        repo = SQLUploadedFileRepository(db)
                        if repo.find_by_filename(filename):
                            await self.websocket.send_text(json.dumps({
                                "type": "upload_start_ack",
                                "upload_id": upload_id,
                                "status": "error",
                                "message": f"文件 '{filename}' 已存在，不支持重复上传！"
                            }, ensure_ascii=False))
                            return
                except Exception as e:
                    logger.error(f"Error checking duplicate upload in upload_start: {e}")
                
                self.current_upload_id = upload_id
                await self.websocket.send_text(json.dumps({
                    "type": "upload_start_ack",
                    "upload_id": self.current_upload_id,
                    "status": "success"
                }))
                logger.info(f"Upload started via WS for {filename}, upload_id: {self.current_upload_id}")
            
            # 断点续传：查询已完成的分片列表
            elif msg_type == "upload_resume":
                resume_upload_id = msg_data.get("upload_id")
                if not _is_safe_upload_id(resume_upload_id):
                    await self.websocket.send_text(json.dumps({
                        "type": "upload_resume_ack",
                        "upload_id": resume_upload_id,
                        "status": "error",
                        "message": "上传会话ID格式不合法"
                    }, ensure_ascii=False))
                    return
                self.current_upload_id = resume_upload_id  # 恢复会话状态
                
                completed_chunks = self.upload_service.get_completed_chunks(resume_upload_id)
                
                await self.websocket.send_text(json.dumps({
                    "type": "upload_resume_ack",
                    "upload_id": resume_upload_id,
                    "completed_chunks": completed_chunks,
                    "status": "success"
                }))
                logger.info(f"Upload resume query for {resume_upload_id}: {len(completed_chunks)} chunks found")
                
            # 纯 WebSocket 大文件流式合并
            elif msg_type == "upload_merge":
                upload_id = msg_data.get("upload_id")
                filename = msg_data.get("filename")
                total_chunks = msg_data.get("total_chunks")
                if not _is_safe_upload_id(upload_id):
                    await self.websocket.send_text(json.dumps({
                        "type": "upload_merge_ack",
                        "upload_id": upload_id,
                        "filename": filename,
                        "status": "error",
                        "message": "上传会话ID格式不合法"
                    }, ensure_ascii=False))
                    return
                
                try:
                    # 异步线程执行分片物理合并与清理
                    file_path = await self.upload_service.merge_chunks(upload_id, filename, total_chunks)
                    safe_name = os.path.basename(file_path)
                    
                    # 获取文件真实物理大小，转换为以 MB 为单位保留两位小数的浮点数
                    file_size_bytes = os.path.getsize(file_path)
                    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
                    
                    # 将上传记录写入数据库中
                    from app.infrastructure.database import SQLUploadedFileRepository
                    from app.domain.upload.entities import UploadedFile
                    uploaded_file = None
                    with transactional_session() as db:
                        repo = SQLUploadedFileRepository(db)
                        uploaded_file = UploadedFile(
                            filename=safe_name,
                            file_path=file_path,
                            file_size_mb=file_size_mb
                        )
                        repo.save(uploaded_file)
                    
                    # 记录成功审计日志
                    await self.audit_service.record_ws_log(
                        client_ip=self.client_ip,
                        user_agent=self.user_agent,
                        action="UPLOAD_FILE",
                        resource_type="uploaded_file",
                        resource_id=str(uploaded_file.id) if uploaded_file else None,
                        status="success",
                        details=f"Filename: {safe_name}, Size: {file_size_mb} MB",
                        operator=self.client_id
                    )
                    
                    await self.websocket.send_text(json.dumps({
                        "type": "upload_merge_ack",
                        "upload_id": upload_id,
                        "filename": safe_name,
                        "status": "success",
                        "path": file_path
                    }))
                    logger.info(f"File merged via WS successfully: {safe_name} -> {file_path}")
                except Exception as e:
                    logger.error(f"Error merging file chunks via WS for {filename}: {e}")
                    # 记录失败审计日志
                    await self.audit_service.record_ws_log(
                        client_ip=self.client_ip,
                        user_agent=self.user_agent,
                        action="UPLOAD_FILE",
                        resource_type="uploaded_file",
                        status="failed",
                        details=str(e),
                        operator=self.client_id
                    )
                    await self.websocket.send_text(json.dumps({
                        "type": "upload_merge_ack",
                        "upload_id": upload_id,
                        "filename": filename,
                        "status": "error",
                        "message": f"合并分片失败: {e}"
                    }))
                
            elif msg_type == "upload_abort":
                upload_id = msg_data.get("upload_id")
                if not _is_safe_upload_id(upload_id):
                    await self.websocket.send_text(json.dumps({
                        "type": "upload_abort_ack",
                        "upload_id": upload_id,
                        "status": "error",
                        "message": "上传会话ID格式不合法"
                    }, ensure_ascii=False))
                    return
                self.upload_service.abort_upload(upload_id)
                self.current_upload_id = None
                await self.websocket.send_text(json.dumps({
                    "type": "upload_abort_ack",
                    "upload_id": upload_id,
                    "status": "success"
                }))
                logger.info(f"Upload aborted via WS, cleaned temp dir for upload_id: {upload_id}")

            else:
                await self.websocket.send_text(f"收到并回显: {data}")
        except json.JSONDecodeError:
            await self.websocket.send_text(f"回显: {data}")

    async def handle_bytes(self, data: bytes):
        """处理分片二进制数据上传帧（引入 memoryview 零拷贝优化）。"""
        if len(data) >= 4 and self.current_upload_id:
            # 引入内存视图，避免 data[4:] 产生二次物理内存拷贝
            mv = memoryview(data)
            chunk_index = int.from_bytes(mv[:4], byteorder='big')
            chunk_bytes = mv[4:]
            
            # 使用 asyncio.to_thread 移出主事件循环，防止物理磁盘 IO 阻塞服务并发
            await asyncio.to_thread(self.upload_service.save_chunk, self.current_upload_id, chunk_index, chunk_bytes)
            
            # 返回分片确认 Ack
            await self.websocket.send_text(json.dumps({
                "type": "upload_chunk_ack",
                "upload_id": self.current_upload_id,
                "chunk_index": chunk_index,
                "status": "success"
            }))
        else:
            await self.websocket.send_text(f"回显: {data}")
            logger.info(f"Sent echo to '{self.client_id}': 回显: {data}")
