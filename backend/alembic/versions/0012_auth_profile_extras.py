"""User avatar + Telegram link-code support.

Revision ID: 0012_auth_profile_extras
Revises: 0011_sale_prices_pos
Create Date: 2026-09-22

- users.avatar: profile avatar. The frontend stores the resolved image
  reference (object key or data URL) — never a binary blob.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_auth_profile_extras"
down_revision = "0011_sale_prices_pos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar")
