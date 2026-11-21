"""Deterministic seeded property/fuzz tests for pure parsers & validators.

Hermetic (stdlib ``random.Random`` only) so CI runs with ``--no-deps`` against
``requirements-dev.lock`` without needing ``hypothesis`` installed.
"""

from __future__ import annotations

import io
import math
import random
import re
import xml.etree.ElementTree as ET
import zipfile
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.domains.conocimiento.parser import body_offset, slugify
from app.domains.geo.ficha_errors import FichaError
from app.domains.geo.informe_area.kmz import (
    ClaseKmz,
    ImagenKmz,
    TemaKmz,
    _clave_imagen,
    _kml_color,
    construir_kmz_informe,
)
from app.domains.geo.informe_area.schemas import _validar_geometria
from app.domains.geo.schemas_ficha import _contar_vertices
from app.domains.padron.schemas import _normalize_cuit, validar_cuit
from app.domains.padron.service import PadronService

_SEED = 20261121
_KML_NS = "{http://www.opengis.net/kml/2.2}"
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _rand_text(rng: random.Random, max_len: int = 40) -> str:
    alphabet = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 áéíóúñÁÉÍÓÚÑ<>&\"'/-_\t"
    )
    length = rng.randint(0, max_len)
    return "".join(rng.choice(alphabet) for _ in range(length))


def _rand_polygon(rng: random.Random) -> dict[str, object]:
    cx = rng.uniform(-64.0, -61.0)
    cy = rng.uniform(-34.0, -31.0)
    n_sides = rng.randint(3, 12)
    ring: list[list[float]] = []
    for i in range(n_sides):
        angle = (2.0 * math.pi * i) / n_sides
        radius = rng.uniform(0.005, 0.05)
        ring.append(
            [round(cx + radius * math.cos(angle), 6), round(cy + radius * math.sin(angle), 6)]
        )
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def _rand_valid_cuit(rng: random.Random) -> str:
    prefix = rng.choice(["20", "23", "24", "27", "30", "33"])
    body = "".join(str(rng.randint(0, 9)) for _ in range(8))
    mults = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    while True:
        ten = prefix + body
        resto = sum(int(d) * m for d, m in zip(ten, mults)) % 11
        if resto == 0:
            dv = 0
            break
        if resto != 1:
            dv = 11 - resto
            break
        body = f"{(int(body) + 1) % 100_000_000:08d}"
    return f"{ten}{dv}"


def test_kmz_builder_always_produces_valid_xml_and_consistent_zip_entries() -> None:
    rng = random.Random(_SEED)
    for idx in range(100):
        seleccion = _rand_polygon(rng)
        temas = [
            TemaKmz(
                titulo=_rand_text(rng) or f"Tema {t}",
                clases=[
                    ClaseKmz(
                        clase=_rand_text(rng) or f"C{c}",
                        color=rng.choice(["#1a9850", "invalid", "#ff00aa", ""]),
                        geometrias=[_rand_polygon(rng) for _ in range(rng.randint(0, 2))],
                    )
                    for c in range(rng.randint(1, 3))
                ],
            )
            for t in range(rng.randint(0, 3))
        ]
        imagenes = [
            ImagenKmz(
                titulo=_rand_text(rng),
                png=_FAKE_PNG,
                bounds=(-63.0, -33.0, -62.5, -32.5),
            )
            for _ in range(rng.randint(0, 3))
        ]
        raw_kmz = construir_kmz_informe(
            nombre=_rand_text(rng) or f"Informe {idx}",
            seleccion_geojson=seleccion,
            subcuencas=[
                {"nombre": _rand_text(rng), "geojson": _rand_polygon(rng)}
                for _ in range(rng.randint(0, 2))
            ],
            temas=temas,
            imagenes=imagenes,
        )

        with zipfile.ZipFile(io.BytesIO(raw_kmz)) as zf:
            names = zf.namelist()
            assert names[0] == "doc.kml"
            assert zf.getinfo("doc.kml").compress_type == zipfile.ZIP_DEFLATED

            root = ET.fromstring(zf.read("doc.kml").decode("utf-8"))
            hrefs = [el.text for el in root.findall(f".//{_KML_NS}Icon/{_KML_NS}href") if el.text]
            assert len(hrefs) == len(imagenes)
            for href in hrefs:
                assert href in names
                assert zf.getinfo(href).compress_type == zipfile.ZIP_STORED

        clave = _clave_imagen(_rand_text(rng), idx)
        assert re.fullmatch(r"[a-z0-9-]+", clave)
        assert len(_kml_color(_rand_text(rng, 10))) == 8


def test_geojson_validators_never_crash_and_reject_adversarial_shapes() -> None:
    rng = random.Random(_SEED + 1)

    for _ in range(75):
        poly = _rand_polygon(rng)
        coords = poly["coordinates"]
        assert isinstance(coords, list)
        expected_vertices = len(coords[0])
        assert _contar_vertices(coords, "Polygon") == expected_vertices
        assert _validar_geometria(poly) == poly

    adversarial_cases = [
        {"type": "Point", "coordinates": [-62.5, -32.5]},
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[]]},
        {"type": "Polygon", "coordinates": [[[-62.0, -32.0], [-62.1, -32.0], [-62.0, -32.0]]]},
        {
            "type": "Polygon",
            "coordinates": [[[-62.0, -32.0], [-62.1, -32.0], [-62.1, -32.1], [-62.2, -32.2]]],
        },
        {
            "type": "Polygon",
            "coordinates": [[[181.0, -32.0], [-62.0, -32.0], [-62.0, -32.1], [181.0, -32.0]]],
        },
        {
            "type": "Polygon",
            "coordinates": [[[-62.0, -91.0], [-62.0, -32.0], [-62.1, -32.0], [-62.0, -91.0]]],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [["-62.0", "-32.0"], [-62.0, -32.1], [-62.1, -32.0], ["-62.0", "-32.0"]]
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [[[True, False], [-62.0, -32.1], [-62.1, -32.0], [True, False]]],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [float("nan"), -32.0],
                    [-62.0, -32.1],
                    [-62.1, -32.0],
                    [float("nan"), -32.0],
                ]
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [float("inf"), -32.0],
                    [-62.0, -32.1],
                    [-62.1, -32.0],
                    [float("inf"), -32.0],
                ]
            ],
        },
    ]

    for bad in adversarial_cases:
        with pytest.raises(FichaError) as err:
            _validar_geometria(bad)
        assert err.value.status_code == 422

    # Randomized vertex-cap violation must raise 422 FichaError.
    too_many = settings.informe_area_max_vertices + 10
    big_ring = [[-62.5 + 0.0001 * i, -32.5] for i in range(too_many - 1)]
    big_ring.append(list(big_ring[0]))
    with pytest.raises(FichaError) as exc:
        _validar_geometria({"type": "Polygon", "coordinates": [big_ring]})
    assert exc.value.status_code == 422


def test_padron_cuit_mod11_and_csv_parser_invariants() -> None:
    rng = random.Random(_SEED + 2)
    service = PadronService(repository=MagicMock())

    for _ in range(150):
        digits = _rand_valid_cuit(rng)
        assert validar_cuit(digits) is True
        formatted = _normalize_cuit(digits)
        assert formatted == f"{digits[:2]}-{digits[2:10]}-{digits[10:]}"
        assert _normalize_cuit(formatted) == formatted

        # Flipping any single digit across positions 0..10 must break mod-11 check (except 10==0 vs 1 impossible).
        pos = rng.randint(0, 10)
        alt_digit = str((int(digits[pos]) + rng.randint(1, 9)) % 10)
        mutated = digits[:pos] + alt_digit + digits[pos + 1 :]
        # Mod-11 non-zero weights (5,4,3,2,7,6,5,4,3,2, check) detect 100% of single-digit flips.
        assert validar_cuit(mutated) is False

    # Garbage CUITs must cleanly return False without crashing.
    for _ in range(75):
        s = _rand_text(rng, 25)
        only_digits = re.sub(r"\D", "", s)
        if len(only_digits) != 11:
            assert validar_cuit(s) is False

    # Fuzzed CSV streams (UTF-8 BOM, Latin-1, malformed quotes, ragged columns) never crash unexpectedly.
    csv_alphabet = "abcde,;\"'\n áéíóúñ0123456789"
    for i in range(100):
        raw_str = "".join(rng.choice(csv_alphabet) for _ in range(rng.randint(0, 120)))
        encoded = raw_str.encode("utf-8-sig" if i % 2 == 0 else "latin-1")
        parsed = service._parse_csv(encoded)
        assert isinstance(parsed, list)
        assert all(
            isinstance(row_num, int) and row_num >= 2 and isinstance(row, dict)
            for row_num, row in parsed
        )

    # Arbitrary CR-containing payloads parse cleanly now that _parse_csv passes newline="".
    cr_alphabet = csv_alphabet + "\r"
    for i in range(50):
        raw_str = "".join(rng.choice(cr_alphabet) for _ in range(rng.randint(0, 120)))
        encoded = raw_str.encode("utf-8-sig" if i % 2 == 0 else "latin-1")
        parsed = service._parse_csv(encoded)
        assert isinstance(parsed, list)


def test_conocimiento_markdown_parser_primitives_invariants() -> None:
    rng = random.Random(_SEED + 3)
    for _ in range(100):
        text = _rand_text(rng, 200)
        if rng.random() < 0.5:
            text = f"---\ntitulo: {_rand_text(rng, 20)}\n---\n{text}"
        offset = body_offset(text)
        assert 0 <= offset <= len(text)

        slug = slugify(_rand_text(rng, 60))
        assert re.fullmatch(r"([0-9a-z]+(-[0-9a-z]+)*)?", slug)
