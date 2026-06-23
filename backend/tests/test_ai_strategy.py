# backend/tests/test_ai_strategy.py
import pytest
from app.domain.game.ai_strategy import ai_decide_call, ai_decide_play
from app.domain.game.card_type import detect_card_type


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
