"""Unit tests for app.domains.geo.stac — STAC catalog, items, collections."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.domains.geo.stac import (
    STAC_VERSION,
    get_collections,
    layer_to_stac_item,
    search_catalog,
)


def _make_layer(**overrides):
    """Create a mock GeoLayer with sensible defaults."""
    layer = MagicMock()
    layer.id = overrides.get("id", 1)
    layer.nombre = overrides.get("nombre", "Test Layer")
    layer.tipo = overrides.get("tipo", "slope")
    layer.fuente = overrides.get("fuente", "dem_pipeline")
    layer.formato = overrides.get("formato", "geotiff")
    layer.srid = overrides.get("srid", 4326)
    layer.bbox = overrides.get("bbox", [-63.0, -33.0, -62.0, -32.0])
    layer.metadata_extra = overrides.get("metadata_extra", None)
    layer.archivo_path = overrides.get("archivo_path", "/data/layers/test.tif")
    layer.area_id = overrides.get("area_id", "area-1")
    layer.created_at = overrides.get("created_at", datetime(2025, 6, 15, 10, 0, 0))
    return layer


# ── layer_to_stac_item ────────────────────────────


class TestLayerToStacItem:
    """Tests for GeoLayer → STAC Item conversion."""

    def test_basic_structure(self):
        item = layer_to_stac_item(_make_layer())
        assert item["type"] == "Feature"
        assert item["stac_version"] == STAC_VERSION
        assert item["id"] == "1"

    def test_bbox_generates_polygon_geometry(self):
        item = layer_to_stac_item(_make_layer(bbox=[-63.0, -33.0, -62.0, -32.0]))
        geom = item["geometry"]
        assert geom["type"] == "Polygon"
        assert len(geom["coordinates"][0]) == 5  # closed ring

    def test_no_bbox_generates_null_geometry(self):
        item = layer_to_stac_item(_make_layer(bbox=[]))
        assert item["geometry"] is None

    def test_none_bbox_generates_null_geometry(self):
        item = layer_to_stac_item(_make_layer(bbox=None))
        assert item["geometry"] is None

    def test_properties_include_custom_fields(self):
        item = layer_to_stac_item(_make_layer(tipo="slope", fuente="gee", srid=32720))
        props = item["properties"]
        assert props["consorcio:tipo"] == "slope"
        assert props["consorcio:fuente"] == "gee"
        assert props["proj:epsg"] == 32720

    def test_datetime_from_created_at(self):
        dt = datetime(2025, 3, 1, 12, 0, 0)
        item = layer_to_stac_item(_make_layer(created_at=dt))
        assert item["properties"]["datetime"] == dt.isoformat()

    def test_geotiff_media_type(self):
        item = layer_to_stac_item(_make_layer(formato="geotiff"))
        assert "image/tiff" in item["assets"]["data"]["type"]

    def test_geojson_media_type(self):
        item = layer_to_stac_item(_make_layer(formato="geojson"))
        assert item["assets"]["data"]["type"] == "application/geo+json"

    def test_no_archivo_path_means_no_data_asset(self):
        item = layer_to_stac_item(_make_layer(archivo_path=None))
        assert "data" not in item["assets"]

    def test_metadata_extra_resolution_injected(self):
        meta = {"resolution": 30, "nodata": -9999}
        item = layer_to_stac_item(_make_layer(metadata_extra=meta))
        props = item["properties"]
        assert props["consorcio:resolution"] == 30
        assert props["consorcio:nodata"] == -9999

    def test_cog_asset_added_when_cog_path_present(self):
        meta = {"cog_path": "/data/cog/test_cog.tif"}
        item = layer_to_stac_item(_make_layer(metadata_extra=meta))
        assert "cog" in item["assets"]
        assert "cloud-optimized" in item["assets"]["cog"]["type"]

    def test_tiles_asset_for_geotiff_with_base_url(self):
        item = layer_to_stac_item(
            _make_layer(formato="geotiff", id=42),
            base_url="http://api.local",
        )
        assert "tiles" in item["assets"]
        assert "/tiles/42/" in item["assets"]["tiles"]["href"]

    def test_no_tiles_for_geojson(self):
        item = layer_to_stac_item(
            _make_layer(formato="geojson"),
            base_url="http://api.local",
        )
        assert "tiles" not in item["assets"]

    def test_links_include_self_and_collection(self):
        item = layer_to_stac_item(_make_layer(id=7), base_url="http://api")
        rels = {link["rel"] for link in item["links"]}
        assert "self" in rels
        assert "collection" in rels


# ── search_catalog ────────────────────────────────


class TestSearchCatalog:
    """Tests for STAC search with filters (mocked DB)."""

    def _mock_db(self, layers, total=None):
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = total if total is not None else len(layers)
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = layers
        return mock_db

    def test_empty_catalog(self):
        result = search_catalog(self._mock_db([]))
        assert result["type"] == "FeatureCollection"
        assert result["numberMatched"] == 0
        assert result["features"] == []

    def test_returns_features(self):
        layers = [_make_layer(id=1), _make_layer(id=2)]
        result = search_catalog(self._mock_db(layers))
        assert result["numberReturned"] == 2
        assert len(result["features"]) == 2

    def test_context_block(self):
        result = search_catalog(self._mock_db([], total=50), limit=10, offset=0)
        assert result["context"]["matched"] == 50
        assert result["context"]["limit"] == 10

    def test_links_present(self):
        result = search_catalog(self._mock_db([]), base_url="http://api")
        rels = {link["rel"] for link in result["links"]}
        assert "self" in rels
        assert "root" in rels


# ── get_collections ───────────────────────────────


class TestGetCollections:
    """Tests for STAC collection grouping by tipo."""

    def test_empty_collections(self):
        mock_db = MagicMock()
        mock_db.query.return_value.group_by.return_value.all.return_value = []
        result = get_collections(mock_db)
        assert result["collections"] == []

    def test_collections_have_stac_version(self):
        mock_db = MagicMock()
        mock_db.query.return_value.group_by.return_value.all.return_value = [
            ("slope", 5),
        ]
        result = get_collections(mock_db)
        coll = result["collections"][0]
        assert coll["stac_version"] == STAC_VERSION
        assert coll["id"] == "slope"
        assert coll["item_count"] == 5

    def test_multiple_collections(self):
        mock_db = MagicMock()
        mock_db.query.return_value.group_by.return_value.all.return_value = [
            ("slope", 3),
            ("aspect", 7),
        ]
        result = get_collections(mock_db)
        assert len(result["collections"]) == 2
        ids = {c["id"] for c in result["collections"]}
        assert ids == {"slope", "aspect"}
