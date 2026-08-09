"""task aware guide support

Revision ID: 20260809_0004
Revises: 20260809_0003
Create Date: 2026-08-09 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0004"
down_revision = "20260809_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("roadmap_tasks", sa.Column("agent_type", sa.String(length=50), nullable=True))
    op.add_column("roadmap_tasks", sa.Column("objective", sa.Text(), nullable=True))
    op.add_column("roadmap_tasks", sa.Column("required_information", sa.JSON(), nullable=True))
    op.add_column("roadmap_tasks", sa.Column("required_documents", sa.JSON(), nullable=True))
    op.add_column("roadmap_tasks", sa.Column("completion_criteria", sa.Text(), nullable=True))
    op.add_column("roadmap_tasks", sa.Column("resource_ids", sa.JSON(), nullable=True))

    op.execute("UPDATE roadmap_tasks SET agent_type = 'planning' WHERE agent_type IS NULL")
    op.execute("UPDATE roadmap_tasks SET required_information = '[]' WHERE required_information IS NULL")
    op.execute("UPDATE roadmap_tasks SET required_documents = '[]' WHERE required_documents IS NULL")
    op.execute("UPDATE roadmap_tasks SET resource_ids = '[]' WHERE resource_ids IS NULL")

    op.alter_column("roadmap_tasks", "agent_type", nullable=False)
    op.alter_column("roadmap_tasks", "required_information", nullable=False)
    op.alter_column("roadmap_tasks", "required_documents", nullable=False)
    op.alter_column("roadmap_tasks", "resource_ids", nullable=False)


def downgrade() -> None:
    op.drop_column("roadmap_tasks", "resource_ids")
    op.drop_column("roadmap_tasks", "completion_criteria")
    op.drop_column("roadmap_tasks", "required_documents")
    op.drop_column("roadmap_tasks", "required_information")
    op.drop_column("roadmap_tasks", "objective")
    op.drop_column("roadmap_tasks", "agent_type")
