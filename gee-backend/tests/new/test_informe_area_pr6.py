"""PR 6 — KMZ, paquete de campo, token público y QR (S3/S4/S5/S7/S8).

Three layers, same discipline as the PR 2/PR 4 suites:

* PURE builders (no db, no raster, no GEE): the KMZ's XML/zip contract
  (doc.kml first entry, one folder per theme, ``radioFolder`` group,
  LatLonBox matching the overlay bounds, parses as XML) and the package
  JSON's shape (clases vectorizadas por tema, límites, leyenda inline,
  basemap data-URL con bounds — and the >30 000 ha degradation that drops
  the basemap WITH a nota, never silently);
* the Celery task end-to-end over the seeded world (rasters + suelos
  IDECOR + anchor events with GEE mocked): ``completed`` with ``kmz_bytes``
  AND ``campo_paquete`` AND a ``token_publico`` that is NOT the informe id;
  the QR on the PDF cover (caption text + URL + vector-ops delta);
* the routes: ``/{id}/kmz`` keeps the PDF's privacy ladder; the PUBLIC
  ``/api/v2/public/campo/{token}`` answers without any auth, 404s the
  unknown/revoked/pending tokens with ONE body (no oracle), and 410s the
  expired one.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from sqlalchemy import delete, text
from sqlalchemy.orm import Session, sessionmaker

pypdf = pytest.importorskip("pypdf")

from app.auth.models import User, UserRole  # noqa: E402
from app.domains.geo.models import (  # noqa: E402
    EstadoGeoJob,
    FormatoGeoLayer,
    FuenteGeoLayer,
    GeoLayer,
    TipoGeoLayer,
)
from app.domains.geo.informe_area import kmz as kmz_export  # noqa: E402
from app.domains.geo.informe_area import service, tasks  # noqa: E402
from app.domains.geo.informe_area.models import InformeArea  # noqa: E402
from app.domains.geo.informe_area.repository import InformeAreaRepository  # noqa: E402
from app.domains.geo.informe_area.schemas import InformeAreaCreate  # noqa: E402
from app.shared.celery_outbox import CeleryTaskOutbox  # noqa: E402

INFORME_PATH = "/api/v2/geo/informes-area"
PUBLIC_CAMPO = "/api/v2/public/campo"

LON0, LAT0 = -61.5, -32.0
LADO = 0.05
NODATA = -9999.0
NS = "{http://www.opengis.net/kml/2.2}"

repo = InformeAreaRepository()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def factory(test_engine):
    return sessionmaker(bind=test_engine, expire_on_commit=False)


def _usuario(db: Session, email: str, role: UserRole = UserRole.OPERADOR) -> SimpleNamespace:
    row = User(
        email=email,
        hashed_password="test",
        role=role,
        nombre="T6",
        apellido="Campo",
        telefono="",
    )
    db.add(row)
    db.flush()
    return SimpleNamespace(id=row.id, role=role)


def _poligono(x0: float, y0: float, x1: float, y1: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
    }


# ── S3: the KMZ builder (pure) ───────────────────────────────────────────────


def test_kmz_estructura_zip_xml_y_radio_folder():
    """S3/S8: doc.kml first, one folder per theme, radioFolder group, XML ok."""
    temas = [
        kmz_export.TemaKmz(
            titulo="Riesgo hídrico",
            clases=[
                kmz_export.ClaseKmz(
                    clase="Alto",
                    color="#fc8d59",
                    geometrias=[_poligono(-62.0, -33.0, -61.95, -32.9)],
                ),
                kmz_export.ClaseKmz(
                    clase="Crítico",
                    color="#d73027",
                    geometrias=[_poligono(-61.95, -33.0, -61.9, -32.9)],
                ),
            ],
        ),
        kmz_export.TemaKmz(
            titulo="Necesidad de drenaje",
            clases=[
                kmz_export.ClaseKmz(
                    clase="Bajo",
                    color="#fff7ec",
                    geometrias=[_poligono(-62.0, -33.0, -61.9, -32.9)],
                )
            ],
        ),
    ]
    imagenes = [
        kmz_export.ImagenKmz(
            titulo=f"Imagen {fecha}", png=b"\x89PNG-fake", bounds=(-62.0, -33.0, -61.9, -32.9)
        )
        for fecha in ("2015-03-16", "2017-02-21", "2025-09-04")
    ]
    kmz = kmz_export.construir_kmz_informe(
        nombre="Informe & <test>",
        seleccion_geojson=_poligono(-62.0, -33.0, -61.9, -32.9),
        subcuencas=[{"nombre": "alpha", "geojson": _poligono(-62.0, -33.0, -61.95, -32.95)}],
        temas=temas,
        imagenes=imagenes,
    )

    # ── zip contract: KMZ magic + doc.kml as FIRST entry + one PNG per image
    assert kmz[:2] == b"PK"
    zf = zipfile.ZipFile(io.BytesIO(kmz))
    nombres = zf.namelist()
    assert nombres[0] == "doc.kml"
    assert sum(1 for n in nombres if n.endswith(".png")) == 3
    for entry in zf.infolist():
        if entry.filename.endswith(".png"):
            assert entry.compress_type == zipfile.ZIP_STORED

    # ── XML contract: parses, escaped name, radioFolder on the wrapper
    root = ET.fromstring(zf.read("doc.kml"))
    assert root.tag == f"{NS}kml"
    doc = root.find(f"{NS}Document")
    assert doc is not None and doc.find(f"{NS}name").text == "Informe & <test>"

    radios = [
        s
        for s in root.iter(f"{NS}Style")
        if s.find(f".//{NS}listItemType") is not None
        and s.find(f".//{NS}listItemType").text == "radioFolder"
    ]
    assert len(radios) == 1

    folders = {f.find(f"{NS}name").text: f for f in root.iter(f"{NS}Folder")}
    # One folder per theme (S3) + límites + the 3 imagery overlays.
    for esperado in (
        "Límite y subcuencas",
        "Temas del informe",
        "Riesgo hídrico",
        "Necesidad de drenaje",
        "Imagen 2015-03-16",
        "Imagen 2017-02-21",
        "Imagen 2025-09-04",
    ):
        assert esperado in folders, list(folders)

    # The radio group WRAPS the themes: the wrapper carries the styleUrl.
    wrapper = folders["Temas del informe"]
    assert wrapper.find(f"{NS}styleUrl").text == "#temas-radio"
    # Límites stays OUT of the radio group.
    assert folders["Límite y subcuencas"].find(f"{NS}styleUrl") is None

    # Exactly one THEME visible (radio), the imagery off by default.
    hijos = list(wrapper.findall(f"{NS}Folder"))
    visibles = [
        f.find(f"{NS}name").text
        for f in hijos
        if f.find(f"{NS}visibility") is not None and f.find(f"{NS}visibility").text == "1"
    ]
    assert visibles == ["Riesgo hídrico"]

    # Vectorized classes as polygons with the palette styles.
    poligonos = root.findall(f".//{NS}Polygon")
    assert len(poligonos) == 3  # 2 riesgo + 1 drenaje
    coordenadas = poligonos[0].find(f".//{NS}coordinates").text
    assert coordenada_valida(coordenadas)

    # GroundOverlay: LatLonBox matching the bounds + href that EXISTS in the zip.
    overlays = root.findall(f".//{NS}GroundOverlay")
    assert len(overlays) == 3
    box = overlays[0].find(f"{NS}LatLonBox")
    assert float(box.find(f"{NS}north").text) == pytest.approx(-32.9, abs=1e-6)
    assert float(box.find(f"{NS}west").text) == pytest.approx(-62.0, abs=1e-6)
    href = overlays[0].find(f".//{NS}href").text
    assert href in nombres, (href, nombres)


def coordenada_valida(texto: str) -> bool:
    primer = texto.split()[0]
    lon, lat = primer.split(",")[:2]
    return -180 < float(lon) < 180 and -90 < float(lat) < 90


# ── S4: the campo package builder (pure) ─────────────────────────────────────


def _temas_paquete() -> list[dict[str, Any]]:
    return [
        {
            "clave": "riesgo",
            "titulo": "Riesgo hídrico",
            "clases": [
                {
                    "clase": "Alto",
                    "color": "#fc8d59",
                    "geometrias": [_poligono(-62.0, -33.0, -61.9, -32.9)],
                }
            ],
        }
    ]


def test_paquete_campo_estructura_chica_con_basemap():
    """S4: JSON with vectorized classes + límites + leyenda + S2 basemap."""
    paquete = service.construir_paquete_campo(
        nombre="Informe cuenca",
        generado_el="2026-11-19T12:00:00+00:00",
        vence_at="2027-02-17T12:00:00+00:00",
        area_ha=5_000.0,
        seleccion_geojson=_poligono(-62.0, -33.0, -61.9, -32.9),
        subcuencas=[{"nombre": "alpha", "geojson": _poligono(-62.0, -33.0, -61.95, -32.95)}],
        temas=_temas_paquete(),
        basemap={
            "png": b"\x89PNG-fake",
            "bounds": (-62.0, -33.0, -61.9, -32.9),
            "fecha": "2025-09-04",
            "sensor": "sentinel2",
        },
    )
    assert paquete["version"] == 1
    assert paquete["limites"]["seleccion"]["type"] == "Polygon"
    assert paquete["limites"]["subcuencas"][0]["nombre"] == "alpha"
    tema = paquete["temas"]["riesgo"]
    assert tema["titulo"] == "Riesgo hídrico"
    clase = tema["clases"][0]
    assert clase["clase"] == "Alto" and clase["color"] == "#fc8d59"
    assert clase["geometrias"][0]["type"] == "Polygon"
    # Leyenda + imagen de fondo con bounds (S4 verbatim).
    assert paquete["basemap"]["imagen"].startswith("data:image/png;base64,")
    assert paquete["basemap"]["bounds"] == [-62.0, -33.0, -61.9, -32.9]
    assert paquete["basemap"]["sensor"] == "sentinel2"
    assert paquete["notas"] == []
    # Round-trips as the bytes the row stores.
    bytes_json = service.serializar_paquete_campo(paquete)
    assert json.loads(bytes_json)["nombre"] == "Informe cuenca"


def test_paquete_campo_area_grande_degrada_con_nota():
    """S4 degradation: > threshold drops the basemap AND SAYS so."""
    paquete = service.construir_paquete_campo(
        nombre="Informe grande",
        generado_el="2026-11-19T12:00:00+00:00",
        vence_at="2027-02-17T12:00:00+00:00",
        area_ha=service.AREA_CAMPO_BASEMAP_MAX_HA + 1.0,
        seleccion_geojson=_poligono(-62.0, -33.0, -61.0, -32.0),
        subcuencas=[],
        temas=_temas_paquete(),
        basemap={
            "png": b"\x89PNG-fake",
            "bounds": (-62.0, -33.0, -61.0, -32.0),
            "fecha": "2025-09-04",
            "sensor": "sentinel2",
        },
    )
    assert paquete["basemap"] is None
    assert any("sin imagen de fondo" in nota for nota in paquete["notas"])
    # The vectors survive the degradation — never a silent failure.
    assert paquete["temas"]["riesgo"]["clases"]

    # No basemap at all (GEE degraded): same honesty.
    sin_imagen = service.construir_paquete_campo(
        nombre="x",
        generado_el="2026-11-19T12:00:00+00:00",
        vence_at="2027-02-17T12:00:00+00:00",
        area_ha=10.0,
        seleccion_geojson=_poligono(-62.0, -33.0, -61.9, -32.9),
        subcuencas=[],
        temas=_temas_paquete(),
        basemap=None,
    )
    assert sin_imagen["basemap"] is None
    assert sin_imagen["notas"]


# ── seeding (PR 2's world + PR 4's anchor events) ───────────────────────────


def _seed_zona(db: Session, nombre: str, x0: float, y0: float) -> uuid.UUID:
    zona_id = uuid.uuid4()
    wkt = (
        f"POLYGON(({x0} {y0}, {x0 + LADO} {y0}, {x0 + LADO} {y0 + LADO}, "
        f"{x0} {y0 + LADO}, {x0} {y0}))"
    )
    db.execute(
        text(
            "INSERT INTO zonas_operativas (id, nombre, cuenca, geometria, superficie_ha) "
            "VALUES (:id, :nombre, 'cuenca-t6', ST_GeomFromText(:wkt, 4326), 0.0)"
        ),
        {"id": zona_id, "nombre": nombre, "wkt": wkt},
    )
    return zona_id


def _png_chico() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), (30, 120, 180)).save(buffer, format="PNG")
    return buffer.getvalue()


def _sembrar_mundo(db: Session, directorio: Any) -> dict[str, Any]:
    # suelos IDECOR (the migration's own DDL + one 'II' unit)
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS suelos_catastro ("
            "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "  simbolo VARCHAR(50) NOT NULL, cap VARCHAR(10), ip VARCHAR(50),"
            "  geometria GEOMETRY(MULTIPOLYGON, 4326) NOT NULL)"
        )
    )
    wkt_suelos = (
        f"MULTIPOLYGON((({LON0 - 0.02} {LAT0 - 0.02}, {LON0 + 0.2} {LAT0 - 0.02}, "
        f"{LON0 + 0.2} {LAT0 + 0.09}, {LON0 - 0.02} {LAT0 + 0.09}, "
        f"{LON0 - 0.02} {LAT0 - 0.02})))"
    )
    from app.db.migrations.versions import zz_idecor_suelos_50mil as migracion_suelos

    for statement in migracion_suelos.UPGRADE_STATEMENTS:
        db.execute(text(statement))
    db.execute(
        text(
            "INSERT INTO idecor_suelos_50mil "
            "(id, simbolo, cu, clase, ip, au_1m, au_2m, serie_1, porc_1, nombre, "
            " tipo_unida, pdf_simbolo, pdf_serie_1, geometria) "
            "VALUES (9002, 'T6U', 'IIc', 'II', 90, 158, 292, 'SERIE T6', 100, "
            "        'Consociación SERIE T6', 'Consociación', 'T6U', 'SERIE_T6', "
            "        ST_GeomFromText(:wkt, 4326))"
        ),
        {"wkt": wkt_suelos},
    )

    # class rasters: constant values → one class each (Crítico / Alto)
    flood = str(directorio / "flood_t6.tif")
    drain = str(directorio / "drain_t6.tif")
    for ruta, valor in ((flood, 80.0), (drain, 60.0)):
        with rasterio.open(
            ruta,
            "w",
            driver="GTiff",
            height=200,
            width=260,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(LON0 - 0.05, LAT0 + 0.06, 0.001, 0.001),
            nodata=NODATA,
        ) as dst:
            dst.write(np.full((200, 260), valor, dtype="float32"), 1)
        db.add(
            GeoLayer(
                nombre=f"t6-{ruta}",
                tipo=TipoGeoLayer.FLOOD_RISK if "flood" in ruta else TipoGeoLayer.DRAINAGE_NEED,
                fuente=FuenteGeoLayer.MANUAL,
                archivo_path=ruta,
                formato=FormatoGeoLayer.GEOTIFF,
                srid=4326,
            )
        )

    # composite + precip normals (the desglose + lluvia sections)
    zona_a = _seed_zona(db, "alpha", LON0, LAT0)
    zona_b = _seed_zona(db, "beta", LON0 + LADO, LAT0)
    for zona in (zona_a, zona_b):
        for tipo in ("flood_risk", "drainage_need"):
            db.execute(
                text(
                    "INSERT INTO composite_zonal_stats "
                    "(id, zona_id, tipo, fecha_calculo, mean_score, max_score, p90_score, "
                    " area_high_risk_ha, ha_alto, ha_critico) "
                    "VALUES (:id, :z, :t, CURRENT_DATE, 50, 90, 70, 2600, 1820, 780)"
                ),
                {"id": uuid.uuid4(), "z": zona, "t": tipo},
            )
    precip = str(directorio / "precip_t6.tif")
    with rasterio.open(
        precip,
        "w",
        driver="GTiff",
        height=40,
        width=40,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(-63.0, -31.0, 0.05, 0.05),
        nodata=NODATA,
    ) as dst:
        dst.write(np.full((40, 40), 100.0, dtype="float32"), 1)
    for mes in [*range(1, 13), "anual"]:
        db.add(
            GeoLayer(
                nombre=f"t6-precip-{mes}",
                tipo=TipoGeoLayer.PRECIP_NORMAL,
                fuente=FuenteGeoLayer.MANUAL,
                archivo_path=precip,
                formato=FormatoGeoLayer.GEOTIFF,
                srid=4326,
                metadata_extra={"mes": mes, "version": "2026-01-01T00:00:00+00:00"},
                area_id="consorcio",
            )
        )

    # anchor events (2015 L8, 2017 S2, 2025 S2) with rank-1 candidates
    payloads = {
        "mar_2015": ("2015-03-15", "landsat8", "LANDSAT/LC08_C02_T1_TOA/LC08_T6"),
        "feb_2017": ("2017-02-20", "sentinel2", "COPERNICUS/S2_SR_HARMONIZED/2017T6"),
        "sep_2025": ("2025-09-05", "sentinel2", "COPERNICUS/S2_SR_HARMONIZED/2025T6"),
    }
    for event_key, (fecha, sensor, escena) in payloads.items():
        db.execute(
            text(
                "INSERT INTO rainfall_extreme_event "
                "(id, source_id, scope_kind, scope_id, scope_version, detector_revision, "
                " provenance, event_key, start_date, end_date, curated_payload) "
                "VALUES (gen_random_uuid(), 'chirps-v3-final', 'provider_asset', "
                "        'zona_cc_ampliada', 'v1', 'curated', 'curated', :k, "
                "        CAST(:d AS date), CAST(:d AS date), "
                "        CAST(:p AS json))",
            ),
            {"k": event_key, "d": fecha, "p": json.dumps({"name": f"Evento {event_key}"})},
        )
        db.execute(
            text(
                "INSERT INTO rainfall_event_imagery_candidate "
                "(id, event_key, scorer_revision, sensor, scene_id, scene_date, "
                " days_from_peak, cloud_pct, cloud_basis, score, rank, visualization, slot) "
                "VALUES (gen_random_uuid(), :k, 't6', :s, :sc, CAST(:d AS date), "
                "        0, 5, 'scene', 99.0, 1, 'falso_color', 'ranked')"
            ),
            {"k": event_key, "s": sensor, "sc": escena, "d": fecha},
        )
    db.commit()
    return {"zona_a": zona_a, "zona_b": zona_b, "rasters": {flood, drain, precip}}


def _limpiar(factory, *, usuario_id, zona_ids, informe_ids, rasters) -> None:
    with factory() as db:
        db.execute(
            delete(CeleryTaskOutbox).where(CeleryTaskOutbox.task_key == "geo.informe_area.generar")
        )
        db.execute(
            delete(InformeArea).where(
                InformeArea.id.in_(informe_ids) | (InformeArea.usuario_id == usuario_id)
            )
        )
        db.execute(delete(GeoLayer).where(GeoLayer.archivo_path.in_(rasters)))
        db.execute(
            text("DELETE FROM composite_zonal_stats WHERE zona_id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(z) for z in zona_ids]},
        )
        db.execute(
            text("DELETE FROM zonas_operativas WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": [str(z) for z in zona_ids]},
        )
        db.execute(text("DROP TABLE IF EXISTS idecor_suelos_50mil"))
        db.execute(
            text("DELETE FROM rainfall_event_imagery_candidate WHERE scorer_revision = 't6'")
        )
        db.execute(
            text(
                "DELETE FROM rainfall_extreme_event WHERE provenance = 'curated' "
                "AND event_key IN ('mar_2015', 'feb_2017', 'sep_2025')"
            )
        )
        if usuario_id is not None:
            db.execute(delete(User).where(User.id == usuario_id))
        db.commit()


def _app_privada(db: Session, usuario: Any) -> Any:
    from fastapi import FastAPI

    from app.auth.dependencies import current_active_user
    from app.db.session import get_db
    from app.domains.geo.ficha_errors import install_ficha_error_handler
    from app.domains.geo.informe_area.errors import install_informe_area_error_handler
    from app.domains.geo.router import router as geo_router

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    install_ficha_error_handler(app)
    install_informe_area_error_handler(app)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_active_user] = lambda: usuario
    return app


def _app_publica(db: Session) -> Any:
    """NO auth override on purpose — the campo route must stand alone (S5)."""
    from fastapi import FastAPI

    from app.db.session import get_db
    from app.domains.geo.informe_area.errors import install_informe_area_error_handler
    from app.domains.geo.informe_area.router import public_router as campo_router

    app = FastAPI()
    app.include_router(campo_router, prefix="/api/v2/public")
    install_informe_area_error_handler(app)
    app.dependency_overrides[get_db] = lambda: db
    return app


# ── the task end-to-end: KMZ + paquete + token + QR (S3/S4/S5/S7) ────────────


def test_tarea_genera_kmz_paquete_token_y_qr(factory, tmp_path, monkeypatch):
    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)
    monkeypatch.setattr(service, "_miniatura_por_defecto", lambda *_a: _png_chico())

    usuario_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    rasters: set[str] = set()
    try:
        with factory() as db:
            mundo = _sembrar_mundo(db, tmp_path)
            zona_ids = [mundo["zona_a"], mundo["zona_b"]]
            rasters = mundo["rasters"]
            usuario = _usuario(db, f"informe-t6-{uuid.uuid4().hex[:8]}@test.local")
            db.commit()
            usuario_id = usuario.id

            row, desde_cache = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe cuenca t6", zona_ids=zona_ids),
                usuario_id=usuario_id,
            )
            assert desde_cache is False
            informe_ids.append(row.id)
            # S5: the token exists from CREATE, is opaque and is NOT the id.
            assert row.token_publico
            assert row.token_publico != str(row.id)
            assert all(c.isalnum() or c in "-_" for c in row.token_publico)

        assert tasks.generar_informe_area(str(informe_ids[0]))["estado"] == "completed"

        with factory() as db:
            fila = db.get(InformeArea, informe_ids[0])
            assert fila.estado == EstadoGeoJob.COMPLETED
            assert fila.kmz_bytes and fila.campo_paquete

            # ── KMZ: real zip, doc.kml parses, one folder per theme (S8).
            zf = zipfile.ZipFile(io.BytesIO(bytes(fila.kmz_bytes)))
            assert zf.namelist()[0] == "doc.kml"
            root = ET.fromstring(zf.read("doc.kml"))
            nombres = [f.find(f"{NS}name").text for f in root.iter(f"{NS}Folder")]
            assert "Riesgo hídrico" in nombres
            assert "Necesidad de drenaje" in nombres
            assert "Suelos (IDECOR 1:50.000)" in nombres
            assert sum("Imagen" in (n or "") for n in nombres) == 3
            assert any(
                (
                    s.find(f".//{NS}listItemType") is not None
                    and s.find(f".//{NS}listItemType").text == "radioFolder"
                )
                for s in root.iter(f"{NS}Style")
            )
            overlays = root.findall(f".//{NS}GroundOverlay")
            assert len(overlays) == 3

            # ── paquete: the JSON contract, basemap from the 2025 S2 scene.
            paquete = json.loads(bytes(fila.campo_paquete))
            assert paquete["version"] == 1
            assert set(paquete["temas"]) == {"riesgo", "drenaje", "suelos"}
            clases_riesgo = paquete["temas"]["riesgo"]["clases"]
            assert clases_riesgo_validas(clases_riesgo)
            assert paquete["basemap"]["sensor"] == "sentinel2"
            assert paquete["basemap"]["imagen"].startswith("data:image/png;base64,")
            assert paquete["limites"]["subcuencas"][0]["nombre"] in ("alpha", "beta")

            # ── resultado carries the campo pointer for the UI (S5).
            campo = fila.resultado["campo"]
            assert campo["token"] == fila.token_publico
            assert f"/campo/{fila.token_publico}" in campo["url"]
            assert campo["paquete_bytes"] == len(fila.campo_paquete)
            assert campo["basemap"] is True

            # ── QR on the cover (S7): caption + plain URL in the text layer,
            #    and the QR's vector ops really grew page 1 (image count is
            #    useless — QrCodeWidget draws rectangles, not an image).
            lector = pypdf.PdfReader(io.BytesIO(bytes(fila.pdf_bytes)))
            texto_pag1 = lector.pages[0].extract_text() or ""
            assert "Mapa de campo" in texto_pag1
            assert fila.token_publico in texto_pag1
            stream_con_qr = len(lector.pages[0].get_contents().get_data())

            # Same cover WITHOUT the campo_url: the delta IS the QR's rects
            # (QrCodeWidget draws vector fills — page.images stays empty).
            from app.shared.pdf.base import get_branding
            from app.shared.pdf.builders_informe_area import build_informe_area_pdf

            pdf_sin = build_informe_area_pdf(
                {"nombre": fila.nombre, "generado_el": "2026-11-19T12:00:00+00:00"},
                get_branding(db),
                mapas={},
            ).getvalue()
            lector_sin = pypdf.PdfReader(io.BytesIO(pdf_sin))
            stream_sin_qr = len(lector_sin.pages[0].get_contents().get_data())
            assert stream_con_qr > stream_sin_qr + 2_000  # the QR's rects

            print(
                f"\nS9 (box local): kmz={len(fila.kmz_bytes) / 1024:.0f} KiB "
                f"paquete={len(fila.campo_paquete) / 1024:.0f} KiB "
                f"pdf={len(fila.pdf_bytes) / 1024:.0f} KiB"
            )
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
            rasters=rasters,
        )


def clases_riesgo_validas(clases: list[dict[str, Any]]) -> bool:
    """Constant-80 raster → exactly one class, Crítico, palette color."""
    return (
        len(clases) == 1
        and clases[0]["clase"] == "Crítico"
        and clases[0]["color"] == "#d73027"
        and clases[0]["geometrias"]
    )


# ── S5: the PUBLIC route ─────────────────────────────────────────────────────


def test_ruta_publica_campo_sin_auth(factory, tmp_path, monkeypatch):
    """200 + JSON for the token; 404 unknown/revoked; 410 vencido; no auth."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)
    monkeypatch.setattr(service, "_miniatura_por_defecto", lambda *_a: _png_chico())

    usuario_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    rasters: set[str] = set()
    try:
        with factory() as db:
            mundo = _sembrar_mundo(db, tmp_path)
            zona_ids = [mundo["zona_a"], mundo["zona_b"]]
            rasters = mundo["rasters"]
            usuario = _usuario(db, f"informe-t6-pub-{uuid.uuid4().hex[:8]}@test.local")
            db.commit()
            usuario_id = usuario.id
            row, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe público", zona_ids=zona_ids),
                usuario_id=usuario_id,
            )
            informe_ids.append(row.id)
            token = row.token_publico

        assert tasks.generar_informe_area(str(row.id))["estado"] == "completed"

        with factory() as db:
            cliente = TestClient(_app_publica(db))
            # Unknown token → the ONE 404 body (no oracle).
            rs = cliente.get(f"{PUBLIC_CAMPO}/no-existe")
            assert rs.status_code == 404
            assert rs.json()["codigo"] == "campo_no_encontrado"
            # The real one → the stored package, JSON, without any auth.
            rs = cliente.get(f"{PUBLIC_CAMPO}/{token}")
            assert rs.status_code == 200
            assert rs.headers["content-type"].startswith("application/json")
            paquete = rs.json()
            assert paquete["temas"]["riesgo"]["titulo"] == "Riesgo hídrico"
            # No usuario data beyond the informe's own nombre/fecha (S5).
            assert "usuario" not in paquete
            assert paquete["nombre"] == "Informe público"

            # Pending row → the same 404 (the map does not exist YET). A
            # DIFFERENT selection: the same one would hit the S4 cache and
            # hand back the completed row above.
            fila_pendiente, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Pendiente", zona_ids=[zona_ids[0]]),
                usuario_id=usuario_id,
            )
            informe_ids.append(fila_pendiente.id)
            rs = cliente.get(f"{PUBLIC_CAMPO}/{fila_pendiente.token_publico}")
            assert rs.status_code == 404

            # Vencido → 410 (the phone deserves "expired", not "missing").
            fila = db.get(InformeArea, row.id)
            fila.vence_at = fila.vence_at.replace(year=fila.vence_at.year - 1)
            db.commit()
            rs = cliente.get(f"{PUBLIC_CAMPO}/{token}")
            assert rs.status_code == 410
            assert rs.json()["codigo"] == "campo_vencido"

        # Deleted row (the retention sweep) → 404: deletion revokes (S10).
        with factory() as db:
            db.execute(delete(InformeArea).where(InformeArea.id == row.id))
            db.commit()
            cliente = TestClient(_app_publica(db))
            assert cliente.get(f"{PUBLIC_CAMPO}/{token}").status_code == 404
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
            rasters=rasters,
        )


# ── S3: the KMZ download keeps the PDF's privacy ladder ─────────────────────


def test_kmz_endpoint_privacidad(factory, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(service, "try_publish_celery_task", lambda _id: False)
    monkeypatch.setattr(service, "_miniatura_por_defecto", lambda *_a: _png_chico())

    usuario_id = otro_id = admin_id = None
    zona_ids: list[uuid.UUID] = []
    informe_ids: list[uuid.UUID] = []
    rasters: set[str] = set()
    try:
        with factory() as db:
            mundo = _sembrar_mundo(db, tmp_path)
            zona_ids = [mundo["zona_a"], mundo["zona_b"]]
            rasters = mundo["rasters"]
            creador = _usuario(db, f"informe-t6-kmz-{uuid.uuid4().hex[:8]}@test.local")
            otro = _usuario(db, f"informe-t6-otro-{uuid.uuid4().hex[:8]}@test.local")
            admin = _usuario(
                db, f"informe-t6-adm-{uuid.uuid4().hex[:8]}@test.local", UserRole.ADMIN
            )
            db.commit()
            usuario_id, otro_id, admin_id = creador.id, otro.id, admin.id
            row, _ = service.crear_informe(
                db,
                InformeAreaCreate(nombre="Informe kmz", zona_ids=zona_ids),
                usuario_id=creador.id,
            )
            informe_ids.append(row.id)

        assert tasks.generar_informe_area(str(row.id))["estado"] == "completed"

        with factory() as db:
            esperado = bytes(db.get(InformeArea, row.id).kmz_bytes)

        with factory() as db:
            cliente = TestClient(
                _app_privada(db, SimpleNamespace(id=usuario_id, role=UserRole.OPERADOR))
            )
            rs = cliente.get(f"{INFORME_PATH}/{row.id}/kmz")
            assert rs.status_code == 200, rs.content[:200]
            assert rs.headers["content-type"].startswith("application/vnd.google-earth.kmz")
            assert rs.headers["content-disposition"].startswith("attachment")
            assert rs.headers["content-disposition"].endswith(".kmz")
            assert rs.content == esperado

        with factory() as db:
            cliente = TestClient(
                _app_privada(db, SimpleNamespace(id=otro_id, role=UserRole.OPERADOR))
            )
            # Same 404 as a missing id — privacy (S11).
            assert cliente.get(f"{INFORME_PATH}/{row.id}/kmz").status_code == 404
            assert cliente.get(f"{INFORME_PATH}/{uuid.uuid4()}/kmz").status_code == 404

        with factory() as db:
            cliente = TestClient(
                _app_privada(db, SimpleNamespace(id=admin_id, role=UserRole.ADMIN))
            )
            assert cliente.get(f"{INFORME_PATH}/{row.id}/kmz").status_code == 200
    finally:
        _limpiar(
            factory,
            usuario_id=usuario_id,
            zona_ids=zona_ids,
            informe_ids=informe_ids,
            rasters=rasters,
        )
