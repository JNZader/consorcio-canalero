"""conocimiento_003: scope estado_vigencia NOT NULL to derecho aplicable

Discovered while ingesting the real corpus at the pinned SHA
`12043582bf8016288a7e8084e85a4b713a97af2f`: **three of the thirty-five
documents carry no `estado_vigencia` key at all** —
`informe-f3-sujeto-expropiante.md`, `informe-zona-de-camino-cordoba.md` and
`jurisprudencia-potrerillo-larreta-2017.md`. All three are fuente secundaria
(two `informe-operativo`, one `jurisprudencia`).

That is not a corpus defect, it is a category boundary: "estado de vigencia" is
a property of a norm. An operational report has no vigencia, and a first-instance
judgment's *firmeza* was explicitly never verified (`MANIFEST.md`, tabla de
normas) — so any value written there would be invented, which is precisely what
the ingestion spec forbids for carried frontmatter fields.

Migration 001 declared the column NOT NULL, which would have made the corpus
un-ingestable. Rather than invent a placeholder, the constraint is scoped to
where it is actually true: `estado_vigencia` is now nullable at the column
level, and a CHECK enforces NOT NULL for every document that IS derecho
aplicable (`es_secundaria = false`). The guarantee that matters — a norm always
travels with its vigencia state — is preserved and now enforced by the database
instead of by convention.

Revision ID: conocimiento_003
Revises: conocimiento_002
"""

from typing import Sequence, Union

from alembic import op

revision: str = "conocimiento_003"
down_revision: Union[str, None] = "conocimiento_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECK_NAME = "ck_rag_documento_estado_vigencia_derecho_aplicable"
CHECK_CONDITION = "es_secundaria OR estado_vigencia IS NOT NULL"

# Same ingestion pass, second discovered gap: three units in the pinned corpus
# are normative content that is not articulado and fits none of D2's six
# `tipo_chunk` values — the `## Anexo` of Ley 25.506 and Anexos I and XI of Res.
# DNV 908/2026. See `models.TIPO_CHUNK_VALUES` for the reasoning.
TIPO_CHUNK_NAME = "ck_rag_unidad_tipo_chunk"
TIPO_CHUNK_OLD = (
    "tipo_chunk IN ('articulo','considerando','guia-de-uso',"
    "'nota-vigencia','ficha-registral','seccion-secundaria')"
)
TIPO_CHUNK_NEW = (
    "tipo_chunk IN ('articulo','considerando','guia-de-uso',"
    "'nota-vigencia','ficha-registral','seccion-secundaria','anexo-normativo')"
)


def upgrade() -> None:
    op.alter_column("rag_documento", "estado_vigencia", nullable=True)
    op.create_check_constraint(CHECK_NAME, "rag_documento", CHECK_CONDITION)

    op.drop_constraint(TIPO_CHUNK_NAME, "rag_unidad", type_="check")
    op.create_check_constraint(TIPO_CHUNK_NAME, "rag_unidad", TIPO_CHUNK_NEW)


def downgrade() -> None:
    op.drop_constraint(TIPO_CHUNK_NAME, "rag_unidad", type_="check")
    op.create_check_constraint(TIPO_CHUNK_NAME, "rag_unidad", TIPO_CHUNK_OLD)

    # Drop the scoped constraint first: restoring the blanket NOT NULL makes it
    # redundant, and leaving both would be two rules for one invariant.
    op.drop_constraint(CHECK_NAME, "rag_documento", type_="check")
    op.alter_column("rag_documento", "estado_vigencia", nullable=False)
