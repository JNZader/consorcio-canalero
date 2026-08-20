"""Basins, bundle import/export and approved-zoning endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.repository import GeoRepository
from app.domains.geo.router_common import (
    ApprovedZonesMapPdfRequest,
    ApprovedZonesResponse,
    ApprovedZonesSaveRequest,
    GeoJsonImportResponse,
    _get_repo,
    _get_user_display_name,
    _import_approved_zoning_payload,
    _import_zonas_operativas_payload,
    _read_geojson_upload,
    _require_admin,
    _require_operator,
    _serialize_approved_zoning,
    _validate_geojson_filename,
    enforce_map_pdf_body_limit,
    parse_map_pdf_body,
    slot_de_pdf,
    MAP_PDF_OPENAPI_EXTRA,
)
from app.shared.pdf.builders_common import ImagenDemasiadoGrande, ImagenInvalida
from app.domains.geo.schemas import (
    ApprovedZonesDeleteResponse,
    BasinCatastroMembershipResponse,
)

router = APIRouter(tags=["Geo Processing"])


def _get_intelligence_repository():
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    return IntelligenceRepository()


# ──────────────────────────────────────────────
# BASINS (PostGIS)
# ──────────────────────────────────────────────


@router.get(
    "/basins/{basin_id}/catastro-membership",
    response_model=BasinCatastroMembershipResponse,
)
def get_basin_catastro_membership(
    basin_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo=Depends(_get_intelligence_repository),
    _user=Depends(_require_operator()),
) -> BasinCatastroMembershipResponse:
    """Return server-computed cadastre membership for one selected basin."""
    nomenclaturas = repo.get_catastro_membership_by_basin(db, basin_id)
    if nomenclaturas is None:
        raise HTTPException(status_code=404, detail="Cuenca operativa no encontrada")
    return BasinCatastroMembershipResponse(
        basin_id=basin_id,
        intersecting_feature_ids=nomenclaturas,
    )


@router.get("/basins", response_model=dict)
def get_basins(
    bbox: Optional[str] = Query(
        default=None,
        description="Bounding box filter: minx,miny,maxx,maxy (EPSG:4326)",
    ),
    tolerance: float = Query(
        default=0.001,
        ge=0.0,
        le=1.0,
        description="ST_Simplify tolerance in degrees (~0.001 = 100m)",
    ),
    limit: int = Query(default=500, ge=1, le=1000),
    cuenca: Optional[str] = Query(default=None, description="Filter by cuenca name"),
    adjusted: bool = Query(
        default=True,
        description="Apply special visual basin adjustments like splitting sub-cuenca 9",
    ),
    db: Session = Depends(get_db),
):
    """Get basin polygons as GeoJSON FeatureCollection from PostGIS (public).

    Queries the ``zonas_operativas`` table using ``ST_AsGeoJSON`` +
    ``ST_Simplify`` for efficient geometry serialisation.  Supports
    bounding-box spatial filtering and cuenca name filtering.
    """
    from app.domains.geo.intelligence.repository import IntelligenceRepository

    parsed_bbox: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError("bbox must have exactly 4 values")
            parsed_bbox = (parts[0], parts[1], parts[2], parts[3])
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="bbox debe ser 4 floats separados por coma: minx,miny,maxx,maxy",
            )

    intel_repo = IntelligenceRepository()
    return intel_repo.get_zonas_as_geojson(
        db,
        bbox=parsed_bbox,
        tolerance=tolerance,
        limit=limit,
        cuenca_filter=cuenca,
    )


@router.post("/basins/import", response_model=GeoJsonImportResponse)
async def import_basins_geojson(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
):
    """Replace operational basins from a GeoJSON FeatureCollection."""
    _validate_geojson_filename(file.filename)
    payload = _read_geojson_upload(await file.read())
    result = _import_zonas_operativas_payload(db, payload)
    db.commit()

    return GeoJsonImportResponse(
        importedCount=result["imported_count"],
        replacedCount=result["replaced_count"],
        featureType="zonas_operativas",
        metadata={
            "filename": file.filename,
            "cuencas": result["cuencas"],
        },
    )


@router.get("/basins/approved-zones/current", response_model=ApprovedZonesResponse | None)
def get_current_approved_basin_zones(
    cuenca: Optional[str] = Query(default=None, description="Optional filter by cuenca name"),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
):
    """Return the persisted approved zoning currently in use."""
    zoning = repo.get_active_approved_zoning(db, cuenca=cuenca)
    if zoning is None:
        return None
    return _serialize_approved_zoning(db, zoning)


@router.put("/basins/approved-zones/current", response_model=ApprovedZonesResponse)
def save_current_approved_basin_zones(
    payload: ApprovedZonesSaveRequest,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    user=Depends(_require_operator()),
):
    """Persist the approved zoning so all clients share the same version."""
    zoning = repo.create_approved_zoning_version(
        db,
        nombre=payload.nombre,
        cuenca=payload.cuenca,
        feature_collection=payload.feature_collection,
        assignments=payload.assignments,
        zone_names=payload.zone_names,
        approved_by_id=getattr(user, "id", None),
        notes=payload.notes,
    )
    db.commit()
    db.refresh(zoning)
    return _serialize_approved_zoning(db, zoning)


@router.post("/basins/approved-zones/import", response_model=GeoJsonImportResponse)
async def import_current_approved_basin_zones(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    user=Depends(_require_admin()),
):
    """Import an approved zoning FeatureCollection from GeoJSON."""
    _validate_geojson_filename(file.filename)
    payload = _read_geojson_upload(await file.read())
    result = _import_approved_zoning_payload(
        db,
        repo,
        payload,
        approved_by_id=getattr(user, "id", None),
        notes=f"Importado desde GeoJSON: {file.filename}",
    )
    db.commit()

    return GeoJsonImportResponse(
        importedCount=result["imported_count"],
        replacedCount=result["replaced_count"],
        featureType="zonificacion_aprobada",
        metadata={
            "filename": file.filename,
            "version": result["version"],
            "nombre": result["nombre"],
            "cuenca": result["cuenca"],
        },
    )


@router.delete(
    "/basins/approved-zones/current",
    response_model=ApprovedZonesDeleteResponse,
)
def clear_current_approved_basin_zones(
    cuenca: Optional[str] = Query(default=None, description="Optional filter by cuenca name"),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
) -> ApprovedZonesDeleteResponse:
    """Delete the currently persisted approved zoning."""
    deleted = repo.clear_active_approved_zoning(db, cuenca=cuenca)
    db.commit()
    return ApprovedZonesDeleteResponse(deleted=deleted)


@router.get("/basins/approved-zones/history", response_model=list[ApprovedZonesResponse])
def list_approved_basin_zone_history(
    cuenca: Optional[str] = Query(default=None, description="Optional filter by cuenca name"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
):
    """Return approved zoning history including the current baseline/current active versions."""
    items = repo.list_approved_zonings(db, cuenca=cuenca, limit=limit)
    return [_serialize_approved_zoning(db, item) for item in items]


@router.get("/basins/approved-zones/current/export-pdf")
def export_current_approved_basin_zones_pdf(
    cuenca: Optional[str] = Query(default=None, description="Optional filter by cuenca name"),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
):
    """Export the current approved zoning as a PDF report."""
    from app.shared.pdf import build_approved_zoning_pdf, get_branding

    zoning = repo.get_active_approved_zoning(db, cuenca=cuenca)
    if zoning is None:
        raise HTTPException(status_code=404, detail="No hay una zonificación aprobada activa")

    branding = get_branding(db)
    approved_by_name = _get_user_display_name(db, zoning.approved_by_id)
    pdf_buffer = build_approved_zoning_pdf(
        zoning,
        branding,
        approved_by_name=approved_by_name,
    )

    filename = f"zonificacion-aprobada-v{zoning.version}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/basins/approved-zones/current/export-map-pdf",
    dependencies=[Depends(enforce_map_pdf_body_limit)],
    openapi_extra=MAP_PDF_OPENAPI_EXTRA,
)
def export_current_map_approved_basin_zones_pdf(
    payload: ApprovedZonesMapPdfRequest = Depends(parse_map_pdf_body),
    db: Session = Depends(get_db),
):
    """Export a cartographic PDF using a clean map capture plus external legends.

    PUBLIC route. Four bounds stand between the caller and reportlab: the body
    limit (413, before anything reads the stream), the per-list caps on
    ``ApprovedZonesMapPdfRequest`` (422), the decoded-image pixel cap the builder
    enforces (``ImagenDemasiadoGrande`` → 422), and the in-flight slot below.

    ``payload`` arrives through a DEPENDENCY on purpose — a declared body
    parameter makes FastAPI read the whole body before dependencies run, which
    silently disables the size guard for chunked requests. See
    ``enforce_map_pdf_body_limit``.
    """
    from app.shared.pdf import build_approved_zoning_map_pdf, get_branding

    branding = get_branding(db)
    try:
        with slot_de_pdf():
            pdf_buffer = build_approved_zoning_map_pdf(payload.model_dump(by_alias=True), branding)
    except (ImagenDemasiadoGrande, ImagenInvalida) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = "zonificacion-aprobada-mapa.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/basins/approved-zones/{zoning_id}/restore", response_model=ApprovedZonesResponse)
def restore_approved_basin_zone_version(
    zoning_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    user=Depends(_require_operator()),
):
    """Create a new active version by restoring a historical approved zoning."""
    source = repo.get_approved_zoning_by_id(db, zoning_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Versión de zonificación no encontrada")

    restored = repo.create_approved_zoning_version(
        db,
        nombre=source.nombre,
        cuenca=source.cuenca,
        feature_collection=source.feature_collection,
        assignments=source.assignments or {},
        zone_names=source.zone_names or {},
        approved_by_id=getattr(user, "id", None),
        notes=f"Restaurada desde versión {source.version}",
    )
    db.commit()
    db.refresh(restored)
    return _serialize_approved_zoning(db, restored)
