"""Tests for the name parser — strict-then-fallback KMZ ``<name>`` decoder.

The real-world KMZ names carry ALL metadata (codigo · descripcion · longitud ·
prioridad [★]) packed into the ``<name>`` string with ``·`` separators.  Some
placemarks omit fields (no codigo, no longitud, no prioridad), so the parser
MUST gracefully fall back to extracting whatever chunks it can identify
regardless of their order.

These tests pin the exact ``ParsedName`` output for representative real names
so the implementation can be verified against a ground truth.
"""

from __future__ import annotations

import pytest

from scripts.etl_canales.parse_name import ParsedName, parse_name


class TestStrictPattern:
    """Strict pattern = ``[CODIGO ·] NOMBRE [· LONG m] [· PRIORIDAD] [★]``."""

    def test_full_strict_with_priority(self):
        raw = "N4 · Readecuación tramo inicial · 1.355 m · ALTA"
        parsed = parse_name(raw)
        assert parsed == ParsedName(
            codigo="N4",
            descripcion="Readecuación tramo inicial",
            longitud_declarada_m=1355.0,
            prioridad="Alta",
            featured=False,
        )

    def test_full_strict_with_star(self):
        raw = "N3 · Tramo faltante · 685 m · ALTA ★"
        parsed = parse_name(raw)
        assert parsed.codigo == "N3"
        assert parsed.descripcion == "Tramo faltante"
        assert parsed.longitud_declarada_m == 685.0
        assert parsed.prioridad == "Alta"
        assert parsed.featured is True

    def test_full_strict_with_star_and_extra_noise(self):
        raw = "S5 · Conexión cantera · 468 m · MEDIA-ALTA ★ alto ROI"
        parsed = parse_name(raw)
        assert parsed.codigo == "S5"
        assert "Conexión cantera" in parsed.descripcion
        # The trailing "alto ROI" must not leak into prioridad — the parser
        # MUST recognise MEDIA-ALTA + ★ and stop there.
        assert parsed.longitud_declarada_m == 468.0
        assert parsed.prioridad == "Media-Alta"
        assert parsed.featured is True

    def test_codigo_with_suffix_letter(self):
        # Real-world examples use multi-char codes like "E21", "S2B", etc.
        raw = "E21 · Canal Monte Leña (tramo) · 3.887 m"
        parsed = parse_name(raw)
        assert parsed.codigo == "E21"
        assert parsed.descripcion == "Canal Monte Leña (tramo)"
        assert parsed.longitud_declarada_m == 3887.0
        assert parsed.prioridad is None
        assert parsed.featured is False

    def test_longitud_five_digit_thousands_sep(self):
        # Spanish numeric notation: "19.413" is 19413 m, NOT 19.413 m.
        raw = "E9 · Colector norte · 19.413 m"
        parsed = parse_name(raw)
        assert parsed.codigo == "E9"
        assert parsed.longitud_declarada_m == 19413.0

    def test_longitud_no_thousands_sep(self):
        raw = "N2 · Tramo X · 468 m · MEDIA"
        parsed = parse_name(raw)
        assert parsed.longitud_declarada_m == 468.0
        assert parsed.prioridad == "Media"

    def test_no_codigo_fallback_to_fallback_path(self):
        # "Canal NE (sin intervención)" has no codigo, no longitud, no priority.
        raw = "Canal NE (sin intervención)"
        parsed = parse_name(raw)
        assert parsed.codigo is None
        assert parsed.descripcion == "Canal NE (sin intervención)"
        assert parsed.longitud_declarada_m is None
        assert parsed.prioridad is None
        assert parsed.featured is False


class TestPriorityNormalization:
    """Every priority string normalises to one of 5 canonical Title-Case values."""

    @pytest.mark.parametrize(
        "raw_priority, expected",
        [
            ("ALTA", "Alta"),
            ("Alta", "Alta"),
            ("alta", "Alta"),
            ("MEDIA-ALTA", "Media-Alta"),
            ("Media-Alta", "Media-Alta"),
            ("media-alta", "Media-Alta"),
            ("MEDIA ALTA", "Media-Alta"),  # space variant — normalise to hyphen
            ("MEDIA", "Media"),
            ("OPCIONAL", "Opcional"),
            ("Opcional", "Opcional"),
            ("LARGO PLAZO", "Largo plazo"),
            ("Largo plazo", "Largo plazo"),
            ("largo plazo", "Largo plazo"),
        ],
    )
    def test_priority_normalizes(self, raw_priority: str, expected: str):
        raw = f"X1 · Test · 100 m · {raw_priority}"
        parsed = parse_name(raw)
        assert parsed.prioridad == expected, (
            f"{raw_priority!r} should normalise to {expected!r}, got {parsed.prioridad!r}"
        )


class TestFallbackPath:
    """When the strict pattern fails, the fallback classifies chunks individually."""

    def test_reordered_chunks(self):
        # Priority before longitud — strict regex fails, fallback classifies.
        raw = "Readecuación · MEDIA · 850 m · E12"
        parsed = parse_name(raw)
        assert parsed.codigo == "E12"
        assert "Readecuación" in parsed.descripcion
        assert parsed.longitud_declarada_m == 850.0
        assert parsed.prioridad == "Media"
        assert parsed.featured is False

    def test_unknown_priority_falls_through(self):
        # Typo — neither strict nor fallback should crash; prioridad stays None.
        raw = "Z3 · Canal test · 100 m · ALTÍSIMA"
        parsed = parse_name(raw)
        assert parsed.codigo == "Z3"
        assert "Canal test" in parsed.descripcion
        assert parsed.longitud_declarada_m == 100.0
        assert parsed.prioridad is None  # unrecognised → None, not a crash
        assert parsed.featured is False

    def test_real_relevado_with_colgate_priority_mention(self):
        # Real relevado name — the 3rd chunk is a free-form descriptor
        # ("readecuación"), NOT a priority. The parser must NOT misinterpret it.
        raw = "S1 · Canal chico este San Marcos Sud · readecuación"
        parsed = parse_name(raw)
        assert parsed.codigo == "S1"
        assert "Canal chico este San Marcos Sud" in parsed.descripcion
        assert parsed.longitud_declarada_m is None
        assert parsed.prioridad is None  # "readecuación" is NOT a priority
        assert parsed.featured is False

    def test_real_opcional_with_sujeto_a_presupuesto_tail(self):
        # Real propuesta name — last chunk is descriptive noise, not priority.
        raw = "S2 complemento opcional (P12) · 5.916 m · sujeto a presupuesto"
        parsed = parse_name(raw)
        assert parsed.codigo is None  # "S2 complemento..." doesn't start with a bare code token
        assert parsed.longitud_declarada_m == 5916.0
        # "sujeto a presupuesto" is NOT a canonical priority → None.
        assert parsed.prioridad is None

    def test_real_largo_plazo_normalisation(self):
        raw = "S7 · Extensión Monte Leña oeste · 6.277 m · LARGO PLAZO"
        parsed = parse_name(raw)
        assert parsed.codigo == "S7"
        assert parsed.longitud_declarada_m == 6277.0
        assert parsed.prioridad == "Largo plazo"


class TestFeaturedStarDetection:
    def test_star_anywhere_flips_featured(self):
        raw = "A1 · Test featured · 500 m · ALTA ★"
        assert parse_name(raw).featured is True

    def test_no_star_means_not_featured(self):
        raw = "A1 · Test plain · 500 m · ALTA"
        assert parse_name(raw).featured is False


class TestEdgeCases:
    def test_empty_string_returns_minimal(self):
        parsed = parse_name("")
        assert parsed.codigo is None
        assert parsed.descripcion == ""
        assert parsed.longitud_declarada_m is None
        assert parsed.prioridad is None
        assert parsed.featured is False

    def test_single_word_no_separators(self):
        parsed = parse_name("Relevamiento")
        assert parsed.codigo is None
        assert parsed.descripcion == "Relevamiento"
        assert parsed.longitud_declarada_m is None
        assert parsed.prioridad is None
