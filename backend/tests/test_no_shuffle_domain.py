# backend/tests/test_no_shuffle_domain.py
import pytest
from app.domain.game.card import Card, FULL_DECK
from app.domain.game.room import GameRoom, Player

def test_cut_cards_preserves_length():
    from app.domain.game.card import cut_cards
    deck = list(range(54))
    cut = cut_cards(deck)
    assert len(cut) == 54
    assert set(cut) == set(range(54))
    # 验证没有被打乱（相邻关系多半保留）
    diff_count = sum(1 for i in range(53) if abs(cut[i+1] - cut[i]) != 1)
    assert diff_count <= 2  # 仅在切牌分割点会出现不连续

def test_deal_with_deck():
    players = [
        Player(id="p1", nickname="P1", is_ai=False),
        Player(id="p2", nickname="P2", is_ai=False),
        Player(id="p3", nickname="P3", is_ai=False),
    ]
    room = GameRoom.create("test_room_1", players, base_score=20)
    room.play_mode = "no_shuffle"
    
    custom_deck = list(range(54))
    hands = room.deal_with_deck(custom_deck)
    
    assert len(room.hands["p1"]) == 17
    assert len(room.hands["p2"]) == 17
    assert len(room.hands["p3"]) == 17
    assert len(room.bottom_cards) == 3
    assert room.phase.value == "CALLING"

def test_recycle_cards_valid():
    players = [
        Player(id="p1", nickname="P1", is_ai=False),
        Player(id="p2", nickname="P2", is_ai=False),
        Player(id="p3", nickname="P3", is_ai=False),
    ]
    room = GameRoom.create("test_room_1", players, base_score=20)
    room.play_mode = "no_shuffle"
    
    custom_deck = list(range(54))
    room.deal_with_deck(custom_deck)
    
    # 模拟玩家出牌和扣牌
    room.all_played_cards = [0, 1, 2, 3] # 玩家打出的牌
    room.hands["p1"] = list(range(4, 17))
    room.hands["p2"] = list(range(17, 34))
    room.hands["p3"] = list(range(34, 51))
    room.bottom_cards = [51, 52, 53]
    room.landlord = None
    
    recycled = room.recycle_cards()
    assert len(recycled) == 54
    assert set(recycled) == set(range(54))

def test_recycle_cards_with_landlord():
    players = [
        Player(id="p1", nickname="P1", is_ai=False),
        Player(id="p2", nickname="P2", is_ai=False),
        Player(id="p3", nickname="P3", is_ai=False),
    ]
    room = GameRoom.create("test_room_2", players, base_score=20)
    room.play_mode = "no_shuffle"
    
    custom_deck = list(range(54))
    room.deal_with_deck(custom_deck)
    
    # 模拟选中地主 p1
    room.landlord = "p1"
    # 地主拿走 3 张底牌 并排序手牌
    from app.domain.game.card import sort_cards
    room.hands["p1"] = sort_cards(room.hands["p1"] + room.bottom_cards)
    
    # 打出几张牌
    p1_initial_hand = list(room.hands["p1"])
    played_cards = [p1_initial_hand[0], p1_initial_hand[1], p1_initial_hand[2]]
    for card in played_cards:
        room.hands["p1"].remove(card)
    room.all_played_cards.extend(played_cards)
    
    p2_initial_hand = list(room.hands["p2"])
    played_cards_p2 = [p2_initial_hand[0], p2_initial_hand[1]]
    for card in played_cards_p2:
        room.hands["p2"].remove(card)
    room.all_played_cards.extend(played_cards_p2)
    
    recycled = room.recycle_cards()
    assert len(recycled) == 54
    assert set(recycled) == set(range(54))
