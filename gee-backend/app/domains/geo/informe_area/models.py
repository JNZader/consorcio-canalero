"""``informes_area`` — one background informe de área per row (PR 2, T1).

House conventions: UUID PK + timestamps via the shared mixins, estado drawn
from the EXISTING ``estado_geo_job`` enum (pending/running/completed/failed —
the informe is a job like any geo job, and reusing the type keeps one status
vocabulary), and JSONB for ``parametros`` / ``resultado`` (nested documents
that T3's UI reads key by key).

The row is PRIVATE (S11): every read path filters by ``usuario_id`` first,
and the only index that serves a cache lookup includes ``usuario_id`` so a
cache probe can never cross users.

Cache identity (S4) is stored, not recomputed on read:

* ``hash_seleccion`` — sha256 of the NORMALIZED selection geometry (union,
  ``ST_SnapToGrid`` 1e-7, WKB bytes) plus the sorted zona ids. Two selections
  of the same zonas in any order collide on purpose.
* ``version_clave`` — ``hash_seleccion`` PLUS the version of every layer the
  informe reads plus ``version_plantilla``. A layer refresh changes the clave,
  which is the whole invalidation mechanism: there is no purge job, an
  expired clave simply stops matching.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.domains.geo.models import EstadoGeoJob

VERSION_CLAVE_MAX = 600


class InformeArea(UUIDMixin, TimestampMixin, Base):
    """A user's background informe over a multi-subcuenca selection."""

    __tablename__ = "informes_area"
    __table_args__ = (
        # The cache probe: same user + same clave + completed → reuse the row.
        Index("ix_informes_area_usuario_version", "usuario_id", "version_clave"),
        # The retention sweep scans this daily (S11).
        Index("ix_informes_area_vence_at", "vence_at"),
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Who requested the informe — the only eye that sees it (S11)",
    )
    nombre: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User-facing label shown in Mis informes",
    )
    estado: Mapped[EstadoGeoJob] = mapped_column(
        Enum(
            EstadoGeoJob,
            name="estado_geo_job",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EstadoGeoJob.PENDING,
    )
    hash_seleccion: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="sha256 of the normalized union geometry + sorted zona ids (S4)",
    )
    version_clave: Mapped[str] = mapped_column(
        String(VERSION_CLAVE_MAX),
        nullable=False,
        comment=("Cache key: hash_seleccion + per-layer versions + version_plantilla"),
    )
    parametros: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Input selection: {zona_ids: [...], desglose: bool}",
    )
    resultado: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Totals + per-subcuenca desglose summary once completed",
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Readable failure reason shown to the user (S8)",
    )
    progreso: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Completion percentage 0-100",
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Preallocated Celery task id from the outbox publication",
    )
    vence_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Retention deadline; the daily sweep deletes past it (S11)",
    )
    # T2 storage decision: DB bytea over a filesystem path under the geo
    # volume. The PDF is ≤ 5 MB (S9), the retention sweep already deletes the
    # row (a file would need a second, orphan-prone cleanup), and BOTH the
    # worker (writer) and the API (reader) see the bytes with zero volume
    # coupling. ``deferred`` keeps the bytea OUT of every listing/cache-probe
    # SELECT — it loads only when the download path touches the attribute.
    pdf_bytes: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        deferred=True,
        nullable=True,
        comment="Rendered PDF (bytea, ≤5MB per S9); deferred so listings never load it",
    )

    def __repr__(self) -> str:
        return f"<InformeArea {self.id} estado={self.estado} usuario={self.usuario_id}>"
