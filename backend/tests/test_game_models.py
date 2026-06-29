# backend/tests/test_game_models.py
import pytest
from app.domain.game.entities import PlayerProfile, GameRecord


class TestPlayerProfile:
    def test_create_profile(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1")
        assert p.beans == 10000  # 初始欢乐豆
        assert p.total_games == 0
        assert p.wins == 0

    def test_win_rate_zero_games(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1")
        assert p.win_rate == 0.0

    def test_win_rate_calculation(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1", total_games=10, wins=6)
        assert p.win_rate == 0.6

    def test_player_profile_rank_title(self):
        p = PlayerProfile(player_id="p1", nickname="玩家1", rank_id=1, sub_rank=4, stars=0)
        assert p.rank_title == "包身工IV"
        
        # 验证 1 映射为 I 级
        p2 = PlayerProfile(player_id="p1", nickname="玩家1", rank_id=6, sub_rank=1, stars=2)
        assert p2.rank_title == "掌柜I"
        
        # 验证 36 级(至尊)不带罗马数字后缀
        p3 = PlayerProfile(player_id="p1", nickname="玩家1", rank_id=36, sub_rank=1, stars=10)
        assert p3.rank_title == "至尊"


class TestGameRecord:
    def test_create_record(self):
        r = GameRecord(
            room_id="room_1", player_id="p1",
            role="landlord", result="win",
            score_change=60, multiplier=2
        )
        assert r.role == "landlord"
        assert r.result == "win"
