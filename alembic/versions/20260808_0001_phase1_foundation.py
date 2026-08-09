"""phase1 foundation

Revision ID: 20260808_0001
Revises:
Create Date: 2026-08-08 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="USER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=False)

    op.create_table(
        "schemes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheme_id", sa.String(length=100), nullable=False),
        sa.Column("scheme_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("eligibility", sa.Text(), nullable=True),
        sa.Column("age_criteria", sa.String(length=255), nullable=True),
        sa.Column("income_criteria", sa.String(length=255), nullable=True),
        sa.Column("target_group", sa.String(length=255), nullable=True),
        sa.Column("benefits", sa.JSON(), nullable=False),
        sa.Column("required_documents", sa.JSON(), nullable=False),
        sa.Column("application_process", sa.Text(), nullable=True),
        sa.Column("official_url", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("last_verified", sa.String(length=50), nullable=True),
        sa.Column("active_status", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_schemes_scheme_id", "schemes", ["scheme_id"], unique=True)
    op.create_index("ix_schemes_category", "schemes", ["category"], unique=False)
    op.create_index("ix_schemes_state", "schemes", ["state"], unique=False)
    op.create_index("ix_schemes_active_status", "schemes", ["active_status"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], unique=False)

    op.create_table(
        "roadmaps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Personalized Roadmap"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_roadmaps_user_id", "roadmaps", ["user_id"], unique=False)
    op.create_index("ix_roadmaps_status", "roadmaps", ["status"], unique=False)

    op.create_table(
        "roadmap_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roadmap_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_roadmap_tasks_roadmap_id", "roadmap_tasks", ["roadmap_id"], unique=False)
    op.create_index("ix_roadmap_tasks_status", "roadmap_tasks", ["status"], unique=False)

    op.create_table(
        "progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roadmap_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="ACTIVE"),
        sa.Column("completed_milestones", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missed_milestones", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overdue_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_history", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_progress_roadmap_id", "progress", ["roadmap_id"], unique=False)
    op.create_index("ix_progress_status", "progress", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_progress_status", table_name="progress")
    op.drop_index("ix_progress_roadmap_id", table_name="progress")
    op.drop_table("progress")

    op.drop_index("ix_roadmap_tasks_status", table_name="roadmap_tasks")
    op.drop_index("ix_roadmap_tasks_roadmap_id", table_name="roadmap_tasks")
    op.drop_table("roadmap_tasks")

    op.drop_index("ix_roadmaps_status", table_name="roadmaps")
    op.drop_index("ix_roadmaps_user_id", table_name="roadmaps")
    op.drop_table("roadmaps")

    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_schemes_active_status", table_name="schemes")
    op.drop_index("ix_schemes_state", table_name="schemes")
    op.drop_index("ix_schemes_category", table_name="schemes")
    op.drop_index("ix_schemes_scheme_id", table_name="schemes")
    op.drop_table("schemes")

    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

