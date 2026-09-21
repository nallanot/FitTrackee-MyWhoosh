"""add native MyWhoosh integration

Revision ID: 674cfb183adb
Revises: 28a548e58b3f
Create Date: 2026-09-20 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


revision = "674cfb183adb"
down_revision = "28a548e58b3f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mywhoosh_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("whoosh_id", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column(
            "auto_sync", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "sync_days", sa.Integer(), server_default="30", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column(
            "last_sync_status",
            sa.String(length=30),
            server_default="never",
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "sync_in_progress",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("sync_started_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        op.f("ix_mywhoosh_connections_user_id"),
        "mywhoosh_connections",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "mywhoosh_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.String(length=255), nullable=False),
        sa.Column("activity_file_id", sa.String(length=255), nullable=False),
        sa.Column("activity_title", sa.String(length=255), nullable=True),
        sa.Column("activity_date", sa.DateTime(), nullable=True),
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("workout_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["mywhoosh_connections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workout_id"], ["workouts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "activity_id",
            name="mywhoosh_import_connection_activity_unique",
        ),
        sa.UniqueConstraint(
            "connection_id",
            "activity_file_id",
            name="mywhoosh_import_connection_file_unique",
        ),
    )
    op.create_index(
        op.f("ix_mywhoosh_imports_connection_id"),
        "mywhoosh_imports",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mywhoosh_imports_workout_id"),
        "mywhoosh_imports",
        ["workout_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_mywhoosh_imports_workout_id"),
        table_name="mywhoosh_imports",
    )
    op.drop_index(
        op.f("ix_mywhoosh_imports_connection_id"),
        table_name="mywhoosh_imports",
    )
    op.drop_table("mywhoosh_imports")
    op.drop_index(
        op.f("ix_mywhoosh_connections_user_id"),
        table_name="mywhoosh_connections",
    )
    op.drop_table("mywhoosh_connections")
