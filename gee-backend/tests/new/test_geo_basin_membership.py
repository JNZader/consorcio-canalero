"""Contract tests for protected basin-to-catastro membership evidence."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth import require_admin_or_operator
from app.domains.geo.intelligence.repository import IntelligenceRepository
from app.domains.geo.router_basins_bundle import (
    get_basin_catastro_membership,
    router,
)

def _scalar_result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)

def _names_result(names):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: names))

def test_repository_uses_interior_intersection_and_returns_sorted_distinct_nomenclaturas():
    basin_id = uuid.uuid4()
    db = MagicMock()
    db.execute.side_effect = [
        _scalar_result(True),
        _names_result(["19-01-003", "19-01-001", "19-01-001"]),
    ]

    result = IntelligenceRepository().get_catastro_membership_by_basin(db, basin_id)

    assert result == ["19-01-001", "19-01-003"]
    membership_statement = db.execute.call_args_list[1].args[0]
    compiled_sql = str(membership_statement)
    assert "parcelas_catastro.nomenclatura" in compiled_sql
    assert "ST_Relate" in compiled_sql
    assert "T********" in compiled_sql
    assert "DISTINCT" in compiled_sql
    assert "ORDER BY parcelas_catastro.nomenclatura" in compiled_sql

def test_repository_distinguishes_unknown_basin_from_empty_membership():
    db = MagicMock()
    db.execute.return_value = _scalar_result(None)

    result = IntelligenceRepository().get_catastro_membership_by_basin(db, uuid.uuid4())

    assert result is None
    db.execute.assert_called_once()

def test_endpoint_returns_only_the_wire_contract_for_an_empty_membership():
    basin_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_catastro_membership_by_basin.return_value = []

    response = get_basin_catastro_membership(
        basin_id,
        db=MagicMock(),
        repo=repo,
        _user=MagicMock(),
    )

    assert response.model_dump(mode="json") == {
        "basin_id": str(basin_id),
        "feature_id_property": "nomenclatura",
        "intersecting_feature_ids": [],
    }

def test_endpoint_returns_404_for_an_unknown_basin():
    repo = MagicMock()
    repo.get_catastro_membership_by_basin.return_value = None

    with pytest.raises(HTTPException) as raised:
        get_basin_catastro_membership(
            uuid.uuid4(), db=MagicMock(), repo=repo, _user=MagicMock()
        )

    assert raised.value.status_code == 404
    assert raised.value.detail == "Cuenca operativa no encontrada"

def test_endpoint_requires_admin_or_operator_authentication():
    route = next(item for item in router.routes if item.path == "/basins/{basin_id}/catastro-membership")

    assert route.dependant.dependencies[-1].call is require_admin_or_operator
