"""documentation free text labels

Revision ID: 20260506_0008
Revises: 20260506_0007
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260506_0008"
down_revision = "20260506_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("documentation_sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("documentation_sessions")}
    if "patient_label" not in columns:
        op.add_column("documentation_sessions", sa.Column("patient_label", sa.String(length=255), nullable=True))
    if "therapist_label" not in columns:
        op.add_column("documentation_sessions", sa.Column("therapist_label", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("documentation_sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("documentation_sessions")}
    if "therapist_label" in columns:
        op.drop_column("documentation_sessions", "therapist_label")
    if "patient_label" in columns:
        op.drop_column("documentation_sessions", "patient_label")
