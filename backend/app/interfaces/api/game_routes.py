# backend/app/interfaces/api/game_routes.py
"""斗地主游戏 HTTP REST API"""
import os
import logging
logger = logging.getLogger("happy_doudizhu")
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Header
from pydantic import BaseModel, Field
from app.infrastructure.config import settings
from sqlalchemy.orm import Session

from app.infrastructure.audit_route import AuditLogRoute
from app.infrastructure.auth import (
    create_game_auth_token,
    hash_password,
    require_game_player_id,
    verify_password,
)
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/api/game", tags=["Game API"], route_class=AuditLogRoute)

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def is_allowed_avatar_content(content: bytes, file_ext: str) -> bool:
    if file_ext == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if file_ext in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if file_ext == ".gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if file_ext == ".webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def ensure_player_access(player_id: str, current_player_id: str) -> None:
    if player_id != current_player_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot access another player")


def ensure_profile_debug_mutation_allowed() -> None:
    if settings.is_production:
        raise HTTPException(
            status_code=403,
            detail="生产环境不允许手动修改欢乐豆或段位",
        )


def normalize_avatar_url(avatar_url: Optional[str]) -> Optional[str]:
    if avatar_url is None:
        return None
    normalized = avatar_url.strip()
    if not normalized:
        return None
    allowed_prefixes = ("http://", "https://", "/static/", "/api/uploads/")
    if not normalized.startswith(allowed_prefixes):
        raise HTTPException(status_code=400, detail="头像地址必须是 http(s) 或站内静态资源地址")
    return normalized


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)
    nickname: str = Field(..., min_length=1, max_length=100)


class UserLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)


class UpdateBeansRequest(BaseModel):
    beans: int = Field(..., ge=0, description="Set beans; must be non-negative")


class UpdateRankRequest(BaseModel):
    rank_id: int = Field(..., ge=1, le=36, description="Rank level, 1-36")
    sub_rank: int = Field(..., ge=1, le=4, description="Sub-rank level, 1-4")
    stars: int = Field(..., ge=0, description="Star count")


class UpdateAvatarRequest(BaseModel):
    avatar_url: Optional[str] = Field(None, max_length=500)


class UpdateProfileRequest(BaseModel):
    nickname: Optional[str] = Field(None, min_length=1, max_length=20)
    avatar_url: Optional[str] = Field(None, max_length=500)


class UpdatePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=100)
    new_password: str = Field(..., min_length=1, max_length=100)


async def acquire_token_bucket(key: str, max_capacity: int, refill_rate: float) -> bool:
    """
    Redis 原子令牌桶限流算法。
    refill_rate: 每秒恢复的令牌数。
    """
    from app.infrastructure.redis_client import redis_client
    import time
    
    lua_script = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local requested = 1
    
    local data = redis.call('hmget', key, 'tokens', 'last_updated')
    local tokens = tonumber(data[1])
    local last_updated = tonumber(data[2])
    
    if not tokens then
        tokens = capacity
        last_updated = now
    else
        local delta = math.max(0, now - last_updated)
        tokens = math.min(capacity, tokens + delta * refill_rate)
        last_updated = now
    end
    
    if tokens >= requested then
        tokens = tokens - requested
        redis.call('hmset', key, 'tokens', tokens, 'last_updated', last_updated)
        redis.call('expire', key, 86400) -- 保留 24 小时过期防止堆积
        return 1
    else
        redis.call('hmset', key, 'tokens', tokens, 'last_updated', last_updated)
        redis.call('expire', key, 86400)
        return 0
    end
    """
    try:
        now = time.time()
        result = await redis_client.eval(lua_script, 1, key, max_capacity, refill_rate, now)
        return bool(result == 1)
    except Exception as e:
        logger.error(f"[RateLimit] Lua evaluation error for {key}: {e}")
        return True  # 降级容灾：Redis 故障时放行，防止阻断正常登录注册


@router.post("/auth/register")
async def register_user(
    req: UserRegisterRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    # 1. IP 维度限流：容量 20，每秒恢复 0.5 (每分钟 30 次)
    client_ip = request.client.host if request.client else "127.0.0.1"
    ip_key = f"game:ratelimit:ip:{client_ip}"
    if not await acquire_token_bucket(ip_key, max_capacity=20, refill_rate=0.5):
        raise HTTPException(status_code=429, detail="您的操作过于频繁，请稍后再试")

    # 2. 账号维度限流：容量 10，每秒恢复 0.2 (每分钟 12 次)
    username_norm = req.username.strip().lower()
    user_key = f"game:ratelimit:user:{username_norm}"
    if not await acquire_token_bucket(user_key, max_capacity=10, refill_rate=0.2):
        raise HTTPException(status_code=429, detail="此账号操作过于频繁，请稍后再试")

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少为 6 位")
    repo = SQLGameRepository(db)
    existing = repo.get_user_by_username(username_norm)
    if existing:
        raise HTTPException(status_code=400, detail="账号已存在，请直接登录")
    user, profile = repo.create_user_and_profile(
        username_norm,
        hash_password(req.password),
        req.nickname.strip(),
    )
    return {
        "ok": True,
        "player_id": user.player_id,
        "nickname": profile.nickname,
        "username": user.username,
        "auth_token": create_game_auth_token(user.player_id),
    }


@router.post("/auth/login")
async def login_user(
    req: UserLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    # 1. IP 维度限流：容量 20，每秒恢复 0.5 (每分钟 30 次)
    client_ip = request.client.host if request.client else "127.0.0.1"
    ip_key = f"game:ratelimit:ip:{client_ip}"
    if not await acquire_token_bucket(ip_key, max_capacity=20, refill_rate=0.5):
        raise HTTPException(status_code=429, detail="您的操作过于频繁，请稍后再试")

    # 2. 账号维度限流：容量 10，每秒恢复 0.2 (每分钟 12 次)
    username_norm = req.username.strip().lower()
    user_key = f"game:ratelimit:user:{username_norm}"
    if not await acquire_token_bucket(user_key, max_capacity=10, refill_rate=0.2):
        raise HTTPException(status_code=429, detail="此账号操作过于频繁，请稍后再试")

    repo = SQLGameRepository(db)
    user = repo.get_user_by_username(username_norm)
    
    # 统一登录失败返回信息，防范用户名枚举泄露
    if not user or not verify_password(req.password, user.password):
        raise HTTPException(status_code=400, detail="用户名或密码不正确")
        
    profile = repo.get_or_create_profile(user.player_id, username_norm)
    return {
        "ok": True,
        "player_id": user.player_id,
        "nickname": profile.nickname,
        "username": user.username,
        "auth_token": create_game_auth_token(user.player_id),
    }


@router.get("/profile/{player_id}")
def get_player_profile(
    player_id: str,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "player_id": profile.player_id,
        "nickname": profile.nickname,
        "avatar_url": profile.avatar_url,
        "beans": profile.beans,
        "total_games": profile.total_games,
        "wins": profile.wins,
        "win_rate": profile.win_rate,
        "rank_id": profile.rank_id,
        "sub_rank": profile.sub_rank,
        "stars": profile.stars,
        "rank_title": profile.rank_title,
    }


@router.get("/history/{player_id}")
def get_game_history(
    player_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    records = repo.get_history(player_id, limit)
    return [
        {
            "room_id": r.room_id,
            "role": r.role,
            "result": r.result,
            "score_change": r.score_change,
            "multiplier": r.multiplier,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@router.get("/leaderboard")
def get_leaderboard(limit: int = 20, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profiles = repo.get_leaderboard(limit)
    return [
        {
            "rank": i + 1,
            "player_id": p.player_id,
            "nickname": p.nickname,
            "avatar_url": p.avatar_url,
            "beans": p.beans,
            "total_games": p.total_games,
            "win_rate": p.win_rate,
            "rank_title": p.rank_title,
        }
        for i, p in enumerate(profiles)
    ]


@router.post("/profile/{player_id}/beans")
def update_beans(
    player_id: str,
    req: UpdateBeansRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_profile_debug_mutation_allowed()
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_beans(player_id, req.beans)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "beans": updated_profile.beans,
    }


@router.post("/profile/{player_id}/rank")
def update_player_rank(
    player_id: str,
    req: UpdateRankRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_profile_debug_mutation_allowed()
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_rank_profile(player_id, req.rank_id, req.sub_rank, req.stars)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "rank_id": updated_profile.rank_id,
        "sub_rank": updated_profile.sub_rank,
        "stars": updated_profile.stars,
    }


@router.post("/profile/{player_id}/avatar")
def update_player_avatar(
    player_id: str,
    req: UpdateAvatarRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    normalized_avatar_url = normalize_avatar_url(req.avatar_url)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_avatar_url(player_id, normalized_avatar_url)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "avatar_url": updated_profile.avatar_url,
    }


@router.post("/profile/{player_id}/update")
def update_player_profile(
    player_id: str,
    req: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    if req.nickname is not None:
        repo.update_nickname(player_id, req.nickname)
    if req.avatar_url is not None:
        normalized = normalize_avatar_url(req.avatar_url)
        repo.update_avatar_url(player_id, normalized)
    updated = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "nickname": updated.nickname,
        "avatar_url": updated.avatar_url,
    }


@router.post("/profile/{player_id}/upload-avatar")
async def upload_player_avatar(
    player_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    content_type = file.content_type
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只允许上传图片格式的文件")

    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in AVATAR_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="只允许上传 png、jpg、jpeg、gif 或 webp 头像")

    content = await file.read(AVATAR_MAX_BYTES + 1)
    if len(content) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="头像文件不能超过 2MB")

    if not is_allowed_avatar_content(content, file_ext):
        raise HTTPException(status_code=400, detail="头像文件内容不是支持的图片格式")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    upload_dir = settings.UPLOAD_DIR or os.path.join(base_dir, "uploads")
    avatar_dir = os.path.join(upload_dir, "avatars")
    if not os.path.exists(avatar_dir):
        os.makedirs(avatar_dir)

    import uuid
    unique_filename = f"avatar_{player_id}_{uuid.uuid4().hex}{file_ext}"
    dest_path = os.path.join(avatar_dir, unique_filename)

    with open(dest_path, "wb") as f:
        f.write(content)

    avatar_url = f"/api/uploads/avatars/{unique_filename}"
    return {
        "ok": True,
        "avatar_url": avatar_url
    }


@router.post("/profile/{player_id}/password")
def update_player_password(
    player_id: str,
    req: UpdatePasswordRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度至少为 6 位")
    repo = SQLGameRepository(db)
    user = repo.get_user_by_id(player_id) if hasattr(SQLGameRepository, "get_user_by_id") else repo.get_user_by_player_id(player_id)
    if not user:
        raise HTTPException(status_code=404, detail="未找到对应的用户记录")

    if not verify_password(req.old_password, user.password):
        raise HTTPException(status_code=400, detail="旧密码输入错误，校验失败")

    if req.old_password == req.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")

    new_hash = hash_password(req.new_password)
    repo.update_user_password(player_id, new_hash)
    return {
        "ok": True,
        "message": "密码修改成功，请重新登录"
    }


class TicketResponse(BaseModel):
    ticket: str
    expires_in: int = 30


@router.post("/auth/ticket", response_model=TicketResponse)
async def create_websocket_ticket(
    current_player_id: str = Depends(require_game_player_id)
):
    """为已登录玩家生成单次使用、30秒有效的 WebSocket 握手票据"""
    import uuid
    ticket_id = f"ticket-{uuid.uuid4().hex}"
    
    from app.infrastructure.redis_client import redis_client
    redis_key = f"game:ws_ticket:{ticket_id}"
    await redis_client.set(redis_key, current_player_id, ex=30)
    
    return {
        "ticket": ticket_id,
        "expires_in": 30
    }


@router.post("/auth/settlement/replay")
async def replay_settlement_tasks(
    request: Request,
    api_token: Optional[str] = Header(None, alias="X-API-Token")
):
    """人工重放结算死信队列任务"""
    if settings.is_production:
        if not settings.API_TOKEN or api_token != settings.API_TOKEN:
            raise HTTPException(status_code=403, detail="Forbidden")
            
    bus = request.app.state.game_message_bus
    if not hasattr(bus, "replay_dead_letter_queue"):
        raise HTTPException(status_code=400, detail="Replay not supported by bus adapter")
        
    count = await bus.replay_dead_letter_queue()
    return {"ok": True, "replayed_count": count}


@router.get("/health/live", summary="进程存活度探活（Liveness）")
def liveness_check():
    """反映进程事件循环是否存活，不发起共享基础设施网络调用，防止网络抖动导致的无意义重启"""
    return {"status": "ok", "live": True}


@router.get("/health/ready", summary="外部就绪度探活（Readiness）")
async def readiness_check(
    request: Request,
    db: Session = Depends(get_db)
):
    """检查 Redis, RabbitMQ 以及 MySQL 的物理连通性，依赖故障时返回 503 触发外部 SLB 下线隔离"""
    from app.infrastructure.redis_client import redis_client
    from sqlalchemy import text
    
    # 1. 验证 MySQL 数据库
    try:
        db.execute(text("SELECT 1"))
    except Exception as db_err:
        logger.error(f"[ReadinessCheck] Database check failed: {db_err}")
        raise HTTPException(status_code=503, detail=f"Database check failed: {db_err}")

    # 2. 验证 Redis
    try:
        await redis_client.ping()
    except Exception as redis_err:
        logger.error(f"[ReadinessCheck] Redis check failed: {redis_err}")
        raise HTTPException(status_code=503, detail=f"Redis check failed: {redis_err}")

    # 3. 验证 RabbitMQ Message Bus
    bus = getattr(request.app.state, "game_message_bus", None)
    if not bus or not bus.channel or bus.channel.is_closed:
        logger.error("[ReadinessCheck] RabbitMQ check failed: Channel is closed or bus not found")
        raise HTTPException(status_code=503, detail="RabbitMQ check failed: Channel is closed")

    return {"status": "ok", "ready": True}
