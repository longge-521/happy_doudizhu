# backend/app/domain/game/card.py
"""扑克牌领域模型：编码、排序、发牌"""
import random
from dataclasses import dataclass
from typing import Tuple, List

# 点数名称映射 (rank index → display name)
RANK_NAMES = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
# 花色名称映射 (suit index → display name)
SUIT_NAMES = ["♠", "♥", "♣", "♦"]

# 完整一副牌: 0~53
FULL_DECK: List[int] = list(range(54))


@dataclass(frozen=True)
class Card:
    """
    扑克牌值对象。
    编码规则：
      - 0~51: 普通牌，rank = card_id // 4, suit = card_id % 4
      - 52: 小王
      - 53: 大王
    """
    card_id: int
    rank: int     # 0~12 对应 3~2, 13=小王, 14=大王
    suit: int     # 0~3 对应 ♠♥♣♦, -1=王

    @classmethod
    def from_id(cls, card_id: int) -> "Card":
        if card_id < 0 or card_id > 53:
            raise ValueError(f"无效的牌编号: {card_id}，合法范围 0~53")
        if card_id == 52:
            return cls(card_id=52, rank=13, suit=-1)
        if card_id == 53:
            return cls(card_id=53, rank=14, suit=-1)
        return cls(card_id=card_id, rank=card_id // 4, suit=card_id % 4)

    @property
    def rank_name(self) -> str:
        if self.rank == 13:
            return "小王"
        if self.rank == 14:
            return "大王"
        return RANK_NAMES[self.rank]

    @property
    def suit_name(self) -> str:
        if self.suit == -1:
            return ""
        return SUIT_NAMES[self.suit]

    @property
    def power(self) -> int:
        """牌力值，数值越大牌越大。用于排序和比较。"""
        return self.rank

    def __str__(self) -> str:
        return f"{self.suit_name}{self.rank_name}"


def sort_cards(card_ids: List[int]) -> List[int]:
    """按牌力从小到大排序"""
    return sorted(card_ids, key=lambda cid: Card.from_id(cid).power)


def shuffle_and_deal() -> Tuple[List[int], List[int], List[int], List[int]]:
    """洗牌并发牌：返回 (手牌1, 手牌2, 手牌3, 底牌)"""
    deck = FULL_DECK.copy()
    random.shuffle(deck)
    hand1 = sort_cards(deck[0:17])
    hand2 = sort_cards(deck[17:34])
    hand3 = sort_cards(deck[34:51])
    bottom = sort_cards(deck[51:54])
    return hand1, hand2, hand3, bottom
