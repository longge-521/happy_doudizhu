import pytest
from app.application.game.game_app_service import GameAppService
from app.domain.game.room import GameRoom, Player, GamePhase


class MemoryRepo:
    def __init__(self, room):
        self.room = room
        self.saved_room = None

    async def get_player_room(self, player_id):
        return self.room.room_id

    async def get_room(self, room_id):
        return self.room

    async def save_room(self, room):
        self.saved_room = room


def make_room():
    players = [
        Player(id="p1", nickname="玩家1"),
        Player(id="p2", nickname="玩家2"),
        Player(id="p3", nickname="玩家3"),
    ]
    room = GameRoom.create("room_1", players)
    room.deal()
    room._first_caller_index = 0
    room._call_index = 0
    room.current_turn = "p1"
    room._set_landlord("p1")
    room.finish_landlord_confirm()
    return room


@pytest.mark.asyncio
async def test_handle_double_choice_saves_room():
    room = make_room()
    repo = MemoryRepo(room)
    service = GameAppService(repo)

    result = await service.handle_double_choice("p1", "double")

    assert result["success"] is True
    assert result["choice"] == "double"
    assert repo.saved_room is room
    assert room.doubling_choices == {"p1": "double"}
