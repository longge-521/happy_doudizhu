# backend/tests/test_card_type.py
import pytest
from app.domain.game.card_type import detect_card_type, can_beat, CardType


class TestDetectCardType:
    """牌型识别测试"""

    def test_single(self):
        """单张"""
        result = detect_card_type([0])  # 3♠
        assert result is not None
        assert result.card_type == CardType.SINGLE

    def test_pair(self):
        """对子"""
        result = detect_card_type([0, 1])  # 3♠3♥
        assert result is not None
        assert result.card_type == CardType.PAIR

    def test_triple(self):
        """三条"""
        result = detect_card_type([0, 1, 2])  # 3♠3♥3♣
        assert result is not None
        assert result.card_type == CardType.TRIPLE

    def test_triple_with_one(self):
        """三带一"""
        result = detect_card_type([0, 1, 2, 4])  # 333+4
        assert result is not None
        assert result.card_type == CardType.TRIPLE_ONE

    def test_triple_with_two(self):
        """三带二 (一对)"""
        result = detect_card_type([0, 1, 2, 4, 5])  # 333+44
        assert result is not None
        assert result.card_type == CardType.TRIPLE_TWO

    def test_straight(self):
        """顺子 (至少5张连续)"""
        result = detect_card_type([0, 4, 8, 12, 16])  # 3-4-5-6-7
        assert result is not None
        assert result.card_type == CardType.STRAIGHT

    def test_straight_invalid_with_two(self):
        """顺子不能包含2"""
        result = detect_card_type([36, 40, 44, 48, 0])  # K-A-2-?-3 不合法
        # 这不是合法顺子
        assert result is None or result.card_type != CardType.STRAIGHT

    def test_double_straight(self):
        """连对 (至少3对连续)"""
        result = detect_card_type([0, 1, 4, 5, 8, 9])  # 33-44-55
        assert result is not None
        assert result.card_type == CardType.DOUBLE_STRAIGHT

    def test_airplane(self):
        """飞机不带 (至少2组连续三条)"""
        result = detect_card_type([0, 1, 2, 4, 5, 6])  # 333-444
        assert result is not None
        assert result.card_type == CardType.AIRPLANE

    def test_airplane_with_singles(self):
        """飞机带单"""
        result = detect_card_type([0, 1, 2, 4, 5, 6, 8, 12])  # 333-444+5+6 (带两个单张)
        assert result is not None
        assert result.card_type == CardType.AIRPLANE_SINGLE

    def test_bomb(self):
        """炸弹"""
        result = detect_card_type([0, 1, 2, 3])  # 3333
        assert result is not None
        assert result.card_type == CardType.BOMB

    def test_rocket(self):
        """王炸"""
        result = detect_card_type([52, 53])  # 小王+大王
        assert result is not None
        assert result.card_type == CardType.ROCKET

    def test_four_two_single(self):
        """四带二单"""
        result = detect_card_type([0, 1, 2, 3, 4, 8])  # 3333+4+5
        assert result is not None
        assert result.card_type == CardType.FOUR_TWO_SINGLE

    def test_four_two_pair(self):
        """四带二对"""
        result = detect_card_type([0, 1, 2, 3, 4, 5, 8, 9])  # 3333+44+55
        assert result is not None
        assert result.card_type == CardType.FOUR_TWO_PAIR

    def test_invalid_cards(self):
        """非法牌型返回 None"""
        result = detect_card_type([0, 4, 12])  # 3+4+6 (三张不同且非顺子)
        assert result is None

    def test_empty_cards(self):
        """空牌返回 None"""
        result = detect_card_type([])
        assert result is None


class TestCanBeat:
    """牌型比较测试"""

    def test_bigger_single(self):
        """大单张压小单张"""
        small = detect_card_type([0])   # 3
        big = detect_card_type([44])    # A
        assert can_beat(big, small)

    def test_smaller_single_cannot_beat(self):
        """小单张不能压大单张"""
        small = detect_card_type([0])   # 3
        big = detect_card_type([44])    # A
        assert not can_beat(small, big)

    def test_bomb_beats_single(self):
        """炸弹压任意非炸弹牌型"""
        single = detect_card_type([44])        # A
        bomb = detect_card_type([0, 1, 2, 3])  # 3333
        assert can_beat(bomb, single)

    def test_rocket_beats_bomb(self):
        """王炸压炸弹"""
        bomb = detect_card_type([0, 1, 2, 3])  # 3333
        rocket = detect_card_type([52, 53])     # 王炸
        assert can_beat(rocket, bomb)

    def test_different_type_cannot_beat(self):
        """不同牌型（非炸弹）不能互压"""
        single = detect_card_type([0])
        pair = detect_card_type([4, 5])
        assert not can_beat(pair, single)

    def test_same_type_same_length_bigger_rank(self):
        """相同牌型相同长度，大的压小的"""
        small_straight = detect_card_type([0, 4, 8, 12, 16])   # 3-4-5-6-7
        big_straight = detect_card_type([4, 8, 12, 16, 20])     # 4-5-6-7-8
        assert can_beat(big_straight, small_straight)

    def test_different_length_straight_cannot_beat(self):
        """不同长度的顺子不能互压"""
        short = detect_card_type([0, 4, 8, 12, 16])          # 3-4-5-6-7 (5张)
        long = detect_card_type([0, 4, 8, 12, 16, 20])       # 3-4-5-6-7-8 (6张)
        assert not can_beat(long, short)
