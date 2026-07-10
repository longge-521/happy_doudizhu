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


def calculate_fifty_k_trick_changes(
    *,
    winner_id: str,
    player_ids: list[str],
    score: int,
    base_score: int,
    multiplier: int,
) -> dict[str, int]:
    total = int(score) * int(base_score) * int(multiplier)
    losers = [player_id for player_id in player_ids if player_id != winner_id]
    if total <= 0 or len(losers) != 2:
        return {player_id: 0 for player_id in player_ids}
    first_loss = total // 2
    second_loss = total - first_loss
    return {
        winner_id: total,
        losers[0]: -first_loss,
        losers[1]: -second_loss,
    }


class GameSettlementService:
    def __init__(
        self,
        session_scope: Callable[[], ContextManager] = transactional_session,
    ):
        self._session_scope = session_scope

    @staticmethod
    def _result_hash(room: GameRoom, result: dict) -> str:
        fifty_k = result.get("fifty_k_settlement") or {}
        payload = {
            "room_id": room.room_id,
            "play_mode": getattr(room, "play_mode", "classic"),
            "landlord": room.landlord,
            "multiplier": int(result.get("multiplier", room.multiplier)),
            "scores": {
                player_id: int(score)
                for player_id, score in sorted(result.get("scores", {}).items())
            },
            "fifty_k_settlement": {
                "winner_id": fifty_k.get("winner_id"),
                "final_multiplier": fifty_k.get("final_multiplier"),
                "remaining_card_scores": fifty_k.get("remaining_card_scores", {}),
                "finish_base_changes": fifty_k.get("finish_base_changes", {}),
                "remaining_card_changes": fifty_k.get("remaining_card_changes", {}),
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

                multiplier = int(result.get("multiplier", room.multiplier))
                if getattr(room, "play_mode", "classic") == "fifty_k":
                    self._settle_fifty_k_final_locked(repo, room, result, multiplier)
                else:
                    scores = result.get("scores", {})
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

    def _settle_fifty_k_final_locked(
        self,
        repo: SQLGameRepository,
        room: GameRoom,
        result: dict,
        multiplier: int,
    ) -> None:
        detail = result.get("fifty_k_settlement") or {}
        winner_id = detail.get("winner_id") or result.get("winner")
        finish_changes = detail.get("finish_base_changes", {})
        remaining_changes = detail.get("remaining_card_changes", {})
        requested_final = {
            player.id: int(finish_changes.get(player.id, 0))
            + int(remaining_changes.get(player.id, 0))
            for player in room.players
        }
        players = {player.id: player for player in room.players}
        profiles = {}
        for player in room.players:
            if player.is_ai:
                continue
            repo.get_or_create_profile(player.id, player.nickname)
            profiles[player.id] = repo.get_profile_orm_for_update(player.id)

        actual_final = {player.id: 0 for player in room.players}
        winner_credit = 0
        for player in room.players:
            if player.id == winner_id:
                continue
            requested_loss = max(0, -requested_final[player.id])
            if player.is_ai:
                actual_loss = requested_loss
            else:
                profile = profiles[player.id]
                actual_loss = min(requested_loss, int(profile.beans))
                profile.beans -= actual_loss
            actual_final[player.id] = -actual_loss
            winner_credit += actual_loss

        winner = players[winner_id]
        actual_final[winner_id] = winner_credit
        if not winner.is_ai:
            profiles[winner_id].beans += winner_credit

        cumulative = getattr(room, "cumulative_bean_changes", {})
        total_actual = {
            player.id: int(cumulative.get(player.id, 0)) + actual_final[player.id]
            for player in room.players
        }
        detail["actual_finish_changes"] = actual_final
        detail["total_bean_changes"] = total_actual
        detail["bean_balances"] = {
            player.id: (
                int(profiles[player.id].beans)
                if not player.is_ai
                else int(getattr(room, "bean_balances", {}).get(player.id, 0))
                + actual_final[player.id]
            )
            for player in room.players
        }

        for player in room.players:
            if player.is_ai:
                continue
            is_win = player.id == winner_id
            profile = profiles[player.id]
            profile.total_games += 1
            if is_win:
                profile.wins += 1
            rank_multiplier = (
                4
                if is_win and winner_id in getattr(room, "player_triggered_boost", set())
                else 1
            )
            repo.update_rank_stats(player.id, is_win, rank_multiplier)
            repo.save_game_record(
                GameRecord(
                    room_id=room.room_id,
                    player_id=player.id,
                    role="player",
                    result="win" if is_win else "lose",
                    score_change=total_actual[player.id],
                    multiplier=multiplier,
                )
            )
    @staticmethod
    def _trick_result_hash(room: GameRoom, trick: dict, requested: dict) -> str:
        payload = {
            "room_id": room.room_id,
            "trick_no": int(trick["trick_no"]),
            "winner_id": trick["winner_id"],
            "trick_cards": list(trick.get("trick_cards", [])),
            "score_gained": int(trick.get("score_gained", 0)),
            "base_score": int(room.base_score),
            "multiplier": int(trick.get("multiplier", room.multiplier)),
            "requested_changes": requested,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def settle_fifty_k_trick(self, room: GameRoom, trick: dict) -> dict:
        player_ids = [player.id for player in room.players]
        multiplier = int(trick.get("multiplier", room.multiplier))
        requested = calculate_fifty_k_trick_changes(
            winner_id=trick["winner_id"],
            player_ids=player_ids,
            score=int(trick.get("score_gained", 0)),
            base_score=int(room.base_score),
            multiplier=multiplier,
        )
        requested_json = json.dumps(requested, ensure_ascii=False, sort_keys=True)
        result_hash = self._trick_result_hash(room, trick, requested)
        trick_no = int(trick["trick_no"])

        try:
            with self._session_scope() as db:
                SQLGameRepository(db).ensure_fifty_k_trick_settlement(
                    room.room_id,
                    trick_no,
                    result_hash,
                    requested_json,
                )
        except IntegrityError:
            pass

        with self._session_scope() as db:
            repo = SQLGameRepository(db)
            settlement = repo.get_fifty_k_trick_settlement_for_update(
                room.room_id,
                trick_no,
            )
            if settlement.result_hash != result_hash:
                raise SettlementConflictError(
                    f"房间 {room.room_id} 牌墩 {trick_no} 的结算结果摘要冲突"
                )
            if settlement.status == "completed":
                return {
                    "status": "already_completed",
                    "bean_changes": json.loads(settlement.actual_changes_json or "{}"),
                    "bean_balances": json.loads(settlement.balances_after_json or "{}"),
                    "requested_changes": json.loads(settlement.requested_changes_json),
                }

            players = {player.id: player for player in room.players}
            actual = {player_id: 0 for player_id in player_ids}
            balances = dict(getattr(room, "bean_balances", {}))
            winner_id = trick["winner_id"]
            winner_credit = 0

            for player_id in player_ids:
                if player_id == winner_id:
                    continue
                requested_loss = max(0, -int(requested.get(player_id, 0)))
                player = players[player_id]
                if player.is_ai:
                    actual_loss = requested_loss
                    balances[player_id] = max(0, int(balances.get(player_id, 0)) - actual_loss)
                else:
                    repo.get_or_create_profile(player.id, player.nickname)
                    profile = repo.get_profile_orm_for_update(player_id)
                    actual_loss = min(requested_loss, int(profile.beans))
                    profile.beans -= actual_loss
                    balances[player_id] = int(profile.beans)
                actual[player_id] = -actual_loss
                winner_credit += actual_loss

            winner = players[winner_id]
            if winner.is_ai:
                balances[winner_id] = int(balances.get(winner_id, 0)) + winner_credit
            else:
                repo.get_or_create_profile(winner.id, winner.nickname)
                winner_profile = repo.get_profile_orm_for_update(winner_id)
                winner_profile.beans += winner_credit
                balances[winner_id] = int(winner_profile.beans)
            actual[winner_id] = winner_credit

            settlement.actual_changes_json = json.dumps(actual, ensure_ascii=False, sort_keys=True)
            settlement.balances_after_json = json.dumps(balances, ensure_ascii=False, sort_keys=True)
            settlement.status = "completed"
            settlement.attempts += 1
            settlement.last_error = None
            settlement.completed_at = datetime.datetime.now()

        return {
            "status": "completed",
            "bean_changes": actual,
            "bean_balances": balances,
            "requested_changes": requested,
        }
    def _record_failure(self, room_id: str, exc: Exception) -> None:
        try:
            with self._session_scope() as db:
                SQLGameRepository(db).mark_settlement_failure(
                    room_id,
                    str(exc),
                )
        except Exception:
            logger.exception("记录结算失败状态时发生异常: room_id=%s", room_id)
