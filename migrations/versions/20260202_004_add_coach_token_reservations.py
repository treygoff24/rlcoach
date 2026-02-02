"""Add coach_token_reservations table.

Revision ID: 004_coach_token_reservations
Revises: 003_coach_message_content_json
Create Date: 2026-02-02 20:50:00+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_coach_token_reservations"
down_revision: Union[str, None] = "003_coach_message_content_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create coach_token_reservations table."""
    op.create_table(
        "coach_token_reservations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("coach_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_coach_token_reservations_user",
        "coach_token_reservations",
        ["user_id"],
    )
    op.create_index(
        "ix_coach_token_reservations_expires",
        "coach_token_reservations",
        ["expires_at"],
    )


def downgrade() -> None:
    """Drop coach_token_reservations table."""
    op.drop_index(
        "ix_coach_token_reservations_expires", table_name="coach_token_reservations"
    )
    op.drop_index(
        "ix_coach_token_reservations_user", table_name="coach_token_reservations"
    )
    op.drop_table("coach_token_reservations")
