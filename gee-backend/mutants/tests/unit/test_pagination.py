"""Unit tests for app.shared.pagination — PaginationParams and PaginatedResponse."""

import pytest
from pydantic import ValidationError

from app.shared.pagination import PaginatedResponse, PaginationParams


# ── PaginationParams ──────────────────────────────


class TestPaginationParams:
    """Tests for pagination query parameter validation and offset calc."""

    def test_defaults(self):
        params = PaginationParams()
        assert params.page == 1
        assert params.limit == 20

    def test_offset_page_1(self):
        params = PaginationParams(page=1, limit=20)
        assert params.offset == 0

    def test_offset_page_2(self):
        params = PaginationParams(page=2, limit=20)
        assert params.offset == 20

    def test_offset_page_5_limit_10(self):
        params = PaginationParams(page=5, limit=10)
        assert params.offset == 40

    def test_page_zero_rejected(self):
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_negative_page_rejected(self):
        with pytest.raises(ValidationError):
            PaginationParams(page=-1)

    def test_limit_zero_rejected(self):
        with pytest.raises(ValidationError):
            PaginationParams(limit=0)

    def test_limit_exceeds_max_rejected(self):
        with pytest.raises(ValidationError):
            PaginationParams(limit=101)

    def test_limit_at_max_boundary(self):
        params = PaginationParams(limit=100)
        assert params.limit == 100

    def test_limit_at_min_boundary(self):
        params = PaginationParams(limit=1)
        assert params.limit == 1

    def test_large_page_number(self):
        params = PaginationParams(page=999, limit=50)
        assert params.offset == 49900


# ── PaginatedResponse ─────────────────────────────


class TestPaginatedResponse:
    """Tests for the paginated response envelope and page calculation."""

    def test_create_basic(self):
        resp = PaginatedResponse.create(
            items=["a", "b", "c"], total=3, page=1, limit=20
        )
        assert resp.items == ["a", "b", "c"]
        assert resp.total == 3
        assert resp.page == 1
        assert resp.limit == 20
        assert resp.pages == 1

    def test_pages_calculation_exact(self):
        resp = PaginatedResponse.create(items=[], total=100, page=1, limit=10)
        assert resp.pages == 10

    def test_pages_calculation_remainder(self):
        resp = PaginatedResponse.create(items=[], total=101, page=1, limit=10)
        assert resp.pages == 11

    def test_pages_zero_total(self):
        resp = PaginatedResponse.create(items=[], total=0, page=1, limit=20)
        assert resp.pages == 0

    def test_pages_one_item(self):
        resp = PaginatedResponse.create(items=["x"], total=1, page=1, limit=20)
        assert resp.pages == 1

    def test_empty_items_list(self):
        resp = PaginatedResponse.create(items=[], total=50, page=3, limit=20)
        assert resp.items == []
        assert resp.total == 50
        assert resp.pages == 3

    def test_generic_type_with_dicts(self):
        items = [{"id": 1}, {"id": 2}]
        resp = PaginatedResponse.create(items=items, total=2, page=1, limit=10)
        assert resp.items == items
        assert resp.pages == 1
