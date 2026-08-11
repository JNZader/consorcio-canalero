"""RAG corpus schema: rag_corpus, rag_documento, rag_unidad.

Runs everywhere, CI-safe — no pgvector dependency. The conditional
embedding column lives in `conocimiento_002_pgvector_embeddings`.

Revision ID: conocimiento_001
Revises: lluvia_v2_005
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import Computed

revision: str = "conocimiento_001"
down_revision: Union[str, None] = "lluvia_v2_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must stay identical to `app.domains.conocimiento.models.RAG_UNIDAD_TSV_EXPRESSION`
# — the 2-arg `to_tsvector('spanish', ...)` form is IMMUTABLE (required for
# a generated column); the 1-arg form is only STABLE and Postgres rejects
# it here. The literal `'spanish'` is load-bearing, not style (design.md D1).
_RAG_UNIDAD_TSV_EXPRESSION = (
    "setweight(to_tsvector('spanish', coalesce(epigrafe, '')), 'A') || "
    "setweight(to_tsvector('spanish', texto_indexado), 'B')"
)


def upgrade() -> None:
    op.create_table(
        "rag_corpus",
        sa.Column("corpus_sha", sa.CHAR(40), primary_key=True),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column(
            "articulos_declarados",
            sa.Integer(),
            nullable=False,
            comment=(
                "Count of tipo_chunk='articulo' units only (the MANIFEST's "
                "declared total, 1383). Distinct from the corpus's total "
                "row count in rag_unidad, which also includes non-article "
                "tipo_chunk values (considerando, guia-de-uso, "
                "nota-vigencia, ficha-registral, seccion-secundaria)."
            ),
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "rag_documento",
        sa.Column("corpus_sha", sa.CHAR(40), primary_key=True),
        sa.Column("documento_id", sa.Text(), primary_key=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("es_secundaria", sa.Boolean(), nullable=False),
        sa.Column("jurisdiccion", sa.Text(), nullable=False),
        sa.Column("estado_vigencia", sa.Text(), nullable=False),
        sa.Column("relevancia_consorcio", sa.Text(), nullable=True),
        sa.Column("verificacion", sa.Text(), nullable=True),
        sa.Column(
            "clasificacion",
            sa.Text(),
            nullable=False,
            server_default="privado",
        ),
        sa.Column("fuente_url", sa.Text(), nullable=True),
        sa.Column("fecha_sancion", sa.Date(), nullable=True),
        sa.Column("fecha_bo", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["corpus_sha"],
            ["rag_corpus.corpus_sha"],
            name="fk_rag_documento_corpus",
        ),
        sa.CheckConstraint(
            "clasificacion IN ('publico', 'privado')",
            name="ck_rag_documento_clasificacion",
        ),
    )

    op.create_table(
        "rag_unidad",
        sa.Column("corpus_sha", sa.CHAR(40), primary_key=True),
        sa.Column("citation_key", sa.Text(), primary_key=True),
        sa.Column("documento_id", sa.Text(), nullable=False),
        sa.Column("tipo_chunk", sa.Text(), nullable=False),
        sa.Column("epigrafe", sa.Text(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("texto_indexado", sa.Text(), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("source_offset", sa.Integer(), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            Computed(_RAG_UNIDAD_TSV_EXPRESSION, persisted=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["corpus_sha", "documento_id"],
            ["rag_documento.corpus_sha", "rag_documento.documento_id"],
            name="fk_rag_unidad_documento",
        ),
        sa.CheckConstraint(
            "tipo_chunk IN ('articulo','considerando','guia-de-uso',"
            "'nota-vigencia','ficha-registral','seccion-secundaria')",
            name="ck_rag_unidad_tipo_chunk",
        ),
    )
    op.create_index("ix_rag_unidad_tsv", "rag_unidad", ["tsv"], postgresql_using="gin")
    op.create_index("ix_rag_unidad_documento", "rag_unidad", ["corpus_sha", "documento_id"])


def downgrade() -> None:
    # Drops all three tables (rag_unidad, rag_documento, rag_corpus) — the
    # embedding column and its index are dropped separately by
    # conocimiento_002's downgrade, which always runs first since it is the
    # later migration in the chain.
    op.drop_index("ix_rag_unidad_documento", table_name="rag_unidad")
    op.drop_index("ix_rag_unidad_tsv", table_name="rag_unidad")
    op.drop_table("rag_unidad")
    op.drop_table("rag_documento")
    op.drop_table("rag_corpus")
