# backend/app/domain/game/room.py
"""游戏房间状态机：管理一局斗地主的完整生命周期"""
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any, Set
from app.domain.game.card import shuffle_and_deal, sort_cards, Card, FULL_DECK
from app.domain.game.card_type import detect_card_type, can_beat, CardPlay


class GamePhase(Enum):
    MATCHING = "MATCHING"
    DEALING = "DEALING"
    CALLING = "CALLING"
    LANDLORD_CONFIRM = "LANDLORD_CONFIRM"
    DOUBLING = "DOUBLING"
    PLAYING = "PLAYING"
    SETTLING = "SETTLING"


@dataclass
class Player:
    id: str
    nickname: str
    is_ai: bool = False
    is_online: bool = True


@dataclass
class LastPlay:
    """最近一次出牌记录"""
    player: Optional[str] = None
    cards: List[int] = field(default_factory=list)
    card_type: Optional[str] = None
    card_play: Optional[CardPlay] = None


class GameRoom:
    """
    斗地主游戏房间。
    封装了一局游戏的全部状态和规则逻辑。
    所有状态变更方法返回 dict 描述操作结果。
    """

    MAX_REDEAL = 3  # 最多重新发牌次数

    def __init__(self, play_mode: str = "classic"):
        self.room_id: str = ""
        self.phase: GamePhase = GamePhase.DEALING
        self.players: List[Player] = []
        self.hands: Dict[str, List[int]] = {}
        self.bottom_cards: List[int] = []
        self.landlord: Optional[str] = None
        self.current_turn: Optional[str] = None
        self.turn_deadline: float = 0
        self.last_play: LastPlay = LastPlay()
        self.pass_count: int = 0  # 连续不出次数
        self.multiplier: int = 1
        self.doubling_choices: Dict[str, str] = {}
        self.show_cards_players: Dict[str, int] = {}
        self.redeal_count: int = 0
        self.created_at: str = ""
        self.base_score: int = 10
        self.all_played_cards: List[int] = []
        self.play_history: List[Dict[str, Any]] = []
        self.auto_play_players: Set[str] = set()
        self.play_mode: str = play_mode
        self.scores: Dict[str, int] = {}
        self.current_trick_cards: List[int] = []
        self.trick_no: int = 0
        self.cumulative_bean_changes: Dict[str, int] = {}
        self.bean_balances: Dict[str, int] = {}
        self.player_triggered_boost: Set[str] = set()

        # 叫地主状态
        self._call_index: int = 0       # 当前叫地主的玩家索引
        self._call_scores: Dict[str, int] = {}  # 每个玩家的叫分 (0=不叫)
        self._first_caller_index: int = 0  # 首位叫牌者索引
        self._call_round: int = 1        # 当前圈数 (1=第一圈, 2=第二圈)
        self._first_bidder: Optional[str] = None  # 首位叫地主的玩家 ID
        self._round2_queue: List[str] = []   # 第二圈待表态队列
        self._round2_scores: Dict[str, int] = {}  # 第二圈叫分记录
        self._grab_count: Dict[str, int] = {}  # 抢地主次数
        self._declined_players: Set[str] = set()  # 选择不叫或不抢的玩家 ID 集合

    @classmethod
    def create(cls, room_id: str, players: List[Player], base_score: int = 10) -> "GameRoom":
        room = cls()
        room.room_id = room_id
        room.players = players
        room.base_score = base_score
        room.phase = GamePhase.DEALING
        room.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        return room

    def _player_ids(self) -> List[str]:
        return [p.id for p in self.players]

    def _next_player(self, current_id: str) -> str:
        ids = self._player_ids()
        idx = ids.index(current_id)
        return ids[(idx + 1) % 3]

    # ── 发牌 ──

    def deal(self) -> Dict[str, List[int]]:
        """洗牌发牌，状态从 DEALING → CALLING"""
        self.player_triggered_boost = set()
        if self.play_mode == "fifty_k":
            import random
            deck = FULL_DECK.copy()
            random.shuffle(deck)
            ids = self._player_ids()
            h1 = sort_cards(deck[0:18])
            h2 = sort_cards(deck[18:36])
            h3 = sort_cards(deck[36:54])
            self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
            self.bottom_cards = []
            self.phase = GamePhase.PLAYING
            self.landlord = None
            self.last_play = LastPlay()
            self.pass_count = 0
            self.scores = {p.id: 0 for p in self.players}
            self.current_trick_cards = []
            self.trick_no = 0
            self.cumulative_bean_changes = {p.id: 0 for p in self.players}
            self.doubling_choices = {}
            self.show_cards_players = {}
            self.all_played_cards = []
            self.play_history = []
            self.auto_play_players = set()

            # 梅花 3（ID=2）持有者获得首出权。
            club_3_player = None
            for pid, hand in self.hands.items():
                if 2 in hand:
                    club_3_player = pid
                    break
            self.current_turn = club_3_player
            self.turn_deadline = time.time() + 30
            return dict(self.hands)

        h1, h2, h3, bottom = shuffle_and_deal()
        ids = self._player_ids()
        self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
        self.bottom_cards = bottom
        self.phase = GamePhase.CALLING
        self.landlord = None
        self.last_play = LastPlay()
        self.pass_count = 0
        self.doubling_choices = {}
        self.show_cards_players = {}
        self.all_played_cards = []
        self.play_history = []
        self.auto_play_players = set()
        self._call_index = 0
        self._call_scores = {}
        self._call_round = 1
        self._first_bidder = None
        self._round2_queue = []
        self._round2_scores = {}
        self._grab_count = {}
        self._declined_players = set()
        # 随机选择首位叫牌者 (使用第一个玩家索引)
        import random
        self._first_caller_index = random.randint(0, 2)
        self._call_index = self._first_caller_index
        self.current_turn = ids[self._first_caller_index]
        self.turn_deadline = time.time() + 18  # 15s 叫牌时间 + 3s 发牌动画缓冲
        return dict(self.hands)

    def deal_with_deck(self, deck: List[int]) -> Dict[str, List[int]]:
        """传入预设牌堆发牌，应用切牌并切片分发"""
        self.player_triggered_boost = set()
        ids = self._player_ids()
        from app.domain.game.card import cut_cards

        if self.play_mode == "fifty_k":
            cut_deck = cut_cards(deck)
            h1 = sort_cards(cut_deck[0:18])
            h2 = sort_cards(cut_deck[18:36])
            h3 = sort_cards(cut_deck[36:54])

            self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
            self.bottom_cards = []
            self.phase = GamePhase.PLAYING
            self.landlord = None
            self.last_play = LastPlay()
            self.pass_count = 0
            self.scores = {p.id: 0 for p in self.players}
            self.current_trick_cards = []
            self.trick_no = 0
            self.cumulative_bean_changes = {p.id: 0 for p in self.players}
            self.doubling_choices = {}
            self.show_cards_players = {}
            self.all_played_cards = []
            self.play_history = []
            self.auto_play_players = set()

            # 梅花 3（ID=2）持有者获得首出权。
            club_3_player = None
            for pid, hand in self.hands.items():
                if 2 in hand:
                    club_3_player = pid
                    break
            self.current_turn = club_3_player
            self.turn_deadline = time.time() + 30
            return dict(self.hands)

        cut_deck = cut_cards(deck)
        h1 = sort_cards(cut_deck[0:17])
        h2 = sort_cards(cut_deck[17:34])
        h3 = sort_cards(cut_deck[34:51])
        bottom = sort_cards(cut_deck[51:54])

        self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
        self.bottom_cards = bottom
        self.phase = GamePhase.CALLING
        self.landlord = None
        self.last_play = LastPlay()
        self.pass_count = 0
        self.doubling_choices = {}
        self.show_cards_players = {}
        self.all_played_cards = []
        self.play_history = []
        self.auto_play_players = set()
        self._call_index = 0
        self._call_scores = {}
        self._call_round = 1
        self._first_bidder = None
        self._round2_queue = []
        self._round2_scores = {}
        self._grab_count = {}
        self._declined_players = set()

        import random
        self._first_caller_index = random.randint(0, 2)
        self._call_index = self._first_caller_index
        self.current_turn = ids[self._first_caller_index]
        self.turn_deadline = time.time() + 18
        return dict(self.hands)

    def recycle_cards(self) -> List[int]:
        """回收已打出和未打出的牌堆"""
        recycled = list(self.all_played_cards)
        # 按玩家座位顺序收集剩余手牌
        for p in self.players:
            recycled.extend(self.hands.get(p.id, []))
        # 如果底牌没有发给任何人且未出现在出牌/手牌中，则追加底牌
        if self.landlord is None:
            recycled.extend(self.bottom_cards)

        # 严格校验是否构成完整的54张牌
        if len(recycled) == 54 and sorted(recycled) == list(range(54)):
            return recycled
        # 失败防御兜底
        return list(range(54))


    # ── 叫地主 ──

    def call_landlord(self, player_id: str, score: int) -> dict:
        """玩家叫地主 (score: 传入值兼容，完全按腾讯规则决定叫/抢)"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前不在叫地主阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        if self._first_bidder is None:
            # 叫地主
            self._first_bidder = player_id
            self.landlord = player_id
            self.multiplier = 1
            self._call_scores[player_id] = 1
            self._call_round = 2  # 设为 2 表示已叫过，转为抢地主阶段
            return self._advance_bidding(player_id)
        else:
            # 抢地主
            if player_id in self._declined_players:
                return {"success": False, "error": "您之前已选择不叫或不抢，无法进行抢地主"}
            if player_id == self.landlord:
                return {"success": False, "error": "您当前已经是暂定地主"}
            if self._grab_count.get(player_id, 0) >= 1:
                return {"success": False, "error": "您已经进行过抢地主，每人限抢一次"}

            self.landlord = player_id
            self.multiplier *= 2
            self._grab_count[player_id] = self._grab_count.get(player_id, 0) + 1
            max_score = max(self._call_scores.values()) if self._call_scores else 0
            self._call_scores[player_id] = max_score + 1
            return self._advance_bidding(player_id)

    def skip_call(self, player_id: str) -> dict:
        """玩家不叫/不抢"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前不在叫地主阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        self._declined_players.add(player_id)
        self._call_scores[player_id] = 0
        return self._advance_bidding(player_id)

    def show_cards(self, player_id: str, show_multiplier: int) -> dict:
        """玩家在发牌阶段选择明牌"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前阶段不允许明牌"}
        if player_id not in self._player_ids():
            return {"success": False, "error": "玩家不在当前房间"}
        if str(player_id) in self.show_cards_players:
            return {"success": False, "error": "你已经明牌了"}
        if show_multiplier not in (2, 3, 4):
            return {"success": False, "error": "无效的明牌倍数"}

        self.show_cards_players[str(player_id)] = show_multiplier
        self.multiplier *= show_multiplier
        return {
            "success": True,
            "player_id": player_id,
            "cards": self.hands[player_id],
            "show_multiplier": show_multiplier,
            "total_multiplier": self.multiplier,
        }

    def landlord_show_cards(self, player_id: str) -> dict:
        """地主在确认阶段选择明牌（固定2倍）"""
        if self.phase != GamePhase.LANDLORD_CONFIRM:
            return {"success": False, "error": "当前不在地主明牌确认阶段"}
        if player_id != self.landlord:
            return {"success": False, "error": "只有地主可以在此阶段明牌"}
        if str(player_id) in self.show_cards_players:
            return {"success": False, "error": "你已经明牌了"}

        self.show_cards_players[str(player_id)] = 2
        self.multiplier *= 2
        self.phase = GamePhase.PLAYING
        self.current_turn = self.landlord
        self.turn_deadline = time.time() + 30
        return {
            "success": True,
            "player_id": player_id,
            "cards": self.hands[player_id],
            "show_multiplier": 2,
            "total_multiplier": self.multiplier,
        }

    def finish_landlord_confirm(self) -> dict:
        """地主选择出牌（不明牌），进入出牌阶段"""
        if self.phase != GamePhase.LANDLORD_CONFIRM:
            return {"success": False, "error": "当前不在明牌选择阶段"}
        self.phase = GamePhase.PLAYING
        self.current_turn = self.landlord
        self.turn_deadline = time.time() + 30
        return {
            "success": True,
            "multiplier": self.multiplier,
        }

    def _advance_bidding(self, current_player_id: str) -> dict:
        """推进叫牌/抢地主流程"""
        ids = self._player_ids()

        if self._first_bidder is None:
            # 尚未有人叫地主
            if len(self._declined_players) >= 3:
                # 重新发牌
                self.redeal_count += 1
                if self.redeal_count >= self.MAX_REDEAL:
                    import random
                    forced = random.choice(ids)
                    self.multiplier = 1
                    return self._set_landlord(forced)
                self.phase = GamePhase.DEALING
                return {"success": True, "redeal": True}

            # 轮到下一个叫地主
            idx = ids.index(current_player_id)
            next_player = ids[(idx + 1) % 3]
            self.current_turn = next_player
            self._call_index = (idx + 1) % 3
            self.turn_deadline = time.time() + 15
            return {"success": True, "next_caller": self.current_turn}
        else:
            # 抢地主流程，寻找下一个符合资格的抢地主玩家
            idx = ids.index(current_player_id)
            next_turn_id = None
            for i in range(1, 3):
                candidate_id = ids[(idx + i) % 3]
                if (
                    candidate_id not in self._declined_players
                    and candidate_id != self.landlord
                    and self._grab_count.get(candidate_id, 0) < 1
                ):
                    next_turn_id = candidate_id
                    break

            if next_turn_id:
                self.current_turn = next_turn_id
                self._call_index = ids.index(next_turn_id)
                self.turn_deadline = time.time() + 15
                return {"success": True, "next_caller": self.current_turn}
            else:
                # 没人能抢了，确定地主
                return self._set_landlord(self.landlord)

    def _set_landlord(self, player_id: str) -> dict:
        """确定地主，分配底牌，进入加倍阶段"""
        self.landlord = player_id
        # 底牌给地主
        self.hands[player_id] = sort_cards(self.hands[player_id] + self.bottom_cards)
        self.phase = GamePhase.DOUBLING
        self.current_turn = None
        self.turn_deadline = time.time() + 15
        self.last_play = LastPlay()
        self.pass_count = 0
        self.doubling_choices = {}
        return {
            "success": True,
            "landlord": player_id,
            "bottom_cards": self.bottom_cards,
            "multiplier": self.multiplier,
        }

    def choose_double(self, player_id: str, choice: str) -> dict:
        """玩家确认加倍选择"""
        if self.phase != GamePhase.DOUBLING:
            return {"success": False, "error": "当前不在加倍确认阶段"}
        if player_id not in self._player_ids():
            return {"success": False, "error": "玩家不在当前房间"}
        if player_id in self.doubling_choices:
            return {"success": False, "error": "你已经选择过加倍"}
        if choice not in ("double", "super", "none"):
            return {"success": False, "error": "无效的加倍选择"}

        self.doubling_choices[player_id] = choice
        if choice == "double":
            self.multiplier *= 2
        elif choice == "super":
            self.multiplier *= 4

        result = {
            "success": True,
            "player": player_id,
            "choice": choice,
            "multiplier": self.multiplier,
        }
        if len(self.doubling_choices) >= len(self.players):
            result.update(self._finish_doubling())
        return result

    def _finish_doubling(self) -> dict:
        """所有玩家完成加倍确认后，决定下一阶段"""
        if self.landlord and str(self.landlord) in self.show_cards_players:
            self.phase = GamePhase.PLAYING
            self.current_turn = self.landlord
            self.turn_deadline = time.time() + 30
            return {
                "doubling_finished": True,
                "next_turn": self.current_turn,
                "multiplier": self.multiplier,
            }
        else:
            self.phase = GamePhase.LANDLORD_CONFIRM
            self.current_turn = self.landlord
            self.turn_deadline = time.time() + 30
            return {
                "doubling_finished": True,
                "landlord_confirm_required": True,
                "next_turn": self.current_turn,
                "multiplier": self.multiplier,
            }

    # ── 出牌 ──

    def play_cards(self, player_id: str, card_ids: List[int]) -> dict:
        """玩家出牌"""
        if self.phase != GamePhase.PLAYING:
            return {"success": False, "error": "当前不在出牌阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}
        if not card_ids:
            return {"success": False, "error": "出牌不能为空"}

        # 检查玩家是否持有这些牌
        hand = self.hands[player_id]
        for cid in card_ids:
            if cid not in hand:
                return {"success": False, "error": f"你没有牌 {cid}"}

        # 检测牌型
        play = detect_card_type(card_ids, play_mode=self.play_mode)
        if play is None:
            return {"success": False, "error": "不合法的牌型"}

        # 如果有上家出牌，必须压过
        if self.last_play.card_play is not None:
            if not can_beat(play, self.last_play.card_play, play_mode=self.play_mode):
                return {"success": False, "error": "出的牌压不过上家"}

        # 炸弹/王炸翻倍
        from app.domain.game.card_type import CardType
        if play.card_type in (CardType.BOMB, CardType.ROCKET):
            self.multiplier *= 2

        if getattr(self, "play_mode", "classic") == "fifty_k":
            if play.card_type in (CardType.FIFTY_K_TRUE, CardType.ROCKET):
                self.player_triggered_boost.add(player_id)

        # 从手牌中移除
        new_hand = list(hand)
        for cid in card_ids:
            new_hand.remove(cid)
        self.hands[player_id] = new_hand
        self.all_played_cards.extend(card_ids)
        if self.play_mode == "fifty_k":
            self.current_trick_cards.extend(card_ids)

        # 更新出牌记录
        self.last_play = LastPlay(
            player=player_id,
            cards=card_ids,
            card_type=play.card_type.value,
            card_play=play
        )
        self.pass_count = 0
        self.play_history.append({"player": player_id, "cards": card_ids})

        # 检查是否出完
        if len(new_hand) == 0:
            if getattr(self, "play_mode", "classic") == "fifty_k":
                self.phase = GamePhase.SETTLING
                result = {
                    "success": True,
                    "cards_played": card_ids,
                    "card_type": play.card_type.value,
                    "remaining": 0,
                    "next_turn": None,
                }
                trick_settlement = self._close_fifty_k_trick(player_id)
                if trick_settlement:
                    result["trick_settlement"] = trick_settlement
                return result
            return self._settle(player_id)

        # 轮到下一个玩家
        self.current_turn = self._next_player(player_id)
        self.turn_deadline = time.time() + 15
        return {
            "success": True,
            "cards_played": card_ids,
            "card_type": play.card_type.value,
            "remaining": len(new_hand),
            "next_turn": self.current_turn,
        }

    def _get_card_score(self, card_id: int) -> int:
        if card_id < 52:
            rank = card_id // 4
            if rank == 2:  # '5'
                return 5
            elif rank == 7:  # '10'
                return 10
            elif rank == 10:  # 'K'
                return 10
        return 0

    def _close_fifty_k_trick(self, winner_id: str) -> Optional[dict]:
        score = sum(self._get_card_score(card_id) for card_id in self.current_trick_cards)
        trick_cards = list(self.current_trick_cards)
        self.current_trick_cards = []
        if score <= 0:
            return None
        self.scores[winner_id] = self.scores.get(winner_id, 0) + score
        self.trick_no += 1
        return {
            "trick_no": self.trick_no,
            "winner_id": winner_id,
            "score_gained": score,
            "trick_cards": trick_cards,
            "multiplier": self.multiplier,
        }

    def pass_turn(self, player_id: str) -> dict:
        """玩家不出（过）"""
        if self.phase != GamePhase.PLAYING:
            return {"success": False, "error": "当前不在出牌阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        # 新一轮的首位出牌者不能不出
        if self.last_play.player is None:
            hand = self.hands.get(player_id, [])
            if hand:
                from app.domain.game.card import sort_cards
                sorted_hand = sort_cards(hand)
                min_card = [sorted_hand[0]]
                return self.play_cards(player_id, min_card)
            return {"success": False, "error": "新一轮必须出牌"}

        self.pass_count += 1
        self.play_history.append({"player": player_id, "cards": []})

        # 如果连续2人不出，最后出牌的人获得新一轮主导权
        if self.pass_count >= 2:
            trick_settlement = None
            if self.play_mode == "fifty_k":
                winner_id = self.last_play.player
                if winner_id:
                    trick_settlement = self._close_fifty_k_trick(winner_id)

            self.current_turn = self.last_play.player
            self.last_play = LastPlay()  # 清空上家，新一轮
            self.pass_count = 0
            self.turn_deadline = time.time() + 15

            res = {"success": True, "new_round": True, "next_turn": self.current_turn}
            if trick_settlement:
                res["trick_settlement"] = trick_settlement
            return res

        self.current_turn = self._next_player(player_id)
        self.turn_deadline = time.time() + 15
        return {"success": True, "next_turn": self.current_turn}

    # ── 结算 ──

    def _settle(self, winner_id: str) -> dict:
        """游戏结算"""
        self.phase = GamePhase.SETTLING
        is_landlord_win = (winner_id == self.landlord)
        winner_side = "landlord" if is_landlord_win else "farmer"

        base_score = self.multiplier * self.base_score
        scores = {}
        for p in self.players:
            if p.id == self.landlord:
                scores[p.id] = base_score * 2 if is_landlord_win else -base_score * 2
            else:
                scores[p.id] = -base_score if is_landlord_win else base_score

        return {
            "success": True,
            "game_over": True,
            "winner": winner_id,
            "winner_side": winner_side,
            "landlord": self.landlord,
            "multiplier": self.multiplier,
            "scores": scores,
            "all_hands": dict(self.hands),
        }

    def settle(self) -> dict:
        """五十K终局结算与收割分数"""
        if self.play_mode != "fifty_k":
            return {}

        # 找出最先跑完手牌的玩家 winner_id
        winner_id = None
        for pid, hand in self.hands.items():
            if len(hand) == 0:
                winner_id = pid
                break

        if not winner_id:
            return {"success": False, "error": "无人出完牌，无法结算"}

        self.phase = GamePhase.SETTLING

        # 统计其余两名玩家手牌里的剩余分牌；历史吃分不得倒扣。
        harvested_scores = {}
        remaining_card_scores = {}
        total_harvested = 0
        for pid, hand in self.hands.items():
            if pid == winner_id:
                continue

            s_single = sum(self._get_card_score(cid) for cid in hand)
            harvested_scores[pid] = -s_single
            remaining_card_scores[pid] = s_single
            total_harvested += s_single

        # 赢家最终得分增加 S_rem
        self.scores[winner_id] = self.scores.get(winner_id, 0) + total_harvested
        harvested_scores[winner_id] = total_harvested

        final_multiplier = int(self.multiplier)
        losers = [player.id for player in self.players if player.id != winner_id]
        finish_base_changes = {player.id: 0 for player in self.players}
        remaining_card_changes = {player.id: 0 for player in self.players}
        for loser_id in losers:
            fixed_loss = 4500 * final_multiplier
            remaining_loss = (
                remaining_card_scores.get(loser_id, 0)
                * self.base_score
                * final_multiplier
            )
            finish_base_changes[loser_id] = -fixed_loss
            remaining_card_changes[loser_id] = -remaining_loss
        finish_base_changes[winner_id] = -sum(finish_base_changes.values())
        remaining_card_changes[winner_id] = -sum(remaining_card_changes.values())
        total_bean_changes = {
            player.id: (
                self.cumulative_bean_changes.get(player.id, 0)
                + finish_base_changes[player.id]
                + remaining_card_changes[player.id]
            )
            for player in self.players
        }

        return {
            "success": True,
            "game_over": True,
            "winner": winner_id,
            "winner_side": "individual",
            "multiplier": final_multiplier,
            "scores": dict(self.scores),
            "all_hands": dict(self.hands),
            "fifty_k_settlement": {
                "winner_id": winner_id,
                "final_multiplier": final_multiplier,
                "harvested_scores": harvested_scores,
                "remaining_card_scores": remaining_card_scores,
                "trick_bean_changes": dict(self.cumulative_bean_changes),
                "finish_base_changes": finish_base_changes,
                "remaining_card_changes": remaining_card_changes,
                "total_bean_changes": total_bean_changes,
            }
        }

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为可存入 Redis 的 dict"""
        return {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "play_mode": self.play_mode,
            "players": [
                {"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai, "is_online": p.is_online}
                for p in self.players
            ],
            "hands": self.hands,
            "bottom_cards": self.bottom_cards,
            "landlord": self.landlord,
            "current_turn": self.current_turn,
            "turn_deadline": self.turn_deadline,
            "last_play": {
                "player": self.last_play.player,
                "cards": self.last_play.cards,
                "card_type": self.last_play.card_type,
            },
            "pass_count": self.pass_count,
            "multiplier": self.multiplier,
            "doubling_choices": self.doubling_choices,
            "redeal_count": self.redeal_count,
            "created_at": self.created_at,
            "call_index": self._call_index,
            "call_scores": self._call_scores,
            "first_caller_index": self._first_caller_index,
            "call_round": self._call_round,
            "first_bidder": self._first_bidder,
            "round2_queue": self._round2_queue,
            "round2_scores": self._round2_scores,
            "base_score": self.base_score,
            "all_played_cards": self.all_played_cards,
            "play_history": self.play_history,
            "grab_count": self._grab_count,
            "declined_players": list(self._declined_players),
            "show_cards_players": self.show_cards_players,
            "auto_play_players": list(self.auto_play_players),
            "scores": self.scores,
            "current_trick_cards": self.current_trick_cards,
            "trick_no": self.trick_no,
            "cumulative_bean_changes": self.cumulative_bean_changes,
            "bean_balances": self.bean_balances,
            "player_triggered_boost": list(self.player_triggered_boost),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameRoom":
        """从 dict 反序列化"""
        room = cls()
        room.room_id = data["room_id"]
        room.play_mode = data.get("play_mode", "classic")
        room.phase = GamePhase(data["phase"])
        room.players = [
            Player(id=p["id"], nickname=p["nickname"], is_ai=p["is_ai"], is_online=p["is_online"])
            for p in data["players"]
        ]
        room.hands = {k: list(v) for k, v in data["hands"].items()}
        room.bottom_cards = data["bottom_cards"]
        room.landlord = data.get("landlord")
        room.current_turn = data.get("current_turn")
        room.turn_deadline = data.get("turn_deadline", 0)
        lp = data.get("last_play", {})
        room.last_play = LastPlay(
            player=lp.get("player"),
            cards=lp.get("cards", []),
            card_type=lp.get("card_type"),
        )
        # 如果有上家出牌，重建 card_play 对象
        if room.last_play.cards:
            room.last_play.card_play = detect_card_type(
                room.last_play.cards,
                play_mode=room.play_mode,
            )
        room.pass_count = data.get("pass_count", 0)
        room.multiplier = data.get("multiplier", 1)
        room.doubling_choices = data.get("doubling_choices", {})
        room.redeal_count = data.get("redeal_count", 0)
        room.created_at = data.get("created_at", "")
        room._call_index = data.get("call_index", 0)
        room._call_scores = data.get("call_scores", {})
        room._first_caller_index = data.get("first_caller_index", 0)
        room._call_round = data.get("call_round", 1)
        room._first_bidder = data.get("first_bidder")
        room._round2_queue = data.get("round2_queue", [])
        room._round2_scores = data.get("round2_scores", {})
        room._grab_count = data.get("grab_count", {})
        room._declined_players = set(data.get("declined_players", []))
        room.show_cards_players = data.get("show_cards_players", {})
        room.base_score = data.get("base_score", 10)
        room.all_played_cards = data.get("all_played_cards", [])
        room.play_history = data.get("play_history", [])
        room.auto_play_players = set(data.get("auto_play_players", []))
        room.scores = {k: int(v) for k, v in data.get("scores", {}).items()}
        room.current_trick_cards = list(data.get("current_trick_cards", []))
        room.trick_no = int(data.get("trick_no", 0))
        room.cumulative_bean_changes = {
            k: int(v) for k, v in data.get("cumulative_bean_changes", {}).items()
        }
        room.bean_balances = {k: int(v) for k, v in data.get("bean_balances", {}).items()}
        room.player_triggered_boost = set(data.get("player_triggered_boost", []))
        return room

    def get_player_view(self, player_id: str) -> dict:
        """获取特定玩家可见的房间状态（隐藏他人手牌）"""
        # 只有在最终确定地主（即已离开 DEALING 和 CALLING 阶段）时才判定地主确定
        is_landlord_decided = self.landlord is not None and self.phase not in (GamePhase.DEALING, GamePhase.CALLING)

        players_view = []
        for p in self.players:
            pv = {"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai, "is_online": p.is_online}
            if p.id == player_id:
                pv["is_self"] = True
            pv["remaining"] = len(self.hands.get(p.id, []))
            # 明牌玩家的手牌对所有人可见
            if p.id in self.show_cards_players:
                pv["shown_cards"] = sort_cards(self.hands.get(p.id, []))
                pv["show_multiplier"] = self.show_cards_players[p.id]

            # 只有地主最终敲定后才设置 is_landlord 标志
            if is_landlord_decided:
                pv["is_landlord"] = (p.id == self.landlord)
            players_view.append(pv)

        view = {
            "room_id": self.room_id,
            "phase": self.phase.value,
            "players": players_view,
            "hand": sort_cards(self.hands.get(player_id, [])),
            "current_turn": self.current_turn,
            "turn_deadline": self.turn_deadline,
            "last_play": {
                "player": self.last_play.player,
                "cards": self.last_play.cards,
                "card_type": self.last_play.card_type,
            },
            "multiplier": self.multiplier,
            "doubling_choices": dict(self.doubling_choices),
            "call_round": self._call_round,
            "call_scores": dict(self._call_scores),
            "first_bidder": self._first_bidder,
            "landlord": self.landlord,
            "base_score": self.base_score,
            "all_played_cards": self.all_played_cards,
            "show_cards_players": dict(self.show_cards_players),
            "auto_play_players": list(self.auto_play_players),
            "play_mode": self.play_mode,
            "scores": dict(self.scores),
            "bean_balances": dict(self.bean_balances),
            "cumulative_bean_changes": dict(self.cumulative_bean_changes),
        }
        # 地主确定后且非叫地主阶段才公开底牌，否则为 []
        if is_landlord_decided:
            view["bottom_cards"] = self.bottom_cards
        else:
            view["bottom_cards"] = []
        return view
