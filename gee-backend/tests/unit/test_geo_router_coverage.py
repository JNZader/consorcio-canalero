"""Unit tests for geo/router.py — covering uncovered endpoints.

Targets: GEE sub-router endpoints, water detection, STAC, temporal analysis,
flood risk, hydrology, routing, bundle export/import, and approved zones PDF/restore.

Uses direct function calls with mocked dependencies.
"""

import io
import json
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    db.flush = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture()
def mock_repo():
    return MagicMock()


@pytest.fixture()
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.nombre = "Admin"
    user.apellido = "Test"
    user.email = "admin@test.com"
    return user


# ---------------------------------------------------------------------------
# GEE Router — Sentinel-2 Tiles
# ---------------------------------------------------------------------------


class TestGeeRouterSentinel2Tiles:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_sentinel2_tiles

        mock_service = MagicMock()
        mock_service.get_sentinel2_tiles.return_value = {
            "tile_url": "https://tiles/{z}/{x}/{y}",
            "imagenes_disponibles": 5,
        }
        mock_ensure.return_value = {"get_gee_service": lambda: mock_service}

        result = await get_sentinel2_tiles(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            max_cloud=40,
        )
        assert "tile_url" in result

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_not_found(self, mock_ensure):
        from app.domains.geo.router import get_sentinel2_tiles
        from app.core.exceptions import NotFoundError

        mock_service = MagicMock()
        mock_service.get_sentinel2_tiles.return_value = {
            "error": "No images found",
        }
        mock_ensure.return_value = {"get_gee_service": lambda: mock_service}

        with pytest.raises(NotFoundError):
            await get_sentinel2_tiles(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 31),
                max_cloud=40,
            )

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_gee_error(self, mock_ensure):
        from app.domains.geo.router import get_sentinel2_tiles
        from app.core.exceptions import AppException

        mock_service = MagicMock()
        mock_service.get_sentinel2_tiles.side_effect = Exception("GEE timeout")
        mock_ensure.return_value = {"get_gee_service": lambda: mock_service}

        with pytest.raises(AppException):
            await get_sentinel2_tiles(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 31),
                max_cloud=40,
            )


# ---------------------------------------------------------------------------
# GEE Router — Consorcios Camineros
# ---------------------------------------------------------------------------


class TestGeeRouterConsorcios:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_list_consorcios(self, mock_ensure):
        from app.domains.geo.router import list_consorcios_camineros

        mock_ensure.return_value = {
            "get_consorcios_camineros": lambda: [{"nombre": "C1"}],
        }

        result = await list_consorcios_camineros()
        body = json.loads(result.body)
        assert body["total"] == 1

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_list_consorcios_error(self, mock_ensure):
        from app.domains.geo.router import list_consorcios_camineros
        from app.core.exceptions import AppException

        def _raise():
            raise Exception("GEE error")

        mock_ensure.return_value = {"get_consorcios_camineros": _raise}

        with pytest.raises(AppException):
            await list_consorcios_camineros()


class TestGeeRouterCaminosConsorcio:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_caminos_consorcio

        mock_ensure.return_value = {
            "get_caminos_by_consorcio": lambda c: {"features": [{"id": 1}]},
        }

        result = await get_caminos_consorcio("CA")
        body = json.loads(result.body)
        assert len(body["features"]) == 1

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_not_found(self, mock_ensure):
        from app.domains.geo.router import get_caminos_consorcio
        from app.core.exceptions import NotFoundError

        mock_ensure.return_value = {
            "get_caminos_by_consorcio": lambda c: {"features": []},
        }

        with pytest.raises(NotFoundError):
            await get_caminos_consorcio("INVALID")

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_gee_error(self, mock_ensure):
        from app.domains.geo.router import get_caminos_consorcio
        from app.core.exceptions import AppException

        def _raise(c):
            raise Exception("GEE error")

        mock_ensure.return_value = {"get_caminos_by_consorcio": _raise}

        with pytest.raises(AppException):
            await get_caminos_consorcio("CA")


class TestGeeRouterCaminosPorNombre:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_caminos_por_nombre_consorcio

        mock_ensure.return_value = {
            "get_caminos_by_consorcio_nombre": lambda n: {"features": [{"id": 1}]},
        }

        result = await get_caminos_por_nombre_consorcio(nombre="Consorcio A")
        body = json.loads(result.body)
        assert len(body["features"]) == 1

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_not_found(self, mock_ensure):
        from app.domains.geo.router import get_caminos_por_nombre_consorcio
        from app.core.exceptions import NotFoundError

        mock_ensure.return_value = {
            "get_caminos_by_consorcio_nombre": lambda n: {"features": []},
        }

        with pytest.raises(NotFoundError):
            await get_caminos_por_nombre_consorcio(nombre="Invalid")

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_gee_error(self, mock_ensure):
        from app.domains.geo.router import get_caminos_por_nombre_consorcio
        from app.core.exceptions import AppException

        def _raise(n):
            raise Exception("GEE error")

        mock_ensure.return_value = {"get_caminos_by_consorcio_nombre": _raise}

        with pytest.raises(AppException):
            await get_caminos_por_nombre_consorcio(nombre="X")


class TestGeeRouterCaminosColoreados:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_caminos_coloreados

        mock_ensure.return_value = {
            "get_caminos_con_colores": lambda: {"type": "FeatureCollection", "features": []},
        }

        result = await get_caminos_coloreados()
        body = json.loads(result.body)
        assert body["type"] == "FeatureCollection"

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_error(self, mock_ensure):
        from app.domains.geo.router import get_caminos_coloreados
        from app.core.exceptions import AppException

        def _raise():
            raise Exception("GEE error")

        mock_ensure.return_value = {"get_caminos_con_colores": _raise}

        with pytest.raises(AppException):
            await get_caminos_coloreados()


class TestGeeRouterEstadisticas:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_estadisticas_caminos

        mock_ensure.return_value = {
            "get_estadisticas_consorcios": lambda: {"consorcios": [], "totales": {}},
        }

        result = await get_estadisticas_caminos()
        body = json.loads(result.body)
        assert "consorcios" in body

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_error(self, mock_ensure):
        from app.domains.geo.router import get_estadisticas_caminos
        from app.core.exceptions import AppException

        def _raise():
            raise Exception("GEE error")

        mock_ensure.return_value = {"get_estadisticas_consorcios": _raise}

        with pytest.raises(AppException):
            await get_estadisticas_caminos()


class TestGeeRouterGetLayer:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_gee_layer

        mock_ensure.return_value = {
            "get_layer_geojson": lambda name: {"type": "FeatureCollection", "features": []},
        }

        result = await get_gee_layer("zona")
        body = json.loads(result.body)
        assert body["type"] == "FeatureCollection"

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_not_found(self, mock_ensure):
        from app.domains.geo.router import get_gee_layer
        from app.core.exceptions import NotFoundError

        def _raise(name):
            raise ValueError("not found")

        mock_ensure.return_value = {"get_layer_geojson": _raise}

        with pytest.raises(NotFoundError):
            await get_gee_layer("invalid")

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_gee_error(self, mock_ensure):
        from app.domains.geo.router import get_gee_layer
        from app.core.exceptions import AppException

        def _raise(name):
            raise Exception("GEE error")

        mock_ensure.return_value = {"get_layer_geojson": _raise}

        with pytest.raises(AppException):
            await get_gee_layer("zona")


# ---------------------------------------------------------------------------
# GEE Images — Available dates, Sentinel-2, Sentinel-1, Compare
# ---------------------------------------------------------------------------


class TestGeeImageAvailableDates:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_available_image_dates

        mock_explorer = MagicMock()
        mock_explorer.get_available_dates.return_value = {
            "dates": ["2025-06-01"], "sensor": "sentinel2", "year": 2025, "month": 6, "total": 1,
        }
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        result = await get_available_image_dates(year=2025, month=6)
        body = json.loads(result.body)
        assert body["total"] == 1

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_error(self, mock_ensure):
        from app.domains.geo.router import get_available_image_dates
        from app.core.exceptions import AppException

        mock_explorer = MagicMock()
        mock_explorer.get_available_dates.side_effect = Exception("fail")
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(AppException):
            await get_available_image_dates(year=2025, month=6)


class TestGeeImageSentinel2:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_sentinel2_image

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel2_image.return_value = {
            "tile_url": "https://tiles/{z}/{x}/{y}",
            "sensor": "Sentinel-2",
        }
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        result = await get_sentinel2_image(target_date=date(2025, 6, 15))
        assert result["sensor"] == "Sentinel-2"

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_not_found(self, mock_ensure):
        from app.domains.geo.router import get_sentinel2_image
        from app.core.exceptions import NotFoundError

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel2_image.return_value = {"error": "No images"}
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(NotFoundError):
            await get_sentinel2_image(target_date=date(2025, 6, 15))

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_error(self, mock_ensure):
        from app.domains.geo.router import get_sentinel2_image
        from app.core.exceptions import AppException

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel2_image.side_effect = Exception("fail")
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(AppException):
            await get_sentinel2_image(target_date=date(2025, 6, 15))


class TestGeeImageSentinel1:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import get_sentinel1_image

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel1_image.return_value = {
            "tile_url": "https://tiles/{z}/{x}/{y}",
            "sensor": "Sentinel-1",
        }
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        result = await get_sentinel1_image(target_date=date(2025, 6, 15))
        assert result["sensor"] == "Sentinel-1"

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_not_found(self, mock_ensure):
        from app.domains.geo.router import get_sentinel1_image
        from app.core.exceptions import NotFoundError

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel1_image.return_value = {"error": "No images"}
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(NotFoundError):
            await get_sentinel1_image(target_date=date(2025, 6, 15))

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_error(self, mock_ensure):
        from app.domains.geo.router import get_sentinel1_image
        from app.core.exceptions import AppException

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel1_image.side_effect = Exception("fail")
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(AppException):
            await get_sentinel1_image(target_date=date(2025, 6, 15))


class TestGeeImageCompare:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success(self, mock_ensure):
        from app.domains.geo.router import compare_flood_dates

        mock_explorer = MagicMock()
        mock_explorer.get_flood_comparison.return_value = {
            "flood_date": "2025-06-15",
            "normal_date": "2025-01-15",
            "flood_detection": {},
        }
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        result = await compare_flood_dates(
            flood_date=date(2025, 6, 15),
            normal_date=date(2025, 1, 15),
        )
        assert result["flood_date"] == "2025-06-15"

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_error(self, mock_ensure):
        from app.domains.geo.router import compare_flood_dates
        from app.core.exceptions import AppException

        mock_explorer = MagicMock()
        mock_explorer.get_flood_comparison.side_effect = Exception("fail")
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(AppException):
            await compare_flood_dates(
                flood_date=date(2025, 6, 15),
                normal_date=date(2025, 1, 15),
            )


class TestGeeHistoricFloodTiles:
    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_success_with_s2(self, mock_ensure):
        from app.domains.geo.router import get_historic_flood_tiles

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel2_image.return_value = {
            "tile_url": "https://tiles/{z}/{x}/{y}",
        }
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        result = await get_historic_flood_tiles("sep_2025")
        assert "flood_info" in result

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_fallback_to_s1_on_error(self, mock_ensure):
        from app.domains.geo.router import get_historic_flood_tiles

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel2_image.return_value = {"error": "no images"}
        mock_explorer.get_sentinel1_image.return_value = {
            "tile_url": "https://sar-tiles/{z}/{x}/{y}",
        }
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        result = await get_historic_flood_tiles("feb_2017")
        assert "flood_info" in result

    @pytest.mark.asyncio
    @patch("app.domains.geo.router._ensure_gee")
    async def test_gee_error(self, mock_ensure):
        from app.domains.geo.router import get_historic_flood_tiles
        from app.core.exceptions import AppException

        mock_explorer = MagicMock()
        mock_explorer.get_sentinel2_image.side_effect = Exception("GEE timeout")
        mock_ensure.return_value = {"get_image_explorer": lambda: mock_explorer}

        with pytest.raises(AppException):
            await get_historic_flood_tiles("sep_2025")


# ---------------------------------------------------------------------------
# GEE Analysis Submit
# ---------------------------------------------------------------------------


class TestSubmitGeeAnalysis:
    @patch("app.domains.geo.router.dispatch_job", create=True)
    def test_submit_flood_analysis(self, mock_dispatch, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import submit_gee_analysis
        from app.domains.geo.schemas import AnalisisGeoCreate

        # Mock the Celery tasks
        with patch("app.domains.geo.router.analyze_flood_task", create=True) as mock_task, \
             patch("app.domains.geo.router.sar_temporal_task", create=True), \
             patch("app.domains.geo.router.supervised_classification_task", create=True), \
             patch("app.domains.geo.gee_tasks.analyze_flood_task", create=True) as mock_flood_task, \
             patch("app.domains.geo.gee_tasks.sar_temporal_task", create=True), \
             patch("app.domains.geo.gee_tasks.supervised_classification_task", create=True):

            mock_analisis = MagicMock()
            mock_analisis.id = uuid.uuid4()
            mock_repo.create_analisis.return_value = mock_analisis

            mock_celery_result = MagicMock()
            mock_celery_result.id = "celery-task-id"
            mock_flood_task.delay.return_value = mock_celery_result

            payload = AnalisisGeoCreate(
                tipo="flood",
                parametros={"start_date": "2025-01-01", "end_date": "2025-01-31", "method": "fusion"},
            )

            result = submit_gee_analysis(payload, mock_db, mock_repo, _user=mock_user)
            # Should create and return the analysis
            mock_repo.create_analisis.assert_called_once()


# ---------------------------------------------------------------------------
# Water Detection
# ---------------------------------------------------------------------------


class TestWaterDetection:
    @patch("app.domains.geo.water_detection.detect_water_from_gee")
    def test_detect_water_success(self, mock_detect, mock_db, mock_user):
        from app.domains.geo.router import detect_water, WaterDetectionRequest

        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Test Zone"
        mock_db.query.return_value.filter.return_value.first.return_value = zona
        mock_db.execute.return_value.scalar.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        mock_detect.return_value = {"water_area_ha": 15.2}

        body = WaterDetectionRequest(
            zona_id=zona.id,
            target_date="2025-06-15",
        )

        result = detect_water(body, mock_db, _user=mock_user)
        assert result["zona"]["nombre"] == "Test Zone"

    def test_detect_water_zona_not_found(self, mock_db, mock_user):
        from app.domains.geo.router import detect_water, WaterDetectionRequest
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.first.return_value = None

        body = WaterDetectionRequest(
            zona_id=uuid.uuid4(),
            target_date="2025-06-15",
        )

        with pytest.raises(NotFoundError):
            detect_water(body, mock_db, _user=mock_user)


class TestWaterDetectionMulti:
    def test_multi_date_zona_not_found(self, mock_db, mock_user):
        from app.domains.geo.router import detect_water_multi, WaterMultiDateRequest
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.first.return_value = None

        body = WaterMultiDateRequest(
            zona_id=uuid.uuid4(),
            dates=["2025-06-01", "2025-06-15"],
        )

        with pytest.raises(NotFoundError):
            detect_water_multi(body, mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# STAC Catalog
# ---------------------------------------------------------------------------


class TestStacCollections:
    @patch("app.domains.geo.router.get_collections", create=True)
    def test_returns_collections(self, mock_get_collections, mock_db):
        from app.domains.geo.router import stac_collections

        mock_get_collections.return_value = {"collections": []}
        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with patch("app.domains.geo.stac.get_collections", mock_get_collections):
            result = stac_collections(request, mock_db)
            assert "collections" in result


class TestStacSearch:
    @patch("app.domains.geo.router.search_catalog", create=True)
    def test_returns_search_results(self, mock_search, mock_db):
        from app.domains.geo.router import stac_search

        mock_search.return_value = {"items": [], "total": 0}
        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with patch("app.domains.geo.stac.search_catalog", mock_search):
            result = stac_search(request, mock_db, tipo="slope", area_id=None, fuente=None, limit=50, offset=0)
            assert "items" in result or result is not None


class TestStacItem:
    def test_found(self, mock_db):
        from app.domains.geo.router import stac_item

        mock_layer = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_layer
        request = MagicMock()
        request.base_url = "http://localhost:8000/"

        with patch("app.domains.geo.stac.layer_to_stac_item", return_value={"id": "test"}):
            result = stac_item(uuid.uuid4(), request, mock_db)
            assert result["id"] == "test"


# ---------------------------------------------------------------------------
# Temporal Analysis
# ---------------------------------------------------------------------------


class TestNdwiTrend:
    def test_zona_not_found(self, mock_db, mock_user):
        from app.domains.geo.router import analyze_ndwi_trend, NdwiTrendRequest
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.first.return_value = None

        body = NdwiTrendRequest(
            zona_id=uuid.uuid4(),
            start_date="2025-01-01",
            end_date="2025-06-01",
        )

        with pytest.raises(NotFoundError):
            analyze_ndwi_trend(body, mock_db, _user=mock_user)

    @patch("app.domains.geo.temporal.analyze_ndwi_trend_gee", create=True)
    def test_success(self, mock_analyze, mock_db, mock_user):
        from app.domains.geo.router import analyze_ndwi_trend, NdwiTrendRequest

        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Zone A"
        mock_db.query.return_value.filter.return_value.first.return_value = zona
        mock_db.execute.return_value.scalar.return_value = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]}'

        mock_analyze.return_value = {"trend": "increasing", "dates": ["2025-01-01"]}

        body = NdwiTrendRequest(
            zona_id=zona.id,
            start_date="2025-01-01",
            end_date="2025-06-01",
        )

        with patch("app.domains.geo.router.analyze_ndwi_trend_gee", mock_analyze, create=True):
            result = analyze_ndwi_trend(body, mock_db, _user=mock_user)
            assert result["zona"]["nombre"] == "Zone A"


class TestCompareRasters:
    def test_no_layers_found(self, mock_db, mock_user):
        from app.domains.geo.router import compare_rasters, RasterCompareRequest
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        body = RasterCompareRequest(layer_tipo="slope")

        with pytest.raises(NotFoundError):
            compare_rasters(body, mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# Flood Risk
# ---------------------------------------------------------------------------


class TestFloodRisk:
    def test_zona_not_found(self, mock_db, mock_user):
        from app.domains.geo.router import get_zona_flood_risk
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(NotFoundError):
            get_zona_flood_risk(uuid.uuid4(), mock_db, _user=mock_user)

    def test_no_rasters_available(self, mock_db, mock_user):
        from app.domains.geo.router import get_zona_flood_risk
        from app.core.exceptions import AppException

        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Zone A"
        mock_db.query.return_value.filter.return_value.first.return_value = zona

        # No layers found for any tipo
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with pytest.raises(AppException):
            get_zona_flood_risk(zona.id, mock_db, _user=mock_user)

    def test_no_rasters_all_missing(self, mock_db, mock_user):
        """When zona exists but no raster layers are found at all."""
        from app.domains.geo.router import get_zona_flood_risk
        from app.core.exceptions import AppException

        zona = MagicMock()
        zona.id = uuid.uuid4()
        zona.nombre = "Zone A"

        call_count = [0]

        def query_side_effect(model):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: ZonaOperativa query
                q.first.return_value = zona
            else:
                # Subsequent calls: GeoLayer queries for hand, twi, flow_acc, slope
                q.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(AppException):
            get_zona_flood_risk(zona.id, mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# Hydrology
# ---------------------------------------------------------------------------


class TestTwiSummary:
    def test_no_layer_found(self, mock_db, mock_user):
        from app.domains.geo.router import get_twi_summary
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with pytest.raises(NotFoundError):
            get_twi_summary(area_id="zona_principal", db=mock_db, _user=mock_user)

    def test_raster_not_on_disk(self, mock_db, mock_user):
        from app.domains.geo.router import get_twi_summary
        from app.core.exceptions import AppException

        mock_layer = MagicMock()
        mock_layer.archivo_path = "/nonexistent/twi.tif"
        mock_layer.metadata_extra = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_layer

        with pytest.raises(AppException):
            get_twi_summary(area_id="zona_principal", db=mock_db, _user=mock_user)


class TestCanalCapacity:
    def test_no_layer_found(self, mock_db, mock_user):
        from app.domains.geo.router import get_canal_capacity
        from app.core.exceptions import NotFoundError

        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with pytest.raises(NotFoundError):
            get_canal_capacity(area_id="zona_principal", db=mock_db, _user=mock_user)

    def test_raster_not_on_disk(self, mock_db, mock_user):
        from app.domains.geo.router import get_canal_capacity
        from app.core.exceptions import AppException

        mock_layer = MagicMock()
        mock_layer.archivo_path = "/nonexistent/flow_acc.tif"
        mock_layer.metadata_extra = None
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_layer

        with pytest.raises(AppException):
            get_canal_capacity(area_id="zona_principal", db=mock_db, _user=mock_user)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRoutingImport:
    @patch("app.domains.geo.routing.import_canals_from_geojson", create=True)
    @patch("app.domains.geo.routing.build_topology", create=True)
    @patch("app.domains.geo.routing.get_network_stats", create=True)
    def test_import_success(self, mock_stats, mock_topo, mock_import, mock_db, mock_user):
        from app.domains.geo.router import import_canal_network, ImportCanalsRequest

        mock_import.return_value = 10
        mock_topo.return_value = {"nodes": 20, "edges": 10}
        mock_stats.return_value = {"nodes": 20, "edges": 10}

        body = ImportCanalsRequest(geojson_paths=["/path/to/canals.geojson"])

        with patch("app.domains.geo.router.import_canals_from_geojson", mock_import, create=True), \
             patch("app.domains.geo.router.build_topology", mock_topo, create=True), \
             patch("app.domains.geo.router.get_network_stats", mock_stats, create=True):
            result = import_canal_network(body, mock_db, _user=mock_user)
            assert result["imported"] == 10


class TestRoutingShortestPath:
    def test_no_vertices_found(self, mock_db, mock_user):
        from app.domains.geo.router import find_shortest_path, ShortestPathRequest
        from app.core.exceptions import NotFoundError

        body = ShortestPathRequest(from_lon=-63.0, from_lat=-32.0, to_lon=-63.1, to_lat=-32.1)

        with patch("app.domains.geo.routing.find_nearest_vertex", return_value=None, create=True):
            with pytest.raises(NotFoundError):
                find_shortest_path(body, mock_db, _user=mock_user)

    def test_success(self, mock_db, mock_user):
        from app.domains.geo.router import find_shortest_path, ShortestPathRequest

        body = ShortestPathRequest(from_lon=-63.0, from_lat=-32.0, to_lon=-63.1, to_lat=-32.1)

        source = {"id": 1, "lon": -63.0, "lat": -32.0}
        target = {"id": 2, "lon": -63.1, "lat": -32.1}
        path_edges = [
            {
                "nombre": "Canal A",
                "cost": 100.0,
                "agg_cost": 100.0,
                "path_seq": 1,
                "geometry": {"type": "LineString", "coordinates": [[-63.0, -32.0], [-63.1, -32.1]]},
            }
        ]

        with patch("app.domains.geo.routing.find_nearest_vertex", side_effect=[source, target], create=True), \
             patch("app.domains.geo.routing.shortest_path", return_value=path_edges, create=True):
            result = find_shortest_path(body, mock_db, _user=mock_user)
            assert result["total_distance_m"] == 100.0
            assert result["edges"] == 1
            assert result["geojson"]["type"] == "FeatureCollection"


class TestRoutingStats:
    def test_returns_stats(self, mock_db, mock_user):
        from app.domains.geo.router import get_routing_network_stats

        with patch("app.domains.geo.routing.get_network_stats", return_value={"nodes": 10}, create=True):
            result = get_routing_network_stats(mock_db, _user=mock_user)
            assert result["nodes"] == 10


# ---------------------------------------------------------------------------
# Approved Zones — PDF Export and Restore
# ---------------------------------------------------------------------------


class TestApprovedZonesPdfExport:
    def test_no_zoning_returns_404(self, mock_db, mock_repo):
        from app.domains.geo.router import export_current_approved_basin_zones_pdf

        mock_repo.get_active_approved_zoning.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            export_current_approved_basin_zones_pdf(cuenca=None, db=mock_db, repo=mock_repo)
        assert exc_info.value.status_code == 404

    @patch("app.domains.geo.router._get_user_display_name")
    @patch("app.shared.pdf.build_approved_zoning_pdf", create=True)
    @patch("app.shared.pdf.get_branding", create=True)
    def test_success(self, mock_branding, mock_pdf, mock_display_name, mock_db, mock_repo):
        from app.domains.geo.router import export_current_approved_basin_zones_pdf

        mock_zoning = MagicMock()
        mock_zoning.version = 1
        mock_zoning.approved_by_id = uuid.uuid4()
        mock_repo.get_active_approved_zoning.return_value = mock_zoning
        mock_branding.return_value = {}
        mock_display_name.return_value = "Admin Test"
        mock_pdf.return_value = io.BytesIO(b"PDF content")

        with patch("app.domains.geo.router.build_approved_zoning_pdf", mock_pdf, create=True), \
             patch("app.domains.geo.router.get_branding", mock_branding, create=True):
            result = export_current_approved_basin_zones_pdf(cuenca=None, db=mock_db, repo=mock_repo)
            assert result.media_type == "application/pdf"


class TestApprovedZonesMapPdf:
    @patch("app.shared.pdf.build_approved_zoning_map_pdf", create=True)
    @patch("app.shared.pdf.get_branding", create=True)
    def test_success(self, mock_branding, mock_pdf, mock_db):
        from app.domains.geo.router import export_current_map_approved_basin_zones_pdf, ApprovedZonesMapPdfRequest

        mock_branding.return_value = {}
        mock_pdf.return_value = io.BytesIO(b"PDF map")

        payload = MagicMock()
        payload.model_dump.return_value = {"mapImageBase64": "base64data"}

        with patch("app.domains.geo.router.build_approved_zoning_map_pdf", mock_pdf, create=True), \
             patch("app.domains.geo.router.get_branding", mock_branding, create=True):
            result = export_current_map_approved_basin_zones_pdf(payload, mock_db)
            assert result.media_type == "application/pdf"


class TestRestoreApprovedZones:
    def test_source_not_found(self, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import restore_approved_basin_zone_version

        mock_repo.get_approved_zoning_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            restore_approved_basin_zone_version(
                zoning_id=uuid.uuid4(), db=mock_db, repo=mock_repo, user=mock_user,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# _ensure_gee
# ---------------------------------------------------------------------------


class TestEnsureGee:
    @patch("app.domains.geo.router._lazy_gee_service")
    def test_success(self, mock_lazy):
        from app.domains.geo.router import _ensure_gee

        mock_ensure_init = MagicMock()
        mock_lazy.return_value = {"ensure_init": mock_ensure_init, "other": "value"}

        result = _ensure_gee()
        mock_ensure_init.assert_called_once()
        assert result["other"] == "value"

    @patch("app.domains.geo.router._lazy_gee_service")
    def test_raises_503_on_failure(self, mock_lazy):
        from app.domains.geo.router import _ensure_gee
        from app.core.exceptions import AppException

        mock_ensure_init = MagicMock(side_effect=Exception("init failed"))
        mock_lazy.return_value = {"ensure_init": mock_ensure_init}

        with pytest.raises(AppException):
            _ensure_gee()


# ---------------------------------------------------------------------------
# Bundle Export
# ---------------------------------------------------------------------------


class TestBundleExport:
    @patch("app.domains.geo.router._build_approved_zoning_export")
    @patch("app.domains.geo.router._build_zonas_operativas_export")
    def test_export_creates_zip(self, mock_zonas, mock_approved, mock_db, mock_repo, mock_user):
        from app.domains.geo.router import export_geo_bundle

        mock_zonas.return_value = {"type": "FeatureCollection", "features": []}
        mock_approved.return_value = None
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        result = export_geo_bundle(mock_db, mock_repo, _user=mock_user)

        assert result.media_type == "application/zip"


# ---------------------------------------------------------------------------
# Suggested Zones
# ---------------------------------------------------------------------------


class TestSuggestedZones:
    @patch("app.domains.geo.router.IntelligenceRepository")
    def test_returns_zones(self, MockIntelRepo, mock_db):
        from app.domains.geo.router import get_suggested_basin_zones

        mock_repo_inst = MagicMock()
        mock_zones = []
        mock_repo_inst.get_zonas.return_value = mock_zones
        MockIntelRepo.return_value = mock_repo_inst

        result = get_suggested_basin_zones(cuenca=None, db=mock_db)
        assert isinstance(result, dict)
