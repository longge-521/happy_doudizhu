"""510K 各自为战动作价值模型与已训练权重加载器。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List, Optional, Sequence

from app.domain.game.card import Card
from app.domain.game.card_type import CardType, detect_card_type

try:
    import torch
    import torch.nn as nn
except ImportError:  # 生产环境未安装 AI 依赖时必须保持规则 AI 可用。
    torch = None
    nn = None

if TYPE_CHECKING:
    from app.domain.game.ai_strategy import AIContext
    from app.domain.game.card_type import CardPlay


logger = logging.getLogger(__name__)

FIFTY_K_RULES_VERSION = "fifty_k_v1"
FIFTY_K_FEATURES_VERSION = "public_state_v3"
CARD_VECTOR_SIZE = 54
HISTORY_LENGTH = 15
FIFTY_K_HISTORY_STEP_SIZE = CARD_VECTOR_SIZE + 3 + 1
FIFTY_K_STATIC_CARD_GROUPS = 7
FIFTY_K_HISTORY_OFFSET = CARD_VECTOR_SIZE * FIFTY_K_STATIC_CARD_GROUPS
FIFTY_K_PUBLIC_STATE_OFFSET = (
    FIFTY_K_HISTORY_OFFSET + HISTORY_LENGTH * FIFTY_K_HISTORY_STEP_SIZE
)
FIFTY_K_PUBLIC_STATE_SIZE = 14
FIFTY_K_STRUCTURE_OFFSET = FIFTY_K_PUBLIC_STATE_OFFSET + FIFTY_K_PUBLIC_STATE_SIZE
FIFTY_K_STRUCTURE_SIZE = 15
STRUCTURE_SPLIT_BOMB_INDEX = 4
FIFTY_K_FEATURE_SIZE = FIFTY_K_STRUCTURE_OFFSET + FIFTY_K_STRUCTURE_SIZE
# 手牌、候选动作、三家公开出牌、上手、五步历史、未出现牌和 7 个局面标量。


def _card_vector(cards: Iterable[int]) -> List[float]:
    vector = [0.0] * CARD_VECTOR_SIZE
    for card_id in cards:
        if isinstance(card_id, int) and 0 <= card_id < CARD_VECTOR_SIZE:
            vector[card_id] = 1.0
    return vector


def _relative_player_ids(ctx: "AIContext") -> List[str]:
    player_ids = list(ctx.player_ids or [])
    if ctx.ai_id not in player_ids:
        player_ids.insert(0, ctx.ai_id)
    own_index = player_ids.index(ctx.ai_id)
    relative_ids = player_ids[own_index:] + player_ids[:own_index]
    while len(relative_ids) < 3:
        relative_ids.append(f"__missing_player_{len(relative_ids)}")
    return relative_ids[:3]


def _score_value(cards: Sequence[int]) -> int:
    score_by_rank = {2: 5, 7: 10, 10: 20}
    return sum(score_by_rank.get(Card.from_id(card_id).rank, 0) for card_id in cards)


def _rank_counts(cards: Sequence[int]) -> Counter:
    return Counter(Card.from_id(card_id).rank for card_id in cards)


def _contains_straight_rank(counts: Counter, target_rank: int) -> bool:
    ranks = sorted(rank for rank, count in counts.items() if count and rank < 12)
    run: List[int] = []
    for rank in ranks:
        if run and rank != run[-1] + 1:
            if len(run) >= 5 and target_rank in run:
                return True
            run = []
        run.append(rank)
    return len(run) >= 5 and target_rank in run


def _remaining_cards(hand: Sequence[int], action: Sequence[int]) -> List[int]:
    remaining = list(hand)
    for card_id in action:
        remaining.remove(card_id)
    return remaining


def _structure_features(hand: Sequence[int], action: Sequence[int]) -> List[float]:
    before = _rank_counts(hand)
    removed = _rank_counts(action)
    after_cards = _remaining_cards(hand, action)
    after = _rank_counts(after_cards)
    play = detect_card_type(list(action), play_mode="fifty_k") if action else None

    split_pair = any(before[rank] >= 2 and after[rank] == 1 for rank in removed)
    split_triple = any(before[rank] >= 3 and 0 < after[rank] < 3 for rank in removed)
    split_bomb = any(
        before[rank] == 4
        and removed[rank] > 0
        and not (
            play is not None
            and play.card_type == CardType.BOMB
            and play.main_rank == rank
        )
        for rank in removed
    )
    split_straight = any(
        _contains_straight_rank(before, rank) and 0 < after[rank]
        for rank in removed
    )

    wing_ranks: List[int] = []
    if play and play.card_type in {
        CardType.TRIPLE_ONE,
        CardType.TRIPLE_TWO,
        CardType.FOUR_TWO_SINGLE,
        CardType.FOUR_TWO_PAIR,
    }:
        wing_ranks = [rank for rank in removed if rank != play.main_rank]

    action_type = play.card_type if play else None
    remaining_rank_count = len(after)
    control_count = sum(Card.from_id(card_id).rank >= 11 for card_id in action)
    return [
        min(len(after_cards), 18) / 18.0,
        min(remaining_rank_count, 15) / 15.0,
        1.0 if split_pair else 0.0,
        1.0 if split_triple else 0.0,
        1.0 if split_bomb else 0.0,
        1.0 if split_straight else 0.0,
        (sum(wing_ranks) / len(wing_ranks) / 14.0) if wing_ranks else 0.0,
        min(_score_value(after_cards), 140) / 140.0,
        min(_score_value(action), 140) / 140.0,
        min(control_count, 4) / 4.0,
        min(len(action), 18) / 18.0,
        1.0 if action_type == CardType.FIFTY_K_TRUE else 0.0,
        1.0 if action_type == CardType.FIFTY_K_FALSE else 0.0,
        1.0 if action_type == CardType.BOMB else 0.0,
        1.0 if action_type == CardType.ROCKET else 0.0,
    ]


def build_fifty_k_features(
    hand: Sequence[int],
    action: Sequence[int],
    last_play: Optional["CardPlay"],
    ctx: "AIContext",
) -> List[float]:
    """构建只含己方手牌与公开信息的对称动作价值特征。"""
    player_ids = _relative_player_ids(ctx)
    played_by_player = {player_id: [] for player_id in player_ids}
    history = list(ctx.play_history or [])
    for record in history:
        player_id = record.get("player")
        if player_id in played_by_player:
            played_by_player[player_id].extend(record.get("cards") or [])

    features: List[float] = []
    features.extend(_card_vector(hand))
    features.extend(_card_vector(action))
    for player_id in player_ids:
        features.extend(_card_vector(played_by_player[player_id]))
    features.extend(_card_vector(last_play.cards if last_play else []))

    features.extend(_card_vector(getattr(ctx, "unseen_cards", [])))

    recent_history = history[-HISTORY_LENGTH:]
    for _ in range(HISTORY_LENGTH - len(recent_history)):
        features.extend([0.0] * FIFTY_K_HISTORY_STEP_SIZE)
    for record in recent_history:
        cards = record.get("cards") or []
        features.extend(_card_vector(cards))
        record_player_id = record.get("player")
        features.extend([
            1.0 if record_player_id == player_id else 0.0
            for player_id in player_ids
        ])
        features.append(1.0 if record_player_id and not cards else 0.0)

    current_scores = getattr(ctx, "current_scores", {})
    features.extend([
        min(max(current_scores.get(player_id, 0), 0), 140) / 140.0
        for player_id in player_ids
    ])
    last_play_from = getattr(ctx, "last_play_from", None)
    features.extend([
        1.0 if last_play_from == player_id else 0.0
        for player_id in player_ids
    ])
    remaining = getattr(ctx, "player_remaining", {})
    opponent_counts = [remaining.get(player_id, 18) for player_id in player_ids[1:3]]
    opponent_counts.extend([18] * (2 - len(opponent_counts)))
    features.extend([
        min(len(hand), 18) / 18.0,
        min(opponent_counts[0], 18) / 18.0,
        min(opponent_counts[1], 18) / 18.0,
        min(max(getattr(ctx, "trick_no", 0), 0), 54) / 54.0,
        min(getattr(ctx, "current_trick_score", 0), 140) / 140.0,
        min(getattr(ctx, "current_multiplier", 1), 16) / 16.0,
        min(getattr(ctx, "pass_count", 0), 2) / 2.0,
        1.0 if last_play is None else 0.0,
    ])
    features.extend(_structure_features(hand, action))

    if len(features) != FIFTY_K_FEATURE_SIZE:
        raise ValueError(f"510K 特征长度异常: {len(features)} != {FIFTY_K_FEATURE_SIZE}")
    return features


if nn is not None:
    class FiftyKActionValueModel(nn.Module):
        """输入单个候选动作与公开局面，输出该动作的终局价值。"""

        def __init__(self) -> None:
            super().__init__()
            # 某些 Windows PyTorch 冷启动会短暂缺失 nn.Sequential 的顶层导出；
            # 使用基础层和 torch.relu 可避免该导入抖动，不改变网络结构。
            self.history_lstm = nn.LSTM(
                input_size=FIFTY_K_HISTORY_STEP_SIZE,
                hidden_size=128,
                batch_first=True,
            )
            static_size = FIFTY_K_FEATURE_SIZE - (
                HISTORY_LENGTH * FIFTY_K_HISTORY_STEP_SIZE
            )
            self.input_layer = nn.Linear(static_size + 128, 256)
            self.hidden_layer_1 = nn.Linear(256, 256)
            self.hidden_layer_2 = nn.Linear(256, 128)
            self.output_layer = nn.Linear(128, 1)

        def forward(self, features):
            history_end = FIFTY_K_PUBLIC_STATE_OFFSET
            history = features[:, FIFTY_K_HISTORY_OFFSET:history_end].reshape(
                -1, HISTORY_LENGTH, FIFTY_K_HISTORY_STEP_SIZE
            )
            _, (history_hidden, _) = self.history_lstm(history)
            return self._score_with_history(features, history_hidden[-1])

        def score_actions_with_shared_history(self, features):
            """同一局面的候选动作共享一份历史编码，避免 CPU 重复推理。"""
            if features.shape[0] <= 1:
                return self.forward(features)
            history_end = FIFTY_K_PUBLIC_STATE_OFFSET
            history = features[:1, FIFTY_K_HISTORY_OFFSET:history_end].reshape(
                1, HISTORY_LENGTH, FIFTY_K_HISTORY_STEP_SIZE
            )
            _, (history_hidden, _) = self.history_lstm(history)
            shared_history = history_hidden[-1].expand(features.shape[0], -1)
            return self._score_with_history(features, shared_history)

        def _score_with_history(self, features, history_hidden):
            history_end = FIFTY_K_PUBLIC_STATE_OFFSET
            static = torch.cat(
                (
                    features[:, :FIFTY_K_HISTORY_OFFSET],
                    features[:, history_end:],
                    history_hidden,
                ),
                dim=1,
            )
            hidden = torch.relu(self.input_layer(static))
            hidden = torch.relu(self.hidden_layer_1(hidden))
            hidden = torch.relu(self.hidden_layer_2(hidden))
            return self.output_layer(hidden)
else:
    class FiftyKActionValueModel:  # type: ignore[no-redef]
        def __init__(self) -> None:
            raise RuntimeError("未安装 PyTorch，无法加载 510K 模型")


class FiftyKAgentManager:
    """仅加载已通过离线评测的 510K 模型，失败时由调用方降级规则 AI。"""

    def __init__(self, model_dir: Optional[Path] = None) -> None:
        default_dir = Path(__file__).resolve().parent / "weights" / "fifty_k"
        configured_dir = os.getenv("FIFTY_K_MODEL_DIR")
        self.model_dir = Path(model_dir or configured_dir or default_dir)
        self.model = None
        self._loaded = False
        self.load_error: Optional[str] = None
        self.load()

    def load(self) -> None:
        self.model = None
        self._loaded = False
        self.load_error = None
        if torch is None:
            self.load_error = "未安装 PyTorch"
            return

        manifest_path = self.model_dir / "manifest.json"
        if not manifest_path.is_file():
            self.load_error = "未找到 510K 模型清单"
            return

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("rules_version") != FIFTY_K_RULES_VERSION:
                raise ValueError("模型规则版本不兼容")
            if manifest.get("features_version") != FIFTY_K_FEATURES_VERSION:
                raise ValueError("模型特征版本不兼容")

            metrics = manifest.get("metrics") or {}
            if (
                float(metrics.get("win_rate_vs_rule", 0)) < 0.40
                or float(metrics.get("score_delta_vs_rule", -1)) < 0
                or float(metrics.get("illegal_action_rate", 1)) != 0
            ):
                raise ValueError("模型尚未通过上线评测门槛")

            checkpoint_path = self.model_dir / str(manifest.get("checkpoint", "model.pt"))
            if not checkpoint_path.is_file():
                raise FileNotFoundError("未找到 510K 模型权重")
            expected_sha = manifest.get("checkpoint_sha256")
            if expected_sha and self._sha256(checkpoint_path) != expected_sha:
                raise ValueError("模型权重校验失败")

            payload = torch.load(checkpoint_path, map_location="cpu")
            state_dict = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
            model = FiftyKActionValueModel()
            model.load_state_dict(state_dict)
            model.eval()
            self.model = model
            self._loaded = True
            logger.info("510K 专属动作价值模型已加载: %s", checkpoint_path)
        except Exception as exc:
            self.load_error = str(exc)
            logger.warning("510K 专属模型未启用，使用规则 AI: %s", exc)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as checkpoint:
            for chunk in iter(lambda: checkpoint.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def is_available(self) -> bool:
        return self._loaded and self.model is not None

    def rank_actions(
        self,
        hand: Sequence[int],
        actions: Sequence[Sequence[int]],
        last_play: Optional["CardPlay"],
        ctx: "AIContext",
    ) -> List[List[int]]:
        if not self.is_available() or torch is None:
            raise RuntimeError("510K 模型未加载")
        if not actions:
            return []

        features = [build_fifty_k_features(hand, action, last_play, ctx) for action in actions]
        inputs = torch.tensor(features, dtype=torch.float32)
        with torch.inference_mode():
            scores = self.model.score_actions_with_shared_history(inputs).reshape(-1)
        order = torch.argsort(scores, descending=True).tolist()
        return [list(actions[index]) for index in order]


fifty_k_manager = FiftyKAgentManager()
