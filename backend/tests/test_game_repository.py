# backend/tests/test_game_repository.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.infrastructure.database.models import Base, PlayerProfileORM
from app.infrastructure.database.game_repository import SQLGameRepository

def test_sql_game_repository_beans():
    # 使用内存数据库进行仓储层单测
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SQLGameRepository(session)
    
    # 1. 验证初始默认欢乐豆为 10000
    profile = repo.get_or_create_profile("player_test", "Tester")
    assert profile.beans == 10000
    
    # 2. 验证 update_beans 对负数的截断（设为负数应变为 0）
    repo.update_beans("player_test", -500)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_test").first()
    assert orm.beans == 0
    
    # 3. 验证 update_profile_stats 破产保护扣减（设为 100 豆，扣减 200 后应截断为 0）
    repo.update_beans("player_test", 100)
    repo.update_profile_stats("player_test", -200, is_win=False)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_test").first()
    assert orm.beans == 0
    
    session.close()


def test_sql_game_repository_rank_state_machine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    repo = SQLGameRepository(session)
    
    # 建立初始段位：包身工IV (rank_id=1, sub_rank=4, stars=0)
    repo.get_or_create_profile("player_rank", "Tester")
    
    # 1. 验证新手保护：输牌不扣星 (包身工IV 0星输球 -> 仍为包身工IV 0星)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 1 and orm.sub_rank == 4 and orm.stars == 0
    
    # 2. 验证赢球加星及溢出升小段 (包身工IV 0星 -> 普通赢 -> 包身工IV 1星)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=1)
    # 再普通赢两场 -> 包身工IV 3星 -> 晋级包身工III 0星 (即 rank_id=1, sub_rank=3, stars=0)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=1)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 1 and orm.sub_rank == 3 and orm.stars == 0
    
    # 2b. 验证非最低段位的低段位输球扣星降级 (包身工III 0星 输球 -> 降级为 包身工IV 2星)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 1 and orm.sub_rank == 4 and orm.stars == 2
    
    # 3. 验证爆发赢加双星及大段晋级
    # 设定为大财主I 2星 (rank_id=9, sub_rank=1, stars=2)
    repo.update_rank_profile("player_rank", rank_id=9, sub_rank=1, stars=2)
    # 特殊赢(+2星) -> 星星变成 4(大财主满星限制3) -> 溢出 1星并大段晋级为县尉IV (rank_id=10, sub_rank=4, stars=1)
    repo.update_rank_stats("player_rank", is_win=True, multiplier=4)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 10 and orm.sub_rank == 4 and orm.stars == 1
    
    # 4. 验证中等段位大段位保护 (县尉IV 0星输球 -> 触发保级 -> 仍为县尉IV 0星)
    repo.update_rank_profile("player_rank", rank_id=10, sub_rank=4, stars=0)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 10 and orm.sub_rank == 4 and orm.stars == 0
    
    # 5. 验证高级段位无降段保护 (大学士IV 0星输球 -> 无保级降大级 -> 尚书I 4星 (尚书满星4，扣1后剩3))
    repo.update_rank_profile("player_rank", rank_id=22, sub_rank=4, stars=0)
    repo.update_rank_stats("player_rank", is_win=False, multiplier=1)
    orm = session.query(PlayerProfileORM).filter_by(player_id="player_rank").first()
    assert orm.rank_id == 21 and orm.sub_rank == 1 and orm.stars == 3
    
    session.close()
