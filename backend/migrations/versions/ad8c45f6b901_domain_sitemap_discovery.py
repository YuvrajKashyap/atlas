"""domain sitemap discovery

Revision ID: ad8c45f6b901
Revises: 7c98a56b9720
Create Date: 2026-07-16 23:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ad8c45f6b901"
down_revision: str | Sequence[str] | None = "7c98a56b9720"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "domain_states",
        sa.Column("sitemaps_discovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "domain_states",
        sa.Column("sitemap_url_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("domain_states", "sitemap_url_count", server_default=None)


def downgrade() -> None:
    op.drop_column("domain_states", "sitemap_url_count")
    op.drop_column("domain_states", "sitemaps_discovered_at")
