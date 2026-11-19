"""Add retry linkage to jobs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "retry_of_job_id" not in columns:
        op.add_column("jobs", sa.Column("retry_of_job_id", sa.String, nullable=True))
    existing_indexes = {index["name"] for index in inspector.get_indexes("jobs")}
    if "ix_jobs_retry_of_job_id" not in existing_indexes:
        op.create_index("ix_jobs_retry_of_job_id", "jobs", ["retry_of_job_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_retry_of_job_id", table_name="jobs")
    op.drop_column("jobs", "retry_of_job_id")
