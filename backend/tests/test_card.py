# backend/tests/test_card.py
import pytest
from app.domain.game.card import Card, FULL_DECK, sort_cards, shuffle_and_deal


class TestCard:
    """扑克牌编码与属性测试"""

    def test_card_from_id_three_of_spades(self):
        """编号0应为黑桃3"""
        card = Card.from_id(0)
        assert card.rank == 0  # 3
        assert card.suit == 0  # ♠
        assert card.rank_name == "3"
        assert card.suit_name == "♠"

    def test_card_from_id_ace_of_hearts(self):
        """编号45应为红桃A"""
        card = Card.from_id(45)
        assert card.rank == 11  # A
        assert card.suit == 1   # ♥
        assert card.rank_name == "A"

    def test_card_from_id_two_of_diamonds(self):
        """编号51应为方块2"""
        card = Card.from_id(51)
        assert card.rank == 12  # 2
        assert card.suit == 3   # ♦
        assert card.rank_name == "2"

    def test_card_from_id_black_joker(self):
        """编号52应为小王"""
        card = Card.from_id(52)
        assert card.rank_name == "小王"
        assert card.suit_name == ""

    def test_card_from_id_red_joker(self):
        """编号53应为大王"""
        card = Card.from_id(53)
        assert card.rank_name == "大王"
        assert card.suit_name == ""

    def test_power_ordering(self):
        """牌力排序：3 < 4 < ... < K < A < 2 < 小王 < 大王"""
        three = Card.from_id(0)    # 3
        ace = Card.from_id(44)     # A
        two = Card.from_id(48)     # 2
        bj = Card.from_id(52)      # 小王
        rj = Card.from_id(53)      # 大王
        assert three.power < ace.power < two.power < bj.power < rj.power

    def test_full_deck_size(self):
        """一副牌应有54张"""
        assert len(FULL_DECK) == 54

    def test_sort_cards(self):
        """排序后应按牌力从小到大"""
        cards = [53, 0, 48, 44]  # 大王, 3♠, 2♠, A♠
        sorted_ids = sort_cards(cards)
        powers = [Card.from_id(c).power for c in sorted_ids]
        assert powers == sorted(powers)

    def test_shuffle_and_deal(self):
        """发牌: 每人17张, 底牌3张, 总计54张不重复"""
        hand1, hand2, hand3, bottom = shuffle_and_deal()
        assert len(hand1) == 17
        assert len(hand2) == 17
        assert len(hand3) == 17
        assert len(bottom) == 3
        all_cards = hand1 + hand2 + hand3 + bottom
        assert len(set(all_cards)) == 54

    def test_card_invalid_id(self):
        """无效编号应抛出 ValueError"""
        with pytest.raises(ValueError):
            Card.from_id(54)
        with pytest.raises(ValueError):
            Card.from_id(-1)
