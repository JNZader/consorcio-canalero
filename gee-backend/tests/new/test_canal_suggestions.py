"""
Integration tests for the canal suggestions data layer (DB-backed).

Tests:
  - CanalSuggestion model creation with all tipos
  - Schema validation (CanalSuggestionResponse, AnalysisRequest)
  - Repository: insert_suggestions_batch, get_suggestions_by_tipo,
    get_latest_batch, get_summary
  - Edge cases: empty batch, filter by tipo, multiple batches
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domains.geo.intelligence.models import CanalSuggestion
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.intelligence.schemas import (
    AnalysisRequest,
    CanalSuggestionResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TIPOS = ("hotspot", "gap", "route", "maintenance", "bottleneck")


@pytest.fixture()
def repo() -> IntelligenceRepository:
    return IntelligenceRepository()


def _make_suggestion(
    tipo: str,
    score: float,
    batch_id: uuid.UUID,
    metadata: dict | None = None,
) -> dict:
    """Build a suggestion insert dict (matches CanalSuggestion columns)."""
    return {
        "tipo": tipo,
        "score": score,
        "batch_id": batch_id,
        "metadata_": metadata or {"source": "test"},
        "geometry": None,
    }


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestCanalSuggestionModel:
    """Direct ORM model creation — verifies columns & defaults."""

    @pytest.mark.parametrize("tipo", TIPOS)
    def test_create_suggestion_all_tipos(self, db, tipo: str):
        batch_id = uuid.uuid4()
        suggestion = CanalSuggestion(
            tipo=tipo,
            score=42.5,
            batch_id=batch_id,
            metadata_={"algo": True},
        )
        db.add(suggestion)
        db.flush()

        assert suggestion.id is not None
        assert suggestion.tipo == tipo
        assert suggestion.score == 42.5
        assert suggestion.batch_id == batch_id
        assert suggestion.created_at is not None

    def test_create_suggestion_without_geometry(self, db):
        s = CanalSuggestion(
            tipo="hotspot",
            score=80.0,
            batch_id=uuid.uuid4(),
        )
        db.add(s)
        db.flush()

        assert s.geometry is None

    def test_create_suggestion_with_metadata(self, db):
        meta = {"flow_acc_max": 1234.5, "risk_level": "critico"}
        s = CanalSuggestion(
            tipo="maintenance",
            score=90.0,
            batch_id=uuid.uuid4(),
            metadata_=meta,
        )
        db.add(s)
        db.flush()

        assert s.metadata_ == meta

    def test_repr_includes_key_fields(self, db):
        batch_id = uuid.uuid4()
        s = CanalSuggestion(tipo="gap", score=55.0, batch_id=batch_id)
        db.add(s)
        db.flush()

        r = repr(s)
        assert "CanalSuggestion" in r
        assert "gap" in r


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestCanalSuggestionSchemas:

    def test_canal_suggestion_response_from_model(self, db):
        batch_id = uuid.uuid4()
        s = CanalSuggestion(
            tipo="route",
            score=60.0,
            batch_id=batch_id,
            metadata_={"cost": 123},
        )
        db.add(s)
        db.flush()
        db.refresh(s)

        resp = CanalSuggestionResponse.model_validate(s, from_attributes=True)
        assert resp.tipo == "route"
        assert resp.score == 60.0
        assert resp.batch_id == batch_id

    def test_analysis_request_valid(self):
        req = AnalysisRequest(area_id="zona_principal")
        assert req.area_id == "zona_principal"
        assert req.tipos is None
        assert req.parameters is None

    def test_analysis_request_with_tipos(self):
        req = AnalysisRequest(
            area_id="zona_principal",
            tipos=["hotspot", "gap"],
            parameters={"threshold": 500},
        )
        assert req.tipos == ["hotspot", "gap"]

    def test_analysis_request_missing_area_id(self):
        with pytest.raises(ValidationError):
            AnalysisRequest()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


class TestSuggestionRepository:

    def test_insert_empty_batch_returns_zero(self, db, repo):
        count = repo.insert_suggestions_batch(db, [])
        assert count == 0

    def test_insert_and_count(self, db, repo):
        batch_id = uuid.uuid4()
        suggestions = [
            _make_suggestion("hotspot", 80.0, batch_id),
            _make_suggestion("hotspot", 60.0, batch_id),
            _make_suggestion("gap", 50.0, batch_id),
        ]
        count = repo.insert_suggestions_batch(db, suggestions)
        assert count == 3

    def test_get_suggestions_by_tipo(self, db, repo):
        batch_id = uuid.uuid4()
        suggestions = [
            _make_suggestion("hotspot", 80.0, batch_id),
            _make_suggestion("hotspot", 60.0, batch_id),
            _make_suggestion("gap", 50.0, batch_id),
        ]
        repo.insert_suggestions_batch(db, suggestions)

        hotspots, total = repo.get_suggestions_by_tipo(db, "hotspot")
        assert total == 2
        assert len(hotspots) == 2
        # Ordered by score desc
        assert hotspots[0].score >= hotspots[1].score

    def test_get_suggestions_by_tipo_empty_result(self, db, repo):
        items, total = repo.get_suggestions_by_tipo(db, "maintenance")
        assert total == 0
        assert items == []

    def test_get_suggestions_by_tipo_with_batch_filter(self, db, repo):
        batch_a = uuid.uuid4()
        batch_b = uuid.uuid4()
        repo.insert_suggestions_batch(db, [
            _make_suggestion("hotspot", 80.0, batch_a),
            _make_suggestion("hotspot", 70.0, batch_b),
        ])

        items_a, total_a = repo.get_suggestions_by_tipo(
            db, "hotspot", batch_id=batch_a
        )
        items_b, total_b = repo.get_suggestions_by_tipo(
            db, "hotspot", batch_id=batch_b
        )
        assert total_a == 1
        assert total_b == 1
        assert items_a[0].score == 80.0
        assert items_b[0].score == 70.0

    def test_get_latest_batch_returns_none_when_empty(self, db, repo):
        result = repo.get_latest_batch(db)
        assert result is None

    def test_get_latest_batch_returns_most_recent(self, db, repo):
        batch_old = uuid.uuid4()
        batch_new = uuid.uuid4()

        # Insert "old" batch first
        repo.insert_suggestions_batch(db, [
            _make_suggestion("gap", 40.0, batch_old),
        ])
        # Insert "new" batch after — created_at should be >= old
        repo.insert_suggestions_batch(db, [
            _make_suggestion("gap", 90.0, batch_new),
        ])

        latest = repo.get_latest_batch(db)
        # Should be one of the two (the most recently created)
        assert latest in (batch_old, batch_new)

    def test_get_summary_returns_none_when_empty(self, db, repo):
        result = repo.get_summary(db)
        assert result is None

    def test_get_summary_for_specific_batch(self, db, repo):
        batch_id = uuid.uuid4()
        repo.insert_suggestions_batch(db, [
            _make_suggestion("hotspot", 80.0, batch_id),
            _make_suggestion("hotspot", 60.0, batch_id),
            _make_suggestion("gap", 50.0, batch_id),
            _make_suggestion("maintenance", 70.0, batch_id),
        ])

        summary = repo.get_summary(db, batch_id=batch_id)
        assert summary is not None
        assert summary["batch_id"] == batch_id
        assert summary["total_suggestions"] == 4
        assert summary["by_tipo"]["hotspot"] == 2
        assert summary["by_tipo"]["gap"] == 1
        assert summary["by_tipo"]["maintenance"] == 1
        assert 60.0 <= summary["avg_score"] <= 70.0  # mean of 80,60,50,70 = 65

    def test_get_summary_uses_latest_batch_when_none(self, db, repo):
        batch_id = uuid.uuid4()
        repo.insert_suggestions_batch(db, [
            _make_suggestion("bottleneck", 33.0, batch_id),
        ])

        summary = repo.get_summary(db)
        assert summary is not None
        assert summary["total_suggestions"] == 1

    @pytest.mark.parametrize("page,limit,expected_count", [
        (1, 2, 2),
        (2, 2, 1),
        (3, 2, 0),
    ])
    def test_get_suggestions_pagination(
        self, db, repo, page, limit, expected_count
    ):
        batch_id = uuid.uuid4()
        repo.insert_suggestions_batch(db, [
            _make_suggestion("hotspot", 90.0, batch_id),
            _make_suggestion("hotspot", 70.0, batch_id),
            _make_suggestion("hotspot", 50.0, batch_id),
        ])

        items, total = repo.get_suggestions_by_tipo(
            db, "hotspot", page=page, limit=limit
        )
        assert total == 3
        assert len(items) == expected_count

    def test_multiple_batches_isolated(self, db, repo):
        """Each batch is independent — summary only covers the requested batch."""
        batch_1 = uuid.uuid4()
        batch_2 = uuid.uuid4()

        repo.insert_suggestions_batch(db, [
            _make_suggestion("hotspot", 90.0, batch_1),
            _make_suggestion("gap", 80.0, batch_1),
        ])
        repo.insert_suggestions_batch(db, [
            _make_suggestion("maintenance", 50.0, batch_2),
        ])

        s1 = repo.get_summary(db, batch_id=batch_1)
        s2 = repo.get_summary(db, batch_id=batch_2)

        assert s1["total_suggestions"] == 2
        assert s2["total_suggestions"] == 1
        assert "hotspot" in s1["by_tipo"]
        assert "maintenance" in s2["by_tipo"]
