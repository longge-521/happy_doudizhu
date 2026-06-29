# backend/app/domain/game/entities.py
"""游戏领域实体：玩家档案与对局记录"""
import datetime
from typing import Optional


RANK_TITLES = [
    "", "包身工", "短工", "长工", "中农", "富农", "掌柜", "商人", "小财主", "大财主",
    "县尉", "县丞", "县令", "通判", "主事", "知府", "员外郎", "郎中", "侍郎", "巡抚",
    "总督", "尚书", "大学士", "太保", "太傅", "太师", "三等伯", "二等伯", "一等伯",
    "三等侯", "二等侯", "一等侯", "辅国公", "镇国公", "郡王", "亲王", "至尊"
]


class PlayerProfile:
    """玩家档案领域实体"""
    DEFAULT_BEANS = 10000

    def __init__(
        self,
        player_id: str,
        nickname: str,
        id: Optional[int] = None,
        beans: int = DEFAULT_BEANS,
        total_games: int = 0,
        wins: int = 0,
        created_at: Optional[datetime.datetime] = None,
        rank_id: int = 1,
        sub_rank: int = 4,
        stars: int = 0,
    ):
        self.id = id
        self.player_id = player_id
        self.nickname = nickname
        self.beans = beans
        self.total_games = total_games
        self.wins = wins
        self.created_at = created_at or datetime.datetime.now()
        self.rank_id = rank_id
        self.sub_rank = sub_rank
        self.stars = stars

    @property
    def win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return round(self.wins / self.total_games, 2)

    @property
    def rank_title(self) -> str:
        if self.rank_id >= 36:
            return "至尊"
        roman_map = {1: "I", 2: "II", 3: "III", 4: "IV"}
        roman = roman_map.get(self.sub_rank, "IV")
        title = RANK_TITLES[self.rank_id] if self.rank_id < len(RANK_TITLES) else "包身工"
        return f"{title}{roman}"


class GameRecord:
    """对局记录领域实体"""

    def __init__(
        self,
        room_id: str,
        player_id: str,
        role: str,         # "landlord" / "farmer"
        result: str,        # "win" / "lose"
        score_change: int,
        multiplier: int,
        id: Optional[int] = None,
        created_at: Optional[datetime.datetime] = None,
    ):
        self.id = id
        self.room_id = room_id
        self.player_id = player_id
        self.role = role
        self.result = result
        self.score_change = score_change
        self.multiplier = multiplier
        self.created_at = created_at or datetime.datetime.now()
