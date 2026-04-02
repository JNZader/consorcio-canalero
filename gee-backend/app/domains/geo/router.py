"""FastAPI router for the geo domain."""

import asyncio
import io
import json
import shutil
import uuid
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.exceptions import AppException, NotFoundError, get_safe_error_detail
from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.models import GeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.schemas import (
    AnalisisGeoCreate,
    AnalisisGeoListResponse,
    AnalisisGeoResponse,
    DemPipelineRequest,
    DemPipelineResponse,
    FloodEventCreate,
    GeoJobCreate,
    GeoJobListResponse,
    GeoJobResponse,
    GeoLayerListResponse,
    GeoLayerResponse,
)
from app.domains.geo.service import dispatch_job

logger = get_logger(__name__)

router = APIRouter(tags=["Geo Processing"])

class ApprovedZonesBuildRequest(BaseModel):
    assignments: dict[str, str] = Field(default_factory=dict)
    zone_names: dict[str, str] = Field(default_factory=dict)
    cuenca: Optional[str] = None


class ApprovedZonesSaveRequest(BaseModel):
    feature_collection: dict = Field(..., alias="featureCollection")
    assignments: dict[str, str] = Field(default_factory=dict)
    zone_names: dict[str, str] = Field(default_factory=dict)
    cuenca: Optional[str] = None
    nombre: str = "Zonificación Consorcio aprobada"
    notes: Optional[str] = None


class ApprovedZonesResponse(BaseModel):
    id: str
    nombre: str
    version: int
    cuenca: Optional[str] = None
    feature_collection: dict = Field(..., alias="featureCollection")
    assignments: dict[str, str] = Field(default_factory=dict)
    zone_names: dict[str, str] = Field(default_factory=dict)
    notes: Optional[str] = None
    approved_at: str = Field(..., alias="approvedAt")
    approved_by_id: Optional[str] = Field(default=None, alias="approvedById")
    approved_by_name: Optional[str] = Field(default=None, alias="approvedByName")


class GeoJsonImportResponse(BaseModel):
    imported_count: int = Field(..., alias="importedCount")
    replaced_count: int = Field(..., alias="replacedCount")
    feature_type: str = Field(..., alias="featureType")
    metadata: dict = Field(default_factory=dict)


class GeoBundleImportResponse(BaseModel):
    vectors_imported: dict = Field(default_factory=dict, alias="vectorsImported")
    layers_imported: int = Field(..., alias="layersImported")
    bundle_name: str = Field(..., alias="bundleName")
    metadata: dict = Field(default_factory=dict)


class MapLegendItemRequest(BaseModel):
    label: str
    color: str
    detail: Optional[str] = None


class RasterLegendGroupRequest(BaseModel):
    label: str
    items: list[MapLegendItemRequest] = Field(default_factory=list)


class MapInfoRowRequest(BaseModel):
    label: str
    value: str


class ZoneSummaryRowRequest(BaseModel):
    name: str
    subcuencas: int | str
    area_ha: float | str = Field(..., alias="areaHa")
    color: Optional[str] = None


class ApprovedZonesMapPdfRequest(BaseModel):
    title: str
    subtitle: Optional[str] = None
    map_image_data_url: str = Field(..., alias="mapImageDataUrl")
    zone_legend: list[MapLegendItemRequest] = Field(default_factory=list, alias="zoneLegend")
    road_legend: list[MapLegendItemRequest] = Field(default_factory=list, alias="roadLegend")
    raster_legends: list[RasterLegendGroupRequest] = Field(default_factory=list, alias="rasterLegends")
    info_rows: list[MapInfoRowRequest] = Field(default_factory=list, alias="infoRows")
    zone_summary: list[ZoneSummaryRowRequest] = Field(default_factory=list, alias="zoneSummary")


# Shared httpx client for tile proxying (avoids creating one per request)
_tile_client = None


def _get_tile_client():
    global _tile_client  # noqa: PLW0603
    if _tile_client is None:
        _tile_client = httpx.AsyncClient(timeout=10.0)
    return _tile_client


def _get_repo() -> GeoRepository:
    """Dependency that provides the repository instance."""
    return GeoRepository()


def _get_user_display_name(db: Session, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None:
        return None
    full_name = " ".join(part for part in [user.nombre, user.apellido] if part).strip()
    return full_name or user.email


def _serialize_approved_zoning(db: Session, zoning) -> ApprovedZonesResponse:
    return ApprovedZonesResponse(
        id=str(zoning.id),
        nombre=zoning.nombre,
        version=zoning.version,
        cuenca=zoning.cuenca,
        featureCollection=zoning.feature_collection,
        assignments=zoning.assignments or {},
        zone_names=zoning.zone_names or {},
        notes=zoning.notes,
        approvedAt=zoning.approved_at.isoformat(),
        approvedById=str(zoning.approved_by_id) if zoning.approved_by_id else None,
        approvedByName=_get_user_display_name(db, zoning.approved_by_id),
    )


def _validate_geojson_filename(filename: str | None) -> None:
    if not filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
    if not filename.lower().endswith((".geojson", ".json")):
        raise HTTPException(status_code=400, detail="Formato no soportado. Use archivos .geojson o .json")


def _read_geojson_upload(content: bytes) -> dict:
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="GeoJSON invalido") from exc

    if payload.get("type") != "FeatureCollection":
        raise HTTPException(status_code=400, detail="El archivo debe ser un FeatureCollection GeoJSON")

    features = payload.get("features")
    if not isinstance(features, list):
        raise HTTPException(status_code=400, detail="El archivo GeoJSON no contiene una lista de features")

    return payload


def _extract_source_properties(properties: dict | None) -> dict:
    if not isinstance(properties, dict):
        return {}
    source_properties = properties.get("source_properties")
    return source_properties if isinstance(source_properties, dict) else properties


def _get_geo_bundle_storage_dir() -> Path:
    candidates = [
        Path("/data/geo/bundles"),
        Path(__file__).resolve().parents[3] / "data" / "geo_bundles",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    raise HTTPException(status_code=500, detail="No se pudo preparar el directorio de bundles geo")


def _build_zonas_operativas_export(db: Session) -> dict:
    intel_repo = IntelligenceRepository()
    return intel_repo.get_zonas_as_geojson(db, tolerance=0.0, limit=10000)


def _build_approved_zoning_export(db: Session, repo: GeoRepository) -> dict | None:
    zoning = repo.get_active_approved_zoning(db)
    if zoning is None:
        return None
    serialized = _serialize_approved_zoning(db, zoning)
    return serialized.model_dump(by_alias=True)


def _normalize_polygon_wkt(geometry: dict) -> str:
    from shapely.geometry import shape as shapely_shape
    from shapely.ops import unary_union

    geom_shape = shapely_shape(geometry)
    if geom_shape.geom_type == "MultiPolygon":
        merged = unary_union(geom_shape)
        if merged.geom_type == "Polygon":
            geom_shape = merged
        elif merged.geom_type == "MultiPolygon":
            geom_shape = max(merged.geoms, key=lambda part: part.area)
    return geom_shape.wkt


def _import_zonas_operativas_payload(db: Session, payload: dict) -> dict:
    features = payload.get("features", [])
    if not features:
        raise HTTPException(status_code=400, detail="El archivo no contiene subcuencas")

    replaced_count = db.execute(delete(ZonaOperativa)).rowcount or 0

    imported_count = 0
    cuencas = Counter()
    for index, feature in enumerate(features, start=1):
        geometry = feature.get("geometry")
        if not geometry:
            raise HTTPException(status_code=400, detail=f"Feature {index} sin geometria")

        geometry_type = geometry.get("type")
        if geometry_type not in {"Polygon", "MultiPolygon"}:
            raise HTTPException(
                status_code=400,
                detail=f"Feature {index} tiene geometria no soportada: {geometry_type}",
            )

        props = feature.get("properties") or {}
        cuenca = str(props.get("cuenca") or "sin_asignar")
        nombre = str(props.get("nombre") or f"Subcuenca {index}")
        superficie_ha = float(props.get("superficie_ha") or 0.0)
        geom_wkt = _normalize_polygon_wkt(geometry)

        db.add(
            ZonaOperativa(
                id=uuid.UUID(str(props["id"])) if props.get("id") else uuid.uuid4(),
                nombre=nombre,
                geometria=f"SRID=4326;{geom_wkt}",
                cuenca=cuenca,
                superficie_ha=superficie_ha,
            )
        )
        imported_count += 1
        cuencas[cuenca] += 1

    return {
        "imported_count": imported_count,
        "replaced_count": replaced_count,
        "cuencas": dict(cuencas),
    }


def _import_approved_zoning_payload(
    db: Session,
    repo: GeoRepository,
    payload: dict,
    *,
    approved_by_id: uuid.UUID | None,
    notes: str | None = None,
) -> dict:
    feature_collection = payload.get("featureCollection")
    if isinstance(feature_collection, dict):
        normalized_features = feature_collection.get("features", [])
        zone_names = payload.get("zone_names") or payload.get("zoneNames") or {}
        assignments = payload.get("assignments") or {}
        approved_name = str(payload.get("nombre") or "Zonificación Consorcio aprobada")
        approved_cuenca = payload.get("cuenca")
    else:
        features = payload.get("features", [])
        if not features:
            raise HTTPException(status_code=400, detail="El archivo no contiene zonas aprobadas")

        normalized_features = []
        zone_names = {}
        assignments = {}
        approved_name = "Zonificación Consorcio aprobada"
        approved_cuenca = None

        for index, feature in enumerate(features, start=1):
            geometry = feature.get("geometry")
            if not geometry:
                raise HTTPException(status_code=400, detail=f"Feature {index} sin geometria")

            geometry_type = geometry.get("type")
            if geometry_type not in {"Polygon", "MultiPolygon"}:
                raise HTTPException(
                    status_code=400,
                    detail=f"Feature {index} tiene geometria no soportada: {geometry_type}",
                )

            props = feature.get("properties") or {}
            source_properties = _extract_source_properties(props)
            normalized_features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": source_properties,
                }
            )

            approved_name = str(props.get("approved_nombre") or approved_name)
            approved_cuenca = props.get("approved_cuenca") or approved_cuenca
            zone_id = str(source_properties.get("zone_id") or props.get("zone_id") or f"zone_{index}")
            zone_name = str(source_properties.get("name") or props.get("name") or f"Zona {index}")
            zone_names[zone_id] = zone_name

    previous_active = repo.get_active_approved_zoning(db, cuenca=approved_cuenca)
    zoning = repo.create_approved_zoning_version(
        db,
        nombre=approved_name,
        cuenca=approved_cuenca,
        feature_collection={
            "type": "FeatureCollection",
            "features": normalized_features,
        },
        assignments=assignments,
        zone_names=zone_names,
        approved_by_id=approved_by_id,
        notes=notes,
    )
    return {
        "imported_count": len(normalized_features),
        "replaced_count": 1 if previous_active else 0,
        "version": zoning.version,
        "nombre": zoning.nombre,
        "cuenca": zoning.cuenca,
    }


def _upsert_bundle_layer(
    db: Session,
    *,
    nombre: str,
    tipo: str,
    fuente: str,
    archivo_path: str,
    formato: str,
    srid: int,
    bbox: dict | list | None,
    metadata_extra: dict | None,
    area_id: str | None,
) -> GeoLayer:
    existing = None
    if area_id:
        existing = db.query(GeoLayer).filter(GeoLayer.tipo == tipo, GeoLayer.area_id == area_id).one_or_none()
    else:
        existing = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo, GeoLayer.nombre == nombre, GeoLayer.area_id.is_(None))
            .one_or_none()
        )

    if existing:
        existing.nombre = nombre
        existing.fuente = fuente
        existing.archivo_path = archivo_path
        existing.formato = formato
        existing.srid = srid
        existing.bbox = bbox
        existing.metadata_extra = metadata_extra
        return existing

    layer = GeoLayer(
        nombre=nombre,
        tipo=tipo,
        fuente=fuente,
        archivo_path=archivo_path,
        formato=formato,
        srid=srid,
        bbox=bbox,
        metadata_extra=metadata_extra,
        area_id=area_id,
    )
    db.add(layer)
    return layer


# Lazy import to avoid circular deps at module level.
def _require_operator():
    """Return the operator dependency at call time."""
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_authenticated():
    """Return the authenticated dependency at call time."""
    from app.auth import require_authenticated

    return require_authenticated


# ──────────────────────────────────────────────
# JOBS
# ──────────────────────────────────────────────


@router.post("/jobs", response_model=GeoJobResponse, status_code=201)
def submit_geo_job(
    payload: GeoJobCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """
    Submit a new geo processing job (requiere operador).

    The job is created in PENDING state. A Celery task is
    dispatched to the geo-worker for actual processing.
    """
    job = dispatch_job(
        db,
        tipo=payload.tipo,
        parametros=payload.parametros,
    )
    return job


@router.get("/jobs", response_model=dict)
def list_geo_jobs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    estado: Optional[str] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List geo processing jobs with pagination and filters."""
    items, total = repo.get_jobs(
        db,
        page=page,
        limit=limit,
        estado_filter=estado,
        tipo_filter=tipo,
    )
    return {
        "items": [GeoJobListResponse.model_validate(j) for j in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/jobs/{job_id}", response_model=GeoJobResponse)
def get_geo_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get geo job detail by ID."""
    job = repo.get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Geo job no encontrado")
    return job


# ──────────────────────────────────────────────
# LAYERS
# ──────────────────────────────────────────────


@router.get("/layers", response_model=dict)
def list_geo_layers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    fuente: Optional[str] = None,
    area_id: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List available geo layers with pagination and filters."""
    items, total = repo.get_layers(
        db,
        page=page,
        limit=limit,
        tipo_filter=tipo,
        fuente_filter=fuente,
        area_id_filter=area_id,
    )
    return {
        "items": [GeoLayerListResponse.model_validate(layer) for layer in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/layers/public", response_model=dict)
def list_public_geo_layers(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    fuente: Optional[str] = None,
    area_id: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
):
    """List a safe public subset of geo layers.

    Currently intended for non-authenticated base visualization only.
    """
    allowed_types = {"dem_raw"}
    if tipo and tipo not in allowed_types:
        return {"items": [], "total": 0, "page": page, "limit": limit}

    items, total = repo.get_layers(
        db,
        page=page,
        limit=limit,
        tipo_filter=tipo or "dem_raw",
        fuente_filter=fuente,
        area_id_filter=area_id,
    )
    filtered_items = [layer for layer in items if layer.tipo in allowed_types]
    return {
        "items": [GeoLayerListResponse.model_validate(layer) for layer in filtered_items],
        "total": len(filtered_items),
        "page": page,
        "limit": limit,
    }


@router.get("/layers/{layer_id}", response_model=GeoLayerResponse)
def get_geo_layer(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get geo layer detail by ID."""
    layer = repo.get_layer_by_id(db, layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")
    return layer


@router.get("/layers/{layer_id}/file")
def get_geo_layer_file(
    layer_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Serve a GeoLayer file (GeoTIFF or GeoJSON) for download or frontend rendering.

    Returns a streaming response with the appropriate content-type.
    """
    layer = repo.get_layer_by_id(db, layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail="Geo layer no encontrado")

    file_path = Path(layer.archivo_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Archivo no encontrado en disco: {layer.archivo_path}",
        )

    # Determine content type based on format
    content_type_map = {
        "geotiff": "image/tiff",
        "geojson": "application/geo+json",
    }
    content_type = content_type_map.get(layer.formato, "application/octet-stream")

    def _file_iterator():
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    return StreamingResponse(
        _file_iterator(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Cache-Control": "public, max-age=3600",
        },
    )


# ──────────────────────────────────────────────
# DEM PIPELINE
# ──────────────────────────────────────────────


def _require_admin():
    """Return the admin dependency at call time."""
    from app.auth import require_admin

    return require_admin


@router.post("/dem-pipeline", response_model=DemPipelineResponse, status_code=201)
def trigger_dem_pipeline(
    payload: DemPipelineRequest = DemPipelineRequest(),
    db: Session = Depends(get_db),
    _user=Depends(_require_admin()),
):
    """Trigger the full DEM pipeline: download from GEE + terrain analysis + basin delineation.

    Admin only. Returns a job ID for status polling via GET /jobs/{job_id}.
    """
    from app.domains.geo.models import TipoGeoJob

    job = dispatch_job(
        db,
        tipo=TipoGeoJob.DEM_FULL_PIPELINE,
        parametros={
            "area_id": payload.area_id,
            "min_basin_area_ha": payload.min_basin_area_ha,
        },
    )
    return DemPipelineResponse(
        job_id=job.id,
        tipo=job.tipo,
        estado=job.estado,
    )


# ──────────────────────────────────────────────
# TILE PROXY (forwards to geo-worker tile service)
# ──────────────────────────────────────────────


@router.get("/layers/{layer_id}/tiles/{z}/{x}/{y}.png")
async def proxy_tile(
    layer_id: uuid.UUID,
    z: int,
    x: int,
    y: int,
    colormap: Optional[str] = Query(default=None),
    encoding: Optional[str] = Query(default=None),
    hide_classes: Optional[str] = Query(default=None),
    hide_ranges: Optional[str] = Query(default=None),
):
    """Proxy tile requests to the geo-worker tile service (public).

    Forwards the request to the internal tile service running on the
    geo-worker container and streams the response back to the client.

    Public endpoint — Leaflet TileLayer cannot set custom auth headers
    on tile requests, and DEM tiles are not sensitive data.
    """
    from app.config import settings

    _cors = {"Access-Control-Allow-Origin": "*"}

    # Build the upstream URL
    params = {}
    if colormap:
        params["colormap"] = colormap
    if encoding:
        params["encoding"] = encoding
    if hide_classes:
        params["hide_classes"] = hide_classes
    if hide_ranges:
        params["hide_ranges"] = hide_ranges

    upstream_url = (
        f"{settings.geo_worker_tile_url}/tiles/{layer_id}/{z}/{x}/{y}.png"
    )

    try:
        client = _get_tile_client()
        resp = await client.get(upstream_url, params=params)
    except (httpx.ConnectError, httpx.TimeoutException):
        return Response(status_code=204, headers=_cors)

    if resp.status_code == 204:
        return Response(status_code=204, headers=_cors)

    if resp.status_code >= 400:
        return Response(status_code=204, headers=_cors)

    return Response(
        content=resp.content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            **_cors,
        },
    )


# ──────────────────────────────────────────────
# BASINS (PostGIS)
# ──────────────────────────────────────────────


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
    feature_collection = intel_repo.get_zonas_as_geojson(
        db,
        bbox=parsed_bbox,
        tolerance=tolerance,
        limit=limit,
        cuenca_filter=cuenca,
    )
    if not adjusted:
        return feature_collection

    from app.domains.geo.intelligence.zoning_suggestions import split_basins_for_display

    adjusted_features = split_basins_for_display(feature_collection["features"])
    feature_collection["features"] = adjusted_features
    feature_collection["metadata"] = {
        **feature_collection.get("metadata", {}),
        "adjusted": True,
    }
    return feature_collection


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


@router.get("/bundle/export")
def export_geo_bundle(
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_admin()),
):
    """Export a geo bundle zip with vectors, active approved zoning and file-backed layers."""
    zonas_payload = _build_zonas_operativas_export(db)
    approved_payload = _build_approved_zoning_export(db, repo)
    layers = db.query(GeoLayer).order_by(GeoLayer.created_at.asc()).all()

    buffer = io.BytesIO()
    manifest_layers = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "vectors/zonas_operativas.geojson",
            json.dumps(zonas_payload, ensure_ascii=False, indent=2),
        )
        if approved_payload is not None:
            bundle.writestr(
                "vectors/approved_zoning.json",
                json.dumps(approved_payload, ensure_ascii=False, indent=2),
            )

        for layer in layers:
            file_path = Path(layer.archivo_path)
            if not file_path.exists() or not file_path.is_file():
                continue

            archive_path = f"layers/{layer.id}_{file_path.name}"
            bundle.write(file_path, archive_path)
            manifest_layers.append(
                {
                    "nombre": layer.nombre,
                    "tipo": layer.tipo,
                    "fuente": layer.fuente,
                    "formato": layer.formato,
                    "srid": layer.srid,
                    "bbox": layer.bbox,
                    "metadata_extra": layer.metadata_extra,
                    "area_id": layer.area_id,
                    "archive_path": archive_path,
                    "original_path": layer.archivo_path,
                }
            )
        manifest_payload = {
            "format": "geo-bundle-v1",
            "vectors": {
                "zonas_operativas": "vectors/zonas_operativas.geojson",
                "approved_zoning": "vectors/approved_zoning.json" if approved_payload else None,
            },
            "layers": manifest_layers,
        }
        bundle.writestr("manifest.json", json.dumps(manifest_payload, ensure_ascii=False, indent=2))

    buffer.seek(0)
    filename = f"geo_bundle_{date.today().isoformat()}.zip"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/bundle/import", response_model=GeoBundleImportResponse)
async def import_geo_bundle(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    user=Depends(_require_admin()),
):
    """Import a geo bundle zip with vectors and file-backed layers."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Debe subir un archivo .zip")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Bundle ZIP invalido") from exc

    try:
        with archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except KeyError as exc:
                raise HTTPException(status_code=400, detail="El bundle no contiene manifest.json") from exc

            bundle_dir = _get_geo_bundle_storage_dir() / f"import_{date.today().isoformat()}_{uuid.uuid4().hex[:8]}"
            bundle_dir.mkdir(parents=True, exist_ok=True)

            vectors_imported: dict[str, int] = {}

            zonas_path = manifest.get("vectors", {}).get("zonas_operativas")
            if zonas_path:
                zonas_payload = json.loads(archive.read(zonas_path).decode("utf-8"))
                zonas_result = _import_zonas_operativas_payload(db, zonas_payload)
                vectors_imported["zonas_operativas"] = zonas_result["imported_count"]

            approved_path = manifest.get("vectors", {}).get("approved_zoning")
            if approved_path:
                approved_payload = json.loads(archive.read(approved_path).decode("utf-8"))
                approved_result = _import_approved_zoning_payload(
                    db,
                    repo,
                    approved_payload,
                    approved_by_id=getattr(user, "id", None),
                    notes=f"Importado desde bundle: {file.filename}",
                )
                vectors_imported["zonificacion_aprobada"] = approved_result["imported_count"]

            layers_imported = 0
            for layer_entry in manifest.get("layers", []):
                archive_path = layer_entry.get("archive_path")
                if not archive_path:
                    continue
                target_path = bundle_dir / Path(archive_path).name
                with archive.open(archive_path) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

                _upsert_bundle_layer(
                    db,
                    nombre=str(layer_entry.get("nombre") or target_path.stem),
                    tipo=str(layer_entry.get("tipo") or "dem_raw"),
                    fuente=str(layer_entry.get("fuente") or "manual"),
                    archivo_path=str(target_path),
                    formato=str(layer_entry.get("formato") or target_path.suffix.lstrip(".") or "geotiff"),
                    srid=int(layer_entry.get("srid") or 4326),
                    bbox=layer_entry.get("bbox"),
                    metadata_extra=layer_entry.get("metadata_extra"),
                    area_id=layer_entry.get("area_id"),
                )
                layers_imported += 1

            db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return GeoBundleImportResponse(
        vectorsImported=vectors_imported,
        layersImported=layers_imported,
        bundleName=file.filename,
        metadata={"bundle_dir": str(bundle_dir), "format": manifest.get("format")},
    )


@router.get("/basins/suggested-zones", response_model=dict)
def get_suggested_basin_zones(
    cuenca: Optional[str] = Query(default=None, description="Optional filter by cuenca name"),
    db: Session = Depends(get_db),
):
    """Generate a draft territorial proposal from existing operational basins.

    This does not modify any persisted zoning. It returns a draft suggestion
    FeatureCollection so the frontend can review it separately from the
    current/manual zoning.

    Current strategy:
    - Norte = norte + noroeste
    - Monte Leña = ml
    - Candil = candil
    - southern/eastern `sin_asignar` basins are absorbed by Monte Leña or Candil
    """
    from app.domains.geo.intelligence.repository import IntelligenceRepository
    from app.domains.geo.intelligence.zoning_suggestions import (
        suggest_grouped_zones,
    )

    intel_repo = IntelligenceRepository()
    basin_features = intel_repo.get_zonas_for_grouping(db, cuenca_filter=cuenca)
    return suggest_grouped_zones(basin_features)


@router.post("/basins/approved-zones/build", response_model=dict)
def build_approved_basin_zones(
    payload: ApprovedZonesBuildRequest,
    db: Session = Depends(get_db),
):
    """Build an approved zoning preview from the current draft assignments."""
    from app.domains.geo.intelligence.repository import IntelligenceRepository
    from app.domains.geo.intelligence.zoning_suggestions import (
        build_zones_from_assignments,
    )

    intel_repo = IntelligenceRepository()
    basin_features = intel_repo.get_zonas_for_grouping(db, cuenca_filter=payload.cuenca)
    return build_zones_from_assignments(
        basin_features,
        basin_zone_assignments=payload.assignments,
        zone_names=payload.zone_names,
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


@router.delete("/basins/approved-zones/current", response_model=dict)
def clear_current_approved_basin_zones(
    cuenca: Optional[str] = Query(default=None, description="Optional filter by cuenca name"),
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Delete the currently persisted approved zoning."""
    deleted = repo.clear_active_approved_zoning(db, cuenca=cuenca)
    db.commit()
    return {"deleted": deleted}


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
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


@router.post("/basins/approved-zones/current/export-map-pdf")
def export_current_map_approved_basin_zones_pdf(
    payload: ApprovedZonesMapPdfRequest,
    db: Session = Depends(get_db),
):
    """Export a cartographic PDF using a clean map capture plus external legends."""
    from app.shared.pdf import build_approved_zoning_map_pdf, get_branding

    branding = get_branding(db)
    pdf_buffer = build_approved_zoning_map_pdf(payload.model_dump(by_alias=True), branding)
    filename = "zonificacion-aprobada-mapa.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
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


# ──────────────────────────────────────────────
# GEE SUB-ROUTER  (Google Earth Engine endpoints)
# ──────────────────────────────────────────────

gee_router = APIRouter(prefix="/gee", tags=["GEE"])


def _lazy_gee_service():
    """Lazy-import the GEE service to avoid import-time initialization."""
    from app.domains.geo.gee_service import (
        _ensure_initialized,
        get_available_layers as gee_available_layers,
        get_caminos_by_consorcio,
        get_caminos_by_consorcio_nombre,
        get_caminos_con_colores,
        get_consorcios_camineros,
        get_estadisticas_consorcios,
        get_gee_service,
        get_image_explorer,
        get_layer_geojson,
        ImageExplorer,
    )
    return {
        "ensure_init": _ensure_initialized,
        "get_available_layers": gee_available_layers,
        "get_caminos_by_consorcio": get_caminos_by_consorcio,
        "get_caminos_by_consorcio_nombre": get_caminos_by_consorcio_nombre,
        "get_caminos_con_colores": get_caminos_con_colores,
        "get_consorcios_camineros": get_consorcios_camineros,
        "get_estadisticas_consorcios": get_estadisticas_consorcios,
        "get_gee_service": get_gee_service,
        "get_image_explorer": get_image_explorer,
        "get_layer_geojson": get_layer_geojson,
        "ImageExplorer": ImageExplorer,
    }


def _ensure_gee():
    """Try to init GEE; raise 503 if unavailable."""
    svc = _lazy_gee_service()
    try:
        svc["ensure_init"]()
    except Exception as e:
        logger.error("No se pudo inicializar GEE", error=str(e))
        raise AppException(
            message="Google Earth Engine no esta disponible temporalmente",
            code="GEE_UNAVAILABLE",
            status_code=503,
        )
    return svc


# ── GEE Layers ──


@gee_router.get("/layers")
async def list_gee_layers() -> JSONResponse:
    """Listar capas disponibles en GEE."""
    svc = _lazy_gee_service()
    return JSONResponse(
        content=svc["get_available_layers"](),
        headers={"Cache-Control": "public, max-age=86400"},
    )


@gee_router.get("/layers/tiles/sentinel2")
async def get_sentinel2_tiles(
    start_date: date = Query(..., description="Fecha de inicio (YYYY-MM-DD)"),
    end_date: date = Query(..., description="Fecha de fin (YYYY-MM-DD)"),
    max_cloud: int = Query(40, ge=0, le=100, description="Porcentaje maximo de nubes"),
):
    """Obtener URL de tiles Sentinel-2 RGB para visualizacion."""
    svc = _ensure_gee()
    try:
        gee_service = svc["get_gee_service"]()
        result = await asyncio.to_thread(
            gee_service.get_sentinel2_tiles, start_date, end_date, max_cloud
        )
        if "error" in result:
            raise NotFoundError(message=result["error"], code="SENTINEL2_NOT_FOUND")
        return result
    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo tiles Sentinel-2", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "tiles Sentinel-2"),
            code="GEE_TILES_ERROR",
            status_code=500,
        )


@gee_router.get("/layers/caminos/consorcios")
async def list_consorcios_camineros() -> JSONResponse:
    """Listar consorcios camineros disponibles en la red vial."""
    svc = _ensure_gee()
    try:
        consorcios = await asyncio.to_thread(svc["get_consorcios_camineros"])
        return JSONResponse(
            content={"consorcios": consorcios, "total": len(consorcios)},
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error("Error obteniendo consorcios camineros", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "consorcios camineros"),
            code="GEE_CONSORCIOS_ERROR",
            status_code=500,
        )


@gee_router.get("/layers/caminos/consorcio/{codigo}")
async def get_caminos_consorcio(codigo: str) -> JSONResponse:
    """Obtener caminos de un consorcio caminero especifico."""
    svc = _ensure_gee()
    try:
        geojson = await asyncio.to_thread(svc["get_caminos_by_consorcio"], codigo)
        if not geojson.get("features"):
            raise NotFoundError(
                message=f"No se encontraron caminos para el consorcio '{codigo}'",
                code="CONSORCIO_NOT_FOUND",
                resource_type="consorcio",
                resource_id=codigo,
            )
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo caminos por consorcio", codigo=codigo, error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos del consorcio"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


@gee_router.get("/layers/caminos/por-nombre")
async def get_caminos_por_nombre_consorcio(
    nombre: str = Query(..., description="Nombre del consorcio (ccn)"),
) -> JSONResponse:
    """Obtener caminos de un consorcio caminero por nombre."""
    svc = _ensure_gee()
    try:
        geojson = await asyncio.to_thread(svc["get_caminos_by_consorcio_nombre"], nombre)
        if not geojson.get("features"):
            raise NotFoundError(
                message=f"No se encontraron caminos para el consorcio '{nombre}'",
                code="CONSORCIO_NOT_FOUND",
                resource_type="consorcio",
            )
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except AppException:
        raise
    except Exception as e:
        logger.error("Error obteniendo caminos por nombre", nombre=nombre, error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos del consorcio"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


@gee_router.get("/layers/caminos/coloreados")
async def get_caminos_coloreados() -> JSONResponse:
    """Obtener red vial con colores distintos por consorcio caminero."""
    svc = _ensure_gee()
    try:
        result = await asyncio.to_thread(svc["get_caminos_con_colores"])
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error("Error obteniendo caminos coloreados", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "caminos coloreados"),
            code="GEE_CAMINOS_ERROR",
            status_code=500,
        )


@gee_router.get("/layers/caminos/estadisticas")
async def get_estadisticas_caminos() -> JSONResponse:
    """Obtener estadisticas de kilometros por consorcio caminero."""
    svc = _ensure_gee()
    try:
        result = await asyncio.to_thread(svc["get_estadisticas_consorcios"])
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error("Error obteniendo estadisticas de consorcios", error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "estadisticas de consorcios"),
            code="GEE_STATS_ERROR",
            status_code=500,
        )


@gee_router.get("/layers/{layer_name}")
async def get_gee_layer(layer_name: str) -> JSONResponse:
    """Obtener GeoJSON de una capa desde GEE."""
    svc = _ensure_gee()
    try:
        geojson = await asyncio.to_thread(svc["get_layer_geojson"], layer_name)
        return JSONResponse(
            content=geojson,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except ValueError as e:
        raise NotFoundError(
            message=get_safe_error_detail(e, "capa"),
            code="LAYER_NOT_FOUND",
            resource_type="layer",
            resource_id=layer_name,
        )
    except Exception as e:
        logger.error("Error obteniendo capa GEE", layer=layer_name, error=str(e))
        raise AppException(
            message=get_safe_error_detail(e, "capa GEE"),
            code="GEE_LAYER_ERROR",
            status_code=500,
        )


# ── GEE Analysis CRUD ──


@gee_router.post("/analysis", response_model=AnalisisGeoResponse, status_code=201)
def submit_gee_analysis(
    payload: AnalisisGeoCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """
    Submit a new GEE analysis (flood detection / classification).

    Creates an AnalisisGeo record in PENDING state and dispatches
    the corresponding Celery task in the background.
    """
    from datetime import date as _date

    from app.domains.geo.gee_tasks import (
        analyze_flood_task,
        sar_temporal_task,
        supervised_classification_task,
    )
    from app.domains.geo.models import TipoAnalisisGee

    # Validate tipo
    valid_tipos = [t.value for t in TipoAnalisisGee]
    if payload.tipo not in valid_tipos:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo invalido '{payload.tipo}'. Valores validos: {valid_tipos}",
        )

    # Create analysis record
    analisis = repo.create_analisis(
        db,
        tipo=payload.tipo,
        fecha_analisis=_date.today(),
        parametros=payload.parametros,
    )
    db.commit()
    db.refresh(analisis)

    # Dispatch appropriate task
    start_date = payload.parametros.get("start_date", _date.today().isoformat())
    end_date = payload.parametros.get("end_date", _date.today().isoformat())
    method = payload.parametros.get("method", "fusion")

    if payload.tipo == TipoAnalisisGee.SAR_TEMPORAL.value:
        # Validate date range for SAR temporal
        if start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="start_date debe ser anterior a end_date",
            )
        scale = payload.parametros.get("scale", 100)
        task = sar_temporal_task.delay(
            start_date, end_date, scale, analisis_id=str(analisis.id)
        )
    elif payload.tipo in (TipoAnalisisGee.FLOOD.value, TipoAnalisisGee.CUSTOM.value):
        task = analyze_flood_task.delay(
            start_date, end_date, method, analisis_id=str(analisis.id)
        )
    else:
        task = supervised_classification_task.delay(
            start_date, end_date, analisis_id=str(analisis.id)
        )

    # Store celery_task_id
    repo.update_analisis_status(db, analisis.id, celery_task_id=task.id)
    db.commit()
    db.refresh(analisis)

    return analisis


@gee_router.get("/analysis", response_model=dict)
def list_gee_analyses(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List GEE analyses with pagination and optional filters."""
    items, total = repo.get_analisis_list(
        db,
        page=page,
        limit=limit,
        tipo_filter=tipo,
        estado_filter=estado,
    )
    return {
        "items": [AnalisisGeoListResponse.model_validate(a) for a in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@gee_router.get("/analysis/{analisis_id}", response_model=AnalisisGeoResponse)
def get_gee_analysis(
    analisis_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get GEE analysis detail/result by ID."""
    analisis = repo.get_analisis_by_id(db, analisis_id)
    if analisis is None:
        raise HTTPException(status_code=404, detail="Analisis GEE no encontrado")
    return analisis


# ── GEE Images (Image Explorer) ──


@gee_router.get("/images/available-dates")
async def get_available_image_dates(
    year: int = Query(..., ge=2015, le=2030, description="Ano"),
    month: int = Query(..., ge=1, le=12, description="Mes"),
    sensor: str = Query("sentinel2", description="Sensor: sentinel2 o sentinel1"),
    max_cloud: int = Query(60, ge=0, le=100, description="Porcentaje maximo de nubes (solo S2)"),
):
    """Obtener fechas con imagenes disponibles para un mes dado."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await asyncio.to_thread(
            explorer.get_available_dates,
            year=year,
            month=month,
            sensor=sensor,
            max_cloud=max_cloud,
        )
        return JSONResponse(
            content=result,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "fechas disponibles"),
            code="AVAILABLE_DATES_ERROR",
            status_code=500,
        )


@gee_router.get("/images/sentinel2")
async def get_sentinel2_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30),
    max_cloud: int = Query(40, ge=0, le=100),
    visualization: str = Query("rgb"),
):
    """Obtener tiles de imagen Sentinel-2 para una fecha especifica."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await asyncio.to_thread(
            explorer.get_sentinel2_image,
            target_date=target_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
            visualization=visualization,
        )
        if "error" in result:
            raise NotFoundError(
                message=result.get("error", "Imagen no encontrada"),
                code="SENTINEL2_NOT_FOUND",
            )
        return result
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "imagen Sentinel-2"),
            code="IMAGE_EXPLORER_ERROR",
            status_code=500,
        )


@gee_router.get("/images/sentinel1")
async def get_sentinel1_image(
    target_date: date = Query(..., description="Fecha objetivo (YYYY-MM-DD)"),
    days_buffer: int = Query(10, ge=1, le=30),
    visualization: str = Query("vv"),
):
    """Obtener tiles de imagen Sentinel-1 (SAR) para una fecha especifica."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await asyncio.to_thread(
            explorer.get_sentinel1_image,
            target_date=target_date,
            days_buffer=days_buffer,
            visualization=visualization,
        )
        if "error" in result:
            raise NotFoundError(
                message=result.get("error", "Imagen no encontrada"),
                code="SENTINEL1_NOT_FOUND",
            )
        return result
    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "imagen Sentinel-1"),
            code="IMAGE_EXPLORER_ERROR",
            status_code=500,
        )


@gee_router.get("/images/compare")
async def compare_flood_dates(
    flood_date: date = Query(..., description="Fecha de inundacion"),
    normal_date: date = Query(..., description="Fecha de referencia (sin inundacion)"),
    days_buffer: int = Query(10, ge=1, le=30),
    max_cloud: int = Query(40, ge=0, le=100),
):
    """Comparar imagen de inundacion con imagen normal."""
    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        result = await asyncio.to_thread(
            explorer.get_flood_comparison,
            flood_date=flood_date,
            normal_date=normal_date,
            days_buffer=days_buffer,
            max_cloud=max_cloud,
        )
        return result
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "comparacion de fechas"),
            code="IMAGE_COMPARE_ERROR",
            status_code=500,
        )


@gee_router.get("/images/visualizations")
async def get_available_visualizations():
    """Obtener lista de visualizaciones disponibles para Sentinel-2."""
    from app.domains.geo.gee_service import ImageExplorer

    visualizations = [
        {"id": key, "description": value["description"]}
        for key, value in ImageExplorer.VIS_PRESETS.items()
    ]
    return JSONResponse(
        content=visualizations,
        headers={"Cache-Control": "public, max-age=86400"},
    )


HISTORIC_FLOODS = [
    {
        "id": "feb_2017",
        "name": "Inundacion Febrero 2017",
        "date": "2017-02-20",
        "description": "Gran inundacion que afecto Bell Ville y zona rural",
        "severity": "alta",
    },
    {
        "id": "sep_2025",
        "name": "Inundacion Septiembre 2025",
        "date": "2025-09-05",
        "description": "Evento de anegamiento por lluvias intensas",
        "severity": "media",
    },
]


@gee_router.get("/images/historic-floods")
async def get_historic_floods():
    """Obtener lista de inundaciones historicas pre-configuradas."""
    return JSONResponse(
        content={"floods": HISTORIC_FLOODS, "total": len(HISTORIC_FLOODS)},
        headers={"Cache-Control": "public, max-age=86400"},
    )


@gee_router.get("/images/historic-floods/{flood_id}")
async def get_historic_flood_tiles(
    flood_id: str,
    visualization: str = Query("rgb"),
):
    """Obtener tiles de una inundacion historica pre-configurada."""
    flood = next((f for f in HISTORIC_FLOODS if f["id"] == flood_id), None)
    if not flood:
        raise NotFoundError(
            message=f"Inundacion '{flood_id}' no encontrada",
            code="FLOOD_NOT_FOUND",
            resource_type="historic_flood",
            resource_id=flood_id,
        )

    svc = _ensure_gee()
    try:
        explorer = svc["get_image_explorer"]()
        flood_date = date.fromisoformat(flood["date"])

        is_old_date = flood_date.year < 2020
        days_buffer = 30 if is_old_date else 15

        result = await asyncio.to_thread(
            explorer.get_sentinel2_image,
            target_date=flood_date,
            days_buffer=days_buffer,
            max_cloud=60,
            visualization=visualization,
            use_median=True,
        )

        if "error" in result:
            result = await asyncio.to_thread(
                explorer.get_sentinel1_image,
                target_date=flood_date,
                days_buffer=days_buffer,
                visualization="vv_flood",
            )

        result["flood_info"] = flood
        return result

    except AppException:
        raise
    except Exception as e:
        raise AppException(
            message=get_safe_error_detail(e, "inundacion historica"),
            code="HISTORIC_FLOOD_ERROR",
            status_code=500,
        )


# ── Zonal Statistics ──────────────────────────────────────────────


class ZonalStatsRequest(BaseModel):
    """Request body for zonal statistics computation."""

    layer_tipo: str = Field(
        ...,
        description="GeoLayer type to use as raster (e.g. slope, twi, hand, flow_acc)",
    )
    zona_source: str = Field(
        default="zonas_operativas",
        description="Source table for zones: zonas_operativas, assets, or denuncias",
    )
    area_id: str | None = Field(
        default=None,
        description="Filter GeoLayer by area_id",
    )
    stats: list[str] | None = Field(
        default=None,
        description="Statistics to compute (default: min, max, mean, std, median, count, sum)",
    )


@router.post("/zonal-stats")
def compute_zonal_statistics(
    body: ZonalStatsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compute raster statistics per zone geometry.

    Crosses a raster layer (from the DEM pipeline) with vector zones
    (zonas_operativas, assets, or denuncias) and returns per-zone stats.
    """
    from geoalchemy2.functions import ST_AsText

    # 1. Find the raster layer
    repo = _get_repo()
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == body.layer_tipo)
        .order_by(GeoLayer.created_at.desc())
    )
    if body.area_id:
        layer = layer.filter(GeoLayer.area_id == body.area_id)
    layer = layer.first()

    if not layer:
        raise NotFoundError(f"No GeoLayer found for tipo={body.layer_tipo}")

    # Prefer COG path if available
    raster_path = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            raster_path = cog

    if not Path(raster_path).exists():
        raise AppException(
            message=f"Raster file not found: {raster_path}",
            code="RASTER_NOT_FOUND",
            status_code=404,
        )

    # 2. Fetch zone geometries from PostGIS
    if body.zona_source == "zonas_operativas":
        rows = db.query(
            ZonaOperativa.id,
            ST_AsText(ZonaOperativa.geometria),
            ZonaOperativa.nombre,
        ).all()
    elif body.zona_source == "assets":
        from app.domains.infraestructura.models import Asset

        rows = db.query(
            Asset.id,
            ST_AsText(Asset.geom),
            Asset.nombre,
        ).filter(Asset.geom.isnot(None)).all()
    elif body.zona_source == "denuncias":
        from app.domains.denuncias.models import Denuncia

        rows = db.query(
            Denuncia.id,
            ST_AsText(Denuncia.geom),
            Denuncia.tipo,
        ).filter(Denuncia.geom.isnot(None)).all()
    else:
        raise AppException(
            message=f"Invalid zona_source: {body.zona_source}",
            code="INVALID_ZONA_SOURCE",
            status_code=400,
        )

    if not rows:
        return {"results": [], "count": 0, "raster": body.layer_tipo}

    # 3. Compute zonal stats
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    zone_data = [(str(r[0]), r[1], r[2]) for r in rows]
    results = compute_stats_for_zones(zone_data, raster_path, body.stats)

    return {
        "results": results,
        "count": len(results),
        "raster": body.layer_tipo,
        "zona_source": body.zona_source,
    }


# ── ML: Flood Prediction ──────────────────────────────────────────


@router.get("/ml/flood-prediction/zona/{zona_id}")
def predict_flood_ml(
    zona_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """ML-based flood probability prediction for a zona operativa.

    Combines DEM features (HAND, TWI, slope, flow_acc) with water
    detection data into a weighted model that outputs flood probability
    (0-1) and risk level. Model weights can be trained from historical
    flood events via POST /ml/flood-prediction/train.
    """
    from geoalchemy2.functions import ST_AsText
    from sqlalchemy import select

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {zona_id}")

    # Get raster stats for features
    zona_wkt = db.execute(
        select(ST_AsText(ZonaOperativa.geometria)).where(ZonaOperativa.id == zona_id)
    ).scalar()

    from app.domains.geo.zonal_stats import compute_stats_for_zones
    zone_data = [(str(zona.id), zona_wkt, zona.nombre)]

    features = {
        "zona_id": str(zona.id),
        "zona_name": zona.nombre,
    }

    layer_stats = {}
    for tipo in ["hand", "twi", "slope", "flow_acc"]:
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc())
            .first()
        )
        if not layer:
            continue

        path = layer.archivo_path
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            cog = layer.metadata_extra["cog_path"]
            if Path(cog).exists():
                path = cog

        if not Path(path).exists():
            continue

        try:
            stats = compute_stats_for_zones(zone_data, path, ["mean", "max", "min", "count"])
            if stats and stats[0].get("count", 0) > 0:
                layer_stats[tipo] = stats[0]
        except Exception:
            pass

    # Map to model features
    if "hand" in layer_stats:
        features["hand_mean"] = layer_stats["hand"].get("mean", 0) or 0
        features["hand_min"] = layer_stats["hand"].get("min", 0) or 0
    if "twi" in layer_stats:
        features["twi_mean"] = layer_stats["twi"].get("mean", 0) or 0
        features["twi_max"] = layer_stats["twi"].get("max", 0) or 0
    if "slope" in layer_stats:
        features["slope_mean"] = layer_stats["slope"].get("mean", 0) or 0
    if "flow_acc" in layer_stats:
        features["flow_acc_max"] = layer_stats["flow_acc"].get("max", 0) or 0
        features["flow_acc_mean"] = layer_stats["flow_acc"].get("mean", 0) or 0

    from app.domains.geo.ml.flood_prediction import predict_flood_for_zone

    prediction = predict_flood_for_zone(features)

    return {
        "zona": {"id": str(zona.id), "nombre": zona.nombre, "cuenca": zona.cuenca},
        "features": features,
        **prediction,
    }


@router.get("/ml/flood-prediction/all-zones")
def predict_flood_all_zones(
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Run flood prediction for ALL zonas operativas.

    Returns a ranked list of zones by flood probability, useful for
    prioritizing maintenance and emergency planning.
    """
    from geoalchemy2.functions import ST_AsText
    from sqlalchemy import select

    zonas = db.query(ZonaOperativa).all()
    if not zonas:
        return {"zones": [], "count": 0}

    # Load raster layers once
    raster_paths = {}
    for tipo in ["hand", "twi", "slope", "flow_acc"]:
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc())
            .first()
        )
        if not layer:
            continue
        path = layer.archivo_path
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            cog = layer.metadata_extra["cog_path"]
            if Path(cog).exists():
                path = cog
        if Path(path).exists():
            raster_paths[tipo] = path

    from app.domains.geo.zonal_stats import compute_stats_for_zones
    from app.domains.geo.ml.flood_prediction import FloodModel, ZoneFeatures

    model = FloodModel.load()
    results = []

    for zona in zonas:
        zona_wkt = db.execute(
            select(ST_AsText(ZonaOperativa.geometria)).where(ZonaOperativa.id == zona.id)
        ).scalar()

        zone_data = [(str(zona.id), zona_wkt, zona.nombre)]
        features = ZoneFeatures(zona_id=str(zona.id), zona_name=zona.nombre)

        for tipo, path in raster_paths.items():
            try:
                stats = compute_stats_for_zones(zone_data, path, ["mean", "max", "min", "count"])
                if stats and stats[0].get("count", 0) > 0:
                    s = stats[0]
                    if tipo == "hand":
                        features.hand_mean = s.get("mean", 0) or 0
                        features.hand_min = s.get("min", 0) or 0
                    elif tipo == "twi":
                        features.twi_mean = s.get("mean", 0) or 0
                        features.twi_max = s.get("max", 0) or 0
                    elif tipo == "slope":
                        features.slope_mean = s.get("mean", 0) or 0
                    elif tipo == "flow_acc":
                        features.flow_acc_max = s.get("max", 0) or 0
                        features.flow_acc_mean = s.get("mean", 0) or 0
            except Exception:
                pass

        prediction = model.predict(features)
        results.append({
            "zona_id": str(zona.id),
            "zona_name": zona.nombre,
            "cuenca": zona.cuenca,
            "superficie_ha": zona.superficie_ha,
            "probability": prediction["probability"],
            "risk_level": prediction["risk_level"],
        })

    # Sort by probability descending
    results.sort(key=lambda r: r["probability"], reverse=True)

    return {
        "zones": results,
        "count": len(results),
        "model_version": model.version,
        "layers_used": list(raster_paths.keys()),
    }


@router.get("/ml/model-info")
def get_ml_model_info():
    """Get information about available ML models."""
    from app.domains.geo.ml.flood_prediction import FloodModel
    from app.domains.geo.ml.water_segmentation import UNetStrategy

    flood_model = FloodModel.load()
    unet = UNetStrategy()

    return {
        "flood_prediction": {
            "version": flood_model.version,
            "weights": flood_model.weights,
            "bias": flood_model.bias,
            "trained": "trained" in flood_model.version,
        },
        "water_segmentation": {
            "strategies": ["ndwi", "unet"],
            "unet_model_available": unet.model_available,
            "unet_model_path": str(unet.MODEL_DIR / unet.MODEL_FILE),
        },
    }


# ── Water Detection ───────────────────────────────────────────────


class WaterDetectionRequest(BaseModel):
    """Request for water detection on a zona operativa."""

    zona_id: uuid.UUID
    target_date: str = Field(..., description="Target date YYYY-MM-DD")
    days_window: int = Field(default=15, ge=1, le=60)
    cloud_cover_max: int = Field(default=20, ge=0, le=100)


class WaterMultiDateRequest(BaseModel):
    """Request for multi-date water detection."""

    zona_id: uuid.UUID
    dates: list[str] = Field(..., description="List of target dates YYYY-MM-DD")
    cloud_cover_max: int = Field(default=20, ge=0, le=100)


@router.post("/water-detection/detect")
def detect_water(
    body: WaterDetectionRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Detect water bodies in a zona operativa using Sentinel-2 NDWI.

    Finds the best available Sentinel-2 image near the target date and
    classifies pixels into water/wet/dry based on NDWI thresholds.
    Returns area statistics in hectares and percentages.

    NOTE: This calls GEE and can take 15-30s.
    """
    from geoalchemy2.functions import ST_AsGeoJSON
    from sqlalchemy import select

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == body.zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {body.zona_id}")

    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(ZonaOperativa.id == body.zona_id)
    ).scalar()

    import json
    geometry = json.loads(geojson_str)

    from app.domains.geo.water_detection import detect_water_from_gee

    result = detect_water_from_gee(
        geometry_geojson=geometry,
        target_date=body.target_date,
        days_window=body.days_window,
        cloud_cover_max=body.cloud_cover_max,
    )

    return {"zona": {"id": str(zona.id), "nombre": zona.nombre}, **result}


@router.post("/water-detection/multi-date")
def detect_water_multi(
    body: WaterMultiDateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Run water detection for multiple dates to track water level changes.

    Returns per-date results and a change summary between first and last date.

    NOTE: Each date calls GEE — total time ≈ 15-30s × number of dates.
    """
    from geoalchemy2.functions import ST_AsGeoJSON
    from sqlalchemy import select

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == body.zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {body.zona_id}")

    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(ZonaOperativa.id == body.zona_id)
    ).scalar()

    import json
    geometry = json.loads(geojson_str)

    from app.domains.geo.water_detection import detect_water_multi_date

    result = detect_water_multi_date(
        geometry_geojson=geometry,
        dates=body.dates,
        cloud_cover_max=body.cloud_cover_max,
    )

    return {"zona": {"id": str(zona.id), "nombre": zona.nombre}, **result}


# ── STAC Catalog ──────────────────────────────────────────────────


@router.get("/stac")
def stac_root(request: Request):
    """STAC API root — catalog landing page."""
    base_url = f"{request.base_url}api/v2/geo"
    return {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": "consorcio-canalero",
        "title": "Consorcio Canalero — Geospatial Catalog",
        "description": "Catalog of DEM pipeline outputs, satellite imagery, and analysis results",
        "links": [
            {"rel": "self", "href": f"{base_url}/stac"},
            {"rel": "collections", "href": f"{base_url}/stac/collections"},
            {"rel": "search", "href": f"{base_url}/stac/search"},
        ],
    }


@router.get("/stac/collections")
def stac_collections(
    request: Request,
    db: Session = Depends(get_db),
):
    """List STAC collections (grouped by GeoLayer type)."""
    from app.domains.geo.stac import get_collections
    base_url = f"{request.base_url}api/v2/geo"
    return get_collections(db, base_url)


@router.get("/stac/search")
def stac_search(
    request: Request,
    db: Session = Depends(get_db),
    tipo: str | None = Query(default=None),
    area_id: str | None = Query(default=None),
    fuente: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Search the STAC catalog with filters."""
    from app.domains.geo.stac import search_catalog
    base_url = f"{request.base_url}api/v2/geo"
    return search_catalog(
        db,
        tipo=tipo,
        area_id=area_id,
        fuente=fuente,
        limit=limit,
        offset=offset,
        base_url=base_url,
    )


@router.get("/stac/items/{item_id}")
def stac_item(
    item_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get a single STAC item by ID."""
    from app.domains.geo.stac import layer_to_stac_item
    layer = db.query(GeoLayer).filter(GeoLayer.id == item_id).first()
    if not layer:
        raise NotFoundError(f"Item not found: {item_id}")
    base_url = f"{request.base_url}api/v2/geo"
    return layer_to_stac_item(layer, base_url)


# ── Temporal Analysis ─────────────────────────────────────────────


class NdwiTrendRequest(BaseModel):
    """Request for NDWI time-series analysis via GEE + Xee."""

    zona_id: uuid.UUID = Field(..., description="Zona operativa ID")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    cloud_cover_max: int = Field(default=30, ge=0, le=100)


@router.post("/temporal/ndwi-trend")
def analyze_ndwi_trend(
    body: NdwiTrendRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Analyze NDWI (water index) trend over time for a zona operativa.

    Uses Sentinel-2 imagery from GEE via Xee + xarray. Returns mean NDWI
    per image date, linear trend, and anomalies.

    NOTE: This can take 30-60s depending on the date range and GEE load.
    """
    from geoalchemy2.functions import ST_AsGeoJSON

    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == body.zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona not found: {body.zona_id}")

    # Get geometry as GeoJSON
    from sqlalchemy import select
    geojson_str = db.execute(
        select(ST_AsGeoJSON(ZonaOperativa.geometria)).where(ZonaOperativa.id == body.zona_id)
    ).scalar()

    import json
    geometry = json.loads(geojson_str)

    from app.domains.geo.temporal import analyze_ndwi_trend_gee

    result = analyze_ndwi_trend_gee(
        geometry_geojson=geometry,
        start_date=body.start_date,
        end_date=body.end_date,
        cloud_cover_max=body.cloud_cover_max,
    )

    return {
        "zona": {"id": str(zona.id), "nombre": zona.nombre},
        **result,
    }


class RasterCompareRequest(BaseModel):
    """Request to compare multiple rasters temporally."""

    layer_tipo: str = Field(..., description="GeoLayer type (e.g. slope, twi)")
    zona_id: uuid.UUID | None = Field(default=None, description="Optional zona to clip to")


@router.post("/temporal/compare-rasters")
def compare_rasters(
    body: RasterCompareRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compare multiple rasters of the same type across time.

    Finds all GeoLayers of the given type and computes per-raster stats
    plus change analysis between first and last.
    """
    layers = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == body.layer_tipo)
        .order_by(GeoLayer.created_at.asc())
        .all()
    )

    if not layers:
        raise NotFoundError(f"No layers found for tipo={body.layer_tipo}")

    raster_paths = []
    labels = []
    for layer in layers:
        path = layer.archivo_path
        if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
            cog = layer.metadata_extra["cog_path"]
            if Path(cog).exists():
                path = cog
        if Path(path).exists():
            raster_paths.append(path)
            labels.append(f"{layer.tipo}_{layer.created_at.date()}")

    if not raster_paths:
        raise AppException(message="No raster files found on disk", code="RASTERS_NOT_FOUND", status_code=404)

    # Get zona geometry if provided
    zona_wkt = None
    if body.zona_id:
        from geoalchemy2.functions import ST_AsText
        from sqlalchemy import select
        zona_wkt = db.execute(
            select(ST_AsText(ZonaOperativa.geometria)).where(ZonaOperativa.id == body.zona_id)
        ).scalar()

    from app.domains.geo.temporal import compare_rasters_temporal

    return compare_rasters_temporal(raster_paths, labels, zona_wkt)


# ── Flood Risk Assessment ─────────────────────────────────────────


@router.get("/flood-risk/zona/{zona_id}")
def get_zona_flood_risk(
    zona_id: uuid.UUID,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Compute comprehensive flood risk score for a zona operativa.

    Combines HAND, TWI, flow accumulation, and slope from the DEM
    pipeline into a single risk assessment. Returns individual metrics
    and a composite risk level.
    """
    from geoalchemy2.functions import ST_AsText

    # Get zona geometry
    zona = db.query(ZonaOperativa).filter(ZonaOperativa.id == zona_id).first()
    if not zona:
        raise NotFoundError(f"Zona operativa not found: {zona_id}")

    # Get raster layers
    layers_needed = ["hand", "twi", "flow_acc", "slope"]
    raster_paths = {}
    for tipo in layers_needed:
        layer = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo)
            .order_by(GeoLayer.created_at.desc())
            .first()
        )
        if layer:
            path = layer.archivo_path
            if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
                cog = layer.metadata_extra["cog_path"]
                if Path(cog).exists():
                    path = cog
            if Path(path).exists():
                raster_paths[tipo] = path

    if not raster_paths:
        raise AppException(
            message="No raster layers available for risk calculation",
            code="NO_RASTERS",
            status_code=404,
        )

    # Get zone geometry as WKT
    from sqlalchemy import select
    zona_wkt = db.execute(
        select(ST_AsText(ZonaOperativa.geometria)).where(ZonaOperativa.id == zona_id)
    ).scalar()

    # Compute zonal stats for each available layer
    from app.domains.geo.zonal_stats import compute_stats_for_zones

    zone_data = [(str(zona.id), zona_wkt, zona.nombre)]
    metrics = {}

    for tipo, path in raster_paths.items():
        try:
            stats = compute_stats_for_zones(zone_data, path, ["mean", "max", "min", "median", "count"])
            if stats and stats[0].get("count", 0) > 0:
                metrics[tipo] = {
                    "mean": stats[0].get("mean"),
                    "max": stats[0].get("max"),
                    "min": stats[0].get("min"),
                    "median": stats[0].get("median"),
                }
        except Exception as exc:
            logger.warning("flood_risk.zonal_stats_failed", tipo=tipo, error=str(exc))

    # Compute composite risk score (0-100)
    risk_score = 0
    risk_factors = []

    if "hand" in metrics and metrics["hand"]["mean"] is not None:
        hand_mean = metrics["hand"]["mean"]
        if hand_mean < 0.5:
            risk_score += 40
            risk_factors.append("HAND muy bajo (<0.5m): zona extremadamente baja")
        elif hand_mean < 1.0:
            risk_score += 30
            risk_factors.append("HAND bajo (<1m): zona baja, susceptible a inundación")
        elif hand_mean < 2.0:
            risk_score += 15
            risk_factors.append("HAND moderado (<2m)")

    if "twi" in metrics and metrics["twi"]["mean"] is not None:
        twi_mean = metrics["twi"]["mean"]
        if twi_mean > 14:
            risk_score += 30
            risk_factors.append("TWI alto (>14): alta acumulación de agua")
        elif twi_mean > 11:
            risk_score += 20
            risk_factors.append("TWI moderado (>11): acumulación moderada")
        elif twi_mean > 8:
            risk_score += 5

    if "flow_acc" in metrics and metrics["flow_acc"]["max"] is not None:
        fa_max = metrics["flow_acc"]["max"]
        if fa_max > 100000:
            risk_score += 20
            risk_factors.append("Flow accumulation extremo: recibe mucha agua upstream")
        elif fa_max > 10000:
            risk_score += 10
            risk_factors.append("Flow accumulation alto")

    if "slope" in metrics and metrics["slope"]["mean"] is not None:
        slope_mean = metrics["slope"]["mean"]
        if slope_mean < 0.3:
            risk_score += 10
            risk_factors.append("Pendiente muy baja (<0.3°): agua no drena")
        elif slope_mean < 0.5:
            risk_score += 5

    risk_score = min(risk_score, 100)
    risk_level = (
        "critico" if risk_score >= 70 else
        "alto" if risk_score >= 50 else
        "moderado" if risk_score >= 30 else
        "bajo"
    )

    return {
        "zona": {
            "id": str(zona.id),
            "nombre": zona.nombre,
            "cuenca": zona.cuenca,
            "superficie_ha": zona.superficie_ha,
        },
        "risk_score": risk_score,
        "risk_level": risk_level,
        "metrics": metrics,
        "risk_factors": risk_factors,
        "layers_used": list(raster_paths.keys()),
    }


# ── Hydrology Analysis ────────────────────────────────────────────


@router.get("/hydrology/twi-summary")
def get_twi_summary(
    area_id: str = Query(default="zona_principal"),
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Get TWI classification summary with area statistics per zone."""
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == "twi", GeoLayer.area_id == area_id)
        .order_by(GeoLayer.created_at.desc())
        .first()
    )
    if not layer:
        raise NotFoundError(f"No TWI layer found for area_id={area_id}")

    raster_path = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            raster_path = cog

    if not Path(raster_path).exists():
        raise AppException(message="TWI raster not found", code="RASTER_NOT_FOUND", status_code=404)

    from app.domains.geo.hydrology import compute_twi_zone_summary

    return compute_twi_zone_summary(raster_path)


@router.get("/hydrology/canal-capacity")
def get_canal_capacity(
    area_id: str = Query(default="zona_principal"),
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Analyze flow accumulation along canal segments to identify capacity risks.

    Returns canals sorted by maximum upstream flow, indicating which
    segments receive the most water and are at risk of overflowing.
    """
    layer = (
        db.query(GeoLayer)
        .filter(GeoLayer.tipo == "flow_acc", GeoLayer.area_id == area_id)
        .order_by(GeoLayer.created_at.desc())
        .first()
    )
    if not layer:
        raise NotFoundError(f"No flow_acc layer found for area_id={area_id}")

    raster_path = layer.archivo_path
    if layer.metadata_extra and layer.metadata_extra.get("cog_path"):
        cog = layer.metadata_extra["cog_path"]
        if Path(cog).exists():
            raster_path = cog

    if not Path(raster_path).exists():
        raise AppException(message="Flow accumulation raster not found", code="RASTER_NOT_FOUND", status_code=404)

    # Use canales_existentes as the primary canal source
    canal_path = "/app/data/waterways/canales_existentes.geojson"
    if not Path(canal_path).exists():
        raise AppException(message="Canal GeoJSON not found", code="GEOJSON_NOT_FOUND", status_code=404)

    from app.domains.geo.hydrology import compute_flow_acc_at_canals

    results = compute_flow_acc_at_canals(raster_path, canal_path)

    return {
        "area_id": area_id,
        "canals_analyzed": len(results),
        "results": results,
    }


# ── Canal Network Routing (pgRouting) ─────────────────────────────


class ImportCanalsRequest(BaseModel):
    """Request to import canals from GeoJSON into the routing network."""

    geojson_paths: list[str] = Field(
        ...,
        description="List of GeoJSON file paths to import",
    )
    rebuild_topology: bool = Field(
        default=True,
        description="Rebuild pgRouting topology after import",
    )
    tolerance: float = Field(
        default=0.0001,
        description="Snapping tolerance for topology",
    )


class ShortestPathRequest(BaseModel):
    """Request for shortest path between two points."""

    from_lon: float
    from_lat: float
    to_lon: float
    to_lat: float


@router.post("/routing/import")
def import_canal_network(
    body: ImportCanalsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Import canal GeoJSON files into the routing network and build topology."""
    from app.domains.geo.routing import (
        import_canals_from_geojson,
        build_topology,
        get_network_stats,
    )

    total_imported = 0
    for path in body.geojson_paths:
        tipo = Path(path).stem
        count = import_canals_from_geojson(db, path, tipo=tipo)
        total_imported += count

    topology = None
    if body.rebuild_topology and total_imported > 0:
        topology = build_topology(db, tolerance=body.tolerance)

    stats = get_network_stats(db)

    return {
        "imported": total_imported,
        "topology": topology,
        "network": stats,
    }


@router.post("/routing/shortest-path")
def find_shortest_path(
    body: ShortestPathRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Find shortest path between two points on the canal network.

    Snaps input coordinates to the nearest network vertices, then
    runs Dijkstra's algorithm via pgRouting.
    """
    from app.domains.geo.routing import find_nearest_vertex, shortest_path

    source = find_nearest_vertex(db, body.from_lon, body.from_lat)
    target = find_nearest_vertex(db, body.to_lon, body.to_lat)

    if not source or not target:
        raise NotFoundError("No vertices found near the given coordinates")

    path = shortest_path(db, source["id"], target["id"])

    # Build GeoJSON FeatureCollection for the path
    features = []
    for edge in path:
        if edge["geometry"]:
            features.append({
                "type": "Feature",
                "properties": {
                    "nombre": edge["nombre"],
                    "cost": edge["cost"],
                    "agg_cost": edge["agg_cost"],
                    "path_seq": edge["path_seq"],
                },
                "geometry": edge["geometry"],
            })

    total_cost = path[-1]["agg_cost"] if path else 0

    return {
        "source": source,
        "target": target,
        "total_distance_m": round(total_cost, 2),
        "edges": len(path),
        "geojson": {
            "type": "FeatureCollection",
            "features": features,
        },
    }


@router.get("/routing/stats")
def get_routing_network_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(_require_operator),
):
    """Get canal network statistics."""
    from app.domains.geo.routing import get_network_stats

    return get_network_stats(db)


# ──────────────────────────────────────────────
# FLOOD EVENTS (calibration labels)
# ──────────────────────────────────────────────


def _run_feature_extraction(
    event_id: uuid.UUID,
    event_date: date,
    label_ids_and_zonas: list[tuple[str, str]],
) -> None:
    """Background task: extract features for each label in a flood event.

    Runs in a separate thread via asyncio.to_thread so the response
    is returned immediately.  Opens its own DB session.
    """
    from app.db.session import SessionLocal

    repo = GeoRepository()
    db = SessionLocal()
    try:
        for label_id_str, zona_id_str in label_ids_and_zonas:
            try:
                features = repo.extract_zone_features(
                    db,
                    zona_id=uuid.UUID(zona_id_str),
                    event_date=event_date,
                )
                if features:
                    repo.update_label_features(
                        db, uuid.UUID(label_id_str), features
                    )
                    db.commit()
            except Exception:
                logger.warning(
                    "Feature extraction failed for label %s",
                    label_id_str,
                    exc_info=True,
                )
                db.rollback()
    finally:
        db.close()


@router.post("/flood-events", status_code=201)
async def create_flood_event(
    payload: FloodEventCreate,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Create a labeled flood event with per-zone labels.

    After persisting the event, triggers background feature extraction
    for each labeled zone via asyncio.to_thread.
    """
    # Validate no duplicate zona_ids
    zona_ids = [label.zona_id for label in payload.labels]
    if len(zona_ids) != len(set(zona_ids)):
        raise HTTPException(status_code=422, detail="duplicate zona_id in labels")

    labels_data = [
        {"zona_id": label.zona_id, "is_flooded": label.is_flooded}
        for label in payload.labels
    ]

    event = repo.create_flood_event(
        db,
        event_date=payload.event_date,
        description=payload.description,
        labels=labels_data,
    )
    db.commit()

    # Re-fetch with labels loaded
    created = repo.get_flood_event_by_id(db, event.id)

    # Kick off background feature extraction (non-blocking)
    label_ids_and_zonas = [
        (str(lbl.id), str(lbl.zona_id)) for lbl in created.labels
    ]
    asyncio.ensure_future(
        asyncio.to_thread(
            _run_feature_extraction,
            created.id,
            payload.event_date,
            label_ids_and_zonas,
        )
    )

    return {
        "id": str(created.id),
        "event_date": str(created.event_date),
        "description": created.description,
        "satellite_source": created.satellite_source,
        "labels": [
            {
                "id": str(lbl.id),
                "zona_id": str(lbl.zona_id),
                "is_flooded": lbl.is_flooded,
                "ndwi_value": lbl.ndwi_value,
                "extracted_features": lbl.extracted_features,
            }
            for lbl in created.labels
        ],
        "created_at": created.created_at.isoformat(),
        "updated_at": created.updated_at.isoformat(),
    }


@router.get("/flood-events")
def list_flood_events(
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """List all flood events ordered by event_date desc."""
    events = repo.list_flood_events(db)
    return [
        {
            "id": str(e["id"]),
            "event_date": str(e["event_date"]),
            "description": e["description"],
            "label_count": e["label_count"],
            "created_at": e["created_at"].isoformat(),
        }
        for e in events
    ]


@router.get("/flood-events/{event_id}")
def get_flood_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_authenticated()),
):
    """Get a single flood event with all labels."""
    event = repo.get_flood_event_by_id(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Flood event not found")

    return {
        "id": str(event.id),
        "event_date": str(event.event_date),
        "description": event.description,
        "satellite_source": event.satellite_source,
        "labels": [
            {
                "id": str(lbl.id),
                "zona_id": str(lbl.zona_id),
                "is_flooded": lbl.is_flooded,
                "ndwi_value": lbl.ndwi_value,
                "extracted_features": lbl.extracted_features,
            }
            for lbl in event.labels
        ],
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


@router.delete("/flood-events/{event_id}", status_code=204)
def delete_flood_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    repo: GeoRepository = Depends(_get_repo),
    _user=Depends(_require_operator()),
):
    """Delete a flood event and all its labels (cascade)."""
    deleted = repo.delete_flood_event(db, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Flood event not found")
    db.commit()
    return Response(status_code=204)


# ── Include GEE sub-router into main geo router ──
router.include_router(gee_router)

# ── Include Intelligence sub-router ──
from app.domains.geo.intelligence.router import router as intel_router

router.include_router(intel_router, prefix="/intelligence")
