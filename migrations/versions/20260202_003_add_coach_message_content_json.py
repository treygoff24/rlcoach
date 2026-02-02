"""Add content_json to coach_messages and backfill.

Revision ID: 003_coach_message_content_json
Revises: 002_free_coach_preview
Create Date: 2026-02-02 20:45:00+00:00

"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_coach_message_content_json"
down_revision: Union[str, None] = "002_free_coach_preview"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add content_json column and backfill existing rows."""
    op.add_column("coach_messages", sa.Column("content_json", sa.Text(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, content FROM coach_messages WHERE content_json IS NULL")
    ).fetchall()
    for row in rows:
        content_json = json.dumps([
            {
                "type": "text",
                "text": row.content or "",
            }
        ])
        bind.execute(
            sa.text(
                "UPDATE coach_messages SET content_json = :content_json WHERE id = :id"
            ),
            {"content_json": content_json, "id": row.id},
        )


def downgrade() -> None:
    """Remove content_json column."""
    op.drop_column("coach_messages", "content_json")
