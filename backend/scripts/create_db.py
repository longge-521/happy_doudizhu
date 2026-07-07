"""
create_db.py
============
用途：以无具体数据库的方式连接 MySQL，自动创建 .env 中指定的数据库，
      再调用项目的 init_db() 完成所有数据表的初始化。

运行方式（在 backend/ 目录下执行）：
    python scripts/create_db.py
"""
import sys
from pathlib import Path

# 将 backend/ 目录加入 Python 路径，以便导入 app 包
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text
from app.infrastructure.config import settings


def create_database_if_not_exists() -> str:
    """连接 MySQL 实例（不指定具体数据库），确保目标数据库存在。"""
    db_host = settings.DB_HOST
    db_port = settings.DB_PORT
    db_user = settings.DB_USER
    db_password = settings.DB_PASSWORD
    db_name = settings.DB_NAME

    # 不携带数据库名的基础连接 URL
    base_url = (
        f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/"
        f"?charset=utf8mb4"
    )

    print(f"[1/3] 正在连接到 MySQL 服务器 {db_host}:{db_port} ...")
    tmp_engine = create_engine(base_url, pool_pre_ping=True)

    with tmp_engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )

    print(f"[2/3] 数据库 `{db_name}` 检查 / 创建成功！")
    tmp_engine.dispose()
    return db_name


def init_tables() -> None:
    """导入并调用 session.init_db() 创建所有表结构与迁移补丁。"""
    from app.infrastructure.database.session import init_db  # noqa: PLC0415

    print("[3/3] 正在初始化数据库表结构（create_all + schema_migrations）...")
    init_db()
    print("      所有数据表初始化完成！")


def main() -> None:
    db_name = create_database_if_not_exists()
    init_tables()
    print(f"\n[OK] 完成！数据库 `{db_name}` 及其所有表已就绪。")


if __name__ == "__main__":
    main()
