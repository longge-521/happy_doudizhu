# backend/app/interfaces/api/game_routes.py
"""斗地主游戏 HTTP REST API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.infrastructure.database.session import get_db
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.audit_route import AuditLogRoute
from app.infrastructure.auth import create_game_auth_token, hash_password, require_game_player_id, verify_password
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/game", tags=["Game API"], route_class=AuditLogRoute)


def ensure_player_access(player_id: str, current_player_id: str) -> None:
    if player_id != current_player_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot access another player")


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4, max_length=100)
    nickname: str = Field(..., min_length=1, max_length=100)


class UserLoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4, max_length=100)


class UpdateBeansRequest(BaseModel):
    beans: int = Field(..., ge=0, description="Set beans; must be non-negative")


class UpdateRankRequest(BaseModel):
    rank_id: int = Field(..., ge=1, le=36, description="Rank level, 1-36")
    sub_rank: int = Field(..., ge=1, le=4, description="Sub-rank level, 1-4")
    stars: int = Field(..., ge=0, description="Star count")



@router.post("/auth/register")
def register_user(req: UserRegisterRequest, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    username_norm = req.username.strip().lower()
    existing = repo.get_user_by_username(username_norm)
    if existing:
        raise HTTPException(status_code=400, detail="账号已存在，请直接登录")
    user, profile = repo.create_user_and_profile(username_norm, hash_password(req.password), req.nickname.strip())
    return {
        "ok": True,
        "player_id": user.player_id,
        "nickname": profile.nickname,
        "username": user.username,
        "auth_token": create_game_auth_token(user.player_id),
    }


@router.post("/auth/login")
def login_user(req: UserLoginRequest, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    username_norm = req.username.strip().lower()
    user = repo.get_user_by_username(username_norm)
    if not user:
        raise HTTPException(status_code=400, detail="账号不存在，请先注册")
    if not verify_password(req.password, user.password):
        raise HTTPException(status_code=400, detail="密码不正确")
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
        "beans": profile.beans,
        "total_games": profile.total_games,
        "wins": profile.wins,
        "win_rate": profile.win_rate,
        "rank_id": profile.rank_id,
        "sub_rank": profile.sub_rank,
        "stars": profile.stars,
        "rank_title": profile.rank_title
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
    return [{
        "room_id": r.room_id,
        "role": r.role,
        "result": r.result,
        "score_change": r.score_change,
        "multiplier": r.multiplier,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in records]


@router.get("/leaderboard")
def get_leaderboard(limit: int = 20, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profiles = repo.get_leaderboard(limit)
    return [{
        "rank": i + 1,
        "player_id": p.player_id,
        "nickname": p.nickname,
        "beans": p.beans,
        "total_games": p.total_games,
        "win_rate": p.win_rate,
        "rank_title": p.rank_title,
    } for i, p in enumerate(profiles)]


@router.post("/profile/{player_id}/beans")
def update_beans(
    player_id: str,
    req: UpdateBeansRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
    ensure_player_access(player_id, current_player_id)
    repo = SQLGameRepository(db)
    repo.get_or_create_profile(player_id, player_id)
    repo.update_beans(player_id, req.beans)
    updated_profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "ok": True,
        "player_id": player_id,
        "beans": updated_profile.beans
    }


@router.post("/profile/{player_id}/rank")
def update_player_rank(
    player_id: str,
    req: UpdateRankRequest,
    db: Session = Depends(get_db),
    current_player_id: str = Depends(require_game_player_id),
):
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
        "stars": updated_profile.stars
    }
