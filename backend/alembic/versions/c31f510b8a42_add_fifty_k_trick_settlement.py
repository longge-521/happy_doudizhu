"""新增 510K 牌墩幂等结算表。

Revision ID: c31f510b8a42
Revises: a7c4d2e91f08
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c31f510b8a42"
down_revision: Union[str, None] = "a7c4d2e91f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ddz_game_trick_settlement",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.String(length=100), nullable=False),
        sa.Column("trick_no", sa.Integer(), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_changes_json", sa.Text(), nullable=False),
        sa.Column("actual_changes_json", sa.Text(), nullable=True),
        sa.Column("balances_after_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            "trick_no",
            name="uq_ddz_game_trick_settlement_room_trick",
        ),
        comment="510K 牌墩幂等欢乐豆结算记录",
    )
    op.create_index(
        "ix_ddz_game_trick_settlement_room_id",
        "ddz_game_trick_settlement",
        ["room_id"],
        unique=False,
    )
    op.create_index(
        "ix_ddz_game_trick_settlement_status",
        "ddz_game_trick_settlement",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ddz_game_trick_settlement_status",
        table_name="ddz_game_trick_settlement",
    )
    op.drop_index(
        "ix_ddz_game_trick_settlement_room_id",
        table_name="ddz_game_trick_settlement",
    )
    op.drop_table("ddz_game_trick_settlement")
