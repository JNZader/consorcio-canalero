"""
Unit tests for betweenness_centrality in geo/routing.py.

NO database — mocks db.execute() to simulate pgRouting and NetworkX fallback.

Tests:
  - Mock pgRouting SQL results
  - NetworkX fallback when pgRouting raises
  - Empty network (no edges)
  - Timeout protection
  - Output format verification
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pgrouting_row(node_id: int, centrality: float) -> SimpleNamespace:
    """Simulate a pgr_betweennessCentrality result row."""
    return SimpleNamespace(
        node_id=node_id,
        centrality=centrality,
        geometry={"type": "Point", "coordinates": [0.0, 0.0]},
    )


def _make_edge_row(
    edge_id: int, source: int, target: int, cost: float
) -> SimpleNamespace:
    """Simulate a canal_network edge row."""
    return SimpleNamespace(id=edge_id, source=source, target=target, cost=cost)


def _make_vertex_row(vertex_id: int) -> SimpleNamespace:
    """Simulate a canal_network_vertices_pgr row."""
    return SimpleNamespace(
        id=vertex_id,
        geometry={"type": "Point", "coordinates": [vertex_id * 0.01, 0.0]},
    )


def _extract_sql_text(call_args) -> str:
    """Extract the raw SQL string from a mock db.execute() call.

    SQLAlchemy text() creates a TextClause; the SQL is in `.text`.
    """
    positional = call_args[0] if call_args[0] else ()
    if not positional:
        return ""
    obj = positional[0]
    # TextClause stores the SQL in .text attribute
    if hasattr(obj, "text"):
        return obj.text
    return str(obj)


# ---------------------------------------------------------------------------
# pgRouting path (happy path)
# ---------------------------------------------------------------------------


class TestBetweennessCentralityPgRouting:
    """Test the pgRouting-based centrality computation."""

    def test_returns_pgrouting_results(self):
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        pgrouting_rows = [
            _make_pgrouting_row(1, 0.85),
            _make_pgrouting_row(2, 0.60),
            _make_pgrouting_row(3, 0.30),
        ]
        mock_db.execute.return_value.fetchall.return_value = pgrouting_rows

        results = betweenness_centrality(mock_db, limit=10, timeout_seconds=60)

        assert len(results) == 3
        assert results[0]["node_id"] == 1
        assert results[0]["centrality"] == pytest.approx(0.85, abs=0.001)

    def test_sets_statement_timeout(self):
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        betweenness_centrality(mock_db, limit=5, timeout_seconds=30)

        # First call should set the timeout
        first_sql = _extract_sql_text(mock_db.execute.call_args_list[0])
        assert "statement_timeout" in first_sql
        assert "30s" in first_sql

    def test_output_format(self):
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            _make_pgrouting_row(42, 0.123456789),
        ]

        results = betweenness_centrality(mock_db, limit=10)

        assert len(results) == 1
        r = results[0]
        assert "node_id" in r
        assert "centrality" in r
        assert "geometry" in r
        assert isinstance(r["node_id"], int)
        assert isinstance(r["centrality"], float)
        # Centrality should be rounded to 6 decimals
        assert r["centrality"] == 0.123457

    def test_limit_is_passed_to_query(self):
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        betweenness_centrality(mock_db, limit=42)

        # The second call (pgr query) should have {"lim": 42}
        last_call = mock_db.execute.call_args_list[-1]
        params = last_call[0][1] if len(last_call[0]) > 1 else {}
        assert params.get("lim") == 42

    def test_empty_result_returns_empty_list(self):
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        results = betweenness_centrality(mock_db, limit=10)
        assert results == []


# ---------------------------------------------------------------------------
# NetworkX fallback
# ---------------------------------------------------------------------------


class TestBetweennessCentralityNetworkXFallback:
    """Test the NetworkX fallback when pgRouting is unavailable.

    networkx may not be installed in the test env, so we mock it.
    """

    def _create_mock_networkx(self):
        """Create a mock networkx module with Graph + betweenness_centrality."""
        mock_nx = MagicMock()

        # Real-ish Graph implementation for the tests
        class FakeGraph:
            def __init__(self):
                self._edges = []
                self._nodes = set()

            def add_edge(self, u, v, **kwargs):
                self._edges.append((u, v, kwargs))
                self._nodes.add(u)
                self._nodes.add(v)

        mock_nx.Graph = FakeGraph
        return mock_nx

    def _setup_fallback_mock(
        self,
        edges: list[SimpleNamespace],
        vertices: list[SimpleNamespace],
        centrality_result: dict[int, float] | None = None,
    ) -> tuple[MagicMock, MagicMock]:
        """Create mock db (pgRouting fails) and mock networkx module."""
        mock_db = MagicMock()
        mock_nx = self._create_mock_networkx()

        if centrality_result is not None:
            mock_nx.betweenness_centrality.return_value = centrality_result
        else:
            mock_nx.betweenness_centrality.return_value = {}

        def side_effect(sql, *args, **kwargs):
            result = MagicMock()
            sql_str = _extract_sql_text(((sql,), {}))

            if "statement_timeout" in sql_str:
                return result
            if "pgr_betweennessCentrality" in sql_str:
                raise Exception(
                    "function pgr_betweennesscentrality does not exist"
                )

            # NetworkX fallback: edge query
            if "canal_network" in sql_str and "source" in sql_str:
                result.fetchall.return_value = edges
                return result

            # NetworkX fallback: vertex geometry query
            if "canal_network_vertices_pgr" in sql_str:
                result.fetchall.return_value = vertices
                return result

            result.fetchall.return_value = []
            return result

        mock_db.execute.side_effect = side_effect
        return mock_db, mock_nx

    def test_falls_back_to_networkx(self):
        edges = [
            _make_edge_row(1, 1, 2, 10.0),
            _make_edge_row(2, 2, 3, 15.0),
            _make_edge_row(3, 1, 3, 25.0),
        ]
        vertices = [
            _make_vertex_row(1),
            _make_vertex_row(2),
            _make_vertex_row(3),
        ]
        centrality_result = {1: 0.0, 2: 0.5, 3: 0.0}

        mock_db, mock_nx = self._setup_fallback_mock(
            edges, vertices, centrality_result
        )

        with patch.dict(sys.modules, {"networkx": mock_nx}):
            # Force re-import so the patched module is picked up
            from app.domains.geo.routing import betweenness_centrality

            results = betweenness_centrality(mock_db, limit=10)

        assert len(results) > 0
        for r in results:
            assert "node_id" in r
            assert "centrality" in r
            assert "geometry" in r

    def test_networkx_empty_network(self):
        mock_db, mock_nx = self._setup_fallback_mock(
            edges=[], vertices=[], centrality_result={}
        )

        with patch.dict(sys.modules, {"networkx": mock_nx}):
            from app.domains.geo.routing import betweenness_centrality

            results = betweenness_centrality(mock_db, limit=10)

        assert results == []

    def test_networkx_output_sorted_descending(self):
        edges = [
            _make_edge_row(1, 1, 2, 1.0),
            _make_edge_row(2, 2, 3, 1.0),
            _make_edge_row(3, 3, 4, 1.0),
            _make_edge_row(4, 4, 5, 1.0),
        ]
        vertices = [_make_vertex_row(i) for i in range(1, 6)]
        # In a linear 1-2-3-4-5 graph, centrality roughly:
        # node 3 = 0.6, nodes 2,4 = 0.3, nodes 1,5 = 0.0
        centrality_result = {1: 0.0, 2: 0.3, 3: 0.6, 4: 0.3, 5: 0.0}

        mock_db, mock_nx = self._setup_fallback_mock(
            edges, vertices, centrality_result
        )

        with patch.dict(sys.modules, {"networkx": mock_nx}):
            from app.domains.geo.routing import betweenness_centrality

            results = betweenness_centrality(mock_db, limit=10)

        centralities = [r["centrality"] for r in results]
        assert centralities == sorted(centralities, reverse=True)

    def test_networkx_center_node_highest(self):
        """In a linear graph, the center node has the highest centrality."""
        edges = [
            _make_edge_row(1, 1, 2, 1.0),
            _make_edge_row(2, 2, 3, 1.0),
            _make_edge_row(3, 3, 4, 1.0),
            _make_edge_row(4, 4, 5, 1.0),
        ]
        vertices = [_make_vertex_row(i) for i in range(1, 6)]
        centrality_result = {1: 0.0, 2: 0.3, 3: 0.6, 4: 0.3, 5: 0.0}

        mock_db, mock_nx = self._setup_fallback_mock(
            edges, vertices, centrality_result
        )

        with patch.dict(sys.modules, {"networkx": mock_nx}):
            from app.domains.geo.routing import betweenness_centrality

            results = betweenness_centrality(mock_db, limit=10)

        assert len(results) > 0
        assert results[0]["node_id"] == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestBetweennessCentralityEdgeCases:

    def test_pgrouting_timeout_falls_back(self):
        """Simulate a statement_timeout cancellation falling back to empty."""
        mock_db = MagicMock()
        mock_nx = MagicMock()
        mock_nx.Graph.return_value = MagicMock()
        mock_nx.betweenness_centrality.return_value = {}

        def side_effect(sql, *args, **kwargs):
            sql_str = _extract_sql_text(((sql,), {}))

            if "statement_timeout" in sql_str:
                return MagicMock()
            if "pgr_betweennessCentrality" in sql_str:
                raise Exception(
                    "canceling statement due to statement timeout"
                )

            # Fallback edges query — return empty
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_db.execute.side_effect = side_effect

        with patch.dict(sys.modules, {"networkx": mock_nx}):
            from app.domains.geo.routing import betweenness_centrality

            results = betweenness_centrality(
                mock_db, limit=5, timeout_seconds=1
            )

        assert results == []

    def test_centrality_values_between_zero_and_one(self):
        """All centrality values should be in [0, 1]."""
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        rows = [
            _make_pgrouting_row(1, 0.0),
            _make_pgrouting_row(2, 0.5),
            _make_pgrouting_row(3, 1.0),
        ]
        mock_db.execute.return_value.fetchall.return_value = rows

        results = betweenness_centrality(mock_db, limit=10)

        for r in results:
            assert 0.0 <= r["centrality"] <= 1.0

    def test_default_timeout_is_120_seconds(self):
        """The default timeout_seconds parameter should be 120."""
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        betweenness_centrality(mock_db)

        first_sql = _extract_sql_text(mock_db.execute.call_args_list[0])
        assert "120s" in first_sql

    def test_default_limit_is_100(self):
        """The default limit parameter should be 100."""
        from app.domains.geo.routing import betweenness_centrality

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []

        betweenness_centrality(mock_db)

        last_call = mock_db.execute.call_args_list[-1]
        params = last_call[0][1] if len(last_call[0]) > 1 else {}
        assert params.get("lim") == 100
