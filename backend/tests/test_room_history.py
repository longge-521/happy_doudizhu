import pytest
from app.domain.game.room import GameRoom, Player

def test_room_play_history_tracking():
    players = [Player("p1", "Player 1"), Player("p2", "Player 2"), Player("p3", "Player 3")]
    room = GameRoom.create("test_room", players)
    room.deal()
    assert hasattr(room, "play_history")
    assert len(room.play_history) == 0
    
    # Simulate a move
    room.phase = room.phase.PLAYING
    room.current_turn = "p1"
    card_to_play = [room.hands["p1"][0]]
    room.play_cards("p1", card_to_play)
    assert len(room.play_history) == 1
    assert room.play_history[0] == {"player": "p1", "cards": card_to_play}
