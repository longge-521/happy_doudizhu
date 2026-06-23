# backend/app/domain/game/ai_strategy.py
"""AI 机器人出牌策略 (MVP版本: 简单规则策略)"""
from typing import Optional, List
from app.domain.game.card import Card, sort_cards
from app.domain.game.card_type import detect_card_type, can_beat, CardPlay, CardType
from collections import Counter


def ai_decide_call(hand: List[int]) -> int:
    """
    根据手牌强度决定叫分。
    评分规则：大王+10, 小王+8, 2+3, A+2, 炸弹+8
    总分 >= 18 叫3分, >= 12 叫2分, >= 8 叫1分, 否则不叫
    """
    score = 0
    rank_counts = Counter(Card.from_id(c).rank for c in hand)

    for cid in hand:
        card = Card.from_id(cid)
        if card.rank == 14:   # 大王
            score += 10
        elif card.rank == 13: # 小王
            score += 8
        elif card.rank == 12: # 2
            score += 3
        elif card.rank == 11: # A
            score += 2

    # 炸弹加分
    for rank, count in rank_counts.items():
        if count == 4:
            score += 8

    if score >= 18:
        return 3
    elif score >= 12:
        return 2
    elif score >= 8:
        return 1
    return 0


def _find_all_plays(hand: List[int]) -> List[CardPlay]:
    """枚举手牌中所有可出的牌型组合 (仅单张、对子、三条及其变体、炸弹)"""
    plays = []
    rank_counts = Counter(Card.from_id(c).rank for c in hand)
    rank_to_cards = {}
    for cid in hand:
        r = Card.from_id(cid).rank
        rank_to_cards.setdefault(r, []).append(cid)

    for rank, cards_of_rank in rank_to_cards.items():
        count = len(cards_of_rank)
        # 单张
        plays.append(detect_card_type([cards_of_rank[0]]))
        # 对子
        if count >= 2:
            plays.append(detect_card_type(cards_of_rank[:2]))
        # 三条
        if count >= 3:
            plays.append(detect_card_type(cards_of_rank[:3]))
        # 炸弹
        if count == 4:
            plays.append(detect_card_type(cards_of_rank[:4]))

    # 王炸
    if 52 in hand and 53 in hand:
        plays.append(detect_card_type([52, 53]))

    return [p for p in plays if p is not None]


def ai_decide_play(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool
) -> Optional[List[int]]:
    """
    AI 决定出什么牌。
    - must_play=True 时必须出牌（新一轮首位）
    - 返回 None 表示不出
    """
    if not hand:
        return None

    sorted_hand = sort_cards(hand)
    all_plays = _find_all_plays(sorted_hand)

    if must_play or last_play is None:
        # 自由出牌：出最小的单张
        all_plays.sort(key=lambda p: (p.main_rank, len(p.cards)))
        if all_plays:
            # 优先选择单张牌
            singles = [p for p in all_plays if p.card_type == CardType.SINGLE]
            if singles:
                singles.sort(key=lambda p: p.main_rank)
                return list(singles[0].cards)
            return list(all_plays[0].cards)
        return [sorted_hand[0]]

    # 需要压过上家
    valid_plays = [p for p in all_plays if can_beat(p, last_play)]
    if not valid_plays:
        return None  # 压不过就不出

    # 选最小的能压过的牌 (非炸弹优先)
    non_bombs = [p for p in valid_plays if p.card_type not in (CardType.BOMB, CardType.ROCKET)]
    if non_bombs:
        non_bombs.sort(key=lambda p: p.main_rank)
        return list(non_bombs[0].cards)

    # 只剩炸弹了，如果手牌不多就炸
    if len(hand) <= 5:
        valid_plays.sort(key=lambda p: p.main_rank)
        return list(valid_plays[0].cards)

    return None  # 手牌多时保留炸弹
