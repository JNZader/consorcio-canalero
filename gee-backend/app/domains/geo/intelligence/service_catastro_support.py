"""Support helpers for intelligence service catastro/afectados endpoints."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.geo.intelligence.repository import (
    bulk_upsert_parcelas,
    get_afectados_by_flood_event,
    get_afectados_by_zona,
)
from app.domains.geo.schemas import (
    AfectadosResponse,
    EventoAfectadosResponse,
    ParcelaImportResult,
)


def import_catastro_geojson(db: Session, geojson_data: dict) -> ParcelaImportResult:
    if geojson_data.get("type") != "FeatureCollection":
        raise HTTPException(
            status_code=400, detail="Se esperaba un GeoJSON de tipo FeatureCollection"
        )
    features = geojson_data.get("features") or []
    if not features:
        raise HTTPException(status_code=400, detail="El GeoJSON no contiene features")
    imported, skipped = bulk_upsert_parcelas(db, features)
    return ParcelaImportResult(imported=imported, skipped=skipped, total=len(features))


def get_afectados_zona(db: Session, zona_id: str) -> AfectadosResponse:
    data = get_afectados_by_zona(db, zona_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Zona operativa no encontrada")
    return AfectadosResponse(**data)


def get_afectados_evento(db: Session, event_id: str) -> EventoAfectadosResponse:
    data = get_afectados_by_flood_event(db, event_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail="Evento de inundación no encontrado"
        )
    return EventoAfectadosResponse(**data)
