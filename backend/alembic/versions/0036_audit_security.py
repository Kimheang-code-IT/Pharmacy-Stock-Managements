"""Audit hardening + security settings enforcement.

- audit_logs gains actor_email (survives a user delete), request_id (request
  correlation) and result (success|failure|denied). An append-only trigger
  blocks UPDATE/DELETE except an explicit archival purge.
- audit_logs_archive holds rows past the retention window.
- system_audit_events is a protected store (no foreign keys) for destructive
  operations; it is never touched by a business data reset.
- users gains password_changed_at, must_change_password, failed_login_attempts
  and locked_until so password expiry/forced change and DB-backed lockout are
  enforced even when Redis is unavailable.
- The system.* permission catalog rows are inserted.

Revision ID: 0036_audit_security
Revises: 0035_pos_refund_ledger
Create Date: 2026-09-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0036_audit_security"
down_revision = "0035_pos_refund_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Audit columns.
    op.add_column("audit_logs", sa.Column("actor_email", sa.String(255), nullable=True))
    op.add_column("audit_logs", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column(
        "audit_logs",
        sa.Column("result", sa.String(20), nullable=False, server_default="success"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    # 2. Archive table (same shape, no FK).
    op.create_table(
        "audit_logs_archive",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("module", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(20), nullable=False, server_default="success"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_logs_archive_created_at", "audit_logs_archive", ["created_at"]
    )

    # 3. Protected system-event store (no FKs, survives a business reset).
    op.create_table(
        "system_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("module", sa.String(100), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(100), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(20), nullable=False, server_default="success"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_system_audit_events_created_at", "system_audit_events", ["created_at"]
    )

    # 4. Append-only guard. UPDATE/DELETE are rejected unless the transaction
    #    explicitly opts in (`SET LOCAL app.allow_audit_purge = 'on'`), which is
    #    only done by the retention/archival job.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_block_mutation() RETURNS trigger AS $$
        BEGIN
            IF current_setting('app.allow_audit_purge', true) = 'on' THEN
                RETURN COALESCE(OLD, NEW);
            END IF;
            RAISE EXCEPTION 'audit_logs is append-only; use the archival job';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION system_audit_events_block_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'system_audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER system_audit_events_append_only
        BEFORE UPDATE OR DELETE ON system_audit_events
        FOR EACH ROW EXECUTE FUNCTION system_audit_events_block_mutation()
        """
    )

    # 5. Security lifecycle columns on users.
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    # Treat existing accounts as having a current password (do not force a
    # change on upgrade).
    op.execute("UPDATE users SET password_changed_at = now() WHERE password_changed_at IS NULL")

    # 6. system.* permission catalog rows (idempotent).
    op.execute(
        """
        INSERT INTO permissions (id, code, module, action, description)
        SELECT gen_random_uuid(), v.code, 'system', v.action, NULL
        FROM (
            VALUES ('system.maintenance', 'maintenance'),
                   ('system.data_reset', 'data_reset'),
                   ('system.backup', 'backup'),
                   ('system.restore', 'restore')
        ) AS v(code, action)
        WHERE NOT EXISTS (SELECT 1 FROM permissions p WHERE p.code = v.code)
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code LIKE 'system.%'")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "password_changed_at")

    op.execute("DROP TRIGGER IF EXISTS system_audit_events_append_only ON system_audit_events")
    op.execute("DROP FUNCTION IF EXISTS system_audit_events_block_mutation()")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_block_mutation()")

    op.drop_index("ix_system_audit_events_created_at", table_name="system_audit_events")
    op.drop_table("system_audit_events")
    op.drop_index("ix_audit_logs_archive_created_at", table_name="audit_logs_archive")
    op.drop_table("audit_logs_archive")

    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_column("audit_logs", "result")
    op.drop_column("audit_logs", "request_id")
    op.drop_column("audit_logs", "actor_email")
