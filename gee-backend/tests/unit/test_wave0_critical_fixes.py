"""Regression tests for Wave 0 production-critical fixes (C1, C3, C5, C6, C7, C8, C11)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import from_origin
from reportlab.lib.units import mm

from app.domains.geo import ficha_errors


def test_app_main_registers_informe_area_error_handler_and_retry_after() -> None:
    """C1: app.main registers InformeAreaError and _manejador emits Retry-After."""
    from app.domains.geo.informe_area.errors import InformeAreaError, _manejador, pdf_en_progreso
    from app.main import app

    assert InformeAreaError in app.exception_handlers

    resp = _manejador(None, pdf_en_progreso())
    assert resp.status_code == 409
    assert resp.headers["Retry-After"] == "30"
    assert json.loads(resp.body)["codigo"] == "informe_en_progreso"


def test_validar_geometrias_reaches_total_vertex_cap() -> None:
    """C3: many small polygons whose combined vertices exceed max_vertices fail with 422."""
    from app.config import settings
    from app.domains.geo.informe_area.schemas import InformeAreaCreate

    # Each 8,001-vertex ring sits under the per-geometry limit (20,000),
    # while three together hit 24,003 > 20,000.
    n = 8000
    ring = [[float(i % 100) * 0.001, float(i // 100) * 0.001] for i in range(n)]
    ring.append(ring[0])
    poly = {"type": "Polygon", "coordinates": [ring]}

    with pytest.raises((ficha_errors.FichaError, ValidationError)) as excinfo:
        InformeAreaCreate(
            nombre="muchos vertices",
            geometrias=[poly, poly, poly],
        )
    if isinstance(excinfo.value, ficha_errors.FichaError):
        assert excinfo.value.codigo == "cap_excedido"
        assert settings.informe_area_max_vertices == 20_000


def test_extract_zonal_profile_oom_guard_for_distant_polygons(tmp_path: Path) -> None:
    """C3: distant polygons inside a huge bounding box must not allocate GBs for ext_fractions."""
    from app.domains.geo.composites import extract_zonal_profile

    tif_path = tmp_path / "small_utm.tif"
    # Small 10x10 raster at 10 m resolution in EPSG:32720 around Bell Ville.
    origin_x, origin_y = 530_000.0, 6_400_000.0
    data = np.ones((10, 10), dtype=np.float32) * 2.0
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:32720",
        transform=from_origin(origin_x, origin_y, 10.0, 10.0),
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)

    # Disjoint MultiPolygon: one tiny square over the raster, another 300 km away
    # -> ext_height * ext_width = ~9e8 pixels without the guard.
    near = [
        [origin_x + 10.0, origin_y - 10.0],
        [origin_x + 50.0, origin_y - 10.0],
        [origin_x + 50.0, origin_y - 50.0],
        [origin_x + 10.0, origin_y - 50.0],
        [origin_x + 10.0, origin_y - 10.0],
    ]
    far = [
        [origin_x + 300_000.0, origin_y - 300_000.0],
        [origin_x + 300_040.0, origin_y - 300_000.0],
        [origin_x + 300_040.0, origin_y - 300_040.0],
        [origin_x + 300_000.0, origin_y - 300_040.0],
        [origin_x + 300_000.0, origin_y - 300_000.0],
    ]
    geom = {"type": "MultiPolygon", "coordinates": [[near], [far]]}

    perfil = extract_zonal_profile(str(tif_path), geom, geom_crs="EPSG:32720")
    assert perfil["valid_pixels"] > 0
    assert perfil["coverage"] == "partial"
    assert 0.4 <= perfil["coverage_ratio"] <= 0.6


def test_kmz_multipolygon_rings_holes_and_ascii_image_keys() -> None:
    """C5: MultiPolygon preserves per-part outer/inner rings, skips short rings, normalizes tildes."""
    from app.domains.geo.informe_area.kmz import (
        KML_NS,
        ClaseKmz,
        ImagenKmz,
        TemaKmz,
        _clave_imagen,
        _placemark_linea,
        construir_kmz_informe,
    )

    outer1 = [[-62.5, -32.5], [-62.4, -32.5], [-62.4, -32.4], [-62.5, -32.4], [-62.5, -32.5]]
    hole1 = [
        [-62.48, -32.48],
        [-62.42, -32.48],
        [-62.42, -32.42],
        [-62.48, -32.42],
        [-62.48, -32.48],
    ]
    outer2 = [[-62.3, -32.3], [-62.2, -32.3], [-62.2, -32.2], [-62.3, -32.2], [-62.3, -32.3]]
    degenerate = [[-62.1, -32.1], [-62.0, -32.1]]  # < 4 vertices

    from shapely.geometry import mapping as shapely_mapping
    from shapely.geometry import shape as shapely_shape

    multipoly = {"type": "MultiPolygon", "coordinates": [[outer1, hole1], [outer2], [degenerate]]}
    # Ensure Shapely mapping() tuple coordinates work identically to JSON lists.
    multipoly_tuples = shapely_mapping(
        shapely_shape({"type": "MultiPolygon", "coordinates": [[outer1, hole1], [outer2]]})
    )
    tema_valido = TemaKmz(
        titulo="Riesgo",
        clases=[
            ClaseKmz(clase="Alto", color="#e04040", geometrias=[multipoly]),
            ClaseKmz(clase="Tupla", color="#3070b0", geometrias=[multipoly_tuples]),
        ],
    )
    tema_vacio = TemaKmz(
        titulo="Vacio",
        clases=[
            ClaseKmz(
                clase="SoloDeg",
                color="#111111",
                geometrias=[{"type": "Polygon", "coordinates": [degenerate]}],
            )
        ],
    )

    assert (
        _placemark_linea("p", "s", [{"type": "Polygon", "coordinates": [[[-62.5, -32.5]]]}]) == ""
    )
    assert _clave_imagen("Imágenes Ñandú Útil", 2) == "imagenes-nandu-util-2"

    kmz_bytes = construir_kmz_informe(
        nombre="Test KMZ",
        seleccion_geojson={"type": "Polygon", "coordinates": [outer1]},
        subcuencas=[],
        temas=[tema_valido, tema_vacio],
        imagenes=[
            ImagenKmz(
                titulo="Evento Otoño", png=b"\x89PNG-test", bounds=(-62.5, -32.5, -62.4, -32.4)
            )
        ],
    )
    with zipfile.ZipFile(BytesIO(kmz_bytes)) as zf:
        names = set(zf.namelist())
        assert "files/imagen-evento-otono-0.png" in names
        root = ET.fromstring(zf.read("doc.kml"))

    polygons = root.findall(f".//{{{KML_NS}}}Polygon")
    assert len(polygons) == 4
    inners = root.findall(f".//{{{KML_NS}}}innerBoundaryIs")
    assert len(inners) == 2
    folder_names = [el.text for el in root.findall(f".//{{{KML_NS}}}Folder/{{{KML_NS}}}name")]
    assert "Vacio" not in folder_names


def test_imagenes_eventos_ancla_simplifies_complex_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C6: imagenes_eventos_ancla passes a simplified geometry clip to fetch_miniatura."""
    from app.domains.geo.informe_area import service

    # 300-point circle around Bell Ville
    angles = np.linspace(0, 2 * np.pi, 300, endpoint=False)
    coords = [[-62.5 + 0.05 * float(np.cos(a)), -32.5 + 0.05 * float(np.sin(a))] for a in angles]
    coords.append(coords[0])
    dense_poly = {"type": "Polygon", "coordinates": [coords]}

    evento = type(
        "_Ev",
        (),
        {"event_key": "ev1", "start_date": "2025-09-04", "curated_payload": {"name": "Sept"}},
    )()
    cand = type(
        "_Ca",
        (),
        {"event_key": "ev1", "sensor": "sentinel2", "scene_id": "S2_IDX", "cloud_pct": 5.0},
    )()

    class _Nested:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Exec:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    db = MagicMock()
    db.begin_nested.side_effect = lambda: _Nested()
    db.execute.side_effect = [_Exec([evento]), _Exec([cand])]

    captured: list[dict] = []

    def _fetch(scene_id: str, sensor: str, region: dict) -> bytes:
        captured.append(region)
        return b"PNG"

    service.imagenes_eventos_ancla(db, dense_poly, fetch_miniatura=_fetch)
    assert len(captured) == 1
    assert len(captured[0]["coordinates"][0]) < len(coords)


def test_qr_bloque_campo_usa_24mm_reales_y_pct_seleccion_usa_area_total(tmp_path: Path) -> None:
    """C7: QR Drawing is 24*mm x 24*mm; C8: _pct_clases, _tabla_clases y _perfil_por_clase divide by area_ha."""
    from app.domains.geo.informe_area.service import _perfil_por_clase
    from app.shared.pdf.base import BrandingInfo, get_pdf_styles
    from app.shared.pdf.builders_informe_area import (
        _pct_clases,
        _qr_campo,
        _tabla_clases,
    )

    branding = BrandingInfo(
        nombre_organizacion="Consorcio", color_primario="#1a5276", logo_path=None
    )
    flowables = _qr_campo("https://consorcio.test/campo/tok123", get_pdf_styles(branding))
    table = flowables[0]
    drawing = table._cellvalues[0][0]
    assert drawing.width == pytest.approx(24.0 * mm, abs=0.01)
    assert drawing.height == pytest.approx(24.0 * mm, abs=0.01)
    assert table._colWidths[0] == pytest.approx(24.0 * mm, abs=0.01)

    # C8a: _perfil_por_clase with partial 10% raster coverage in a 100 ha selection -> pct ~= 10.0, not 100.0
    tif_path = tmp_path / "cob_parcial.tif"
    origin_x, origin_y = 530_000.0, 6_400_000.0
    arr = np.full((10, 10), np.nan, dtype=np.float32)
    arr[0:1, :] = 1.0  # 10 pixels of class 1 out of 100 pixels = 10%
    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:32720",
        transform=from_origin(origin_x, origin_y, 100.0, 100.0),
    ) as dst:
        dst.write(arr, 1)

    from pyproj import Transformer
    from shapely.geometry import box, mapping
    from shapely.ops import transform as shapely_transform

    to_4326 = Transformer.from_crs("EPSG:32720", "EPSG:4326", always_xy=True)
    geom4326 = mapping(
        shapely_transform(
            to_4326.transform,
            box(origin_x, origin_y - 1000.0, origin_x + 1000.0, origin_y),
        )
    )
    clases, cobertura, _ratio = _perfil_por_clase(
        str(tif_path),
        [{"codigo": 1, "etiqueta": "Soja"}],
        geom4326,
        1_000_000.0,  # 100 ha
    )
    assert cobertura == "partial"
    assert clases[0]["clase"] == "Soja"
    assert clases[0]["pct"] == pytest.approx(10.0, abs=0.2)

    # C8b: _pct_clases & _tabla_clases scale covered-only raster pct by cobertura_ratio,
    # keeping full coverage at exact 100.0 without cross-CRS distortion.
    dataset = {
        "cobertura": "parcial",
        "area_ha": 1000.0,
        "pixel_count": 100,
        "cobertura_ratio": 0.1,
        "clases": [{"clase": "Alto", "ha": 100.0, "pct": 100.0}],
    }
    assert _pct_clases(dataset, ("Alto",)) == 10.0
    assert (
        _pct_clases({**dataset, "cobertura_ratio": 1.0, "cobertura": "total"}, ("Alto",)) == 100.0
    )

    tabla_flows = _tabla_clases(
        dataset,
        [{"label": "Alto"}],
        branding,
        titulo_total="Total con cobertura",
    )
    tbl = tabla_flows[0]
    alto_row = tbl._cellvalues[1]
    pct_text = alto_row[2].text if hasattr(alto_row[2], "text") else str(alto_row[2])
    assert "10,0 %" in pct_text or "10,0%" in pct_text


def test_middleware_public_map_get_blocks_private_basins_subroutes() -> None:
    """C11: only exact /basins and /basins/approved-zones/current bypass rate limit/cache."""
    from app.core.middleware import DistributedRateLimitMiddleware

    assert DistributedRateLimitMiddleware._is_public_map_get("GET", "/api/v2/geo/basins") is True
    assert (
        DistributedRateLimitMiddleware._is_public_map_get(
            "GET", "/api/v2/geo/basins/approved-zones/current"
        )
        is True
    )
    assert (
        DistributedRateLimitMiddleware._is_public_map_get(
            "GET", "/api/v2/geo/basins/catastro-membership"
        )
        is False
    )
    assert (
        DistributedRateLimitMiddleware._is_public_map_get(
            "GET", "/api/v2/geo/basins/approved-zones/history"
        )
        is False
    )
    assert (
        DistributedRateLimitMiddleware._is_public_map_get(
            "GET", "/api/v2/geo/basins/approved-zones/current/export-pdf"
        )
        is False
    )
