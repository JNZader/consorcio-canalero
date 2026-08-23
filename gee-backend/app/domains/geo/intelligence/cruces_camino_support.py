"""Support for the road-crossing run: variant resolution, snapshot-copy, staleness.

Everything here exists because the crossing task **reads rasters the DEM
pipeline owns and rewrites**, and because "which drainage variant did this rank
list come from" must be an answerable question rather than a guess.

Three mechanisms, each with its own reason:

* :func:`resolver_variante_drenaje` — resolves the pair **by exact name**, and
  substitutes the operational pair only under a *verified* no-burn condition.
* the snapshot-copy protocol (:func:`verificar_dem_libre`,
  :func:`copiar_rasters_a_scratch`) — makes the reader independent of the
  writer's timing instead of trying to interleave with it.
* :func:`calcular_desactualizado` — turns "these crossings predate the current
  inputs" into a comparable fact.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

#: The two DEM job tipos, and BOTH are destructive.
#:
#: Round 2 claimed the plain pipeline "re-registers layers by UPSERT without the
#: wipe". That claim is false: ``run_dem_pipeline_impl`` calls
#: ``archive_previous_output`` immediately after claiming its job
#: (``tasks_dem_support.py:59-66``), and that helper **renames the whole
#: ``output/`` directory away** (``output_archive_support.py:60``) before
#: ``rmtree``-ing the oldest archives. The full pipeline is worse in degree, not
#: different in kind: ``cleanup_full_dem_state`` deletes the layer rows, COMMITs
#: at ``:557``, and only then empties the output directory from disk. So: every
#: DEM job tipo can move, truncate or delete the exact files this run reads, at
#: any moment during that read.
DEM_JOB_TIPOS: tuple[str, ...] = ("dem_pipeline", "dem_full_pipeline")

#: "Has reached RUNNING" — i.e. has already had the chance to destroy something.
#: Deliberately NOT ``completed`` only: ``full_dem_pipeline`` wipes the layer rows
#: and the output directory *immediately after claiming*, so a run that later
#: FAILS has already destroyed the rasters the crossings were computed from.
#: Under a COMPLETED-only rule the operator would keep reading a rank list
#: derived from files that no longer exist, with no warning at all.
ESTADOS_ALCANZO_RUNNING: tuple[str, ...] = ("running", "completed", "failed")

#: The pre-check also refuses on ``pending``: on the real dispatch path the API
#: creates the row as PENDING and the worker claims it after broker latency
#: (``service.py:99-112``), so a PENDING DEM row means destruction is imminent
#: and this run refuses early rather than racing it.
ESTADOS_DEM_OCUPADO: tuple[str, ...] = ("pending", "running")

#: ``GeoJob`` has **no area column** (``geo/models.py:165-220``) — the area lives
#: inside its ``parametros`` JSON, written as ``{"area_id": area_id, ...}`` by
#: both pipelines (``tasks_dem_support.py:41`` and ``:464``). ``parametros`` is a
#: SQLAlchemy ``JSON`` column, so the ``->>`` accessor needs an explicit
#: ``::jsonb`` cast; a silently non-matching JSON predicate returns "never
#: stale" and looks perfectly fine, which is why a real-PG test pins it.
#:
#: The comparison is plain ``text = text``: ``->>`` yields ``text`` and
#: ``cruce_camino.area_id`` is ``VARCHAR``, so there is **no ``::uuid`` cast on
#: either side** and no cast that could raise on a non-UUID area identifier.
_AREA_PREDICATE = "(parametros::jsonb)->>'area_id' = :area_id"

#: Adding an ``area_id`` column to ``geo_jobs`` was considered and rejected: it is
#: a shared table written by every geo task, backfilling it means rewriting
#: historical rows from their ``parametros``, and this feature needs one query,
#: not a schema change to a table it does not own.
SQL_DEM_JOB_OCUPADO = text(
    f"""
    SELECT 1 FROM geo_jobs
     WHERE tipo::text = ANY(:tipos)
       AND estado::text = ANY(:estados)
       AND {_AREA_PREDICATE}
     LIMIT 1
    """
)

SQL_DEM_JOB_INTERVINO = text(
    f"""
    SELECT 1 FROM geo_jobs
     WHERE tipo::text = ANY(:tipos)
       AND estado::text = ANY(:estados)
       AND updated_at >= :desde
       AND {_AREA_PREDICATE}
     LIMIT 1
    """
)

#: ``created_at``, not ``updated_at``, and the reason is directional.
#:
#: ``GeoJob`` inherits ``TimestampMixin``, so neither timestamp is "the moment
#: this job became RUNNING": ``created_at`` is stamped once at INSERT, and
#: ``updated_at`` is bumped by ``update_job_status_if_current`` on EVERY
#: compare-and-set — including every progress write — so on a finished job it
#: holds the moment of its *last* transition, potentially an hour after it
#: started. On the real dispatch path the API creates the job as PENDING and the
#: worker claims it after broker latency, so ``created_at`` is always at or
#: before the RUNNING transition. Comparing against the earlier of the two can
#: therefore only produce **false positives** — a dismissible notice — and never
#: a false negative, which would be a silently wrong ranking presented as
#: current. That asymmetry is the whole justification.
SQL_MAX_DEM_CREATED_AT = text(
    f"""
    SELECT max(created_at) FROM geo_jobs
     WHERE tipo::text = ANY(:tipos)
       AND estado::text = ANY(:estados)
       AND {_AREA_PREDICATE}
    """
)

#: Terrain is not the only input. A road reload changes the geometry the
#: crossings were derived from, and ``lado_cruce`` / ``rumbo_camino_deg`` are
#: defined relative to the segment's stored digitization direction — so a reload
#: that changes ONLY the vertex order (Hausdorff 0, so the loader correctly keeps
#: the id and the history) silently reverses the meaning of both stored values.
#: The loader is a module entry point, not a Celery task, and writes no
#: ``geo_jobs`` row, so ``red_vial.ultima_carga_en`` is the event to compare
#: against; inventing a synthetic job for a script would be worse than storing
#: the fact.
SQL_MAX_RED_VIAL_CARGA = text(
    """
    SELECT max(rv.ultima_carga_en) FROM red_vial rv
     WHERE rv.id IN (SELECT DISTINCT tramo_ref FROM cruce_camino WHERE area_id = :area_id)
    """
)

SQL_DEM_RESULTADOS = text(
    f"""
    SELECT resultado FROM geo_jobs
     WHERE tipo::text = ANY(:tipos)
       AND resultado IS NOT NULL
       AND {_AREA_PREDICATE}
     ORDER BY created_at DESC
    """
)

#: The keys a DEM run writes into ``outputs`` ONLY inside its burn branch
#: (``tasks_dem_support.py:109-143``). Their presence IS the record of a burn;
#: their absence, on a run that produced any output at all, is the record of
#: none. That is the checked fact the fallback below is licensed by.
CLAVES_DE_QUEMADO: tuple[str, ...] = ("burned_dem", "filled_hydro_dem")


class VarianteNoDisponible(RuntimeError):
    """The required drainage result does not resolve, and may not be substituted.

    Carries ``area_id`` and ``capa_faltante`` because the caller must do two
    things with it: report which layer is missing, and **still compute the canal
    crossings**. A hard refusal here aborts the ``flujo_natural`` derivation
    only — canal crossings have no raster dependency whatsoever, so an area with
    a broken DEM still gets its culvert candidates.
    """

    def __init__(self, area_id: str, capa_faltante: str, detalle: str = "") -> None:
        self.area_id = area_id
        self.capa_faltante = capa_faltante
        super().__init__(
            f"drainage result unavailable for area {area_id!r}: {capa_faltante} {detalle}".strip()
        )


class DemJobEnCurso(RuntimeError):
    """A DEM job owns this area's rasters right now, so the run refuses.

    ``motivo`` is one of ``dem_job_running_pre_check`` (caught cheaply, before
    the claim) or ``dem_job_started_during_copy`` (caught by the post-copy
    re-check, which is the case the pre-check alone *cannot* catch).
    """

    def __init__(self, area_id: str, motivo: str) -> None:
        self.area_id = area_id
        self.motivo = motivo
        super().__init__(f"{motivo}: a DEM job owns area {area_id!r}")


@dataclass(frozen=True)
class VarianteResuelta:
    """The pair this run will read, and the name of what it actually read."""

    flow_dir_path: str
    flow_acc_path: str
    variante: str  # 'natural' | 'relevado_equivale_natural'
    flow_dir_layer: str
    flow_acc_layer: str


def resolver_variante_drenaje(db, repo, *, area_id: str) -> VarianteResuelta:
    """Resolve the drainage pair BY EXACT NAME, substituting only under proof.

    Order:

    1. ``natural_flow_dir_{area_id}`` / ``natural_flow_acc_{area_id}``. Both
       resolve → use them. Done.
    2. **Both** absent → verify the no-burn condition explicitly before
       substituting anything. Only under that verified condition fall back to
       ``flow_dir_{area_id}`` / ``flow_acc_{area_id}`` and **record** the
       substitution as ``variante: relevado_equivale_natural``.
    3. Anything else — one of a pair present and the other absent, or natural
       absent *with a burn on record*, or no DEM run at all — is a hard refusal
       naming the missing layer.

    There is no path that reads ``escenario_*`` (a SIMULATION of canals nobody
    has built) and no path that reads a burned raster while calling it natural.

    Resolution is by name and not by ``tipo``: three layers share
    ``tipo = FLOW_ACC``, so ``.first()`` over an unordered query is *unspecified*
    — worse than random, because it is stable enough to look correct in testing
    and free to change under a plan change — and the caller could not state which
    variant it read.
    """
    natural_dir = repo.get_layer_by_nombre(db, f"natural_flow_dir_{area_id}")
    natural_acc = repo.get_layer_by_nombre(db, f"natural_flow_acc_{area_id}")

    if natural_dir and natural_acc:
        return VarianteResuelta(
            flow_dir_path=natural_dir.archivo_path,
            flow_acc_path=natural_acc.archivo_path,
            variante="natural",
            flow_dir_layer=f"natural_flow_dir_{area_id}",
            flow_acc_layer=f"natural_flow_acc_{area_id}",
        )

    if natural_dir or natural_acc:
        missing = f"natural_flow_acc_{area_id}" if natural_dir else f"natural_flow_dir_{area_id}"
        raise VarianteNoDisponible(
            area_id,
            missing,
            "— exactly one of the natural pair resolved, which is a broken "
            "pipeline run rather than a licence to substitute",
        )

    resultados = repo.get_dem_resultados(db, area_id)
    if not resultados:
        raise VarianteNoDisponible(
            area_id,
            f"natural_flow_acc_{area_id}",
            "— no DEM run is on record for this area, so the no-burn condition "
            "cannot be verified; absence of evidence is not evidence of no burn",
        )

    # The newest run decides: an area burned once and re-run without canals is
    # no longer burned.
    hubo_quemado = any(clave in (resultados[0] or {}) for clave in CLAVES_DE_QUEMADO)
    if hubo_quemado:
        raise VarianteNoDisponible(
            area_id,
            f"natural_flow_acc_{area_id}",
            "— the last DEM run recorded a burn, so the operational pair is NOT "
            "equivalent to the natural variant and must not stand in for it",
        )

    operational_dir = repo.get_layer_by_nombre(db, f"flow_dir_{area_id}")
    operational_acc = repo.get_layer_by_nombre(db, f"flow_acc_{area_id}")
    if not (operational_dir and operational_acc):
        missing = f"flow_acc_{area_id}" if operational_dir else f"flow_dir_{area_id}"
        raise VarianteNoDisponible(area_id, missing)

    # Licensed by a checked fact: with no burn, ``hay_variante_natural`` was
    # false and ``_computar_flujo`` ran once over ``filled_hydro``, which IS the
    # same file object as ``filled``. These rasters are not an approximation of
    # the natural variant — they are byte-identical to what it would have been.
    return VarianteResuelta(
        flow_dir_path=operational_dir.archivo_path,
        flow_acc_path=operational_acc.archivo_path,
        variante="relevado_equivale_natural",
        flow_dir_layer=f"flow_dir_{area_id}",
        flow_acc_layer=f"flow_acc_{area_id}",
    )


# ---------------------------------------------------------------------------
# The snapshot-copy protocol — NOT a lock
# ---------------------------------------------------------------------------
#
# ``pg_advisory_xact_lock(hashtext('geo_area:' || area_id))`` was withdrawn in
# full. It did not work, for four independent reasons, each verified in the code:
#
# 1. **The lock is released before the destruction finishes.**
#    ``cleanup_full_dem_state_impl`` does its database work, ``db.commit()``s at
#    ``tasks_dem_support.py:557`` — which ends the transaction and therefore
#    releases any transaction-scoped advisory lock — and only THEN walks the
#    output directory deleting files (``:567-578``). A reader blocked on that
#    lock would be woken up precisely in time to read files being deleted.
# 2. **The plain pipeline was never covered.** ``archive_previous_output`` runs
#    inside ``run_dem_pipeline_impl``, for which no lock was proposed at all,
#    because that path was believed non-destructive. It renames the directory
#    out from under the reader.
# 3. **The key namespace collides with an unrelated lock.** ``hashtext`` returns
#    ``int4``, and the auth domain already takes
#    ``pg_advisory_xact_lock(hashtext(str(family_id)))`` on refresh-token
#    families (``app/auth/refresh_tokens.py:183``) in that same single-key space.
#    Improbable, not impossible — and the symptom would be a token refresh and a
#    crossing run mysteriously serializing with no code linking them.
# 4. **In-place raster rewrites at stage 2 are not bounded by the cleanup step**,
#    which is the only place a lock was proposed. Locking one of three
#    destructive moments protects against one of three.
#
# The replacement makes the reader independent of the writer's TIMING instead of
# trying to interleave with it — and it needs no cooperation from the writer, so
# ``tasks_dem_support.py`` is not modified by this change at all. There is no
# "the guard is worthless if only one side takes it" failure mode, no lock
# ordering, no ``lock_timeout`` to tune, and **no long-lived transaction held
# open across a multi-minute raster computation** pinning VACUUM's xmin horizon
# for the whole database.


def dem_job_ocupado(db: Session, area_id: str) -> bool:
    """Pre-check: is a DEM job PENDING or RUNNING for this area?

    A cheap first layer, and **its TOCTOU residue is real and is not papered
    over**: a pipeline can reach RUNNING one microsecond after this returns
    empty, and this check cannot see that. It catches the common case at
    negligible cost; :func:`verificar_dem_libre` is what makes the run *safe*.
    """
    return (
        db.execute(
            SQL_DEM_JOB_OCUPADO,
            {
                "tipos": list(DEM_JOB_TIPOS),
                "estados": list(ESTADOS_DEM_OCUPADO),
                "area_id": area_id,
            },
        ).scalar()
        is not None
    )


def verificar_dem_libre(db: Session, area_id: str, *, desde: datetime) -> None:
    """Post-copy revalidation. THIS is the real guard.

    Keyed on ``updated_at >= desde`` rather than ``created_at``: every
    compare-and-set bumps ``updated_at`` (``geo_repository_jobs_layers.py:82-110``),
    so the ``PENDING → RUNNING`` claim of a job **created before** the pre-check
    necessarily moves it past the mark — which ``created_at`` would miss
    entirely.

    If any DEM job for this area reached RUNNING since the pre-check instant, the
    copy may be **torn** and the run aborts, computing nothing and writing
    nothing.
    """
    intervino = db.execute(
        SQL_DEM_JOB_INTERVINO,
        {
            "tipos": list(DEM_JOB_TIPOS),
            "estados": list(ESTADOS_ALCANZO_RUNNING),
            "desde": desde,
            "area_id": area_id,
        },
    ).scalar()
    if intervino is not None:
        raise DemJobEnCurso(area_id, "dem_job_started_during_copy")


def copiar_rasters_a_scratch(
    variante: VarianteResuelta, *, scratch_root: str | Path
) -> tuple[Path, str, str]:
    """Copy the two resolved rasters into this run's own private directory.

    These are area-DEM state rasters — order of megabytes, not gigabytes — so a
    full copy is cheap enough to be **the mechanism** rather than an
    optimization. After this step nothing in the run touches the pipeline's files
    again, so a pipeline that starts, archives, wipes or rewrites the originals
    mid-run cannot affect a computation already in flight.
    """
    scratch = Path(scratch_root) / f"cruces-{uuid.uuid4().hex}"
    scratch.mkdir(parents=True, exist_ok=False)
    flow_dir_copy = scratch / "flow_dir.tif"
    flow_acc_copy = scratch / "flow_acc.tif"
    shutil.copy2(variante.flow_dir_path, flow_dir_copy)
    shutil.copy2(variante.flow_acc_path, flow_acc_copy)
    return scratch, str(flow_dir_copy), str(flow_acc_copy)


def corroborar_copias(flow_dir_copy: str, flow_acc_copy: str) -> None:
    """Two cheap sanity checks that ride along — CORROBORATION, not proof.

    Both files are non-empty and their size is stable across two stats, and
    ``rasterio.open`` succeeds on both. Stated for exactly what they are: a torn
    or truncated GeoTIFF fails to parse with **high probability, not with
    certainty**. The post-copy job re-check is the guard; this is a second
    opinion that costs nothing.
    """
    import rasterio

    for path in (flow_dir_copy, flow_acc_copy):
        first = Path(path).stat().st_size
        if first == 0:
            raise DemJobEnCurso("", "dem_job_started_during_copy")
        if Path(path).stat().st_size != first:
            raise DemJobEnCurso("", "dem_job_started_during_copy")
        with rasterio.open(path) as src:
            if src.width == 0 or src.height == 0:
                raise DemJobEnCurso("", "dem_job_started_during_copy")


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def calcular_desactualizado(db: Session, area_id: str, calculada_en: Optional[datetime]) -> bool:
    """Do these crossings predate their inputs?

    True when the newest of (max DEM-job ``created_at`` for the area, max
    ``red_vial.ultima_carga_en`` over the segments in scope) is newer than
    ``calculada_en``.

    **The overlap blind spot is closed by construction.** A crossing run that
    started before a DEM job and finished after it would stamp a ``calculada_en``
    newer than that job's ``created_at``, so the comparison would read "current"
    over rasters replaced underneath it mid-run. Under the snapshot-copy protocol
    such a run **cannot exist**: a DEM job reaching RUNNING between the pre-check
    and the end of the copy aborts the crossing run, and one reaching RUNNING
    after the copy cannot touch a computation reading private files. Every
    persisted row therefore comes from a run that overlapped no DEM job, so the
    comparison genuinely means "computed after the last terrain change". The flag
    does not have to reason about crossing runs it cannot see, because the
    protocol refuses to produce them.
    """
    if calculada_en is None:
        return False
    marks = [
        db.execute(
            SQL_MAX_DEM_CREATED_AT,
            {
                "tipos": list(DEM_JOB_TIPOS),
                "estados": list(ESTADOS_ALCANZO_RUNNING),
                "area_id": area_id,
            },
        ).scalar(),
        db.execute(SQL_MAX_RED_VIAL_CARGA, {"area_id": area_id}).scalar(),
    ]
    return any(mark is not None and mark > calculada_en for mark in marks)


def dem_resultados_por_area(db: Session, area_id: str) -> list[dict[str, Any]]:
    """The DEM runs' ``resultado`` payloads for this area, newest first."""
    rows = (
        db.execute(SQL_DEM_RESULTADOS, {"tipos": list(DEM_JOB_TIPOS), "area_id": area_id})
        .scalars()
        .all()
    )
    return [row for row in rows if isinstance(row, dict)]
