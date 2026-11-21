"""Focused pure-python unit tests for the ``app.domains.geo.informe_area.kmz`` mutation target.

Exercises every branch (palette lookup, KML color byte reversal, polygon/line
placemarks, inner hole rings, MultiGeometry thresholds, camera LookAt clamping,
image stem sanitization, zip compression choices, radioFolder visibility, and XML
escaping) with zero DB or GDAL dependencies so cosmic-ray runs fast.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

from app.domains.geo.informe_area.kmz import (
    _ALPHA_RELLENO,
    _PALETA_SUELOS_EXTRA,
    KML_NS,
    PALETA_SUELOS,
    ClaseKmz,
    ImagenKmz,
    TemaKmz,
    _anillos,
    _bounds_geojson,
    _clave_imagen,
    _coord,
    _estilo_linea,
    _estilo_poligono,
    _kml_color,
    _look_at,
    _placemark_linea,
    _placemark_poligono,
    _poligonos,
    color_suelo,
    construir_kmz_informe,
)

_NS = f"{{{KML_NS}}}"
_EXTERIOR = [[-62.1, -32.1], [-62.0, -32.1], [-62.0, -32.0], [-62.1, -32.0], [-62.1, -32.1]]
_HOLE = [[-62.08, -32.08], [-62.02, -32.08], [-62.02, -32.02], [-62.08, -32.02], [-62.08, -32.08]]
_POLY_WITH_HOLE = {"type": "Polygon", "coordinates": [_EXTERIOR, _HOLE]}
_POLY_SIMPLE = {"type": "Polygon", "coordinates": [_EXTERIOR]}


def test_color_suelo_known_and_fallback_cycling() -> None:
    for numeral, expected in PALETA_SUELOS.items():
        assert color_suelo(numeral, 3) == expected
    assert len(PALETA_SUELOS) == 8
    assert color_suelo("IX", 0) == _PALETA_SUELOS_EXTRA[0]
    assert color_suelo("unknown", len(_PALETA_SUELOS_EXTRA) + 2) == _PALETA_SUELOS_EXTRA[2]


def test_kml_color_and_coord_formatting() -> None:
    assert _kml_color("#112233") == "ff332211"
    assert _kml_color("aabbcc", "b4") == "b4ccbbaa"
    assert _kml_color("#short", "aa") == "aa808080"
    assert _ALPHA_RELLENO == "b4"
    assert _coord(-62.12345678, -32.87654321) == "-62.1234568,-32.8765432"


def test_poligonos_and_anillos_variants() -> None:
    assert len(_poligonos(_POLY_WITH_HOLE)) == 1
    assert len(_anillos(_POLY_WITH_HOLE)) == 2
    multi = {"type": "MultiPolygon", "coordinates": [[_EXTERIOR], [_HOLE], []]}
    assert len(_poligonos(multi)) == 2
    assert len(_anillos(multi)) == 2
    assert _poligonos({"type": "Point", "coordinates": [-62.0, -32.0]}) == []
    assert _poligonos({"type": "MultiPolygon", "coordinates": None}) == []


def test_placemark_poligono_handles_holes_multigeometry_and_invalid_rings() -> None:
    # Single polygon with hole + invalid short hole ring + short coord tuple
    geom = {
        "type": "Polygon",
        "coordinates": [
            _EXTERIOR,
            _HOLE,
            [[-62.0, -32.0], [-62.1, -32.1]],  # < 4 vertices -> skipped
        ],
    }
    single_xml = _placemark_poligono("Clase & <A>", "st-1", [geom])
    assert "<name>Clase &amp; &lt;A&gt;</name>" in single_xml
    assert "<styleUrl>#st-1</styleUrl>" in single_xml
    assert "<tessellate>1</tessellate>" in single_xml
    assert "<MultiGeometry>" not in single_xml
    assert "<innerBoundaryIs>" in single_xml

    # Multiple polygons wrap in MultiGeometry
    multi_xml = _placemark_poligono("Multi", "st-2", [_POLY_SIMPLE, _POLY_SIMPLE])
    assert "<MultiGeometry>" in multi_xml

    # Exterior with fewer than 4 coords is skipped -> empty string
    short = {"type": "Polygon", "coordinates": [[[1.0, 2.0], [3.0, 4.0], [1.0]]]}
    assert _placemark_poligono("Empty", "st-3", [short]) == ""


def test_placemark_linea_handles_single_multi_and_short() -> None:
    single = _placemark_linea("Línea <1>", "l-1", [_POLY_SIMPLE])
    assert "<name>Línea &lt;1&gt;</name>" in single
    assert "<LineString><tessellate>1</tessellate>" in single
    assert "<MultiGeometry>" not in single

    multi = _placemark_linea("Líneas", "l-2", [_POLY_WITH_HOLE])
    assert "<MultiGeometry>" in multi

    too_short = {"type": "Polygon", "coordinates": [[[-62.0, -32.0]]]}
    assert _placemark_linea("Corta", "l-3", [too_short]) == ""


def test_styles_look_at_and_bounds() -> None:
    line_style = _estilo_linea("ls", "#112233", 3.2)
    assert '<Style id="ls">' in line_style
    assert "<color>ff332211</color>" in line_style
    assert "<width>3.2</width>" in line_style

    poly_style = _estilo_poligono("ps", "#112233")
    assert "<width>0.8</width>" in poly_style
    assert f"<color>{_ALPHA_RELLENO}332211</color>" in poly_style

    small = _look_at((-62.001, -32.001, -62.0, -32.0))
    assert "<range>2000</range>" in small
    assert "<longitude>-62.0005000</longitude>" in small
    assert "<latitude>-32.0005000</latitude>" in small
    assert "<altitude>0</altitude><range>2000</range><tilt>0</tilt><heading>0</heading>" in small

    wide = _look_at((-63.0, -33.0, -62.0, -32.0))
    assert "<range>2000</range>" not in wide

    minx, miny, maxx, maxy = _bounds_geojson([_POLY_SIMPLE])
    assert (minx, miny, maxx, maxy) == (-62.1, -32.1, -62.0, -32.0)


def test_clave_imagen_sanitization_and_truncation() -> None:
    assert _clave_imagen("Árbol Ñandú — 2025/09!", 0) == "arbol-nandu-2025-09-0"
    assert _clave_imagen("!!!", 2) == "imagen-2"
    long_title = "a" * 60
    assert _clave_imagen(long_title, 1) == f"{'a' * 40}-1"


def test_construir_kmz_informe_full_structure_radio_and_images() -> None:
    png_bytes = b"\x89PNG\r\n\x1a\nfake-png"
    kmz_bytes = construir_kmz_informe(
        nombre="Informe & <Test>",
        seleccion_geojson=_POLY_SIMPLE,
        subcuencas=[
            {"nombre": "Arroyo Litín", "geojson": _POLY_SIMPLE},
            {"geojson": _POLY_SIMPLE},  # default Subcuenca 2
            {"nombre": "Sin geo", "geojson": None},
        ],
        temas=[
            TemaKmz(titulo="Vacío", clases=[ClaseKmz(clase="X", color="#000000", geometrias=[])]),
            TemaKmz(
                titulo="Riesgo",
                clases=[ClaseKmz(clase="Alto", color="#ff0000", geometrias=[_POLY_SIMPLE])],
            ),
            TemaKmz(
                titulo="Drenaje",
                clases=[ClaseKmz(clase="Malo", color="#00ff00", geometrias=[_POLY_SIMPLE])],
            ),
        ],
        imagenes=[
            ImagenKmz(titulo="Evento S2", png=png_bytes, bounds=(-62.2, -32.2, -62.0, -32.0)),
        ],
    )

    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as zf:
        names = zf.namelist()
        assert names == ["doc.kml", "files/imagen-evento-s2-0.png"]
        assert zf.getinfo("doc.kml").compress_type == zipfile.ZIP_DEFLATED
        assert zf.getinfo("files/imagen-evento-s2-0.png").compress_type == zipfile.ZIP_STORED
        assert zf.read("files/imagen-evento-s2-0.png") == png_bytes
        root = ET.fromstring(zf.read("doc.kml").decode("utf-8"))

    doc = root.find(f"{_NS}Document")
    assert doc is not None
    assert doc.findtext(f"{_NS}name") == "Informe & <Test>"

    folders = doc.findall(f"{_NS}Folder")
    assert [f.findtext(f"{_NS}name") for f in folders] == [
        "Límite y subcuencas",
        "Temas del informe",
    ]

    limite_pms = [p.findtext(f"{_NS}name") for p in folders[0].findall(f"{_NS}Placemark")]
    assert limite_pms == ["Selección", "Arroyo Litín", "Subcuenca 2"]

    temas_folder = folders[1]
    assert temas_folder.findtext(f"{_NS}styleUrl") == "#temas-radio"
    child_folders = temas_folder.findall(f"{_NS}Folder")
    assert [(c.findtext(f"{_NS}name"), c.findtext(f"{_NS}visibility")) for c in child_folders] == [
        ("Riesgo", "1"),
        ("Drenaje", "0"),
        ("Evento S2", "0"),
    ]

    overlay = child_folders[2].find(f"{_NS}GroundOverlay")
    assert overlay is not None
    assert overlay.findtext(f"{_NS}Icon/{_NS}href") == "files/imagen-evento-s2-0.png"
    assert overlay.findtext(f"{_NS}LatLonBox/{_NS}north") == "-32.0000000"
    assert overlay.findtext(f"{_NS}LatLonBox/{_NS}west") == "-62.2000000"


def test_construir_kmz_informe_omits_empty_sections() -> None:
    empty_kmz = construir_kmz_informe(
        nombre="Solo raíz",
        seleccion_geojson={"type": "Polygon", "coordinates": []},
        subcuencas=[],
        temas=[],
        imagenes=None,
    )
    with zipfile.ZipFile(io.BytesIO(empty_kmz)) as zf:
        assert zf.namelist() == ["doc.kml"]
        root = ET.fromstring(zf.read("doc.kml").decode("utf-8"))
    doc = root.find(f"{_NS}Document")
    assert doc is not None
    assert doc.findall(f"{_NS}Folder") == []
