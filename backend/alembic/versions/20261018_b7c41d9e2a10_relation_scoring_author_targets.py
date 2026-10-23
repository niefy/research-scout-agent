"""relation scoring, author-targeted crawling, digests

Revision ID: b7c41d9e2a10
Revises: f1a7b16d75e8
Create Date: 2026-10-18 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7c41d9e2a10"
down_revision = "f1a7b16d75e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("authors") as batch:
        batch.add_column(
            sa.Column("is_curated", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("curated_rank", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )
        batch.add_column(
            sa.Column("crawl_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(
            sa.Column(
                "quality_score", sa.Float(), nullable=False, server_default=sa.text("0.5")
            )
        )
        batch.add_column(
            sa.Column(
                "sector_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch.add_column(sa.Column("last_crawled_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column(
                "crawl_status",
                sa.String(length=24),
                nullable=False,
                server_default=sa.text("'idle'"),
            )
        )
        batch.add_column(sa.Column("crawl_error", sa.String(length=512)))
    op.create_index("ix_authors_is_curated", "authors", ["is_curated"])

    with op.batch_alter_table("ingest_runs") as batch:
        batch.add_column(sa.Column("author_id", sa.Integer()))
    op.create_index("ix_ingest_runs_author_id", "ingest_runs", ["author_id"])

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "digest_email_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("stock_score_snapshots") as batch:
        batch.add_column(
            sa.Column(
                "total_points", sa.Float(), nullable=False, server_default=sa.text("0")
            )
        )
        batch.add_column(
            sa.Column(
                "relation_counts",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.add_column(
            sa.Column(
                "evidence_level",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'none'"),
            )
        )
        batch.add_column(
            sa.Column(
                "evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
            )
        )
    op.create_index(
        "ix_snapshot_user_security_scope_time",
        "stock_score_snapshots",
        ["user_id", "security_id", "scope", "window", "computed_at"],
    )
    op.create_index(
        "ix_snapshot_security_time",
        "stock_score_snapshots",
        ["security_id", "computed_at"],
    )

    op.execute(
        "UPDATE stock_score_snapshots "
        "SET total_points = (final_score + 1) * 50 "
        "WHERE total_points = 0"
    )
    op.execute(
        "UPDATE stock_score_snapshots SET scope = 'personal' WHERE scope = 'followed'"
    )

    op.create_table(
        "report_security_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("security_id", sa.Integer(), nullable=False),
        sa.Column(
            "action",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'irrelevant'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"]),
        sa.ForeignKeyConstraint(["security_id"], ["securities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "report_id", "security_id", name="uq_report_security_feedback"
        ),
    )
    op.create_index(
        "ix_report_security_feedback_user_id",
        "report_security_feedback",
        ["user_id"],
    )
    op.create_index(
        "ix_report_security_feedback_report_id",
        "report_security_feedback",
        ["report_id"],
    )
    op.create_index(
        "ix_report_security_feedback_security_id",
        "report_security_feedback",
        ["security_id"],
    )
    op.create_index(
        "ix_report_security_feedback_user_security",
        "report_security_feedback",
        ["user_id", "security_id"],
    )

    op.create_table(
        "digest_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'email'"),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("error", sa.String(length=512)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "digest_date", "channel", name="uq_digest_delivery"),
    )
    op.create_index("ix_digest_deliveries_user_id", "digest_deliveries", ["user_id"])
    op.create_index(
        "ix_digest_delivery_date", "digest_deliveries", ["digest_date", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_digest_delivery_date", table_name="digest_deliveries")
    op.drop_index("ix_digest_deliveries_user_id", table_name="digest_deliveries")
    op.drop_table("digest_deliveries")

    op.drop_index(
        "ix_report_security_feedback_user_security",
        table_name="report_security_feedback",
    )
    op.drop_index(
        "ix_report_security_feedback_security_id",
        table_name="report_security_feedback",
    )
    op.drop_index(
        "ix_report_security_feedback_report_id",
        table_name="report_security_feedback",
    )
    op.drop_index(
        "ix_report_security_feedback_user_id",
        table_name="report_security_feedback",
    )
    op.drop_table("report_security_feedback")

    op.drop_index(
        "ix_snapshot_security_time", table_name="stock_score_snapshots"
    )
    op.drop_index(
        "ix_snapshot_user_security_scope_time", table_name="stock_score_snapshots"
    )
    with op.batch_alter_table("stock_score_snapshots") as batch:
        batch.drop_column("evidence")
        batch.drop_column("evidence_level")
        batch.drop_column("relation_counts")
        batch.drop_column("total_points")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("digest_email_enabled")

    op.drop_index("ix_ingest_runs_author_id", table_name="ingest_runs")
    with op.batch_alter_table("ingest_runs") as batch:
        batch.drop_column("author_id")

    op.drop_index("ix_authors_is_curated", table_name="authors")
    with op.batch_alter_table("authors") as batch:
        batch.drop_column("crawl_error")
        batch.drop_column("crawl_status")
        batch.drop_column("last_crawled_at")
        batch.drop_column("sector_tags")
        batch.drop_column("quality_score")
        batch.drop_column("crawl_enabled")
        batch.drop_column("curated_rank")
        batch.drop_column("is_curated")
