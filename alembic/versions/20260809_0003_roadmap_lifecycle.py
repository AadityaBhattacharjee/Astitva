"""roadmap lifecycle support

Revision ID: 20260809_0003
Revises: 20260808_0002
Create Date: 2026-08-09 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0003"
down_revision = "20260808_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("onboarding_data", sa.JSON(), nullable=True))
    op.add_column("user_profiles", sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE user_profiles SET onboarding_data = '{}' WHERE onboarding_data IS NULL")
    op.alter_column("user_profiles", "onboarding_data", nullable=False)

    op.add_column("roadmap_tasks", sa.Column("sequence", sa.Integer(), nullable=True))
    op.execute("UPDATE roadmap_tasks SET sequence = 0 WHERE sequence IS NULL")
    op.alter_column("roadmap_tasks", "sequence", nullable=False)


def downgrade() -> None:
    op.drop_column("roadmap_tasks", "sequence")
    op.drop_column("user_profiles", "onboarding_completed_at")
    op.drop_column("user_profiles", "onboarding_data")
