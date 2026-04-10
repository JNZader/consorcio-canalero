from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

_UPSERT_PARCELA_SQL = text("""
    INSERT INTO parcelas_catastro
        (id, nomenclatura, geometria, tipo_parcela, desig_oficial,
         departamento, pedania, superficie_ha, nro_cuenta, par_idparcela)
    VALUES (
        gen_random_uuid(),
        :nomenclatura,
        ST_GeomFromGeoJSON(:geom_json),
        :tipo_parcela,
        :desig_oficial,
        :departamento,
        :pedania,
        :superficie_ha,
        :nro_cuenta,
        :par_idparcela
    )
    ON CONFLICT (nomenclatura) DO UPDATE SET
        geometria    = EXCLUDED.geometria,
        tipo_parcela = EXCLUDED.tipo_parcela,
        desig_oficial = EXCLUDED.desig_oficial,
        departamento  = EXCLUDED.departamento,
        pedania       = EXCLUDED.pedania,
        superficie_ha = EXCLUDED.superficie_ha,
        nro_cuenta    = EXCLUDED.nro_cuenta,
        par_idparcela = EXCLUDED.par_idparcela
""")

_AFECTADOS_BY_ZONA_SQL = text("""
    SELECT c.id AS consorcista_id, c.nombre AS nombre, c.parcela AS parcela, pc.superficie_ha AS hectareas,
           pc.nomenclatura AS nomenclatura, zo.nombre AS zona_nombre, zo.id::text AS zona_id
    FROM consorcistas c
    JOIN parcelas_catastro pc ON pc.nomenclatura = c.parcela
    JOIN zonas_operativas zo ON ST_Intersects(pc.geometria, zo.geometria)
    WHERE zo.id = CAST(:zona_id AS uuid)
    ORDER BY c.nombre
""")


def bulk_upsert_parcelas(db: Session, features: list[dict]) -> tuple[int, int]:
    imported = skipped = 0
    for feature in features:
        props = feature.get("properties") or {}
        nomenclatura, geometry = props.get("Nomenclatura"), feature.get("geometry")
        if not nomenclatura or not geometry:
            skipped += 1
            continue
        sup_m2 = props.get("Superficie_Tierra_Rural")
        superficie_ha = round(sup_m2 / 10_000, 4) if sup_m2 else None
        nro_cuenta = props.get("Nro_Cuenta")
        try:
            db.execute(
                _UPSERT_PARCELA_SQL,
                {
                    "nomenclatura": str(nomenclatura),
                    "geom_json": json.dumps(geometry),
                    "tipo_parcela": props.get("Tipo_Parcela"),
                    "desig_oficial": props.get("desig_oficial"),
                    "departamento": props.get("departamento"),
                    "pedania": props.get("pedania"),
                    "superficie_ha": superficie_ha,
                    "nro_cuenta": str(nro_cuenta) if nro_cuenta is not None else None,
                    "par_idparcela": props.get("par_idparcela"),
                },
            )
            imported += 1
        except Exception:
            skipped += 1
    db.commit()
    return imported, skipped


def get_afectados_by_zona(db: Session, zona_id: str) -> dict | None:
    rows = db.execute(_AFECTADOS_BY_ZONA_SQL, {"zona_id": zona_id}).mappings().all()
    zona_row = (
        db.execute(
            text(
                "SELECT id, nombre FROM zonas_operativas WHERE id = CAST(:id AS uuid)"
            ),
            {"id": zona_id},
        )
        .mappings()
        .first()
    )
    if zona_row is None:
        return None
    afectados = [dict(r) for r in rows]
    total_ha = sum(a["hectareas"] or 0 for a in afectados)
    return {
        "zona_id": zona_id,
        "zona_nombre": zona_row["nombre"],
        "total_consorcistas": len(afectados),
        "total_ha": round(total_ha, 2),
        "afectados": afectados,
    }


def get_afectados_by_flood_event(db: Session, event_id: str) -> dict | None:
    event_row = (
        db.execute(
            text(
                "SELECT id, event_date FROM flood_events WHERE id = CAST(:id AS uuid)"
            ),
            {"id": event_id},
        )
        .mappings()
        .first()
    )
    if event_row is None:
        return None
    flooded_zones = (
        db.execute(
            text("""
        SELECT zo.id::text AS zona_id
        FROM flood_labels fl
        JOIN zonas_operativas zo ON zo.id = fl.zona_id
        WHERE fl.event_id = CAST(:event_id AS uuid) AND fl.is_flooded = true
    """),
            {"event_id": event_id},
        )
        .mappings()
        .all()
    )
    zonas_afectadas = [
        zona_data
        for row in flooded_zones
        if (zona_data := get_afectados_by_zona(db, row["zona_id"]))
    ]
    all_consorcista_ids = {
        a["consorcista_id"] for z in zonas_afectadas for a in z["afectados"]
    }
    total_ha = sum(z["total_ha"] for z in zonas_afectadas)
    return {
        "event_id": event_id,
        "event_date": str(event_row["event_date"]),
        "total_consorcistas": len(all_consorcista_ids),
        "total_ha": round(total_ha, 2),
        "zonas_afectadas": zonas_afectadas,
    }
