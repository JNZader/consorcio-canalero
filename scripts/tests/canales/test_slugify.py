"""Tests for the deterministic slug generator.

Slugs back the per-canal layer-id convention in the frontend store
(``canal_relevado_<slug>`` / ``canal_propuesto_<slug>``) so they MUST be:

- lowercase,
- ASCII-only (accents stripped via NFKD decomposition),
- ``[a-z0-9]+`` runs joined by ``-``, with NO leading/trailing dash,
- stable across runs given the same inputs,
- globally unique — when two canals collide on their base slug, the second
  and subsequent ones are disambiguated via a deterministic folder + index
  suffix so no IDs are ever reused.
"""

from __future__ import annotations

from scripts.etl_canales.slugify import slugify, slugify_with_suffix


class TestBasicSlugify:
    def test_simple_lowercase(self):
        assert slugify("Canal NE") == "canal-ne"

    def test_strip_accents(self):
        assert slugify("Readecuación") == "readecuacion"

    def test_mixed_accents(self):
        assert slugify("Colector Norte Ñandú") == "colector-norte-nandu"

    def test_non_alphanumeric_collapsed(self):
        assert slugify("N4 · Tramo 1/2") == "n4-tramo-1-2"

    def test_multiple_spaces_and_edge_chars(self):
        assert slugify("  Canal  -  Norte  ") == "canal-norte"

    def test_parentheses_stripped(self):
        assert slugify("Canal NE (sin intervención)") == "canal-ne-sin-intervencion"

    def test_hyphenated_priority_string(self):
        assert slugify("Media-Alta") == "media-alta"

    def test_arrows_and_punctuation(self):
        # Real name: "Candil tramo SE→NO (sin intervención)"
        assert (
            slugify("Candil tramo SE→NO (sin intervención)")
            == "candil-tramo-se-no-sin-intervencion"
        )

    def test_empty_string_returns_empty(self):
        assert slugify("") == ""

    def test_whitespace_only_returns_empty(self):
        assert slugify("   ") == ""

    def test_digits_only_preserved(self):
        assert slugify("2025") == "2025"


class TestCollisionSuffix:
    """`slugify_with_suffix` disambiguates identical base slugs per folder + idx."""

    def test_first_occurrence_adds_suffix(self):
        # Even the first collision gets the folder+idx suffix — the caller
        # decides whether to use it, but the helper always produces it.
        assert (
            slugify_with_suffix("canal-existente", "canal-norte", 0)
            == "canal-existente-canal-norte-0"
        )

    def test_different_folders_yield_different_slugs(self):
        a = slugify_with_suffix("canal-existente", "canal-norte", 0)
        b = slugify_with_suffix("canal-existente", "canal-monte-lena", 0)
        assert a != b
        assert a == "canal-existente-canal-norte-0"
        assert b == "canal-existente-canal-monte-lena-0"

    def test_same_folder_different_idx(self):
        a = slugify_with_suffix("canal-existente", "revisar", 0)
        b = slugify_with_suffix("canal-existente", "revisar", 1)
        assert a != b
        assert a.endswith("-revisar-0")
        assert b.endswith("-revisar-1")

    def test_folder_with_accents_slugified(self):
        # The folder label itself can contain accents — the suffix helper
        # must slugify the folder too.
        out = slugify_with_suffix("canal-existente", "Canal Monte Leña", 2)
        assert out == "canal-existente-canal-monte-lena-2"

    def test_empty_folder_still_produces_unique_slug(self):
        out = slugify_with_suffix("canal-existente", "", 3)
        # With an empty folder label, we still want uniqueness via the index.
        assert out == "canal-existente--3" or out == "canal-existente-3"
