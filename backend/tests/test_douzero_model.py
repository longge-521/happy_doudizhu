import pytest
import torch
from unittest.mock import patch
from app.domain.game.douzero_model import DouZeroAgentManager, LandlordLstmModel, FarmerLstmModel

def test_model_definitions_and_inference():
    # Test LandlordLstmModel Structure
    landlord_model = LandlordLstmModel()
    dummy_z = torch.zeros(1, 5, 162)
    dummy_x = torch.zeros(1, 373)
    out = landlord_model(dummy_z, dummy_x)
    assert out.shape == (1, 1)

    # Test FarmerLstmModel Structure
    farmer_model = FarmerLstmModel()
    dummy_z_farmer = torch.zeros(1, 5, 162)
    dummy_x_farmer = torch.zeros(1, 484)
    out_farmer = farmer_model(dummy_z_farmer, dummy_x_farmer)
    assert out_farmer.shape == (1, 1)

    # Test Manager Fallback when weights are missing
    with patch("os.path.exists", return_value=False):
        manager = DouZeroAgentManager()
        assert manager.is_available() is False

    # Test get_action_value when models are not loaded
    with pytest.raises(RuntimeError, match="DouZero models not loaded."):
        manager.get_action_value("landlord", dummy_z, dummy_x)

    # Test get_action_value when role is invalid but models are "loaded" (mocked)
    manager._loaded = True
    manager.models = {"landlord": landlord_model}
    with pytest.raises(ValueError, match="Invalid role: invalid_role. Expected one of \\['landlord'\\]"):
        manager.get_action_value("invalid_role", dummy_z, dummy_x)
