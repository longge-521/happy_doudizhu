import os
import logging
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

class LandlordLstmModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(162, 128, batch_first=True)
        self.dense1 = nn.Linear(373 + 128, 512)
        self.dense2 = nn.Linear(512, 512)
        self.dense3 = nn.Linear(512, 512)
        self.dense4 = nn.Linear(512, 512)
        self.dense5 = nn.Linear(512, 512)
        self.dense6 = nn.Linear(512, 1)

    def forward(self, z, x):
        lstm_out, _ = self.lstm(z)
        lstm_out = lstm_out[:, -1, :]
        out = torch.cat([lstm_out, x], dim=-1)
        out = F.relu(self.dense1(out))
        out = F.relu(self.dense2(out))
        out = F.relu(self.dense3(out))
        out = F.relu(self.dense4(out))
        out = F.relu(self.dense5(out))
        out = self.dense6(out)
        return out

class FarmerLstmModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(162, 128, batch_first=True)
        self.dense1 = nn.Linear(484 + 128, 512)
        self.dense2 = nn.Linear(512, 512)
        self.dense3 = nn.Linear(512, 512)
        self.dense4 = nn.Linear(512, 512)
        self.dense5 = nn.Linear(512, 512)
        self.dense6 = nn.Linear(512, 1)

    def forward(self, z, x):
        lstm_out, _ = self.lstm(z)
        lstm_out = lstm_out[:, -1, :]
        out = torch.cat([lstm_out, x], dim=-1)
        out = F.relu(self.dense1(out))
        out = F.relu(self.dense2(out))
        out = F.relu(self.dense3(out))
        out = F.relu(self.dense4(out))
        out = F.relu(self.dense5(out))
        out = self.dense6(out)
        return out

class DouZeroAgentManager:
    def __init__(self):
        self.models = {}
        self._loaded = False
        self.load_models()

    def load_models(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        weights_dir = os.path.join(base_dir, "weights")
        
        landlord_path = os.path.join(weights_dir, "landlord.ckpt")
        landlord_up_path = os.path.join(weights_dir, "landlord_up.ckpt")
        landlord_down_path = os.path.join(weights_dir, "landlord_down.ckpt")

        if not (os.path.exists(landlord_path) and os.path.exists(landlord_up_path) and os.path.exists(landlord_down_path)):
            logger.warning("DouZero weights are not fully present in backend/app/domain/game/weights/. Fallback engine active.")
            return

        try:
            # Initialize structures
            self.models["landlord"] = LandlordLstmModel()
            self.models["landlord_up"] = FarmerLstmModel()
            self.models["landlord_down"] = FarmerLstmModel()

            # Load weights
            self.models["landlord"].load_state_dict(torch.load(landlord_path, map_location="cpu"))
            self.models["landlord_up"].load_state_dict(torch.load(landlord_up_path, map_location="cpu"))
            self.models["landlord_down"].load_state_dict(torch.load(landlord_down_path, map_location="cpu"))

            # Set to eval mode
            for m in self.models.values():
                m.eval()
            
            self._loaded = True
            logger.info("DouZero RL models loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load DouZero weights: {e}. Fallback active.")
            self.models = {}
            self._loaded = False

    def is_available(self) -> bool:
        return self._loaded

    def get_action_value(self, role: str, z: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
        if not self._loaded:
            raise RuntimeError("DouZero models not loaded.")
        if role not in self.models:
            raise ValueError(f"Invalid role: {role}. Expected one of {list(self.models.keys())}")
        with torch.no_grad():
            return self.models[role](z, x)

# Global Singleton instance
douzero_manager = DouZeroAgentManager()
