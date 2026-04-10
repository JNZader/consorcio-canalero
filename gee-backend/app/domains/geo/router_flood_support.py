from __future__ import annotations

import uuid
from datetime import date

from fastapi import HTTPException

from app.core.exceptions import AppException


def run_feature_extraction_impl(
    *,
    event_id: uuid.UUID,
    event_date: date,
    label_ids_and_zonas: list[tuple[str, str]],
    session_local,
    geo_repository_cls,
    logger,
) -> None:
    """Background task: extract features for each label in a flood event."""
    repo = geo_repository_cls()
    db = session_local()
    extracted_count = 0
    failed_count = 0
    try:
        for label_id_str, zona_id_str in label_ids_and_zonas:
            try:
                features = repo.extract_zone_features(
                    db,
                    zona_id=uuid.UUID(zona_id_str),
                    event_date=event_date,
                )
                if features:
                    repo.update_label_features(db, uuid.UUID(label_id_str), features)
                    db.commit()
                    extracted_count += 1
                else:
                    failed_count += 1
                    logger.warning(
                        "feature_extraction.empty_result",
                        label_id=label_id_str,
                        zona_id=zona_id_str,
                    )
            except Exception:
                failed_count += 1
                logger.warning(
                    "feature_extraction.failed — GEE may be unavailable. "
                    "label=%s zona=%s event=%s",
                    label_id_str,
                    zona_id_str,
                    str(event_id),
                    exc_info=True,
                )
                db.rollback()
        logger.info(
            "feature_extraction.complete event=%s extracted=%d failed=%d",
            str(event_id),
            extracted_count,
            failed_count,
        )
    finally:
        db.close()


def create_flood_event_impl(
    *,
    payload,
    db,
    repo,
    zona_operativa_model,
    flood_event_model,
    run_feature_extraction,
    asyncio_module,
) -> dict:
    """Create a labeled flood event and schedule feature extraction."""
    zona_ids = [label.zona_id for label in payload.labels]
    if len(zona_ids) != len(set(zona_ids)):
        raise HTTPException(status_code=422, detail="Zona duplicada en las etiquetas")

    existing_zonas = {
        row.id
        for row in db.query(zona_operativa_model.id)
        .filter(zona_operativa_model.id.in_(zona_ids))
        .all()
    }
    missing = set(zona_ids) - existing_zonas
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Zonas no encontradas: {', '.join(str(z) for z in missing)}",
        )

    existing_event = (
        db.query(flood_event_model)
        .filter(flood_event_model.event_date == payload.event_date)
        .first()
    )
    if existing_event:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un evento para la fecha {payload.event_date}",
        )

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

    created = repo.get_flood_event_by_id(db, event.id)
    if created is None:
        raise AppException(
            message="Flood event not found after creation",
            code="FLOOD_EVENT_NOT_FOUND",
            status_code=404,
        )

    label_ids_and_zonas = [(str(lbl.id), str(lbl.zona_id)) for lbl in created.labels]
    asyncio_module.ensure_future(
        asyncio_module.to_thread(
            run_feature_extraction,
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


def train_flood_model_impl(
    *,
    db,
    repo,
    flood_model_cls,
    model_path,
    shutil_module,
    response_cls,
):
    """Train the flood prediction model from labeled events."""
    labels = repo.get_labels_with_features(db)
    if len(labels) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Se necesitan al menos 5 etiquetas con features extraidas para entrenar. Actualmente hay {len(labels)}. Asegurate de que los eventos tengan features extraidas (puede tardar unos segundos despues de guardar).",
        )

    training_data = [
        {"features": label.extracted_features, "flooded": label.is_flooded}
        for label in labels
    ]

    model = flood_model_cls.load()
    weights_before = dict(model.weights)

    backup_path = model_path.parent / "flood_model_backup.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if model_path.exists():
        shutil_module.copy2(str(model_path), str(backup_path))
    else:
        model.save(str(backup_path))

    result = model.train_from_events(training_data)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    model.save()
    return response_cls(
        events_used=result["events"],
        epochs=result["epochs"],
        initial_loss=result["initial_loss"],
        final_loss=result["final_loss"],
        weights_before=weights_before,
        weights_after=result["weights"],
        bias=result["bias"],
        backup_path=str(backup_path),
    )
