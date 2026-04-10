"""Support helpers for hydrology service orchestration."""

from __future__ import annotations

import json
import math
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any


def get_canal_length_for_zona_impl(
    *,
    db,
    text_fn,
    logger,
    zona_id: uuid.UUID,
    zona_geometria: dict[str, Any],
    superficie_ha: float,
) -> float:
    fallback_m = math.sqrt(superficie_ha * 10_000)
    try:
        geojson_str = json.dumps(zona_geometria)
        row = db.execute(
            text_fn(
                "SELECT MAX(ST_Length(ST_Transform(geom, 32721))) "
                "FROM waterways "
                "WHERE ST_Within(geom, ST_GeomFromGeoJSON(:zona_geojson))"
            ),
            {"zona_geojson": geojson_str},
        ).scalar()
        if row is None:
            logger.debug(
                "No waterways found in zona %s — using sqrt fallback %.1f m",
                zona_id,
                fallback_m,
            )
            return fallback_m
        return float(row)
    except Exception as exc:
        logger.debug(
            "waterways query failed for zona %s (%s) — using sqrt fallback %.1f m",
            zona_id,
            exc,
            fallback_m,
        )
        return fallback_m


def get_rainfall_intensity_impl(
    *, db, select_fn, rainfall_model, logger, zona_id: uuid.UUID, fecha_lluvia: date
) -> float:
    stmt = (
        select_fn(rainfall_model)
        .where(
            rainfall_model.zona_operativa_id == zona_id,
            rainfall_model.date == fecha_lluvia,
        )
        .limit(1)
    )
    record = db.execute(stmt).scalar_one_or_none()
    if record is None:
        logger.debug(
            "No CHIRPS record for zona %s on %s — using fallback 20 mm/h",
            zona_id,
            fecha_lluvia,
        )
        return 20.0
    return record.precipitation_mm / 6.0


def get_zona_geojson_impl(
    *, db, select_fn, st_as_geojson, zona_model, json_module, zona_id: uuid.UUID
):
    geojson_str = db.execute(
        select_fn(st_as_geojson(zona_model.geometria)).where(zona_model.id == zona_id)
    ).scalar()
    return None if geojson_str is None else json_module.loads(geojson_str)


def preload_zona_db_data_impl(
    *,
    db,
    zona_ids,
    select_fn,
    zona_model,
    get_zona_geojson,
    get_canal_length_for_zona,
    get_rainfall_intensity,
    fecha_lluvia: date,
) -> tuple[dict[uuid.UUID, Any], dict[uuid.UUID, dict[str, Any]], list[dict[str, Any]]]:
    stmt = select_fn(zona_model).where(zona_model.id.in_(zona_ids))
    zona_map = {z.id: z for z in db.execute(stmt).scalars().all()}
    zona_db_data: dict[uuid.UUID, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for zona_id in zona_ids:
        zona = zona_map.get(zona_id)
        if zona is None:
            errors.append(
                {"zona_id": str(zona_id), "error": "Zona operativa no encontrada"}
            )
            continue
        geometria = get_zona_geojson(db, zona_id)
        if geometria is None:
            errors.append(
                {"zona_id": str(zona_id), "error": "La zona no tiene geometría cargada"}
            )
            continue
        superficie_ha = zona.superficie_ha or 1.0
        l_m = get_canal_length_for_zona(db, zona_id, geometria, superficie_ha)
        try:
            db.rollback()
        except Exception:
            pass
        intensidad_mm_h = get_rainfall_intensity(db, zona_id, fecha_lluvia)
        zona_db_data[zona_id] = {
            "zona": zona,
            "geometria": geometria,
            "superficie_ha": superficie_ha,
            "L_m": l_m,
            "intensidad_mm_h": intensidad_mm_h,
            "capacidad_m3s": getattr(zona, "capacidad_m3s", None),
        }
    return zona_map, zona_db_data, errors


def run_gee_for_zonas_impl(
    *, zona_db_data, fecha_lluvia: date, get_slope_from_gee, get_ndvi_and_c, logger
) -> dict[uuid.UUID, dict[str, Any]]:
    def _gee_for_zona(zona_id: uuid.UUID) -> dict[str, Any]:
        data = zona_db_data[zona_id]
        geometria = data["geometria"]
        slope_degrees = get_slope_from_gee(geometria)
        slope_rad = math.radians(slope_degrees)
        s_val = math.tan(slope_rad)
        c_val, c_source = get_ndvi_and_c(geometria, fecha_lluvia)
        return {"S": s_val, "c_val": c_val, "c_source": c_source}

    gee_results: dict[uuid.UUID, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_zona = {
            executor.submit(_gee_for_zona, zona_id): zona_id for zona_id in zona_db_data
        }
        for future in as_completed(future_to_zona):
            zona_id = future_to_zona[future]
            try:
                gee_results[zona_id] = future.result()
            except Exception as exc:
                logger.error("flood_flow.gee_error zona=%s error=%s", zona_id, exc)
                gee_results[zona_id] = {
                    "S": math.tan(math.radians(0.5)),
                    "c_val": 0.4,
                    "c_source": "fallback_default",
                }
    return gee_results


def finalize_flood_flow_impl(
    *,
    db,
    zona_db_data,
    gee_results,
    fecha_lluvia: date,
    today: date,
    repository,
    kirpich_tc,
    rational_method_q,
    classify_hydraulic_risk,
    result_schema,
    logger,
):
    results = []
    errors = []
    for zona_id, db_data in zona_db_data.items():
        try:
            gee = gee_results[zona_id]
            zona = db_data["zona"]
            tc = kirpich_tc(db_data["L_m"], gee["S"])
            q_val = rational_method_q(
                gee["c_val"],
                db_data["intensidad_mm_h"],
                db_data["superficie_ha"] / 100.0,
            )
            nivel_riesgo, porcentaje = classify_hydraulic_risk(
                q_val, db_data["capacidad_m3s"]
            )
            payload = {
                "fecha_calculo": today,
                "tc_minutos": tc,
                "c_escorrentia": gee["c_val"],
                "c_source": gee["c_source"],
                "intensidad_mm_h": db_data["intensidad_mm_h"],
                "area_km2": db_data["superficie_ha"] / 100.0,
                "caudal_m3s": q_val,
                "capacidad_m3s": db_data["capacidad_m3s"],
                "porcentaje_capacidad": porcentaje,
                "nivel_riesgo": nivel_riesgo,
            }
            repository.upsert(db, zona_id, fecha_lluvia, payload)
            results.append(
                result_schema(
                    zona_id=zona_id,
                    zona_nombre=zona.nombre,
                    tc_minutos=tc,
                    c_escorrentia=gee["c_val"],
                    c_source=gee["c_source"],
                    intensidad_mm_h=db_data["intensidad_mm_h"],
                    area_km2=db_data["superficie_ha"] / 100.0,
                    caudal_m3s=q_val,
                    capacidad_m3s=db_data["capacidad_m3s"],
                    porcentaje_capacidad=porcentaje,
                    nivel_riesgo=nivel_riesgo,
                    fecha_lluvia=fecha_lluvia,
                    fecha_calculo=today,
                )
            )
        except Exception as exc:
            logger.error(
                "flood_flow.compute_error zona=%s error=%s", zona_id, exc, exc_info=True
            )
            errors.append({"zona_id": str(zona_id), "error": str(exc)})
    db.commit()
    return results, errors
