# backend/app/domain/game/room.py
"""游戏房间状态机：管理一局斗地主的完整生命周期"""
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any
from app.domain.game.card import shuffle_and_deal, sort_cards, Card
from app.domain.game.card_type import detect_card_type, can_beat, CardPlay


class GamePhase(Enum):
    MATCHING = "MATCHING"
    DEALING = "DEALING"
    CALLING = "CALLING"
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

    def __init__(self):
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
        self.redeal_count: int = 0
        self.created_at: str = ""
        self.base_score: int = 10
        self.all_played_cards: List[int] = []
        self.play_history: List[Dict[str, Any]] = []

        # 叫地主状态
        self._call_index: int = 0       # 当前叫地主的玩家索引
        self._call_scores: Dict[str, int] = {}  # 每个玩家的叫分 (0=不叫)
        self._first_caller_index: int = 0  # 首位叫牌者索引
        self._call_round: int = 1        # 当前圈数 (1=第一圈, 2=第二圈)
        self._first_bidder: Optional[str] = None  # 首位叫地主的玩家 ID

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
        h1, h2, h3, bottom = shuffle_and_deal()
        ids = self._player_ids()
        self.hands = {ids[0]: h1, ids[1]: h2, ids[2]: h3}
        self.bottom_cards = bottom
        self.phase = GamePhase.CALLING
        self.landlord = None
        self.last_play = LastPlay()
        self.pass_count = 0
        self.all_played_cards = []
        self.play_history = []
        self._call_index = 0
        self._call_scores = {}
        self._call_round = 1
        self._first_bidder = None
        # 随机选择首位叫牌者 (使用第一个玩家索引)
        import random
        self._first_caller_index = random.randint(0, 2)
        self._call_index = self._first_caller_index
        self.current_turn = ids[self._first_caller_index]
        self.turn_deadline = time.time() + 15
        return dict(self.hands)

    # ── 叫地主 ──

    def call_landlord(self, player_id: str, score: int) -> dict:
        """玩家叫地主 (score: 1/2/3)"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前不在叫地主阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}
        if score < 1 or score > 3:
            return {"success": False, "error": "叫分必须在1~3之间"}

        if self._call_round == 1:
            # 叫分必须高于已有最高分
            current_max = max(self._call_scores.values()) if self._call_scores else 0
            if score <= current_max:
                return {"success": False, "error": f"叫分必须高于当前最高分 {current_max}"}

            self._call_scores[player_id] = score
            self.multiplier = score

            if self._first_bidder is None:
                self._first_bidder = player_id

            # 第一圈叫3分直接成为地主
            if score == 3:
                return self._set_landlord(player_id)

            # 继续轮转
            return self._advance_call()
        else:
            # 第二圈抢地主
            if player_id != self._first_bidder:
                return {"success": False, "error": "非首位叫地主玩家在第二圈不能抢地主"}

            self._call_scores[player_id] = score
            self.multiplier *= 2
            return self._set_landlord(player_id)

    def skip_call(self, player_id: str) -> dict:
        """玩家不叫/不抢"""
        if self.phase != GamePhase.CALLING:
            return {"success": False, "error": "当前不在叫地主阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        if self._call_round == 1:
            self._call_scores[player_id] = 0
            return self._advance_call()
        else:
            # 第二圈不抢
            if player_id != self._first_bidder:
                return {"success": False, "error": "非首位叫地主玩家在第二圈不能选择不抢"}

            self._call_scores[player_id] = 0
            # 找到第一圈除了首叫者之外叫分最高的玩家
            candidates = {pid: s for pid, s in self._call_scores.items() if pid != self._first_bidder and s > 0}
            if not candidates:
                winner = self._first_bidder
            else:
                winner = max(candidates, key=candidates.get)
            return self._set_landlord(winner)

    def _advance_call(self) -> dict:
        """推进叫地主流程"""
        ids = self._player_ids()
        
        if self._call_round == 1:
            # 检查是否所有人都叫过了（即第一圈是否结束）
            if len(self._call_scores) >= 3:
                called_players = [pid for pid, s in self._call_scores.items() if s > 0]
                
                if len(called_players) == 0:
                    # 所有人都不叫，重新发牌
                    self.redeal_count += 1
                    if self.redeal_count >= self.MAX_REDEAL:
                        # 超过重发次数，随机指定地主
                        import random
                        forced = random.choice(ids)
                        self.multiplier = 1
                        return self._set_landlord(forced)
                    self.phase = GamePhase.DEALING
                    return {"success": True, "redeal": True}
                
                elif len(called_players) == 1:
                    # 只有 1 人叫分，直接成为地主
                    return self._set_landlord(called_players[0])
                
                else:
                    # 有 2 人或 3 人叫分，进入第二圈抢地主，轮到首叫者表态
                    self._call_round = 2
                    self.current_turn = self._first_bidder
                    self._call_index = ids.index(self._first_bidder)
                    self.turn_deadline = time.time() + 15
                    return {"success": True, "next_caller": self.current_turn, "call_round": 2}
            
            # 第一圈还没结束，轮到下一个
            self._call_index = (self._call_index + 1) % 3
            self.current_turn = ids[self._call_index]
            self.turn_deadline = time.time() + 15
            return {"success": True, "next_caller": self.current_turn}

    def _set_landlord(self, player_id: str) -> dict:
        """确定地主，分配底牌，进入出牌阶段"""
        self.landlord = player_id
        # 底牌给地主
        self.hands[player_id] = sort_cards(self.hands[player_id] + self.bottom_cards)
        self.phase = GamePhase.PLAYING
        self.current_turn = player_id  # 地主先出
        self.turn_deadline = time.time() + 15
        self.last_play = LastPlay()
        self.pass_count = 0
        return {
            "success": True,
            "landlord": player_id,
            "bottom_cards": self.bottom_cards,
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
        play = detect_card_type(card_ids)
        if play is None:
            return {"success": False, "error": "不合法的牌型"}

        # 如果有上家出牌，必须压过
        if self.last_play.card_play is not None:
            if not can_beat(play, self.last_play.card_play):
                return {"success": False, "error": "出的牌压不过上家"}

        # 炸弹/王炸翻倍
        from app.domain.game.card_type import CardType
        if play.card_type in (CardType.BOMB, CardType.ROCKET):
            self.multiplier *= 2

        # 从手牌中移除
        new_hand = list(hand)
        for cid in card_ids:
            new_hand.remove(cid)
        self.hands[player_id] = new_hand
        self.all_played_cards.extend(card_ids)

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

    def pass_turn(self, player_id: str) -> dict:
        """玩家不出（过）"""
        if self.phase != GamePhase.PLAYING:
            return {"success": False, "error": "当前不在出牌阶段"}
        if player_id != self.current_turn:
            return {"success": False, "error": "不是你的回合"}

        # 新一轮的首位出牌者不能不出
        if self.last_play.player is None:
            return {"success": False, "error": "新一轮必须出牌"}

        self.pass_count += 1
        self.play_history.append({"player": player_id, "cards": []})

        # 如果连续2人不出，最后出牌的人获得新一轮主导权
        if self.pass_count >= 2:
            self.current_turn = self.last_play.player
            self.last_play = LastPlay()  # 清空上家，新一轮
            self.pass_count = 0
            self.turn_deadline = time.time() + 15
            return {"success": True, "new_round": True, "next_turn": self.current_turn}

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

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为可存入 Redis 的 dict"""
        return {
            "room_id": self.room_id,
            "phase": self.phase.value,
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
            "redeal_count": self.redeal_count,
            "created_at": self.created_at,
            "call_index": self._call_index,
            "call_scores": self._call_scores,
            "first_caller_index": self._first_caller_index,
            "call_round": self._call_round,
            "first_bidder": self._first_bidder,
            "base_score": self.base_score,
            "all_played_cards": self.all_played_cards,
            "play_history": self.play_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameRoom":
        """从 dict 反序列化"""
        room = cls()
        room.room_id = data["room_id"]
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
            room.last_play.card_play = detect_card_type(room.last_play.cards)
        room.pass_count = data.get("pass_count", 0)
        room.multiplier = data.get("multiplier", 1)
        room.redeal_count = data.get("redeal_count", 0)
        room.created_at = data.get("created_at", "")
        room._call_index = data.get("call_index", 0)
        room._call_scores = data.get("call_scores", {})
        room._first_caller_index = data.get("first_caller_index", 0)
        room._call_round = data.get("call_round", 1)
        room._first_bidder = data.get("first_bidder")
        room.base_score = data.get("base_score", 10)
        room.all_played_cards = data.get("all_played_cards", [])
        room.play_history = data.get("play_history", [])
        return room

    def get_player_view(self, player_id: str) -> dict:
        """获取特定玩家可见的房间状态（隐藏他人手牌）"""
        players_view = []
        for p in self.players:
            pv = {"id": p.id, "nickname": p.nickname, "is_ai": p.is_ai, "is_online": p.is_online}
            if p.id == player_id:
                pv["is_self"] = True
            else:
                pv["remaining"] = len(self.hands.get(p.id, []))
            if self.landlord:
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
            "call_round": self._call_round,
            "call_scores": dict(self._call_scores),
            "first_bidder": self._first_bidder,
            "landlord": self.landlord,
            "base_score": self.base_score,
            "all_played_cards": self.all_played_cards,
        }
        # 地主确定后才公开底牌
        if self.landlord:
            view["bottom_cards"] = self.bottom_cards
        return view
