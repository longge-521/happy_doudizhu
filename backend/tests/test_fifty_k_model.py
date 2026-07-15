import json
from unittest.mock import patch

import torch

import app.domain.game.fifty_k_model as fifty_k_model_module
from app.domain.game.ai_strategy import (
    AIContext,
    ai_rank_play_candidates,
    build_ai_context,
    generate_legal_actions_dz,
)
from app.domain.game.card_type import detect_card_type
from app.domain.game.fifty_k_model import (
    FIFTY_K_FEATURE_SIZE,
    FiftyKActionValueModel,
    FiftyKAgentManager,
    build_fifty_k_features,
)
from app.training.fifty_k.environment import FiftyKSelfPlayEnv


def _context() -> AIContext:
    return AIContext(
        ai_id="p1",
        role="individual",
        landlord_id="p1",
        teammate_id=None,
        landlord_remaining=6,
        teammate_remaining=0,
        last_play_from="p2",
        is_last_play_teammate=False,
        is_last_play_landlord=False,
        play_mode="fifty_k",
        player_ids=["p1", "p2", "p3"],
        player_remaining={"p1": 6, "p2": 5, "p3": 7},
        current_trick_score=35,
        current_multiplier=2,
        unseen_cards=[1, 2, 3, 4],
        play_history=[{"player": "p2", "cards": [8]}],
    )


def test_fifty_k_action_value_model_scores_each_candidate():
    model = FiftyKActionValueModel()

    scores = model(torch.zeros(3, FIFTY_K_FEATURE_SIZE))

    assert scores.shape == (3, 1)
    assert isinstance(model.history_lstm, torch.nn.LSTM)


def test_shared_history_batch_scoring_matches_regular_forward():
    model = FiftyKActionValueModel().eval()
    ctx = _context()
    features = torch.tensor([
        build_fifty_k_features([0, 4, 8], action, None, ctx)
        for action in ([0], [4], [8])
    ])

    with torch.inference_mode():
        regular_scores = model(features)
        shared_scores = model.score_actions_with_shared_history(features)

    assert torch.allclose(shared_scores, regular_scores, atol=1e-6)


def test_fifty_k_features_only_use_public_information():
    features = build_fifty_k_features(
        hand=[8, 28, 40, 0, 4, 12],
        action=[8, 28, 40],
        last_play=detect_card_type([8], play_mode="fifty_k"),
        ctx=_context(),
    )

    assert len(features) == FIFTY_K_FEATURE_SIZE
    assert any(features)


def test_fifty_k_features_encode_public_scores_recent_actors_and_trick_progress():
    ctx = _context()
    ctx.current_scores = {"p1": 20, "p2": 40, "p3": 80}
    ctx.trick_no = 9
    ctx.play_history = [
        {"player": "p2", "cards": []},
        {"player": "p3", "cards": [12]},
    ]

    features = build_fifty_k_features(
        hand=[8, 28, 40],
        action=[8],
        last_play=detect_card_type([12], play_mode="fifty_k"),
        ctx=ctx,
    )

    assert fifty_k_model_module.FIFTY_K_FEATURES_VERSION == "public_state_v3"
    assert fifty_k_model_module.HISTORY_LENGTH == 15
    history_offset = fifty_k_model_module.FIFTY_K_HISTORY_OFFSET
    history_step = fifty_k_model_module.FIFTY_K_HISTORY_STEP_SIZE
    recent_history = features[
        history_offset + 13 * history_step:
        history_offset + 15 * history_step
    ]
    assert recent_history[54:58] == [0.0, 1.0, 0.0, 1.0]
    assert recent_history[history_step + 54:history_step + 58] == [0.0, 0.0, 1.0, 0.0]

    score_offset = fifty_k_model_module.FIFTY_K_PUBLIC_STATE_OFFSET
    assert features[score_offset:score_offset + 3] == [
        20 / 140.0,
        40 / 140.0,
        80 / 140.0,
    ]
    assert features[score_offset + 3:score_offset + 6] == [0.0, 1.0, 0.0]
    assert features[score_offset + 9] == 9 / 54.0


def test_fifty_k_features_mark_when_candidate_breaks_a_bomb():
    ctx = _context()
    hand = [40, 41, 42, 43, 44, 45, 48, 49, 0]
    action = [40, 41, 42, 43, 44, 45, 48, 49]

    features = build_fifty_k_features(hand, action, None, ctx)

    structure_offset = fifty_k_model_module.FIFTY_K_STRUCTURE_OFFSET
    assert features[
        structure_offset + fifty_k_model_module.STRUCTURE_SPLIT_BOMB_INDEX
    ] == 1.0


def test_fifty_k_features_keep_exactly_last_fifteen_actions():
    ctx = _context()
    ctx.play_history = [
        {"player": ("p1", "p2", "p3")[index % 3], "cards": [index]}
        for index in range(16)
    ]

    features = build_fifty_k_features([40], [40], None, ctx)

    history_offset = fifty_k_model_module.FIFTY_K_HISTORY_OFFSET
    first_kept_action = features[
        history_offset:history_offset + fifty_k_model_module.CARD_VECTOR_SIZE
    ]
    assert first_kept_action[1] == 1.0
    assert first_kept_action[0] == 0.0


def test_build_ai_context_includes_public_scores_and_trick_number():
    room = FiftyKSelfPlayEnv(seed=7).reset()
    room.scores = {"p1": 15, "p2": 35, "p3": 50}
    room.trick_no = 6

    ctx = build_ai_context(room, "p1")

    assert ctx.current_scores == room.scores
    assert ctx.trick_no == 6


def test_fifty_k_features_normalize_full_one_hundred_forty_point_pool():
    ctx = _context()
    ctx.current_trick_score = 140

    features = build_fifty_k_features(
        hand=[8, 28, 40],
        action=[8],
        last_play=None,
        ctx=ctx,
    )

    assert features[fifty_k_model_module.FIFTY_K_PUBLIC_STATE_OFFSET + 10] == 1.0


def test_fifty_k_manager_rejects_manifest_for_another_rule_version(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"rules_version": "other"}), encoding="utf-8")

    manager = FiftyKAgentManager(model_dir=tmp_path)

    assert manager.is_available() is False


def test_fifty_k_manager_rejects_legacy_feature_schema(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({
            "rules_version": fifty_k_model_module.FIFTY_K_RULES_VERSION,
            "metrics": {
                "win_rate_vs_rule": 0.40,
                "score_delta_vs_rule": 0.0,
                "illegal_action_rate": 0.0,
            },
        }),
        encoding="utf-8",
    )

    manager = FiftyKAgentManager(model_dir=tmp_path)

    assert manager.is_available() is False
    assert manager.load_error == "模型特征版本不兼容"


def test_fifty_k_candidate_ranking_uses_loaded_model_scores():
    ctx = _context()
    hand = [0, 8, 12, 28, 40, 44]
    last_play = detect_card_type([8], play_mode="fifty_k")

    with patch("app.domain.game.ai_strategy.fifty_k_manager") as manager:
        manager.is_available.return_value = True
        manager.rank_actions.return_value = [[44], [12], []]

        candidates = ai_rank_play_candidates(hand, last_play, False, ctx)

    assert candidates[:3] == [[44], [12], []]


def test_fifty_k_immediate_next_player_one_card_forces_highest_safe_single():
    ctx = _context()
    ctx.last_play_from = "p3"
    ctx.player_remaining = {"p1": 3, "p2": 1, "p3": 4}
    ctx.other_players_min_remaining = 1
    ctx.unseen_cards = [0, 1, 2, 3]
    hand = [8, 12, 53]
    last_play = detect_card_type([4], play_mode="fifty_k")

    with patch("app.domain.game.ai_strategy.fifty_k_manager") as manager:
        manager.is_available.return_value = True
        manager.rank_actions.return_value = [[], [8], [53]]

        candidates = ai_rank_play_candidates(hand, last_play, False, ctx)

    assert candidates[0] == [53]


def test_fifty_k_model_reranks_all_legal_candidates():
    ctx = _context()
    hand = [0, 4, 8, 12, 16, 20]
    rule_ranked = [[0], [4], [8], [12], [16], [20]]

    with patch("app.domain.game.ai_strategy.fifty_k_manager") as manager:
        manager.is_available.return_value = True
        manager.rank_actions.return_value = [[20], [16], [12], [8], [4], [0]]
        with patch(
            "app.domain.game.ai_strategy._rank_fifty_k_rule_actions",
            return_value=rule_ranked,
        ):
            candidates = ai_rank_play_candidates(hand, None, True, ctx)

    assert manager.rank_actions.call_args.args[1] == rule_ranked
    assert candidates == [[20], [16], [12], [8], [4], [0]]


def test_fifty_k_candidate_ranking_falls_back_to_rule_when_model_inference_fails():
    ctx = _context()
    hand = [0, 8, 12, 28, 40, 44]
    last_play = detect_card_type([8], play_mode="fifty_k")

    with patch("app.domain.game.ai_strategy.fifty_k_manager") as manager:
        manager.is_available.return_value = True
        manager.rank_actions.side_effect = RuntimeError("模型推理异常")
        with patch("app.domain.game.ai_strategy._rank_fifty_k_rule_actions", return_value=[[12], []]) as fallback:
            candidates = ai_rank_play_candidates(hand, last_play, False, ctx)

    fallback.assert_called_once()
    assert candidates == [[12], []]


def test_fifty_k_candidates_preserve_each_scored_card_suit_for_special_combinations():
    hand = [8, 9, 28, 29, 40, 41]

    candidates = generate_legal_actions_dz(hand, None, True, play_mode="fifty_k")

    assert [8] in candidates
    assert [9] in candidates
    assert [28] in candidates
    assert [29] in candidates
    assert [40] in candidates
    assert [41] in candidates
    assert [8, 28, 40] in candidates
    assert [9, 29, 41] in candidates
