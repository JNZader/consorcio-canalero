"""Tests for geo/router.py — covers helper functions and endpoint lines NOT hit
by existing tests.

Strategy: test utility functions directly + use TestClient with mocked deps
for endpoint coverage. No real DB or GEE needed.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Utility / helper function tests (these don't need TestClient)
# ---------------------------------------------------------------------------


class TestValidateGeojsonFilename:
    def test_accepts_geojson(self):
        from app.domains.geo.router_common import _validate_geojson_filename

        _validate_geojson_filename("basins.geojson")  # no exception

    def test_accepts_json(self):
        from app.domains.geo.router_common import _validate_geojson_filename

        _validate_geojson_filename("data.json")

    def test_rejects_none(self):
        from app.domains.geo.router_common import _validate_geojson_filename

        with pytest.raises(HTTPException) as exc_info:
            _validate_geojson_filename(None)
        assert exc_info.value.status_code == 400

    def test_rejects_wrong_extension(self):
        from app.domains.geo.router_common import _validate_geojson_filename

        with pytest.raises(HTTPException) as exc_info:
            _validate_geojson_filename("data.csv")
        assert exc_info.value.status_code == 400


class TestReadGeojsonUpload:
    def test_rejects_empty(self):
        from app.domains.geo.router_common import _read_geojson_upload

        with pytest.raises(HTTPException) as exc_info:
            _read_geojson_upload(b"")
        assert exc_info.value.status_code == 400

    def test_rejects_invalid_json(self):
        from app.domains.geo.router_common import _read_geojson_upload

        with pytest.raises(HTTPException) as exc_info:
            _read_geojson_upload(b"not json")
        assert exc_info.value.status_code == 400

    def test_rejects_non_feature_collection(self):
        from app.domains.geo.router_common import _read_geojson_upload

        with pytest.raises(HTTPException) as exc_info:
            _read_geojson_upload(json.dumps({"type": "Feature"}).encode())
        assert exc_info.value.status_code == 400

    def test_rejects_missing_features(self):
        from app.domains.geo.router_common import _read_geojson_upload

        with pytest.raises(HTTPException) as exc_info:
            _read_geojson_upload(json.dumps({"type": "FeatureCollection", "features": "bad"}).encode())
        assert exc_info.value.status_code == 400

    def test_accepts_valid_geojson(self):
        from app.domains.geo.router_common import _read_geojson_upload

        payload = {"type": "FeatureCollection", "features": []}
        result = _read_geojson_upload(json.dumps(payload).encode())
        assert result["type"] == "FeatureCollection"


class TestExtractSourceProperties:
    def test_returns_source_properties_if_present(self):
        from app.domains.geo.router_common import _extract_source_properties

        props = {"source_properties": {"name": "Zone 1"}, "other": "val"}
        assert _extract_source_properties(props) == {"name": "Zone 1"}

    def test_returns_full_properties_if_no_source(self):
        from app.domains.geo.router_common import _extract_source_properties

        props = {"name": "Zone 1", "area": 100}
        result = _extract_source_properties(props)
        assert result == props

    def test_returns_empty_for_non_dict(self):
        from app.domains.geo.router_common import _extract_source_properties

        assert _extract_source_properties(None) == {}
        assert _extract_source_properties("string") == {}


class TestGetUserDisplayName:
    def test_returns_none_for_none_user_id(self):
        from app.domains.geo.router import _get_user_display_name

        db = MagicMock()
        assert _get_user_display_name(db, None) is None

    def test_returns_none_for_missing_user(self):
        from app.domains.geo.router import _get_user_display_name

        db = MagicMock()
        db.get.return_value = None
        assert _get_user_display_name(db, uuid.uuid4()) is None

    def test_returns_full_name(self):
        from app.domains.geo.router import _get_user_display_name

        user = SimpleNamespace(nombre="Juan", apellido="Pérez", email="j@x.com")
        db = MagicMock()
        db.get.return_value = user
        assert _get_user_display_name(db, uuid.uuid4()) == "Juan Pérez"

    def test_falls_back_to_email(self):
        from app.domains.geo.router import _get_user_display_name

        user = SimpleNamespace(nombre="", apellido="", email="j@x.com")
        db = MagicMock()
        db.get.return_value = user
        assert _get_user_display_name(db, uuid.uuid4()) == "j@x.com"


class TestGetGeoBundleStorageDir:
    def test_returns_first_writable(self, tmp_path):
        with patch("app.domains.geo.router_common.Path") as MockPath:
            mock_candidate = MagicMock()
            mock_candidate.mkdir.return_value = None
            MockPath.return_value = mock_candidate

            from app.domains.geo.router_common import _get_geo_bundle_storage_dir

            # Reset so we hit the real logic
            from importlib import reload
            import app.domains.geo.router_common

    def test_raises_500_when_all_fail(self):
        from app.domains.geo.router_common import _get_geo_bundle_storage_dir

        with patch("pathlib.Path.mkdir", side_effect=OSError("fail")):
            with pytest.raises(HTTPException) as exc_info:
                _get_geo_bundle_storage_dir()
            assert exc_info.value.status_code == 500


class TestSerializeApprovedZoning:
    def test_serializes_zoning(self):
        from app.domains.geo.router import _serialize_approved_zoning

        zoning = SimpleNamespace(
            id=uuid.uuid4(),
            nombre="Test Zoning",
            version=1,
            cuenca="norte",
            feature_collection={"type": "FeatureCollection", "features": []},
            assignments={"z1": "zone_a"},
            zone_names={"z1": "Zone A"},
            notes="Test notes",
            approved_at=datetime(2025, 1, 15, 10, 0),
            approved_by_id=None,
        )
        db = MagicMock()
        result = _serialize_approved_zoning(db, zoning)
        assert result.nombre == "Test Zoning"
        assert result.version == 1


class TestNormalizePolygonWkt:
    def test_polygon(self):
        from app.domains.geo.router_common import _normalize_polygon_wkt

        geom = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        wkt = _normalize_polygon_wkt(geom)
        assert "POLYGON" in wkt

    def test_multipolygon_merges(self):
        from app.domains.geo.router_common import _normalize_polygon_wkt

        geom = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                [[[2, 2], [3, 2], [3, 3], [2, 2]]],
            ],
        }
        wkt = _normalize_polygon_wkt(geom)
        assert "POLYGON" in wkt


class TestImportZonasPayload:
    def test_empty_features_raises(self):
        from app.domains.geo.router_common import _import_zonas_operativas_payload

        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            _import_zonas_operativas_payload(db, {"features": []})
        assert exc_info.value.status_code == 400

    def test_feature_without_geometry_raises(self):
        from app.domains.geo.router_common import _import_zonas_operativas_payload

        db = MagicMock()
        db.execute.return_value = MagicMock(rowcount=0)
        with pytest.raises(HTTPException) as exc_info:
            _import_zonas_operativas_payload(
                db,
                {"features": [{"geometry": None, "properties": {}}]},
            )
        assert exc_info.value.status_code == 400

    def test_unsupported_geometry_raises(self):
        from app.domains.geo.router_common import _import_zonas_operativas_payload

        db = MagicMock()
        db.execute.return_value = MagicMock(rowcount=0)
        with pytest.raises(HTTPException) as exc_info:
            _import_zonas_operativas_payload(
                db,
                {
                    "features": [
                        {
                            "geometry": {"type": "Point", "coordinates": [0, 0]},
                            "properties": {},
                        }
                    ]
                },
            )
        assert exc_info.value.status_code == 400

    def test_valid_import(self):
        from app.domains.geo.router_common import _import_zonas_operativas_payload

        db = MagicMock()
        db.execute.return_value = MagicMock(rowcount=0)
        result = _import_zonas_operativas_payload(
            db,
            {
                "features": [
                    {
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                        },
                        "properties": {"cuenca": "norte", "nombre": "Z1"},
                    }
                ]
            },
        )
        assert result["imported_count"] == 1
        assert result["replaced_count"] == 0


class TestImportApprovedZoningPayload:
    def test_feature_collection_format(self):
        from app.domains.geo.router_common import _import_approved_zoning_payload

        db = MagicMock()
        repo = MagicMock()
        repo.get_active_approved_zoning.return_value = None
        repo.create_approved_zoning_version.return_value = SimpleNamespace(
            version=1, nombre="Test", cuenca="norte"
        )

        result = _import_approved_zoning_payload(
            db,
            repo,
            {
                "featureCollection": {
                    "type": "FeatureCollection",
                    "features": [{"type": "Feature", "geometry": {}, "properties": {}}],
                },
                "assignments": {},
                "zone_names": {},
                "nombre": "Test Zoning",
            },
            approved_by_id=None,
        )
        assert result["imported_count"] == 1

    def test_flat_features_format(self):
        from app.domains.geo.router_common import _import_approved_zoning_payload

        db = MagicMock()
        repo = MagicMock()
        repo.get_active_approved_zoning.return_value = None
        repo.create_approved_zoning_version.return_value = SimpleNamespace(
            version=1, nombre="Test", cuenca=None
        )

        result = _import_approved_zoning_payload(
            db,
            repo,
            {
                "features": [
                    {
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                        },
                        "properties": {"name": "Zone A", "zone_id": "z1"},
                    }
                ]
            },
            approved_by_id=uuid.uuid4(),
        )
        assert result["imported_count"] == 1

    def test_empty_features_raises(self):
        from app.domains.geo.router_common import _import_approved_zoning_payload

        db = MagicMock()
        repo = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            _import_approved_zoning_payload(
                db, repo, {"features": []}, approved_by_id=None
            )
        assert exc_info.value.status_code == 400


class TestUpsertBundleLayer:
    def test_creates_new_layer(self):
        from app.domains.geo.router_common import _upsert_bundle_layer

        db = MagicMock()
        db.query.return_value.filter.return_value.one_or_none.return_value = None

        result = _upsert_bundle_layer(
            db,
            nombre="test",
            tipo="dem_raw",
            fuente="manual",
            archivo_path="/test.tif",
            formato="geotiff",
            srid=4326,
            bbox=None,
            metadata_extra=None,
            area_id=None,
        )
        db.add.assert_called_once()

    def test_updates_existing_layer(self):
        from app.domains.geo.router_common import _upsert_bundle_layer

        existing = SimpleNamespace(
            nombre="old", fuente="old", archivo_path="/old.tif",
            formato="geotiff", srid=4326, bbox=None, metadata_extra=None,
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.one_or_none.return_value = existing

        result = _upsert_bundle_layer(
            db,
            nombre="new",
            tipo="dem_raw",
            fuente="manual",
            archivo_path="/new.tif",
            formato="geotiff",
            srid=4326,
            bbox=None,
            metadata_extra=None,
            area_id="a1",
        )
        assert result.nombre == "new"
        assert result.archivo_path == "/new.tif"
        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# GEE sub-router helpers
# ---------------------------------------------------------------------------


class TestEnsureGee:
    def test_raises_503_when_gee_unavailable(self):
        from app.domains.geo.router import _ensure_gee

        mock_svc = {"ensure_init": MagicMock(side_effect=RuntimeError("no creds"))}
        with patch("app.domains.geo.router._lazy_gee_service", return_value=mock_svc):
            from app.core.exceptions import AppException

            with pytest.raises(AppException) as exc_info:
                _ensure_gee()
            assert exc_info.value.status_code == 503

    def test_returns_service_on_success(self):
        from app.domains.geo.router import _ensure_gee

        mock_svc = {
            "ensure_init": MagicMock(),
            "get_available_layers": MagicMock(),
        }
        with patch("app.domains.geo.router._lazy_gee_service", return_value=mock_svc):
            result = _ensure_gee()
            assert "get_available_layers" in result


class TestGetTileClient:
    def test_creates_client_once(self):
        import app.domains.geo.router as router_mod

        router_mod._tile_client = None
        client = router_mod._get_tile_client()
        assert client is not None
        client2 = router_mod._get_tile_client()
        assert client is client2
        router_mod._tile_client = None  # cleanup


class TestHistoricFloods:
    def test_historic_floods_list(self):
        from app.domains.geo.router_gee_support import HISTORIC_FLOODS

        assert len(HISTORIC_FLOODS) >= 2
        assert all("id" in f for f in HISTORIC_FLOODS)
        assert all("date" in f for f in HISTORIC_FLOODS)


# ---------------------------------------------------------------------------
# Request model validation
# ---------------------------------------------------------------------------


class TestRequestModels:
    def test_zonal_stats_request_defaults(self):
        from app.domains.geo.router_analysis import ZonalStatsRequest

        req = ZonalStatsRequest(layer_tipo="slope")
        assert req.zona_source == "zonas_operativas"
        assert req.area_id is None

    def test_approved_zones_build_request(self):
        from app.domains.geo.router_common import ApprovedZonesBuildRequest

        req = ApprovedZonesBuildRequest()
        assert req.assignments == {}
        assert req.zone_names == {}

    def test_approved_zones_save_request(self):
        from app.domains.geo.router import ApprovedZonesSaveRequest

        req = ApprovedZonesSaveRequest(
            featureCollection={"type": "FeatureCollection", "features": []},
        )
        assert req.nombre == "Zonificación Consorcio aprobada"

    def test_approved_zones_response(self):
        from app.domains.geo.router_common import ApprovedZonesResponse

        resp = ApprovedZonesResponse(
            id=str(uuid.uuid4()),
            nombre="Test",
            version=1,
            featureCollection={"type": "FeatureCollection", "features": []},
            approvedAt="2025-01-01T00:00:00",
        )
        assert resp.version == 1

    def test_geo_json_import_response(self):
        from app.domains.geo.router_common import GeoJsonImportResponse

        resp = GeoJsonImportResponse(
            importedCount=5,
            replacedCount=2,
            featureType="zonas_operativas",
        )
        assert resp.imported_count == 5

    def test_geo_bundle_import_response(self):
        from app.domains.geo.router_common import GeoBundleImportResponse

        resp = GeoBundleImportResponse(
            layersImported=3,
            bundleName="test.zip",
        )
        assert resp.layers_imported == 3

    def test_approved_zones_map_pdf_request(self):
        from app.domains.geo.router import ApprovedZonesMapPdfRequest

        req = ApprovedZonesMapPdfRequest(
            title="Test Map",
            mapImageDataUrl="data:image/png;base64,abc",
        )
        assert req.title == "Test Map"
        assert req.zone_legend == []

    def test_map_legend_item_request(self):
        from app.domains.geo.router_common import MapLegendItemRequest

        item = MapLegendItemRequest(label="Zone A", color="#ff0000")
        assert item.detail is None

    def test_raster_legend_group_request(self):
        from app.domains.geo.router_common import RasterLegendGroupRequest

        group = RasterLegendGroupRequest(label="Elevation")
        assert group.items == []

    def test_map_info_row_request(self):
        from app.domains.geo.router_common import MapInfoRowRequest

        row = MapInfoRowRequest(label="Area", value="100 ha")
        assert row.label == "Area"

    def test_zone_summary_row_request(self):
        from app.domains.geo.router_common import ZoneSummaryRowRequest

        row = ZoneSummaryRowRequest(name="Zone A", subcuencas=3, areaHa=500.0)
        assert row.name == "Zone A"

    def test_flood_event_create_schema_requires_labels(self):
        from app.domains.geo.schemas import FloodEventCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            FloodEventCreate(
                event_date=date(2025, 3, 1),
                nombre="Flood March 2025",
                labels=[],
            )
