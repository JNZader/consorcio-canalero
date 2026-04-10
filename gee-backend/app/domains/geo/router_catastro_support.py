from __future__ import annotations


async def import_catastro_impl(*, geojson_data: dict, db, import_catastro_geojson):
    return import_catastro_geojson(db, geojson_data)


async def afectados_por_zona_impl(*, zona_id: str, db, get_afectados_zona):
    return get_afectados_zona(db, zona_id)


async def afectados_por_evento_impl(*, event_id: str, db, get_afectados_evento):
    return get_afectados_evento(db, event_id)
