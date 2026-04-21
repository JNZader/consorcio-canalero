"""Tests for the deterministic slug generator used by Escuela feature ids.

Slugs back the per-school ``Feature.id`` convention in the static GeoJSON
(``"id": "esc-joaquin-victor-gonzalez"``) so they MUST be:

- lowercase,
- ASCII-only (accents stripped via NFKD decomposition — same strategy as
  ``scripts.etl_canales.slugify.slugify``),
- ``[a-z0-9]+`` runs joined by ``-`` with NO leading/trailing dash,
- deterministic across runs given the same inputs,
- globally unique within the output — two schools that happen to share a
  name get disambiguated via ``slug_with_counter`` which appends ``-2``,
  ``-3``, … in KML document order (0-indexed internally, ``-2`` suffix is
  the FIRST collision per the prompt — ``esc-duplicada`` → ``esc-duplicada-2``).

The suffixing convention here is simpler than ``etl_canales.slugify_with_suffix``
(which includes a folder segment): the Escuelas KMZ is FLAT (no nested folders),
so we only need a per-base counter.
"""

from __future__ import annotations

from scripts.etl_escuelas.parse import slug, slug_with_counter


class TestSlugBasic:
    def test_slug_basic(self) -> None:
        assert slug("Escuela Mariano Necochea") == "escuela-mariano-necochea"

    def test_slug_strips_accents_nfkd(self) -> None:
        # "Joaquín Víctor González" → accents dropped via NFKD.
        assert slug("Escuela Joaquín Víctor González") == "escuela-joaquin-victor-gonzalez"

    def test_slug_strips_enye(self) -> None:
        # "ñ" should become "n" (NFKD decomposition + combining-mark strip).
        assert slug("Colonia Ermila ñ") == "colonia-ermila-n"

    def test_slug_non_alnum_collapsed(self) -> None:
        # Punctuation, parens, arrows — all collapse to a single dash.
        assert slug("Esc. French & Berutti (rural)") == "esc-french-berutti-rural"

    def test_slug_lowercases_everything(self) -> None:
        assert slug("ALL CAPS NAME") == "all-caps-name"

    def test_slug_trims_leading_trailing_dashes(self) -> None:
        assert slug("  ---Esc. Foo---  ") == "esc-foo"

    def test_slug_empty_returns_empty(self) -> None:
        assert slug("") == ""

    def test_slug_whitespace_only_returns_empty(self) -> None:
        assert slug("   ") == ""

    def test_slug_is_deterministic_across_runs(self) -> None:
        # Same input → same output, forever.  Used by the ETL idempotence gate.
        name = "Escuela Nicolás Rodríguez Peña"
        expected = "escuela-nicolas-rodriguez-pena"
        assert slug(name) == expected
        assert slug(name) == expected  # run again — still identical
        assert slug(name) == expected  # and again


class TestSlugWithCounter:
    """``slug_with_counter`` appends ``-2``, ``-3``, … on collision.

    The first occurrence of a base slug is used AS-IS; the second gets the
    ``-2`` suffix (a human-friendly count, not a 0-indexed one).  The helper
    mutates a caller-owned ``seen`` dict so the loop body stays stateless.
    """

    def test_first_occurrence_uses_base_slug(self) -> None:
        seen: dict[str, int] = {}
        out = slug_with_counter("esc-duplicada", seen)
        assert out == "esc-duplicada"
        # The counter advanced so the next call collides.
        assert seen == {"esc-duplicada": 1}

    def test_slug_collision_counter_suffix(self) -> None:
        seen: dict[str, int] = {}
        first = slug_with_counter("esc-duplicada", seen)
        second = slug_with_counter("esc-duplicada", seen)
        third = slug_with_counter("esc-duplicada", seen)
        assert first == "esc-duplicada"
        assert second == "esc-duplicada-2"
        assert third == "esc-duplicada-3"

    def test_independent_bases_do_not_interfere(self) -> None:
        seen: dict[str, int] = {}
        a = slug_with_counter("esc-a", seen)
        b = slug_with_counter("esc-b", seen)
        a2 = slug_with_counter("esc-a", seen)
        assert a == "esc-a"
        assert b == "esc-b"
        assert a2 == "esc-a-2"

    def test_order_matches_input_order(self) -> None:
        # Determinism: same call sequence → same output sequence.
        seen1: dict[str, int] = {}
        seq1 = [
            slug_with_counter("esc-x", seen1),
            slug_with_counter("esc-y", seen1),
            slug_with_counter("esc-x", seen1),
            slug_with_counter("esc-x", seen1),
        ]
        seen2: dict[str, int] = {}
        seq2 = [
            slug_with_counter("esc-x", seen2),
            slug_with_counter("esc-y", seen2),
            slug_with_counter("esc-x", seen2),
            slug_with_counter("esc-x", seen2),
        ]
        assert seq1 == seq2 == ["esc-x", "esc-y", "esc-x-2", "esc-x-3"]
