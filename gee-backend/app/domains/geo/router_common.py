"""Shared router models and helpers for the geo domain."""

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.models import User
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


class ApprovedZonesMapPdfRequest(BaseModel):
    title: str
    subtitle: Optional[str] = None
    map_image_data_url: str = Field(..., alias="mapImageDataUrl")
    zone_legend: list[MapLegendItemRequest] = Field(
        default_factory=list, alias="zoneLegend"
    )
    road_legend: list[MapLegendItemRequest] = Field(
        default_factory=list, alias="roadLegend"
    )
    canal_legend: list[CanalDetailRowRequest] = Field(
        default_factory=list, alias="canalLegend"
    )
    raster_legends: list[RasterLegendGroupRequest] = Field(
        default_factory=list, alias="rasterLegends"
    )
    info_rows: list[MapInfoRowRequest] = Field(default_factory=list, alias="infoRows")
    zone_summary: list[ZoneSummaryRowRequest] = Field(
        default_factory=list, alias="zoneSummary"
    )


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
    raise HTTPException(
        status_code=500, detail="No se pudo preparar el directorio de bundles geo"
    )


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
            raise HTTPException(
                status_code=400, detail=f"Feature {index} sin geometria"
            )

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
            raise HTTPException(
                status_code=400, detail="El archivo no contiene zonas aprobadas"
            )

        normalized_features = []
        zone_names = {}
        assignments = {}
        approved_name = "Zonificación Consorcio aprobada"
        approved_cuenca = None

        for index, feature in enumerate(features, start=1):
            geometry = feature.get("geometry")
            if not geometry:
                raise HTTPException(
                    status_code=400, detail=f"Feature {index} sin geometria"
                )

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
                source_properties.get("zone_id")
                or props.get("zone_id")
                or f"zone_{index}"
            )
            zone_name = str(
                source_properties.get("name") or props.get("name") or f"Zona {index}"
            )
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
