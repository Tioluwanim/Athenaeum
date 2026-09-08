"""add users table, chat_sessions.user_id, and documents.checksum index

Revision ID: 20260907_0003
Revises: d4c742e572d9
Create Date: 2026-09-07
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260907_0003"
down_revision = "d4c742e572d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("role", sa.String(16), nullable=False, server_default="staff"),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_chat_sessions_user_id", "users", ["user_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_documents_checksum", "documents", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_documents_checksum", table_name="documents")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    with op.batch_alter_table("chat_sessions") as batch_op:
        batch_op.drop_constraint("fk_chat_sessions_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
