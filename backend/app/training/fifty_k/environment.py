"""复用领域规则的 510K 自博弈环境。"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.domain.game.ai_strategy import generate_legal_actions_dz
from app.domain.game.card import sort_cards
from app.domain.game.room import GamePhase, GameRoom, LastPlay, Player


PLAYER_IDS = ("p1", "p2", "p3")


def terminal_reward(player_id: str, scores: Dict[str, int], winner_id: str) -> float:
    """首个出完的胜局奖励必须压倒最多 140 分的分牌差。"""
    other_scores = [score for other_id, score in scores.items() if other_id != player_id]
    average_other_score = sum(other_scores) / len(other_scores) if other_scores else 0
    return (1000 if player_id == winner_id else 0) + scores.get(player_id, 0) - average_other_score


@dataclass(frozen=True)
class StepResult:
    done: bool
    next_player_id: Optional[str]
    rewards: Optional[Dict[str, float]] = None
    winner_id: Optional[str] = None
    scores: Optional[Dict[str, int]] = None


class FiftyKSelfPlayEnv:
    """三人对称、信息不泄露的 510K 离线对局环境。"""

    def __init__(self, seed: Optional[int] = None, base_score: int = 1) -> None:
        self._random = random.Random(seed)
        self.base_score = base_score
        self.room: Optional[GameRoom] = None

    def reset(self) -> GameRoom:
        players = [Player(id=player_id, nickname=player_id, is_ai=True) for player_id in PLAYER_IDS]
        room = GameRoom.create(f"self_play_{self._random.randrange(1 << 30)}", players, base_score=self.base_score)
        room.play_mode = "fifty_k"

        deck = list(range(54))
        self._random.shuffle(deck)
        room.hands = {
            PLAYER_IDS[0]: sort_cards(deck[0:18]),
            PLAYER_IDS[1]: sort_cards(deck[18:36]),
            PLAYER_IDS[2]: sort_cards(deck[36:54]),
        }
        room.bottom_cards = []
        room.phase = GamePhase.PLAYING
        room.last_play = LastPlay()
        room.pass_count = 0
        room.multiplier = 1
        room.scores = {player_id: 0 for player_id in PLAYER_IDS}
        room.current_trick_cards = []
        room.trick_no = 0
        room.cumulative_bean_changes = {player_id: 0 for player_id in PLAYER_IDS}
        room.bean_balances = {}
        room.all_played_cards = []
        room.play_history = []
        room.current_turn = next(player_id for player_id, hand in room.hands.items() if 2 in hand)
        self.room = room
        return room

    def legal_actions(self, player_id: str) -> List[List[int]]:
        room = self._require_room()
        if player_id != room.current_turn:
            return []
        return generate_legal_actions_dz(
            room.hands[player_id],
            room.last_play.card_play,
            must_play=room.last_play.card_play is None,
            play_mode="fifty_k",
        )

    def step(self, player_id: str, action: List[int]) -> StepResult:
        room = self._require_room()
        if player_id != room.current_turn:
            raise ValueError("不是当前自博弈玩家的回合")
        legal_actions = self.legal_actions(player_id)
        if action not in legal_actions:
            raise ValueError("自博弈动作不合法")

        result = room.play_cards(player_id, action) if action else room.pass_turn(player_id)
        if not result.get("success"):
            raise RuntimeError(result.get("error", "自博弈动作执行失败"))

        if room.phase != GamePhase.SETTLING:
            return StepResult(done=False, next_player_id=room.current_turn)

        settlement = room.settle()
        winner_id = settlement["winner"]
        fifty_k_settlement = settlement.get("fifty_k_settlement") or {}
        reward_scores = fifty_k_settlement.get("penalty_adjusted_scores") or settlement["scores"]
        rewards = {
            current_player_id: terminal_reward(current_player_id, reward_scores, winner_id)
            for current_player_id in PLAYER_IDS
        }
        return StepResult(
            done=True,
            next_player_id=None,
            rewards=rewards,
            winner_id=winner_id,
            scores=dict(reward_scores),
        )

    def _require_room(self) -> GameRoom:
        if self.room is None:
            raise RuntimeError("请先调用 reset()")
        return self.room
