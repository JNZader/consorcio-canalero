from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.services.infrastructure_service import InfrastructureService


def _service_with_db(db):
    service = InfrastructureService.__new__(InfrastructureService)
    service.db = db
    return service


def test_get_gee_service_or_raise_returns_service_when_available(monkeypatch):
    service = _service_with_db(MagicMock())
    gee = MagicMock()

    monkeypatch.setattr("app.services.infrastructure_service._gee_initialized", True)
    monkeypatch.setattr(
        "app.services.infrastructure_service.get_gee_service", lambda: gee
    )

    assert service._get_gee_service_or_raise() is gee


def test_get_gee_service_or_raise_raises_app_exception_on_failure(monkeypatch):
    service = _service_with_db(MagicMock())

    monkeypatch.setattr("app.services.infrastructure_service._gee_initialized", False)
    monkeypatch.setattr(
        "app.services.infrastructure_service.initialize_gee",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(AppException) as exc:
        service._get_gee_service_or_raise()

    assert exc.value.code == "GEE_UNAVAILABLE"


def test_get_potential_intersections_returns_empty_when_canales_empty(monkeypatch):
    service = _service_with_db(MagicMock())
    gee = MagicMock()
    gee.caminos = MagicMock()
    gee.canales = MagicMock()
    gee.canales.size.return_value.getInfo.return_value = 0

    monkeypatch.setattr(service, "_get_gee_service_or_raise", lambda: gee)

    result = service.get_potential_intersections()

    assert result == {"type": "FeatureCollection", "features": []}


def test_get_potential_intersections_returns_geojson(monkeypatch):
    service = _service_with_db(MagicMock())
    roads = MagicMock()
    intersections = MagicMock()
    points = MagicMock()
    points.getInfo.return_value = {"type": "FeatureCollection", "features": [{"id": 1}]}
    intersections.filter.return_value = points
    roads.map.return_value = intersections

    canals = MagicMock()
    canals.size.return_value.getInfo.return_value = 3
    canals.geometry.return_value = "geom"

    gee = MagicMock(caminos=roads, canales=canals)
    monkeypatch.setattr(service, "_get_gee_service_or_raise", lambda: gee)
    monkeypatch.setattr(
        "app.services.infrastructure_service.ee.Filter",
        MagicMock(isNotNull=lambda _field: "not-null-filter"),
    )

    result = service.get_potential_intersections()

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 1


def test_get_all_assets_applies_optional_cuenca_filter():
    query = MagicMock()
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value.data = [{"id": "a1"}]

    db = MagicMock()
    db.client.table.return_value = query
    service = _service_with_db(db)

    assert service.get_all_assets() == [{"id": "a1"}]
    assert service.get_all_assets(cuenca="norte") == [{"id": "a1"}]
    query.eq.assert_called_with("cuenca", "norte")


def test_add_maintenance_log_updates_asset_when_insert_succeeds():
    log_query = MagicMock()
    log_query.insert.return_value = log_query
    log_query.execute.return_value.data = [{"id": "log-1"}]

    infra_query = MagicMock()
    infra_query.update.return_value = infra_query
    infra_query.eq.return_value = infra_query
    infra_query.execute.return_value.data = [{"id": "asset-1"}]

    db = MagicMock()
    db.client.table.side_effect = [log_query, infra_query]
    service = _service_with_db(db)

    asset_id = str(uuid4())
    result = service.add_maintenance_log(
        {"infraestructura_id": asset_id, "nuevo_estado": "regular"}
    )

    assert result == {"id": "log-1"}
    infra_query.eq.assert_called_once_with("id", asset_id)
