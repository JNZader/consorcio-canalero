from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.domains.geo.models import GeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.schemas import AnalisisGeoListResponse


def export_geo_bundle_impl(db: Session, repo: GeoRepository, build_zonas_export, build_approved_export):
    zonas_payload = build_zonas_export(db)
    approved_payload = build_approved_export(db, repo)
    layers = db.query(GeoLayer).order_by(GeoLayer.created_at.asc()).all()
    buffer = io.BytesIO()
    manifest_layers = []
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("vectors/zonas_operativas.geojson", json.dumps(zonas_payload, ensure_ascii=False, indent=2))
        if approved_payload is not None:
            bundle.writestr("vectors/approved_zoning.json", json.dumps(approved_payload, ensure_ascii=False, indent=2))
        for layer in layers:
            file_path = Path(layer.archivo_path)
            if not file_path.exists() or not file_path.is_file():
                continue
            archive_path = f"layers/{layer.id}_{file_path.name}"
            bundle.write(file_path, archive_path)
            manifest_layers.append({"nombre": layer.nombre, "tipo": layer.tipo, "fuente": layer.fuente, "formato": layer.formato, "srid": layer.srid, "bbox": layer.bbox, "metadata_extra": layer.metadata_extra, "area_id": layer.area_id, "archive_path": archive_path, "original_path": layer.archivo_path})
        bundle.writestr("manifest.json", json.dumps({"format": "geo-bundle-v1", "vectors": {"zonas_operativas": "vectors/zonas_operativas.geojson", "approved_zoning": "vectors/approved_zoning.json" if approved_payload else None}, "layers": manifest_layers}, ensure_ascii=False, indent=2))
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="geo_bundle_{date.today().isoformat()}.zip"'})


def export_current_approved_basin_zones_pdf_impl(cuenca: Optional[str], db: Session, repo: GeoRepository, get_user_display_name):
    from app.shared.pdf import build_approved_zoning_pdf, get_branding

    zoning = repo.get_active_approved_zoning(db, cuenca=cuenca)
    if zoning is None:
        raise HTTPException(status_code=404, detail="No hay una zonificación aprobada activa")
    pdf_buffer = build_approved_zoning_pdf(zoning, get_branding(db), approved_by_name=get_user_display_name(db, zoning.approved_by_id))
    return StreamingResponse(pdf_buffer, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="zonificacion-aprobada-v{zoning.version}.pdf"'})


def export_current_map_approved_basin_zones_pdf_impl(payload, db: Session):
    from app.shared.pdf import build_approved_zoning_map_pdf, get_branding

    return StreamingResponse(build_approved_zoning_map_pdf(payload.model_dump(by_alias=True), get_branding(db)), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="zonificacion-aprobada-mapa.pdf"'})


def import_canal_network_impl(body, db: Session):
    from app.domains.geo.routing import build_topology, get_network_stats, import_canals_from_geojson

    total_imported = 0
    for path in body.geojson_paths:
        total_imported += import_canals_from_geojson(db, path, tipo=Path(path).stem)
    topology = build_topology(db, tolerance=body.tolerance) if body.rebuild_topology and total_imported > 0 else None
    return {"imported": total_imported, "topology": topology, "network": get_network_stats(db)}


def submit_gee_analysis_impl(payload, db: Session, repo: GeoRepository):
    from datetime import date as _date

    from app.domains.geo.gee_tasks import analyze_flood_task, sar_temporal_task, supervised_classification_task
    from app.domains.geo.models import TipoAnalisisGee

    valid_tipos = [t.value for t in TipoAnalisisGee]
    if payload.tipo not in valid_tipos:
        raise HTTPException(status_code=422, detail=f"Tipo invalido '{payload.tipo}'. Valores validos: {valid_tipos}")
    analisis = repo.create_analisis(db, tipo=payload.tipo, fecha_analisis=_date.today(), parametros=payload.parametros)
    db.commit()
    db.refresh(analisis)
    start_date = payload.parametros.get("start_date", _date.today().isoformat())
    end_date = payload.parametros.get("end_date", _date.today().isoformat())
    method = payload.parametros.get("method", "fusion")
    if payload.tipo == TipoAnalisisGee.SAR_TEMPORAL.value:
        if start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date debe ser anterior a end_date")
        task = sar_temporal_task.delay(start_date, end_date, payload.parametros.get("scale", 100), analisis_id=str(analisis.id))
    elif payload.tipo in (TipoAnalisisGee.FLOOD.value, TipoAnalisisGee.CUSTOM.value):
        task = analyze_flood_task.delay(start_date, end_date, method, analisis_id=str(analisis.id))
    else:
        task = supervised_classification_task.delay(start_date, end_date, analisis_id=str(analisis.id))
    repo.update_analisis_status(db, analisis.id, celery_task_id=task.id)
    db.commit()
    db.refresh(analisis)
    return analisis


def list_gee_analyses_impl(page: int, limit: int, tipo: Optional[str], estado: Optional[str], db: Session, repo: GeoRepository):
    items, total = repo.get_analisis_list(db, page=page, limit=limit, tipo_filter=tipo, estado_filter=estado)
    return {"items": [AnalisisGeoListResponse.model_validate(a) for a in items], "total": total, "page": page, "limit": limit}


def get_gee_analysis_impl(analisis_id, db: Session, repo: GeoRepository):
    analisis = repo.get_analisis_by_id(db, analisis_id)
    if analisis is None:
        raise HTTPException(status_code=404, detail="Analisis GEE no encontrado")
    return analisis
