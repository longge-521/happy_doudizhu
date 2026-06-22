import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.application.message.message_app_service import MessageAppService
from app.infrastructure.auth import verify_token
from app.infrastructure.database import SQLMessageRepository
from app.infrastructure.database.session import get_db
from app.infrastructure.audit_route import AuditLogRoute

logger = logging.getLogger("hmp_ws_service")
router = APIRouter(
    prefix="/api/messages",
    tags=["Messages"],
    dependencies=[Depends(verify_token)],
    route_class=AuditLogRoute
)

from pydantic import BaseModel, Field


class MessageSendRequest(BaseModel):
    sender: str = Field("system", max_length=50, description="发送者 ID")
    receiver: str = Field(..., min_length=1, max_length=50, description="接收者 ID")
    content: str = Field(..., min_length=1, max_length=1000, description="站内信内容")


def get_message_service(request: Request,
                        db: Session = Depends(get_db)) -> MessageAppService:
    repo = SQLMessageRepository(db)
    return MessageAppService(repo, request.app.state.mq_adapter)


@router.post("/send", summary="SEND_MESSAGE", description="site_message")
async def send_message_api(request_data: MessageSendRequest,
                           service: MessageAppService = Depends(get_message_service)):
    msg = await service.send_message(
        request_data.sender,
        request_data.receiver,
        request_data.content
    )
    return {"status": "success", "message": f"站内信已入库 (id={msg.id})", "id": msg.id}


@router.get("", summary="QUERY_MESSAGES", description="site_message")
async def get_messages_api(receiver: str = Query(...), status: str = Query("all"),
                           service: MessageAppService = Depends(get_message_service)):
    try:
        messages = await service.get_messages(receiver, status)
        result = []
        for msg in messages:
            result.append({
                "id": msg.id,
                "sender": msg.sender,
                "receiver": msg.receiver,
                "content": msg.content,
                "is_read": msg.is_read,
                "created_at": msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if msg.created_at else "",
                "updated_at": msg.updated_at.strftime("%Y-%m-%d %H:%M:%S") if msg.updated_at else "",
                "read_at": msg.read_at.strftime("%Y-%m-%d %H:%M:%S") if msg.read_at else ""
            })
        return result
    except Exception as e:
        logger.error(f"Failed to fetch site messages API: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch site messages")


@router.post("/{message_id}/read", summary="READ_MESSAGE", description="site_message")
async def mark_as_read_api(message_id: int,
                           service: MessageAppService = Depends(get_message_service)):
    success = await service.mark_as_read(message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "success", "message": f"Message {message_id} marked as read"}


@router.post("/read-all", summary="READ_ALL_MESSAGES", description="site_message")
async def mark_all_as_read_api(receiver: str = Query(...),
                               service: MessageAppService = Depends(get_message_service)):
    await service.mark_all_as_read(receiver)
    return {"status": "success", "message": f"All messages for {receiver} marked as read"}