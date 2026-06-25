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
