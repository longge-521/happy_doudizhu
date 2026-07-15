# backend/tests/test_fifty_k.py
import pytest
from app.domain.game.card_type import detect_card_type, can_beat, CardType
from app.domain.game.room import GameRoom, Player, GamePhase

def test_fifty_k_card_detection():
    # ♠5 (ID=8), ♠10 (ID=28), ♠K (ID=40)
    true_fifty_k = detect_card_type([8, 28, 40], play_mode="fifty_k")
    assert true_fifty_k is not None
    assert true_fifty_k.card_type == CardType.FIFTY_K_TRUE

    # ♥5 (ID=9), ♦10 (ID=31), ♣K (ID=42)
    false_fifty_k = detect_card_type([9, 31, 42], play_mode="fifty_k")
    assert false_fifty_k is not None
    assert false_fifty_k.card_type == CardType.FIFTY_K_FALSE

def test_fifty_k_can_beat():
    # 我们先在测试逻辑中防范如果还未实现，detect_card_type 可能返回 None
    true_play = detect_card_type([8, 28, 40], play_mode="fifty_k")
    false_play = detect_card_type([9, 31, 42], play_mode="fifty_k")
    single_play = detect_card_type([0], play_mode="fifty_k")  # 单张3
    bomb_play = detect_card_type([0, 1, 2, 3], play_mode="fifty_k")  # 3333 炸弹

    # 验证压制关系：
    # 假510K大过单张
    assert can_beat(false_play, single_play, play_mode="fifty_k")
    # 真510K大过假510K
    assert can_beat(true_play, false_play, play_mode="fifty_k")
    # 真510K大过炸弹
    assert can_beat(true_play, bomb_play, play_mode="fifty_k")
    # 炸弹大过假510K
    assert can_beat(bomb_play, false_play, play_mode="fifty_k")
    # 假510K压不过炸弹
    assert not can_beat(false_play, bomb_play, play_mode="fifty_k")


def test_fifty_k_rules_do_not_leak_into_classic_mode():
    assert detect_card_type([8, 28, 40], play_mode="classic") is None


def test_fifty_k_score_values_and_room_round_trip():
    players = [
        Player(id="p1", nickname="Player1"),
        Player(id="p2", nickname="Player2"),
        Player(id="p3", nickname="Player3"),
    ]
    room = GameRoom.create("room_round_trip", players, base_score=80)
    room.play_mode = "fifty_k"

    assert room._get_card_score(8) == 5
    assert room._get_card_score(28) == 10
    assert room._get_card_score(40) == 20
    assert sum(room._get_card_score(card_id) for card_id in range(54)) == 140

    room.scores = {"p1": 35, "p2": 0, "p3": 0}
    room.current_trick_cards = [8, 28, 40]
    room.trick_no = 3
    room.cumulative_bean_changes = {"p1": 5600, "p2": -2800, "p3": -2800}
    room.bean_balances = {"p1": 15600, "p2": 7200, "p3": 7200}
    room.player_triggered_boost = {"p1"}

    restored = GameRoom.from_dict(room.to_dict())

    assert restored.scores == room.scores
    assert restored.current_trick_cards == room.current_trick_cards
    assert restored.trick_no == room.trick_no
    assert restored.cumulative_bean_changes == room.cumulative_bean_changes
    assert restored.bean_balances == room.bean_balances
    assert restored.player_triggered_boost == room.player_triggered_boost

def test_fifty_k_deal_and_first_turn(monkeypatch):
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    def deal_club_three_to_p1_and_spade_three_to_p2(deck):
        deck[0], deck[18] = deck[18], deck[0]

    monkeypatch.setattr("random.shuffle", deal_club_three_to_p1_and_spade_three_to_p2)
    hands = room.deal()
    assert len(room.bottom_cards) == 0
    assert len(hands["p1"]) == 18
    assert len(hands["p2"]) == 18
    assert len(hands["p3"]) == 18
    assert room.phase == GamePhase.PLAYING

    # 找出包含 2（梅花3）的玩家 ID，验证该 ID 等于 room.current_turn
    club_3_player = None
    for pid, hand in hands.items():
        if 2 in hand:
            club_3_player = pid
            break
    assert club_3_player is not None
    assert room.current_turn == club_3_player


@pytest.mark.asyncio
async def test_fifty_k_trick_settle_realtime_bean_update():
    from unittest.mock import AsyncMock, patch, MagicMock

    # 1. 验证房间状态机的分牌吃分
    p1 = Player(id="p1", nickname="Player1", is_ai=False)
    p2 = Player(id="p2", nickname="Player2", is_ai=False)
    p3 = Player(id="p3", nickname="Player3", is_ai=False)
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"
    room.phase = GamePhase.PLAYING
    room.hands = {"p1": [8, 28, 40, 1, 2], "p2": [0], "p3": [4]}
    room.scores = {"p1": 0, "p2": 0, "p3": 0}
    room.current_turn = "p1"
    
    # 模拟出牌 ♠5 (8), ♠10 (28), ♠K (40)
    res1 = room.play_cards("p1", [8, 28, 40])
    assert res1["success"] is True
    
    # 模拟过牌1
    res2 = room.pass_turn("p2")
    assert res2["success"] is True
    
    # 模拟过牌2（此时触发一轮结束）
    res3 = room.pass_turn("p3")
    assert res3["success"] is True
    
    # 验证大住结算
    assert room.pass_count == 0
    assert room.scores["p1"] == 35
    assert "trick_settlement" in res3
    assert res3["trick_settlement"]["winner_id"] == "p1"
    assert res3["trick_settlement"]["score_gained"] == 35
    assert res3["trick_settlement"]["trick_cards"] == [8, 28, 40]

    # 2. 验证 GameAppService 里的金豆划拨与广播
    from app.application.game.game_app_service import GameAppService
    
    mock_repo = AsyncMock()
    mock_repo.get_player_room.return_value = "room_test"
    mock_repo.get_room.return_value = room
    
    # 重置 room 状态以进行第二次测试
    room.hands = {"p1": [8, 28, 40, 1, 2], "p2": [0], "p3": [4]}
    room.scores = {"p1": 0, "p2": 0, "p3": 0}
    room.current_trick_cards = []
    # 重置 last_play
    from app.domain.game.room import LastPlay
    room.last_play = LastPlay()
    room.pass_count = 0
    room.current_turn = "p1"
    
    service = GameAppService(mock_repo)
    service._settlement_service = MagicMock()
    service._settlement_service.settle_fifty_k_trick.return_value = {
        "status": "completed",
        "bean_changes": {"p1": 250, "p2": -125, "p3": -125},
        "bean_balances": {"p1": 10250, "p2": 9875, "p3": 9875},
    }

    with patch("app.infrastructure.config.settings.DISTRIBUTED_MODE", False):
            # p1 出牌
            res_play = await service.handle_play("p1", [8, 28, 40])
            assert res_play["success"] is True
            
            # p2 过牌
            res_pass1 = await service.handle_pass("p2")
            assert res_pass1["success"] is True
            
            # p3 过牌 (本轮结束，大住吃分)
            res_pass2 = await service.handle_pass("p3")
            assert res_pass2["success"] is True
            
            # 确认返回结果中包含事件广播包
            assert "trick_settlement_event" in res_pass2
            evt = res_pass2["trick_settlement_event"]
            assert evt["event"] == "trick_settled"
            assert evt["winner_id"] == "p1"
            assert evt["score_gained"] == 35
            assert evt["bean_changes"]["p1"] == 250
            assert evt["bean_changes"]["p2"] == -125
            assert evt["bean_changes"]["p3"] == -125


@pytest.mark.asyncio
async def test_fifty_k_game_over_harvest():
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.application.game.game_app_service import GameAppService
    
    p1 = Player(id="p1", nickname="Player1", is_ai=False)
    p2 = Player(id="p2", nickname="Player2", is_ai=False)
    p3 = Player(id="p3", nickname="Player3", is_ai=False)
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"
    room.phase = GamePhase.PLAYING
    
    # 1. 验证 Domain 层的结算与分牌收割
    room.hands = {"p1": [4], "p2": [8], "p3": [28]}
    room.scores = {"p1": 50, "p2": 30, "p3": 5}
    room.current_turn = "p1"
    
    # A 出最后一张牌 [4]
    res = room.play_cards("p1", [4])
    assert res["success"] is True
    
    # 验证房间状态切换为 GamePhase.SETTLING
    assert room.phase == GamePhase.SETTLING
    
    # 调用 room.settle() 触发结算
    settlement = room.settle()
    
    # 验证最终局内积分：
    # A 的最终积分为 65 (50 + 15)
    # 输家保留此前已吃到的历史积分。
    assert room.scores["p1"] == 65
    assert room.scores["p2"] == 30
    assert room.scores["p3"] == 5
    
    assert "fifty_k_settlement" in settlement
    fk_settle = settlement["fifty_k_settlement"]
    assert fk_settle["winner_id"] == "p1"
    assert fk_settle["harvested_scores"]["p1"] == 15
    assert fk_settle["harvested_scores"]["p2"] == -5
    assert fk_settle["harvested_scores"]["p3"] == -10
    assert fk_settle["penalty_adjusted_scores"] == {
        "p1": 65,
        "p2": 25,
        "p3": -5,
    }

    # 2. 验证 GameAppService 里的金豆收割、排位星数结算与广播
    # 重新初始化 room 为出牌前状态
    from app.domain.game.room import LastPlay
    room.last_play = LastPlay()
    room.phase = GamePhase.PLAYING
    room.hands = {"p1": [4], "p2": [8], "p3": [28]}
    room.scores = {"p1": 50, "p2": 30, "p3": 5}
    room.current_turn = "p1"
    room.player_triggered_boost = set() # 没有触发爆发
    
    mock_repo = AsyncMock()
    mock_repo.get_player_room.return_value = "room_test"
    mock_repo.get_room.return_value = room
    
    service = GameAppService(mock_repo)

    with patch("app.infrastructure.config.settings.DISTRIBUTED_MODE", False):
            # p1 出牌 [4]
            res_play = await service.handle_play("p1", [4])
            assert res_play["success"] is True
            assert res_play.get("game_over") is True
            assert res_play["winner"] == "p1"
            
            fk_result = res_play["fifty_k_settlement"]
            assert fk_result["finish_base_changes"] == {
                "p1": 9000,
                "p2": -4500,
                "p3": -4500,
            }
            assert fk_result["remaining_card_changes"] == {
                "p1": 150,
                "p2": -50,
                "p3": -100,
            }

            # 再次测试爆发性胜利结算
            # 重新初始化 room 并更改 room_id 避免并发防重拦截
            room.room_id = "room_test_boost"
            room.last_play = LastPlay()
            room.phase = GamePhase.PLAYING
            room.hands = {"p1": [4], "p2": [8], "p3": [28]}
            room.scores = {"p1": 50, "p2": 30, "p3": 5}
            room.current_turn = "p1"
            room.player_triggered_boost = {"p1"} # 爆发胜利
            
            # 再次出牌
            res_play_boost = await service.handle_play("p1", [4])
            assert res_play_boost["success"] is True
            assert res_play_boost["multiplier"] == room.multiplier


def test_fifty_k_ai_strategy_decomposition():
    from app.domain.game.ai_strategy import _decompose_hand
    # ♠5 (8), ♠10 (28), ♠K (40) -> 真510K
    hand_true = [8, 28, 40, 4]  # 加一张 4 凑牌
    plan_true = _decompose_hand(hand_true, play_mode="fifty_k")
    # 验证 bombs 里有该真五十K牌型
    assert len(plan_true.bombs) == 1
    assert plan_true.bombs[0].card_type == CardType.FIFTY_K_TRUE

    # ♥5 (9), ♦10 (31), ♣K (42) -> 假510K
    hand_false = [9, 31, 42, 4]
    plan_false = _decompose_hand(hand_false, play_mode="fifty_k")
    assert len(plan_false.bombs) == 1
    assert plan_false.bombs[0].card_type == CardType.FIFTY_K_FALSE


def test_fifty_k_ai_candidates_use_rule_strategy_and_return_legal_actions():
    from app.domain.game.ai_strategy import AIContext, ai_rank_play_candidates

    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=4, teammate_remaining=0, last_play_from=None,
        is_last_play_teammate=False, is_last_play_landlord=False,
        play_mode="fifty_k",
    )
    candidates = ai_rank_play_candidates([8, 28, 40, 0], None, True, ctx)

    assert candidates
    assert all(detect_card_type(cards, play_mode="fifty_k") for cards in candidates)


def test_fifty_k_ai_follows_single_five_when_higher_single_exists():
    from app.domain.game.ai_strategy import AIContext, ai_rank_play_candidates

    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=12, teammate_remaining=0, last_play_from="p2",
        is_last_play_teammate=False, is_last_play_landlord=False,
        play_mode="fifty_k",
    )
    last_play = detect_card_type([8], play_mode="fifty_k")

    candidates = ai_rank_play_candidates(
        [12, 40],
        last_play,
        False,
        ctx,
    )

    assert candidates[0] == [12]


def test_fifty_k_ai_uses_smallest_special_layer_when_following_false_510k():
    from app.domain.game.ai_strategy import AIContext, ai_rank_play_candidates

    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=5, teammate_remaining=0, last_play_from="p2",
        is_last_play_teammate=False, is_last_play_landlord=False,
        play_mode="fifty_k",
    )
    last_play = detect_card_type([9, 30, 43], play_mode="fifty_k")

    candidates = ai_rank_play_candidates(
        [0, 1, 2, 3, 12],
        last_play,
        False,
        ctx,
    )

    assert set(candidates[0]) == {0, 1, 2, 3}


def test_fifty_k_ai_lead_keeps_a_complete_straight():
    from app.domain.game.ai_strategy import AIContext, ai_rank_play_candidates

    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=6, teammate_remaining=0, last_play_from=None,
        is_last_play_teammate=False, is_last_play_landlord=False,
        play_mode="fifty_k",
    )

    candidates = ai_rank_play_candidates([0, 4, 8, 12, 16, 40], None, True, ctx)

    assert candidates[0] == [0, 4, 8, 12, 16]


def test_fifty_k_ai_lead_keeps_control_cards_and_sheds_small_junk_single():
    from app.domain.game.ai_strategy import AIContext, ai_rank_play_candidates

    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=3, teammate_remaining=0, last_play_from=None,
        is_last_play_teammate=False, is_last_play_landlord=False,
        play_mode="fifty_k",
        other_players_min_remaining=4,
    )

    candidates = ai_rank_play_candidates([0, 28, 48], None, True, ctx)

    assert candidates[0] == [0]


def test_fifty_k_ai_leads_triple_with_small_single_before_large_pair():
    from app.domain.game.ai_strategy import (
        AIContext,
        _rank_fifty_k_rule_actions,
        generate_legal_actions_dz,
    )

    hand = [4, 5, 6, 0, 44, 45]  # 444、单3、对A
    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=len(hand), teammate_remaining=0,
        last_play_from=None, is_last_play_teammate=False,
        is_last_play_landlord=False, play_mode="fifty_k",
        other_players_min_remaining=10,
    )
    actions = generate_legal_actions_dz(hand, None, True, play_mode="fifty_k")

    ranked = _rank_fifty_k_rule_actions(hand, actions, None, ctx)

    assert set(ranked[0]) == {0, 4, 5, 6}


def test_fifty_k_ai_does_not_lead_four_k_with_two_large_pairs_when_not_running_out():
    from app.domain.game.ai_strategy import (
        AIContext,
        _rank_fifty_k_rule_actions,
        generate_legal_actions_dz,
    )
    from app.domain.game.card_type import CardType, detect_card_type

    hand = [40, 41, 42, 43, 44, 45, 48, 49, 0]  # K炸、对A、对2、单3
    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=len(hand), teammate_remaining=0,
        last_play_from=None, is_last_play_teammate=False,
        is_last_play_landlord=False, play_mode="fifty_k",
        other_players_min_remaining=10,
    )
    actions = generate_legal_actions_dz(hand, None, True, play_mode="fifty_k")

    ranked = _rank_fifty_k_rule_actions(hand, actions, None, ctx)
    first_play = detect_card_type(ranked[0], play_mode="fifty_k")

    assert first_play is not None
    assert first_play.card_type != CardType.FOUR_TWO_PAIR


def test_fifty_k_ai_follows_with_standalone_single_before_splitting_pair():
    from app.domain.game.ai_strategy import AIContext, ai_rank_play_candidates

    ctx = AIContext(
        ai_id="p1", role="landlord", landlord_id="p1", teammate_id=None,
        landlord_remaining=3, teammate_remaining=0, last_play_from="p2",
        is_last_play_teammate=False, is_last_play_landlord=False,
        play_mode="fifty_k",
    )

    candidates = ai_rank_play_candidates(
        [4, 5, 12], detect_card_type([0], play_mode="fifty_k"), False, ctx,
    )

    assert candidates[0] == [12]


def test_fifty_k_ai_context_exposes_only_visible_opponent_remaining_counts():
    from app.domain.game.ai_strategy import build_ai_context

    players = [Player(id="p1", nickname="Player1"), Player(id="p2", nickname="Player2"), Player(id="p3", nickname="Player3")]
    room = GameRoom.create("room_test", players, base_score=10)
    room.play_mode = "fifty_k"
    room.hands = {"p1": [0, 4, 8], "p2": [12], "p3": [16, 20]}

    ctx = build_ai_context(room, "p1")

    assert ctx.player_remaining == {"p1": 3, "p2": 1, "p3": 2}


def test_fifty_k_ai_play_route():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # 初始化手牌
    room.hands = {
        "p1": [8, 28, 40], # 真510K
        "p2": [0],
        "p3": [4]
    }
    
    # 验证上下文构造不会因 landlord_id 为 None 而崩溃
    ctx = build_ai_context(room, "p1")
    assert ctx.role == "landlord"  # 伪装地主以实施各自为战
    assert ctx.play_mode == "fifty_k"

    # 验证 AI 出牌决策不会报错，且在 must_play 下能正常出牌
    cards = ai_decide_play(room.hands["p1"], None, True, ctx)
    assert cards is not None
    # 规则 AI 应该首选打出真 510K 或者是其他合理牌型
    assert set(cards) == {8, 28, 40}


def test_fifty_k_pass_turn_self_healing():
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # 首出发牌，且 last_play 为空
    room.hands = {
        "p1": [8, 28, 40], # ♠5 (8), ♠10 (28), ♠K (40)
        "p2": [0],
        "p3": [4]
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 试图过牌 (pass_turn)
    res = room.pass_turn("p1")
    # 验证此时操作不仅没有返回“新一轮必须出牌”错误，还成功被自我修复为了出牌
    assert res["success"] is True
    # 检查打出的牌是 p1 最小的一张单牌，♠5 (card_id = 8)
    assert room.last_play.card_play is not None
    assert room.last_play.card_play.cards == [8]
    # 回合也已顺利前移至 p2
    assert room.current_turn == "p2"


def test_fifty_k_ai_lead_card_prefer_small():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI 手牌有：对3 (0, 1) 和 大王 (51, 即卡牌ID51对应的rank是14，2的ID是48,49,50,51是大王)
    # 大王 53 (card_id 53 是大王, 52是小王)
    # 对3: ♣3(0), ♦3(1)
    room.hands = {
        "p1": [0, 1, 48, 53], # ♣3(0), ♦3(1), ♣2(48), 大王(53)
        "p2": [4],
        "p3": [5]
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    ctx = build_ai_context(room, "p1")
    cards = ai_decide_play(room.hands["p1"], None, True, ctx)
    
    # 验证 AI 优先打出对 3 (cards = [0, 1])，而不是把 2 或大王首发出去
    assert cards is not None
    assert set(cards) == {0, 1}


def test_fifty_k_ai_follow_save_big_card():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 有 10 张牌：大单张 2 (card_id = 48), 大王 (53)，以及 8 张比 10 小的小牌 (对3, 对4, 对5, 对6)
    # 此时大家手牌还很多 (p2 有 10 张，p3 有 10 张)
    room.hands = {
        "p1": [48, 53, 0, 1, 4, 5, 8, 9, 12, 13],
        "p2": [0] * 10,
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 上家 p2 出了一个单张 10 (card_id = 28, rank = 7)
    from app.domain.game.card_type import detect_card_type
    p2_play = detect_card_type([28], play_mode="fifty_k") # 单张10
    room.last_play.player = "p2"
    room.last_play.card_play = p2_play

    ctx = build_ai_context(room, "p1")
    cards = ai_decide_play(room.hands["p1"], p2_play, False, ctx)

    # 验证 AI 会大方地用 2 压制上家的 10 抢回牌权，而不会降进选择 Pass 避战
    assert cards == [48]


def test_fifty_k_ai_zero_score_do_not_evade():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play

    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 有 6 张牌：常规压牌为单张 J (32, rank 8) 或 Q (36, rank 9)
    # 其它 4 张牌都是比 10 小的常规单张，如 3, 4, 5, 6
    room.hands = {
        "p1": [32, 36, 0, 4, 8, 12],  # J, Q, 3, 4, 5, 6 (长度6，无手牌数警报)
        "p2": [0] * 10,
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 上家 p2 出了单张 10 (card_id = 28, rank = 7)
    from app.domain.game.card_type import detect_card_type
    p2_play = detect_card_type([28], play_mode="fifty_k")
    room.last_play.player = "p2"
    room.last_play.card_play = p2_play

    # 桌面 0 分，无警报
    room.current_trick_cards = []

    ctx = build_ai_context(room, "p1")
    cards_play = ai_decide_play(room.hands["p1"], p2_play, False, ctx)
    assert cards_play is not None and len(cards_play) == 1
    assert cards_play[0] in [32, 36]


def test_fifty_k_ai_high_score_unlimit_big_cards():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    from app.domain.game.card_type import detect_card_type
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 有 6 张牌：2 (48, rank 12)，以及其它几张不能压单张 10 的小牌 (比如 3, 4, 5, 6, 7)
    room.hands = {
        "p1": [48, 0, 4, 8, 12, 16],  # 2, 3, 4, 5, 6, 7 (长度6，无警报)
        "p2": [0] * 10,
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 上家 p2 出了单张 10 (card_id = 28, rank = 7)
    p2_play = detect_card_type([28], play_mode="fifty_k")
    room.last_play.player = "p2"
    room.last_play.card_play = p2_play

    # 1. 即使是桌面低分 (0 分)，且没有警报，面对单张 10 这种大常规牌，AI 也应该用 2 压制以抢占出牌权
    room.current_trick_cards = []
    ctx = build_ai_context(room, "p1")
    cards_low = ai_decide_play(room.hands["p1"], p2_play, False, ctx)
    assert cards_low == [48]

    # 2. 桌面大分 (比如 20分，>= 15分)，AI 也直接用 2 压制
    room.current_trick_cards = [28, 29]  # 两个 10 共 20 分
    ctx = build_ai_context(room, "p1")
    cards_high = ai_decide_play(room.hands["p1"], p2_play, False, ctx)
    assert cards_high == [48]


def test_fifty_k_ai_uses_bomb_only_when_trick_value_justifies_it():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    from app.domain.game.card_type import detect_card_type
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 有炸弹 4444 (card_id = 4, 5, 6, 7) 和其它小单张
    room.hands = {
        "p1": [4, 5, 6, 7, 0, 8, 12, 16],  # 炸弹4，单张3, 5, 6, 7 (长度8，无警报)
        "p2": [0] * 10,
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 上家 p2 出了单张 10 (card_id = 28)
    p2_play = detect_card_type([28], play_mode="fifty_k")
    room.last_play.player = "p2"
    room.last_play.card_play = p2_play

    # 1. 桌面低分 (0 分)，且非封堵、非终局、非助攻队友，AI 不应当扔出炸弹
    room.current_trick_cards = []
    ctx = build_ai_context(room, "p1")
    cards_nobomb = ai_decide_play(room.hands["p1"], p2_play, False, ctx)
    assert cards_nobomb is None or cards_nobomb == []

    # 2. 桌面吃分累计 >= 10分 (比如 ♣10(28) 10分)，AI 强制使用炸弹压制抢分
    room.current_trick_cards = [28]  # 10 分
    ctx = build_ai_context(room, "p1")
    cards_bomb = ai_decide_play(room.hands["p1"], p2_play, False, ctx)
    assert cards_bomb is not None
    assert set(cards_bomb) == {4, 5, 6, 7}


def test_fifty_k_ai_evades_with_sole_fifty_k_bomb():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    from app.domain.game.card_type import detect_card_type
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 只有 3 张牌：5, 10, K (8, 29, 40)
    room.hands = {
        "p1": [8, 29, 40],
        "p2": [0] * 10,
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 上家 p2 出了单张 7 (card_id = 16)
    p2_play = detect_card_type([16], play_mode="fifty_k")
    room.last_play.player = "p2"
    room.last_play.card_play = p2_play

    # 桌面 0 分
    room.current_trick_cards = []

    ctx = build_ai_context(room, "p1")
    cards = ai_decide_play(room.hands["p1"], p2_play, False, ctx)

    # AI 应当直接打出假五十K炸弹 [8, 29, 40] 赢牌跑光，而决不能选择过牌！
    assert cards is not None
    assert set(cards) == {8, 29, 40}


def test_fifty_k_ai_blocks_running_opponent_with_bomb():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    from app.domain.game.card_type import detect_card_type
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 有 8 张牌 (非终结冲刺)：4444 炸弹 (4, 5, 6, 7) 加上 4 张常规小单牌
    # 对手 p2 的手牌只有 3 张 (听牌警报拉响)
    room.hands = {
        "p1": [4, 5, 6, 7, 0, 8, 12, 16],
        "p2": [0] * 3,
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    # 上家 p2 出了单张 10 (card_id = 28)
    p2_play = detect_card_type([28], play_mode="fifty_k")
    room.last_play.player = "p2"
    room.last_play.card_play = p2_play

    # 桌面 0 分
    room.current_trick_cards = []

    ctx = build_ai_context(room, "p1")
    # 验证 other_players_min_remaining 确实为 3 (触发封堵警报)
    assert ctx.other_players_min_remaining == 3

    cards = ai_decide_play(room.hands["p1"], p2_play, False, ctx)

    # 验证 AI 砸出炸弹 4444 进行顽强防守
    assert cards is not None
    assert set(cards) == {4, 5, 6, 7}


def test_fifty_k_ai_preserves_triple_over_double_straight():
    from app.domain.game.ai_strategy import _decompose_hand
    from app.domain.game.card_type import CardType
    
    # 模拟用户截图中的手牌：红桃 A(48), 对 6(12, 13), 对 5(8, 9), 3张 4(4, 5, 6), 对 3(0, 1)
    # 按照之前的 DFS 拆分：会由于连对手数优先，被强拆为：33-44-55-66 连对(1) + 4 单张(1) + A 单张(1) = 3手
    # 但在折算合并后，保留三条的折算手数为：444带33 三带二(1) + 55 对(1) + 66 对(1) + A 单(1) = 4手。
    # 等等，如果折算后是 4手，连对加单张是 3手。DFS 依然会偏向 3手。
    # 那如果我们在 DFS 叶子节点对手数进行了更精确的拟合，我们来运行本测试看看 _decompose_hand 的真实产出
    hand = [0, 1, 4, 5, 6, 8, 9, 12, 13, 48]
    plan = _decompose_hand(hand, "fifty_k")
    
    # 验证在我们的实际规划组合中，三条 4 (rank 1) 被保留为了 TRIPLE，而没有退化被拆散成对子/单张！
    triples = [p for p in plan.plays if p.card_type == CardType.TRIPLE_TWO or p.card_type == CardType.TRIPLE]
    assert len(triples) > 0 or any(p.card_type == CardType.TRIPLE_TWO for p in plan.plays)


def test_fifty_k_ai_leads_biggest_card_when_opponent_danger():
    from app.domain.game.ai_strategy import build_ai_context, ai_decide_play
    p1 = Player(id="p1", nickname="Player1")
    p2 = Player(id="p2", nickname="Player2")
    p3 = Player(id="p3", nickname="Player3")
    room = GameRoom.create("room_test", [p1, p2, p3], base_score=10)
    room.play_mode = "fifty_k"

    # AI (p1) 剩两手牌且无法出完：单张 4 (card_id = 4) 和单张 2 (card_id = 48)
    # 对手 p2 只有 1 张牌 (已拉响最高警戒级别听牌警报)
    room.hands = {
        "p1": [4, 48],
        "p2": [0],
        "p3": [4] * 10
    }
    room.current_turn = "p1"
    room.phase = GamePhase.PLAYING

    ctx = build_ai_context(room, "p1")
    assert ctx.other_players_min_remaining == 1

    # 轮到 AI 主动首出 (last_play 为 None，must_play 为 True)
    cards = ai_decide_play(room.hands["p1"], None, True, ctx)

    # 验证 AI 顶牌出大牌 2，绝对不能放手小牌 4
    assert cards == [48]
