"""Regression tests for Wave 5 W-INF-03, S-01 PDF/Mapas/PROJ, and composite NaNs."""

from __future__ import annotations

import io
import math
import uuid
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from PIL import Image as PILImage
from rasterio.transform import from_origin
from shapely.geometry import box
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.domains.geo import ficha_errors, ficha_service
from app.domains.geo.composites import extract_composite_zonal_stats
from app.domains.geo.informe_area.mapas import render_mapa_ubicacion
from app.shared.pdf.base import BrandingInfo
from app.shared.pdf.builders_informe_area import build_informe_area_pdf

pypdf = pytest.importorskip("pypdf")


def test_pdf_escapes_untrusted_xml_and_prints_correct_section3_note_and_full_tables() -> None:
    desglose = [
        {
            "zona_id": str(uuid.UUID(int=i + 1)),
            "nombre": f"Subcuenca <{i + 1}> & norte",
            "cuenca": "Cuenca <A&B>",
            "ha": float(1000 - i * 10),
            "pct_alto_critico": 12.5,
            "pct_drenaje_alto_critico": 8.0,
        }
        for i in range(10)
    ]
    cobertura_por_zona = {
        row["zona_id"]: {"pct_cultivo": 40.0, "pct_soja": 25.0} for row in desglose
    }
    suelos_por_zona = {
        row["zona_id"]: {
            "clase_dominante": "IV <w&s>",
            "ip_ponderado": 72.0,
            "cobertura_pct": 95.0,
        }
        for row in desglose
    }
    canales_por_zona = {
        row["zona_id"]: {
            "km_relevados": 1.2,
            "km_propuestos": 0.3,
            "km_total": 1.5,
            "km_por_mil_ha": 1.8,
        }
        for row in desglose
    }

    datos: dict[str, Any] = {
        "nombre": "Informe <Especial> & Prueba",
        "generado_el": "2026-11-21T12:00:00+00:00",
        "area_ha": 5000.0,
        "cantidad_zonas": 10,
        "cuencas": ["Cuenca <A&B>", "Cuenca Sur & Oeste"],
        "campo_url": "https://example.test/campo/tok?foo=1&bar=<2>",
        "umbral_alto_critico": "leyenda-55",
        "riesgo": {
            "cobertura": "total",
            "cobertura_ratio": 1.0,
            "area_ha": 5000.0,
            "pixel_count": 100,
            "clases": [
                {"clase": "Bajo", "ha": 2500.0, "pct": 50.0},
                {"clase": "Medio", "ha": 1500.0, "pct": 30.0},
                {"clase": "Alto", "ha": 700.0, "pct": 14.0},
                {"clase": "Crítico", "ha": 300.0, "pct": 6.0},
            ],
        },
        "drenaje": {
            "cobertura": "total",
            "cobertura_ratio": 1.0,
            "area_ha": 5000.0,
            "pixel_count": 100,
            "clases": [
                {"clase": "Bajo", "ha": 3000.0, "pct": 60.0},
                {"clase": "Medio", "ha": 1200.0, "pct": 24.0},
                {"clase": "Alto", "ha": 500.0, "pct": 10.0},
                {"clase": "Crítico", "ha": 300.0, "pct": 6.0},
            ],
        },
        "riesgo_validacion": {
            "eventos": [
                {
                    "evento_key": "ev_2025_<1&2>",
                    "fecha": "2025-09-05",
                    "sensor": "sentinel2 & L8",
                    "clases": {"Alto": {"pct_con_agua": 44.0}},
                    "lluvia_30d_mm": 120.0,
                }
            ]
        },
        "suelos": {
            "cobertura": "total",
            "cobertura_ratio": 1.0,
            "area_ha": 5000.0,
            "ip_ponderado": 72.0,
            "unidades": [
                {
                    "simbolo": "S<1>",
                    "series": "Serie A & B",
                    "clase": "III",
                    "ip": 72,
                    "au_1m": 150,
                    "au_2m": 280,
                    "ha": 5000.0,
                    "pct": 100.0,
                }
            ],
            "por_zona": suelos_por_zona,
        },
        "cobertura": {
            "cobertura": "total",
            "cobertura_ratio": 1.0,
            "clases": [
                {"clase": "16 - Cultivo <anual> & pasto", "ha": 4000.0, "pct": 80.0},
            ],
            "pct_agua_estacional": 2.0,
            "etiqueta_agua_estacional": "9 - Agua <estacional> & bañados",
            "campanias": [
                {
                    "campania": "2024/2025 & <test>",
                    "clases": [{"clase": "Soja <1>", "ha": 3000.0, "pct": 60.0}],
                    "ha_cultivo": 3000.0,
                    "pct_cultivo": 60.0,
                }
            ],
            "por_zona": cobertura_por_zona,
        },
        "canales": {
            "km_relevados": 12.0,
            "km_propuestos": 3.0,
            "km_total": 15.0,
            "cruces_total": 1,
            "conflictos_total": 0,
            "por_zona": canales_por_zona,
        },
        "imagenes": [
            {
                "event_key": "ev_1",
                "nombre": "Lluvia <Fuerte> & Sur",
                "fecha": "2025-09-05",
                "sensor": "sentinel2 & optical",
                "nubes_pct": 5.0,
                "png": None,
                "escena": "COPERNICUS/S2&SCENE<1>",
            }
        ],
        "desglose": desglose,
    }

    pdf_buf = build_informe_area_pdf(
        datos,
        BrandingInfo(
            nombre_organizacion="Consorcio Canalero",
            logo_path=None,
            color_primario="#1976D2",
        ),
        mapas={},
    )
    reader = pypdf.PdfReader(io.BytesIO(pdf_buf.getvalue()))
    texto = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalizado = " ".join(texto.split())

    assert "Alto 50–70 y Crítico 70–100" in normalizado
    assert "Subcuenca <10> & norte" in normalizado
    assert normalizado.count("Subcuenca <10> & norte") >= 5
    assert normalizado.count("Detalle completo (10 subcuencas):") >= 4
    assert "secciones 2, 3, 4, 5, 6 y 7" in normalizado


def test_ficha_zonas_ignores_legacy_rows_without_ha_alto_and_critico(db: Any) -> None:
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS suelos_catastro ("
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  simbolo VARCHAR(50) NOT NULL,"
            "  cap VARCHAR(10),"
            "  ip VARCHAR(50),"
            "  geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL)"
        )
    )
    zona_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, 'Zona Legacy 70', 'cuenca-leg', "
            "ST_GeomFromText('POLYGON((-62.3 -32.3, -62.29 -32.3, -62.29 -32.29, -62.3 -32.29, -62.3 -32.3))', 4326), "
            "105.0)"
        ),
        {"id": str(zona_id)},
    )
    db.execute(
        text(
            "INSERT INTO composite_zonal_stats "
            "(id, zona_id, tipo, fecha_calculo, mean_score, max_score, p90_score, "
            " area_high_risk_ha, ha_alto, ha_critico) "
            "VALUES (:id, :zid, 'flood_risk', CURRENT_DATE, 40.0, 80.0, 60.0, 35.0, NULL, NULL)"
        ),
        {"id": uuid.uuid4(), "zid": zona_id},
    )
    db.flush()

    zona = ficha_service.ZonaResuelta(
        zona_id=zona_id,
        nombre="Zona Legacy 70",
        cuenca="cuenca-leg",
        ha=105.0,
        g4326="{}",
    )
    desglose, _tag = ficha_service._desglose_zonas(db, [zona])
    assert len(desglose) == 1
    assert desglose[0].pct_alto_critico is None


def test_traducir_fallas_db_maps_proj_transform_error_to_422() -> None:
    orig = SimpleNamespace(sqlstate="XX000")
    exc = OperationalError(
        "SELECT ST_Transform(...)",
        {},
        Exception("transform: latitude or longitude exceeded limits"),
    )
    exc.orig = orig

    with pytest.raises(ficha_errors.FichaError) as exc_info:
        with ficha_service._traducir_fallas_db():
            raise exc
    assert exc_info.value.status_code == 422
    assert exc_info.value.codigo == "geometria_invalida"


def test_extract_composite_zonal_stats_ignores_nan_pixels(tmp_path) -> None:
    ruta = str(tmp_path / "nan_composite.tif")
    arr = np.array(
        [
            [20.0, np.nan, 60.0],
            [np.nan, 80.0, np.nan],
        ],
        dtype="float32",
    )
    with rasterio.open(
        ruta,
        "w",
        driver="GTiff",
        height=2,
        width=3,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-62.0, -32.0, 0.001, 0.001),
        nodata=None,
    ) as dst:
        dst.write(arr, 1)

    zona_geom = box(-62.0, -32.002, -61.997, -32.0).__geo_interface__
    results = extract_composite_zonal_stats(
        ruta,
        [{"id": uuid.uuid4(), "geometry": zona_geom}],
        "flood_risk",
    )
    assert len(results) == 1
    row = results[0]
    assert math.isfinite(row["mean_score"])
    assert row["max_score"] == 80.0
    assert row["mean_score"] == pytest.approx((20.0 + 60.0 + 80.0) / 3.0, abs=0.02)


def test_render_mapa_ubicacion_applies_latitude_cosine_aspect() -> None:
    # 1 deg lon x 1 deg lat centered near -33 deg: cos(-33) ~ 0.8387, so height > width.
    geom = box(-62.5, -33.5, -61.5, -32.5).__geo_interface__
    png = render_mapa_ubicacion(geom, [])
    assert png is not None
    img = PILImage.open(io.BytesIO(png))
    assert img.height > img.width
