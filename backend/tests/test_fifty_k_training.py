from app.training.fifty_k.environment import FiftyKSelfPlayEnv, terminal_reward
import copy
import logging
import math
import os
from pathlib import Path
import random
import subprocess
import sys

import pytest
import torch

import app.training.fifty_k.trainer as trainer_module

from app.training.fifty_k.trainer import (
    DEFAULT_MODEL_DIR,
    TrainingConfig,
    TrainingMetrics,
    RolloutExample,
    _collect_episode,
    collect_self_play_batch,
    _full_ranking_loss_from_scores,
    _rollout_action_values,
    _rollout_value_loss,
    _teacher_gate_passed,
    _top1_accuracy_from_scores,
    evaluate_rule_agreement,
    _is_better_checkpoint,
    _relative_terminal_rewards,
    _select_rule_opponents,
    exploration_rate_at,
    train_self_play,
    write_model_artifact,
)
from app.domain.game.fifty_k_model import FiftyKActionValueModel, FiftyKAgentManager


def test_fifty_k_terminal_reward_prioritizes_winning_before_score():
    scores = {"p1": 80, "p2": 40, "p3": 20}

    assert terminal_reward("p1", scores, "p1") == 1050
    assert terminal_reward("p2", scores, "p1") == -10


def test_fifty_k_terminal_reward_uses_remaining_card_penalty():
    scores = {"p1": 85, "p2": 20, "p3": 35}
    penalty_adjusted_scores = {"p1": 60, "p2": 0, "p3": 80}

    raw_reward = terminal_reward("p1", scores, "p3")
    penalty_reward = terminal_reward("p1", penalty_adjusted_scores, "p3")

    assert raw_reward == 57.5
    assert penalty_reward == 20


def test_fifty_k_environment_returns_remaining_card_penalty_scores():
    environment = FiftyKSelfPlayEnv(seed=1)
    room = environment.reset()
    room.hands = {"p1": [4], "p2": [8], "p3": [28]}
    room.scores = {"p1": 50, "p2": 30, "p3": 5}
    room.current_turn = "p1"

    result = environment.step("p1", [4])

    assert result.done is True
    assert result.winner_id == "p1"
    assert result.scores == {"p1": 65, "p2": 25, "p3": -5}
    assert result.rewards["p2"] == -5


def test_fifty_k_self_play_environment_deals_eighteen_cards_and_club_three_leads():
    environment = FiftyKSelfPlayEnv(seed=7)
    room = environment.reset()

    assert all(len(hand) == 18 for hand in room.hands.values())
    assert sum(len(hand) for hand in room.hands.values()) == 54
    assert 2 in room.hands[room.current_turn]
    assert environment.legal_actions(room.current_turn)


def test_fifty_k_training_artifact_can_only_load_after_passing_metrics(tmp_path):
    metrics = TrainingMetrics(
        win_rate_vs_rule=0.40,
        score_delta_vs_rule=0.0,
        illegal_action_rate=0.0,
    )

    write_model_artifact(
        tmp_path,
        FiftyKActionValueModel(),
        metrics,
        training_episodes=20_000,
    )

    assert FiftyKAgentManager(model_dir=tmp_path).is_available() is True

    manifest = __import__("json").loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["training_episodes"] == 20_000


def test_fifty_k_training_default_output_matches_runtime_model_directory():
    assert DEFAULT_MODEL_DIR == FiftyKAgentManager().model_dir


def test_fifty_k_training_reports_start_and_batch_progress(caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")

    train_self_play(
        TrainingConfig(
            episodes=1,
            batch_size=1,
            num_actors=1,
            seed=7,
            checkpoint_interval=0,
            checkpoint_evaluation_games=0,
        )
    )

    messages = [record.getMessage() for record in caplog.records]
    assert any("phase=rollout" in message for message in messages)
    assert any("DMC" in message for message in messages)
    assert any("510K 训练开始" in message for message in messages)
    assert any("510K 训练进度 1/1" in message for message in messages)
    assert any("带探索训练胜率=" in message and "本批" in message and "累计" in message for message in messages)
    assert any("模拟排序损失=" in message for message in messages)


def test_training_switches_from_teacher_to_rollout_phase(caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")

    train_self_play(
        TrainingConfig(
            episodes=2,
            batch_size=1,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=0.0,
            rollout_candidate_count=1,
            checkpoint_interval=0,
            num_actors=1,
            seed=7,
        )
    )

    messages = [record.getMessage() for record in caplog.records]
    assert any("phase=teacher" in message for message in messages)
    assert any("phase=rollout" in message for message in messages)
    assert any("模拟位置=开局" in message for message in messages)


def test_training_stays_in_teacher_phase_when_rule_agreement_gate_fails(caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")

    train_self_play(
        TrainingConfig(
            episodes=2,
            batch_size=1,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=1.1,
            checkpoint_interval=0,
            num_actors=1,
            seed=7,
        )
    )

    phase_messages = [record.getMessage() for record in caplog.records if "phase=" in record.getMessage()]
    assert phase_messages
    assert all("phase=teacher" in message for message in phase_messages)


def test_teacher_phase_runs_configured_optimizer_updates(monkeypatch):
    step_calls = 0
    original_step = torch.optim.Adam.step

    def counted_step(optimizer, *args, **kwargs):
        nonlocal step_calls
        step_calls += 1
        return original_step(optimizer, *args, **kwargs)

    monkeypatch.setattr(torch.optim.Adam, "step", counted_step)

    train_self_play(
        TrainingConfig(
            episodes=1,
            batch_size=1,
            teacher_episodes=1,
            teacher_evaluation_games=0,
            teacher_updates_per_batch=3,
            checkpoint_interval=0,
            num_actors=1,
            seed=7,
        )
    )

    assert step_calls == 3


def test_rollout_phase_runs_configured_optimizer_updates(monkeypatch):
    step_calls = 0
    original_step = torch.optim.Adam.step

    def counted_step(optimizer, *args, **kwargs):
        nonlocal step_calls
        step_calls += 1
        return original_step(optimizer, *args, **kwargs)

    monkeypatch.setattr(torch.optim.Adam, "step", counted_step)

    train_self_play(
        TrainingConfig(
            episodes=2,
            batch_size=1,
            teacher_episodes=1,
            teacher_evaluation_games=0,
            teacher_updates_per_batch=1,
            rollout_updates_per_batch=3,
            rollout_candidate_count=0,
            checkpoint_interval=0,
            num_actors=1,
            seed=7,
        )
    )

    assert step_calls == 4


def test_failed_teacher_gate_restores_best_agreement_instead_of_win_checkpoint(monkeypatch):
    agreement_states = []
    checkpoint_calls = 0

    def capture_state(model):
        return {
            name: parameter.detach().cpu().clone()
            for name, parameter in model.state_dict().items()
        }

    def fake_rule_agreement(model, games, seed):
        agreement_states.append(capture_state(model))
        return (0.70, 0.80)[len(agreement_states) - 1]

    def fake_game_evaluation(model, games, seed):
        nonlocal checkpoint_calls
        checkpoint_calls += 1
        return TrainingMetrics(
            win_rate_vs_rule=1.0 if checkpoint_calls == 1 else 0.0,
            score_delta_vs_rule=0.0,
            illegal_action_rate=0.0,
        )

    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_rule_agreement",
        fake_rule_agreement,
    )
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_against_rule",
        fake_game_evaluation,
    )

    model = train_self_play(
        TrainingConfig(
            episodes=2,
            batch_size=1,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_evaluation_interval=1,
            teacher_min_agreement=1.1,
            teacher_updates_per_batch=1,
            checkpoint_interval=1,
            checkpoint_evaluation_games=1,
            num_actors=1,
            seed=7,
        )
    )

    returned_state = capture_state(model)
    assert checkpoint_calls == 0
    assert all(
        torch.equal(returned_state[name], agreement_states[-1][name])
        for name in returned_state
    )


def test_rollout_guard_restores_best_teacher_weights(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")
    agreement_states = []
    formal_evaluations = 0

    def capture_state(model):
        return {
            name: parameter.detach().cpu().clone()
            for name, parameter in model.state_dict().items()
        }

    def fake_rule_agreement(model, games, seed):
        agreement_states.append(capture_state(model))
        return (0.90, 0.50)[len(agreement_states) - 1]

    def record_teacher_baseline(model, games, seed):
        nonlocal formal_evaluations
        formal_evaluations += 1
        return TrainingMetrics(
            win_rate_vs_rule=0.30,
            score_delta_vs_rule=0.0,
            illegal_action_rate=0.0,
        )

    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_rule_agreement",
        fake_rule_agreement,
    )
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_against_rule",
        record_teacher_baseline,
    )

    model = train_self_play(
        TrainingConfig(
            episodes=2,
            batch_size=1,
            exploration_rate=0.0,
            min_exploration_rate=0.0,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=0.85,
            rollout_min_agreement=0.75,
            rollout_candidate_count=1,
            checkpoint_interval=1,
            checkpoint_evaluation_games=1,
            num_actors=1,
            seed=7,
        )
    )

    returned_state = capture_state(model)
    assert len(agreement_states) == 2
    assert formal_evaluations == 1
    assert all(
        torch.equal(returned_state[name], agreement_states[0][name])
        for name in returned_state
    )
    assert any(
        "rollout 一致率保护" in record.getMessage()
        for record in caplog.records
    )


def test_passing_teacher_gate_seeds_formal_checkpoint_baseline(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")
    formal_evaluations = 0

    def fake_rule_agreement(model, games, seed):
        return 0.90

    def fake_formal_evaluation(model, games, seed):
        nonlocal formal_evaluations
        formal_evaluations += 1
        return TrainingMetrics(
            win_rate_vs_rule=0.33,
            score_delta_vs_rule=-1.0,
            illegal_action_rate=0.0,
        )

    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_rule_agreement",
        fake_rule_agreement,
    )
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_against_rule",
        fake_formal_evaluation,
    )

    train_self_play(
        TrainingConfig(
            episodes=1,
            batch_size=1,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=0.85,
            checkpoint_interval=1,
            checkpoint_evaluation_games=1,
            num_actors=1,
            seed=7,
        )
    )

    assert formal_evaluations == 1
    assert any(
        "teacher 正式基线" in record.getMessage()
        for record in caplog.records
    )


def test_training_evaluates_unchecked_rollout_tail_before_restoring_best(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")
    evaluated_states = []
    evaluation_metrics = iter((
        TrainingMetrics(0.30, 0.0, 0.0),
        TrainingMetrics(0.20, -5.0, 0.0),
        TrainingMetrics(0.40, 2.0, 0.0),
    ))

    def capture_state(model):
        return {
            name: parameter.detach().cpu().clone()
            for name, parameter in model.state_dict().items()
        }

    def fake_formal_evaluation(model, games, seed):
        evaluated_states.append(capture_state(model))
        return next(evaluation_metrics)

    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_rule_agreement",
        lambda model, games, seed: 0.90,
    )
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_against_rule",
        fake_formal_evaluation,
    )

    model = train_self_play(
        TrainingConfig(
            episodes=3,
            batch_size=1,
            exploration_rate=0.0,
            min_exploration_rate=0.0,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=0.85,
            rollout_min_agreement=0.75,
            rollout_candidate_count=1,
            checkpoint_interval=2,
            checkpoint_evaluation_games=1,
            num_actors=1,
            seed=7,
        )
    )

    returned_state = capture_state(model)
    assert len(evaluated_states) == 3
    assert all(
        torch.equal(returned_state[name], evaluated_states[-1][name])
        for name in returned_state
    )
    assert any(
        "最终检查点 3 局成为当前最佳" in record.getMessage()
        for record in caplog.records
    )


def test_failed_rollout_checkpoint_restores_best_before_next_training_batch(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")
    evaluated_states = []
    evaluation_metrics = iter((
        TrainingMetrics(0.40, 2.0, 0.0),
        TrainingMetrics(0.30, -2.0, 0.0),
        TrainingMetrics(0.30, -2.0, 0.0),
    ))

    def capture_state(model):
        return {
            name: parameter.detach().cpu().clone()
            for name, parameter in model.state_dict().items()
        }

    def fake_formal_evaluation(model, games, seed):
        evaluated_states.append(capture_state(model))
        return next(evaluation_metrics)

    def deterministic_step(optimizer, closure=None):
        with torch.no_grad():
            for group in optimizer.param_groups:
                for parameter in group["params"]:
                    parameter.add_(0.001)

    monkeypatch.setattr(torch.optim.Adam, "step", deterministic_step)
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_rule_agreement",
        lambda model, games, seed: 0.90,
    )
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_against_rule",
        fake_formal_evaluation,
    )

    train_self_play(
        TrainingConfig(
            episodes=3,
            batch_size=1,
            exploration_rate=0.0,
            min_exploration_rate=0.0,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=0.85,
            rollout_min_agreement=0.75,
            rollout_candidate_count=1,
            checkpoint_interval=2,
            checkpoint_evaluation_games=1,
            num_actors=1,
            seed=7,
        )
    )

    assert len(evaluated_states) == 3
    assert all(
        torch.equal(evaluated_states[1][name], evaluated_states[2][name])
        for name in evaluated_states[1]
    )
    assert any(
        "未超过最佳，已恢复最佳权重并重置优化器" in record.getMessage()
        for record in caplog.records
    )


def test_statistically_tied_rollout_checkpoint_continues_from_current_weights(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.training.fifty_k.trainer")
    evaluated_states = []
    evaluation_metrics = iter((
        TrainingMetrics(0.40, 2.0, 0.0),
        TrainingMetrics(0.39, 1.0, 0.0),
        TrainingMetrics(0.41, 3.0, 0.0),
    ))

    def capture_state(model):
        return {
            name: parameter.detach().cpu().clone()
            for name, parameter in model.state_dict().items()
        }

    def fake_formal_evaluation(model, games, seed):
        evaluated_states.append(capture_state(model))
        return next(evaluation_metrics)

    def deterministic_step(optimizer, closure=None):
        with torch.no_grad():
            for group in optimizer.param_groups:
                for parameter in group["params"]:
                    parameter.add_(0.001)

    monkeypatch.setattr(torch.optim.Adam, "step", deterministic_step)
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_rule_agreement",
        lambda model, games, seed: 0.90,
    )
    monkeypatch.setattr(
        "app.training.fifty_k.trainer.evaluate_against_rule",
        fake_formal_evaluation,
    )

    train_self_play(
        TrainingConfig(
            episodes=3,
            batch_size=1,
            exploration_rate=0.0,
            min_exploration_rate=0.0,
            teacher_episodes=1,
            teacher_evaluation_games=1,
            teacher_min_agreement=0.85,
            rollout_min_agreement=0.75,
            rollout_candidate_count=1,
            checkpoint_interval=2,
            checkpoint_evaluation_games=1,
            num_actors=1,
            seed=7,
        )
    )

    assert len(evaluated_states) == 3
    assert any(
        not torch.equal(evaluated_states[1][name], evaluated_states[2][name])
        for name in evaluated_states[1]
    )
    assert any(
        "统计持平，保留当前权重继续训练" in record.getMessage()
        for record in caplog.records
    )


def test_training_seed_reproduces_initial_model_weights():
    first = train_self_play(TrainingConfig(episodes=0, seed=7))
    second = train_self_play(TrainingConfig(episodes=0, seed=7))

    assert all(
        torch.equal(first.state_dict()[name], second.state_dict()[name])
        for name in first.state_dict()
    )


def test_training_can_resume_from_an_existing_checkpoint(tmp_path):
    source = FiftyKActionValueModel()
    for parameter in source.parameters():
        parameter.data.fill_(0.125)
    checkpoint = tmp_path / "model.pt"
    torch.save({"state_dict": source.state_dict()}, checkpoint)

    resumed = train_self_play(
        TrainingConfig(episodes=0, initial_checkpoint=checkpoint, seed=7)
    )

    assert all(
        torch.equal(resumed.state_dict()[name], source.state_dict()[name])
        for name in source.state_dict()
    )


def test_episode_collection_tracks_model_win_against_two_rule_opponents():
    collection = _collect_episode(
        FiftyKActionValueModel(),
        seed=7,
        exploration_rate=0.0,
        rule_opponent_ratio=1.0,
        rollout_candidate_count=2,
    )

    assert collection.model_vs_rule_games == 1
    assert collection.model_vs_rule_wins in (0, 1)
    assert collection.transitions
    assert len(collection.rollout_examples) == 1
    assert all(len(example.candidate_features) <= 2 for example in collection.rollout_examples)
    assert sum(collection.rollout_position_counts) == 1


def test_episode_collection_can_sample_multiple_rollout_decisions():
    collection = _collect_episode(
        FiftyKActionValueModel(),
        seed=7,
        exploration_rate=0.0,
        rule_opponent_ratio=1.0,
        rollout_candidate_count=2,
        rollout_samples_per_episode=3,
    )

    assert len(collection.rollout_examples) == 3
    assert all(len(example.candidate_features) <= 2 for example in collection.rollout_examples)
    assert sum(collection.rollout_position_counts) == 3


def test_rollout_reservoir_samples_the_whole_episode_uniformly():
    assert hasattr(trainer_module, "_reservoir_should_replace")
    total_decisions = 30
    position_counts = [0, 0, 0]

    for seed in range(600):
        rng = random.Random(seed)
        selected_index = 0
        for seen_count in range(1, total_decisions + 1):
            if trainer_module._reservoir_should_replace(rng, seen_count):
                selected_index = seen_count - 1
        bucket = min(selected_index * 3 // total_decisions, 2)
        position_counts[bucket] += 1

    assert all(150 <= count <= 250 for count in position_counts)


def test_teacher_episode_collects_rule_ranking_labels_without_claiming_model_win():
    collection = _collect_episode(
        FiftyKActionValueModel(),
        seed=7,
        exploration_rate=0.0,
        rule_opponent_ratio=1.0,
        force_rule_for_model=True,
    )

    assert collection.transitions == []
    assert collection.model_vs_rule_games == 0
    assert collection.teacher_examples
    assert all(
        sorted(example.target_order) == list(range(len(example.candidate_features)))
        for example in collection.teacher_examples
    )


def test_full_rule_ranking_loss_and_top1_accuracy_follow_the_whole_order():
    groups = [(0, 3, [0, 1, 2])]
    better_scores = torch.tensor([3.0, 2.0, 1.0])
    worse_scores = torch.tensor([1.0, 2.0, 3.0])

    better = _full_ranking_loss_from_scores(
        better_scores,
        groups,
    )
    worse = _full_ranking_loss_from_scores(
        worse_scores,
        groups,
    )

    assert better < worse
    assert _top1_accuracy_from_scores(better_scores, groups) == 1.0
    assert _top1_accuracy_from_scores(worse_scores, groups) == 0.0


def test_rollout_ranking_loss_preserves_terminal_reward_priority():
    class FirstFeatureScore(torch.nn.Module):
        def forward(self, features):
            return features[:, :1]

    candidate_features = [[0.0], [0.0]]
    model = FirstFeatureScore()
    device = torch.device("cpu")

    win_flip = _rollout_value_loss(
        model,
        [RolloutExample(candidate_features, [1.0, 0.0])],
        device,
    )
    five_point_gain = _rollout_value_loss(
        model,
        [RolloutExample(candidate_features, [0.005, 0.0])],
        device,
    )

    assert win_flip.item() > five_point_gain.item() * 100


def test_rollout_ranking_loss_ignores_equal_value_candidates():
    class FirstFeatureScore(torch.nn.Module):
        def forward(self, features):
            return features[:, :1]

    loss = _rollout_value_loss(
        FirstFeatureScore(),
        [RolloutExample([[3.0], [1.0]], [0.5, 0.5])],
        torch.device("cpu"),
    )

    assert loss.item() == pytest.approx(0.0)


def test_rollout_action_values_do_not_mutate_source_room():
    environment = FiftyKSelfPlayEnv(seed=7)
    room = environment.reset()
    player_id = room.current_turn
    actions = environment.legal_actions(player_id)
    before = copy.deepcopy(room.to_dict())

    values = _rollout_action_values(
        room,
        player_id,
        actions,
        max_candidates=2,
        determinizations=2,
        determinization_seed=11,
    )

    assert 1 <= len(values) <= 2
    assert all(math.isfinite(value) for value in values)
    assert room.to_dict() == before


def test_public_rollout_determinizations_redistribute_hidden_hands_reproducibly():
    assert hasattr(trainer_module, "_public_determinized_states")
    environment = FiftyKSelfPlayEnv(seed=7)
    room = environment.reset()
    observer_id = room.current_turn
    before = copy.deepcopy(room.to_dict())
    opponent_ids = [player.id for player in room.players if player.id != observer_id]

    states = trainer_module._public_determinized_states(
        room,
        observer_id,
        count=2,
        seed=11,
    )
    repeated = trainer_module._public_determinized_states(
        room,
        observer_id,
        count=2,
        seed=11,
    )

    assert states == repeated
    assert room.to_dict() == before
    assert len(states) == 2
    assert all(state["hands"][observer_id] == before["hands"][observer_id] for state in states)
    assert all(
        len(state["hands"][opponent_id]) == len(before["hands"][opponent_id])
        for state in states
        for opponent_id in opponent_ids
    )
    assert all(
        sorted(card_id for hand in state["hands"].values() for card_id in hand)
        == list(range(54))
        for state in states
    )
    assert any(
        state["hands"][opponent_id] != before["hands"][opponent_id]
        for state in states
        for opponent_id in opponent_ids
    )


def test_teacher_gate_requires_configured_top1_agreement():
    assert _teacher_gate_passed(0.85, 0.85)
    assert not _teacher_gate_passed(0.849, 0.85)


def test_rule_agreement_evaluation_is_reproducible():
    model = FiftyKActionValueModel().eval()

    first = evaluate_rule_agreement(model, games=2, seed=7)
    second = evaluate_rule_agreement(model, games=2, seed=7)

    assert first == second
    assert 0.0 <= first <= 1.0


def test_training_module_reports_live_win_rate_from_windows_worker_processes(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "APP_DISTRIBUTED_MODE": "false"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.training.fifty_k.trainer",
            "--episodes",
            "2",
            "--batch-size",
            "2",
            "--actors",
            "2",
            "--teacher-episodes",
            "1",
            "--teacher-evaluation-games",
            "1",
            "--teacher-min-agreement",
            "0",
            "--rollout-candidates",
            "1",
            "--checkpoint-interval",
            "0",
            "--evaluate-games",
            "0",
            "--output",
            str(tmp_path / "model"),
        ],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "带探索训练胜率=" in f"{result.stdout}\n{result.stderr}"
    assert "phase=teacher" in f"{result.stdout}\n{result.stderr}"
    assert "phase=rollout" in f"{result.stdout}\n{result.stderr}"


def test_batch_collection_uses_the_training_owned_worker_pool():
    class InlineExecutor:
        def __init__(self):
            self.map_calls = 0

        def map(self, worker, payloads):
            self.map_calls += 1
            return [worker(payload) for payload in payloads]

    executor = InlineExecutor()
    collection = collect_self_play_batch(
        FiftyKActionValueModel(),
        seeds=[7, 8],
        exploration_rate=0.0,
        num_actors=2,
        rule_opponent_ratio=1.0,
        worker_executor=executor,
        rollout_candidate_count=1,
    )

    assert executor.map_calls == 1
    assert collection.teacher_examples
    assert len(collection.rollout_examples) == 2
    assert sum(collection.rollout_position_counts) == 2


def test_training_config_mixes_rule_opponents_and_decays_exploration():
    config = TrainingConfig(
        episodes=100,
        rule_opponent_ratio=0.5,
        exploration_rate=0.35,
        min_exploration_rate=0.05,
    )

    assert _select_rule_opponents(__import__("random").Random(7), 1.0)
    assert not _select_rule_opponents(__import__("random").Random(7), 0.0)
    assert exploration_rate_at(config, 0) == pytest.approx(0.35)
    assert exploration_rate_at(config, 100) == pytest.approx(0.05)
    assert TrainingConfig().rule_opponent_ratio == 0.0
    assert TrainingConfig().teacher_episodes == 0
    assert TrainingConfig().teacher_min_agreement == 0.85
    assert TrainingConfig().teacher_updates_per_batch == 4
    assert TrainingConfig().rollout_updates_per_batch == 4
    assert TrainingConfig().rollout_samples_per_episode == 3
    assert TrainingConfig().imitation_weight == 0.0
    assert TrainingConfig().rollout_min_agreement == 0.75
    assert TrainingConfig().rollout_candidate_count == 0


def test_relative_terminal_rewards_are_zero_sum():
    rewards = _relative_terminal_rewards({"p1": 1060.0, "p2": -20.0, "p3": -40.0})

    assert sum(rewards.values()) == pytest.approx(0.0)
    assert rewards["p1"] > rewards["p2"]


def test_dmc_episode_records_terminal_return_for_every_model_seat():
    collection = _collect_episode(
        FiftyKActionValueModel(),
        seed=7,
        exploration_rate=0.0,
        rule_opponent_ratio=0.0,
        rollout_candidate_count=0,
    )

    assert collection.transitions
    assert {transition.player_id for transition in collection.transitions} == {
        "p1",
        "p2",
        "p3",
    }
    assert all(math.isfinite(transition.target) for transition in collection.transitions)
    assert any(transition.target > 0 for transition in collection.transitions)
    assert any(transition.target < 0 for transition in collection.transitions)


def test_dmc_episode_does_not_serialize_unused_teacher_candidates():
    collection = _collect_episode(
        FiftyKActionValueModel(),
        seed=7,
        exploration_rate=0.0,
        rule_opponent_ratio=0.0,
        rollout_candidate_count=0,
        collect_teacher_examples=False,
    )

    assert collection.transitions
    assert collection.teacher_examples == []


def test_monte_carlo_loss_regresses_selected_action_to_terminal_return():
    transition_type = trainer_module.MonteCarloTransition
    model = FiftyKActionValueModel()
    transition = transition_type(
        features=[0.0] * trainer_module.FIFTY_K_FEATURE_SIZE,
        target=0.5,
        player_id="p1",
    )

    loss = trainer_module._monte_carlo_loss(
        model,
        [transition],
        torch.device("cpu"),
    )

    assert loss.ndim == 0
    assert math.isfinite(loss.item())
    assert loss.item() >= 0


def test_dmc_training_defaults_to_three_model_seats_without_teacher_filter():
    config = TrainingConfig()

    assert config.rule_opponent_ratio == 0.0
    assert config.teacher_episodes == 0
    assert config.rollout_candidate_count == 0
    assert config.imitation_weight == 0.0


def test_formal_evaluation_rotates_three_seats_on_the_same_deal():
    assert [trainer_module._evaluation_deal_seed(7, index) for index in range(6)] == [
        7,
        7,
        7,
        8,
        8,
        8,
    ]


def test_continued_training_manifest_counts_previous_episodes(tmp_path):
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"checkpoint")
    (tmp_path / "manifest.json").write_text(
        '{"training_episodes": 5000}',
        encoding="utf-8",
    )

    assert trainer_module._cumulative_training_episodes(checkpoint, 15_000) == 20_000


def test_checkpoint_comparison_prefers_safe_higher_win_rate_then_score():
    baseline = TrainingMetrics(win_rate_vs_rule=0.40, score_delta_vs_rule=0.0, illegal_action_rate=0.0)

    assert _is_better_checkpoint(
        TrainingMetrics(win_rate_vs_rule=0.41, score_delta_vs_rule=-10.0, illegal_action_rate=0.0),
        baseline,
    )
    assert _is_better_checkpoint(
        TrainingMetrics(win_rate_vs_rule=0.40, score_delta_vs_rule=1.0, illegal_action_rate=0.0),
        baseline,
    )
    assert not _is_better_checkpoint(
        TrainingMetrics(win_rate_vs_rule=0.90, score_delta_vs_rule=10.0, illegal_action_rate=0.01),
        baseline,
    )


def test_fifty_k_terminal_step_returns_one_final_score_snapshot():
    environment = FiftyKSelfPlayEnv(seed=11)
    room = environment.reset()

    for _ in range(200):
        result = environment.step(room.current_turn, environment.legal_actions(room.current_turn)[0])
        if result.done:
            assert result.winner_id in room.hands
            assert result.scores == room.scores
            assert sum(result.scores.values()) == 140
            return

    raise AssertionError("自博弈未在合理步数内结束")
