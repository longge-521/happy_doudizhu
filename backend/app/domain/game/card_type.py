# backend/app/domain/game/card_type.py
"""牌型检测与比较引擎"""
from collections import Counter
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
from app.domain.game.card import Card


class CardType(Enum):
    """合法牌型枚举"""
    SINGLE = "单张"
    PAIR = "对子"
    TRIPLE = "三条"
    TRIPLE_ONE = "三带一"
    TRIPLE_TWO = "三带二"
    STRAIGHT = "顺子"
    DOUBLE_STRAIGHT = "连对"
    AIRPLANE = "飞机"
    AIRPLANE_SINGLE = "飞机带单"
    AIRPLANE_PAIR = "飞机带对"
    BOMB = "炸弹"
    ROCKET = "王炸"
    FOUR_TWO_SINGLE = "四带二单"
    FOUR_TWO_PAIR = "四带二对"


@dataclass
class CardPlay:
    """一次出牌的完整描述"""
    card_type: CardType
    main_rank: int       # 主牌的 rank (用于比较大小)
    length: int          # 主牌序列长度 (顺子5张 length=5)
    cards: List[int]     # 原始牌编号


def _get_rank_counts(card_ids: List[int]) -> Counter:
    """统计每个 rank 出现的次数"""
    ranks = [Card.from_id(cid).rank for cid in card_ids]
    return Counter(ranks)


def _find_consecutive_ranks(ranks: List[int], min_length: int) -> Optional[List[int]]:
    """
    在给定的 rank 列表中找到连续序列。
    rank 必须 < 12 (即不包含2) 且 < 13 (不包含王)。
    返回排序后的连续 rank 列表，或 None。
    """
    valid = sorted([r for r in ranks if r < 12])  # 排除 2(rank=12) 和 王
    if len(valid) < min_length:
        return None
    # 检查是否连续
    for i in range(1, len(valid)):
        if valid[i] != valid[i - 1] + 1:
            return None
    return valid


def detect_card_type(card_ids: List[int]) -> Optional[CardPlay]:
    """
    检测一组牌的牌型。
    返回 CardPlay 描述，非法牌型返回 None。
    """
    if not card_ids:
        return None

    n = len(card_ids)
    rank_counts = _get_rank_counts(card_ids)

    # 王炸: 大小王
    if n == 2 and set(card_ids) == {52, 53}:
        return CardPlay(CardType.ROCKET, main_rank=14, length=1, cards=card_ids)

    # 按出现次数分组
    count_groups = {}  # count -> [rank, ...]
    for rank, count in rank_counts.items():
        count_groups.setdefault(count, []).append(rank)
    for k in count_groups:
        count_groups[k].sort()

    # 单张
    if n == 1:
        rank = Card.from_id(card_ids[0]).rank
        return CardPlay(CardType.SINGLE, main_rank=rank, length=1, cards=card_ids)

    # 对子
    if n == 2 and len(rank_counts) == 1:
        rank = list(rank_counts.keys())[0]
        return CardPlay(CardType.PAIR, main_rank=rank, length=1, cards=card_ids)

    # 炸弹: 4张相同
    if n == 4 and len(rank_counts) == 1:
        rank = list(rank_counts.keys())[0]
        return CardPlay(CardType.BOMB, main_rank=rank, length=1, cards=card_ids)

    # 三条
    if n == 3 and len(rank_counts) == 1:
        rank = list(rank_counts.keys())[0]
        return CardPlay(CardType.TRIPLE, main_rank=rank, length=1, cards=card_ids)

    # 三带一
    if n == 4 and 3 in count_groups and len(count_groups[3]) == 1:
        main_rank = count_groups[3][0]
        return CardPlay(CardType.TRIPLE_ONE, main_rank=main_rank, length=1, cards=card_ids)

    # 三带二 (副牌必须是对子)
    if n == 5 and 3 in count_groups and 2 in count_groups:
        if len(count_groups[3]) == 1 and len(count_groups[2]) == 1:
            main_rank = count_groups[3][0]
            return CardPlay(CardType.TRIPLE_TWO, main_rank=main_rank, length=1, cards=card_ids)

    # 顺子: ≥5张连续单张 (不含2和王)
    if n >= 5 and all(c == 1 for c in rank_counts.values()):
        seq = _find_consecutive_ranks(list(rank_counts.keys()), n)
        if seq and len(seq) == n:
            return CardPlay(CardType.STRAIGHT, main_rank=seq[0], length=n, cards=card_ids)

    # 连对: ≥3对连续 (不含2和王)
    if n >= 6 and n % 2 == 0 and all(c == 2 for c in rank_counts.values()):
        num_pairs = n // 2
        seq = _find_consecutive_ranks(list(rank_counts.keys()), num_pairs)
        if seq and len(seq) == num_pairs:
            return CardPlay(CardType.DOUBLE_STRAIGHT, main_rank=seq[0], length=num_pairs, cards=card_ids)

    # 飞机相关: 先找连续的三条
    triples = sorted(count_groups.get(3, []))
    # 也考虑4张中拆出3张的情况
    fours = sorted(count_groups.get(4, []))

    # 合并三条候选
    all_triples = sorted(list(set(triples + fours)))

    # 纯飞机 (≥2组连续三条)
    if all_triples and len(all_triples) >= 2:
        # 我们可能需要在所有三条候选中寻找连续的序列
        # 考虑到三带单或三带对，可能存在三条个数不等于实际飞机长度
        # 比如 333 444 555 带 6 7 8，我们有 3 组连续三条，总张数 12 张。
        # 这里寻找刚好能组合成飞机的最长连续序列
        # 例如对于包含 triples 的列表，我们探测连续子串
        # 一种简化且标准做法是：飞机的长度由总张数 n 决定。
        # 纯飞机：n % 3 == 0，长度为 n // 3
        # 飞机带单：n % 4 == 0，长度为 n // 4
        # 飞机带双：n % 5 == 0，长度为 n // 5
        
        # 尝试匹配不同的飞机规格
        for plane_type, divisor in [
            (CardType.AIRPLANE, 3),
            (CardType.AIRPLANE_SINGLE, 4),
            (CardType.AIRPLANE_PAIR, 5)
        ]:
            if n % divisor == 0:
                expected_len = n // divisor
                if expected_len >= 2:
                    # 在 all_triples 中寻找长度为 expected_len 的连续子串
                    # 遍历可能的起点
                    for i in range(len(all_triples) - expected_len + 1):
                        sub = all_triples[i:i+expected_len]
                        seq = _find_consecutive_ranks(sub, expected_len)
                        if seq and len(seq) == expected_len:
                            # 找到了符合要求的连续三条
                            # 验证副牌是否符合规范
                            if plane_type == CardType.AIRPLANE:
                                return CardPlay(CardType.AIRPLANE, main_rank=seq[0], length=expected_len, cards=card_ids)
                            elif plane_type == CardType.AIRPLANE_SINGLE:
                                return CardPlay(CardType.AIRPLANE_SINGLE, main_rank=seq[0], length=expected_len, cards=card_ids)
                            elif plane_type == CardType.AIRPLANE_PAIR:
                                # 飞机带对子，副牌必须全是对子
                                side_ranks = [r for r, c in rank_counts.items() if r not in seq]
                                side_counts = [rank_counts[r] for r in side_ranks]
                                # 注意：如果副牌里有4张相同的，也可以看作是两对
                                if all(c in (2, 4) for c in side_counts) and sum(c // 2 for c in side_counts) == expected_len:
                                    return CardPlay(CardType.AIRPLANE_PAIR, main_rank=seq[0], length=expected_len, cards=card_ids)

    # 四带二单
    if n == 6 and 4 in count_groups and len(count_groups[4]) == 1:
        main_rank = count_groups[4][0]
        return CardPlay(CardType.FOUR_TWO_SINGLE, main_rank=main_rank, length=1, cards=card_ids)

    # 四带二对
    if n == 8 and 4 in count_groups and len(count_groups[4]) == 1:
        main_rank = count_groups[4][0]
        side_ranks = [r for r in rank_counts if r != main_rank]
        if all(rank_counts[r] in (2, 4) for r in side_ranks) and sum(rank_counts[r] // 2 for r in side_ranks) == 2:
            return CardPlay(CardType.FOUR_TWO_PAIR, main_rank=main_rank, length=1, cards=card_ids)

    return None


def can_beat(current_play: CardPlay, last_play: CardPlay) -> bool:
    """
    判断 current_play 是否能压过 last_play。
    规则：
      1. 王炸压一切
      2. 炸弹压非炸弹，大炸弹压小炸弹
      3. 相同牌型 + 相同长度 + 更大的 main_rank
    """
    # 王炸压一切
    if current_play.card_type == CardType.ROCKET:
        return True
    if last_play.card_type == CardType.ROCKET:
        return False

    # 炸弹 vs 非炸弹
    if current_play.card_type == CardType.BOMB and last_play.card_type != CardType.BOMB:
        return True
    if current_play.card_type != CardType.BOMB and last_play.card_type == CardType.BOMB:
        return False

    # 相同牌型比较
    if current_play.card_type != last_play.card_type:
        return False
    if current_play.length != last_play.length:
        return False
    return current_play.main_rank > last_play.main_rank
