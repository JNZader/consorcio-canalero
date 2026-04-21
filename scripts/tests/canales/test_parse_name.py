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
        # The parenthesized (P12) is the REAL code (bug fix: parser used to
        # extract "S2" or None; now it extracts "P12" from the parenthesis).
        raw = "S2 complemento opcional (P12) · 5.916 m · sujeto a presupuesto"
        parsed = parse_name(raw)
        assert parsed.codigo == "P12"
        assert parsed.longitud_declarada_m == 5916.0
        # Keyword inference kicks in: lowercase "opcional" + "sujeto a
        # presupuesto" tail both map to "Opcional" when no explicit
        # uppercase priority tag is present.
        assert parsed.prioridad == "Opcional"


class TestParenthesizedCodeOverride:
    """A parenthesized P-series / N-series code in the name overrides any
    prefix token. Real KMZ names like "S2 complemento opcional (P12) · ..."
    carry the true codigo inside the parentheses; S2 is just the group
    family marker used by the author, not the canal code.
    """

    def test_parenthesized_code_overrides_prefix(self):
        # S2 is the group prefix, (P12) is the real code.
        r = parse_name(
            "S2 complemento opcional (P12) · 5.916 m · sujeto a presupuesto"
        )
        assert r.codigo == "P12"
        assert r.descripcion.startswith("S2 complemento opcional")
        # longitud + prioridad may or may not parse; both OK.

    def test_parenthesized_code_with_letter_suffix(self):
        r = parse_name("S2 alternativa a o c (P14a norte)")
        assert r.codigo == "P14a"

    def test_parenthesized_code_without_length_or_prio(self):
        r = parse_name("S2 alternativa b o c (P13)")
        assert r.codigo == "P13"

    def test_parenthesized_code_p14b(self):
        r = parse_name("S2 alternativa a solamente (P14b sur)")
        assert r.codigo == "P14b"

    def test_parenthesized_code_p15(self):
        r = parse_name("S2 alternativa c (P15)")
        assert r.codigo == "P15"

    def test_no_parenthesis_keeps_prefix(self):
        # No paren → keep current behavior (S2 as code, or None).
        r = parse_name("S2 núcleo · Tramo norte centro-este")
        # The original may be S2 or None depending on strict pattern — but
        # NOT P-anything.
        assert r.codigo is None or r.codigo.startswith("S")

    def test_parenthesized_n_series_code(self):
        # N-series in parentheses also triggers the override (for safety).
        r = parse_name("Grupo · Canal viejo (N3) · 500 m")
        assert r.codigo == "N3"

    def test_real_largo_plazo_normalisation(self):
        raw = "S7 · Extensión Monte Leña oeste · 6.277 m · LARGO PLAZO"
        parsed = parse_name(raw)
        assert parsed.codigo == "S7"
        assert parsed.longitud_declarada_m == 6277.0
        assert parsed.prioridad == "Largo plazo"


class TestPriorityInferenceFromKeywords:
    """When the explicit/strict parser can't extract a priority token, infer
    from keywords in the full raw name. Applies ONLY when explicit parse
    failed — uppercase tags ALWAYS win.
    """

    def test_infer_opcional_from_lowercase_keyword(self):
        r = parse_name("S2 complemento opcional (P12) · 5.916 m · sujeto a presupuesto")
        assert r.codigo == "P12"
        assert r.prioridad == "Opcional"
        assert r.longitud_declarada_m == 5916.0

    def test_infer_opcional_from_sujeto_presupuesto_even_without_word(self):
        # Hypothetical: a name with "sujeto a presupuesto" but no "opcional"
        r = parse_name("N9 tramo conexión futura · 2.500 m · sujeto a presupuesto")
        assert r.prioridad == "Opcional"

    def test_infer_largo_plazo(self):
        r = parse_name("Alguna cosa largo plazo (P99) · 100 m")
        assert r.prioridad == "Largo plazo"

    def test_explicit_priority_wins_over_keyword(self):
        # Even if "opcional" appears, the uppercase "ALTA" token wins
        r = parse_name("N3 tramo opcional alternativo · 500 m · ALTA")
        assert r.prioridad == "Alta"  # NOT "Opcional"


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
