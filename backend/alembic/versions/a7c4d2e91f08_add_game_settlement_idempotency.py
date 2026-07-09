"""add game settlement idempotency

Revision ID: a7c4d2e91f08
Revises: 56455943753d
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c4d2e91f08"
down_revision: Union[str, None] = "56455943753d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT room_id, player_id, COUNT(*) AS duplicate_count
            FROM ddz_game_record
            GROUP BY room_id, player_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "检测到重复战绩，停止迁移："
            f"room_id={duplicate.room_id}, player_id={duplicate.player_id}, "
            f"count={duplicate.duplicate_count}"
        )

    op.create_table(
        "ddz_game_settlement",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.String(length=100), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "room_id",
            name="uq_ddz_game_settlement_room_id",
        ),
        comment="对局幂等结算主记录",
    )
    op.create_index(
        "ix_ddz_game_settlement_room_id",
        "ddz_game_settlement",
        ["room_id"],
        unique=False,
    )
    op.create_index(
        "ix_ddz_game_settlement_status",
        "ddz_game_settlement",
        ["status"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_ddz_game_record_room_player",
        "ddz_game_record",
        ["room_id", "player_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ddz_game_record_room_player",
        "ddz_game_record",
        type_="unique",
    )
    op.drop_index(
        "ix_ddz_game_settlement_status",
        table_name="ddz_game_settlement",
    )
    op.drop_index(
        "ix_ddz_game_settlement_room_id",
        table_name="ddz_game_settlement",
    )
    op.drop_table("ddz_game_settlement")
