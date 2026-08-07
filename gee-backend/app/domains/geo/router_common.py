"""Shared router models and helpers for the geo domain."""

import json
import threading
import uuid
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from app.auth.models import User
from app.config import settings
from app.domains.geo.intelligence.models import ZonaOperativa
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.models import GeoLayer
from app.domains.geo.repository import GeoRepository


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


class CanalDetailRowRequest(BaseModel):
    """Per-canal row for the "Canales existentes (Pilar Azul)" PDF table.

    Distinct from `MapLegendItemRequest` because the third column is a numeric
    `km` value (rendered in a dedicated narrow column), NOT a free-form detail
    string. The TOTAL row is computed server-side from the sum of `km`."""

    label: str
    color: str
    km: float

    model_config = ConfigDict(populate_by_name=True)


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


# Every list on the public map-PDF request is bounded. The body limit alone is
# not enough: 8 MiB of minimal JSON rows is still ~100 k table rows, and a
# reportlab Table is laid out row by row. Mirrors the ficha's "cap before
# compute" rule for a route whose compute is PDF layout instead of raster.
_MAX_LEGEND_ITEMS = settings.geo_map_pdf_max_legend_items


class ApprovedZonesMapPdfRequest(BaseModel):
    title: str = Field(..., max_length=300)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    map_image_data_url: str = Field(..., alias="mapImageDataUrl")
    zone_legend: list[MapLegendItemRequest] = Field(
        default_factory=list, alias="zoneLegend", max_length=_MAX_LEGEND_ITEMS
    )
    road_legend: list[MapLegendItemRequest] = Field(
        default_factory=list, alias="roadLegend", max_length=_MAX_LEGEND_ITEMS
    )
    canal_legend: list[CanalDetailRowRequest] = Field(
        default_factory=list, alias="canalLegend", max_length=_MAX_LEGEND_ITEMS
    )
    raster_legends: list[RasterLegendGroupRequest] = Field(
        default_factory=list, alias="rasterLegends", max_length=_MAX_LEGEND_ITEMS
    )
    info_rows: list[MapInfoRowRequest] = Field(
        default_factory=list, alias="infoRows", max_length=_MAX_LEGEND_ITEMS
    )
    zone_summary: list[ZoneSummaryRowRequest] = Field(
        default_factory=list, alias="zoneSummary", max_length=_MAX_LEGEND_ITEMS
    )


async def cache_bounded_request_body(
    request: Request,
    *,
    maximum: int,
    too_large_detail: str,
    invalid_length_detail: str,
    disconnected_detail: str,
) -> bytes:
    """Cache a request stream while enforcing its byte bound before parsing."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            length = int(declared)
            if length < 0:
                raise ValueError
            if length > maximum:
                raise HTTPException(status_code=413, detail=too_large_detail)
        except ValueError:
            raise HTTPException(status_code=422, detail=invalid_length_detail) from None
    if not hasattr(request, "_body"):
        chunks: list[bytes] = []
        read = 0
        try:
            async for chunk in request.stream():
                read += len(chunk)
                if read > maximum:
                    raise HTTPException(status_code=413, detail=too_large_detail)
                chunks.append(chunk)
        except ClientDisconnect:
            raise HTTPException(status_code=400, detail=disconnected_detail) from None
        request._body = b"".join(chunks)
    return await request.body()


async def parse_bounded_json_object(
    request: Request,
    *,
    maximum: int,
    detail_prefix: str,
) -> dict:
    """Read one bounded JSON object without letting FastAPI pre-buffer a typed body."""
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail=f"{detail_prefix} requires application/json")
    raw = await cache_bounded_request_body(
        request,
        maximum=maximum,
        too_large_detail=f"{detail_prefix} body exceeds limit",
        invalid_length_detail=f"{detail_prefix} has invalid content-length",
        disconnected_detail=f"{detail_prefix} body disconnected",
    )
    try:
        payload = json.loads(raw or b"null")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail=f"{detail_prefix} body must be valid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail=f"{detail_prefix} body must be a JSON object")
    return payload


async def enforce_map_pdf_body_limit(request: Request) -> None:
    """413 BEFORE parsing the public map-PDF body.

    Same shape as ``router_ficha.enforce_body_limit`` (JDB-007) and for the same
    reason: the per-field caps above only fire once the whole body has been
    deserialized, so without this a 500 MB "map capture" would be read and
    base64-decoded in full first. A declared ``Content-Length`` over the cap is
    refused outright; a chunked body with no ``Content-Length`` is read through
    a counting guard that aborts at the same threshold, and the bytes read are
    cached on the request so the parser below reuses them.

    Kept local instead of importing the ficha dependency because that one is
    wired to the ficha error envelope (``codigo``) and to a 1 MiB cap sized for
    a drawn polygon, which a legitimate map capture exceeds.

    THE ROUTE MUST NOT DECLARE A PYDANTIC BODY PARAMETER. FastAPI resolves a
    declared body field by awaiting ``request.body()`` BEFORE it solves
    dependencies, so by the time this runs ``request._body`` already exists and
    the stream-counting branch below is dead code — which leaves a chunked body
    (no ``Content-Length``) completely uncapped. Measured on fastapi 0.135.2
    against this app: with a body param, an 8.4 MB chunked POST reached the
    handler; without it, the same request is a clean 413. That is why the body
    arrives through ``parse_map_pdf_body`` instead, exactly like the ficha's
    ``payload: Any = Depends(parse_ficha_body)``.
    """
    maximum = settings.geo_map_pdf_max_body_bytes
    await cache_bounded_request_body(
        request,
        maximum=maximum,
        too_large_detail=f"Cuerpo mayor a {maximum} bytes",
        invalid_length_detail="content-length invalido",
        disconnected_detail="Cliente desconectado",
    )


# Hand-written request schema for the map-PDF route. Because the body is parsed
# through a dependency (see ``enforce_map_pdf_body_limit``), FastAPI cannot infer
# it. Pydantic's default ``$defs`` refs are valid JSON Schema 2020-12, which is
# what OpenAPI 3.1 (the version FastAPI emits) uses, so the document stays
# self-contained — no hoisting into ``components`` needed.
MAP_PDF_OPENAPI_EXTRA: dict = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": ApprovedZonesMapPdfRequest.model_json_schema()}},
    }
}


# In-flight bound for the public map-PDF build. Own semaphore, NOT the ficha's:
# the two are unrelated public surfaces, and sharing one would let an
# unauthenticated PDF flood starve the ficha's raster slots (and the reverse).
# Sized independently against the pixel cap — see ``geo_map_pdf_max_concurrency``.
# Built lazily so tests can change the setting first, mirroring
# ``ficha_service.get_ficha_slots``.
_pdf_slots: threading.BoundedSemaphore | None = None
PDF_SEMAFORO_TIMEOUT_S = 2.0


def get_map_pdf_slots() -> threading.BoundedSemaphore:
    """The in-flight bound for map-PDF builds. Built on first use."""
    global _pdf_slots  # noqa: PLW0603
    if _pdf_slots is None:
        _pdf_slots = threading.BoundedSemaphore(settings.geo_map_pdf_max_concurrency)
    return _pdf_slots


def reset_map_pdf_slots() -> None:
    """Drop the cached semaphore so the next call re-reads the setting (tests)."""
    global _pdf_slots  # noqa: PLW0603
    _pdf_slots = None


@contextmanager
def slot_de_pdf() -> Iterator[None]:
    """Bound simultaneous PDF builds; 503 on timeout.

    The pixel cap bounds ONE request (~120 MB RGB worst case); without a slot
    bound, N unauthenticated requests materialise N of those at once. The
    handler is sync and runs on Starlette's threadpool, so this is the real
    ceiling on concurrent image memory for this route.
    """
    slots = get_map_pdf_slots()
    if not slots.acquire(timeout=PDF_SEMAFORO_TIMEOUT_S):
        raise HTTPException(
            status_code=503,
            detail="Exportacion de mapa saturada, reintente en unos segundos",
            headers={"Retry-After": str(int(PDF_SEMAFORO_TIMEOUT_S) or 1)},
        )
    try:
        yield
    finally:
        slots.release()


async def parse_map_pdf_body(request: Request) -> ApprovedZonesMapPdfRequest:
    """Validate the map-PDF body AFTER the size guard, never before.

    Mirrors ``router_ficha.parse_ficha_body``: validation happens here instead of
    through a declared body parameter so that the body-limit dependency is the
    first thing that touches the stream. Keeping this as a dependency is what
    makes the 413 real (see ``enforce_map_pdf_body_limit``), so do NOT "simplify"
    it back into a typed parameter on the route signature.
    """
    crudo = await request.body()
    try:
        datos = json.loads(crudo or b"null")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="El cuerpo debe ser JSON valido")
    if not isinstance(datos, dict):
        raise HTTPException(status_code=422, detail="El cuerpo debe ser un objeto JSON")
    try:
        return ApprovedZonesMapPdfRequest.model_validate(datos)
    except ValidationError as exc:
        primero = exc.errors()[0]
        campo = ".".join(str(parte) for parte in primero.get("loc", ()))
        raise HTTPException(
            status_code=422,
            detail=f"{campo or 'cuerpo'}: {primero.get('msg', '')}",
        ) from exc


_tile_client = None


def _get_tile_client():
    global _tile_client  # noqa: PLW0603
    if _tile_client is None:
        _tile_client = httpx.AsyncClient(timeout=10.0)
    return _tile_client


def _get_repo() -> GeoRepository:
    return GeoRepository()


def _require_operator():
    from app.auth import require_admin_or_operator

    return require_admin_or_operator


def _require_authenticated():
    from app.auth import require_authenticated

    return require_authenticated


def _require_admin():
    from app.auth import require_admin

    return require_admin


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
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Use archivos .geojson o .json",
        )


def _read_geojson_upload(content: bytes) -> dict:
    if not content:
        raise HTTPException(status_code=400, detail="Archivo vacio")

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="GeoJSON invalido") from exc

    if payload.get("type") != "FeatureCollection":
        raise HTTPException(
            status_code=400, detail="El archivo debe ser un FeatureCollection GeoJSON"
        )

    features = payload.get("features")
    if not isinstance(features, list):
        raise HTTPException(
            status_code=400,
            detail="El archivo GeoJSON no contiene una lista de features",
        )

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
    cuencas: Counter[str] = Counter()
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
            zone_id = str(
                source_properties.get("zone_id") or props.get("zone_id") or f"zone_{index}"
            )
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
        existing = (
            db.query(GeoLayer)
            .filter(GeoLayer.tipo == tipo, GeoLayer.area_id == area_id)
            .one_or_none()
        )
    else:
        existing = (
            db.query(GeoLayer)
            .filter(
                GeoLayer.tipo == tipo,
                GeoLayer.nombre == nombre,
                GeoLayer.area_id.is_(None),
            )
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
