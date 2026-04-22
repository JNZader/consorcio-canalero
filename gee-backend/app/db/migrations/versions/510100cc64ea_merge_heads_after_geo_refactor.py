"""merge heads after geo refactor

Revision ID: 510100cc64ea
Revises: c1r9v0w1x2y159, zz_mgmt_indexes
Create Date: 2026-04-22 13:57:48.548855

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "510100cc64ea"
down_revision: Union[str, Sequence[str], None] = ("c1r9v0w1x2y159", "zz_mgmt_indexes")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
