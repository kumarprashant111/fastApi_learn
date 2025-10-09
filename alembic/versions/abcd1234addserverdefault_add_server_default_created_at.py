# alembic/versions/xxxx_add_server_default_created_at.py
from alembic import op
import sqlalchemy as sa

# alembic/versions/abcd1234_add_server_default_created_at.py

revision = "abcd1234addserverdefault"   # any unique string; use the one Alembic generated
down_revision = "f87c8c64ff32"          # <-- put the actual head id from step 1
branch_labels = None
depends_on = None


def upgrade():
    # backfill existing NULLs, if any
    op.execute("UPDATE recontract_estimates SET created_at = NOW() WHERE created_at IS NULL;")
    # add server default
    op.alter_column(
        "recontract_estimates",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=sa.text("now()"),
    )

def downgrade():
    op.alter_column(
        "recontract_estimates",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=None,
    )
