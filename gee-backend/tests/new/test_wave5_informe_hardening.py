"""Regression tests for Wave 5 W-INF-04 and S-01 GEE/suelos/preview hardening."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from affine import Affine
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform as shapely_transform
from sqlalchemy.orm import Session

from app.domains.geo import ficha_service
from app.domains.geo.informe_area import service, tasks
from app.domains.geo.informe_area.schemas import InformeAreaPreviewRequest


def test_sanitizar_error_informe_strips_sql_paths_and_dsns() -> None:
    sql_exc = RuntimeError("SELECT * FROM users WHERE postgresql://admin:pw@db.internal:5432/prod")
    path_exc = OSError("cannot open /app/data/secret.tif")
    benign_exc = RuntimeError("GEE no disponible")

    assert "postgresql://" not in tasks._sanitizar_error_informe(sql_exc)
    assert "SELECT" not in tasks._sanitizar_error_informe(sql_exc)
    assert "/app/data" not in tasks._sanitizar_error_informe(path_exc)
    assert tasks._sanitizar_error_informe(benign_exc) == "RuntimeError: GEE no disponible"


def test_recurrencia_estivales_windows_dynamic_pixel_size_and_latest_3_campaigns(
    tmp_path,
) -> None:
    crs = "EPSG:32720"
    # 20 m x 20 m pixels (0.04 ha/px instead of hardcoded 0.01 ha/px), 20x20 grid
    origin_x, origin_y = 500_000.0, 6_450_000.0
    transform = Affine(20.0, 0.0, origin_x, 0.0, -20.0, origin_y)
    # 4x4 pixel polygon -> 16 pixels * 0.04 ha = 0.64 ha total
    poly_32720 = box(origin_x + 40.0, origin_y - 120.0, origin_x + 120.0, origin_y - 40.0)
    to_4326 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    geom4326 = mapping(shapely_transform(to_4326.transform, poly_32720))

    # Build 4 campaigns so latest 3 (c2, c3, c4) are evaluated and c1 is ignored:
    # first 8 pixels valid in all 3 latest campaigns, next 8 valid in 2 latest campaigns.
    estivales = []
    for idx, mask_row_range in enumerate(
        [
            slice(0, 0),  # c1: empty (should be dropped by estivales[-3:])
            slice(2, 6),  # c2: rows 2..5 (all 4 rows inside polygon)
            slice(2, 6),  # c3: rows 2..5 (all 4 rows inside polygon)
            slice(2, 4),  # c4: rows 2..3 (top half of polygon only -> 8 pixels)
        ],
        start=1,
    ):
        ruta = str(tmp_path / f"estival_{idx}.tif")
        arr = np.full((20, 20), np.nan, dtype="float32")
        arr[mask_row_range, 2:6] = 1.0
        with rasterio.open(
            ruta,
            "w",
            driver="GTiff",
            height=20,
            width=20,
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
            nodata=None,
        ) as dst:
            dst.write(arr, 1)
        estivales.append({"capa": f"c{idx}", "archivo_path": ruta})

    res = service._recurrencia_estivales(estivales, geom4326)
    assert res is not None
    assert res["3_campanias_ha"] == pytest.approx(0.32, abs=0.01)
    assert res["2_campanias_ha"] == pytest.approx(0.32, abs=0.01)
    assert res["1_campanias_ha"] == 0.0
    assert res["0_campanias_ha"] == 0.0


def test_previsualizar_applies_statement_timeout_and_reports_full_fuera_when_no_zone_intersects(
    db: Session, monkeypatch
) -> None:
    calls: list[Session] = []
    real_timeout = ficha_service._aplicar_statement_timeout

    def spy_timeout(sess: Session) -> None:
        calls.append(sess)
        real_timeout(sess)

    monkeypatch.setattr(ficha_service, "_aplicar_statement_timeout", spy_timeout)

    # Drawn square far from any seeded zona in DB -> zona_consorcio.g is NULL -> 100% fuera
    isolated_poly = {
        "type": "Polygon",
        "coordinates": [
            [[-69.0, -39.0], [-68.99, -39.0], [-68.99, -38.99], [-69.0, -38.99], [-69.0, -39.0]]
        ],
    }
    resp = service.previsualizar(
        db,
        InformeAreaPreviewRequest(zona_ids=[], geometrias=[isolated_poly]),
    )
    assert calls == [db]
    assert resp.area_total_ha > 0.0
    assert resp.fuera_zona_ha == pytest.approx(resp.area_total_ha, rel=1e-4)


def test_miniatura_falso_color_enforces_streaming_and_content_length_caps() -> None:
    class _Imagen:
        def select(self, _b):
            return self

        def clip(self, _r):
            return self

        def getThumbURL(self, _p):
            return "https://ee.example/thumb"

    class _EE:
        def Image(self, _s):
            return _Imagen()

        def Geometry(self, **_kw):
            return "reg"

    class _StreamResp:
        def __init__(self, headers, chunks) -> None:
            self.headers = headers
            self._chunks = chunks
            self.closed = False

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, _chunk_size: int):
            yield from self._chunks

        def close(self) -> None:
            self.closed = True

    oversized_header_resp = _StreamResp(
        {"Content-Length": str(service.MINIATURA_MAX_BYTES + 1)},
        [b"abc"],
    )
    with pytest.raises(ValueError, match="excede limite"):
        service.miniatura_falso_color_impl(
            scene_id="COPERNICUS/S2/1",
            sensor="sentinel2",
            region_geojson={"type": "Polygon", "coordinates": []},
            ee_module=_EE(),
            requests_module=SimpleNamespace(get=lambda *_a, **_kw: oversized_header_resp),
        )
    assert oversized_header_resp.closed is True

    oversized_stream_resp = _StreamResp(
        {},
        [
            b"a" * (service.MINIATURA_MAX_BYTES // 2 + 1),
            b"b" * (service.MINIATURA_MAX_BYTES // 2 + 1),
        ],
    )
    with pytest.raises(ValueError, match="excede limite"):
        service.miniatura_falso_color_impl(
            scene_id="COPERNICUS/S2/1",
            sensor="sentinel2",
            region_geojson={"type": "Polygon", "coordinates": []},
            ee_module=_EE(),
            requests_module=SimpleNamespace(get=lambda *_a, **_kw: oversized_stream_resp),
        )
    assert oversized_stream_resp.closed is True


def test_imagenes_eventos_ancla_fetches_in_parallel_and_preserves_order() -> None:
    eventos = [
        SimpleNamespace(event_key="ev_1", start_date="2015-03-15", curated_payload={"name": "E1"}),
        SimpleNamespace(event_key="ev_2", start_date="2017-02-20", curated_payload={"name": "E2"}),
        SimpleNamespace(event_key="ev_3", start_date="2025-09-05", curated_payload={"name": "E3"}),
    ]
    candidatos = [
        SimpleNamespace(event_key="ev_1", sensor="landsat8", scene_id="S1", cloud_pct=1.0),
        SimpleNamespace(event_key="ev_2", sensor="sentinel2", scene_id="S2", cloud_pct=2.0),
        SimpleNamespace(event_key="ev_3", sensor="sentinel2", scene_id="S3", cloud_pct=3.0),
    ]

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Nested:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    class _FakeDB:
        def __init__(self) -> None:
            self.step = 0

        def begin_nested(self):
            return _Nested()

        def execute(self, _stmt):
            self.step += 1
            return _Res(eventos if self.step == 1 else candidatos)

    barrier = threading.Barrier(3, timeout=3.0)

    def fetch(scene_id: str, _sensor: str, _region: dict[str, Any]) -> bytes:
        barrier.wait()
        if scene_id == "S2":
            time.sleep(0.01)
            raise RuntimeError("boom")
        return f"png:{scene_id}".encode("ascii")

    out = service.imagenes_eventos_ancla(
        _FakeDB(),  # type: ignore[arg-type]
        {"type": "Polygon", "coordinates": []},
        fetch_miniatura=fetch,
    )
    assert [row["event_key"] for row in out] == ["ev_1", "ev_2", "ev_3"]
    assert out[0]["png"] == b"png:S1"
    assert out[1]["png"] is None
    assert out[2]["png"] == b"png:S3"


def test_suelos_geometrias_clase_skips_empty_geometrycollection() -> None:
    empty_gc = '{"type": "GeometryCollection", "geometries": []}'
    valid_poly = (
        '{"type": "Polygon", "coordinates": [[[-62.1, -32.1], [-62.0, -32.1], '
        "[-62.0, -32.0], [-62.1, -32.0], [-62.1, -32.1]]]}"
    )
    fake_rows = [
        SimpleNamespace(clase="V", geo=empty_gc),
        SimpleNamespace(clase="III", geo=valid_poly),
    ]

    class _FakeDB:
        def begin_nested(self):
            class _CM:
                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return False

            return _CM()

        def execute(self, *_a, **_kw):
            return SimpleNamespace(all=lambda: fake_rows)

    clases = service.suelos_geometrias_clase(_FakeDB(), valid_poly)  # type: ignore[arg-type]
    assert clases is not None
    assert [c["clase"] for c in clases] == ["III"]
