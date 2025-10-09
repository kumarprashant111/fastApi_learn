"""merge heads after created_at default

Revision ID: 25bfd00998ba
Revises: 701c13325998, abcd1234addserverdefault
Create Date: 2025-10-09 14:07:58.972996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25bfd00998ba'
down_revision: Union[str, Sequence[str], None] = ('701c13325998', 'abcd1234addserverdefault')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
