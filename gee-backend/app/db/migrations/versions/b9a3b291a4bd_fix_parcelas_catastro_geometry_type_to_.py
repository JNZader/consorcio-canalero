"""fix parcelas_catastro geometry type to generic

Revision ID: b9a3b291a4bd
Revises: 0015_add_territorial_tables
Create Date: 2026-04-06 18:12:54.674264

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b9a3b291a4bd"
down_revision: Union[str, Sequence[str], None] = "0015_add_territorial_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change geometria from Polygon to generic Geometry to support MultiPolygon features."""
    op.execute(
        "ALTER TABLE parcelas_catastro "
        "ALTER COLUMN geometria TYPE geometry(Geometry, 4326) "
        "USING geometria::geometry(Geometry, 4326)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE parcelas_catastro "
        "ALTER COLUMN geometria TYPE geometry(Polygon, 4326) "
        "USING ST_CollectionExtract(geometria, 3)::geometry(Polygon, 4326)"
    )
