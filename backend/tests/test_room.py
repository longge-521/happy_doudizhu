# backend/tests/test_room.py
import pytest
from app.domain.game.room import GameRoom, GamePhase, Player


def make_players():
    return [
        Player(id="p1", nickname="玩家1", is_ai=False, is_online=True),
        Player(id="p2", nickname="玩家2", is_ai=False, is_online=True),
        Player(id="p3", nickname="机器人", is_ai=True, is_online=True),
    ]


def choose_no_doubles(room):
    for player in room.players:
        room.choose_double(player.id, "none")


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
        """模拟设置地主，进入加倍阶段"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        result = room._set_landlord(caller)
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == caller
        assert room.multiplier == 1
        # 地主应该有20张牌
        assert len(room.hands[caller]) == 20
        choose_no_doubles(room)
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == caller

    def test_landlord_decided_enters_doubling_phase(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn

        result = room._set_landlord(caller)

        assert result["success"] is True
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == caller
        assert room.current_turn is None
        assert room.doubling_choices == {}
        assert len(room.hands[caller]) == 20

    def test_double_choices_update_multiplier_and_finish_to_playing(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        room._set_landlord(ids[0])

        first = room.choose_double(ids[0], "double")
        second = room.choose_double(ids[1], "super")
        third = room.choose_double(ids[2], "none")

        assert first["success"] is True
        assert second["success"] is True
        assert third["success"] is True
        assert third["doubling_finished"] is True
        assert room.doubling_choices == {
            ids[0]: "double",
            ids[1]: "super",
            ids[2]: "none",
        }
        assert room.multiplier == 8
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == ids[0]

    def test_cannot_play_before_all_players_choose_double(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        room._set_landlord(caller)

        result = room.play_cards(caller, [room.hands[caller][0]])

        assert result["success"] is False
        assert "出牌" in result["error"] or "阶段" in result["error"]

    def test_cannot_choose_double_twice_or_with_invalid_choice(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        caller = room.current_turn
        room._set_landlord(caller)

        first = room.choose_double(caller, "double")
        repeat = room.choose_double(caller, "none")
        invalid = room.choose_double(room.current_turn or caller, "bad")

        assert first["success"] is True
        assert repeat["success"] is False
        assert invalid["success"] is False

    def test_doubling_choices_are_serialized_and_visible(self):
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        room._set_landlord(ids[0])
        room.choose_double(ids[0], "double")

        restored = GameRoom.from_dict(room.to_dict())
        view = restored.get_player_view(ids[1])

        assert restored.doubling_choices == {ids[0]: "double"}
        assert view["doubling_choices"] == {ids[0]: "double"}

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
        # 直接模拟成为地主
        caller = room.current_turn
        room._set_landlord(caller)
        choose_no_doubles(room)
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
        room._set_landlord(caller)
        choose_no_doubles(room)
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
        """只有 1 人叫地主，其他人都不抢，该人直接成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        p1 = room.current_turn
        room.call_landlord(p1, 1)
        p2 = room.current_turn
        room.skip_call(p2)
        p3 = room.current_turn
        room.skip_call(p3)

        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == p1
        assert room.multiplier == 1
        choose_no_doubles(room)
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == p1

    def test_two_round_bidding_flow(self):
        """抢地主流：首叫者叫地主，下家抢地主，下下家不抢，首叫者再抢"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # ids[0] 叫地主
        room.call_landlord(ids[0], 1)
        assert room.multiplier == 1
        
        # ids[1] 抢地主
        room.call_landlord(ids[1], 1)
        assert room.multiplier == 2
        assert room.landlord == ids[1]
        
        # ids[2] 不抢
        room.skip_call(ids[2])
        assert room.current_turn == ids[0]  # 轮回到首叫者 ids[0]
        
        # ids[0] 选择抢地主
        room.call_landlord(ids[0], 1)
        
        # 表态结束，ids[0] 成为地主，倍数翻倍为 4
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == ids[0]
        assert room.multiplier == 4
        choose_no_doubles(room)
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == ids[0]

    def test_two_round_bidding_skip_first_then_next(self):
        """抢地主流：首叫者不抢，下表态者成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # ids[0] 叫地主
        room.call_landlord(ids[0], 1)
        
        # ids[1] 抢地主
        room.call_landlord(ids[1], 1)
        
        # ids[2] 不抢
        room.skip_call(ids[2])
        
        # ids[0] 不抢
        room.skip_call(ids[0])
        
        # 表态结束，ids[1] 获得地主，倍数为 2
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == ids[1]
        assert room.multiplier == 2
        choose_no_doubles(room)
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == ids[1]

    def test_skip_then_call_flow(self):
        """首叫者不叫，下家叫地主，下下家不抢，下家直接成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # ids[0] 不叫
        room.skip_call(ids[0])
        
        # ids[1] 叫地主
        room.call_landlord(ids[1], 1)
        assert room.multiplier == 1
        assert room.landlord == ids[1]
        
        # ids[2] 不抢
        room.skip_call(ids[2])
        
        # 表态结束，因为 ids[0] 之前不叫，无权再抢。所以地主直接归 ids[1]
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == ids[1]
        assert room.multiplier == 1
        choose_no_doubles(room)
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == ids[1]

    def test_two_round_bidding_skip(self):
        """两圈抢地主流：首叫者不抢且只剩他自己（下一个立刻结束），最高分者成为地主"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # 第一圈：只有 ids[0] 叫分，其他人不叫（单独叫分，直接成地主，不进入第二圈）
        room.call_landlord(ids[0], 1)
        room.skip_call(ids[1])
        result = room.skip_call(ids[2])

        # 只有 1 人叫分，直接成为地主
        assert room.phase == GamePhase.DOUBLING
        assert room.landlord == ids[0]
        assert room.multiplier == 1
        choose_no_doubles(room)
        assert room.phase == GamePhase.PLAYING
        assert room.current_turn == ids[0]

    def test_bottom_cards_and_landlord_status_hidden_during_calling(self):
        """在叫牌（CALLING）阶段，即使有暂定地主，底牌和 is_landlord 仍需隐藏"""
        room = GameRoom.create("room_1", make_players())
        room.deal()
        ids = [p.id for p in room.players]
        # 重置首叫者为 ids[0] 以消除随机性
        room._first_caller_index = 0
        room._call_index = 0
        room.current_turn = ids[0]
        
        # 1. 叫地主前，底牌为空，所有人不显示 is_landlord
        view = room.get_player_view(ids[0])
        assert view["bottom_cards"] == []
        for p in view["players"]:
            assert "is_landlord" not in p
            
        # 2. 玩家1叫地主，成为暂定地主
        room.call_landlord(ids[0], 1)
        assert room.landlord == ids[0]
        assert room.phase == GamePhase.CALLING
        
        # 3. 再次获取视角，底牌和 is_landlord 应继续隐藏
        view = room.get_player_view(ids[0])
        assert view["bottom_cards"] == []
        for p in view["players"]:
            assert "is_landlord" not in p

        # 4. 其它玩家选择 skip，确认地主并进入下一阶段
        room.skip_call(ids[1])
        room.skip_call(ids[2])
        assert room.phase == GamePhase.DOUBLING
        
        # 5. 此时进入 DOUBLING 阶段，底牌应公开，玩家1的 is_landlord 为 True，其它为 False
        view = room.get_player_view(ids[0])
        assert view["bottom_cards"] == room.bottom_cards
        for p in view["players"]:
            if p["id"] == ids[0]:
                assert p["is_landlord"] is True
            else:
                assert p["is_landlord"] is False
