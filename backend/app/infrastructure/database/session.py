import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from app.infrastructure.database.models import Base

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_NAME = os.getenv("DB_NAME", "hmp_ws_service")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

engine = create_engine(DATABASE_URL, pool_recycle=3600, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from sqlalchemy import inspect, text


def _is_production_env():
    return os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}


def _env_flag(name):
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def should_auto_init_db():
    configured = _env_flag("AUTO_INIT_DB")
    if configured is not None:
        return configured
    return not _is_production_env()


def init_db():
    """初始化数据库表（如果不存在的话）并自愈补齐新字段"""
    Base.metadata.create_all(bind=engine)
    
    # 动态检测并扩容缺失字段，保证平滑升级而免受数据库结构不一致引发的崩溃
    try:
        inspector = inspect(engine)
        # audit_log 自愈
        columns_audit = [col["name"] for col in inspector.get_columns("audit_log")]
        with engine.begin() as conn:
            if "request_params" not in columns_audit:
                conn.execute(text("ALTER TABLE audit_log ADD COLUMN request_params TEXT NULL COMMENT '请求参数/传参'"))
            if "execution_time" not in columns_audit:
                conn.execute(text("ALTER TABLE audit_log ADD COLUMN execution_time FLOAT NULL COMMENT '执行耗时(毫秒)'"))
            if "method" not in columns_audit:
                conn.execute(text("ALTER TABLE audit_log ADD COLUMN method VARCHAR(20) NULL COMMENT '请求方式：GET/POST等'"))
        
        # player_profile 自愈
        columns_profile = [col["name"] for col in inspector.get_columns("player_profile")]
        with engine.begin() as conn:
            if "rank_id" not in columns_profile:
                conn.execute(text("ALTER TABLE player_profile ADD COLUMN rank_id INT NOT NULL DEFAULT 1 COMMENT '大级别(1-36)'"))
            if "sub_rank" not in columns_profile:
                conn.execute(text("ALTER TABLE player_profile ADD COLUMN sub_rank INT NOT NULL DEFAULT 4 COMMENT '子级别(1-4，对应I-IV)'"))
            if "stars" not in columns_profile:
                conn.execute(text("ALTER TABLE player_profile ADD COLUMN stars INT NOT NULL DEFAULT 0 COMMENT '累积星星数'"))
    except Exception as e:
        import logging
        logging.getLogger("hmp_ws_service").warning(f"Database schema self-healing warning: {e}")

from contextlib import contextmanager

def get_db():
    """FastAPI 依赖注入：获取数据库连接 Session (具备自动事务提交/回滚保护)"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@contextmanager
def transactional_session():
    """具有自动事务控制（Commit/Rollback）的 Session 上下文管理器，适用于非 Web 请求场景如 WebSocket Handler 或后台任务"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
