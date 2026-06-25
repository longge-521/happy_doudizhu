# backend/app/infrastructure/database/game_repository.py
"""游戏数据库仓储：玩家档案与对局记录的持久化"""
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from app.infrastructure.database.models import PlayerProfileORM, GameRecordORM, UserORM
from app.domain.game.entities import PlayerProfile, GameRecord

logger = logging.getLogger("hmp_ws_service")


class SQLGameRepository:

    def __init__(self, db: Session):
        self._db = db

    def get_user_by_username(self, username: str) -> Optional[UserORM]:
        return self._db.query(UserORM).filter_by(username=username).first()

    def create_user_and_profile(self, username: str, password_hash: str, nickname: str) -> tuple:
        import uuid
        player_id = f"p_{uuid.uuid4().hex[:12]}"
        user = UserORM(
            username=username,
            password=password_hash,
            player_id=player_id
        )
        self._db.add(user)
        profile = PlayerProfileORM(
            player_id=player_id,
            nickname=nickname,
            beans=10000,
            total_games=0,
            wins=0
        )
        self._db.add(profile)
        self._db.commit()
        return user, profile

    def get_or_create_profile(self, player_id: str, nickname: str) -> PlayerProfile:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if not orm:
            orm = PlayerProfileORM(player_id=player_id, nickname=nickname)
            self._db.add(orm)
            self._db.flush()
        return PlayerProfile(
            id=orm.id, player_id=orm.player_id, nickname=orm.nickname,
            beans=orm.beans, total_games=orm.total_games, wins=orm.wins,
            created_at=orm.created_at
        )

    def update_beans(self, player_id: str, beans: int) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.beans = max(0, beans)

    def update_profile_stats(self, player_id: str, beans_delta: int, is_win: bool) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.beans = max(0, orm.beans + beans_delta)
            orm.total_games += 1
            if is_win:
                orm.wins += 1

    def save_game_record(self, record: GameRecord) -> None:
        orm = GameRecordORM(
            room_id=record.room_id, player_id=record.player_id,
            role=record.role, result=record.result,
            score_change=record.score_change, multiplier=record.multiplier,
        )
        self._db.add(orm)

    def get_history(self, player_id: str, limit: int = 20) -> List[GameRecord]:
        rows = (self._db.query(GameRecordORM)
                .filter_by(player_id=player_id)
                .order_by(GameRecordORM.created_at.desc())
                .limit(limit).all())
        return [GameRecord(
            id=r.id, room_id=r.room_id, player_id=r.player_id,
            role=r.role, result=r.result, score_change=r.score_change,
            multiplier=r.multiplier, created_at=r.created_at
        ) for r in rows]

    def get_leaderboard(self, limit: int = 20) -> List[PlayerProfile]:
        rows = (self._db.query(PlayerProfileORM)
                .order_by(PlayerProfileORM.beans.desc())
                .limit(limit).all())
        return [PlayerProfile(
            id=r.id, player_id=r.player_id, nickname=r.nickname,
            beans=r.beans, total_games=r.total_games, wins=r.wins,
            created_at=r.created_at
        ) for r in rows]
