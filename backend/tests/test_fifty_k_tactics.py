"""510K 固定战术回归集。

这些用例只断言稳定战术原则，不把某一局训练权重的偶然输出写成规则。
"""
from __future__ import annotations

import pytest

from app.domain.game import ai_strategy
from app.domain.game.ai_strategy import (
    AIContext,
    _choose_immediate_next_player_block,
    _rank_fifty_k_rule_actions,
    build_ai_context,
    generate_legal_actions_dz,
)
from app.domain.game.card_type import CardType, can_beat, detect_card_type
from app.domain.game.room import GameRoom, LastPlay, Player


TACTICAL_CATEGORIES = {
    "规则合法性",
    "首出减手",
    "完整牌形保护",
    "跟牌最小代价",
    "牌权控制",
    "分牌管理",
    "特殊牌节制",
    "对手听牌",
    "残局跑牌",
    "公开信息",
    "模型降级",
}


def _ctx(
    *,
    last_player: str | None = None,
    opponent_min: int = 10,
    trick_score: int = 0,
) -> AIContext:
    return AIContext(
        ai_id="p1",
        role="individual",
        landlord_id="p1",
        teammate_id=None,
        landlord_remaining=10,
        teammate_remaining=0,
        last_play_from=last_player,
        is_last_play_teammate=False,
        is_last_play_landlord=False,
        play_mode="fifty_k",
        player_ids=["p1", "p2", "p3"],
        player_remaining={"p1": 10, "p2": opponent_min, "p3": 10},
        other_players_min_remaining=opponent_min,
        current_trick_score=trick_score,
    )


def _rank(hand, last_play=None, *, opponent_min=10, trick_score=0):
    actions = generate_legal_actions_dz(
        hand,
        last_play,
        last_play is None,
        play_mode="fifty_k",
    )
    return _rank_fifty_k_rule_actions(
        hand,
        actions,
        last_play,
        _ctx(
            last_player="p2" if last_play else None,
            opponent_min=opponent_min,
            trick_score=trick_score,
        ),
    )


def _immediate_next_ctx(*, unseen_cards=None) -> AIContext:
    ctx = _ctx(last_player="p3", opponent_min=1)
    ctx.player_remaining = {"p1": 6, "p2": 1, "p3": 6}
    ctx.unseen_cards = list(unseen_cards or [])
    return ctx


def _block_choice(hand, last_cards, ctx, ranked_actions):
    last_play = detect_card_type(last_cards, play_mode="fifty_k")
    legal_actions = generate_legal_actions_dz(
        hand,
        last_play,
        False,
        play_mode="fifty_k",
    )
    return _choose_immediate_next_player_block(
        hand,
        legal_actions,
        ranked_actions,
        last_play,
        ctx,
    )


@pytest.mark.parametrize(
    ("cards", "expected_type"),
    [
        ([0], CardType.SINGLE),
        ([0, 1], CardType.PAIR),
        ([0, 1, 2, 4], CardType.TRIPLE_ONE),
        ([0, 1, 2, 4, 5], CardType.TRIPLE_TWO),
        ([0, 4, 8, 12, 16], CardType.STRAIGHT),
        ([0, 1, 4, 5, 8, 9], CardType.DOUBLE_STRAIGHT),
        ([0, 1, 2, 4, 5, 6], CardType.AIRPLANE),
        ([0, 1, 2, 3, 4, 8], CardType.FOUR_TWO_SINGLE),
        ([0, 1, 2, 3, 4, 5, 8, 9], CardType.FOUR_TWO_PAIR),
        ([8, 29, 42], CardType.FIFTY_K_FALSE),
        ([8, 28, 40], CardType.FIFTY_K_TRUE),
        ([0, 1, 2, 3], CardType.BOMB),
        ([52, 53], CardType.ROCKET),
    ],
)
def test_tactical_legal_pattern_catalog(cards, expected_type):
    play = detect_card_type(cards, play_mode="fifty_k")

    assert play is not None
    assert play.card_type == expected_type


@pytest.mark.parametrize(
    ("weaker", "stronger"),
    [
        ([0], [4]),
        ([8, 29, 42], [0, 1, 2, 3]),
        ([0, 1, 2, 3], [8, 28, 40]),
        ([8, 28, 40], [52, 53]),
    ],
)
def test_tactical_compression_hierarchy(weaker, stronger):
    weaker_play = detect_card_type(weaker, play_mode="fifty_k")
    stronger_play = detect_card_type(stronger, play_mode="fifty_k")

    assert weaker_play is not None and stronger_play is not None
    assert can_beat(stronger_play, weaker_play, play_mode="fifty_k") is True
    assert can_beat(weaker_play, stronger_play, play_mode="fifty_k") is False


@pytest.mark.parametrize(
    ("hand", "expected"),
    [
        ([0, 28, 48], [0]),
        ([0, 1, 4, 8], [0, 1]),
        ([0, 4, 8, 12, 16, 40], [0, 4, 8, 12, 16]),
        ([0, 1, 4, 5, 8, 9, 44], [0, 1, 4, 5, 8, 9]),
        ([4, 5, 6, 0, 44, 45], [0, 4, 5, 6]),
        ([8, 28, 40, 0], [0]),
        ([8, 29, 42, 0], [0]),
    ],
)
def test_tactical_lead_preserves_control_and_complete_patterns(hand, expected):
    assert set(_rank(hand)[0]) == set(expected)


@pytest.mark.parametrize(
    "hand",
    [
        [0],
        [0, 1],
        [0, 1, 2, 4],
        [0, 1, 2, 4, 5],
        [0, 4, 8, 12, 16],
        [0, 1, 4, 5, 8, 9],
        [0, 1, 2, 3, 4, 8],
        [0, 1, 2, 3, 4, 5, 8, 9],
        [8, 29, 42],
        [8, 28, 40],
        [0, 1, 2, 3],
        [52, 53],
    ],
)
def test_tactical_direct_finish_outranks_saving_the_pattern(hand):
    assert set(_rank(hand)[0]) == set(hand)


@pytest.mark.parametrize(
    ("hand", "last_cards", "expected"),
    [
        ([4, 8, 12], [0], [4]),
        ([4, 5, 8, 9, 12], [0, 1], [4, 5]),
        ([4, 5, 6, 8, 9, 10], [0, 1, 2], [4, 5, 6]),
        ([4, 8, 12, 16, 20, 24], [0, 4, 8, 12, 16], [4, 8, 12, 16, 20]),
        ([4, 5, 12], [0], [12]),
    ],
)
def test_tactical_follow_uses_smallest_non_breaking_response(hand, last_cards, expected):
    last_play = detect_card_type(last_cards, play_mode="fifty_k")

    assert set(_rank(hand, last_play)[0]) == set(expected)


def test_tactical_regular_response_is_used_before_bomb_or_pass():
    hand = [32, 4, 5, 6, 7]
    last_play = detect_card_type([28], play_mode="fifty_k")

    assert _rank(hand, last_play)[0] == [32]


def test_tactical_special_card_can_be_saved_when_it_is_the_only_response():
    hand = [4, 5, 6, 7, 0]
    last_play = detect_card_type([48], play_mode="fifty_k")

    assert _rank(hand, last_play, opponent_min=8, trick_score=0)[0] == []


def test_tactical_special_card_finishes_immediately_instead_of_passing():
    hand = [4, 5, 6, 7]
    last_play = detect_card_type([48], play_mode="fifty_k")

    assert set(_rank(hand, last_play, opponent_min=8, trick_score=0)[0]) == set(hand)


def test_tactical_four_with_large_pairs_does_not_destroy_bomb_without_finishing():
    hand = [40, 41, 42, 43, 44, 45, 48, 49, 0]

    first_play = detect_card_type(_rank(hand)[0], play_mode="fifty_k")

    assert first_play is not None
    assert first_play.card_type not in {CardType.FOUR_TWO_SINGLE, CardType.FOUR_TWO_PAIR}


def test_tactical_first_player_never_receives_pass_candidate():
    actions = generate_legal_actions_dz([0, 4], None, True, play_mode="fifty_k")

    assert [] not in actions


def test_tactical_follower_always_has_legal_pass_candidate():
    last_play = detect_card_type([0], play_mode="fifty_k")
    actions = generate_legal_actions_dz([4], last_play, False, play_mode="fifty_k")

    assert [] in actions


def test_immediate_next_block_uses_lowest_cost_special_when_single_is_not_safe():
    hand = [0, 1, 2, 3, 8, 29, 42]
    choice = _block_choice(
        hand,
        [48],
        _immediate_next_ctx(unseen_cards=[53]),
        [[], [0, 1, 2, 3], [8, 29, 42]],
    )

    assert set(choice) == {8, 29, 42}


def test_immediate_next_block_allows_pass_when_there_is_no_legal_response():
    choice = _block_choice(
        [0, 4],
        [53],
        _immediate_next_ctx(unseen_cards=[52]),
        [[]],
    )

    assert choice is None


def test_immediate_next_block_does_not_trigger_for_multi_card_table_play():
    choice = _block_choice(
        [4, 5, 8],
        [0, 1],
        _immediate_next_ctx(unseen_cards=[53]),
        [[], [4, 5]],
    )

    assert choice is None


def test_immediate_next_block_does_not_trigger_for_other_one_card_player():
    ctx = _immediate_next_ctx(unseen_cards=[0, 1, 2, 3])
    ctx.player_remaining = {"p1": 3, "p2": 4, "p3": 1}

    choice = _block_choice([8, 12, 53], [4], ctx, [[], [8], [53]])

    assert choice is None


def test_immediate_next_block_does_not_trigger_when_next_player_has_two_cards():
    ctx = _immediate_next_ctx(unseen_cards=[53])
    ctx.player_remaining["p2"] = 2

    choice = _block_choice([8, 12], [4], ctx, [[], [8], [12]])

    assert choice is None


def test_immediate_next_block_only_uses_public_room_context(monkeypatch):
    players = [
        Player(id="p1", nickname="P1", is_ai=True),
        Player(id="p2", nickname="P2"),
        Player(id="p3", nickname="P3"),
    ]
    room = GameRoom.create("public-block", players)
    room.play_mode = "fifty_k"
    room.hands = {"p1": [8, 12], "p2": [52], "p3": [53]}
    room.all_played_cards = [4]
    last_play = detect_card_type([4], play_mode="fifty_k")
    room.last_play = LastPlay(player="p3", cards=[4], card_play=last_play)

    hidden_swap = GameRoom.from_dict(room.to_dict())
    hidden_swap.hands["p2"], hidden_swap.hands["p3"] = (
        hidden_swap.hands["p3"],
        hidden_swap.hands["p2"],
    )
    original_ctx = build_ai_context(room, "p1")
    swapped_ctx = build_ai_context(hidden_swap, "p1")
    monkeypatch.setattr(ai_strategy.fifty_k_manager, "is_available", lambda: False)

    original_ranked = ai_strategy.ai_rank_play_candidates(
        room.hands["p1"], last_play, False, original_ctx, room=room
    )
    swapped_ranked = ai_strategy.ai_rank_play_candidates(
        hidden_swap.hands["p1"], last_play, False, swapped_ctx, room=hidden_swap
    )

    assert original_ctx == swapped_ctx
    assert original_ranked == swapped_ranked


@pytest.mark.parametrize(
    ("special_actions", "expected_type"),
    [
        (
            [[9, 30, 43], [0, 1, 2, 3], [8, 28, 40], [52, 53]],
            CardType.FIFTY_K_FALSE,
        ),
        ([[0, 1, 2, 3], [8, 28, 40], [52, 53]], CardType.BOMB),
        ([[8, 28, 40], [52, 53]], CardType.FIFTY_K_TRUE),
        ([[52, 53]], CardType.ROCKET),
    ],
)
def test_immediate_next_block_uses_complete_special_cost_order(
    special_actions, expected_type
):
    hand = [4] + [card for action in special_actions for card in action]
    choice = _choose_immediate_next_player_block(
        hand,
        special_actions,
        [[]],
        detect_card_type([48], play_mode="fifty_k"),
        _immediate_next_ctx(),
    )

    play = detect_card_type(choice, play_mode="fifty_k")
    assert play is not None
    assert play.card_type == expected_type


def test_immediate_next_block_prefers_direct_finish_over_saving_cards():
    choice = _block_choice(
        [4],
        [0],
        _immediate_next_ctx(unseen_cards=[53]),
        [[], [4]],
    )

    assert choice == [4]


def test_immediate_next_block_uses_highest_single_when_none_is_publicly_safe():
    choice = _block_choice(
        [8, 12],
        [4],
        _immediate_next_ctx(unseen_cards=[53]),
        [[], [8], [12]],
    )

    assert choice == [12]


def test_immediate_next_block_is_not_overwritten_by_endgame_search(monkeypatch):
    ctx = _immediate_next_ctx(unseen_cards=[0, 1, 2, 3])
    hand = [8, 12, 53]
    last_play = detect_card_type([4], play_mode="fifty_k")

    monkeypatch.setattr(ai_strategy.fifty_k_manager, "is_available", lambda: True)
    monkeypatch.setattr(
        ai_strategy.fifty_k_manager,
        "rank_actions",
        lambda hand, actions, last_play, ctx: [[], [8], [53]],
    )
    monkeypatch.setattr(ai_strategy, "should_search_fifty_k_endgame", lambda room, ai_id: True)

    def fail_if_searched(*args, **kwargs):
        raise AssertionError("门禁命中后不应执行随机残局搜索")

    monkeypatch.setattr(ai_strategy, "choose_fifty_k_endgame_action", fail_if_searched)

    ranked = ai_strategy.ai_rank_play_candidates(
        hand,
        last_play,
        False,
        ctx,
        room=object(),
    )

    assert ranked[0] == [53]


def test_tactical_catalog_has_broad_risk_dimensions():
    assert len(TACTICAL_CATEGORIES) >= 10
