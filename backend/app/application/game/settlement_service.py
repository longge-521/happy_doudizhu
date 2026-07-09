import datetime
import hashlib
import json
import logging
from typing import Callable, ContextManager, Literal

from sqlalchemy.exc import IntegrityError

from app.domain.game.entities import GameRecord
from app.domain.game.room import GameRoom
from app.infrastructure.database.game_repository import SQLGameRepository
from app.infrastructure.database.session import transactional_session

logger = logging.getLogger("happy_doudizhu")


class SettlementConflictError(RuntimeError):
    pass


class GameSettlementService:
    def __init__(
        self,
        session_scope: Callable[[], ContextManager] = transactional_session,
    ):
        self._session_scope = session_scope

    @staticmethod
    def _result_hash(room: GameRoom, result: dict) -> str:
        payload = {
            "room_id": room.room_id,
            "landlord": room.landlord,
            "multiplier": int(result.get("multiplier", room.multiplier)),
            "scores": {
                player_id: int(score)
                for player_id, score in sorted(result.get("scores", {}).items())
            },
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def settle(
        self,
        room: GameRoom,
        result: dict,
    ) -> Literal["completed", "already_completed"]:
        result_hash = self._result_hash(room, result)

        try:
            with self._session_scope() as db:
                SQLGameRepository(db).ensure_settlement(room.room_id, result_hash)
        except IntegrityError:
            # 并发结算可能同时创建主记录；唯一约束决定唯一事实，
            # 后续加锁读取会校验其摘要。
            pass

        try:
            with self._session_scope() as db:
                repo = SQLGameRepository(db)
                settlement = repo.get_settlement_for_update(room.room_id)
                if settlement.result_hash != result_hash:
                    raise SettlementConflictError(
                        f"房间 {room.room_id} 的结算结果摘要冲突"
                    )
                if settlement.status == "completed":
                    return "already_completed"

                scores = result.get("scores", {})
                multiplier = int(result.get("multiplier", room.multiplier))
                for player in room.players:
                    if player.is_ai:
                        continue
                    score_change = int(scores.get(player.id, 0))
                    is_win = score_change > 0
                    repo.get_or_create_profile(player.id, player.nickname)
                    repo.update_profile_stats(player.id, score_change, is_win)
                    repo.update_rank_stats(player.id, is_win, multiplier)
                    repo.save_game_record(
                        GameRecord(
                            room_id=room.room_id,
                            player_id=player.id,
                            role=(
                                "landlord"
                                if player.id == room.landlord
                                else "farmer"
                            ),
                            result="win" if is_win else "lose",
                            score_change=score_change,
                            multiplier=multiplier,
                        )
                    )

                settlement.status = "completed"
                settlement.attempts += 1
                settlement.last_error = None
                settlement.completed_at = datetime.datetime.now()
            return "completed"
        except SettlementConflictError:
            raise
        except Exception as exc:
            self._record_failure(room.room_id, exc)
            raise

    def _record_failure(self, room_id: str, exc: Exception) -> None:
        try:
            with self._session_scope() as db:
                SQLGameRepository(db).mark_settlement_failure(
                    room_id,
                    str(exc),
                )
        except Exception:
            logger.exception("记录结算失败状态时发生异常: room_id=%s", room_id)
