"""ORM models for Fase B — mirrors ``0023_add_relevamiento_tramo`` column for column.

Two tables and one view, and the reasons they are shaped this way are in design
D4. The short version, because each one is a rule somebody could otherwise
"simplify" away:

* ``version`` is a ``BIGSERIAL`` and it is what orders the history.
  ``relevado_en`` defaults to ``now()``, which is **transaction-start** time, so
  two overlapping transactions can stamp it identically or in the opposite order
  to their commits — and ``id`` is a random UUIDv4, whose tie-break is
  lexicographic accident. ``relevado_en`` is for display only.
* The cuneta combination rule lives in a table-level CHECK, not in the service.
* ``TramoClasificacionCandidata`` is keyed ``(tramo_ref, geo_job_id)``;
  ``dem_layer_id`` carries **no** FK and is allowed to dangle.

The ``relevamiento_tramo_vigente`` view is attached to the table's ``after_create``
event so the test schema — built from ``Base.metadata.create_all`` — has it too.
Production DDL is owned by the migration; ``test_relevamiento_repository`` asserts
the two texts have not drifted apart.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    DDL,
    Float,
    ForeignKey,
    Index,
    Sequence,
    Text,
    event,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin

#: The current-state query, kept as ONE definition so the model-side view and the
#: migration cannot drift into two different answers to "which record wins".
VIGENTE_VIEW_NAME = "relevamiento_tramo_vigente"

VIGENTE_VIEW_SELECT = """
    SELECT DISTINCT ON (tramo_ref)
           id, tramo_ref, nivel_relativo, tiene_cuneta, estado_cuneta, observaciones,
           relevado_por, relevado_en, version, nivel_desde_candidata,
           created_at, updated_at
      FROM relevamiento_tramo
     ORDER BY tramo_ref, version DESC
"""


class RelevamientoTramo(UUIDMixin, TimestampMixin, Base):
    """One field survey of one road segment. Append-only, author-attributed.

    ``relevado_por`` is ``NOT NULL`` and there is no update path in the
    repository, which together are the whole of RSS-R1's "no record without an
    identified author; the author is not alterable afterwards".

    ``nivel_desde_candidata`` records whether the stored level was **accepted**
    from the DEM candidate or **chosen** by the operator. Without it, "confirmed
    the suggestion" and "entered the value" are the same row, the design's claim
    that no field is stored as a value the operator did not give is
    unverifiable, and the coverage split cannot tell a surveyed segment from a
    rubber-stamped candidate.
    """

    __tablename__ = "relevamiento_tramo"
    __table_args__ = (
        CheckConstraint(
            "nivel_relativo IN ('menor', 'igual', 'mayor')",
            name="ck_relevamiento_nivel_relativo",
        ),
        CheckConstraint(
            "tiene_cuneta IN ('si', 'no', 'parcial')",
            name="ck_relevamiento_tiene_cuneta",
        ),
        CheckConstraint(
            "estado_cuneta IS NULL OR estado_cuneta IN ('limpia', 'colmatada')",
            name="ck_relevamiento_estado_cuneta_valores",
        ),
        # The COMBINATION rule, at table level on purpose: a rule enforced only
        # in the service is a rule psql and any future ETL bypass.
        CheckConstraint(
            "(tiene_cuneta = 'no' AND estado_cuneta IS NULL)"
            " OR (tiene_cuneta <> 'no' AND estado_cuneta IS NOT NULL)",
            name="ck_relevamiento_cuneta_combinacion",
        ),
        Index("ix_relevamiento_tramo_version", "tramo_ref", sa.text("version DESC")),
    )

    tramo_ref: Mapped[str] = mapped_column(
        Text,
        ForeignKey("red_vial.id", ondelete="RESTRICT"),
        nullable=False,
        comment="The surveyed segment; roads are retired, never deleted",
    )
    nivel_relativo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Road level against the surrounding terrain: menor | igual | mayor",
    )
    tiene_cuneta: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="si | no | parcial",
    )
    estado_cuneta: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="limpia | colmatada; NULL iff tiene_cuneta = 'no'",
    )
    observaciones: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Free-text note. An observation, never a dimension",
    )
    relevado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="The author. Never rewritten, never published",
    )
    relevado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
        comment="DISPLAY ONLY: transaction-start time, never the ordering key",
    )
    version: Mapped[int] = mapped_column(
        BigInteger,
        # A real sequence, so ``create_all`` builds the same ``BIGSERIAL`` the
        # migration does and the ordering key exists in the test schema too.
        #
        # The ``server_default`` is NOT redundant with the ``Sequence``: a
        # ``Sequence`` on a non-primary-key column is applied by the ORM at
        # INSERT time and is NOT rendered as a column DEFAULT in the emitted
        # DDL, so a plain SQL ``INSERT`` — which is exactly what the append-only
        # repository issues — would leave the column NULL. ``BIGSERIAL`` in the
        # migration is precisely this pair, and the sequence names match.
        Sequence("relevamiento_tramo_version_seq"),
        server_default=sa.text("nextval('relevamiento_tramo_version_seq')"),
        nullable=False,
        unique=True,
        comment="The total order: assigned at INSERT, unique by construction",
    )
    nivel_desde_candidata: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=sa.text("false"),
        comment="True only when the level was accepted as pre-filled from the candidate",
    )

    def __repr__(self) -> str:
        return f"<RelevamientoTramo tramo={self.tramo_ref} version={self.version}>"


class TramoClasificacionCandidata(Base):
    """What the DEM suggested for a segment, on one run. Never authoritative.

    Keyed ``(tramo_ref, geo_job_id)``: ``dem_layer_id`` is not a run identifier —
    ``upsert_layer`` mutates a layer row in place keeping the same UUID, and
    ``delete_layers_by_area_id`` wipes those rows outright — so it is kept as
    informational provenance with **no FK**, allowed to dangle. A candidate whose
    job's rasters are gone is a recorded past computation, not a live pointer, and
    it stays readable and pre-fillable.
    """

    __tablename__ = "tramo_clasificacion_candidata"
    __table_args__ = (
        CheckConstraint(
            "clasificacion_candidata IN ('terraplen', 'canal', 'neutro')",
            name="ck_candidata_clasificacion",
        ),
        Index("ix_tramo_candidata_reciente", "tramo_ref", sa.text("calculada_en DESC")),
    )

    tramo_ref: Mapped[str] = mapped_column(
        Text,
        ForeignKey("red_vial.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    geo_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geo_jobs.id"),
        primary_key=True,
        comment="The run that produced this guess. Fresh per run, never reused",
    )
    dem_layer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Informational provenance only — NO FK, allowed to dangle",
    )
    clasificacion_candidata: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="terraplen | canal | neutro",
    )
    confianza_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="SIGNED median(road) - median(flank), in metres",
    )
    calculada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<TramoClasificacionCandidata tramo={self.tramo_ref} "
            f"clasificacion={self.clasificacion_candidata}>"
        )


# The view is part of the schema, not of the ORM: it is created right after its
# base table so a ``Base.metadata.create_all`` schema (the test one) can read
# current state exactly the way production does.
event.listen(
    RelevamientoTramo.__table__,
    "after_create",
    DDL(f"CREATE OR REPLACE VIEW {VIGENTE_VIEW_NAME} AS {VIGENTE_VIEW_SELECT}"),
)
event.listen(
    RelevamientoTramo.__table__,
    "before_drop",
    DDL(f"DROP VIEW IF EXISTS {VIGENTE_VIEW_NAME}"),
)


__all__ = [
    "RelevamientoTramo",
    "TramoClasificacionCandidata",
    "VIGENTE_VIEW_NAME",
    "VIGENTE_VIEW_SELECT",
]
