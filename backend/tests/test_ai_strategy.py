# backend/tests/test_ai_strategy.py
import pytest
from app.domain.game.ai_strategy import (
    ai_decide_call, ai_decide_play, build_ai_context,
    _decompose_hand, _pick_lead_play, _pick_follow_play, _should_use_bomb,
    AIContext, HandPlan
)
from app.domain.game.card_type import detect_card_type, CardType


class TestAIDecideCall:
    def test_strong_hand_calls_high(self):
        """有王炸和炸弹的强牌应叫高分"""
        hand = [52, 53, 0, 1, 2, 3, 44, 45, 46, 47, 40, 41, 42, 43, 36, 37, 38]
        score = ai_decide_call(hand)
        assert score >= 2

    def test_weak_hand_skips(self):
        """全是小牌的弱牌应不叫"""
        hand = [0, 4, 8, 12, 16, 20, 1, 5, 9, 13, 17, 21, 2, 6, 10, 14, 18]
        score = ai_decide_call(hand)
        assert score == 0


class TestAIDecidePlay:
    def test_must_play_returns_cards(self):
        """必须出牌时应返回合法的牌"""
        hand = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 1, 5, 9, 13]
        cards = ai_decide_play(hand, last_play=None, must_play=True)
        assert cards is not None
        assert len(cards) > 0
        # 出的牌应是合法牌型
        assert detect_card_type(cards) is not None

    def test_can_pass_when_not_must_play(self):
        """有上家大牌时AI可选择不出"""
        hand = [0, 1]  # 只有两张3
        last = detect_card_type([48])  # 上家出了2
        result = ai_decide_play(hand, last_play=last, must_play=False)
        # 3压不过2，应返回 None (不出)
        assert result is None

    def test_play_smallest_single(self):
        """自由出牌时应优先出最小的"""
        hand = [0, 4, 8, 44, 48, 52]  # 3,4,5,A,2,小王
        cards = ai_decide_play(hand, last_play=None, must_play=True)
        assert cards is not None
        # 应该出最小的单张
        assert len(cards) == 1


class TestHandDecompose:
    def test_keeps_straight(self):
        # 3,4,5,6,7 (card IDs 0, 4, 8, 12, 16)
        hand = [0, 4, 8, 12, 16]
        plan = _decompose_hand(hand)
        # Should be 1 play (the straight)
        assert len(plan.plays) == 1
        assert plan.plays[0].card_type == CardType.STRAIGHT

    def test_keeps_double_straight(self):
        # 3,3, 4,4, 5,5 (card IDs 0,1, 4,5, 8,9)
        hand = [0, 1, 4, 5, 8, 9]
        plan = _decompose_hand(hand)
        assert len(plan.plays) == 1
        assert plan.plays[0].card_type == CardType.DOUBLE_STRAIGHT

    def test_pair_not_split(self):
        # 3,3 (0,1)
        hand = [0, 1]
        plan = _decompose_hand(hand)
        assert len(plan.plays) == 1
        assert plan.plays[0].card_type == CardType.PAIR


class TestLeadPlay:
    def test_leads_pair_not_single(self):
        # Hand only has pair of 3s (0, 1) and pair of 4s (4, 5)
        hand = [0, 1, 4, 5]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="test_ai", role="landlord", landlord_id="test_ai",
            teammate_id=None, landlord_remaining=4, teammate_remaining=0,
            last_play_from=None, is_last_play_teammate=False, is_last_play_landlord=False
        )
        lead = _pick_lead_play(plan, "landlord", ctx)
        # Should lead pair of 3s [0, 1] (or pair of 4s, but 3 is smaller)
        assert len(lead) == 2
        assert set(lead) == {0, 1}

    def test_landlord_up_leads_big(self):
        # Has small card 3 (0), and medium-large cards 10 (28) and J (32)
        # Ranks: 3 is rank 0, 10 is rank 7, J is rank 8
        hand = [0, 28, 32]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="farmer_up", role="landlord_up", landlord_id="landlord",
            teammate_id="farmer_down", landlord_remaining=10, teammate_remaining=10,
            last_play_from=None, is_last_play_teammate=False, is_last_play_landlord=False
        )
        lead = _pick_lead_play(plan, "landlord_up", ctx)
        # Normal stage: landlord has 10 cards. Landlord up should lead a big card (rank >= 7)
        # Big cards are 10 (28) and J (32). Should lead the smaller of these big cards: 10 (28)
        assert len(lead) == 1
        assert lead[0] == 28


class TestFollowPlay:
    def test_farmer_passes_teammate(self):
        # Teammate played a single J (rank 8, card ID 32)
        last_play = detect_card_type([32])
        # We are farmer_up (role landlord_up), teammate is farmer_down
        # We have single Q (36) and two other cards: 3 (0), 4 (4)
        # We can beat J with Q, but since it's teammate's non-small play and we can't win, we default to pass
        hand = [0, 4, 36]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="farmer_up", role="landlord_up", landlord_id="landlord",
            teammate_id="farmer_down", landlord_remaining=10, teammate_remaining=5,
            last_play_from="farmer_down", is_last_play_teammate=True, is_last_play_landlord=False
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord_up", ctx)
        # Should be None (pass)
        assert follow is None

    def test_farmer_beats_landlord(self):
        # Landlord played single 8 (20)
        last_play = detect_card_type([20])
        # We have single 10 (28). Landlord is opponent, we should beat it
        hand = [28]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="farmer_up", role="landlord_up", landlord_id="landlord",
            teammate_id="farmer_down", landlord_remaining=10, teammate_remaining=10,
            last_play_from="landlord", is_last_play_teammate=False, is_last_play_landlord=True
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord_up", ctx)
        assert follow is not None
        assert follow[0] == 28

    def test_no_split_to_beat(self):
        # Landlord played single 5 (8)
        last_play = detect_card_type([8])
        # We have a pair of 6s (12, 13) and a single J (32)
        # We should NOT split the pair of 6s to beat 5. We should play J (32).
        hand = [12, 13, 32]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="farmer_up", role="landlord_up", landlord_id="landlord",
            teammate_id="farmer_down", landlord_remaining=10, teammate_remaining=10,
            last_play_from="landlord", is_last_play_teammate=False, is_last_play_landlord=True
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord_up", ctx)
        # Should play J (32), not 6 (12 or 13)
        assert follow is not None
        assert follow[0] == 32

    def test_split_pair_to_beat_single(self):
        # Opponent played single 3 (2)
        last_play = detect_card_type([2])
        # We have Pair of 8s (20, 21) and no other singles.
        # We should split the Pair of 8s to play 8 (20 or 21).
        hand = [20, 21]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="landlord", role="landlord", landlord_id="landlord",
            teammate_id=None, landlord_remaining=2, teammate_remaining=0,
            last_play_from="farmer", is_last_play_teammate=False, is_last_play_landlord=False
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord", ctx)
        assert follow is not None
        assert len(follow) == 1
        assert follow[0] in (20, 21)

    def test_split_triple_two_to_beat_triple_one(self):
        # Opponent played Triple-one of 8 (three 8s (20, 21, 22) + single 4 (4))
        last_play = detect_card_type([20, 21, 22, 4])
        # We have Triple J (33, 34, 35) packaged as Triple-two with Pair 10 (28, 30)
        # and Triple A (44, 45, 46) packaged as Triple-one with Single 3 (0)
        # We should beat it with Triple J + Single 3.
        hand = [33, 34, 35, 28, 30, 44, 45, 46, 0]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="landlord", role="landlord", landlord_id="landlord",
            teammate_id=None, landlord_remaining=9, teammate_remaining=0,
            last_play_from="farmer", is_last_play_teammate=False, is_last_play_landlord=False
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord", ctx)
        assert follow is not None
        # Should be J, J, J + 3 (IDs 33, 34, 35 + 0)
        assert len(follow) == 4
        assert set(follow) == {33, 34, 35, 0}


class TestBombUsage:
    def test_bomb_when_landlord_low(self):
        # Landlord played A (44)
        last_play = detect_card_type([44])
        # We have a bomb of 4s (4, 5, 6, 7)
        # Landlord has 3 cards left. We should bomb!
        hand = [4, 5, 6, 7]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="farmer_up", role="landlord_up", landlord_id="landlord",
            teammate_id="farmer_down", landlord_remaining=3, teammate_remaining=10,
            last_play_from="landlord", is_last_play_teammate=False, is_last_play_landlord=True
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord_up", ctx)
        assert follow is not None
        assert len(follow) == 4

    def test_hold_bomb_early(self):
        # Landlord played A (44)
        last_play = detect_card_type([44])
        # We have a bomb of 4s (4, 5, 6, 7) and 10 other cards
        # Landlord has 15 cards left. We should hold our bomb!
        hand = [4, 5, 6, 7, 12, 13, 16, 20, 24, 28]
        plan = _decompose_hand(hand)
        ctx = AIContext(
            ai_id="farmer_up", role="landlord_up", landlord_id="landlord",
            teammate_id="farmer_down", landlord_remaining=15, teammate_remaining=10,
            last_play_from="landlord", is_last_play_teammate=False, is_last_play_landlord=True
        )
        follow = _pick_follow_play(hand, plan, last_play, "landlord_up", ctx)
        # Should hold the bomb and pass
        assert follow is None


def test_ai_decide_play_fallback():
    # Ensure that even if play_history or weights are missing, AI plays a valid card
    hand = [0, 1, 2, 3] # four 3s (bomb)
    res = ai_decide_play(hand, last_play=None, must_play=True)
    assert res is not None
    assert len(res) > 0


def test_ai_decide_play_douzero_route():
    from unittest.mock import patch
    import numpy as np
    import torch
    
    hand = [0, 1, 2, 3] # four 3s
    ctx = AIContext(
        ai_id="test_ai",
        role="landlord",
        landlord_id="test_ai",
        teammate_id=None,
        landlord_remaining=4,
        teammate_remaining=0,
        last_play_from=None,
        is_last_play_teammate=False,
        is_last_play_landlord=False,
        play_history=[{"player": "test_ai", "cards": [4]}],
        player_ids=["test_ai", "farmer1", "farmer2"]
    )
    
    with patch("app.domain.game.ai_strategy.douzero_manager") as mock_manager:
        mock_manager.is_available.return_value = True
        mock_manager.get_action_value.return_value = torch.tensor([[1.0], [2.0], [3.0], [4.0]])
        
        with patch("app.domain.game.ai_strategy.get_obs_for_douzero") as mock_get_obs:
            mock_get_obs.return_value = {
                'x_batch': np.zeros((4, 373)),
                'z_batch': np.zeros((4, 5, 162)),
                'legal_actions': [[3], [3, 3], [3, 3, 3], [3, 3, 3, 3]]
            }
            res = ai_decide_play(hand, last_play=None, must_play=True, ctx=ctx)
            assert res == [0, 1, 2, 3]


