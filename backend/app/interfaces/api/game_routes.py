# backend/app/interfaces/api/game_routes.py
"""斗地主游戏 HTTP REST API"""
from fastapi import APIRouter, Depends
from app.infrastructure.database.session import get_db
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.audit_route import AuditLogRoute
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/game", tags=["Game API"], route_class=AuditLogRoute)


@router.get("/profile/{player_id}")
def get_player_profile(player_id: str, db: Session = Depends(get_db)):
    repo = SQLGameRepository(db)
    profile = repo.get_or_create_profile(player_id, player_id)
    return {
        "player_id": profile.player_id,
        "nickname": profile.nickname,
        "beans": profile.beans,
        "total_games": profile.total_games,
        "wins": profile.wins,
        "win_rate": profile.win_rate,
    }


@router.get("/history/{player_id}")
def get_game_history(player_id: str, limit: int = 20, db: Session = Depends(get_db)):
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
    } for i, p in enumerate(profiles)]
