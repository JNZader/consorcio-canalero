"""Tests for ``normalize_cuenta`` — the load-bearing join-key normaliser.

``Nro_Cuenta`` (catastro), ``cuenta`` (bpa_2025) and ``lista_cuenta`` (agro)
all carry the same logical identifier through three different IDECor layers,
but each comes with its own quirks: whitespace, dots as thousands separators,
int vs str, nullish sentinel values.  ``normalize_cuenta`` is the single
choke-point that makes them joinable.
"""

from __future__ import annotations

import pytest

from scripts.etl_pilar_verde.join import normalize_cuenta


class TestNormalizeCuenta:
    def test_none_returns_none(self):
        assert normalize_cuenta(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_cuenta("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_cuenta("   ") is None

    def test_string_none_sentinel_returns_none(self):
        # IDECor occasionally serialises null as the literal "None"
        assert normalize_cuenta("None") is None

    def test_strips_leading_and_trailing_whitespace(self):
        assert normalize_cuenta("  150115736126  ") == "150115736126"

    def test_strips_embedded_whitespace(self):
        assert normalize_cuenta("1501 157 36126") == "150115736126"

    def test_strips_dot_thousands_separator(self):
        assert normalize_cuenta("1501.1573.6126") == "150115736126"

    def test_int_is_cast_to_string(self):
        assert normalize_cuenta(150115736126) == "150115736126"

    def test_float_with_trailing_zero_is_preserved_as_string(self):
        # Edge case: JSON numbers may arrive as floats (e.g. 1501157361.0).
        # Strategy: str() first, strip dot-separator artefacts. A true decimal
        # fraction is NOT expected for a cuenta — flagging via length would be
        # noise here. The simplest deterministic rule: str() + strip dots.
        assert normalize_cuenta(1501157361.0) == "15011573610"

    def test_idempotent(self):
        once = normalize_cuenta("  150115736126  ")
        twice = normalize_cuenta(once)
        assert once == twice == "150115736126"
