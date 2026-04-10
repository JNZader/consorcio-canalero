"""Geo bundle import/export endpoints."""

import io
import json
import shutil
import uuid
import zipfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.models import GeoLayer
from app.domains.geo.repository import GeoRepository
from app.domains.geo.router_common import (
    GeoBundleImportResponse,
    _build_approved_zoning_export,
    _build_zonas_operativas_export,
    _get_geo_bundle_storage_dir,
    _get_repo,
    _import_approved_zoning_payload,
    _import_zonas_operativas_payload,
    _require_admin,
    _upsert_bundle_layer,
)

router = APIRouter(tags=["Geo Processing"])

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
                "approved_zoning": "vectors/approved_zoning.json"
                if approved_payload
                else None,
            },
            "layers": manifest_layers,
        }
        bundle.writestr(
            "manifest.json", json.dumps(manifest_payload, ensure_ascii=False, indent=2)
        )

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
                raise HTTPException(
                    status_code=400, detail="El bundle no contiene manifest.json"
                ) from exc

            bundle_dir = (
                _get_geo_bundle_storage_dir()
                / f"import_{date.today().isoformat()}_{uuid.uuid4().hex[:8]}"
            )
            bundle_dir.mkdir(parents=True, exist_ok=True)

            vectors_imported: dict[str, int] = {}

            zonas_path = manifest.get("vectors", {}).get("zonas_operativas")
            if zonas_path:
                zonas_payload = json.loads(archive.read(zonas_path).decode("utf-8"))
                zonas_result = _import_zonas_operativas_payload(db, zonas_payload)
                vectors_imported["zonas_operativas"] = zonas_result["imported_count"]

            approved_path = manifest.get("vectors", {}).get("approved_zoning")
            if approved_path:
                approved_payload = json.loads(
                    archive.read(approved_path).decode("utf-8")
                )
                approved_result = _import_approved_zoning_payload(
                    db,
                    repo,
                    approved_payload,
                    approved_by_id=getattr(user, "id", None),
                    notes=f"Importado desde bundle: {file.filename}",
                )
                vectors_imported["zonificacion_aprobada"] = approved_result[
                    "imported_count"
                ]

            layers_imported = 0
            for layer_entry in manifest.get("layers", []):
                archive_path = layer_entry.get("archive_path")
                if not archive_path:
                    continue
                target_path = bundle_dir / Path(archive_path).name
                with (
                    archive.open(archive_path) as source,
                    target_path.open("wb") as target,
                ):
                    shutil.copyfileobj(source, target)

                _upsert_bundle_layer(
                    db,
                    nombre=str(layer_entry.get("nombre") or target_path.stem),
                    tipo=str(layer_entry.get("tipo") or "dem_raw"),
                    fuente=str(layer_entry.get("fuente") or "manual"),
                    archivo_path=str(target_path),
                    formato=str(
                        layer_entry.get("formato")
                        or target_path.suffix.lstrip(".")
                        or "geotiff"
                    ),
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
