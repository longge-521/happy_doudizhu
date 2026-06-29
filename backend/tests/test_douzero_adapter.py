import pytest
import logging
from app.domain.game.douzero_adapter import card_id_to_douzero, douzero_to_card_ids, get_obs_for_douzero

def test_card_translation_and_obs_generation():
    # Test card translation (including 3..29 range)
    assert card_id_to_douzero(52) == 20  # Small Joker
    assert card_id_to_douzero(53) == 30  # Big Joker
    assert card_id_to_douzero(48) == 17  # Rank 2 (card ID 48 // 4 = 12)
    assert card_id_to_douzero(0) == 3    # Rank 3
    assert card_id_to_douzero(16) == 7   # Rank 4 (16 // 4 = 4 -> 4 + 3 = 7)
    
    # Test translating back
    hand = [0, 1, 2, 52] # three 3s, small joker
    assert douzero_to_card_ids([3, 3], hand) == [0, 1]
    
    # Test obs generation shapes with updated get_obs_for_douzero signature
    legal_actions = [[3], [3, 3]]
    # player_ids = ["p1", "p2", "p3"]. landlord_id is "p1".
    # In player_ids list order: landlord = "p1", landlord_down = "p2", landlord_up = "p3"
    play_history = [
        {"player": "p1", "cards": [4]},     # landlord plays single 4 (card ID 4 -> DZ 4)
        {"player": "p2", "cards": [8]},     # landlord_down plays single 5 (card ID 8 -> DZ 5)
        {"player": "p3", "cards": [12]},    # landlord_up plays single 6 (card ID 12 -> DZ 6)
    ]
    
    obs = get_obs_for_douzero(
        hand=hand,
        legal_actions=legal_actions,
        role="landlord",
        landlord_id="p1",
        player_ids=["p1", "p2", "p3"],
        play_history=play_history
    )
    
    assert obs["x_batch"].shape == (2, 373)
    assert obs["z_batch"].shape == (2, 5, 162)

def test_role_deduction_validation():
    hand = [0, 1, 2]
    legal_actions = [[3]]
    play_history = [{"player": "unknown_player", "cards": [4]}]
    
    # Invalid landlord_id
    with pytest.raises(ValueError, match="must be in player_ids"):
        get_obs_for_douzero(
            hand=hand,
            legal_actions=legal_actions,
            role="landlord",
            landlord_id="non_exist",
            player_ids=["p1", "p2", "p3"],
            play_history=[]
        )
        
    # Player in play history not in player_ids
    with pytest.raises(ValueError, match="not found in player_ids"):
        get_obs_for_douzero(
            hand=hand,
            legal_actions=legal_actions,
            role="landlord",
            landlord_id="p1",
            player_ids=["p1", "p2", "p3"],
            play_history=play_history
        )

def test_douzero_to_card_ids_warning(caplog):
    with caplog.at_level(logging.WARNING):
        hand = [0, 1, 2] # all translate to DouZero value 3
        # Attempt to translate DouZero value 4, which is not in hand
        result = douzero_to_card_ids([4], hand)
        assert result == []
        assert any("Translation warning" in record.message for record in caplog.records)
