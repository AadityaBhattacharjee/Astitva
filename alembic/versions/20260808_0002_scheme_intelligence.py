"""scheme intelligence

Revision ID: 20260808_0002
Revises: 20260808_0001
Create Date: 2026-08-08 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0002"
down_revision = "20260808_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schemes", sa.Column("min_age", sa.Integer(), nullable=True))
    op.add_column("schemes", sa.Column("max_age", sa.Integer(), nullable=True))
    op.add_column("schemes", sa.Column("income_limit", sa.Integer(), nullable=True))
    op.create_index("ix_schemes_target_group", "schemes", ["target_group"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_schemes_target_group", table_name="schemes")
    op.drop_column("schemes", "income_limit")
    op.drop_column("schemes", "max_age")
    op.drop_column("schemes", "min_age")
