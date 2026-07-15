"""510K 动作价值模型的自博弈训练、评测与安全产物发布。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import random
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import torch
import torch.nn.functional as functional

from app.domain.game.ai_strategy import (
    _rank_fifty_k_rule_actions,
    build_ai_context,
    generate_legal_actions_dz,
)
from app.domain.game.card import sort_cards
from app.domain.game.fifty_k_model import (
    FIFTY_K_FEATURE_SIZE,
    FIFTY_K_FEATURES_VERSION,
    FIFTY_K_RULES_VERSION,
    FiftyKActionValueModel,
    build_fifty_k_features,
)
from app.domain.game.fifty_k_search import (
    choose_fifty_k_endgame_action,
    should_search_fifty_k_endgame,
)
from app.domain.game.room import GameRoom
from app.training.fifty_k.environment import PLAYER_IDS, FiftyKSelfPlayEnv


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingMetrics:
    win_rate_vs_rule: float
    score_delta_vs_rule: float
    illegal_action_rate: float


@dataclass(frozen=True)
class TrainingConfig:
    episodes: int = 2000
    batch_size: int = 64
    learning_rate: float = 3e-4
    exploration_rate: float = 0.35
    min_exploration_rate: float = 0.05
    rule_opponent_ratio: float = 0.0
    teacher_episodes: int = 0
    teacher_evaluation_games: int = 50
    teacher_evaluation_interval: int = 500
    teacher_min_agreement: float = 0.85
    teacher_updates_per_batch: int = 4
    rollout_updates_per_batch: int = 4
    imitation_weight: float = 0.0
    rollout_min_agreement: float = 0.75
    rollout_candidate_count: int = 0
    rollout_determinizations: int = 2
    rollout_samples_per_episode: int = 3
    checkpoint_interval: int = 2000
    checkpoint_evaluation_games: int = 100
    checkpoint_max_win_rate_drop: float = 0.03
    num_actors: int = 1
    seed: int = 20260714
    initial_checkpoint: Optional[Path] = None


DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "domain" / "game" / "weights" / "fifty_k"
VALUE_TARGET_SCALE = 1000.0


@dataclass(frozen=True)
class MonteCarloTransition:
    features: List[float]
    target: float
    player_id: str


Transition = MonteCarloTransition


@dataclass(frozen=True)
class TeacherExample:
    candidate_features: List[List[float]]
    target_order: List[int]


@dataclass(frozen=True)
class RolloutExample:
    candidate_features: List[List[float]]
    target_values: List[float]


@dataclass(frozen=True)
class PendingRollout:
    room_state: dict
    player_id: str
    actions: List[List[int]]
    candidate_features: List[List[float]]
    decision_index: int
    seed: int


@dataclass(frozen=True)
class SelfPlayCollection:
    """一批采样样本及其中模型独自对规则 AI 的胜负统计。"""

    transitions: List[Transition]
    model_vs_rule_games: int = 0
    model_vs_rule_wins: int = 0
    teacher_examples: List[TeacherExample] = field(default_factory=list)
    rollout_examples: List[RolloutExample] = field(default_factory=list)
    rollout_position_counts: Tuple[int, int, int] = (0, 0, 0)


def _model_device(model: FiftyKActionValueModel) -> torch.device:
    return next(model.parameters()).device


def exploration_rate_at(config: TrainingConfig, completed_episodes: int) -> float:
    if config.episodes <= 0:
        return config.min_exploration_rate
    progress = min(max(completed_episodes / config.episodes, 0.0), 1.0)
    return config.exploration_rate + (config.min_exploration_rate - config.exploration_rate) * progress


def _select_rule_opponents(rng: random.Random, rule_opponent_ratio: float) -> Set[str]:
    """按局混入两名固定规则 AI，让模型持续面对稳定基线。"""
    ratio = min(max(rule_opponent_ratio, 0.0), 1.0)
    if ratio == 0.0 or rng.random() >= ratio:
        return set()
    model_player_id = rng.choice(PLAYER_IDS)
    return {player_id for player_id in PLAYER_IDS if player_id != model_player_id}


def _relative_terminal_rewards(rewards: Dict[str, float]) -> Dict[str, float]:
    """移除同局公共奖励偏置，保留三人之间的相对胜负优势。"""
    if not rewards:
        return {}
    average_reward = sum(rewards.values()) / len(rewards)
    return {player_id: reward - average_reward for player_id, reward in rewards.items()}


def _full_ranking_loss_from_scores(
    scores: torch.Tensor,
    groups: Iterable[Tuple[int, int, List[int]]],
) -> torch.Tensor:
    """使用 ListMLE 让模型学习规则 AI 给出的完整候选顺序。"""
    losses = []
    for start, end, target_order in groups:
        if end - start <= 1:
            continue
        order = torch.tensor(target_order, dtype=torch.long, device=scores.device)
        ordered_scores = scores[start:end][order]
        suffix_logsumexp = torch.logcumsumexp(ordered_scores.flip(0), dim=0).flip(0)
        losses.append((suffix_logsumexp[:-1] - ordered_scores[:-1]).mean())
    return torch.stack(losses).mean() if losses else scores.sum() * 0.0


def _top1_accuracy_from_scores(
    scores: torch.Tensor,
    groups: Iterable[Tuple[int, int, List[int]]],
) -> float:
    matches = 0
    total = 0
    for start, end, target_order in groups:
        if end <= start or not target_order:
            continue
        predicted_index = int(torch.argmax(scores[start:end]).item())
        matches += int(predicted_index == target_order[0])
        total += 1
    return matches / total if total else 0.0


def _teacher_action_loss(
    model: FiftyKActionValueModel,
    examples: Iterable[TeacherExample],
    device: torch.device,
) -> torch.Tensor:
    flat_features: List[List[float]] = []
    groups: List[Tuple[int, int, List[int]]] = []
    for example in examples:
        start = len(flat_features)
        flat_features.extend(example.candidate_features)
        groups.append((start, len(flat_features), example.target_order))
    if not flat_features:
        return torch.zeros((), dtype=torch.float32, device=device)
    scores = model(torch.tensor(flat_features, dtype=torch.float32, device=device)).reshape(-1)
    return _full_ranking_loss_from_scores(scores, groups)


def _teacher_action_accuracy(
    model: FiftyKActionValueModel,
    examples: Iterable[TeacherExample],
    device: torch.device,
) -> float:
    flat_features: List[List[float]] = []
    groups: List[Tuple[int, int, List[int]]] = []
    for example in examples:
        start = len(flat_features)
        flat_features.extend(example.candidate_features)
        groups.append((start, len(flat_features), example.target_order))
    if not flat_features:
        return 0.0
    with torch.inference_mode():
        scores = model(torch.tensor(flat_features, dtype=torch.float32, device=device)).reshape(-1)
    return _top1_accuracy_from_scores(scores, groups)


def _rollout_value_loss(
    model: FiftyKActionValueModel,
    examples: Iterable[RolloutExample],
    device: torch.device,
) -> torch.Tensor:
    flat_features: List[List[float]] = []
    groups: List[Tuple[int, int, List[float]]] = []
    for example in examples:
        start = len(flat_features)
        flat_features.extend(example.candidate_features)
        groups.append((start, len(flat_features), example.target_values))
    if not flat_features:
        return torch.zeros((), dtype=torch.float32, device=device)
    scores = model(torch.tensor(flat_features, dtype=torch.float32, device=device)).reshape(-1)
    losses = []
    for start, end, target_values in groups:
        group_scores = scores[start:end]
        for left in range(len(target_values)):
            for right in range(left + 1, len(target_values)):
                if target_values[left] == target_values[right]:
                    continue
                preferred, other = (
                    (left, right)
                    if target_values[left] > target_values[right]
                    else (right, left)
                )
                reward_gap = abs(target_values[left] - target_values[right])
                losses.append(
                    reward_gap
                    * functional.softplus(-(group_scores[preferred] - group_scores[other]))
                )
    return torch.stack(losses).mean() if losses else scores.sum() * 0.0


def _monte_carlo_loss(
    model: FiftyKActionValueModel,
    transitions: Iterable[MonteCarloTransition],
    device: torch.device,
) -> torch.Tensor:
    samples = list(transitions)
    if not samples:
        return torch.zeros((), dtype=torch.float32, device=device)
    features = torch.tensor(
        [sample.features for sample in samples],
        dtype=torch.float32,
        device=device,
    )
    targets = torch.tensor(
        [sample.target for sample in samples],
        dtype=torch.float32,
        device=device,
    )
    predictions = model(features).reshape(-1)
    return functional.mse_loss(predictions, targets)


def _teacher_gate_passed(agreement: float, minimum_agreement: float) -> bool:
    return agreement >= minimum_agreement


def _is_better_checkpoint(candidate: TrainingMetrics, best: Optional[TrainingMetrics]) -> bool:
    """优先选择零非法动作，其次胜率，最后比较平均得分差。"""
    if best is None:
        return True
    return (
        -candidate.illegal_action_rate,
        candidate.win_rate_vs_rule,
        candidate.score_delta_vs_rule,
    ) > (
        -best.illegal_action_rate,
        best.win_rate_vs_rule,
        best.score_delta_vs_rule,
    )


def _checkpoint_materially_degraded(
    candidate: TrainingMetrics,
    best: Optional[TrainingMetrics],
    max_win_rate_drop: float,
) -> bool:
    if best is None:
        return False
    return (
        candidate.illegal_action_rate > best.illegal_action_rate
        or candidate.win_rate_vs_rule
        < best.win_rate_vs_rule - max(max_win_rate_drop, 0.0)
    )


def _clone_model_state(model: FiftyKActionValueModel) -> Dict[str, torch.Tensor]:
    return {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}


def _rank_rule_actions(room, player_id: str, actions: Optional[List[List[int]]] = None) -> List[List[int]]:
    ctx = build_ai_context(room, player_id)
    legal_actions = actions or generate_legal_actions_dz(
        room.hands[player_id],
        room.last_play.card_play,
        room.last_play.card_play is None,
        play_mode="fifty_k",
    )
    return _rank_fifty_k_rule_actions(
        room.hands[player_id],
        legal_actions,
        room.last_play.card_play,
        ctx,
    )


def _rule_action(room, player_id: str) -> List[int]:
    return _rank_rule_actions(room, player_id)[0]


def _public_determinized_states(
    room: GameRoom,
    observer_id: str,
    count: int,
    seed: int,
) -> List[dict]:
    """仅依据公开信息重分配两家暗牌，生成可复现的信息集局面。"""
    base_state = copy.deepcopy(room.to_dict())
    observer_hand = list(room.hands.get(observer_id, []))
    opponent_ids = [player.id for player in room.players if player.id != observer_id]
    visible_cards = set(observer_hand)
    visible_cards.update(getattr(room, "all_played_cards", []))
    unseen_cards = [card_id for card_id in range(54) if card_id not in visible_cards]
    opponent_counts = {
        player_id: len(room.hands.get(player_id, []))
        for player_id in opponent_ids
    }
    if sum(opponent_counts.values()) != len(unseen_cards):
        raise ValueError("510K 公开信息无法按对手剩余张数完整分配未见牌")

    rng = random.Random(seed)
    states: List[dict] = []
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
        states.append(state)
    return states


def _rollout_action_values(
    room: GameRoom,
    player_id: str,
    actions: List[List[int]],
    max_candidates: int = 4,
    determinizations: int = 1,
    determinization_seed: int = 0,
) -> List[float]:
    """复制当前局面，分别试走候选动作并由规则 AI 完成余下对局。"""
    selected_actions = actions[:max(1, max_candidates)]
    public_states = _public_determinized_states(
        room,
        player_id,
        determinizations,
        determinization_seed,
    )
    values: List[float] = []
    for action in selected_actions:
        sampled_values: List[float] = []
        for public_state in public_states:
            rollout_room = GameRoom.from_dict(copy.deepcopy(public_state))
            rollout_environment = FiftyKSelfPlayEnv(base_score=rollout_room.base_score)
            rollout_environment.room = rollout_room
            result = rollout_environment.step(player_id, list(action))
            for _ in range(300):
                if result.done:
                    rewards = result.rewards or {}
                    sampled_values.append(rewards.get(player_id, 0.0) / VALUE_TARGET_SCALE)
                    break
                current_player_id = rollout_room.current_turn
                result = rollout_environment.step(
                    current_player_id,
                    _rule_action(rollout_room, current_player_id),
                )
            else:
                raise RuntimeError("510K 候选动作模拟未在 300 步内结束")
        values.append(sum(sampled_values) / len(sampled_values))
    return values


def _reservoir_should_replace(rng: random.Random, seen_count: int) -> bool:
    """以 1/seen_count 的概率替换当前样本，使整局每个决策等概率入选。"""
    if seen_count <= 0:
        raise ValueError("seen_count 必须大于 0")
    return rng.randrange(seen_count) == 0


def _reservoir_replacement_index(
    rng: random.Random,
    seen_count: int,
    capacity: int,
) -> Optional[int]:
    """返回固定容量蓄水池中应写入的槽位；无需替换时返回 None。"""
    if seen_count <= 0:
        raise ValueError("seen_count 必须大于 0")
    if capacity <= 0:
        return None
    if seen_count <= capacity:
        return seen_count - 1
    candidate_index = rng.randrange(seen_count)
    return candidate_index if candidate_index < capacity else None


def _collect_episode(
    model: FiftyKActionValueModel,
    seed: int,
    exploration_rate: float,
    rule_opponent_ratio: float = 0.0,
    force_rule_for_model: bool = False,
    rollout_candidate_count: int = 0,
    rollout_determinizations: int = 1,
    rollout_samples_per_episode: int = 1,
    collect_teacher_examples: bool = True,
) -> SelfPlayCollection:
    environment = FiftyKSelfPlayEnv(seed=seed)
    room = environment.reset()
    rng = random.Random(seed ^ 0x510)
    rollout_rng = random.Random(seed ^ 0x510510)
    rule_player_ids = _select_rule_opponents(rng, rule_opponent_ratio)
    teacher_examples: List[TeacherExample] = []
    rollout_examples: List[RolloutExample] = []
    pending_rollouts: List[PendingRollout] = []
    selected_features_by_player: Dict[str, List[List[float]]] = {
        player_id: [] for player_id in PLAYER_IDS
    }
    model_decision_count = 0

    while True:
        player_id = room.current_turn
        actions = environment.legal_actions(player_id)
        ctx = build_ai_context(room, player_id)
        last_play = room.last_play.card_play
        if player_id in rule_player_ids:
            action = _rule_action(room, player_id)
        else:
            candidate_features = [
                build_fifty_k_features(room.hands[player_id], candidate, last_play, ctx)
                for candidate in actions
            ]
            action_indexes = {tuple(action): index for index, action in enumerate(actions)}
            needs_rule_ranking = (
                collect_teacher_examples
                or force_rule_for_model
                or rollout_candidate_count > 0
            )
            ranked_actions = (
                _rank_rule_actions(room, player_id, actions)
                if needs_rule_ranking
                else actions
            )
            if collect_teacher_examples:
                target_order = [
                    action_indexes[tuple(action)]
                    for action in ranked_actions
                    if tuple(action) in action_indexes
                ]
                target_order.extend(
                    index for index in range(len(actions)) if index not in target_order
                )
                teacher_examples.append(TeacherExample(candidate_features, target_order))
            rule_action = ranked_actions[0]
            if not force_rule_for_model and rollout_candidate_count > 0:
                model_decision_count += 1
            replacement_index = None
            if not force_rule_for_model and rollout_candidate_count > 0:
                replacement_index = _reservoir_replacement_index(
                    rollout_rng,
                    model_decision_count,
                    rollout_samples_per_episode,
                )
            if replacement_index is not None:
                selected_actions = ranked_actions[:rollout_candidate_count]
                pending = PendingRollout(
                    room_state=copy.deepcopy(room.to_dict()),
                    player_id=player_id,
                    actions=[list(action) for action in selected_actions],
                    candidate_features=[
                        list(candidate_features[action_indexes[tuple(action)]])
                        for action in selected_actions
                    ],
                    decision_index=model_decision_count - 1,
                    seed=seed ^ (model_decision_count * 0x9E3779B1),
                )
                if replacement_index == len(pending_rollouts):
                    pending_rollouts.append(pending)
                else:
                    pending_rollouts[replacement_index] = pending
            if force_rule_for_model:
                action = rule_action
            else:
                supported_actions = (
                    ranked_actions[:rollout_candidate_count]
                    if rollout_candidate_count > 0
                    else actions
                )
                if rng.random() < exploration_rate:
                    action = list(rng.choice(supported_actions))
                else:
                    supported_features = [
                        candidate_features[action_indexes[tuple(candidate)]]
                        for candidate in supported_actions
                    ]
                    inputs = torch.tensor(
                        supported_features,
                        dtype=torch.float32,
                        device=_model_device(model),
                    )
                    with torch.inference_mode():
                        scores = model.score_actions_with_shared_history(inputs).reshape(-1)
                    action = list(supported_actions[int(torch.argmax(scores).item())])
                selected_features_by_player[player_id].append(
                    list(candidate_features[action_indexes[tuple(action)]])
                )
        result = environment.step(player_id, action)
        if result.done:
            rollout_position_counts = [0, 0, 0]
            for pending in pending_rollouts:
                selected_room = GameRoom.from_dict(copy.deepcopy(pending.room_state))
                rollout_examples.append(
                    RolloutExample(
                        candidate_features=pending.candidate_features,
                        target_values=_rollout_action_values(
                            selected_room,
                            pending.player_id,
                            pending.actions,
                            rollout_candidate_count,
                            rollout_determinizations,
                            pending.seed,
                        ),
                    )
                )
                position_bucket = min(
                    pending.decision_index * 3 // max(model_decision_count, 1),
                    2,
                )
                rollout_position_counts[position_bucket] += 1
            model_vs_rule_games = int(
                not force_rule_for_model and len(rule_player_ids) == len(PLAYER_IDS) - 1
            )
            model_vs_rule_wins = int(
                model_vs_rule_games
                and result.winner_id is not None
                and result.winner_id not in rule_player_ids
            )
            relative_rewards = _relative_terminal_rewards(result.rewards or {})
            transitions = [
                MonteCarloTransition(
                    features=features,
                    target=relative_rewards.get(selected_player_id, 0.0)
                    / VALUE_TARGET_SCALE,
                    player_id=selected_player_id,
                )
                for selected_player_id, selected_features in selected_features_by_player.items()
                for features in selected_features
            ]
            return SelfPlayCollection(
                transitions=transitions,
                model_vs_rule_games=model_vs_rule_games,
                model_vs_rule_wins=model_vs_rule_wins,
                teacher_examples=teacher_examples,
                rollout_examples=rollout_examples,
                rollout_position_counts=tuple(rollout_position_counts),
            )


def _merge_collections(collections: Iterable[SelfPlayCollection]) -> SelfPlayCollection:
    transitions: List[Transition] = []
    model_vs_rule_games = 0
    model_vs_rule_wins = 0
    teacher_examples: List[TeacherExample] = []
    rollout_examples: List[RolloutExample] = []
    rollout_position_counts = [0, 0, 0]
    for collection in collections:
        transitions.extend(collection.transitions)
        model_vs_rule_games += collection.model_vs_rule_games
        model_vs_rule_wins += collection.model_vs_rule_wins
        teacher_examples.extend(collection.teacher_examples)
        rollout_examples.extend(collection.rollout_examples)
        for index, count in enumerate(collection.rollout_position_counts):
            rollout_position_counts[index] += count
    return SelfPlayCollection(
        transitions=transitions,
        model_vs_rule_games=model_vs_rule_games,
        model_vs_rule_wins=model_vs_rule_wins,
        teacher_examples=teacher_examples,
        rollout_examples=rollout_examples,
        rollout_position_counts=tuple(rollout_position_counts),
    )


def _collect_worker(
    payload: Tuple[Dict[str, torch.Tensor], List[int], float, float, bool, int, int, int, bool],
) -> SelfPlayCollection:
    # Windows 多个 Actor 若各自占满全部 Torch 线程会严重过度争用。
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass
    (
        state_dict,
        seeds,
        exploration_rate,
        rule_opponent_ratio,
        force_rule_for_model,
        rollout_candidate_count,
        rollout_determinizations,
        rollout_samples_per_episode,
        collect_teacher_examples,
    ) = payload
    model = FiftyKActionValueModel()
    model.load_state_dict(state_dict)
    model.eval()
    return _merge_collections(
        _collect_episode(
            model,
            seed,
            exploration_rate,
            rule_opponent_ratio,
            force_rule_for_model,
            rollout_candidate_count,
            rollout_determinizations,
            rollout_samples_per_episode,
            collect_teacher_examples,
        )
        for seed in seeds
    )


def collect_self_play_batch(
    model: FiftyKActionValueModel,
    seeds: Iterable[int],
    exploration_rate: float,
    num_actors: int,
    rule_opponent_ratio: float = 0.0,
    worker_executor: Optional[ProcessPoolExecutor] = None,
    force_rule_for_model: bool = False,
    rollout_candidate_count: int = 0,
    rollout_determinizations: int = 1,
    rollout_samples_per_episode: int = 1,
    collect_teacher_examples: bool = True,
) -> SelfPlayCollection:
    seed_list = list(seeds)
    if num_actors <= 1 or len(seed_list) <= 1:
        return _collect_worker((
            {key: value.detach().cpu() for key, value in model.state_dict().items()},
            seed_list,
            exploration_rate,
            rule_opponent_ratio,
            force_rule_for_model,
            rollout_candidate_count,
            rollout_determinizations,
            rollout_samples_per_episode,
            collect_teacher_examples,
        ))

    chunks = [seed_list[index::num_actors] for index in range(num_actors)]
    state_dict = {key: value.detach().cpu() for key, value in model.state_dict().items()}
    payloads = [
        (
            state_dict,
            chunk,
            exploration_rate,
            rule_opponent_ratio,
            force_rule_for_model,
            rollout_candidate_count,
            rollout_determinizations,
            rollout_samples_per_episode,
            collect_teacher_examples,
        )
        for chunk in chunks
        if chunk
    ]
    if worker_executor is not None:
        return _merge_collections(worker_executor.map(_collect_worker, payloads))
    with ProcessPoolExecutor(max_workers=len(payloads)) as executor:
        batches = list(executor.map(_collect_worker, payloads))
    return _merge_collections(batches)


def train_self_play(config: TrainingConfig) -> FiftyKActionValueModel:
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = FiftyKActionValueModel().to(device)
    if config.initial_checkpoint is not None:
        payload = torch.load(config.initial_checkpoint, map_location=device)
        state_dict = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
        model.load_state_dict(state_dict)
        logger.info("510K 已加载续训检查点：%s", config.initial_checkpoint)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    rng = random.Random(config.seed)
    started_at = time.perf_counter()
    logger.info(
        "510K 训练开始：局数=%s，批次=%s，采样进程=%s，设备=%s，"
        "规则对手比例=%.0f%%，探索率=%.2f→%.2f，信息集确定化=%s，检查点=%s 局/%s 局评测",
        config.episodes,
        config.batch_size,
        config.num_actors,
        device,
        config.rule_opponent_ratio * 100,
        config.exploration_rate,
        config.min_exploration_rate,
        config.rollout_determinizations,
        config.checkpoint_interval,
        config.checkpoint_evaluation_games,
    )
    logger.info(
        "510K rollout 采样配置：候选=%s，每局决策点=%s，每个决策确定化=%s，批次更新=%s",
        config.rollout_candidate_count,
        config.rollout_samples_per_episode,
        config.rollout_determinizations,
        config.rollout_updates_per_batch,
    )

    completed = 0
    next_checkpoint = config.checkpoint_interval
    best_state: Optional[Dict[str, torch.Tensor]] = None
    best_metrics: Optional[TrainingMetrics] = None
    best_teacher_state: Optional[Dict[str, torch.Tensor]] = None
    best_teacher_agreement = -1.0
    cumulative_model_vs_rule_games = 0
    cumulative_model_vs_rule_wins = 0
    teacher_ready = config.teacher_episodes <= 0
    next_teacher_evaluation = max(config.teacher_episodes, 1)
    latest_teacher_agreement = 0.0
    rollout_started = False
    last_rollout_checkpoint_completed: Optional[int] = None
    worker_executor = (
        ProcessPoolExecutor(max_workers=config.num_actors)
        if config.num_actors > 1
        else None
    )

    if (
        config.initial_checkpoint is not None
        and teacher_ready
        and config.episodes > 0
        and config.checkpoint_evaluation_games > 0
    ):
        best_teacher_state = _clone_model_state(model)
        best_teacher_agreement = evaluate_rule_agreement(
            model.cpu().eval(),
            games=config.teacher_evaluation_games,
            seed=config.seed + 30_000,
        )
        best_metrics = evaluate_against_rule(
            model,
            games=config.checkpoint_evaluation_games,
            seed=config.seed + 10_000,
        )
        model.to(device)
        best_state = _clone_model_state(model)
        logger.info(
            "510K 续训基线：规则Top1=%.1f%%，胜率=%.3f，平均得分差=%.2f，非法率=%.3f",
            best_teacher_agreement * 100,
            best_metrics.win_rate_vs_rule,
            best_metrics.score_delta_vs_rule,
            best_metrics.illegal_action_rate,
        )

    def evaluate_rollout_checkpoint(checkpoint_label: str) -> None:
        nonlocal optimizer, best_state, best_metrics
        rollout_agreement = evaluate_rule_agreement(
            model.cpu().eval(),
            games=config.teacher_evaluation_games,
            seed=config.seed + 30_000,
        )
        model.to(device)
        checkpoint_rejected = (
            best_teacher_state is not None
            and rollout_agreement < config.rollout_min_agreement
        )
        if checkpoint_rejected:
            model.load_state_dict(best_teacher_state)
            optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
            logger.info(
                "510K rollout 一致率保护：当前=%.1f%%，最低=%.1f%%，"
                "已恢复最佳 teacher 权重并重置优化器",
                rollout_agreement * 100,
                config.rollout_min_agreement * 100,
            )
            return

        checkpoint_metrics = evaluate_against_rule(
            model.cpu().eval(),
            games=config.checkpoint_evaluation_games,
            seed=config.seed + 10_000,
        )
        model.to(device)
        if _is_better_checkpoint(checkpoint_metrics, best_metrics):
            best_state = _clone_model_state(model)
            best_metrics = checkpoint_metrics
            logger.info(
                "510K %s成为当前最佳：胜率=%.3f，平均得分差=%.2f，非法率=%.3f",
                checkpoint_label,
                checkpoint_metrics.win_rate_vs_rule,
                checkpoint_metrics.score_delta_vs_rule,
                checkpoint_metrics.illegal_action_rate,
            )
        elif _checkpoint_materially_degraded(
            checkpoint_metrics,
            best_metrics,
            config.checkpoint_max_win_rate_drop,
        ):
            if best_state is not None:
                model.load_state_dict(best_state)
                optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
            logger.info(
                "510K %s未超过最佳，已恢复最佳权重并重置优化器："
                "当前胜率=%.3f，最佳胜率=%.3f",
                checkpoint_label,
                checkpoint_metrics.win_rate_vs_rule,
                best_metrics.win_rate_vs_rule if best_metrics else 0.0,
            )
        else:
            logger.info(
                "510K %s 未超过最佳但在 %.1f%% 容差内，统计持平，保留当前权重继续训练："
                "当前胜率=%.3f，最佳胜率=%.3f",
                checkpoint_label,
                config.checkpoint_max_win_rate_drop * 100,
                checkpoint_metrics.win_rate_vs_rule,
                best_metrics.win_rate_vs_rule if best_metrics else 0.0,
            )

    while completed < config.episodes:
        batch_started_at = time.perf_counter()
        teacher_phase = not teacher_ready
        if not teacher_phase:
            rollout_started = True
        current_batch = min(config.batch_size, config.episodes - completed)
        if teacher_phase and config.teacher_evaluation_games > 0:
            current_batch = min(current_batch, max(next_teacher_evaluation - completed, 1))
        seeds = [rng.randrange(1 << 30) for _ in range(current_batch)]
        current_exploration_rate = exploration_rate_at(config, completed)
        model.eval()
        collection = collect_self_play_batch(
            model,
            seeds,
            current_exploration_rate,
            config.num_actors,
            config.rule_opponent_ratio,
            worker_executor,
            force_rule_for_model=teacher_phase,
            rollout_candidate_count=0 if teacher_phase else config.rollout_candidate_count,
            rollout_determinizations=config.rollout_determinizations,
            rollout_samples_per_episode=config.rollout_samples_per_episode,
            collect_teacher_examples=(teacher_phase or config.imitation_weight > 0),
        )
        model.train()
        update_count = max(
            config.teacher_updates_per_batch if teacher_phase else config.rollout_updates_per_batch,
            1,
        )
        for _ in range(update_count):
            optimizer.zero_grad()
            teacher_loss = _teacher_action_loss(model, collection.teacher_examples, device)
            rollout_loss = _rollout_value_loss(model, collection.rollout_examples, device)
            monte_carlo_loss = _monte_carlo_loss(model, collection.transitions, device)
            if teacher_phase:
                loss = teacher_loss
            else:
                loss = (
                    monte_carlo_loss
                    + rollout_loss
                    + config.imitation_weight * teacher_loss
                )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
        batch_teacher_accuracy = _teacher_action_accuracy(
            model,
            collection.teacher_examples,
            device,
        )
        completed += current_batch
        cumulative_model_vs_rule_games += collection.model_vs_rule_games
        cumulative_model_vs_rule_wins += collection.model_vs_rule_wins

        elapsed = time.perf_counter() - started_at
        batch_elapsed = time.perf_counter() - batch_started_at
        estimated_remaining = elapsed / completed * (config.episodes - completed) if completed else 0
        current_win_rate = (
            f"{collection.model_vs_rule_wins / collection.model_vs_rule_games:.1%}"
            if collection.model_vs_rule_games
            else "暂无对局"
        )
        cumulative_win_rate = (
            f"{cumulative_model_vs_rule_wins / cumulative_model_vs_rule_games:.1%}"
            if cumulative_model_vs_rule_games
            else "暂无对局"
        )
        logger.info(
            "510K 训练进度 %s/%s（%.1f%%）：batch=%s，样本=%s，探索率=%.3f，loss=%.6f，"
            "带探索训练胜率=%s（本批 %s/%s，累计 %s/%s；累计胜率=%s），本批=%.1fs，已用=%.1fs，预计剩余=%.1fs",
            completed,
            config.episodes,
            completed / config.episodes * 100,
            current_batch,
            len(collection.transitions),
            current_exploration_rate,
            loss.item(),
            current_win_rate,
            collection.model_vs_rule_wins,
            collection.model_vs_rule_games,
            cumulative_model_vs_rule_wins,
            cumulative_model_vs_rule_games,
            cumulative_win_rate,
            batch_elapsed,
            elapsed,
            estimated_remaining,
        )
        logger.info(
            "510K 训练阶段 phase=%s，规则排序样本=%s，模拟样本=%s，teacher更新=%s，规则Top1=%.1f%%，"
            "模拟位置=开局%s/中局%s/残局%s，规则损失=%.6f，模拟排序损失=%.6f",
            "teacher" if teacher_phase else "rollout",
            len(collection.teacher_examples),
            len(collection.rollout_examples),
            update_count,
            batch_teacher_accuracy * 100,
            *collection.rollout_position_counts,
            teacher_loss.item(),
            rollout_loss.item(),
        )
        logger.info(
            "510K DMC 轨迹样本=%s，终局回报损失=%.6f",
            len(collection.transitions),
            monte_carlo_loss.item(),
        )

        if teacher_phase and completed >= config.teacher_episodes:
            if config.teacher_evaluation_games <= 0:
                teacher_ready = True
            elif completed >= next_teacher_evaluation:
                latest_teacher_agreement = evaluate_rule_agreement(
                    model.cpu().eval(),
                    games=config.teacher_evaluation_games,
                    seed=config.seed + 20_000,
                )
                model.to(device)
                if (
                    best_teacher_state is None
                    or latest_teacher_agreement > best_teacher_agreement
                ):
                    best_teacher_state = _clone_model_state(model)
                    best_teacher_agreement = latest_teacher_agreement
                teacher_ready = _teacher_gate_passed(
                    latest_teacher_agreement,
                    config.teacher_min_agreement,
                )
                logger.info(
                    "510K 规则一致率门禁：当前=%.1f%%，要求=%.1f%%，结果=%s",
                    latest_teacher_agreement * 100,
                    config.teacher_min_agreement * 100,
                    "通过，下一批进入 rollout" if teacher_ready else "未通过，继续 teacher",
                )
                if (
                    teacher_ready
                    and config.checkpoint_interval > 0
                    and config.checkpoint_evaluation_games > 0
                ):
                    best_metrics = evaluate_against_rule(
                        model.cpu().eval(),
                        games=config.checkpoint_evaluation_games,
                        seed=config.seed + 10_000,
                    )
                    model.to(device)
                    best_state = _clone_model_state(model)
                    logger.info(
                        "510K teacher 正式基线：胜率=%.3f，平均得分差=%.2f，非法率=%.3f",
                        best_metrics.win_rate_vs_rule,
                        best_metrics.score_delta_vs_rule,
                        best_metrics.illegal_action_rate,
                    )
                elif not teacher_ready:
                    next_teacher_evaluation += max(config.teacher_evaluation_interval, 1)

        if teacher_phase and config.checkpoint_interval > 0:
            while next_checkpoint <= completed:
                next_checkpoint += config.checkpoint_interval

        if (
            not teacher_phase
            and config.checkpoint_interval > 0
            and config.checkpoint_evaluation_games > 0
            and next_checkpoint <= config.episodes
            and completed >= next_checkpoint
        ):
            evaluate_rollout_checkpoint(f"检查点 {completed} 局")
            last_rollout_checkpoint_completed = completed
            next_checkpoint += config.checkpoint_interval

    if worker_executor is not None:
        worker_executor.shutdown(wait=True)

    if (
        rollout_started
        and teacher_ready
        and config.checkpoint_interval > 0
        and config.checkpoint_evaluation_games > 0
        and last_rollout_checkpoint_completed != completed
    ):
        logger.info("510K 检测到未评测的 rollout 尾段，执行最终检查点：局数=%s", completed)
        evaluate_rollout_checkpoint(f"最终检查点 {completed} 局")

    if not teacher_ready and best_teacher_state is not None:
        model.load_state_dict(best_teacher_state)
        logger.info(
            "510K 已恢复最佳 teacher 权重（规则一致率=%.1f%%）",
            best_teacher_agreement * 100,
        )
    elif best_state is not None:
        model.load_state_dict(best_state)
        logger.info("510K 已恢复最佳检查点权重")
    logger.info("510K 训练完成：总耗时=%.1fs", time.perf_counter() - started_at)
    return model.cpu().eval()


def _model_action(
    model: FiftyKActionValueModel,
    room,
    player_id: str,
    *,
    use_endgame_search: bool = True,
) -> List[int]:
    actions = generate_legal_actions_dz(
        room.hands[player_id],
        room.last_play.card_play,
        room.last_play.card_play is None,
        play_mode="fifty_k",
    )
    ctx = build_ai_context(room, player_id)
    features = [build_fifty_k_features(room.hands[player_id], action, room.last_play.card_play, ctx) for action in actions]
    with torch.inference_mode():
        scores = model.score_actions_with_shared_history(
            torch.tensor(features, dtype=torch.float32)
        ).reshape(-1)
    order = torch.argsort(scores, descending=True).tolist()
    ranked_actions = [list(actions[index]) for index in order]
    if use_endgame_search and should_search_fifty_k_endgame(room, player_id):
        return choose_fifty_k_endgame_action(
            room,
            player_id,
            ranked_actions,
            _rank_rule_actions,
        )
    return ranked_actions[0]


def _evaluation_deal_seed(base_seed: int, game_index: int) -> int:
    """每副固定牌依次让模型坐三个座位，降低发牌方差。"""
    return base_seed + game_index // len(PLAYER_IDS)


def evaluate_rule_agreement(
    model: FiftyKActionValueModel,
    games: int = 50,
    seed: int = 20260714,
) -> float:
    """在固定规则轨迹上评估模型首选动作与规则 AI 的 Top-1 一致率。"""
    matches = 0
    decisions = 0
    model.eval()
    for game_index in range(games):
        environment = FiftyKSelfPlayEnv(seed=_evaluation_deal_seed(seed, game_index))
        room = environment.reset()
        observed_player_id = PLAYER_IDS[game_index % len(PLAYER_IDS)]
        while True:
            player_id = room.current_turn
            rule_action = _rule_action(room, player_id)
            if player_id == observed_player_id:
                matches += int(
                    _model_action(
                        model,
                        room,
                        player_id,
                        use_endgame_search=False,
                    ) == rule_action
                )
                decisions += 1
            result = environment.step(player_id, rule_action)
            if result.done:
                break
    return matches / decisions if decisions else 0.0


def evaluate_against_rule(model: FiftyKActionValueModel, games: int = 300, seed: int = 20260714) -> TrainingMetrics:
    wins = 0
    score_delta = 0.0
    illegal_actions = 0
    model.eval()
    logger.info("510K 评测开始：对局=%s，随机种子=%s", games, seed)
    report_interval = max(1, games // 10)
    for game_index in range(games):
        environment = FiftyKSelfPlayEnv(seed=_evaluation_deal_seed(seed, game_index))
        room = environment.reset()
        model_player_id = ("p1", "p2", "p3")[game_index % 3]
        while True:
            player_id = room.current_turn
            try:
                if player_id == model_player_id:
                    action = _model_action(model, room, player_id)
                else:
                    ctx = build_ai_context(room, player_id)
                    actions = generate_legal_actions_dz(
                        room.hands[player_id],
                        room.last_play.card_play,
                        room.last_play.card_play is None,
                        play_mode="fifty_k",
                    )
                    action = _rank_fifty_k_rule_actions(
                        room.hands[player_id], actions, room.last_play.card_play, ctx
                    )[0]
                result = environment.step(player_id, action)
            except (IndexError, ValueError, RuntimeError):
                illegal_actions += 1
                break
            if result.done:
                scores = result.scores or {}
                if result.winner_id == model_player_id:
                    wins += 1
                others = [score for player_id, score in scores.items() if player_id != model_player_id]
                score_delta += scores[model_player_id] - sum(others) / len(others)
                break

        completed_games = game_index + 1
        if completed_games % report_interval == 0 or completed_games == games:
            logger.info(
                "510K 评测进度 %s/%s：胜率=%.3f，平均得分差=%.2f，非法率=%.3f",
                completed_games,
                games,
                wins / completed_games,
                score_delta / completed_games,
                illegal_actions / completed_games,
            )

    metrics = TrainingMetrics(
        win_rate_vs_rule=wins / games if games else 0.0,
        score_delta_vs_rule=score_delta / games if games else 0.0,
        illegal_action_rate=illegal_actions / games if games else 1.0,
    )
    logger.info(
        "510K 评测完成：胜率=%.3f，平均得分差=%.2f，非法率=%.3f",
        metrics.win_rate_vs_rule,
        metrics.score_delta_vs_rule,
        metrics.illegal_action_rate,
    )
    return metrics


def write_model_artifact(
    output_dir: Path,
    model: FiftyKActionValueModel,
    metrics: TrainingMetrics,
    *,
    training_episodes: int = 0,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "model.pt"
    torch.save({"state_dict": model.cpu().state_dict()}, checkpoint_path)
    checkpoint_hash = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    manifest = {
        "rules_version": FIFTY_K_RULES_VERSION,
        "features_version": FIFTY_K_FEATURES_VERSION,
        "checkpoint": checkpoint_path.name,
        "checkpoint_sha256": checkpoint_hash,
        "training_episodes": training_episodes,
        "metrics": asdict(metrics),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _cumulative_training_episodes(
    initial_checkpoint: Optional[Path],
    current_episodes: int,
) -> int:
    if initial_checkpoint is None:
        return current_episodes
    manifest_path = initial_checkpoint.parent / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_episodes = int(manifest.get("training_episodes", 0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        previous_episodes = 0
    return max(previous_episodes, 0) + current_episodes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="训练并评测 510K 专属动作价值模型")
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--actors", type=int, default=1)
    parser.add_argument("--rule-opponent-ratio", type=float, default=0.0)
    parser.add_argument("--exploration-rate", type=float, default=0.35)
    parser.add_argument("--teacher-episodes", type=int, default=0)
    parser.add_argument("--teacher-evaluation-games", type=int, default=50)
    parser.add_argument("--teacher-evaluation-interval", type=int, default=500)
    parser.add_argument("--teacher-min-agreement", type=float, default=0.85)
    parser.add_argument("--teacher-updates-per-batch", type=int, default=4)
    parser.add_argument("--rollout-updates-per-batch", type=int, default=4)
    parser.add_argument("--imitation-weight", type=float, default=0.0)
    parser.add_argument("--rollout-min-agreement", type=float, default=0.75)
    parser.add_argument("--rollout-candidates", type=int, default=0)
    parser.add_argument("--rollout-determinizations", type=int, default=2)
    parser.add_argument("--rollout-samples-per-episode", type=int, default=3)
    parser.add_argument("--min-exploration-rate", type=float, default=0.05)
    parser.add_argument("--checkpoint-interval", type=int, default=2000)
    parser.add_argument("--checkpoint-evaluation-games", type=int, default=100)
    parser.add_argument("--checkpoint-max-win-rate-drop", type=float, default=0.03)
    parser.add_argument("--evaluate-games", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--initial-checkpoint", type=Path)
    args = parser.parse_args()

    model = train_self_play(
        TrainingConfig(
            episodes=args.episodes,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            num_actors=args.actors,
            rule_opponent_ratio=args.rule_opponent_ratio,
            exploration_rate=args.exploration_rate,
            teacher_episodes=args.teacher_episodes,
            teacher_evaluation_games=args.teacher_evaluation_games,
            teacher_evaluation_interval=args.teacher_evaluation_interval,
            teacher_min_agreement=args.teacher_min_agreement,
            teacher_updates_per_batch=args.teacher_updates_per_batch,
            rollout_updates_per_batch=args.rollout_updates_per_batch,
            imitation_weight=args.imitation_weight,
            rollout_min_agreement=args.rollout_min_agreement,
            rollout_candidate_count=args.rollout_candidates,
            rollout_determinizations=args.rollout_determinizations,
            rollout_samples_per_episode=args.rollout_samples_per_episode,
            min_exploration_rate=args.min_exploration_rate,
            checkpoint_interval=args.checkpoint_interval,
            checkpoint_evaluation_games=args.checkpoint_evaluation_games,
            checkpoint_max_win_rate_drop=args.checkpoint_max_win_rate_drop,
            seed=args.seed,
            initial_checkpoint=args.initial_checkpoint,
        )
    )
    metrics = evaluate_against_rule(model, games=args.evaluate_games, seed=args.seed)
    manifest_path = write_model_artifact(
        args.output,
        model,
        metrics,
        training_episodes=_cumulative_training_episodes(
            args.initial_checkpoint,
            args.episodes,
        ),
    )
    logger.info("510K 模型产物已写入：%s", manifest_path)
    print(json.dumps({"manifest": str(manifest_path), "metrics": asdict(metrics)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
