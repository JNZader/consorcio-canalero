from __future__ import annotations

import io
import json
import uuid
import zipfile
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.domains.geo.models import GeoLayer, TipoAnalisisGee
from app.domains.geo.repository import GeoRepository
from app.domains.geo.schemas import AnalisisGeoListResponse
from app.shared.celery_outbox import (
    CeleryTaskKey,
    enqueue_celery_task,
    try_publish_celery_task,
)
from app.shared.pagination import PaginatedResponse

logger = get_logger(__name__)


def export_geo_bundle_impl(
    db: Session, repo: GeoRepository, build_zonas_export, build_approved_export
):
    zonas_payload = build_zonas_export(db)
    approved_payload = build_approved_export(db, repo)
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
        bundle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "geo-bundle-v1",
                    "vectors": {
                        "zonas_operativas": "vectors/zonas_operativas.geojson",
                        "approved_zoning": "vectors/approved_zoning.json"
                        if approved_payload
                        else None,
                    },
                    "layers": manifest_layers,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="geo_bundle_{date.today().isoformat()}.zip"'
        },
    )


def export_current_approved_basin_zones_pdf_impl(
    cuenca: Optional[str], db: Session, repo: GeoRepository, get_user_display_name
):
    from app.shared.pdf import build_approved_zoning_pdf, get_branding

    zoning = repo.get_active_approved_zoning(db, cuenca=cuenca)
    if zoning is None:
        raise HTTPException(status_code=404, detail="No hay una zonificación aprobada activa")
    pdf_buffer = build_approved_zoning_pdf(
        zoning,
        get_branding(db),
        approved_by_name=get_user_display_name(db, zoning.approved_by_id),
    )
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="zonificacion-aprobada-v{zoning.version}.pdf"'
        },
    )


def export_current_map_approved_basin_zones_pdf_impl(payload, db: Session):
    from app.shared.pdf import build_approved_zoning_map_pdf, get_branding

    return StreamingResponse(
        build_approved_zoning_map_pdf(payload.model_dump(by_alias=True), get_branding(db)),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="zonificacion-aprobada-mapa.pdf"'},
    )


def _get_gee_task_key_map() -> Mapping[TipoAnalisisGee, CeleryTaskKey]:
    """Map every accepted analysis family to a fixed outbox task key."""
    return {
        TipoAnalisisGee.FLOOD: CeleryTaskKey.ANALYZE_FLOOD,
        TipoAnalisisGee.VEGETATION: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoAnalisisGee.CLASSIFICATION: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoAnalisisGee.NDVI: CeleryTaskKey.SUPERVISED_CLASSIFICATION,
        TipoAnalisisGee.CUSTOM: CeleryTaskKey.ANALYZE_FLOOD,
        TipoAnalisisGee.SAR_TEMPORAL: CeleryTaskKey.SAR_TEMPORAL,
    }


def _resolve_gee_task_plan(
    tipo: str | TipoAnalisisGee,
    parametros: dict,
    *,
    today: date,
) -> tuple[TipoAnalisisGee, CeleryTaskKey, dict[str, object]]:
    """Validate a submission and build broker kwargs before persistence."""
    valid_tipos = [member.value for member in TipoAnalisisGee]
    try:
        normalized_tipo = TipoAnalisisGee(tipo)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo invalido '{tipo}'. Valores validos: {valid_tipos}",
        ) from exc

    task_key = _get_gee_task_key_map().get(normalized_tipo)
    if task_key is None:
        raise RuntimeError("Unsupported GEE analysis task mapping")

    start_raw = parametros.get("start_date", today.isoformat())
    end_raw = parametros.get("end_date", today.isoformat())
    try:
        start_date = date.fromisoformat(str(start_raw))
        end_date = date.fromisoformat(str(end_raw))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="start_date y end_date deben usar YYYY-MM-DD",
        ) from exc
    if start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date debe ser anterior a end_date")

    task_kwargs: dict[str, object] = {
        "start_date_str": start_date.isoformat(),
        "end_date_str": end_date.isoformat(),
    }
    if normalized_tipo in (TipoAnalisisGee.FLOOD, TipoAnalisisGee.CUSTOM):
        method = parametros.get("method", "fusion")
        if not isinstance(method, str) or method not in {
            "fusion",
            "sar_only",
            "optical_only",
        }:
            raise HTTPException(status_code=422, detail="method invalido")
        task_kwargs["method"] = method
    elif normalized_tipo == TipoAnalisisGee.SAR_TEMPORAL:
        try:
            scale = int(parametros.get("scale", 100))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="scale debe ser un entero") from exc
        if not 1 <= scale <= 10_000:
            raise HTTPException(status_code=422, detail="scale fuera de rango")
        task_kwargs["scale"] = scale

    return normalized_tipo, task_key, task_kwargs


def _rollback_gee_submission_quietly(db: Session) -> None:
    try:
        db.rollback()
    except Exception as rollback_error:
        logger.error(
            "gee_analysis.submission_rollback_failed",
            error_type=type(rollback_error).__name__,
        )


def submit_gee_analysis_impl(payload, db: Session, repo: GeoRepository):
    """Atomically persist an AnalisisGeo and its Celery publication intent."""
    today = date.today()
    stored_parameters = dict(payload.parametros)
    normalized_tipo, task_key, base_task_kwargs = _resolve_gee_task_plan(
        payload.tipo,
        stored_parameters,
        today=today,
    )
    celery_task_id = uuid.uuid4()

    try:
        analisis = repo.create_analisis(
            db,
            tipo=normalized_tipo,
            fecha_analisis=today,
            parametros=stored_parameters,
            usuario_id=None,
            celery_task_id=str(celery_task_id),
        )
        outbox = enqueue_celery_task(
            db,
            celery_task_id=celery_task_id,
            task_key=task_key,
            task_kwargs={**base_task_kwargs, "analisis_id": str(analisis.id)},
        )
        db.commit()
    except Exception:
        _rollback_gee_submission_quietly(db)
        raise

    db.refresh(analisis)
    try:
        published = try_publish_celery_task(outbox.id)
    except Exception as publication_error:
        published = False
        logger.error(
            "gee_analysis.outbox_immediate_publish_failed",
            analisis_id=str(analisis.id),
            outbox_id=str(outbox.id),
            error_type=type(publication_error).__name__,
        )

    if not published:
        logger.warning(
            "gee_analysis.outbox_publication_deferred",
            analisis_id=str(analisis.id),
            outbox_id=str(outbox.id),
            task_key=task_key.value,
        )
    return analisis


def list_gee_analyses_impl(
    page: int,
    limit: int,
    tipo: Optional[str],
    estado: Optional[str],
    db: Session,
    repo: GeoRepository,
) -> PaginatedResponse[AnalisisGeoListResponse]:
    items, total = repo.get_analisis_list(
        db, page=page, limit=limit, tipo_filter=tipo, estado_filter=estado
    )
    return PaginatedResponse[AnalisisGeoListResponse].create(
        items=[AnalisisGeoListResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        limit=limit,
    )


def get_gee_analysis_impl(analisis_id, db: Session, repo: GeoRepository):
    analisis = repo.get_analisis_by_id(db, analisis_id)
    if analisis is None:
        raise HTTPException(status_code=404, detail="Analisis GEE no encontrado")
    return analisis
