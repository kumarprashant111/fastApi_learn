"""add project_id to supply points

Revision ID: 64cfbdb3686e
Revises: 5c281855dfe4
Create Date: 2025-10-10 14:53:19.798834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64cfbdb3686e'
down_revision: Union[str, Sequence[str], None] = '5c281855dfe4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
