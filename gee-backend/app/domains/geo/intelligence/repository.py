"""Repository layer — all database access for the intelligence sub-module."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from app.domains.geo.intelligence.models import (
    AlertaGeo,
    CanalSuggestion,
    CompositeZonalStats,
    IndiceHidrico,
    PuntoConflicto,
    ZonaOperativa,
)


class IntelligenceRepository:
    """Data-access layer for operational intelligence entities."""

    # ── ZONA OPERATIVA ────────────────────────────

    def get_zona_by_id(
        self, db: Session, zona_id: uuid.UUID
    ) -> Optional[ZonaOperativa]:
        stmt = select(ZonaOperativa).where(ZonaOperativa.id == zona_id)
        return db.execute(stmt).scalar_one_or_none()

    def get_zonas(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 50,
        cuenca_filter: Optional[str] = None,
    ) -> tuple[list[ZonaOperativa], int]:
        base = select(ZonaOperativa)
        if cuenca_filter:
            base = base.where(ZonaOperativa.cuenca == cuenca_filter)

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(ZonaOperativa.nombre).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def create_zona(
        self,
        db: Session,
        *,
        nombre: str,
        geometria: str,
        cuenca: str,
        superficie_ha: float = 0.0,
    ) -> ZonaOperativa:
        zona = ZonaOperativa(
            nombre=nombre,
            geometria=geometria,
            cuenca=cuenca,
            superficie_ha=superficie_ha,
        )
        db.add(zona)
        db.flush()
        return zona

    def delete_zonas_by_cuenca(self, db: Session, cuenca: str) -> int:
        """Delete all ZonaOperativa records for a given cuenca. Returns count deleted."""
        from sqlalchemy import delete

        stmt = delete(ZonaOperativa).where(ZonaOperativa.cuenca == cuenca)
        result = db.execute(stmt)
        db.flush()
        return result.rowcount

    def get_zonas_as_geojson(
        self,
        db: Session,
        *,
        bbox: tuple[float, float, float, float] | None = None,
        tolerance: float = 0.001,
        limit: int = 500,
        cuenca_filter: str | None = None,
    ) -> dict:
        """Return ZonaOperativa records as a GeoJSON FeatureCollection.

        Uses PostGIS ``ST_AsGeoJSON(ST_Simplify(...))`` so geometry
        simplification and serialisation happen entirely in the database.

        Args:
            db: Database session.
            bbox: Optional (minx, miny, maxx, maxy) bounding box filter.
            tolerance: Simplification tolerance in degrees (default ~100 m).
            limit: Maximum number of features returned.
            cuenca_filter: Optional watershed name filter.

        Returns:
            A GeoJSON FeatureCollection dict.
        """
        geojson_col = func.ST_AsGeoJSON(
            func.ST_Simplify(ZonaOperativa.geometria, tolerance)
        ).label("geojson")

        stmt = select(
            ZonaOperativa.id,
            ZonaOperativa.nombre,
            ZonaOperativa.cuenca,
            ZonaOperativa.superficie_ha,
            geojson_col,
        )

        if cuenca_filter:
            stmt = stmt.where(ZonaOperativa.cuenca == cuenca_filter)

        if bbox is not None:
            minx, miny, maxx, maxy = bbox
            envelope = func.ST_MakeEnvelope(minx, miny, maxx, maxy, 4326)
            stmt = stmt.where(
                func.ST_Intersects(ZonaOperativa.geometria, envelope)
            )

        stmt = stmt.order_by(ZonaOperativa.nombre).limit(limit)

        rows = db.execute(stmt).all()

        import json as _json

        features = []
        for row in rows:
            geometry = _json.loads(row.geojson) if row.geojson else None
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "id": str(row.id),
                        "nombre": row.nombre,
                        "cuenca": row.cuenca,
                        "superficie_ha": row.superficie_ha,
                    },
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "total": len(features),
                "tolerance": tolerance,
                "bbox": list(bbox) if bbox else None,
            },
        }

    def get_zonas_for_grouping(
        self,
        db: Session,
        *,
        cuenca_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return operational basins with full geometry for grouping heuristics."""
        geojson_col = func.ST_AsGeoJSON(ZonaOperativa.geometria).label("geojson")

        stmt = select(
            ZonaOperativa.id,
            ZonaOperativa.nombre,
            ZonaOperativa.cuenca,
            ZonaOperativa.superficie_ha,
            geojson_col,
        ).order_by(ZonaOperativa.nombre)

        if cuenca_filter:
            stmt = stmt.where(ZonaOperativa.cuenca == cuenca_filter)

        rows = db.execute(stmt).all()

        import json as _json

        features: list[dict[str, Any]] = []
        for row in rows:
            geometry = _json.loads(row.geojson) if row.geojson else None
            if geometry is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "id": str(row.id),
                        "nombre": row.nombre,
                        "cuenca": row.cuenca,
                        "superficie_ha": row.superficie_ha,
                    },
                }
            )
        return features

    def get_zonas_criticas(
        self, db: Session, nivel_riesgo_min: str = "alto"
    ) -> list[ZonaOperativa]:
        """Get zones whose latest HCI is above the given risk threshold.

        Args:
            db: Database session.
            nivel_riesgo_min: Minimum risk level ('medio', 'alto', 'critico').

        Returns:
            List of zones at or above the threshold.
        """
        niveles = ["bajo", "medio", "alto", "critico"]
        min_idx = niveles.index(nivel_riesgo_min) if nivel_riesgo_min in niveles else 2
        target_niveles = niveles[min_idx:]

        # Subquery: latest HCI per zone
        latest_hci = (
            select(
                IndiceHidrico.zona_id,
                func.max(IndiceHidrico.fecha_calculo).label("max_fecha"),
            )
            .group_by(IndiceHidrico.zona_id)
            .subquery()
        )

        stmt = (
            select(ZonaOperativa)
            .join(IndiceHidrico, IndiceHidrico.zona_id == ZonaOperativa.id)
            .join(
                latest_hci,
                (IndiceHidrico.zona_id == latest_hci.c.zona_id)
                & (IndiceHidrico.fecha_calculo == latest_hci.c.max_fecha),
            )
            .where(IndiceHidrico.nivel_riesgo.in_(target_niveles))
        )
        return list(db.execute(stmt).scalars().all())

    # ── INDICE HIDRICO ────────────────────────────

    def get_indices_hidricos(
        self,
        db: Session,
        *,
        zona_id: Optional[uuid.UUID] = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[IndiceHidrico], int]:
        base = select(IndiceHidrico)
        if zona_id:
            base = base.where(IndiceHidrico.zona_id == zona_id)

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(IndiceHidrico.fecha_calculo.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def create_indice_hidrico(
        self,
        db: Session,
        *,
        zona_id: uuid.UUID,
        fecha_calculo: date,
        pendiente_media: float,
        acumulacion_media: float,
        twi_medio: float,
        proximidad_canal_m: float,
        historial_inundacion: float,
        indice_final: float,
        nivel_riesgo: str,
    ) -> IndiceHidrico:
        ih = IndiceHidrico(
            zona_id=zona_id,
            fecha_calculo=fecha_calculo,
            pendiente_media=pendiente_media,
            acumulacion_media=acumulacion_media,
            twi_medio=twi_medio,
            proximidad_canal_m=proximidad_canal_m,
            historial_inundacion=historial_inundacion,
            indice_final=indice_final,
            nivel_riesgo=nivel_riesgo,
        )
        db.add(ih)
        db.flush()
        return ih

    # ── PUNTO DE CONFLICTO ────────────────────────

    def get_conflictos(
        self,
        db: Session,
        *,
        tipo_filter: Optional[str] = None,
        severidad_filter: Optional[str] = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[PuntoConflicto], int]:
        base = select(PuntoConflicto)
        if tipo_filter:
            base = base.where(PuntoConflicto.tipo == tipo_filter)
        if severidad_filter:
            base = base.where(PuntoConflicto.severidad == severidad_filter)

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(PuntoConflicto.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def get_conflictos_por_zona(
        self, db: Session, zona_id: uuid.UUID
    ) -> list[PuntoConflicto]:
        """Get conflicts within an operational zone (spatial query)."""
        zona = self.get_zona_by_id(db, zona_id)
        if zona is None:
            return []

        stmt = select(PuntoConflicto).where(
            func.ST_Within(PuntoConflicto.geometria, zona.geometria)
        )
        return list(db.execute(stmt).scalars().all())

    def create_conflicto(
        self,
        db: Session,
        *,
        tipo: str,
        geometria: str,
        descripcion: str,
        severidad: str,
        infraestructura_ids: Optional[list[str]] = None,
        acumulacion_valor: float = 0.0,
        pendiente_valor: float = 0.0,
    ) -> PuntoConflicto:
        conflicto = PuntoConflicto(
            tipo=tipo,
            geometria=geometria,
            descripcion=descripcion,
            severidad=severidad,
            infraestructura_ids=infraestructura_ids,
            acumulacion_valor=acumulacion_valor,
            pendiente_valor=pendiente_valor,
        )
        db.add(conflicto)
        db.flush()
        return conflicto

    def bulk_create_conflictos(
        self, db: Session, conflictos: list[dict[str, Any]]
    ) -> int:
        """Bulk insert conflict points. Returns count of inserted rows."""
        objects = [PuntoConflicto(**c) for c in conflictos]
        db.add_all(objects)
        db.flush()
        return len(objects)

    # ── ALERTAS ───────────────────────────────────

    def get_alertas_activas(
        self, db: Session, *, limit: int = 100
    ) -> list[AlertaGeo]:
        stmt = (
            select(AlertaGeo)
            .where(AlertaGeo.activa.is_(True))
            .order_by(AlertaGeo.created_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    def create_alerta(
        self,
        db: Session,
        *,
        tipo: str,
        mensaje: str,
        nivel: str,
        zona_id: Optional[uuid.UUID] = None,
        datos: Optional[dict] = None,
    ) -> AlertaGeo:
        alerta = AlertaGeo(
            tipo=tipo,
            mensaje=mensaje,
            nivel=nivel,
            zona_id=zona_id,
            datos=datos,
        )
        db.add(alerta)
        db.flush()
        return alerta

    def deactivate_alerta(
        self, db: Session, alerta_id: uuid.UUID
    ) -> Optional[AlertaGeo]:
        stmt = select(AlertaGeo).where(AlertaGeo.id == alerta_id)
        alerta = db.execute(stmt).scalar_one_or_none()
        if alerta:
            alerta.activa = False
            db.flush()
        return alerta

    # ── DASHBOARD ─────────────────────────────────

    def get_dashboard_inteligente(self, db: Session) -> dict[str, Any]:
        """Compute aggregated intelligence dashboard metrics."""
        # Total zones and their areas
        zonas_total = db.execute(
            select(func.count()).select_from(ZonaOperativa)
        ).scalar_one()

        # Count zones by risk level (latest HCI per zone)
        latest_hci = (
            select(
                IndiceHidrico.zona_id,
                func.max(IndiceHidrico.fecha_calculo).label("max_fecha"),
            )
            .group_by(IndiceHidrico.zona_id)
            .subquery()
        )

        zonas_por_nivel: dict[str, int] = {"bajo": 0, "medio": 0, "alto": 0, "critico": 0}
        nivel_counts = db.execute(
            select(IndiceHidrico.nivel_riesgo, func.count())
            .join(
                latest_hci,
                (IndiceHidrico.zona_id == latest_hci.c.zona_id)
                & (IndiceHidrico.fecha_calculo == latest_hci.c.max_fecha),
            )
            .group_by(IndiceHidrico.nivel_riesgo)
        ).all()

        for nivel, count in nivel_counts:
            if nivel in zonas_por_nivel:
                zonas_por_nivel[nivel] = count

        # Area at risk (medio+)
        at_risk_count = (
            zonas_por_nivel.get("medio", 0)
            + zonas_por_nivel.get("alto", 0)
            + zonas_por_nivel.get("critico", 0)
        )
        pct_risk = (at_risk_count / zonas_total * 100.0) if zonas_total > 0 else 0.0

        # Active conflicts and alerts
        conflictos = db.execute(
            select(func.count()).select_from(PuntoConflicto)
        ).scalar_one()

        alertas = db.execute(
            select(func.count()).select_from(
                select(AlertaGeo).where(AlertaGeo.activa.is_(True)).subquery()
            )
        ).scalar_one()

        return {
            "porcentaje_area_riesgo": round(pct_risk, 2),
            "canales_criticos": 0,  # Computed in service layer
            "caminos_vulnerables": 0,  # Computed in service layer
            "conflictos_activos": conflictos,
            "alertas_activas": alertas,
            "zonas_por_nivel": zonas_por_nivel,
            "evolucion_temporal": [],  # Computed in service layer
        }

    # ── MATERIALIZED VIEWS ─────────────────────────

    def refresh_materialized_views(self, db: Session) -> dict[str, str]:
        """Refresh all 3 geo materialized views concurrently.

        Requires the unique indexes to exist (created by migration).
        Returns a dict with view names and their refresh status.
        """
        views = [
            "mv_dashboard_geo_stats",
            "mv_hci_por_zona",
            "mv_alertas_resumen",
        ]
        results: dict[str, str] = {}
        for view in views:
            try:
                db.execute(
                    text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                )
                results[view] = "ok"
            except Exception:
                # If the view has no data yet, CONCURRENTLY fails — fallback
                db.rollback()
                try:
                    db.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
                    results[view] = "ok (non-concurrent)"
                except Exception as inner_exc:
                    results[view] = f"error: {inner_exc!s}"
        db.commit()
        return results

    def get_dashboard_stats(self, db: Session) -> dict[str, Any]:
        """Read pre-computed dashboard KPIs from mv_dashboard_geo_stats."""
        row = db.execute(
            text("SELECT * FROM mv_dashboard_geo_stats LIMIT 1")
        ).mappings().first()

        if row is None:
            return {}
        return dict(row)

    def get_hci_por_zona(
        self,
        db: Session,
        *,
        page: int = 1,
        limit: int = 50,
        cuenca_filter: Optional[str] = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Read latest HCI per zone from mv_hci_por_zona (paginated)."""
        where_clause = ""
        params: dict[str, Any] = {}
        if cuenca_filter:
            where_clause = "WHERE cuenca = :cuenca"
            params["cuenca"] = cuenca_filter

        # Total count
        count_sql = f"SELECT COUNT(*) FROM mv_hci_por_zona {where_clause}"
        total: int = db.execute(text(count_sql), params).scalar_one()

        # Paginated data
        offset = (page - 1) * limit
        data_sql = (
            f"SELECT zona_id, zona_nombre, cuenca, superficie_ha, "
            f"indice_final, nivel_riesgo, fecha_calculo "
            f"FROM mv_hci_por_zona {where_clause} "
            f"ORDER BY indice_final DESC "
            f"OFFSET :offset LIMIT :limit"
        )
        params["offset"] = offset
        params["limit"] = limit

        rows = db.execute(text(data_sql), params).mappings().all()
        return [dict(r) for r in rows], total

    def get_alertas_resumen(self, db: Session) -> dict[str, Any]:
        """Read active alerts summary from mv_alertas_resumen."""
        row = db.execute(
            text("SELECT * FROM mv_alertas_resumen LIMIT 1")
        ).mappings().first()

        if row is None:
            return {}
        return dict(row)

    # ── COMPOSITE ZONAL STATS ────────────────────

    def bulk_upsert_composite_stats(
        self, db: Session, stats: list[dict[str, Any]]
    ) -> int:
        """Insert or update composite zonal stats on conflict (zona_id + tipo).

        If a record with the same zona_id + tipo already exists, it is updated
        with the new values. Otherwise a new record is inserted.

        Args:
            db: Database session.
            stats: List of dicts with keys matching CompositeZonalStats columns.

        Returns:
            Number of rows upserted.
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not stats:
            return 0

        stmt = pg_insert(CompositeZonalStats).values(stats)
        stmt = stmt.on_conflict_do_update(
            index_elements=["zona_id", "tipo"],
            set_={
                "fecha_calculo": stmt.excluded.fecha_calculo,
                "mean_score": stmt.excluded.mean_score,
                "max_score": stmt.excluded.max_score,
                "p90_score": stmt.excluded.p90_score,
                "area_high_risk_ha": stmt.excluded.area_high_risk_ha,
                "weights_used": stmt.excluded.weights_used,
                "updated_at": func.now(),
            },
        )
        result = db.execute(stmt)
        db.flush()
        return result.rowcount

    def get_composite_stats_by_area(
        self,
        db: Session,
        area_id: str,
        tipo: Optional[str] = None,
    ) -> list[CompositeZonalStats]:
        """Query composite zonal stats for zones in an area.

        Joins with ZonaOperativa to filter by cuenca (used as area identifier)
        and optionally filters by composite tipo (flood_risk / drainage_need).
        Results are ordered by mean_score DESC (highest risk first).

        Args:
            db: Database session.
            area_id: Area identifier — matches ZonaOperativa.nombre pattern
                ``basin_{area_id}_%`` or ZonaOperativa.cuenca.
            tipo: Optional filter: "flood_risk" or "drainage_need".

        Returns:
            List of CompositeZonalStats with zona relationship loaded.
        """
        stmt = (
            select(CompositeZonalStats)
            .join(ZonaOperativa, CompositeZonalStats.zona_id == ZonaOperativa.id)
            .options(joinedload(CompositeZonalStats.zona))
            .where(
                ZonaOperativa.nombre.like(f"basin_{area_id}_%")
                | (ZonaOperativa.cuenca == area_id)
            )
        )

        if tipo:
            stmt = stmt.where(CompositeZonalStats.tipo == tipo)

        stmt = stmt.order_by(CompositeZonalStats.mean_score.desc())
        items = list(db.execute(stmt).scalars().unique().all())
        if items:
            return items

        # Fallback for the current app setup: composite stats are computed for the
        # single active analysis area (`zona_principal`) but the subcuencas keep
        # their original `cuenca` values (sub_candil_*, sub_ml_*, etc.), so the
        # area_id does not match ZonaOperativa.cuenca. In that case return the
        # full ranked list instead of failing with 404.
        if area_id == "zona_principal":
            fallback_stmt = (
                select(CompositeZonalStats)
                .join(ZonaOperativa, CompositeZonalStats.zona_id == ZonaOperativa.id)
                .options(joinedload(CompositeZonalStats.zona))
            )
            if tipo:
                fallback_stmt = fallback_stmt.where(CompositeZonalStats.tipo == tipo)
            fallback_stmt = fallback_stmt.order_by(CompositeZonalStats.mean_score.desc())
            return list(db.execute(fallback_stmt).scalars().unique().all())

        return items

    # ── CANAL SUGGESTIONS ────────────────────────

    def insert_suggestions_batch(
        self,
        db: Session,
        suggestions: list[dict[str, Any]],
    ) -> int:
        """Bulk insert canal suggestions from an analysis run.

        Args:
            db: Database session.
            suggestions: List of dicts with keys matching CanalSuggestion columns.

        Returns:
            Number of rows inserted.
        """
        if not suggestions:
            return 0
        objects = [CanalSuggestion(**s) for s in suggestions]
        db.add_all(objects)
        db.flush()
        return len(objects)

    def get_suggestions_by_tipo(
        self,
        db: Session,
        tipo: str,
        *,
        page: int = 1,
        limit: int = 50,
        batch_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[CanalSuggestion], int]:
        """Get canal suggestions filtered by tipo, ordered by score DESC.

        Args:
            db: Database session.
            tipo: Suggestion type (hotspot/gap/route/maintenance/bottleneck).
            page: Page number (1-based).
            limit: Page size.
            batch_id: Optional filter by analysis batch.

        Returns:
            Tuple of (items, total_count).
        """
        base = select(CanalSuggestion).where(CanalSuggestion.tipo == tipo)
        if batch_id:
            base = base.where(CanalSuggestion.batch_id == batch_id)

        total: int = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one()

        offset = (page - 1) * limit
        items = list(
            db.execute(
                base.order_by(CanalSuggestion.score.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total

    def get_latest_batch(self, db: Session) -> Optional[uuid.UUID]:
        """Return the batch_id of the most recent analysis run.

        Returns:
            The latest batch_id or None if no suggestions exist.
        """
        stmt = (
            select(CanalSuggestion.batch_id)
            .order_by(CanalSuggestion.created_at.desc())
            .limit(1)
        )
        return db.execute(stmt).scalar_one_or_none()

    def get_summary(
        self,
        db: Session,
        batch_id: Optional[uuid.UUID] = None,
    ) -> Optional[dict[str, Any]]:
        """Get aggregated summary for a batch (or the latest batch).

        Args:
            db: Database session.
            batch_id: Specific batch to summarize. If None, uses latest.

        Returns:
            Dict with batch_id, total_suggestions, by_tipo, avg_score,
            created_at — or None if no data.
        """
        if batch_id is None:
            batch_id = self.get_latest_batch(db)
        if batch_id is None:
            return None

        # Total and average score
        agg_stmt = select(
            func.count().label("total"),
            func.avg(CanalSuggestion.score).label("avg_score"),
            func.min(CanalSuggestion.created_at).label("created_at"),
        ).where(CanalSuggestion.batch_id == batch_id)

        agg = db.execute(agg_stmt).one()
        if agg.total == 0:
            return None

        # Count by tipo
        tipo_counts = db.execute(
            select(CanalSuggestion.tipo, func.count().label("cnt"))
            .where(CanalSuggestion.batch_id == batch_id)
            .group_by(CanalSuggestion.tipo)
        ).all()

        by_tipo = {row.tipo: row.cnt for row in tipo_counts}

        return {
            "batch_id": batch_id,
            "total_suggestions": agg.total,
            "by_tipo": by_tipo,
            "avg_score": round(float(agg.avg_score), 2),
            "created_at": agg.created_at,
        }


# ── Catastro / Afectados ──────────────────────────────────────────────────────


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


def bulk_upsert_parcelas(
    db: Session, features: list[dict]
) -> tuple[int, int]:
    """Upsert IDECOR parcelas from a GeoJSON FeatureCollection features list.

    Returns (imported, skipped) counts.
    Superficie_Tierra_Rural in IDECOR is in m² — convert to ha.
    """
    imported = 0
    skipped = 0
    for feature in features:
        props = feature.get("properties") or {}
        nomenclatura = props.get("Nomenclatura")
        geometry = feature.get("geometry")
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


_AFECTADOS_BY_ZONA_SQL = text("""
    SELECT
        c.id            AS consorcista_id,
        c.nombre        AS nombre,
        c.parcela       AS parcela,
        pc.superficie_ha AS hectareas,
        pc.nomenclatura  AS nomenclatura,
        zo.nombre        AS zona_nombre,
        zo.id::text      AS zona_id
    FROM consorcistas c
    JOIN parcelas_catastro pc ON pc.nomenclatura = c.parcela
    JOIN zonas_operativas  zo ON ST_Intersects(pc.geometria, zo.geometria)
    WHERE zo.id = :zona_id::uuid
    ORDER BY c.nombre
""")


def get_afectados_by_zona(db: Session, zona_id: str) -> dict | None:
    """Return consorcistas whose parcela intersects the given zona."""
    rows = db.execute(_AFECTADOS_BY_ZONA_SQL, {"zona_id": zona_id}).mappings().all()

    # Verify the zona actually exists even when no consorcistas match
    zona_row = db.execute(
        text("SELECT id, nombre FROM zonas_operativas WHERE id = :id::uuid"),
        {"id": zona_id},
    ).mappings().first()
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
    """Return afectados grouped by flooded zone for a given flood event."""
    event_row = db.execute(
        text("SELECT id, event_date FROM flood_events WHERE id = :id::uuid"),
        {"id": event_id},
    ).mappings().first()
    if event_row is None:
        return None

    flooded_zones = db.execute(
        text("""
            SELECT zo.id::text AS zona_id
            FROM flood_labels fl
            JOIN zonas_operativas zo ON zo.id = fl.zona_id
            WHERE fl.event_id = :event_id::uuid AND fl.is_flooded = true
        """),
        {"event_id": event_id},
    ).mappings().all()

    zonas_afectadas = []
    for row in flooded_zones:
        zona_data = get_afectados_by_zona(db, row["zona_id"])
        if zona_data:
            zonas_afectadas.append(zona_data)

    all_consorcista_ids = {
        a["consorcista_id"]
        for z in zonas_afectadas
        for a in z["afectados"]
    }
    total_ha = sum(z["total_ha"] for z in zonas_afectadas)

    return {
        "event_id": event_id,
        "event_date": str(event_row["event_date"]),
        "total_consorcistas": len(all_consorcista_ids),
        "total_ha": round(total_ha, 2),
        "zonas_afectadas": zonas_afectadas,
    }
