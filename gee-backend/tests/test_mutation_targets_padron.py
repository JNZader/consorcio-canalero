"""Focused unit tests for the padron mutation target — service + pure schemas.

Stage 2 of the staged mutation plan documented in ``.cosmic-ray.toml``: the file
started as the schema half (``validar_cuit`` mod-11 — pure logic, no DB) and now
also carries the ``PadronService`` half, which is what actually makes
``app/domains/padron/service.py`` a measurable mutation target.

The recipe is the one finanzas proved (see
``tests/test_mutation_targets_finanzas.py``): ``PadronService`` never touches the
database itself — it delegates to ``PadronRepository`` and owns only the 404/409
mapping, the CUIT-uniqueness rules and the CSV/XLSX import pipeline. All of that
runs against a ``MagicMock`` repository and a ``MagicMock`` session: no engine, no
container, no migrations, and one pytest invocation cheap enough to be multiplied
by hundreds of mutants.

Assertion style for the tests added in stage 2: behaviour and effects (status
codes, counters, which repository calls did or did not happen, the shape of the
``errors`` payload). None of them pin the WORDING of a user-facing message —
those are slated for translation and would have to be rewritten with it. Where a
message is checked at all it is for the DATA it must carry (the offending CUIT,
so the operator can find the row in the spreadsheet), not for its phrasing.

Two asserts predating this stage do pin Spanish text — ``"11 digitos"`` and
``"digito verificador"`` in ``TestNormalizeCuit`` — and are left alone here: they
belong to the i18n cleanup, not to the mutation work.

CUIT fixtures are DERIVED, not copied from anywhere real: base + the check digit
the AFIP mod-11 algorithm demands for it.
"""

from __future__ import annotations

import io
import sys
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.domains.padron.schemas import (
    ConsorcistaCreate,
    ConsorcistaUpdate,
    _normalize_cuit,
    validar_cuit,
)
from app.domains.padron.service import (
    _COLUMN_ALIASES,
    PadronService,
    _canonical_key,
    _normalize_cuit as _service_normalize_cuit,
    _normalize_text,
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


# ===========================================================================
# padron service — module-level normalisers (pure python, no DB)
# ===========================================================================

#: Four distinct CUITs that pass the AFIP check digit, in raw and stored form.
CUIT_A_RAW, CUIT_A = "20100000009", "20-10000000-9"
CUIT_B_RAW, CUIT_B = "27100000003", "27-10000000-3"
CUIT_C_RAW, CUIT_C = "30100000004", "30-10000000-4"
CUIT_D_RAW, CUIT_D = "23100000008", "23-10000000-8"
#: 11 digits, wrong check digit — parses as a CUIT, fails AFIP validation.
CUIT_WRONG_DV = "20100000008"

#: Two ids with a FIXED ordering. ``uuid.UUID`` compares with ``<``/``>`` as
#: happily as with ``!=``, so an identity check that drifted into an ordering
#: check would pass or fail at random against ``uuid4()`` fixtures.
LOW_ID = uuid.UUID(int=1)
HIGH_ID = uuid.UUID(int=2)


class TestNormalizeText:
    def test_none_stays_none(self) -> None:
        assert _normalize_text(None) is None

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert _normalize_text("  Ana  ") == "Ana"

    def test_a_whitespace_only_cell_becomes_none_not_an_empty_string(self) -> None:
        """Downstream every check is ``if not payload.get(...)``, so a blank cell
        and a missing column must collapse to the same thing."""
        assert _normalize_text("   ") is None
        assert _normalize_text("") is None

    def test_a_non_string_cell_is_coerced(self) -> None:
        """XLSX hands back ints and floats, not strings."""
        assert _normalize_text(0) == "0"
        assert _normalize_text(12.5) == "12.5"


class TestServiceNormalizeCuit:
    """The importer's CUIT normaliser is deliberately LENIENT — it formats what
    looks like a CUIT and passes anything else through untouched, leaving the
    actual AFIP validation to ``ConsorcistaCreate``."""

    def test_eleven_digits_are_split_two_eight_one(self) -> None:
        assert _service_normalize_cuit("20123456789") == "20-12345678-9"

    def test_an_already_formatted_cuit_is_idempotent(self) -> None:
        assert _service_normalize_cuit("20-12345678-9") == "20-12345678-9"

    def test_arbitrary_separators_are_stripped_before_formatting(self) -> None:
        assert _service_normalize_cuit(" 20.12345678/9 ") == "20-12345678-9"

    @pytest.mark.parametrize("value", ["12345", "201234567891"])
    def test_anything_that_is_not_eleven_digits_passes_through_unchanged(self, value: str) -> None:
        """Too short AND too long: the guard is an equality, not a floor or a
        ceiling, so both sides have to be pinned."""
        assert _service_normalize_cuit(value) == value

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_an_empty_cell_yields_none(self, value: Any) -> None:
        assert _service_normalize_cuit(value) is None


class TestCanonicalKey:
    @pytest.mark.parametrize(
        "alias,canonical",
        sorted(
            (alias, canonical)
            for canonical, aliases in _COLUMN_ALIASES.items()
            for alias in aliases
        ),
    )
    def test_every_declared_alias_maps_to_its_canonical_field(
        self, alias: str, canonical: str
    ) -> None:
        assert _canonical_key(alias) == canonical

    def test_headers_are_matched_case_and_whitespace_insensitively(self) -> None:
        assert _canonical_key("  Nombre  ") == "nombre"

    def test_internal_spaces_become_underscores(self) -> None:
        """``Direccion Postal`` is a real column name in the spreadsheets the
        consorcio actually receives."""
        assert _canonical_key("Direccion Postal") == "domicilio"

    def test_an_unknown_header_maps_to_nothing(self) -> None:
        assert _canonical_key("observaciones") is None

    def test_an_empty_header_maps_to_nothing(self) -> None:
        assert _canonical_key(None) is None


# ===========================================================================
# PadronService — queries and commands
# ===========================================================================


def _service() -> tuple[PadronService, MagicMock, MagicMock]:
    """Service wired to a fake repository and a fake session.

    The session is a mock on purpose: ``commit``/``refresh``/``begin_nested`` are
    part of the contract this layer owns, and asserting on the mock is how the
    sequencing gets pinned without a database.
    """
    repo = MagicMock()
    return PadronService(repository=repo), repo, MagicMock()


class TestConstruction:
    def test_an_injected_repository_is_the_one_used(self) -> None:
        repo = MagicMock()
        assert PadronService(repository=repo).repo is repo

    def test_a_service_built_without_a_repository_makes_its_own(self) -> None:
        from app.domains.padron.repository import PadronRepository

        assert isinstance(PadronService().repo, PadronRepository)


class TestGetById:
    def test_returns_the_row_when_the_repository_finds_it(self) -> None:
        svc, repo, db = _service()
        consorcista = object()
        repo.get_by_id.return_value = consorcista
        consorcista_id = uuid.uuid4()

        assert svc.get_by_id(db, consorcista_id) is consorcista
        repo.get_by_id.assert_called_once_with(db, consorcista_id)

    def test_raises_404_when_the_repository_returns_none(self) -> None:
        svc, repo, db = _service()
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.get_by_id(db, uuid.uuid4())

        assert exc.value.status_code == 404


class TestListConsorcistas:
    def test_defaults_are_page_1_limit_20_and_no_filters(self) -> None:
        """The pagination defaults are part of the contract: a mutated ``limit=20``
        would silently change every un-parameterised listing."""
        svc, repo, db = _service()
        repo.get_all.return_value = ([], 0)

        assert svc.list_consorcistas(db) == ([], 0)
        repo.get_all.assert_called_once_with(
            db, page=1, limit=20, estado_filter=None, categoria_filter=None, search=None
        )

    def test_every_argument_is_forwarded_under_the_repository_kwarg_names(self) -> None:
        svc, repo, db = _service()
        repo.get_all.return_value = (["row"], 1)

        result = svc.list_consorcistas(
            db, page=3, limit=50, estado="activo", categoria="propietario", search="diaz"
        )

        assert result == (["row"], 1)
        repo.get_all.assert_called_once_with(
            db,
            page=3,
            limit=50,
            estado_filter="activo",
            categoria_filter="propietario",
            search="diaz",
        )

    def test_the_filters_are_keyword_only(self) -> None:
        """``page`` and ``limit`` are adjacent ints with different meanings; the
        keyword-only marker is what stops ``list(db, 20, 1)`` from type-checking
        as a valid call and silently paginating backwards."""
        svc, repo, db = _service()
        repo.get_all.return_value = ([], 0)

        with pytest.raises(TypeError):
            svc.list_consorcistas(db, 3)


class TestGetStats:
    def test_stats_are_a_straight_passthrough(self) -> None:
        svc, repo, db = _service()
        repo.get_stats.return_value = {"total": 7}

        assert svc.get_stats(db) == {"total": 7}
        repo.get_stats.assert_called_once_with(db)


def _create_payload(cuit: str = CUIT_A_RAW) -> ConsorcistaCreate:
    return ConsorcistaCreate(nombre="Ana", apellido="Diaz", cuit=cuit)


class TestCreate:
    def test_a_free_cuit_creates_commits_and_refreshes(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        created = object()
        repo.create.return_value = created
        data = _create_payload()

        assert svc.create(db, data) is created
        repo.get_by_cuit.assert_called_once_with(db, CUIT_A)
        repo.create.assert_called_once_with(db, data)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(created)

    def test_a_taken_cuit_is_409_and_writes_nothing(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = SimpleNamespace(id=uuid.uuid4())

        with pytest.raises(HTTPException) as exc:
            svc.create(db, _create_payload())

        assert exc.value.status_code == 409
        repo.create.assert_not_called()
        db.commit.assert_not_called()


class TestUpdate:
    def test_an_update_that_does_not_touch_the_cuit_skips_the_uniqueness_check(self) -> None:
        svc, repo, db = _service()
        repo.get_by_id.return_value = SimpleNamespace(id=uuid.uuid4())
        updated = object()
        repo.update.return_value = updated
        consorcista_id = uuid.uuid4()
        data = ConsorcistaUpdate(nombre="Ana Maria")

        assert svc.update(db, consorcista_id, data) is updated
        repo.get_by_cuit.assert_not_called()
        repo.update.assert_called_once_with(db, consorcista_id, data)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(updated)

    def test_an_explicit_null_cuit_also_skips_the_uniqueness_check(self) -> None:
        svc, repo, db = _service()
        repo.get_by_id.return_value = SimpleNamespace(id=uuid.uuid4())
        repo.update.return_value = object()

        svc.update(db, uuid.uuid4(), ConsorcistaUpdate(cuit=None))

        repo.get_by_cuit.assert_not_called()
        repo.update.assert_called_once()

    def test_a_free_cuit_is_accepted(self) -> None:
        svc, repo, db = _service()
        repo.get_by_id.return_value = SimpleNamespace(id=uuid.uuid4())
        repo.get_by_cuit.return_value = None
        repo.update.return_value = object()

        svc.update(db, uuid.uuid4(), ConsorcistaUpdate(cuit=CUIT_B_RAW))

        repo.get_by_cuit.assert_called_once()
        assert repo.get_by_cuit.call_args.args[1] == CUIT_B
        repo.update.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.parametrize(
        "target_id,owner_id",
        [(LOW_ID, HIGH_ID), (HIGH_ID, LOW_ID)],
        ids=["owner-above", "owner-below"],
    )
    def test_a_cuit_owned_by_somebody_else_is_409_and_writes_nothing(
        self, target_id: uuid.UUID, owner_id: uuid.UUID
    ) -> None:
        """Both orderings on purpose. ``uuid.UUID`` is orderable, so an owner
        check written as ``<`` or ``>`` instead of ``!=`` would still reject
        roughly half the conflicts and let the other half through — and with
        random ids it would do so intermittently."""
        svc, repo, db = _service()
        repo.get_by_id.return_value = SimpleNamespace(id=target_id)
        repo.get_by_cuit.return_value = SimpleNamespace(id=owner_id)

        with pytest.raises(HTTPException) as exc:
            svc.update(db, target_id, ConsorcistaUpdate(cuit=CUIT_B_RAW))

        assert exc.value.status_code == 409
        repo.update.assert_not_called()
        db.commit.assert_not_called()

    def test_re_sending_the_row_s_own_cuit_is_not_a_conflict(self) -> None:
        """The owner check compares VALUES, not object identity: the row the
        repository hands back is a different object from the id in the URL even
        when they denote the same consorcista."""
        svc, repo, db = _service()
        consorcista_id = uuid.uuid4()
        repo.get_by_id.return_value = SimpleNamespace(id=consorcista_id)
        repo.get_by_cuit.return_value = SimpleNamespace(id=uuid.UUID(str(consorcista_id)))
        repo.update.return_value = object()

        svc.update(db, consorcista_id, ConsorcistaUpdate(cuit=CUIT_B_RAW))

        repo.update.assert_called_once()
        db.commit.assert_called_once()

    def test_an_unknown_id_is_404_before_anything_else_happens(self) -> None:
        svc, repo, db = _service()
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.update(db, uuid.uuid4(), ConsorcistaUpdate(nombre="Ana"))

        assert exc.value.status_code == 404
        repo.update.assert_not_called()
        db.commit.assert_not_called()

    def test_a_row_that_vanishes_between_the_read_and_the_write_is_404(self) -> None:
        """Defensive branch: ``get_by_id`` succeeded but ``update`` came back
        empty. It must stay a 404 and must NOT commit."""
        svc, repo, db = _service()
        repo.get_by_id.return_value = SimpleNamespace(id=uuid.uuid4())
        repo.update.return_value = None

        with pytest.raises(HTTPException) as exc:
            svc.update(db, uuid.uuid4(), ConsorcistaUpdate(nombre="Ana"))

        assert exc.value.status_code == 404
        db.commit.assert_not_called()


# ===========================================================================
# PadronService — CSV / XLSX / XLS import
# ===========================================================================


def _csv(*lines: str, encoding: str = "utf-8") -> bytes:
    return ("\r\n".join(lines) + "\r\n").encode(encoding)


def _error_rows(result: dict[str, Any]) -> list[int]:
    return [entry["row"] for entry in result["errors"]]


def _created_schemas(repo: MagicMock) -> list[ConsorcistaCreate]:
    return [call.args[1] for call in repo.create.call_args_list]


class TestImportCsv:
    def test_a_clean_row_is_created_committed_and_counted(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _csv("nombre,apellido,cuit,hectareas", f"Ana,Diaz,{CUIT_A_RAW},12.5")

        result = svc.import_csv(db, content, "padron.csv")

        assert result == {"processed": 1, "created": 1, "skipped": 0, "errors": []}
        db.begin_nested.assert_called_once()
        db.commit.assert_called_once()
        schema = _created_schemas(repo)[0]
        assert (schema.nombre, schema.apellido, schema.cuit) == ("Ana", "Diaz", CUIT_A)
        assert schema.hectareas == 12.5

    def test_a_row_without_hectareas_stores_none_not_zero(self) -> None:
        """``0 ha`` and ``unknown ha`` are different facts about a parcel."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None

        svc.import_csv(db, _csv("nombre,apellido,cuit", f"Ana,Diaz,{CUIT_A_RAW}"), "p.csv")

        assert _created_schemas(repo)[0].hectareas is None

    @pytest.mark.parametrize(
        "row", [f",Diaz,{CUIT_A_RAW}", f"Ana,,{CUIT_A_RAW}", f",,{CUIT_A_RAW}"]
    )
    def test_a_row_missing_a_name_is_rejected_before_any_lookup(self, row: str) -> None:
        """Nombre AND apellido are both required: neither one alone is enough,
        and the rejection happens before the CUIT is even looked up."""
        svc, repo, db = _service()

        result = svc.import_csv(db, _csv("nombre,apellido,cuit", row), "padron.csv")

        assert (result["processed"], result["created"], result["skipped"]) == (1, 0, 1)
        assert _error_rows(result) == [2]
        repo.get_by_cuit.assert_not_called()
        repo.create.assert_not_called()
        db.commit.assert_not_called()

    def test_a_row_without_a_cuit_is_rejected_before_any_lookup(self) -> None:
        svc, repo, db = _service()

        result = svc.import_csv(db, _csv("nombre,apellido,cuit", "Ana,Diaz,"), "padron.csv")

        assert (result["processed"], result["created"], result["skipped"]) == (1, 0, 1)
        assert _error_rows(result) == [2]
        repo.get_by_cuit.assert_not_called()
        repo.create.assert_not_called()

    def test_a_cuit_repeated_inside_the_file_is_imported_once(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _csv(
            "nombre,apellido,cuit",
            f"Ana,Diaz,{CUIT_A_RAW}",
            f"Otro,Diaz,{CUIT_A_RAW}",
        )

        result = svc.import_csv(db, content, "padron.csv")

        assert (result["processed"], result["created"], result["skipped"]) == (2, 1, 1)
        assert _error_rows(result) == [3]
        assert repo.create.call_count == 1

    def test_a_cuit_already_in_the_padron_is_skipped(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = SimpleNamespace(id=uuid.uuid4())

        result = svc.import_csv(
            db, _csv("nombre,apellido,cuit", f"Ana,Diaz,{CUIT_A_RAW}"), "padron.csv"
        )

        assert (result["processed"], result["created"], result["skipped"]) == (1, 0, 1)
        assert _error_rows(result) == [2]
        repo.create.assert_not_called()
        db.commit.assert_not_called()

    def test_a_bad_row_never_stops_the_file(self) -> None:
        """Every rejection path has to CONTINUE, not abort: one malformed line in
        a 900-row spreadsheet must not silently truncate the import. Rows 2, 3, 5
        and 6 each trip a different guard, and rows 4 and 7 still land."""
        svc, repo, db = _service()
        repo.get_by_cuit.side_effect = lambda _db, cuit: (
            SimpleNamespace(id=uuid.uuid4()) if cuit == CUIT_C else None
        )
        content = _csv(
            "nombre,apellido,cuit",
            f",Diaz,{CUIT_A_RAW}",  # row 2 — no nombre
            "Ana,Diaz,",  # row 3 — no cuit
            f"Ana,Diaz,{CUIT_B_RAW}",  # row 4 — created
            f"Otro,Diaz,{CUIT_B_RAW}",  # row 5 — duplicate inside the file
            f"Ana,Diaz,{CUIT_C_RAW}",  # row 6 — already in the padron
            f"Luis,Perez,{CUIT_D_RAW}",  # row 7 — created
        )

        result = svc.import_csv(db, content, "padron.csv")

        assert (result["processed"], result["created"], result["skipped"]) == (6, 2, 4)
        assert _error_rows(result) == [2, 3, 5, 6]
        assert [schema.cuit for schema in _created_schemas(repo)] == [CUIT_B, CUIT_D]
        db.commit.assert_called_once()

    def test_an_invalid_check_digit_is_reported_as_a_row_error_not_a_crash(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _csv(
            "nombre,apellido,cuit",
            f"Ana,Diaz,{CUIT_WRONG_DV}",
            f"Luis,Perez,{CUIT_B_RAW}",
        )

        result = svc.import_csv(db, content, "padron.csv")

        assert (result["processed"], result["created"], result["skipped"]) == (2, 1, 1)
        assert _error_rows(result) == [2]

    def test_a_unique_violation_at_insert_time_is_reported_against_its_cuit(self) -> None:
        """The pre-checks can lose a race (or miss a constraint they do not model).
        The row must be reported as a duplicate — naming the offending CUIT, which
        is the only way the operator can find it in the spreadsheet — and the
        import must keep going."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        repo.create.side_effect = IntegrityError("INSERT INTO consorcistas", {}, Exception("dup"))

        result = svc.import_csv(
            db, _csv("nombre,apellido,cuit", f"Ana,Diaz,{CUIT_A_RAW}"), "padron.csv"
        )

        assert (result["processed"], result["created"], result["skipped"]) == (1, 0, 1)
        assert _error_rows(result) == [2]
        assert CUIT_A in result["errors"][0]["error"]
        db.commit.assert_not_called()

    def test_the_savepoint_is_per_row_so_one_failed_insert_does_not_eat_the_rest(
        self,
    ) -> None:
        """THE property the ``with db.begin_nested()`` inside the loop exists for.

        On real PostgreSQL a failed INSERT aborts the whole transaction: every
        statement after it dies with 25P02 until something rolls back. Without a
        savepoint per row, one duplicate in the middle of a spreadsheet silently
        drops every row after it — the import still reports success, the data is
        just not there. This project has already been bitten by that class of bug.

        ``begin_nested`` is therefore asserted with an EXACT count, not
        ``called``: hoisting the savepoint out of the loop (or dropping it) keeps
        every other assertion in this file green and only moves this number.
        """
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        # Row 3 is the one that trips the constraint; the rows around it are fine.
        repo.create.side_effect = [
            None,
            IntegrityError("INSERT INTO consorcistas", {}, Exception("dup")),
            None,
            None,
        ]
        content = _csv(
            "nombre,apellido,cuit",
            f"Ana,Diaz,{CUIT_A_RAW}",  # row 2 — created
            f"Otro,Diaz,{CUIT_B_RAW}",  # row 3 — unique violation at INSERT time
            f"Luis,Perez,{CUIT_C_RAW}",  # row 4 — created, AFTER the failure
            f"Eva,Sosa,{CUIT_D_RAW}",  # row 5 — created, AFTER the failure
        )

        result = svc.import_csv(db, content, "padron.csv")

        # (a) the rows after the failure still land
        assert (result["processed"], result["created"], result["skipped"]) == (4, 3, 1)
        # (b) one savepoint per row that reached the INSERT — the whole point
        assert db.begin_nested.call_count == 4
        # (c) the failure is reported against ITS row, and only that one
        assert _error_rows(result) == [3]
        assert CUIT_B in result["errors"][0]["error"]
        # every row was attempted; ``created`` counts only the ones that stuck
        assert [schema.cuit for schema in _created_schemas(repo)] == [
            CUIT_A,
            CUIT_B,
            CUIT_C,
            CUIT_D,
        ]
        db.commit.assert_called_once()

    def test_nothing_created_means_nothing_committed(self) -> None:
        svc, repo, db = _service()

        result = svc.import_csv(db, _csv("nombre,apellido,cuit", "Ana,Diaz,"), "padron.csv")

        assert result["created"] == 0
        db.commit.assert_not_called()

    def test_an_empty_file_is_a_no_op_not_an_error(self) -> None:
        svc, repo, db = _service()

        result = svc.import_csv(db, _csv("nombre,apellido,cuit"), "padron.csv")

        assert result == {"processed": 0, "created": 0, "skipped": 0, "errors": []}
        db.commit.assert_not_called()

    def test_unrecognised_columns_are_ignored_without_dropping_the_rest(self) -> None:
        """The unknown column comes FIRST on purpose: mapping has to skip it and
        carry on, not stop at the first thing it does not understand."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _csv("observaciones,nombre,apellido,cuit", f"sin datos,Ana,Diaz,{CUIT_A_RAW}")

        result = svc.import_csv(db, content, "padron.csv")

        assert result["created"] == 1
        assert _created_schemas(repo)[0].nombre == "Ana"

    def test_alias_headers_are_accepted(self) -> None:
        """Real spreadsheets say ``Nombres`` / ``Apellidos`` / ``CUIL``."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _csv("Nombres,Apellidos,CUIL,Superficie", f"Ana,Diaz,{CUIT_A_RAW},8")

        result = svc.import_csv(db, content, "padron.csv")

        assert result["created"] == 1
        schema = _created_schemas(repo)[0]
        assert (schema.nombre, schema.cuit, schema.hectareas) == ("Ana", CUIT_A, 8.0)


class TestImportCsvEncodings:
    ACCENTED = ("José", "Núñez")

    def _content(self, encoding: str) -> bytes:
        return _csv(
            "nombre,apellido,cuit",
            f"{self.ACCENTED[0]},{self.ACCENTED[1]},{CUIT_A_RAW}",
            encoding=encoding,
        )

    @pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "latin-1"])
    def test_accents_survive_every_supported_encoding(self, encoding: str) -> None:
        """The two encodings are tried in order and the FIRST one that decodes
        wins — decoding UTF-8 bytes a second time as Latin-1 would turn ``Núñez``
        into mojibake, and giving up after the first failure would reject every
        file Excel exports in Latin-1."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None

        result = svc.import_csv(db, self._content(encoding), "padron.csv")

        assert result["created"] == 1
        schema = _created_schemas(repo)[0]
        assert (schema.nombre, schema.apellido) == self.ACCENTED

    def test_a_byte_order_mark_does_not_poison_the_first_header(self) -> None:
        """Excel writes a BOM; without stripping it the first column reads as
        ``\\ufeffnombre`` and every row loses its name."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _csv("nombre,apellido,cuit", f"Ana,Diaz,{CUIT_A_RAW}", encoding="utf-8-sig")

        assert svc.import_csv(db, content, "padron.csv")["created"] == 1


def _xlsx_bytes(rows: list[list[Any]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestImportXlsx:
    def test_rows_are_read_and_numbered_from_the_second_spreadsheet_line(self) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _xlsx_bytes(
            [
                ["nombre", "apellido", "cuit", "hectareas"],
                ["", "Diaz", CUIT_A_RAW, 10],
                ["Ana", "Diaz", CUIT_B_RAW, 12.5],
            ]
        )

        result = svc.import_csv(db, content, "padron.xlsx")

        assert (result["processed"], result["created"], result["skipped"]) == (2, 1, 1)
        assert _error_rows(result) == [2]
        schema = _created_schemas(repo)[0]
        assert (schema.nombre, schema.cuit, schema.hectareas) == ("Ana", CUIT_B, 12.5)

    def test_an_xlsx_without_a_header_row_yields_nothing(self) -> None:
        svc, repo, db = _service()

        result = svc.import_csv(db, _xlsx_bytes([]), "padron.xlsx")

        assert (result["processed"], result["created"]) == (0, 0)

    def test_a_formula_cell_is_not_imported_as_its_own_source_text(self) -> None:
        """The workbook is opened for VALUES. A formula that openpyxl cannot
        evaluate has no cached value, so the row is reported as incomplete —
        importing the literal ``=1+1`` as somebody's name would be worse."""
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        content = _xlsx_bytes([["nombre", "apellido", "cuit"], ["=1+1", "Diaz", CUIT_A_RAW]])

        result = svc.import_csv(db, content, "padron.xlsx")

        assert (result["processed"], result["created"], result["skipped"]) == (1, 0, 1)
        repo.create.assert_not_called()

    def test_a_missing_openpyxl_is_a_domain_error_not_an_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc, repo, db = _service()
        monkeypatch.setitem(sys.modules, "openpyxl", None)

        with pytest.raises(ValueError):
            svc.import_csv(db, b"anything", "padron.xlsx")


class _FakeXlsSheet:
    """Minimal stand-in for ``xlrd.sheet.Sheet``.

    Legacy ``.xls`` is a binary format no maintained python library can WRITE, so
    the only way to exercise the reader branch without committing an opaque
    fixture is to fake the reader itself. Indexing semantics match xlrd's: rows
    and columns are 0-based lists, ``nrows``/``ncols`` are their sizes.
    """

    def __init__(self, rows: list[list[Any]]) -> None:
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max((len(row) for row in rows), default=0)

    def cell_value(self, row: int, col: int) -> Any:
        return self._rows[row][col]


def _install_fake_xlrd(monkeypatch: pytest.MonkeyPatch, sheets: list[_FakeXlsSheet]) -> None:
    book = SimpleNamespace(sheet_by_index=lambda index: sheets[index])
    monkeypatch.setitem(
        sys.modules, "xlrd", SimpleNamespace(open_workbook=lambda *, file_contents: book)
    )


#: Header + three data rows, two of which are incomplete on purpose.
_XLS_ROWS = [
    ["nombre", "apellido", "cuit"],
    ["", "Diaz", CUIT_A_RAW],
    ["Ana", "", CUIT_B_RAW],
    ["Luis", "Perez", CUIT_C_RAW],
]


class TestImportXls:
    def test_the_first_row_is_the_header_and_data_starts_at_line_two(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc, repo, db = _service()
        repo.get_by_cuit.return_value = None
        _install_fake_xlrd(
            monkeypatch,
            [_FakeXlsSheet(_XLS_ROWS), _FakeXlsSheet([["nombre"], ["Otra"]])],
        )

        result = svc.import_csv(db, b"xls-bytes", "padron.xls")

        assert (result["processed"], result["created"], result["skipped"]) == (3, 1, 2)
        assert _error_rows(result) == [2, 3]
        assert _created_schemas(repo)[0].cuit == CUIT_C

    def test_an_xls_without_data_rows_yields_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc, repo, db = _service()
        _install_fake_xlrd(monkeypatch, [_FakeXlsSheet([])])

        result = svc.import_csv(db, b"xls-bytes", "padron.xls")

        assert (result["processed"], result["created"]) == (0, 0)

    def test_a_missing_xlrd_is_a_domain_error_not_an_import_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        svc, repo, db = _service()
        monkeypatch.setitem(sys.modules, "xlrd", None)

        with pytest.raises(ValueError):
            svc.import_csv(db, b"anything", "padron.xls")


class TestImportFormatDispatch:
    def test_an_unsupported_extension_is_rejected_before_any_parsing(self) -> None:
        svc, repo, db = _service()

        with pytest.raises(ValueError):
            svc.import_csv(db, b"nombre,apellido,cuit\n", "padron.txt")

        repo.create.assert_not_called()
