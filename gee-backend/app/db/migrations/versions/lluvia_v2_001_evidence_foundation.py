"""Rainfall v2 evidence foundation.

Revision ID: lluvia_v2_001
Revises: 0020_add_canal_consorcio
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "lluvia_v2_001"
down_revision = "0020_add_canal_consorcio"
branch_labels = None
depends_on = None

_IMMUTABLE_TABLES = (
    "rainfall_source_eligibility",
    "rainfall_interval_value",
    "rainfall_interval_lifecycle",
    "rainfall_analysis_revision",
)


def upgrade():
    op.create_table(
        "rainfall_source_eligibility",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("evidence_revision", sa.String(64), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criteria", postgresql.JSONB(), nullable=False),
        sa.Column("failed_criteria", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "source_id", "role", "evidence_revision", name="uq_rainfall_eligibility_evidence"
        ),
    )
    op.create_table(
        "rainfall_interval_value",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column("scope_version", sa.String(128), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_revision", sa.String(128), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "interval_start",
            "interval_end",
            "provider_revision",
            name="uq_rainfall_interval_revision",
        ),
    )
    op.create_table(
        "rainfall_interval_lifecycle",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interval_value_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_rainfall_interval_lifecycle_value", "rainfall_interval_lifecycle", ["interval_value_id"]
    )
    op.create_table(
        "rainfall_analysis_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_fingerprint", sa.String(128), nullable=False),
        sa.Column("policy_revision", sa.String(64), nullable=False),
        sa.Column("data_revision", sa.String(128), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "request_fingerprint",
            "policy_revision",
            "data_revision",
            name="uq_rainfall_analysis_snapshot",
        ),
    )
    op.create_table(
        "rainfall_backfill_checkpoint",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column("scope_version", sa.String(128), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "source_id",
            "scope_kind",
            "scope_id",
            "scope_version",
            "year",
            name="uq_rainfall_backfill_source_scope_version_year",
        ),
    )
    op.execute("""
        CREATE FUNCTION prevent_rainfall_audit_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_TABLE_NAME = 'rainfall_interval_value'
               AND TG_OP = 'DELETE'
               AND current_setting('app.rainfall_expiry_purge', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'rainfall audit rows are append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in _IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION prevent_rainfall_audit_mutation()"
        )
    op.execute("""
        CREATE FUNCTION purge_expired_rainfall_intervals(p_cutoff timestamptz) RETURNS integer AS $$
        DECLARE deleted_count integer;
        BEGIN
            PERFORM set_config('app.rainfall_expiry_purge', 'on', true);
            DELETE FROM rainfall_interval_value AS value
            USING rainfall_interval_lifecycle AS lifecycle
            WHERE lifecycle.interval_value_id = value.id
              AND lifecycle.event_type = 'expired'
              AND lifecycle.expires_at IS NOT NULL
              AND lifecycle.expires_at <= p_cutoff;
            GET DIAGNOSTICS deleted_count = ROW_COUNT;
            RETURN deleted_count;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.create_index(
        "ix_rainfall_interval_lookup",
        "rainfall_interval_value",
        ["source_id", "scope_kind", "scope_id", "scope_version", "interval_start"],
    )


def downgrade():
    op.execute("DROP FUNCTION purge_expired_rainfall_intervals(timestamptz)")
    for table in _IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION prevent_rainfall_audit_mutation()")
    op.drop_table("rainfall_backfill_checkpoint")
    op.drop_table("rainfall_analysis_revision")
    op.drop_index("ix_rainfall_interval_lifecycle_value", table_name="rainfall_interval_lifecycle")
    op.drop_table("rainfall_interval_lifecycle")
    op.drop_table("rainfall_interval_value")
    op.drop_table("rainfall_source_eligibility")
