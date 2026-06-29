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
            created_at=orm.created_at,
            rank_id=orm.rank_id, sub_rank=orm.sub_rank, stars=orm.stars
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
            created_at=r.created_at,
            rank_id=r.rank_id, sub_rank=r.sub_rank, stars=r.stars
        ) for r in rows]

    def update_rank_profile(self, player_id: str, rank_id: int, sub_rank: int, stars: int) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if orm:
            orm.rank_id = max(1, min(36, rank_id))
            orm.sub_rank = max(1, min(4, sub_rank))
            orm.stars = max(0, stars)

    def update_rank_stats(self, player_id: str, is_win: bool, multiplier: int) -> None:
        orm = self._db.query(PlayerProfileORM).filter_by(player_id=player_id).first()
        if not orm:
            return
        
        # 1. 判定当前段位所需的满星数
        # 1-9级：3星；10-21级：4星；22-35级：5星；36级(至尊)：无限制
        if orm.rank_id < 10:
            max_stars = 3
        elif orm.rank_id < 22:
            max_stars = 4
        else:
            max_stars = 5

        if is_win:
            # 2. 赢牌加星：multiplier >= 4 为爆发胜利 +2星，否则 +1星
            delta = 2 if multiplier >= 4 else 1
            if orm.rank_id >= 36:
                # 至尊不限制子级别，无限累加星星
                orm.stars += delta
                return
                
            orm.stars += delta
            # 星星溢出，小段位晋级
            while orm.stars >= max_stars:
                orm.stars -= max_stars
                orm.sub_rank -= 1
                
                # 子级别溢出(小于1)，大级别晋升
                if orm.sub_rank < 1:
                    orm.sub_rank = 4
                    orm.rank_id += 1
                    
                    if orm.rank_id >= 36:
                        # 满阶升入至尊
                        orm.rank_id = 36
                        orm.sub_rank = 1
                        # 溢出星不作额外处理，但跳出循环
                        break
                    
                    # 重新刷新当前段位满星数
                    if orm.rank_id < 10:
                        max_stars = 3
                    elif orm.rank_id < 22:
                        max_stars = 4
                    else:
                        max_stars = 5
        else:
            # 3. 输牌扣星：最低段位(包身工IV 0星)不扣星，其他段位均需扣星
            if orm.rank_id == 1 and orm.sub_rank == 4 and orm.stars == 0:
                return
            if orm.rank_id >= 36:
                # 至尊段位输球扣星，但不降段
                orm.stars = max(0, orm.stars - 1)
                return
                
            orm.stars -= 1
            # 掉星降级
            if orm.stars < 0:
                if orm.sub_rank < 4:
                    orm.sub_rank += 1
                    # 降小级，星星设定为：新的小段位满星 - 1 
                    orm.stars = max_stars - 1
                else:
                    # 子级别已到最低 (sub_rank == 4)
                    if orm.rank_id < 22:
                        # 10-21 级大段位保护，不降级
                        orm.stars = 0
                    else:
                        # 22-35 级无保护降大级
                        orm.rank_id -= 1
                        orm.sub_rank = 1
                        
                        # 降大级后的满星扣减
                        new_max = 3 if orm.rank_id < 10 else (4 if orm.rank_id < 22 else 5)
                        orm.stars = new_max - 1
