"""``RelevamientoTramoCreate`` refuses what this capability does not record.

Two rules, both mechanical rather than documentary:

* **RSS-R6 — observations, not dimensions.** ``extra="forbid"`` makes a request
  carrying ``ancho_cuneta`` / ``profundidad`` / ``capacidad`` fail **naming the
  offending field**. "Dimensioning is outside this capability" written in a
  docstring is a sentence; this is the enforcement.
* **RSS-R1 — a partial record is refused, with the missing field named.** A
  submission missing one of the three answers is a 422 listing the field, never a
  row storing a value the operator did not give.

The cuneta combination rule (``estado_cuneta`` is ``None`` **iff**
``tiene_cuneta == 'no'``) is checked here too — and it is *also* a table-level
CHECK in the migration, on purpose. The schema gives the operator a named error;
the CHECK is what holds when a future ETL bypasses the schema entirely.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domains.geo.relevamiento.schemas import (
    CANDIDATA_A_NIVEL,
    CandidataResponse,
    RelevamientoTramoCreate,
)

VALID = {
    "tramo_ref": "28188",
    "nivel_relativo": "mayor",
    "tiene_cuneta": "si",
    "estado_cuneta": "limpia",
}


def _errors(payload: dict) -> list[dict]:
    with pytest.raises(ValidationError) as excinfo:
        RelevamientoTramoCreate(**payload)
    return excinfo.value.errors()


def _named_fields(errors: list[dict]) -> set[str]:
    return {str(loc) for error in errors for loc in error["loc"]}


class TestDimensionsAreRefusedByName:
    @pytest.mark.parametrize("field", ["ancho_cuneta", "profundidad", "capacidad", "seccion"])
    def test_a_dimension_field_is_rejected_naming_it(self, field: str):
        errors = _errors({**VALID, field: 1.5})

        assert _named_fields(errors) == {field}, (
            "the refusal must name the offending field, not fail generically"
        )
        assert any(error["type"] == "extra_forbidden" for error in errors)

    def test_the_model_forbids_extras_rather_than_ignoring_them(self):
        """Asserted on the config, so the rule survives a field being renamed."""
        assert RelevamientoTramoCreate.model_config["extra"] == "forbid"


class TestAPartialRecordIsRefusedWithTheFieldNamed:
    @pytest.mark.parametrize("missing", ["tramo_ref", "nivel_relativo", "tiene_cuneta"])
    def test_a_missing_answer_names_the_field(self, missing: str):
        payload = {k: v for k, v in VALID.items() if k != missing}

        errors = _errors(payload)

        assert missing in _named_fields(errors)
        assert any(error["type"] == "missing" for error in errors)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("nivel_relativo", "alto"),
            ("tiene_cuneta", "quizas"),
            ("estado_cuneta", "sucia"),
        ],
    )
    def test_an_out_of_domain_answer_names_the_field(self, field: str, value: str):
        errors = _errors({**VALID, field: value})

        assert field in _named_fields(errors)


class TestTheCunetaCombinationRule:
    def test_no_cuneta_requires_no_state(self):
        errors = _errors({**VALID, "tiene_cuneta": "no", "estado_cuneta": "limpia"})

        assert "estado_cuneta" in _named_fields(errors)

    @pytest.mark.parametrize("tiene", ["si", "parcial"])
    def test_a_cuneta_requires_a_state(self, tiene: str):
        errors = _errors({**VALID, "tiene_cuneta": tiene, "estado_cuneta": None})

        assert "estado_cuneta" in _named_fields(errors)

    def test_no_cuneta_with_no_state_is_accepted(self):
        payload = RelevamientoTramoCreate(**{**VALID, "tiene_cuneta": "no", "estado_cuneta": None})

        assert payload.estado_cuneta is None

    @pytest.mark.parametrize("tiene", ["si", "parcial"])
    def test_a_cuneta_with_a_state_is_accepted(self, tiene: str):
        payload = RelevamientoTramoCreate(**{**VALID, "tiene_cuneta": tiene})

        assert payload.estado_cuneta == "limpia"


class TestThePreFillFlagIsExplicit:
    """The client says whether the level control was left as pre-filled.

    It is only half of ``nivel_desde_candidata``: the API also compares the
    submitted value against the candidate row server-side (3.9), because a flag
    the client can set freely is a claim, not a fact.
    """

    def test_it_defaults_to_false(self):
        """The honest default: a value is the operator's unless proven accepted."""
        assert RelevamientoTramoCreate(**VALID).nivel_confirmado_sin_cambios is False

    def test_it_can_be_set(self):
        payload = RelevamientoTramoCreate(**VALID, nivel_confirmado_sin_cambios=True)

        assert payload.nivel_confirmado_sin_cambios is True


class TestTheSuggestedLevelIsDerivedFromTheOneTable:
    """``nivel_sugerido`` — computed from ``CANDIDATA_A_NIVEL``, never stored.

    The mapping is exposed so no consumer has to re-implement it. Every pair is
    named here, INCLUDING ``neutro → igual``: it is the one the classifier
    produces when the DEM sees no difference, it is the one a form is most likely
    to translate as "leave it blank", and until now nothing asserted it at all.
    """

    @pytest.mark.parametrize(
        ("clasificacion", "nivel"),
        [("terraplen", "mayor"), ("canal", "menor"), ("neutro", "igual")],
    )
    def test_each_classification_has_exactly_one_operator_level(
        self, clasificacion: str, nivel: str
    ):
        candidata = _candidata(clasificacion)

        assert candidata.nivel_sugerido == nivel
        assert CANDIDATA_A_NIVEL[clasificacion] == nivel

    def test_the_response_carries_it(self):
        cuerpo = _candidata("terraplen").model_dump()

        assert cuerpo["nivel_sugerido"] == "mayor", (
            "a computed field the serializer drops would leave the client with "
            "the raw classification and no choice but to translate it itself"
        )

    def test_it_cannot_be_supplied_by_the_caller(self):
        """Derived means derived: an input would be a second source of truth."""
        candidata = CandidataResponse(**{**_candidata_kwargs("canal"), "nivel_sugerido": "mayor"})

        assert candidata.nivel_sugerido == "menor"

    def test_the_table_covers_every_classification_the_column_allows(self):
        """Total by construction, so the lookup cannot raise on a valid row."""
        from typing import get_args

        from app.domains.geo.relevamiento.schemas import ClasificacionCandidata

        assert set(CANDIDATA_A_NIVEL) == set(get_args(ClasificacionCandidata))

    def test_the_service_uses_this_very_object(self):
        """Not "an equal copy" — the same object, so it cannot drift."""
        from app.domains.geo.relevamiento import service

        assert service.CANDIDATA_A_NIVEL is CANDIDATA_A_NIVEL


def _candidata_kwargs(clasificacion: str) -> dict:
    return {
        "tramo_ref": "28188",
        "geo_job_id": uuid.uuid4(),
        "clasificacion_candidata": clasificacion,
        "confianza_m": 1.4,
        "calculada_en": datetime.now(timezone.utc),
    }


def _candidata(clasificacion: str) -> CandidataResponse:
    return CandidataResponse(**_candidata_kwargs(clasificacion))


class TestNoHydraulicQuantityIsOffered:
    @pytest.mark.parametrize(
        "forbidden",
        ["volumen", "caudal", "profundidad", "ancho", "capacidad", "periodo_retorno", "m3"],
    )
    def test_no_field_names_a_quantity(self, forbidden: str):
        field_names = " ".join(RelevamientoTramoCreate.model_fields).lower()

        assert forbidden not in field_names
