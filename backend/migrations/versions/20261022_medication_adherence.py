"""add medication adherence tracking

Revision ID: 20261022_med_adherence
Revises: 20261022_initial
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20261022_med_adherence"
down_revision = "20261022_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "medications",
        sa.Column("dose_times", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.create_table(
        "medication_dose_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("medication_id", sa.Integer(), nullable=False),
        sa.Column("dose_date", sa.Date(), nullable=False),
        sa.Column("dose_time", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["medication_id"], ["medications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("medication_id", "dose_date", "dose_time", name="uq_medication_dose_slot"),
    )
    op.create_index(op.f("ix_medication_dose_logs_id"), "medication_dose_logs", ["id"], unique=False)
    op.create_index(op.f("ix_medication_dose_logs_medication_id"), "medication_dose_logs", ["medication_id"], unique=False)
    op.create_index(op.f("ix_medication_dose_logs_dose_date"), "medication_dose_logs", ["dose_date"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_medication_dose_logs_dose_date"), table_name="medication_dose_logs")
    op.drop_index(op.f("ix_medication_dose_logs_medication_id"), table_name="medication_dose_logs")
    op.drop_index(op.f("ix_medication_dose_logs_id"), table_name="medication_dose_logs")
    op.drop_table("medication_dose_logs")
    op.drop_column("medications", "dose_times")