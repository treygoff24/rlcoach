"""Add free_coach_message_used column to users table.

Revision ID: 002_free_coach_preview
Revises: 001_initial
Create Date: 2026-01-04 17:00:00+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_free_coach_preview"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add free_coach_message_used column for free tier coach preview."""
    op.add_column(
        "users",
        sa.Column(
            "free_coach_message_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Remove free_coach_message_used column."""
    op.drop_column("users", "free_coach_message_used")
