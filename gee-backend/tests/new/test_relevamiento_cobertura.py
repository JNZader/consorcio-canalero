"""``GET /api/v2/geo/relevamiento/cobertura`` — three counters, never one total.

RSS-R4: a candidate is never authoritative and never counts as surveyed. The
response therefore carries ``relevados``, ``solo_candidato`` and ``sin_datos`` as
three separate fields, and no field anywhere sums them into "surveyed".

All four figures — the three counters and ``total_activos`` — are computed over
``red_vial`` rows with ``activo = true`` only (design D4). A retired segment keeps
its survey history but leaves the working set: counting it as ``sin_datos`` would
permanently depress coverage against a road that no longer exists in the source,
and counting it as ``relevados`` would inflate coverage of the network that does.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("UPLOADS_ROOT", "/tmp/uploads-test-cobertura")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-at-least-32-characters-long")

ENDPOINT = "/api/v2/geo/relevamiento/cobertura"
AREA = "zona_cobertura"

#: The area's DEM footprint — and the ONLY footprint the filter uses (owner
#: ratification A, 2026-08-23).
DEM_BBOX = [-62.2, -32.6, -61.9, -32.4]

#: A second layer for the same area, registered over much wider ground. Under
#: the old union rule its bbox widened the area; under the DEM-footprint rule it
#: is irrelevant, and ``cob-fuera-del-dem`` below is what proves which rule ran.
OTRA_CAPA_BBOX = [-63.5, -33.5, -61.0, -32.0]

#: Inside the seeded area footprint.
TRAMOS = {
    "cob-relevado": -62.00,
    "cob-candidato": -62.01,
    "cob-vacio": -62.02,
    "cob-retirado": -62.03,
}

#: Outside the DEM footprint, inside ``OTRA_CAPA_BBOX``. Active and surveyed, so
#: it would land in ``relevados`` and in ``total_activos`` the moment the filter
#: widened past the DEM.
TRAMO_FUERA_DEL_DEM = "cob-fuera-del-dem"
LON_FUERA_DEL_DEM = -63.20


@pytest.fixture
def app_client(db_session_factory):
    from app.db.session import get_db
    from app.main import app

    def _get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    client = TestClient(app)
    client.headers.update({"Host": "localhost"})
    yield app, client
    app.dependency_overrides.clear()


def _as_operator(app) -> None:
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole
    from types import SimpleNamespace

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
        role=UserRole("operador")
    )


@pytest.fixture
def seeded(db_session_factory):
    """One segment of each coverage state, plus a retired one that was surveyed."""
    from app.auth.models import User, UserRole
    from app.domains.geo.models import (
        EstadoGeoJob,
        FormatoGeoLayer,
        FuenteGeoLayer,
        GeoJob,
        GeoLayer,
        TipoGeoJob,
        TipoGeoLayer,
    )
    from app.domains.geo.relevamiento.repository import RelevamientoRepository

    session = db_session_factory()
    try:
        user = User(
            email=f"operator-cobertura-{uuid.uuid4().hex[:8]}@test.com",
            hashed_password="fakehash",
            nombre="Operador",
            apellido="Cobertura",
            role=UserRole.OPERADOR,
        )
        session.add(user)
        session.add(
            GeoLayer(
                nombre=f"dem_raw_{AREA}",
                tipo=TipoGeoLayer.DEM_RAW,
                fuente=FuenteGeoLayer.GEE,
                archivo_path=f"/data/geo/{AREA}/output/dem_raw.tif",
                formato=FormatoGeoLayer.GEOTIFF,
                srid=4326,
                bbox=DEM_BBOX,
                area_id=AREA,
            )
        )
        session.add(
            GeoLayer(
                nombre=f"flow_acc_{AREA}",
                tipo=TipoGeoLayer.FLOW_ACC,
                fuente=FuenteGeoLayer.DEM_PIPELINE,
                archivo_path=f"/data/geo/{AREA}/output/flow_acc.tif",
                formato=FormatoGeoLayer.GEOTIFF,
                srid=4326,
                bbox=OTRA_CAPA_BBOX,
                area_id=AREA,
            )
        )
        job = GeoJob(
            tipo=TipoGeoJob.TRAMO_CLASSIFICATION,
            estado=EstadoGeoJob.COMPLETED,
            parametros={"area_id": AREA},
            progreso=100,
        )
        session.add(job)
        session.flush()

        for tramo, lon in TRAMOS.items():
            session.execute(
                text(
                    "INSERT INTO red_vial (id, source_id, geom, geom_hash, activo) VALUES "
                    "(:id, :id, ST_GeomFromText(:wkt, 4326), :h, :activo)"
                ),
                {
                    "id": tramo,
                    "wkt": f"LINESTRING({lon} -32.50, {lon - 0.005} -32.51)",
                    "h": f"hash-{tramo}",
                    "activo": tramo != "cob-retirado",
                },
            )

        session.execute(
            text(
                "INSERT INTO red_vial (id, source_id, geom, geom_hash, activo) VALUES "
                "(:id, :id, ST_GeomFromText(:wkt, 4326), :h, true)"
            ),
            {
                "id": TRAMO_FUERA_DEL_DEM,
                "wkt": (
                    f"LINESTRING({LON_FUERA_DEL_DEM} -32.90, {LON_FUERA_DEL_DEM - 0.005} -32.91)"
                ),
                "h": f"hash-{TRAMO_FUERA_DEL_DEM}",
            },
        )

        repo = RelevamientoRepository()
        for tramo in ("cob-relevado", "cob-retirado", TRAMO_FUERA_DEL_DEM):
            repo.insertar(
                session,
                tramo_ref=tramo,
                nivel_relativo="mayor",
                tiene_cuneta="no",
                estado_cuneta=None,
                observaciones=None,
                relevado_por=user.id,
                nivel_desde_candidata=False,
            )
        repo.insertar_candidatas(
            session,
            filas=[
                {
                    "tramo_ref": "cob-candidato",
                    "clasificacion_candidata": "terraplen",
                    "confianza_m": 1.4,
                }
            ],
            geo_job_id=job.id,
            calculada_en=datetime.now(timezone.utc),
        )
        session.commit()
    finally:
        session.close()


class TestTheThreeCountersAreSeparate:
    def test_each_state_is_counted_once_in_its_own_field(self, app_client, seeded):
        app, client = app_client
        _as_operator(app)

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert body["relevados"] == 1
        assert body["solo_candidato"] == 1
        assert body["sin_datos"] == 1
        assert body["total_activos"] == 3

    def test_no_field_merges_the_candidate_into_the_surveyed_total(self, app_client, seeded):
        """RSS-R4 mechanically: there is no field that could hold the sum."""
        app, client = app_client
        _as_operator(app)

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        for clave in body:
            assert clave in {
                "area_id",
                "relevados",
                "solo_candidato",
                "sin_datos",
                "total_activos",
            }, f"unexpected coverage field {clave!r} — a merged total has no home here"

        assert body["relevados"] != body["relevados"] + body["solo_candidato"]

    def test_the_counters_partition_the_active_network(self, app_client, seeded):
        app, client = app_client
        _as_operator(app)

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert (
            body["relevados"] + body["solo_candidato"] + body["sin_datos"] == body["total_activos"]
        ), "every active segment falls in exactly one of the three states"


class TestARetiredSegmentLeavesTheWorkingSet:
    def test_a_retired_surveyed_segment_is_in_none_of_the_four_figures(self, app_client, seeded):
        app, client = app_client
        _as_operator(app)

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert body["total_activos"] == 3, "the retired segment is out of the denominator"
        assert body["relevados"] == 1, (
            "counting a retired segment as surveyed would inflate coverage of the "
            "network that actually exists"
        )

    def test_its_history_is_still_retrievable_by_tramo_ref(self, app_client, seeded):
        app, client = app_client
        _as_operator(app)

        detalle = client.get("/api/v2/geo/relevamiento/tramos/cob-retirado").json()

        assert detalle["vigente"] is not None
        assert detalle["vigente"]["es_vigente"] is True
        assert len(detalle["historial"]) == 1


class TestTheAreaFilter:
    def test_an_area_with_no_registered_footprint_is_a_named_refusal(self, app_client, seeded):
        """Answering a question about one area with a number about every area
        is a degradation nobody can see from the number itself."""
        app, client = app_client
        _as_operator(app)

        response = client.get(ENDPOINT, params={"area_id": "area_inexistente"})

        assert response.status_code == 404
        assert "area_inexistente" in response.text

    def test_the_area_is_echoed_back_with_the_counters(self, app_client, seeded):
        app, client = app_client
        _as_operator(app)

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert body["area_id"] == AREA


class TestTheFootprintIsTheDemAndOnlyTheDem:
    """Owner ratification A (2026-08-23): the DEM's bbox, never a union.

    The area a survey campaign covers is the ground its terrain analysis
    covers. A union over every layer that ever named the area makes the
    denominator depend on what else got registered — a wider GEE import, a
    hand-loaded raster — and it widens SILENTLY: nobody re-reads a coverage
    percentage and wonders which layers were in scope when it was computed.

    ``cob-fuera-del-dem`` is the discriminator. It is active and surveyed, and it
    sits inside ``OTRA_CAPA_BBOX`` but outside ``DEM_BBOX``, so a union filter
    would put it in ``relevados`` and in ``total_activos``.
    """

    def test_a_segment_outside_the_dem_is_in_none_of_the_three_counters(self, app_client, seeded):
        app, client = app_client
        _as_operator(app)

        body = client.get(ENDPOINT, params={"area_id": AREA}).json()

        assert body["total_activos"] == 3, (
            "the segment outside the DEM is out of the denominator; a union over "
            f"{OTRA_CAPA_BBOX} would have made this 4"
        )
        assert body["relevados"] == 1, (
            "it is surveyed, so a widened footprint would have shown up here as "
            "fieldwork credited to an area that never covered that ground"
        )
        assert body["solo_candidato"] == 1
        assert body["sin_datos"] == 1

    def test_it_is_the_dem_layers_bbox_that_is_read(self, db_session_factory, seeded):
        """Read directly, so the counters cannot mask which bbox won."""
        from app.domains.geo.relevamiento.repository import RelevamientoRepository

        session = db_session_factory()
        try:
            bbox = RelevamientoRepository().get_area_bbox(session, AREA)
        finally:
            session.close()

        assert bbox == tuple(DEM_BBOX), (
            "the union of the two seeded layers would be "
            f"{OTRA_CAPA_BBOX} — a footprint nobody chose"
        )

    def test_an_area_whose_only_layer_is_not_a_dem_is_the_named_refusal(
        self, app_client, db_session_factory, seeded
    ):
        """No DEM means no footprint — and no footprint is a 404, not the network.

        The 404 is kept exactly as it was: an area with layers but no terrain
        analysis has nothing to count coverage over, and answering it with the
        whole network's numbers under that area's label is the degradation this
        refusal exists to prevent.
        """
        from app.domains.geo.models import (
            FormatoGeoLayer,
            FuenteGeoLayer,
            GeoLayer,
            TipoGeoLayer,
        )

        app, client = app_client
        _as_operator(app)
        sin_dem = "zona_sin_dem"
        session = db_session_factory()
        try:
            session.add(
                GeoLayer(
                    nombre=f"basins_{sin_dem}",
                    tipo=TipoGeoLayer.BASINS,
                    fuente=FuenteGeoLayer.DEM_PIPELINE,
                    archivo_path=f"/data/geo/{sin_dem}/output/basins.geojson",
                    formato=FormatoGeoLayer.GEOJSON,
                    srid=4326,
                    bbox=OTRA_CAPA_BBOX,
                    area_id=sin_dem,
                )
            )
            session.commit()
        finally:
            session.close()

        response = client.get(ENDPOINT, params={"area_id": sin_dem})

        assert response.status_code == 404
        assert sin_dem in response.text
