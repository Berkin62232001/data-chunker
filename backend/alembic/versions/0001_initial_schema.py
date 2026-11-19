"""Initial schema — all 11 tables

Revision ID: 0001
Revises:
Create Date: 2026-06-01

Usage on a fresh database:
    alembic upgrade head

Usage on an existing database (tables already created via init_db):
    alembic stamp head

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "documents" not in existing:
        op.create_table(
            "documents",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.String, unique=True, nullable=False, index=True),
            sa.Column("original_filename", sa.String, nullable=False),
            sa.Column("stored_filename", sa.String, nullable=False),
            sa.Column("mime_type", sa.String),
            sa.Column("file_size_bytes", sa.Integer),
            sa.Column("status", sa.String),
            sa.Column("current_phase", sa.String),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if "document_profiles" not in existing:
        op.create_table(
            "document_profiles",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.String, nullable=False, index=True),
            sa.Column("detected_type", sa.String),
            sa.Column("mime_type", sa.String),
            sa.Column("page_count", sa.Integer),
            sa.Column("requires_ocr", sa.Boolean),
            sa.Column("profile_json", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "pipeline_decisions" not in existing:
        op.create_table(
            "pipeline_decisions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.String, nullable=False, index=True),
            sa.Column("selected_pipeline", sa.String, nullable=False),
            sa.Column("output_format", sa.String),
            sa.Column("llm_send_format", sa.String),
            sa.Column("decision_json", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "conversions" not in existing:
        op.create_table(
            "conversions",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.String, nullable=False, index=True),
            sa.Column("status", sa.String, nullable=False),
            sa.Column("converter_used", sa.String),
            sa.Column("estimated_tokens", sa.Integer),
            sa.Column("warnings_json", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "chunk_manifests" not in existing:
        op.create_table(
            "chunk_manifests",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.String, nullable=False, index=True),
            sa.Column("total_chunks", sa.Integer, nullable=False),
            sa.Column("total_estimated_tokens", sa.Integer),
            sa.Column("chunking_strategy", sa.String),
            sa.Column("manifest_json", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "integrity_reports" not in existing:
        op.create_table(
            "integrity_reports",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("document_id", sa.String, nullable=False, index=True),
            sa.Column("status", sa.String, nullable=False),
            sa.Column("report_json", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "llm_payloads" not in existing:
        op.create_table(
            "llm_payloads",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("payload_id", sa.String, unique=True, nullable=False, index=True),
            sa.Column("document_id", sa.String, index=True),
            sa.Column("project_id", sa.String, index=True),
            sa.Column("provider", sa.String),
            sa.Column("query", sa.Text),
            sa.Column("retrieval_mode", sa.String),
            sa.Column("selected_chunk_count", sa.Integer),
            sa.Column("estimated_context_tokens", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "llm_calls" not in existing:
        op.create_table(
            "llm_calls",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("call_id", sa.String, unique=True, nullable=False, index=True),
            sa.Column("document_id", sa.String, index=True),
            sa.Column("project_id", sa.String, index=True),
            sa.Column("provider", sa.String),
            sa.Column("query", sa.Text),
            sa.Column("status", sa.String),
            sa.Column("payload_id", sa.String),
            sa.Column("error_message", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "projects" not in existing:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("project_id", sa.String, unique=True, nullable=False, index=True),
            sa.Column("name", sa.String, nullable=False),
            sa.Column("description", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )

    if "project_documents" not in existing:
        op.create_table(
            "project_documents",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("project_id", sa.String, nullable=False, index=True),
            sa.Column("document_id", sa.String, nullable=False, index=True),
            sa.Column("added_at", sa.DateTime(timezone=True)),
        )

    if "audit_events" not in existing:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("event_type", sa.String, nullable=False, index=True),
            sa.Column("document_id", sa.String, index=True),
            sa.Column("project_id", sa.String, index=True),
            sa.Column("payload_id", sa.String),
            sa.Column("metadata_json", sa.Text),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("project_documents")
    op.drop_table("projects")
    op.drop_table("llm_calls")
    op.drop_table("llm_payloads")
    op.drop_table("integrity_reports")
    op.drop_table("chunk_manifests")
    op.drop_table("conversions")
    op.drop_table("pipeline_decisions")
    op.drop_table("document_profiles")
    op.drop_table("documents")
