# alembic/versions/20251009_create_ppa_bundle_project_supply_points.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20251009_create_ppa_bundle_project_supply_points"
down_revision = "4cdcfa48ce3e"
branch_labels = None
depends_on = None


def _safe_create_enum(enum_name: str, labels: list[str]) -> None:
    # Build `'A','B','C'`
    labels_sql = ", ".join([f"'{l}'" for l in labels])
    # Use dollar-quoted EXECUTE so inner single quotes are fine
    op.execute(
        f"""
        DO $do$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = '{enum_name}'
          ) THEN
            EXECUTE $$CREATE TYPE {enum_name} AS ENUM ({labels_sql})$$;
          END IF;
        EXCEPTION
          WHEN duplicate_object THEN
            -- race-safe: ignore if created in parallel
            NULL;
        END $do$;
        """
    )


def upgrade() -> None:
    # 1) Ensure enums exist once
    _safe_create_enum("voltagelevel", ["HIGH", "EXTRA_HIGH", "LOW"])
    _safe_create_enum("ppaqstatus", ["DRAFT", "SUBMITTED", "PRICED", "EXCEL_READY"])
    _safe_create_enum("ppaofferstatus", ["NONE", "OFFERED", "WON", "LOST"])

    # 2) Bind columns to these existing types without creating them again
    voltagelevel = postgresql.ENUM(name="voltagelevel", create_type=False)
    ppaqstatus = postgresql.ENUM(name="ppaqstatus", create_type=False)
    ppaofferstatus = postgresql.ENUM(name="ppaofferstatus", create_type=False)

    # --- ppa_bundles
    op.create_table(
        "ppa_bundles",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("agency_id", sa.Integer(), sa.ForeignKey("agencies.id"), nullable=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), nullable=False),

        sa.Column("voltage", voltagelevel, nullable=False),
        sa.Column("area", sa.String(32), nullable=False),
        sa.Column("prev_supplier_plan", sa.String(120), nullable=True),

        sa.Column("contract_start_date", sa.Date(), nullable=True),
        sa.Column("quote_valid_days", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.Date(), nullable=True),
        sa.Column("request_due_date", sa.Date(), nullable=True),

        sa.Column("quote_status", ppaqstatus, nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("offer_status", ppaofferstatus, nullable=False, server_default=sa.text("'NONE'")),

        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ppa_bundles_customer_id", "ppa_bundles", ["customer_id"])
    op.create_index("ix_ppa_bundles_agency_id", "ppa_bundles", ["agency_id"])
    op.create_index("ix_ppa_bundles_plan_id", "ppa_bundles", ["plan_id"])

    # --- ppa_projects
    op.create_table(
        "ppa_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bundle_id", sa.Integer(), sa.ForeignKey("ppa_bundles.id"), nullable=False),
        sa.Column("capacity_mw", sa.Float(), nullable=False),
        sa.Column("ppa_unit_price_yen_per_kwh", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ppa_projects_bundle_id", "ppa_projects", ["bundle_id"])

    # --- ppa_supply_points
    op.create_table(
        "ppa_supply_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bundle_id", sa.Integer(), sa.ForeignKey("ppa_bundles.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("supply_point_number", sa.String(64), nullable=True),
        sa.Column("contract_kw", sa.Float(), nullable=True, server_default="0"),
    )
    op.create_index("ix_ppa_supply_points_bundle_id", "ppa_supply_points", ["bundle_id"])
    op.create_index("ix_ppa_supply_points_spn", "ppa_supply_points", ["supply_point_number"])


def downgrade() -> None:
    op.drop_index("ix_ppa_supply_points_spn", table_name="ppa_supply_points")
    op.drop_index("ix_ppa_supply_points_bundle_id", table_name="ppa_supply_points")
    op.drop_table("ppa_supply_points")

    op.drop_index("ix_ppa_projects_bundle_id", table_name="ppa_projects")
    op.drop_table("ppa_projects")

    op.drop_index("ix_ppa_bundles_plan_id", table_name="ppa_bundles")
    op.drop_index("ix_ppa_bundles_agency_id", table_name="ppa_bundles")
    op.drop_index("ix_ppa_bundles_customer_id", table_name="ppa_bundles")
    op.drop_table("ppa_bundles")

    # Optionally drop enums in dev
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_type WHERE typname='ppaofferstatus') THEN DROP TYPE ppaofferstatus; END IF; END $$;")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_type WHERE typname='ppaqstatus') THEN DROP TYPE ppaqstatus; END IF; END $$;")
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_type WHERE typname='voltagelevel') THEN DROP TYPE voltagelevel; END IF; END $$;")
