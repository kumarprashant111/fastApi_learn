"""add project_id to supply points

Revision ID: 5c281855dfe4
Revises: 20251010_add_project_id_to_supply_points
Create Date: 2025-10-10 14:44:56.561470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c281855dfe4'
down_revision: Union[str, Sequence[str], None] = '20251010_add_project_id_to_supply_points'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
