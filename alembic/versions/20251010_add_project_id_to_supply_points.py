# alembic/versions/20251010_add_project_id_to_supply_points.py
from alembic import op
import sqlalchemy as sa

revision = "20251010_add_project_id_to_supply_points"
down_revision = "20251009_create_ppa_bundle_project_supply_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) add column only if missing
    cols = {c["name"] for c in insp.get_columns("ppa_supply_points")}
    if "project_id" not in cols:
        op.add_column(
            "ppa_supply_points",
            sa.Column("project_id", sa.Integer(), nullable=True),
        )

    # 2) FK only if missing
    fks = {fk["name"] for fk in insp.get_foreign_keys("ppa_supply_points")}
    if "fk_ppa_supply_points_project_id_ppa_projects" not in fks:
        op.create_foreign_key(
            "fk_ppa_supply_points_project_id_ppa_projects",
            "ppa_supply_points",
            "ppa_projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 3) index only if missing
    idxs = {ix["name"] for ix in insp.get_indexes("ppa_supply_points")}
    if "ix_ppa_supply_points_project_id" not in idxs:
        op.create_index(
            "ix_ppa_supply_points_project_id",
            "ppa_supply_points",
            ["project_id"],
            unique=False,
        )

    # 4) optional backfill – wrap in DO block so it’s safe to re-run
    op.execute(
        """
        DO $$
        BEGIN
          -- naive backfill: if project_id is null, set it to the smallest project in the same bundle
          UPDATE ppa_supply_points sp
          SET project_id = fp.project_id
          FROM (
            SELECT bundle_id, MIN(id) AS project_id
            FROM ppa_projects
            GROUP BY bundle_id
          ) fp
          WHERE sp.project_id IS NULL AND sp.bundle_id = fp.bundle_id;
        END $$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # drop index if exists
    idxs = {ix["name"] for ix in insp.get_indexes("ppa_supply_points")}
    if "ix_ppa_supply_points_project_id" in idxs:
        op.drop_index("ix_ppa_supply_points_project_id", table_name="ppa_supply_points")

    # drop FK if exists
    fks = {fk["name"] for fk in insp.get_foreign_keys("ppa_supply_points")}
    if "fk_ppa_supply_points_project_id_ppa_projects" in fks:
        op.drop_constraint(
            "fk_ppa_supply_points_project_id_ppa_projects",
            "ppa_supply_points",
            type_="foreignkey",
        )

    # drop column if exists
    cols = {c["name"] for c in insp.get_columns("ppa_supply_points")}
    if "project_id" in cols:
        op.drop_column("ppa_supply_points", "project_id")
