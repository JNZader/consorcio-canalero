"""Tests for the shared pagination helpers.

The ``pages`` field on ``PaginatedResponse`` is computed once at
construction time. The math has to be right — every list endpoint now
relies on it after F4-G, so a wrong rounding here would corrupt every
paginator widget on the frontend at once.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.shared.pagination import PaginatedResponse, PaginationParams


class _Item(BaseModel):
    id: int


class TestPaginationParamsOffset:
    def test_first_page_offset_is_zero(self):
        assert PaginationParams(page=1, limit=20).offset == 0

    def test_second_page_offset_is_limit(self):
        assert PaginationParams(page=2, limit=20).offset == 20

    def test_large_page_offset(self):
        assert PaginationParams(page=10, limit=50).offset == 450

    def test_rejects_zero_page(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PaginationParams(page=0, limit=20)

    def test_rejects_negative_page(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PaginationParams(page=-1, limit=20)

    def test_rejects_limit_over_100(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PaginationParams(page=1, limit=200)


class TestPaginatedResponseCreate:
    def test_empty_list_no_division_by_zero(self):
        """Edge case from F4-G review: empty page must not raise."""
        resp = PaginatedResponse[_Item].create(items=[], total=0, page=1, limit=20)
        assert resp.items == []
        assert resp.total == 0
        assert resp.pages == 0

    def test_exact_multiple(self):
        resp = PaginatedResponse[_Item].create(
            items=[_Item(id=i) for i in range(20)],
            total=100,
            page=1,
            limit=20,
        )
        assert resp.pages == 5

    def test_partial_last_page_rounds_up(self):
        """101 items, 20 per page → 6 pages (ceil(101/20)), not 5."""
        resp = PaginatedResponse[_Item].create(items=[], total=101, page=1, limit=20)
        assert resp.pages == 6

    def test_single_item(self):
        resp = PaginatedResponse[_Item].create(items=[_Item(id=1)], total=1, page=1, limit=20)
        assert resp.pages == 1

    def test_limit_one(self):
        resp = PaginatedResponse[_Item].create(items=[], total=7, page=1, limit=1)
        assert resp.pages == 7

    def test_zero_limit_yields_zero_pages_no_crash(self):
        """Defensive: ``limit > 0`` is enforced at the schema level, but
        the helper still must not divide by zero if called directly."""
        resp = PaginatedResponse[_Item].create(items=[], total=10, page=1, limit=0)
        assert resp.pages == 0

    def test_generic_type_preserved_in_serialisation(self):
        """``PaginatedResponse[Item]`` must serialise nested items via
        their Pydantic schema, not as opaque dicts. This is the whole
        point of the F4-G migration."""
        resp = PaginatedResponse[_Item].create(
            items=[_Item(id=1), _Item(id=2)], total=2, page=1, limit=20
        )
        dumped = resp.model_dump()
        assert dumped == {
            "items": [{"id": 1}, {"id": 2}],
            "total": 2,
            "page": 1,
            "limit": 20,
            "pages": 1,
        }
