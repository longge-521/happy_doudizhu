# backend/app/domain/game/ai_strategy.py
"""AI 机器人出牌策略 (基于规则引擎与手牌最优拆解的智能算法)"""
import logging
from typing import Optional, List, Dict
from app.domain.game.card import Card, sort_cards
from app.domain.game.card_type import detect_card_type, can_beat, CardPlay, CardType
from collections import Counter
from dataclasses import dataclass, field
from app.domain.game.douzero_model import douzero_manager
from app.domain.game.douzero_adapter import card_id_to_douzero, douzero_to_card_ids, get_obs_for_douzero

logger = logging.getLogger(__name__)


@dataclass
class AIContext:
    ai_id: str                  # 当前 AI 的玩家 ID
    role: str                   # 'landlord' | 'landlord_up' | 'landlord_down'
    landlord_id: str            # 地主玩家 ID
    teammate_id: Optional[str]  # 队友 ID（地主为 None）
    landlord_remaining: int     # 地主剩余手牌数
    teammate_remaining: int     # 队友剩余手牌数（地主为 0）
    last_play_from: Optional[str]  # 上一次出牌的玩家 ID
    is_last_play_teammate: bool    # 上一次出牌是否来自队友
    is_last_play_landlord: bool    # 上一次出牌是否来自地主
    play_history: Optional[List[dict]] = None
    player_ids: Optional[List[str]] = None
    play_mode: str = "classic"   # 玩法模式
    other_players_min_remaining: int = 18  # 其他对手最小剩余手牌数
    player_remaining: Dict[str, int] = field(default_factory=dict)
    current_trick_score: int = 0  # 桌面累计分值

    def __post_init__(self):
        if self.play_history is None:
            self.play_history = []
        if self.player_ids is None:
            self.player_ids = []


@dataclass
class HandPlan:
    plays: List[CardPlay]     # 拆解出的常规牌型列表
    hand_count: int           # 总手数（不含炸弹）
    bombs: List[CardPlay]     # 保留的炸弹/王炸


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


def build_ai_context(room, ai_id: str) -> AIContext:
    """从 GameRoom 中提取 AI 上下文，判定角色（地主/顶牌位/跑牌位）"""
    play_mode = getattr(room, "play_mode", "classic")
    player_ids = [p.id for p in room.players]

    if play_mode == "fifty_k":
        landlord_id = ai_id
        role = "landlord"
        teammate_id = None
        other_hands_len = [len(room.hands.get(pid, [])) for pid in player_ids if pid != ai_id]
        other_players_min_remaining = min(other_hands_len) if other_hands_len else 18
    else:
        landlord_id = room.landlord
        other_players_min_remaining = 18
        # 判定角色
        if ai_id == landlord_id:
            role = "landlord"
        else:
            l_idx = player_ids.index(landlord_id)
            ai_idx = player_ids.index(ai_id)
            if ai_idx == (l_idx + 1) % 3:
                role = "landlord_down"  # 下家 (跑牌位)
            else:
                role = "landlord_up"    # 上家 (顶牌位)

        # 队友 ID
        teammate_id = None
        if role != "landlord":
            teammate_id = [pid for pid in player_ids if pid != landlord_id and pid != ai_id][0]

    # 剩余牌数
    landlord_remaining = len(room.hands.get(landlord_id, []))
    teammate_remaining = len(room.hands.get(teammate_id, [])) if teammate_id else 0

    # 提取 play_history、玩家顺序和公开的剩余手牌数
    play_history = getattr(room, "play_history", [])
    player_remaining = {
        player_id: len(room.hands.get(player_id, []))
        for player_id in player_ids
    }

    # 上次出牌信息
    last_play_from = room.last_play.player
    is_last_play_teammate = False
    is_last_play_landlord = False
    if last_play_from:
        if last_play_from == landlord_id:
            is_last_play_landlord = True
        elif teammate_id and last_play_from == teammate_id:
            is_last_play_teammate = True

    # 计算桌面 Trick 分数
    current_trick_score = 0
    if play_mode == "fifty_k" and hasattr(room, "current_trick_cards"):
        def get_score(card_id: int) -> int:
            if card_id < 52:
                rank = card_id // 4
                if rank == 2:  # '5'
                    return 5
                elif rank == 7:  # '10'
                    return 10
                elif rank == 10:  # 'K'
                    return 10
            return 0
        current_trick_score = sum(get_score(cid) for cid in room.current_trick_cards)

    return AIContext(
        ai_id=ai_id,
        role=role,
        landlord_id=landlord_id,
        teammate_id=teammate_id,
        landlord_remaining=landlord_remaining,
        teammate_remaining=teammate_remaining,
        last_play_from=last_play_from,
        is_last_play_teammate=is_last_play_teammate,
        is_last_play_landlord=is_last_play_landlord,
        play_history=play_history,
        player_ids=player_ids,
        play_mode=play_mode,
        other_players_min_remaining=other_players_min_remaining,
        player_remaining=player_remaining,
        current_trick_score=current_trick_score,
    )


def _decompose_hand(hand: List[int], play_mode: str = "classic") -> HandPlan:
    """DFS 手牌最优拆解：提取炸弹 -> 递归寻找连对/顺子 -> 组合飞机/三带配翼 -> 返回手数最少方案"""
    bombs = []
    remaining_hand = list(hand)

    # 1. 提取王炸
    if 52 in remaining_hand and 53 in remaining_hand:
        rocket_play = detect_card_type([52, 53], play_mode=play_mode)
        if rocket_play:
            bombs.append(rocket_play)
            remaining_hand.remove(52)
            remaining_hand.remove(53)

    # 510K 炸弹提取 (同花真510K优先，杂花假510K次之)
    # 查找真 510K (同花色)
    for suit in range(4):
        c5 = 2 * 4 + suit
        c10 = 7 * 4 + suit
        cK = 10 * 4 + suit
        if c5 in remaining_hand and c10 in remaining_hand and cK in remaining_hand:
            fifty_k_cards = [c5, c10, cK]
            play_obj = detect_card_type(fifty_k_cards, play_mode=play_mode)
            if play_obj and play_obj.card_type == CardType.FIFTY_K_TRUE:
                bombs.append(play_obj)
                for cid in fifty_k_cards:
                    remaining_hand.remove(cid)

    # 查找假 510K (杂花色)
    cards_5 = [c for c in remaining_hand if Card.from_id(c).rank == 2]
    cards_10 = [c for c in remaining_hand if Card.from_id(c).rank == 7]
    cards_K = [c for c in remaining_hand if Card.from_id(c).rank == 10]
    while cards_5 and cards_10 and cards_K:
        c5 = cards_5.pop(0)
        c10 = cards_10.pop(0)
        cK = cards_K.pop(0)
        fifty_k_cards = [c5, c10, cK]
        play_obj = detect_card_type(fifty_k_cards, play_mode=play_mode)
        if play_obj and play_obj.card_type == CardType.FIFTY_K_FALSE:
            bombs.append(play_obj)
            for cid in fifty_k_cards:
                remaining_hand.remove(cid)
        else:
            cards_5.insert(0, c5)
            cards_10.insert(0, c10)
            cards_K.insert(0, cK)
            break

    # 2. 提取普通炸弹
    rank_counts = Counter(Card.from_id(c).rank for c in remaining_hand)
    bomb_ranks = [r for r, count in rank_counts.items() if count == 4]
    for r in bomb_ranks:
        bomb_cards = [c for c in remaining_hand if Card.from_id(c).rank == r]
        bomb_play = detect_card_type(bomb_cards, play_mode=play_mode)
        if bomb_play:
            bombs.append(bomb_play)
            for c in bomb_cards:
                remaining_hand.remove(c)

    # 重新整理剩余牌的 rank counts
    rank_counts = Counter(Card.from_id(c).rank for c in remaining_hand)
    counts = [0] * 15
    for r, count in rank_counts.items():
        counts[r] = count

    rank_to_cards = {}
    for c in remaining_hand:
        r = Card.from_id(c).rank
        rank_to_cards.setdefault(r, []).append(c)
    for r in rank_to_cards:
        rank_to_cards[r].sort()

    best_plays_ranks = None
    best_hands_count = 9999

    def dfs(current_counts: List[int], current_plays: List[dict]):
        nonlocal best_plays_ranks, best_hands_count

        # 任何时候都允许直接将剩余牌做琐碎拆解，作为一个竞争分支参与手数评估
        temp_plays = list(current_plays)
        triples_list = []
        pairs_list = []
        singles_list = []
        for r in range(15):
            cnt = current_counts[r]
            if cnt == 3:
                triples_list.append(r)
            elif cnt == 2:
                pairs_list.append(r)
            elif cnt == 1:
                singles_list.append(r)

        # 模拟三带二/三带一的翅膀合并，计算真实的折算手数
        usable_pairs = len(pairs_list)
        usable_singles = len(singles_list)
        actual_triples = len(triples_list)

        # 优先三条配对子 (三带二)
        bring_pair = min(actual_triples, usable_pairs)
        actual_triples -= bring_pair
        usable_pairs -= bring_pair

        # 其次三条配单张 (三带一)
        bring_single = min(actual_triples, usable_singles)
        actual_triples -= bring_single
        usable_singles -= bring_single

        # 拆散三条的惩罚分：如果某个 rank 原始有 3 张牌，但在当前规划中却没有作为三条保留，惩罚 1.5 手
        penalty = 0.0
        for r in range(15):
            if counts[r] == 3 and r not in triples_list:
                penalty += 1.5

        # 折算后的实际总手数
        total_hands = len(temp_plays) + len(triples_list) + len(pairs_list) + len(singles_list) - bring_pair - bring_single + penalty

        if total_hands < best_hands_count:
            best_hands_count = total_hands
            flat_plays = list(temp_plays)
            for r in triples_list:
                flat_plays.append({"type": "triple", "rank": r})
            for r in pairs_list:
                flat_plays.append({"type": "pair", "rank": r})
            for r in singles_list:
                flat_plays.append({"type": "single", "rank": r})
            best_plays_ranks = flat_plays

        if len(current_plays) >= best_hands_count:
            return

        possible_straights = []
        possible_double_straights = []

        # 连对检测
        for start in range(10):
            for length in range(3, 13 - start):
                if all(current_counts[r] >= 2 for r in range(start, start + length)):
                    possible_double_straights.append((start, length))

        # 顺子检测
        for start in range(8):
            for length in range(5, 13 - start):
                if all(current_counts[r] >= 1 for r in range(start, start + length)):
                    possible_straights.append((start, length))

        # 优先尝试提取连对
        for start, length in possible_double_straights:
            next_counts = list(current_counts)
            for r in range(start, start + length):
                next_counts[r] -= 2
            dfs(next_counts, current_plays + [{"type": "double_straight", "rank": start, "length": length}])

        # 尝试提取顺子
        for start, length in possible_straights:
            next_counts = list(current_counts)
            for r in range(start, start + length):
                next_counts[r] -= 1
            dfs(next_counts, current_plays + [{"type": "straight", "rank": start, "length": length}])

    dfs(counts, [])

    # 将最佳拆解方案映射回 CardPlay
    temp_rank_to_cards = {r: list(cards) for r, cards in rank_to_cards.items()}
    base_plays = []
    if best_plays_ranks is not None:
        for p in best_plays_ranks:
            ptype = p["type"]
            r = p["rank"]
            if ptype == "single":
                cards = [temp_rank_to_cards[r].pop(0)]
                base_plays.append(CardPlay(CardType.SINGLE, r, 1, cards))
            elif ptype == "pair":
                cards = [temp_rank_to_cards[r].pop(0) for _ in range(2)]
                base_plays.append(CardPlay(CardType.PAIR, r, 1, cards))
            elif ptype == "triple":
                cards = [temp_rank_to_cards[r].pop(0) for _ in range(3)]
                base_plays.append(CardPlay(CardType.TRIPLE, r, 1, cards))
            elif ptype == "straight":
                length = p["length"]
                cards = []
                for r_idx in range(r, r + length):
                    cards.append(temp_rank_to_cards[r_idx].pop(0))
                base_plays.append(CardPlay(CardType.STRAIGHT, r, length, cards))
            elif ptype == "double_straight":
                length = p["length"]
                cards = []
                for r_idx in range(r, r + length):
                    cards.append(temp_rank_to_cards[r_idx].pop(0))
                    cards.append(temp_rank_to_cards[r_idx].pop(0))
                base_plays.append(CardPlay(CardType.DOUBLE_STRAIGHT, r, length, cards))

    # 飞机合并逻辑：将连续的三条合并为纯飞机 (不含 2 和王)
    triples = [p for p in base_plays if p.card_type == CardType.TRIPLE]
    other_plays = [p for p in base_plays if p.card_type != CardType.TRIPLE]
    triples.sort(key=lambda p: p.main_rank)

    planes = []
    i = 0
    while i < len(triples):
        seq = [triples[i]]
        j = i + 1
        while j < len(triples) and triples[j].main_rank == seq[-1].main_rank + 1 and triples[j].main_rank < 12:
            seq.append(triples[j])
            j += 1
        if len(seq) >= 2:
            plane_cards = []
            for t in seq:
                plane_cards.extend(t.cards)
            planes.append(CardPlay(CardType.AIRPLANE, seq[0].main_rank, len(seq), plane_cards))
            i = j
        else:
            other_plays.append(triples[i])
            i += 1

    # 翅膀搭配逻辑：将单张/对子作为翅膀搭配给飞机和三条
    singles = [p for p in other_plays if p.card_type == CardType.SINGLE]
    pairs = [p for p in other_plays if p.card_type == CardType.PAIR]
    triples = [p for p in other_plays if p.card_type == CardType.TRIPLE]
    other_combos = [p for p in other_plays if p.card_type not in (CardType.SINGLE, CardType.PAIR, CardType.TRIPLE)]

    # 从小到大排序单张和对子，优先消耗小翅膀
    singles.sort(key=lambda p: p.main_rank)
    pairs.sort(key=lambda p: p.main_rank)
    planes.sort(key=lambda p: p.main_rank)
    triples.sort(key=lambda p: p.main_rank)

    final_plays = []

    # 飞机带翅膀
    for plane in planes:
        L = plane.length
        if len(pairs) >= L:
            wing_pairs = pairs[:L]
            pairs = pairs[L:]
            wing_cards = []
            for wp in wing_pairs:
                wing_cards.extend(wp.cards)
            combined = plane.cards + wing_cards
            play = detect_card_type(combined)
            final_plays.append(play if play else plane)
        elif len(singles) >= L:
            wing_singles = singles[:L]
            singles = singles[L:]
            wing_cards = []
            for ws in wing_singles:
                wing_cards.extend(ws.cards)
            combined = plane.cards + wing_cards
            play = detect_card_type(combined)
            final_plays.append(play if play else plane)
        else:
            final_plays.append(plane)

    # 三条带翅膀
    for triple in triples:
        if len(pairs) >= 1:
            wp = pairs.pop(0)
            combined = triple.cards + wp.cards
            play = detect_card_type(combined)
            final_plays.append(play if play else triple)
        elif len(singles) >= 1:
            ws = singles.pop(0)
            combined = triple.cards + ws.cards
            play = detect_card_type(combined)
            final_plays.append(play if play else triple)
        else:
            final_plays.append(triple)

    final_plays.extend(singles)
    final_plays.extend(pairs)
    final_plays.extend(other_combos)

    return HandPlan(plays=final_plays, hand_count=len(final_plays), bombs=bombs)


def _get_lead_priority(play: CardPlay) -> int:
    """首发出牌的牌型优先级（数值越小优先级越高）"""
    type_order = [
        CardType.SINGLE,
        CardType.PAIR,
        CardType.TRIPLE_ONE,
        CardType.TRIPLE_TWO,
        CardType.TRIPLE,
        CardType.STRAIGHT,
        CardType.DOUBLE_STRAIGHT,
        CardType.AIRPLANE_SINGLE,
        CardType.AIRPLANE_PAIR,
        CardType.AIRPLANE,
    ]
    try:
        return type_order.index(play.card_type)
    except ValueError:
        return 99


def _get_lead_card_weight(p: CardPlay) -> float:
    """评估主动出牌的权重值，值越小越优先出，惩罚首出 2/王"""
    rank = p.main_rank
    priority_offset = _get_lead_priority(p) * 0.1

    # 检查出牌组合中是否含有 2、小王、大王 (rank >= 12)
    has_big_card = False
    for cid in p.cards:
        c_rank = Card.from_id(cid).rank
        if c_rank >= 12:
            has_big_card = True
            break

    if has_big_card:
        # 首出 2/小王/大王 极度不划算，加上 50 惩罚分
        return 50.0 + rank + priority_offset
    return float(rank) + priority_offset


def _pick_lead_play(plan: HandPlan, role: str, ctx: AIContext) -> List[int]:
    """主动出牌决策"""
    if not plan.plays:
        if plan.bombs:
            # 仅剩炸弹，出最小的炸弹
            sorted_bombs = sorted(plan.bombs, key=lambda b: b.main_rank)
            return sorted_bombs[0].cards
        return []

    # 1. 终局顶防：如果有对手剩余手牌 <= 2 张且拉响警报，且我们无法一次性将整手牌打完 (手数 > 1)，我们首出常规牌必须打出能够防住对手的牌！
    is_opponent_danger = getattr(ctx, "other_players_min_remaining", 18) <= 2
    total_hands = len(plan.plays) + len(plan.bombs)
    if is_opponent_danger and total_hands > 1:
        min_rem = getattr(ctx, "other_players_min_remaining", 18)
        if min_rem == 1:
            # 对手只剩 1 张单牌，说明他要不起任何非单张 (对子、三条、顺子等)
            # 所以如果我们有非单张牌，优先出这些绝对安全的非单张牌型跑小牌
            non_singles = [p for p in plan.plays if p.card_type != CardType.SINGLE]
            if non_singles:
                sorted_non_singles = sorted(non_singles, key=_get_lead_card_weight)
                return sorted_non_singles[0].cards
            else:
                # 只有单张牌了，必须顶防：出手中最大的常规单张牌
                sorted_plays = sorted(plan.plays, key=lambda p: p.main_rank, reverse=True)
                return sorted_plays[0].cards
        else:
            # 对手剩 2 张牌，无法判定牌型，首出我们手里最大的常规牌型去顶防
            sorted_plays = sorted(plan.plays, key=lambda p: p.main_rank, reverse=True)
            return sorted_plays[0].cards

    # 冲刺模式：手牌不多且只剩一两手牌即可出完
    if len(plan.plays) + len(plan.bombs) <= 2:
        # 优先把常规牌打出 (按权重排序)
        sorted_plays = sorted(plan.plays, key=_get_lead_card_weight)
        return sorted_plays[0].cards

    # 1. 地主策略：出最小的独立牌型
    if role == "landlord":
        sorted_plays = sorted(plan.plays, key=_get_lead_card_weight)
        return sorted_plays[0].cards

    # 2. 地主上家 (顶牌位) 策略
    elif role == "landlord_up":
        # 地主牌少于等于3张，直接出最大牌抢占控制权
        if ctx.landlord_remaining <= 3:
            sorted_plays = sorted(plan.plays, key=lambda p: p.main_rank, reverse=True)
            return sorted_plays[0].cards
        # 正常情况：出中大牌顶地主 (主rank >= 7，即10及以上)
        big_plays = [p for p in plan.plays if p.main_rank >= 7]
        if big_plays:
            sorted_plays = sorted(big_plays, key=lambda p: (_get_lead_priority(p), p.main_rank))
            return sorted_plays[0].cards
        # 没有大牌，出最小牌型
        sorted_plays = sorted(plan.plays, key=lambda p: (_get_lead_priority(p), p.main_rank))
        return sorted_plays[0].cards

    # 3. 地主下家 (跑牌位) 策略
    else:
        # 队友剩余牌 <= 2 张，出大牌抢回出牌权，之后送小牌给队友
        if ctx.teammate_remaining <= 2:
            sorted_plays = sorted(plan.plays, key=lambda p: p.main_rank, reverse=True)
            return sorted_plays[0].cards
        # 否则正常跑牌：出最小的独立牌型
        sorted_plays = sorted(plan.plays, key=lambda p: (_get_lead_priority(p), p.main_rank))
        return sorted_plays[0].cards


def _get_split_single(plan: HandPlan, last_play: CardPlay) -> Optional[List[int]]:
    """在没有单牌时，尝试从对子/三条（含带翅膀的）中拆出一个最小的单张来压牌"""
    candidates = []  # 元素为 (rank, card_id)

    for p in plan.plays:
        if p.card_type == CardType.PAIR:
            if p.main_rank > last_play.main_rank:
                candidates.append((p.main_rank, p.cards[0]))
        elif p.card_type in (CardType.TRIPLE, CardType.TRIPLE_ONE, CardType.TRIPLE_TWO):
            if p.main_rank > last_play.main_rank:
                card_id = [c for c in p.cards if Card.from_id(c).rank == p.main_rank][0]
                candidates.append((p.main_rank, card_id))
            if p.card_type == CardType.TRIPLE_TWO:
                wing_ranks = list(set(Card.from_id(c).rank for c in p.cards if Card.from_id(c).rank != p.main_rank))
                if wing_ranks:
                    wing_rank = wing_ranks[0]
                    if wing_rank > last_play.main_rank:
                        card_id = [c for c in p.cards if Card.from_id(c).rank == wing_rank][0]
                        candidates.append((wing_rank, card_id))
        elif p.card_type == CardType.FOUR_TWO_PAIR:
            wing_ranks = list(set(Card.from_id(c).rank for c in p.cards if Card.from_id(c).rank != p.main_rank))
            for wing_rank in wing_ranks:
                if wing_rank > last_play.main_rank:
                    card_id = [c for c in p.cards if Card.from_id(c).rank == wing_rank][0]
                    candidates.append((wing_rank, card_id))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return [candidates[0][1]]
    return None


def _get_split_pair(plan: HandPlan, last_play: CardPlay) -> Optional[List[int]]:
    """在没有独立对子时，优先从三带二、四带二对等牌型的翅膀中提取对子，其次再尝试从三条核心中拆一对来压牌"""
    # 1. 优先寻找不需要拆分三条/四条核心主牌的现成对子（从三带二、四带二对等翅膀中提取）
    wing_pair_candidates = []  # 元素为 (rank, [card_ids])
    for p in plan.plays:
        if p.card_type == CardType.TRIPLE_TWO:
            wing_cards = [c for c in p.cards if Card.from_id(c).rank != p.main_rank]
            if len(wing_cards) == 2:
                wr = Card.from_id(wing_cards[0]).rank
                if wr > last_play.main_rank:
                    wing_pair_candidates.append((wr, wing_cards))
        elif p.card_type == CardType.FOUR_TWO_PAIR:
            wing_ranks = list(set(Card.from_id(c).rank for c in p.cards if Card.from_id(c).rank != p.main_rank))
            for wr in wing_ranks:
                if wr > last_play.main_rank:
                    wing_cards = [c for c in p.cards if Card.from_id(c).rank == wr]
                    if len(wing_cards) == 2:
                        wing_pair_candidates.append((wr, wing_cards))

    if wing_pair_candidates:
        # 优先使用最小的能压过的对子翅膀，保护大牌
        wing_pair_candidates.sort(key=lambda x: x[0])
        return wing_pair_candidates[0][1]

    # 2. 如果没有现成翅膀对子，才兜底考虑从三条核心中拆一对
    candidates = []  # 元素为 (rank, [card_id1, card_id2])
    for p in plan.plays:
        if p.card_type in (CardType.TRIPLE, CardType.TRIPLE_ONE, CardType.TRIPLE_TWO):
            if p.main_rank > last_play.main_rank:
                card_ids = [c for c in p.cards if Card.from_id(c).rank == p.main_rank][:2]
                candidates.append((p.main_rank, card_ids))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    return None


def _get_split_triple_with_wings(plan: HandPlan, last_play: CardPlay) -> Optional[List[int]]:
    """智能组合/拆分三条来跟牌 (支持三条、三带一、三带二)"""
    # 1. 寻找手牌中所有可以压过它的三条
    triple_plays = []
    for p in plan.plays:
        if p.card_type in (CardType.TRIPLE, CardType.TRIPLE_ONE, CardType.TRIPLE_TWO):
            if p.main_rank > last_play.main_rank:
                triple_plays.append(p)

    if not triple_plays:
        return None

    # 按 main_rank 从小到大排序，优先使用最小的可压制三条
    triple_plays.sort(key=lambda p: p.main_rank)
    best_triple_play = triple_plays[0]

    # 提取核心三张牌
    core_cards = [c for c in best_triple_play.cards if Card.from_id(c).rank == best_triple_play.main_rank]

    if last_play.card_type == CardType.TRIPLE:
        return core_cards

    # 提取可用的单牌和对子作为翅膀 (排除核心牌)
    available_singles = []
    available_pairs = []

    for p in plan.plays:
        if p.card_type == CardType.SINGLE:
            cards = [c for c in p.cards if c not in core_cards]
            if cards:
                available_singles.append(cards[0])
        elif p.card_type == CardType.PAIR:
            cards = [c for c in p.cards if c not in core_cards]
            if len(cards) == 2:
                available_pairs.append(cards)
            elif len(cards) == 1:
                available_singles.append(cards[0])
        elif p.card_type == CardType.TRIPLE:
            if p.main_rank != best_triple_play.main_rank:
                cards = [c for c in p.cards if c not in core_cards]
                if len(cards) == 3:
                    available_pairs.append(cards[:2])
                    available_singles.append(cards[2])
        elif p.card_type in (CardType.TRIPLE_ONE, CardType.TRIPLE_TWO):
            wing = [c for c in p.cards if Card.from_id(c).rank != p.main_rank and c not in core_cards]
            if p.card_type == CardType.TRIPLE_ONE:
                available_singles.extend(wing)
            else:
                if len(wing) == 2:
                    available_pairs.append(wing)
                elif len(wing) == 1:
                    available_singles.append(wing[0])

    # 按牌力升序排列，优先使用最小的翅膀
    available_singles.sort(key=lambda c: Card.from_id(c).rank)
    available_pairs.sort(key=lambda pair: Card.from_id(pair[0]).rank)

    if last_play.card_type == CardType.TRIPLE_ONE:
        # 需要 1 张翅膀
        if available_singles:
            return core_cards + [available_singles[0]]
        elif available_pairs:
            return core_cards + [available_pairs[0][0]]  # 拆对子作为单张翅膀

    elif last_play.card_type == CardType.TRIPLE_TWO:
        # 需要 2 张对子翅膀
        if available_pairs:
            return core_cards + available_pairs[0]

    return None


def _pick_follow_play(hand: List[int], plan: HandPlan, last_play: CardPlay, role: str, ctx: AIContext) -> Optional[List[int]]:
    """被动跟牌决策"""
    is_opponent_play = (role == "landlord") or (role != "landlord" and ctx.is_last_play_landlord)

    # 情况 A：上家是对手 (地主跟农民，或农民跟地主)
    if is_opponent_play:
        # 1. 如果是三条相关牌型，使用专用的智能组合与拆牌逻辑
        if last_play.card_type in (CardType.TRIPLE, CardType.TRIPLE_ONE, CardType.TRIPLE_TWO):
            split_cards = _get_split_triple_with_wings(plan, last_play)
            if split_cards:
                return split_cards

        # 2. 查找相同牌型与长度，且能压过的整牌 (不拆牌)
        matching_plays = [
            p for p in plan.plays
            if p.card_type == last_play.card_type and p.length == last_play.length and p.main_rank > last_play.main_rank
        ]

        if matching_plays:
            matching_plays.sort(key=lambda p: p.main_rank)
            smallest_match = matching_plays[0]

            # 地主快跑完 (地主手牌数 <= 5) 时：有什么压什么
            if role != "landlord" and ctx.landlord_remaining <= 5:
                return smallest_match.cards

            # 地主出小牌 (主牌 rank <= 5，即8及以下)：用最小的能压过的牌压
            if last_play.main_rank <= 5:
                if getattr(ctx, "play_mode", "classic") == "fifty_k" and smallest_match.main_rank >= 12:
                    # 五十K模式下，用大牌压小牌必须有对手或自己手牌 <= 5 警报，或者桌面分 >= 5
                    if getattr(ctx, "other_players_min_remaining", 18) <= 5 or len(hand) <= 5 or getattr(ctx, "current_trick_score", 0) >= 5:
                        return smallest_match.cards
                else:
                    return smallest_match.cards

            # 地主出大牌 (主牌 rank >= 6)：
            # 如果压牌代价 <= A (rank 11)，直接压；
            # 如果需要使用 2 (rank 12) 或 王 (rank 13, 14)，也直接压 (大牌压大牌合情合理)
            return smallest_match.cards

        # 2. 拆单张跟牌：当上家出单张，且我们没有相同整牌，尝试拆对子/三条来跟牌
        if last_play.card_type == CardType.SINGLE:
            split_cards = _get_split_single(plan, last_play)
            if split_cards:
                return split_cards

        # 3. 拆对子跟牌：当上家出对子，且我们没有相同整牌，尝试从三条中拆一对来跟牌
        if last_play.card_type == CardType.PAIR:
            split_cards = _get_split_pair(plan, last_play)
            if split_cards:
                return split_cards

        # 4. 考虑使用炸弹 (详见炸弹决策)
        if plan.bombs and _should_use_bomb(hand, plan, ctx):
            # 找出能压过 last_play 的最小炸弹
            valid_bombs = [b for b in plan.bombs if can_beat(b, last_play, play_mode=ctx.play_mode)]
            if valid_bombs:
                valid_bombs.sort(key=lambda b: b.main_rank)
                return valid_bombs[0].cards

        return None

    # 情况 B：上家是农民队友
    else:
        # 1. 如果自己手牌 <= 3 张，且接过来就能直接赢，就必须抢牌权
        matching_plays = [
            p for p in plan.plays
            if p.card_type == last_play.card_type and p.length == last_play.length and p.main_rank > last_play.main_rank
        ]
        if matching_plays:
            matching_plays.sort(key=lambda p: p.main_rank)
            smallest_match = matching_plays[0]
            if len(hand) - len(smallest_match.cards) == 0:
                return smallest_match.cards

        # 2. 队友出了小牌 (主牌 rank <= 6)，且自己有不需要拆牌的较小整牌 (主牌 rank <= 10，即 K 及以下)，
        # 并且队友不是快出完的情况 (队友手牌数 > 2)，可以接管牌权来主导攻防
        if ctx.teammate_remaining > 2 and last_play.main_rank <= 6:
            if matching_plays and smallest_match.main_rank <= 10:
                return smallest_match.cards

        # 3. 默认放行 (不出)
        return None


def _dedupe_candidates(candidates: List[List[int]]) -> List[List[int]]:
    seen = set()
    result = []
    for cards in candidates:
        key = tuple(sorted(cards))
        if key in seen:
            continue
        seen.add(key)
        result.append(cards)
    return result


def _rule_decide_play(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool,
    ctx: AIContext,
) -> Optional[List[int]]:
    try:
        hand_play = detect_card_type(hand, play_mode=ctx.play_mode)
        if hand_play is not None:
            if last_play is None or must_play:
                logger.info(f"AI 冲刺：整手手牌为合法牌型 {hand_play.card_type.value}，直接一次性出完赢牌")
                return hand
            if can_beat(hand_play, last_play, play_mode=ctx.play_mode):
                logger.info(f"AI 冲刺：整手手牌为 {hand_play.card_type.value} 且可压过上家，直接一次性出完赢牌")
                return hand
    except Exception as e:
        logger.warning(f"AI 冲刺判断异常: {e}")

    sorted_hand = sort_cards(hand)
    plan = _decompose_hand(sorted_hand, play_mode=ctx.play_mode)

    if must_play or last_play is None:
        return _pick_lead_play(plan, ctx.role, ctx)

    return _pick_follow_play(sorted_hand, plan, last_play, ctx.role, ctx)


def ai_rank_play_candidates(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool,
    ctx: AIContext,
    limit: int = 12,
) -> List[List[int]]:
    if not hand:
        return []

    try:
        is_fifty_k = (ctx and getattr(ctx, "play_mode", "classic") == "fifty_k")
        if not is_fifty_k and ctx and ctx.play_history is not None and douzero_manager.is_available():
            legal_actions = generate_legal_actions_dz(hand, last_play, must_play)
            if not legal_actions:
                return []
            obs = get_obs_for_douzero(
                hand=hand,
                legal_actions=legal_actions,
                role=ctx.role,
                landlord_id=ctx.landlord_id,
                player_ids=ctx.player_ids,
                play_history=ctx.play_history,
            )
            import torch

            z = torch.from_numpy(obs["z_batch"]).float()
            x = torch.from_numpy(obs["x_batch"]).float()
            scores = douzero_manager.get_action_value(ctx.role, z, x).reshape(-1)
            order = torch.argsort(scores, descending=True).tolist()

            ranked = []
            for idx in order:
                action_dz = obs["legal_actions"][idx]
                if not action_dz:
                    ranked.append([])
                    continue
                cards = douzero_to_card_ids(action_dz, hand)
                if cards:
                    ranked.append(cards)
            return _dedupe_candidates(ranked)[:limit]
    except Exception as e:
        logger.warning(f"DouZero ranking failed, falling back to rule engine: {e}")

    fallback = _rule_decide_play(hand, last_play, must_play, ctx)
    return [fallback] if fallback else ([] if must_play else [[]])


def _should_use_bomb(hand: List[int], plan: HandPlan, ctx: AIContext) -> bool:
    """炸弹使用判定"""
    if not plan.bombs:
        return False

    # 510K模式下，当桌面分值 >= 10 时，强制返回 True 引导炸弹介入抢分
    if getattr(ctx, "play_mode", "classic") == "fifty_k" and getattr(ctx, "current_trick_score", 0) >= 10:
        return True

    # 1. 封堵对手：在 510K 模式下，有任何其他对手的手牌数 <= 3 张，必须予以封堵轰炸
    if getattr(ctx, "play_mode", "classic") == "fifty_k":
        if getattr(ctx, "other_players_min_remaining", 18) <= 3:
            return True
    else:
        # 经典/不洗牌模式下的封堵地主
        if ctx.role != "landlord" and ctx.landlord_remaining <= 3:
            return True

    # 2. 终结局：自己手牌 <= 5 张，炸完之后剩余牌能一手出完
    if len(hand) <= 5 and plan.hand_count <= 1:
        return True

    # 3. 助攻队友：农民合作下，队友剩余牌 <= 2 张，炸完送牌给队友赢
    if ctx.role != "landlord" and ctx.teammate_remaining <= 2:
        return True

    return False


def generate_legal_actions_dz(hand: List[int], last_play: Optional[CardPlay], must_play: bool) -> List[List[int]]:
    from collections import Counter
    from itertools import combinations

    my_hand_dz = sorted([card_id_to_douzero(c) for c in hand])
    dz_counts = Counter(my_hand_dz)

    # 1. 找出所有的单张
    singles = sorted(list(dz_counts.keys()))

    # 2. 找出所有的对子
    pairs = sorted([r for r, c in dz_counts.items() if c >= 2])

    # 3. 找出所有的三条
    triples = sorted([r for r, c in dz_counts.items() if c >= 3])

    # 4. 找出所有的炸弹
    bombs = sorted([r for r, c in dz_counts.items() if c >= 4])

    # 5. 王炸
    has_rocket = (20 in dz_counts and 30 in dz_counts)

    # 我们生成所有的候选 DouZero 动作 (dz action)
    candidates_dz = []

    # 单张
    for r in singles:
        candidates_dz.append([r])

    # 对子
    for r in pairs:
        candidates_dz.append([r, r])

    # 三条
    for r in triples:
        candidates_dz.append([r, r, r])

    # 三带一
    for r in triples:
        for wing in singles:
            if wing != r:
                candidates_dz.append([r, r, r, wing])

    # 三带二
    for r in triples:
        for wing in pairs:
            if wing != r:
                candidates_dz.append([r, r, r, wing, wing])

    # 顺子 (>= 5张连续, 不含2(17)和王(20, 30))
    valid_seq_ranks = sorted([r for r in singles if r < 17])
    for length in range(5, len(valid_seq_ranks) + 1):
        for start_idx in range(len(valid_seq_ranks) - length + 1):
            sub = valid_seq_ranks[start_idx:start_idx + length]
            if sub[-1] == sub[0] + length - 1:
                candidates_dz.append(sub)

    # 连对 (>= 3对连续, 不含2(17)和王(20, 30))
    valid_pair_ranks = sorted([r for r in pairs if r < 17])
    for length in range(3, len(valid_pair_ranks) + 1):
        for start_idx in range(len(valid_pair_ranks) - length + 1):
            sub = valid_pair_ranks[start_idx:start_idx + length]
            if sub[-1] == sub[0] + length - 1:
                act = []
                for r in sub:
                    act.extend([r, r])
                candidates_dz.append(act)

    # 飞机相关
    valid_triple_ranks = sorted([r for r in triples if r < 17])
    for length in range(2, len(valid_triple_ranks) + 1):
        for start_idx in range(len(valid_triple_ranks) - length + 1):
            sub = valid_triple_ranks[start_idx:start_idx + length]
            if sub[-1] == sub[0] + length - 1:
                base_act = []
                for r in sub:
                    base_act.extend([r, r, r])
                candidates_dz.append(base_act)

                other_singles = sorted([r for r in singles if r not in sub])
                if len(other_singles) >= length:
                    for wings in combinations(other_singles, length):
                        candidates_dz.append(base_act + list(wings))

                other_pairs = sorted([r for r in pairs if r not in sub])
                if len(other_pairs) >= length:
                    for wings in combinations(other_pairs, length):
                        act = list(base_act)
                        for w in wings:
                            act.extend([w, w])
                        candidates_dz.append(act)

    # 四带二
    for r in bombs:
        # 四带二单
        remaining = list(my_hand_dz)
        for _ in range(4):
            remaining.remove(r)
        if len(remaining) >= 2:
            seen_combos = set()
            for combo in combinations(remaining, 2):
                combo_sorted = tuple(sorted(combo))
                if combo_sorted not in seen_combos:
                    seen_combos.add(combo_sorted)
                    candidates_dz.append([r, r, r, r] + list(combo_sorted))

        # 四带二对
        other_pairs = sorted([p for p in pairs if p != r])
        if len(other_pairs) >= 2:
            for pair_combo in combinations(other_pairs, 2):
                act = [r, r, r, r]
                for p in pair_combo:
                    act.extend([p, p])
                candidates_dz.append(act)

    # 炸弹
    for r in bombs:
        candidates_dz.append([r, r, r, r])

    # 王炸
    if has_rocket:
        candidates_dz.append([20, 30])

    # 2. 映射回卡牌 ID 并验证合法性
    legal_actions = []
    for act_dz in candidates_dz:
        card_ids = douzero_to_card_ids(act_dz, hand)
        if card_ids:
            play = detect_card_type(card_ids)
            if play is not None:
                if last_play is None:
                    legal_actions.append(card_ids)
                elif can_beat(play, last_play):
                    legal_actions.append(card_ids)

    if not must_play and last_play is not None:
        legal_actions.append([])

    return legal_actions


def ai_decide_play(
    hand: List[int],
    last_play: Optional[CardPlay],
    must_play: bool,
    ctx: Optional[AIContext] = None,
) -> Optional[List[int]]:
    """
    AI 决策出牌入口函数。
    - hand: 当前 AI 的手牌 ID 列表
    - last_play: 最近一次合法的出牌记录 (若为新一轮则为 None)
    - must_play: 是否必须出牌 (首发)
    - ctx: AI 决策上下文 (可选，为空时在测试环境下生成默认值)
    """
    if not hand:
        return None

    # 构建默认上下文（主要针对旧的单测兼容）
    if ctx is None:
        ctx = AIContext(
            ai_id="test_ai",
            role="landlord",
            landlord_id="test_ai",
            teammate_id=None,
            landlord_remaining=len(hand),
            teammate_remaining=0,
            last_play_from=None,
            is_last_play_teammate=False,
            is_last_play_landlord=False,
        )

    ranked = ai_rank_play_candidates(hand, last_play, must_play, ctx, limit=1)
    if ranked:
        best = ranked[0]
        return best if best else None

    return _rule_decide_play(hand, last_play, must_play, ctx)
