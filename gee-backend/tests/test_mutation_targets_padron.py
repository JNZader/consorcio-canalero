"""Focused unit tests for the padron pure validations — CUIT mod-11 + schemas.

Second half of the ``.cosmic-ray.toml`` TODO ("escribir primero unit tests
LIVIANOS sin DB — ej. ``validar_cuit`` mod-11"). Everything here is pure python:
no DB, no app boot, no testcontainers.

Scope note, so nobody misreads the numbers: these tests cover
``app/domains/padron/schemas.py``, which is where ``validar_cuit`` actually lives.
The candidate mutation module for the padron stage is
``app/domains/padron/service.py`` — a different file. This is the groundwork
(a real, fast safety net over the domain's only non-trivial algorithm), not the
padron kill-rate lever; that one needs fake-repository tests over the service,
the same shape as ``tests/test_mutation_targets_finanzas.py``.

CUIT fixtures are DERIVED, not copied from anywhere real: base + the check digit
the AFIP mod-11 algorithm demands for it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.padron.schemas import (
    ConsorcistaCreate,
    ConsorcistaUpdate,
    _normalize_cuit,
    validar_cuit,
)

#: One valid CUIT per real AFIP prefix (20/23/27 personas, 30/33 empresas).
VALID_BY_PREFIX = {
    "20": "20100000009",
    "23": "23100000008",
    "27": "27100000003",
    "30": "30100000004",
    "33": "33100000003",
}
#: ``resto == 0`` -> the check digit must be exactly 0 (its own branch).
VALID_RESTO_ZERO = "20100000130"
#: ``resto == 1`` -> ALWAYS invalid. AFIP never issues these; it changes the
#: prefix instead (20 -> 23). This is the branch a mutated ``resto == 1`` guard
#: would silently open.
RESTO_ONE = "20100000050"


class TestValidarCuitAcceptsRealOnes:
    @pytest.mark.parametrize("prefix,cuit", sorted(VALID_BY_PREFIX.items()))
    def test_a_valid_cuit_of_every_prefix_family_passes(self, prefix: str, cuit: str) -> None:
        assert cuit.startswith(prefix)
        assert validar_cuit(cuit) is True

    def test_the_resto_zero_branch_accepts_check_digit_zero(self) -> None:
        assert VALID_RESTO_ZERO.endswith("0")
        assert validar_cuit(VALID_RESTO_ZERO) is True

    def test_the_dash_formatted_form_is_accepted(self) -> None:
        assert validar_cuit("20-10000000-9") is True

    def test_arbitrary_separators_are_stripped_before_checking(self) -> None:
        assert validar_cuit("20.10000000/9") is True


class TestValidarCuitRejects:
    def test_a_wrong_check_digit_is_rejected(self) -> None:
        """Same 10-digit base, every OTHER check digit must fail — this is the
        assertion a mutated multiplier or ``11 - resto`` cannot survive."""
        base = VALID_BY_PREFIX["20"][:10]
        correct = VALID_BY_PREFIX["20"][10]
        wrong = [str(d) for d in range(10) if str(d) != correct]
        assert all(validar_cuit(base + d) is False for d in wrong)

    def test_resto_one_is_always_invalid_whatever_the_check_digit(self) -> None:
        base = RESTO_ONE[:10]
        assert all(validar_cuit(base + str(d)) is False for d in range(10))

    @pytest.mark.parametrize("cuit", ["", "2010000000", "201000000099", "1"])
    def test_a_wrong_length_is_rejected(self, cuit: str) -> None:
        assert validar_cuit(cuit) is False

    def test_non_numeric_input_is_rejected_not_crashed(self) -> None:
        # Letters are stripped as separators, so this is a length failure, and it
        # must be a clean False — never a ValueError out of int().
        assert validar_cuit("AB-CDEFGHIJ-K") is False
        assert validar_cuit("20-1000000A-9") is False

    def test_the_multipliers_are_position_sensitive(self) -> None:
        """Reversing a valid CUIT's base breaks it: without position-sensitive
        multipliers a mod-11 check is just a digit sum."""
        valid = VALID_BY_PREFIX["27"]
        reversed_base = valid[:10][::-1]
        assert validar_cuit(reversed_base + valid[10]) is False


class TestNormalizeCuit:
    def test_digits_only_input_comes_back_dash_formatted(self) -> None:
        assert _normalize_cuit("20100000009") == "20-10000000-9"

    def test_already_formatted_input_is_idempotent(self) -> None:
        assert _normalize_cuit("20-10000000-9") == "20-10000000-9"

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert _normalize_cuit("  20100000009  ") == "20-10000000-9"

    def test_a_wrong_length_names_the_expected_format(self) -> None:
        with pytest.raises(ValueError) as exc:
            _normalize_cuit("2010000000")
        assert "11 digitos" in str(exc.value)

    def test_a_bad_check_digit_says_so_specifically(self) -> None:
        """The two failure messages must stay distinct: "wrong length" and "wrong
        check digit" are different data-entry mistakes."""
        with pytest.raises(ValueError) as exc:
            _normalize_cuit("20100000008")
        assert "digito verificador" in str(exc.value)


class TestConsorcistaSchemas:
    def test_create_normalises_the_cuit_it_stores(self) -> None:
        consorcista = ConsorcistaCreate(nombre="Ana", apellido="Diaz", cuit="27100000003")
        assert consorcista.cuit == "27-10000000-3"

    def test_create_rejects_an_invalid_cuit(self) -> None:
        with pytest.raises(ValidationError):
            ConsorcistaCreate(nombre="Ana", apellido="Diaz", cuit="20100000008")

    def test_estado_defaults_to_activo(self) -> None:
        assert ConsorcistaCreate(nombre="Ana", apellido="Diaz", cuit="27100000003").estado == (
            "activo"
        )

    def test_negative_hectareas_are_rejected_and_zero_is_allowed(self) -> None:
        with pytest.raises(ValidationError):
            ConsorcistaCreate(nombre="Ana", apellido="Diaz", cuit="27100000003", hectareas=-0.5)
        assert (
            ConsorcistaCreate(
                nombre="Ana", apellido="Diaz", cuit="27100000003", hectareas=0.0
            ).hectareas
            == 0.0
        )

    def test_an_empty_nombre_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConsorcistaCreate(nombre="", apellido="Diaz", cuit="27100000003")

    def test_update_leaves_an_absent_cuit_alone(self) -> None:
        """The ``v is None`` short-circuit: a PATCH that does not touch the CUIT
        must not be validated as if it carried an empty one."""
        assert ConsorcistaUpdate(nombre="Ana").cuit is None
        assert ConsorcistaUpdate(cuit=None).cuit is None

    def test_update_normalises_a_present_cuit(self) -> None:
        assert ConsorcistaUpdate(cuit="30100000004").cuit == "30-10000000-4"

    def test_update_rejects_a_present_but_invalid_cuit(self) -> None:
        with pytest.raises(ValidationError):
            ConsorcistaUpdate(cuit="30100000005")
