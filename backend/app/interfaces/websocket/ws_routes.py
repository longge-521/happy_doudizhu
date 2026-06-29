import time
import logging
import re
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.application.message.message_app_service import MessageAppService
from app.application.upload.upload_app_service import UploadAppService

logger = logging.getLogger("hmp_ws_service")
router = APIRouter(tags=["WebSocket"])

def _is_safe_upload_id(upload_id: str) -> bool:
    """校验 upload_id 是否安全，防范路径穿越与字符注入"""
    if not upload_id or not isinstance(upload_id, str):
        return False
    return bool(re.match(r"^[a-zA-Z0-9_\-\.]+$", upload_id)) and 5 <= len(upload_id) <= 150

class WSConnectionManager:
    """管理活跃的 WebSocket 长连接与广播/推送事件，支持同账号多标签页并存。"""
    
    def __init__(self):
        self.active_connections: Dict[str, list] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        self.active_connections[client_id].append(websocket)
        logger.info(f"Client '{client_id}' connected (Socket count: {len(self.active_connections[client_id])}). Total active clients: {len(self.active_connections)}")

    def disconnect(self, client_id: str, websocket: WebSocket):
        if client_id in self.active_connections:
            if websocket in self.active_connections[client_id]:
                self.active_connections[client_id].remove(websocket)
                logger.info(f"Socket disconnected for Client '{client_id}'. Remaining sockets: {len(self.active_connections[client_id])}")
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
                logger.info(f"Client '{client_id}' has no active sockets left. Removed from active list. Total active clients: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, client_id: str):
        sockets = self.active_connections.get(client_id)
        if sockets:
            for ws in list(sockets):
                try:
                    await ws.send_text(message)
                    logger.info(f"Sent to '{client_id}' on socket {id(ws)}: {message}")
                except Exception as e:
                    logger.error(f"Error sending message to client '{client_id}' on socket {id(ws)}: {e}")
                    self.disconnect(client_id, ws)

    async def broadcast(self, message: str):
        logger.info(f"Broadcasting: {message}")
        for client_id, sockets in list(self.active_connections.items()):
            for ws in list(sockets):
                try:
                    await ws.send_text(message)
                except Exception as e:
                    logger.error(f"Error broadcasting message to '{client_id}' on socket {id(ws)}, disconnecting: {e}")
                    self.disconnect(client_id, ws)

def get_websocket_manager(websocket: WebSocket) -> WSConnectionManager:
    return websocket.app.state.websocket_manager

def get_message_service(websocket: WebSocket) -> MessageAppService:
    # 返回不带持久 DB Session 的应用服务，具体 DB 操作在长连接内部动态获取以防连接池耗尽
    return MessageAppService(None, websocket.app.state.mq_adapter)

def get_upload_service(websocket: WebSocket) -> UploadAppService:
    return websocket.app.state.upload_service

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    manager: WSConnectionManager = Depends(get_websocket_manager),
    msg_service: MessageAppService = Depends(get_message_service),
    upload_service: UploadAppService = Depends(get_upload_service)
):
    # 验证 WebSocket 握手 Token 凭证，防范未授权接入
    from app.infrastructure.auth import verify_ws_token
    if not verify_ws_token(websocket.query_params):
        await websocket.accept()
        await websocket.close(code=1008, reason="Unauthorized: Invalid token")
        return

    from app.interfaces.websocket.handler import WebSocketHandler
    handler = WebSocketHandler(websocket, client_id, manager, msg_service, upload_service)
    await handler.run()


@router.websocket("/hmp_ws_service/repository/mirror/v2.0")
async def repository_mirror_ws_endpoint(
    websocket: WebSocket,
    manager: WSConnectionManager = Depends(get_websocket_manager)
):
    """物理机系统连接的镜像仓库端点，用于心跳与状态维持。"""
    client_id = f"mirror_client_{int(time.time())}"
    await manager.connect(websocket, client_id)
    await manager.broadcast(f"系统提示: 镜像仓库 WebSocket 客户端 '{client_id}' 已上线。")
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received from mirror WS ({client_id}): {data}")
            await websocket.send_text(f"echo: {data}")
    except WebSocketDisconnect:
        manager.disconnect(client_id, websocket)
        if client_id not in manager.active_connections:
            await manager.broadcast(f"系统提示: 镜像仓库 WebSocket 客户端 '{client_id}' 已下线。")
    except Exception as e:
        logger.error(f"WebSocket error on mirror WS client '{client_id}': {e}")
        manager.disconnect(client_id, websocket)
