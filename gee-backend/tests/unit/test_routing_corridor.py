from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import LineString


def _edge(
    edge_id: int,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    cost: float = 100.0,
    agg_cost: float | None = None,
    name: str = "Canal",
):
    return {
        "edge": edge_id,
        "path_seq": edge_id,
        "cost": cost,
        "agg_cost": cost if agg_cost is None else agg_cost,
        "nombre": name,
        "geometry": {
            "type": "LineString",
            "coordinates": [list(start), list(end)],
        },
    }


class TestBuildRouteFeatureCollection:
    def test_returns_geojson_features_with_edge_ids(self):
        from app.domains.geo.routing import build_route_feature_collection

        route = [
            _edge(1, (-63.0, -32.0), (-63.01, -32.01), cost=100.0, agg_cost=100.0),
            _edge(2, (-63.01, -32.01), (-63.02, -32.02), cost=120.0, agg_cost=220.0),
        ]

        geojson = build_route_feature_collection(route)

        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 2
        assert geojson["features"][0]["properties"]["edge_id"] == 1
        assert geojson["features"][1]["properties"]["agg_cost"] == 220.0


class TestBuildCorridorPolygon:
    def test_builds_polygon_feature_from_route_edges(self):
        from app.domains.geo.routing import build_corridor_polygon

        route = [
            _edge(1, (-63.0, -32.0), (-63.01, -32.01)),
            _edge(2, (-63.01, -32.01), (-63.02, -32.02)),
        ]

        corridor = build_corridor_polygon(route, width_m=50)

        assert corridor["type"] == "Feature"
        assert corridor["geometry"]["type"] in {"Polygon", "MultiPolygon"}
        assert corridor["properties"]["corridor_width_m"] == 50

    def test_returns_none_for_empty_route(self):
        from app.domains.geo.routing import build_corridor_polygon

        assert build_corridor_polygon([], width_m=50) is None


class TestCorridorRouting:
    def test_resolves_profile_defaults_for_hidraulico(self):
        from app.domains.geo.routing import resolve_routing_profile

        resolved = resolve_routing_profile("hidraulico")

        assert resolved == {
            "profile": "hidraulico",
            "corridor_width_m": 80.0,
            "alternative_count": 1,
            "penalty_factor": 2.0,
        }

    def test_profile_defaults_can_be_overridden(self):
        from app.domains.geo.routing import resolve_routing_profile

        resolved = resolve_routing_profile(
            "evitar_propiedad",
            corridor_width_m=120,
            alternative_count=4,
            penalty_factor=6.5,
        )

        assert resolved == {
            "profile": "evitar_propiedad",
            "corridor_width_m": 120.0,
            "alternative_count": 4,
            "penalty_factor": 6.5,
        }

    def test_merges_base_profile_and_alternative_penalties(self):
        from app.domains.geo.routing import merge_edge_factors

        assert merge_edge_factors({10: 0.8, 20: 1.3}, {20: 3.0, 30: 2.0}) == {
            10: 0.8,
            20: 3.9,
            30: 2.0,
        }

    def test_returns_centerline_corridor_and_alternatives(self):
        from app.domains.geo.routing import corridor_routing

        db = MagicMock()
        primary_route = [_edge(10, (-63.0, -32.0), (-63.1, -32.1), agg_cost=100.0)]
        alt_route = [_edge(11, (-63.0, -32.0), (-63.08, -32.08), agg_cost=120.0)]
        source = {"id": 1, "distance_m": 3.5}
        target = {"id": 2, "distance_m": 4.2}

        with (
            patch("app.domains.geo.routing.find_nearest_vertex", side_effect=[source, target]),
            patch(
                "app.domains.geo.routing.resolve_profile_edge_factors",
                return_value=(
                    {10: 0.82},
                    {
                        "parcel_intersections": 0,
                        "near_parcels": 0,
                        "avg_hydric_index": 82.0,
                        "hydraulic_edge_count": 1,
                        "profile_edge_count": 1,
                    },
                ),
            ),
            patch(
                "app.domains.geo.routing.shortest_path_with_penalties",
                return_value=primary_route,
            ),
            patch("app.domains.geo.routing.compute_route_alternatives", return_value=[alt_route]),
        ):
            result = corridor_routing(
                db,
                from_lon=-63.0,
                from_lat=-32.0,
                to_lon=-63.1,
                to_lat=-32.1,
                profile="hidraulico",
                corridor_width_m=60,
                alternative_count=1,
                penalty_factor=3.0,
            )

        assert result["summary"]["total_distance_m"] == 100.0
        assert result["summary"]["corridor_width_m"] == 60
        assert result["summary"]["profile"] == "hidraulico"
        assert result["summary"]["penalty_factor"] == 3.0
        assert result["summary"]["cost_breakdown"]["avg_hydric_index"] == 82.0
        assert result["summary"]["cost_breakdown"]["edge_count_with_profile_factor"] == 1
        assert result["centerline"]["type"] == "FeatureCollection"
        assert result["corridor"]["properties"]["corridor_width_m"] == 60
        assert len(result["alternatives"]) == 1
        assert result["alternatives"][0]["rank"] == 1
        assert result["alternatives"][0]["edge_ids"] == [11]

    def test_raises_when_no_vertices_found(self):
        from app.core.exceptions import NotFoundError
        from app.domains.geo.routing import corridor_routing

        db = MagicMock()

        with patch("app.domains.geo.routing.find_nearest_vertex", return_value=None):
            with pytest.raises(NotFoundError):
                corridor_routing(
                    db,
                    from_lon=-63.0,
                    from_lat=-32.0,
                    to_lon=-63.1,
                    to_lat=-32.1,
                    profile="balanceado",
                    corridor_width_m=50,
                    alternative_count=0,
                    penalty_factor=2.0,
                )

    def test_raster_mode_uses_multicriteria_corridor(self):
        from app.domains.geo.routing import corridor_routing

        db = MagicMock()
        with patch(
            "app.domains.geo.routing.raster_corridor_routing",
            return_value={
                "line": LineString([(-63.0, -32.0), (-63.08, -32.08)]),
                "total_distance_m": 1520.5,
                "cost_meta": {
                    "mode": "raster",
                    "weights": {"slope": 0.35, "hydric": 0.55, "property": 0.1},
                    "property_features": 3,
                    "hydric_features": 4,
                },
                "raster_source": "/tmp/slope.tif",
            },
        ):
            result = corridor_routing(
                db,
                from_lon=-63.0,
                from_lat=-32.0,
                to_lon=-63.08,
                to_lat=-32.08,
                mode="raster",
                profile="hidraulico",
                corridor_width_m=80,
                weight_overrides={"slope": 0.2, "hydric": 0.6, "property": 0.2},
            )

        assert result["summary"]["mode"] == "raster"
        assert result["summary"]["total_distance_m"] == 1520.5
        assert result["summary"]["cost_breakdown"]["weights"]["hydric"] == 0.55
        assert result["alternatives"] == []
        assert result["centerline"]["features"][0]["geometry"]["type"] == "LineString"


class TestCorridorEndpoint:
    def test_endpoint_returns_corridor_payload(self):
        from app.domains.geo.router import CorridorRoutingRequest, calculate_corridor_route

        body = CorridorRoutingRequest(
            from_lon=-63.0,
            from_lat=-32.0,
            to_lon=-63.1,
            to_lat=-32.1,
            mode="raster",
            area_id="zona_principal",
            profile="evitar_propiedad",
            corridor_width_m=75,
            alternative_count=1,
            penalty_factor=2.5,
        )

        expected = {
            "summary": {
                "profile": "evitar_propiedad",
                "mode": "raster",
                "corridor_width_m": 75,
                "penalty_factor": 2.5,
                "total_distance_m": 100.0,
                "edges": 1,
                "cost_breakdown": {"profile": "evitar_propiedad"},
            },
            "centerline": {"type": "FeatureCollection", "features": []},
            "corridor": {
                "type": "Feature",
                "properties": {"corridor_width_m": 75},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
            "alternatives": [],
            "source": {"id": 1},
            "target": {"id": 2},
        }

        with patch(
            "app.domains.geo.routing.corridor_routing",
            return_value=expected,
            create=True,
        ) as corridor_mock:
            result = calculate_corridor_route(body, MagicMock(), _user=MagicMock())

        assert result == expected
        corridor_mock.assert_called_once()
        assert corridor_mock.call_args.kwargs["profile"] == "evitar_propiedad"
        assert corridor_mock.call_args.kwargs["mode"] == "raster"
        assert corridor_mock.call_args.kwargs["area_id"] == "zona_principal"

    def test_save_scenario_persists_payload(self):
        from app.domains.geo.router_hydrology_routing import (
            CorridorScenarioSaveRequest,
            save_corridor_scenario,
        )

        db = MagicMock()
        repo = MagicMock()
        scenario = MagicMock()
        repo.create_routing_scenario.return_value = scenario

        body = CorridorScenarioSaveRequest(
            name="Escenario Norte",
            profile="balanceado",
            request_payload={"from_lon": -63.0, "to_lon": -63.1},
            result_payload={"summary": {"profile": "balanceado"}},
            notes="Prueba",
        )

        result = save_corridor_scenario(
            body,
            db,
            _user=MagicMock(id="user-1"),
            repo=repo,
        )

        assert result is scenario
        repo.create_routing_scenario.assert_called_once()
        assert repo.create_routing_scenario.call_args.kwargs["name"] == "Escenario Norte"
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(scenario)

    def test_export_scenario_geojson_flattens_saved_payload(self):
        from app.domains.geo.router_hydrology_routing import export_corridor_scenario_geojson

        repo = MagicMock()
        repo.get_routing_scenario.return_value = MagicMock(
            result_payload={
                "centerline": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": []},
                            "properties": {},
                        }
                    ],
                },
                "corridor": {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": []},
                    "properties": {},
                },
                "alternatives": [
                    {
                        "rank": 1,
                        "geojson": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "LineString",
                                        "coordinates": [],
                                    },
                                    "properties": {},
                                }
                            ],
                        },
                    }
                ],
            }
        )

        result = export_corridor_scenario_geojson(
            uuid.uuid4(),
            MagicMock(),
            _user=MagicMock(),
            repo=repo,
        )

        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 3
        assert {f["properties"]["route_role"] for f in result["features"]} == {
            "centerline",
            "corridor",
            "alternative",
        }

    def test_approve_scenario_marks_it_approved(self):
        from app.domains.geo.router_hydrology_routing import approve_corridor_scenario

        db = MagicMock()
        repo = MagicMock()
        scenario = MagicMock()
        repo.approve_routing_scenario.return_value = scenario

        result = approve_corridor_scenario(
            uuid.uuid4(),
            db,
            _user=MagicMock(id="user-1"),
            repo=repo,
        )

        assert result is scenario
        repo.approve_routing_scenario.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(scenario)

    def test_unapprove_and_favorite_scenario_update_state(self):
        from app.domains.geo.router_hydrology_routing import (
            CorridorScenarioFavoriteRequest,
            unapprove_corridor_scenario,
            favorite_corridor_scenario,
        )

        db = MagicMock()
        repo = MagicMock()
        scenario = MagicMock(id=uuid.uuid4())
        repo.unapprove_routing_scenario.return_value = scenario
        repo.set_routing_scenario_favorite.return_value = scenario
        repo.list_routing_scenario_approval_events.return_value = []

        unapproved = unapprove_corridor_scenario(
            uuid.uuid4(),
            db,
            _user=MagicMock(id="user-1"),
            repo=repo,
        )
        favorited = favorite_corridor_scenario(
            uuid.uuid4(),
            db,
            _user=MagicMock(id="user-1"),
            repo=repo,
            body=CorridorScenarioFavoriteRequest(is_favorite=True),
        )

        assert unapproved is scenario
        assert favorited is scenario
        repo.unapprove_routing_scenario.assert_called_once()
        repo.set_routing_scenario_favorite.assert_called_once()

    def test_export_scenario_pdf_streams_pdf_document(self):
        from app.domains.geo.router_hydrology_routing import export_corridor_scenario_pdf

        repo = MagicMock()
        repo.get_routing_scenario.return_value = MagicMock(
            id=uuid.uuid4(),
            name="Escenario PDF",
            profile="balanceado",
            request_payload={},
            result_payload={"summary": {"profile": "balanceado"}},
            approved_by_id=None,
        )

        with (
            patch(
                "app.shared.pdf.build_corridor_routing_pdf",
                return_value=MagicMock(),
            ),
            patch("app.shared.pdf.get_branding", return_value=MagicMock()),
            patch(
                "app.domains.geo.router_hydrology_routing._get_user_display_name",
                return_value=None,
            ),
        ):
            response = export_corridor_scenario_pdf(
                uuid.uuid4(),
                MagicMock(),
                _user=MagicMock(),
                repo=repo,
            )

        assert response.media_type == "application/pdf"
        assert "attachment; filename=" in response.headers["content-disposition"]
