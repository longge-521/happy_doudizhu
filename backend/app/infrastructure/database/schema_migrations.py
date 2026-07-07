import logging
from typing import Set

from sqlalchemy import inspect, text

logger = logging.getLogger("happy_doudizhu")


def _column_names(inspector, table_name: str) -> Set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def run_schema_migrations(bind) -> None:
    try:
        inspector = inspect(bind)

        audit_columns = _column_names(inspector, "ddz_audit_log")
        with bind.begin() as conn:
            if "request_params" not in audit_columns:
                conn.execute(text("ALTER TABLE ddz_audit_log ADD COLUMN request_params TEXT NULL COMMENT 'Request parameters'"))
            if "execution_time" not in audit_columns:
                conn.execute(text("ALTER TABLE ddz_audit_log ADD COLUMN execution_time FLOAT NULL COMMENT 'Execution time in ms'"))
            if "method" not in audit_columns:
                conn.execute(text("ALTER TABLE ddz_audit_log ADD COLUMN method VARCHAR(20) NULL COMMENT 'HTTP method'"))

        profile_columns = _column_names(inspector, "ddz_player_profile")
        with bind.begin() as conn:
            if "avatar_url" not in profile_columns:
                conn.execute(text("ALTER TABLE ddz_player_profile ADD COLUMN avatar_url VARCHAR(500) NULL COMMENT 'Avatar image URL'"))
            if "rank_id" not in profile_columns:
                conn.execute(text("ALTER TABLE ddz_player_profile ADD COLUMN rank_id INT NOT NULL DEFAULT 1 COMMENT 'Rank level 1-36'"))
            if "sub_rank" not in profile_columns:
                conn.execute(text("ALTER TABLE ddz_player_profile ADD COLUMN sub_rank INT NOT NULL DEFAULT 4 COMMENT 'Sub-rank level 1-4'"))
            if "stars" not in profile_columns:
                conn.execute(text("ALTER TABLE ddz_player_profile ADD COLUMN stars INT NOT NULL DEFAULT 0 COMMENT 'Accumulated stars'"))
    except Exception as exc:
        logger.warning(f"Database schema migration warning: {exc}")
