"""Tests for the CDATA description parser.

The KMZ stores ALL per-school metadata inside an HTML-ish CDATA blob that
looks like:

    <b>Escuela …</b><br/>
    <b>CUE:</b> 140173000<br/>              ← IGNORED (burocratic)
    <b>Localidad:</b> Monte Leña<br/>       ← PARSED
    <b>Departamento:</b> Unión<br/>         ← IGNORED (burocratic)
    <b>Ámbito:</b> Rural Aglomerado<br/>    ← PARSED
    <b>Nivel:</b> Inicial · Primario<br/>   ← PARSED (middot preserved inside value)
    <b>Sector:</b> Estatal<br/>             ← IGNORED (burocratic)
    <b>Directivo:</b> ...<br/>              ← IGNORED (PII)
    <b>Teléfono:</b> ...<br/>               ← IGNORED (PII)
    <b>Email:</b> ...<br/>                  ← IGNORED (PII)

Per spec REQ-ESC-2 + REQ-ESC-11, the parser MUST return EXACTLY 3 keys
(``localidad``, ``ambito``, ``nivel``). The 4th operational field
(``nombre``) comes from the KML ``<name>`` element, not from the CDATA.
"""

from __future__ import annotations

import pytest

from scripts.etl_escuelas.parse import parse_description


SAMPLE_CDATA_AGLOMERADO = """
<b>Escuela Joaquín Víctor González</b><br/>
<b>CUE:</b> 140173000<br/>
<b>Localidad:</b> Monte Leña<br/>
<b>Departamento:</b> Unión<br/>
<b>Ámbito:</b> Rural Aglomerado<br/>
<b>Nivel:</b> Inicial · Primario<br/>
<b>Sector:</b> Estatal<br/>
<b>Directivo:</b> Barbero, Norma Magdalena<br/>
<b>Teléfono:</b> (03537) 15654790<br/><b>Email:</b> torner20@hotmail.com<br/>
"""

SAMPLE_CDATA_DISPERSO = """
<b>Escuela Presidente Santiago Derqui</b><br/>
<b>CUE:</b> 140173300<br/>
<b>Localidad:</b> Colonia Marcos Sastre<br/>
<b>Ámbito:</b> Rural Disperso<br/>
<b>Nivel:</b> Primario<br/>
<b>Directivo:</b> Moyano, Stella Maris<br/>
<b>Teléfono:</b> (03537) 15335211<br/>
"""


class TestParseDescriptionExtractsRequiredFields:
    def test_parse_cdata_extracts_localidad(self) -> None:
        parsed = parse_description(SAMPLE_CDATA_AGLOMERADO)
        assert parsed["localidad"] == "Monte Leña"

    def test_parse_cdata_extracts_ambito(self) -> None:
        parsed = parse_description(SAMPLE_CDATA_AGLOMERADO)
        assert parsed["ambito"] == "Rural Aglomerado"

    def test_parse_cdata_extracts_nivel_with_middot_separator(self) -> None:
        # The `·` (U+00B7) inside "Inicial · Primario" is VALUE content,
        # NOT a field separator — the parser splits on <br/>, not on ·.
        parsed = parse_description(SAMPLE_CDATA_AGLOMERADO)
        assert parsed["nivel"] == "Inicial · Primario"

    def test_parse_cdata_extracts_simple_nivel(self) -> None:
        parsed = parse_description(SAMPLE_CDATA_DISPERSO)
        assert parsed["nivel"] == "Primario"

    def test_parse_cdata_extracts_disperso_ambito(self) -> None:
        parsed = parse_description(SAMPLE_CDATA_DISPERSO)
        assert parsed["ambito"] == "Rural Disperso"


class TestParseDescriptionHandlesAccentedLabels:
    def test_parse_cdata_handles_accented_labels(self) -> None:
        # `Ámbito` (A-acute) and `Nivel` must match case-insensitively AND
        # tolerate the diacritic on `Á` — via Unicode-aware regex.
        cdata = (
            "<b>Localidad:</b> Xxx<br/>"
            "<b>Ámbito:</b> Rural Aglomerado<br/>"
            "<b>Nivel:</b> Inicial<br/>"
        )
        parsed = parse_description(cdata)
        assert parsed["ambito"] == "Rural Aglomerado"
        assert parsed["nivel"] == "Inicial"


class TestParseDescriptionReturnsExactlyThreeKeys:
    def test_parse_cdata_returns_exactly_three_keys(self) -> None:
        parsed = parse_description(SAMPLE_CDATA_AGLOMERADO)
        assert set(parsed.keys()) == {"localidad", "ambito", "nivel"}

    def test_parse_cdata_ignores_pii_labels(self) -> None:
        # Defense-in-depth: even though the CDATA contains CUE, Departamento,
        # Sector, Directivo, Teléfono, Email — NONE of those keys may leak
        # into the returned dict (spec REQ-ESC-11 zero-PII gate).
        parsed = parse_description(SAMPLE_CDATA_AGLOMERADO)
        pii_keys = {
            "cue",
            "departamento",
            "sector",
            "directivo",
            "telefono",
            "teléfono",
            "email",
        }
        assert pii_keys.isdisjoint(parsed.keys())


class TestParseDescriptionTolerantToMissingFields:
    def test_missing_field_absent_from_dict(self) -> None:
        # When a placemark is missing one of the 3 labels, the key must be
        # absent rather than silently present-with-empty-value. The caller
        # decides whether missing-field is an error (spec says 7/7 have all 3
        # fields — any missing field signals a data-quality issue).
        cdata = "<b>Localidad:</b> Xxx<br/><b>Nivel:</b> Primario<br/>"
        parsed = parse_description(cdata)
        assert "ambito" not in parsed
        assert parsed["localidad"] == "Xxx"
        assert parsed["nivel"] == "Primario"

    def test_empty_cdata_returns_empty_dict(self) -> None:
        assert parse_description("") == {}

    def test_none_cdata_returns_empty_dict(self) -> None:
        # Defensive: some KML parsers emit None for missing descriptions.
        assert parse_description(None) == {}  # type: ignore[arg-type]
