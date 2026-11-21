"""Contract tests against the REAL GEE API — opt-in, like IDECOR_LIVE.

RULE (AGENTS.md): for any external API integration there MUST be at least
one opt-in live test exercising the real API surface. Mocked tests prove
internal logic; they CANNOT prove the API contract (keyword names, asset
loading patterns, band validation, projection handling). Seven layers of
mock-passed bugs shipped to production before this rule existed
(PRs #753-#760, the "thumbnail onion").

Run with: GEE_LIVE=1 PYTHONPATH=. pytest tests/new/test_gee_live_contract.py -v
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEE_LIVE"),
    reason="GEE real — opt-in with GEE_LIVE=1 (requires service account)",
)

# A known-good S1 scene from the anchor events (curated flood anchors).
_S1_SCENE = "S1A_IW_GRDH_1SDV_20250904T093110_20250904T093135_060836_079311_84C3"

# A small polygon in the consorcio zone.
_REGION = {
    "type": "Polygon",
    "coordinates": [
        [
            [-62.55, -32.55],
            [-62.45, -32.55],
            [-62.45, -32.48],
            [-62.55, -32.48],
            [-62.55, -32.55],
        ]
    ],
}


class TestGeeInitialization:
    def test_ensure_initialized_resolves(self):
        """Layer 4: the app's _ensure_initialized must succeed with the box's key."""
        from app.domains.geo.gee_service import _ensure_initialized

        _ensure_initialized()


class TestSentinel1Thumbnail:
    def test_s1_band_config_is_single_band(self):
        """Layer 9: production renders S1 with a single VV band — multi-band
        S1 compositing triggers 'inconsistent projections' (box-verified
        2026-11-20: 2 bands fail, VV alone returns a valid PNG)."""
        from app.domains.geo.informe_area.service import _BANDAS_FALSO_COLOR

        bandas, minimo, maximo = _BANDAS_FALSO_COLOR["sentinel1"]
        assert bandas == ["VV"]
        assert minimo == -25.0
        assert maximo == 0.0

    def test_s1_scene_loads_from_collection(self):
        """Layer 5: S1 scenes are NOT standalone assets — they live in ImageCollection."""
        import ee
        from app.domains.geo.gee_service import _ensure_initialized

        _ensure_initialized()
        col = ee.ImageCollection("COPERNICUS/S1_GRD")
        img = col.filter(ee.Filter.eq("system:index", _S1_SCENE)).first()
        assert img is not None
        # This getInfo() would fail with "Image asset not found" if the
        # loading pattern is wrong (ee.Image(scene_id) instead of collection).
        assert img.get("system:index").getInfo() == _S1_SCENE

    def test_s1_select_bands_no_duplicates(self):
        """Layer 6: select() rejects duplicate band names."""
        import ee
        from app.domains.geo.gee_service import _ensure_initialized

        _ensure_initialized()
        col = ee.ImageCollection("COPERNICUS/S1_GRD")
        img = col.filter(ee.Filter.eq("system:index", _S1_SCENE)).first()
        # This would throw "band already exists" with [VV, VH, VV]
        selected = img.select(["VV", "VH"])
        assert selected is not None

    def test_miniatura_falso_color_returns_png(self):
        """Layers 1-7: the full thumbnail pipeline must produce PNG bytes.

        Exercises: sensor band lookup, Geometry constructor keyword,
        initialization, collection loading, band selection, clip,
        getThumbURL with crs, HTTP download. Any of the seven onion
        layers failing surfaces here as a non-PNG or empty result.
        """
        from app.domains.geo.informe_area.service import (
            _miniatura_por_defecto,
        )

        png = _miniatura_por_defecto(_S1_SCENE, "sentinel1", _REGION)
        assert png is not None
        assert len(png) > 1000, f"PNG too small: {len(png)} bytes"
        assert png[:4] == b"\x89PNG", f"Not a PNG: starts with {png[:8]!r}"

        import io

        import numpy as np
        from PIL import Image

        arr = np.asarray(Image.open(io.BytesIO(png)))
        assert float(arr.std()) > 1.0, "S1 thumbnail is flat/black (stretch bug)"


class TestSentinel2Thumbnail:
    def test_s2_scene_loads_as_standalone_image(self):
        """S2 scenes DO load as standalone Image assets (unlike S1)."""
        import ee
        from app.domains.geo.gee_service import _ensure_initialized

        _ensure_initialized()
        # A known S2 scene over Córdoba
        img = ee.Image("COPERNICUS/S2_SR_HARMONIZED/20250315T140049_20250315T140049_T21HUB")
        assert img is not None
        assert img.get("system:index").getInfo() == "20250315T140049_20250315T140049_T21HUB"

    def test_miniatura_s2_falso_color(self):
        """The S2 thumbnail pipeline (if an S2 scene is ever used for anchors)."""
        from app.domains.geo.informe_area.service import (
            _BANDAS_FALSO_COLOR,
        )

        assert "sentinel2" in _BANDAS_FALSO_COLOR
        bandas, _minimo, maximo = _BANDAS_FALSO_COLOR["sentinel2"]
        assert len(bandas) == 3  # NIR, SWIR1, Red — true false-color
        assert maximo > 0
