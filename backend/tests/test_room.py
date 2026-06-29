# backend/tests/test_room.py
import pytest
from app.domain.game.room import GameRoom, GamePhase, Player


def make_players():
    return [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="机器人", is_ai=True, is_online=True),
    ]


class TestGameRoom:

    def test_create_room(self):
        """创建房间后状态应为 DEALING"""
        room = GameRoom.create("room_1", make_players())
        assert room.room_id == "room_1"
        assert room.phase == GamePhase.DEALING
        assert len(room.players) == 3

    def test_deal(self):
        """发牌后每人17张，底牌3张，状态变为 CALLING"""
        room = GameRoom.create("room_1", make_players())
        hands = room.deal()
        assert room.phase == GamePhase.CALLING
        for pid in ["p1", "p2", "p3"]:
            assert len(room.hands[pid]) == 17
        assert len(room.bottom_cards) == 3

    def test_call_landlord(self):
        """叫3分直接成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        result = room.call_landlord(caller, 3)
        assert room.phase == GamePhase.PLAYING
        assert room.landlord == caller
        assert room.multiplier == 3
        # 地主应该有20张牌
        assert len(room.hands[caller]) == 20

    def test_skip_call_all(self):
        """三人都不叫，应重新发牌"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        for _ in range(3):
            pid = room.current_turn
            result = room.skip_call(pid)
        # 应该重新发牌或标记重发
        assert result.get("redeal") is True or room.phase == GamePhase.DEALING

    def test_play_cards_valid(self):
        """出合法的牌应成功"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        # 直接叫3分成为地主
        caller = room.current_turn
        room.call_landlord(caller, 3)
        # 地主出牌（出最小的一张）
        landlord = room.landlord
        card_to_play = [room.hands[landlord][0]]
        result = room.play_cards(landlord, card_to_play)
        assert result["success"] is True
        assert card_to_play[0] not in room.hands[landlord]

    def test_play_cards_not_your_turn(self):
        """不是你的回合不能出牌"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        room.call_landlord(caller, 3)
        # 尝试让非当前回合玩家出牌
        other = [p for p in ["p1", "p2", "p3"] if p != room.current_turn][0]
        result = room.play_cards(other, [room.hands[other][0]])
        assert result["success"] is False

    def test_serialization(self):
        """序列化/反序列化应保持状态一致"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        data = room.to_dict()
        restored = GameRoom.from_dict(data)
        assert restored.room_id == room.room_id
        assert restored.phase == room.phase
        assert restored.hands == room.hands

    def test_player_view_hides_others_hands(self):
        """玩家视图不应包含其他人的手牌"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        view = room.get_player_view("p1")
        assert "hand" in view  # 自己的手牌
        for p in view["players"]:
            if p["id"] != "p1":
                assert "hand" not in p  # 不应有其他人手牌
                assert "remaining" in p  # 应有剩余牌数
        assert "call_scores" in view
        assert "first_bidder" in view

    def test_single_bidder_becomes_landlord(self):
        """只有1人叫分，该人直接成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        
        # 让第一个人叫 1 分，其他人不叫
        p1 = room.current_turn
        room.call_landlord(p1, 1)
        
        p2 = room.current_turn
        room.skip_call(p2)
        
        p3 = room.current_turn
        result = room.skip_call(p3)
        
        assert room.phase == GamePhase.PLAYING
        assert room.landlord == p1
        assert room.multiplier == 1

    def test_two_round_bidding_flow(self):
        """两圈抢地主流：首叫者叫1，下家抢2，下下家不抢，第二圈首叫者抢则成为地主且倍数翻倍"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # 第一圈：
        room.call_landlord(ids[0], 1)
        room.call_landlord(ids[1], 2)
        room.skip_call(ids[2])
        
        # 此时应该进入第二圈，轮到首叫者 ids[0]
        assert room._call_round == 2
        assert room.current_turn == ids[0]
        
        # 首叫者 ids[0] 选择抢，直接成为地主且 multiplier 翻倍 (2 * 2 = 4)
        result = room.call_landlord(ids[0], 3)
        assert room.phase == GamePhase.PLAYING
        assert room.landlord == ids[0]
        assert room.multiplier == 4

    def test_two_round_bidding_skip(self):
        """两圈抢地主流：首叫者不抢，则最高分者成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # 第一圈：
        room.call_landlord(ids[0], 1)
        room.call_landlord(ids[1], 2)
        room.skip_call(ids[2])
        
        # 第二圈首叫者 ids[0] 不抢 -> ids[1] (叫2分的) 成为地主
        room.skip_call(ids[0])
        assert room.phase == GamePhase.PLAYING
        assert room.landlord == ids[1]
        assert room.multiplier == 2
