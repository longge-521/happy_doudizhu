"""510K 公开信息残局搜索。"""
from __future__ import annotations

import copy
import hashlib
import json
import random
from typing import Callable, List, Sequence

from app.domain.game.card import sort_cards
from app.domain.game.room import GamePhase, GameRoom


FIFTY_K_SEARCH_OWN_CARD_LIMIT = 9
FIFTY_K_SEARCH_OPPONENT_CARD_LIMIT = 5
FIFTY_K_SEARCH_DETERMINIZATIONS = 1
FIFTY_K_SEARCH_CANDIDATE_LIMIT = 2

RankActions = Callable[[GameRoom, str], Sequence[Sequence[int]]]


def should_search_fifty_k_endgame(room: GameRoom, player_id: str) -> bool:
    """自己进入残局或任一对手听牌时才启用搜索。"""
    if getattr(room, "play_mode", "classic") != "fifty_k":
        return False
    own_remaining = len(room.hands.get(player_id, []))
    opponent_remaining = [
        len(room.hands.get(player.id, []))
        for player in room.players
        if player.id != player_id
    ]
    return (
        own_remaining <= FIFTY_K_SEARCH_OWN_CARD_LIMIT
        or bool(opponent_remaining)
        and min(opponent_remaining) <= FIFTY_K_SEARCH_OPPONENT_CARD_LIMIT
    )


def _public_state_seed(room: GameRoom, observer_id: str) -> int:
    payload = {
        "observer": observer_id,
        "hand": sorted(room.hands.get(observer_id, [])),
        "played": list(getattr(room, "all_played_cards", [])),
        "remaining": {
            player.id: len(room.hands.get(player.id, []))
            for player in room.players
        },
        "current_turn": room.current_turn,
        "last_play_player": room.last_play.player,
        "last_play_cards": list(room.last_play.cards),
        "pass_count": int(room.pass_count),
        "trick_no": int(getattr(room, "trick_no", 0)),
        "scores": dict(getattr(room, "scores", {})),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big")


def _public_determinized_rooms(
    room: GameRoom,
    observer_id: str,
    count: int,
) -> List[GameRoom]:
    """按公开剩余张数重分暗牌，不读取两名对手的真实牌面。"""
    base_state = copy.deepcopy(room.to_dict())
    observer_hand = list(room.hands.get(observer_id, []))
    opponent_ids = [player.id for player in room.players if player.id != observer_id]
    visible_cards = set(observer_hand)
    visible_cards.update(getattr(room, "all_played_cards", []))
    unseen_cards = [card_id for card_id in range(54) if card_id not in visible_cards]
    opponent_counts = {
        opponent_id: len(room.hands.get(opponent_id, []))
        for opponent_id in opponent_ids
    }
    if sum(opponent_counts.values()) != len(unseen_cards):
        raise ValueError("510K 公开信息无法按对手剩余张数完整分配未见牌")

    rng = random.Random(_public_state_seed(room, observer_id))
    rooms: List[GameRoom] = []
    for _ in range(max(1, count)):
        shuffled_cards = list(unseen_cards)
        rng.shuffle(shuffled_cards)
        state = copy.deepcopy(base_state)
        state["hands"][observer_id] = list(observer_hand)
        offset = 0
        for opponent_id in opponent_ids:
            hand_size = opponent_counts[opponent_id]
            state["hands"][opponent_id] = sort_cards(
                shuffled_cards[offset:offset + hand_size]
            )
            offset += hand_size
        rooms.append(GameRoom.from_dict(state))
    return rooms


def _apply_action(room: GameRoom, player_id: str, action: Sequence[int]) -> None:
    result = (
        room.play_cards(player_id, list(action))
        if action
        else room.pass_turn(player_id)
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error", "510K 搜索动作执行失败"))


def _terminal_value(room: GameRoom, player_id: str) -> float:
    settlement = room.settle()
    if not settlement.get("success"):
        raise RuntimeError(settlement.get("error", "510K 搜索终局结算失败"))
    fifty_k_settlement = settlement.get("fifty_k_settlement") or {}
    scores = fifty_k_settlement.get("penalty_adjusted_scores") or settlement["scores"]
    other_scores = [score for pid, score in scores.items() if pid != player_id]
    average_other_score = sum(other_scores) / len(other_scores) if other_scores else 0
    return (
        (1000 if settlement["winner"] == player_id else 0)
        + scores.get(player_id, 0)
        - average_other_score
    )


def choose_fifty_k_endgame_action(
    room: GameRoom,
    player_id: str,
    actions: Sequence[Sequence[int]],
    rank_actions: RankActions,
    *,
    determinizations: int = FIFTY_K_SEARCH_DETERMINIZATIONS,
    max_steps: int = 300,
) -> List[int]:
    """对规则候选执行公开信息模拟，平分时保留原规则顺序。"""
    selected_actions = [
        list(action)
        for action in actions[:FIFTY_K_SEARCH_CANDIDATE_LIMIT]
    ]
    if not selected_actions:
        raise ValueError("510K 残局搜索缺少合法候选")

    public_rooms = _public_determinized_rooms(
        room,
        player_id,
        determinizations,
    )
    action_values: List[float] = []
    for action in selected_actions:
        sampled_values: List[float] = []
        for public_room in public_rooms:
            rollout_room = GameRoom.from_dict(copy.deepcopy(public_room.to_dict()))
            _apply_action(rollout_room, player_id, action)
            for _ in range(max_steps):
                if rollout_room.phase == GamePhase.SETTLING:
                    sampled_values.append(_terminal_value(rollout_room, player_id))
                    break
                current_player_id = rollout_room.current_turn
                ranked = rank_actions(rollout_room, current_player_id)
                if not ranked:
                    raise RuntimeError("510K 搜索未生成合法后续动作")
                _apply_action(rollout_room, current_player_id, ranked[0])
            else:
                raise RuntimeError(f"510K 搜索未在 {max_steps} 步内结束")
        action_values.append(sum(sampled_values) / len(sampled_values))

    best_index = max(range(len(action_values)), key=action_values.__getitem__)
    return selected_actions[best_index]
