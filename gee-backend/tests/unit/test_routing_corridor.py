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
                    "weights": {"slope": 0.3, "hydric": 0.45, "property": 0.1, "landcover": 0.15},
                    "property_features": 3,
                    "hydric_features": 4,
                    "landcover_features": 12,
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
                weight_overrides={"slope": 0.2, "hydric": 0.5, "property": 0.15, "landcover": 0.15},
            )

        assert result["summary"]["mode"] == "raster"
        assert result["summary"]["total_distance_m"] == 1520.5
        assert result["summary"]["cost_breakdown"]["weights"]["hydric"] == 0.45
        assert result["summary"]["cost_breakdown"]["weights"]["landcover"] == 0.15
        assert result["alternatives"] == []
        assert result["centerline"]["features"][0]["geometry"]["type"] == "LineString"

    def test_raster_mode_projects_points_to_raster_crs(self):
        from app.domains.geo.routing_raster_support import raster_corridor_routing

        db = MagicMock()
        fake_src = MagicMock()
        fake_src.__enter__.return_value = fake_src
        fake_src.__exit__.return_value = None
        fake_src.crs.to_epsg.return_value = 32720

        with (
            patch(
                "app.domains.geo.routing_raster_support.get_latest_slope_raster_path",
                return_value="/tmp/slope.tif",
            ),
            patch(
                "app.domains.geo.routing_raster_support.build_multicriteria_cost_surface",
                return_value=("/tmp/cost.tif", {"mode": "raster", "weights": {}}),
            ),
            patch("rasterio.open", return_value=fake_src),
            patch(
                "app.domains.geo.routing_raster_support.cost_distance",
            ) as cost_distance_mock,
            patch(
                "app.domains.geo.routing_raster_support.least_cost_path",
                return_value=LineString([(500000, 6400000), (500100, 6400100)]),
            ),
        ):
            raster_corridor_routing(
                db,
                from_lon=-63.0,
                from_lat=-32.0,
                to_lon=-63.01,
                to_lat=-32.01,
                profile="balanceado",
                corridor_width_m=50,
            )

        source_point = cost_distance_mock.call_args.args[1][0]
        assert source_point[0] > 1000
        assert source_point[1] > 1000


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


class TestAutoCorridorAnalysis:
    def test_generates_unique_candidates_from_prioritized_zones(self):
        from app.domains.geo.routing_auto_analysis import (
            generate_auto_corridor_candidates,
        )

        zones = [
            {
                "id": "z1",
                "nombre": "Zona 1",
                "cuenca": "A",
                "priority_score": 91.0,
                "hydric_score": 90.0,
                "flood_score": 80.0,
                "risk_level": "critico",
                "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                "nearest_network_point": {"type": "Point", "coordinates": [-63.005, -32.002]},
                "distance_to_network_m": 240.0,
            },
            {
                "id": "z2",
                "nombre": "Zona 2",
                "cuenca": "A",
                "priority_score": 80.0,
                "hydric_score": 75.0,
                "flood_score": 62.0,
                "risk_level": "alto",
                "point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                "nearest_network_point": {"type": "Point", "coordinates": [-63.012, -32.011]},
                "distance_to_network_m": 180.0,
            },
            {
                "id": "z3",
                "nombre": "Zona 3",
                "cuenca": "A",
                "priority_score": 0.0,
                "hydric_score": 0.0,
                "flood_score": 0.0,
                "risk_level": "desconocido",
                "point": {"type": "Point", "coordinates": [-63.05, -32.04]},
                "nearest_network_point": {"type": "Point", "coordinates": [-63.051, -32.041]},
                "distance_to_network_m": 100.0,
            },
        ]

        candidates = generate_auto_corridor_candidates(zones, max_candidates=2)

        assert len(candidates) == 2
        assert candidates[0]["candidate_type"] == "zone_to_network"
        assert candidates[0]["source_zone_id"] == "z1"
        assert candidates[0]["target_zone_id"] == "network"
        assert len({item["candidate_id"] for item in candidates}) == len(candidates)

    def test_auto_analysis_marks_unroutable_candidates_explicitly(self):
        from app.domains.geo.routing_auto_analysis import auto_analyze_corridors

        db = MagicMock()
        routed_payload = {
            "summary": {
                "edges": 2,
                "total_distance_m": 1200.0,
                "cost_breakdown": {
                    "avg_profile_factor": 1.1,
                    "avg_hydric_index": 75.0,
                    "parcel_intersections": 1,
                    "near_parcels": 4,
                },
            },
            "centerline": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature"}],
            },
            "corridor": {"type": "Feature", "geometry": {"type": "Polygon"}},
            "alternatives": [],
        }
        unroutable_payload = {
            "summary": {
                "edges": 0,
                "total_distance_m": 0.0,
                "cost_breakdown": {"avg_profile_factor": 1.0},
            },
            "centerline": {"type": "FeatureCollection", "features": []},
            "corridor": None,
            "alternatives": [],
        }

        with (
            patch(
                "app.domains.geo.routing_auto_analysis.load_auto_analysis_zones",
                return_value=[
                    {
                        "id": "z1",
                        "nombre": "Zona 1",
                        "cuenca": "A",
                        "priority_score": 90.0,
                        "hydric_score": 90.0,
                        "flood_score": 80.0,
                        "risk_level": "critico",
                        "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.005, -32.002]},
                        "distance_to_network_m": 200.0,
                    },
                    {
                        "id": "z2",
                        "nombre": "Zona 2",
                        "cuenca": "A",
                        "priority_score": 80.0,
                        "hydric_score": 75.0,
                        "flood_score": 70.0,
                        "risk_level": "alto",
                        "point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.012, -32.011]},
                        "distance_to_network_m": 300.0,
                    },
                    {
                        "id": "z3",
                        "nombre": "Zona 3",
                        "cuenca": "A",
                        "priority_score": 70.0,
                        "hydric_score": 50.0,
                        "flood_score": 55.0,
                        "risk_level": "medio",
                        "point": {"type": "Point", "coordinates": [-63.03, -32.03]},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.031, -32.032]},
                        "distance_to_network_m": 400.0,
                    },
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.corridor_routing",
                side_effect=[routed_payload, unroutable_payload, unroutable_payload],
            ),
        ):
            result = auto_analyze_corridors(
                db,
                scope_type="consorcio",
                scope_id=None,
                mode="network",
                profile="balanceado",
                max_candidates=2,
            )

        assert result["summary"]["generated_candidates"] >= 2
        assert result["summary"]["routed_candidates"] == 1
        assert result["summary"]["unroutable_candidates"] >= 1
        assert result["candidates"][0]["status"] == "routed"
        assert result["candidates"][0]["score"] > 0
        assert result["candidates"][1]["status"] == "unroutable"
        assert (
            result["candidates"][1]["ranking_breakdown"]["explanation"]
            == "No se encontró una ruta útil sobre el ámbito seleccionado."
        )

    def test_auto_analysis_falls_back_to_gap_seed_candidates(self):
        from app.domains.geo.routing_auto_analysis import auto_analyze_corridors

        db = MagicMock()
        routed_payload = {
            "summary": {
                "mode": "raster",
                "profile": "balanceado",
                "total_distance_m": 950.0,
                "edges": 1,
                "corridor_width_m": 50,
                "cost_breakdown": {"avg_profile_factor": 1.1},
            },
            "centerline": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-63.0, -32.0], [-63.01, -32.01]]}, "properties": {}}],
            },
            "corridor": None,
            "alternatives": [],
        }

        with (
            patch(
                "app.domains.geo.routing_auto_analysis.load_auto_analysis_zones",
                return_value=[
                    {
                        "id": "z1",
                        "nombre": "Zona 1",
                        "cuenca": "A",
                        "priority_score": 0.0,
                        "hydric_score": 0.0,
                        "flood_score": 0.0,
                        "risk_level": "desconocido",
                        "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                        "distance_to_network_m": 250.0,
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.generate_auto_corridor_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_suggestion_seed_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_gap_seed_candidates",
                return_value=[
                    {
                        "candidate_id": "z1::gapcalc::network",
                        "candidate_type": "gap_to_network",
                        "source_zone_id": "z1",
                        "source_zone_name": "Zona 1",
                        "target_zone_id": "network",
                        "target_zone_name": "Red existente",
                        "from_lon": -63.0,
                        "from_lat": -32.0,
                        "to_lon": -63.01,
                        "to_lat": -32.01,
                        "zone_pair_distance_deg": 0.01,
                        "network_distance_m": 250.0,
                        "priority_score": 62.0,
                        "reason": "Descargar gap alto detectado en Zona 1 hacia la red existente más cercana en A",
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.corridor_routing",
                return_value=routed_payload,
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._centerline_overlap_metrics",
                return_value={"existing_network_overlap_m": 20.0, "overlap_ratio": 0.1},
            ),
        ):
            result = auto_analyze_corridors(
                db,
                scope_type="consorcio",
                scope_id=None,
                mode="raster",
                profile="balanceado",
                max_candidates=3,
            )

        assert result["summary"]["returned_candidates"] >= 1
        assert any(candidate["candidate_type"] == "gap_to_network" for candidate in result["candidates"])
        gap_candidate = next(candidate for candidate in result["candidates"] if candidate["candidate_type"] == "gap_to_network")
        assert gap_candidate["status"] == "routed"
        assert gap_candidate["score"] > 0

    def test_gap_seed_candidates_use_proxy_signal_when_real_scores_are_empty(self):
        from app.domains.geo.routing_auto_analysis import _build_gap_seed_candidates

        db = MagicMock()
        zones = [
            {
                "id": "z1",
                "nombre": "Zona 1",
                "cuenca": "A",
                "priority_score": 0.0,
                "hydric_score": 0.0,
                "flood_score": 0.0,
                "risk_level": "desconocido",
                "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                "geometry": {"type": "Polygon", "coordinates": []},
                "nearest_network_point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                "distance_to_network_m": 240.0,
            }
        ]

        with (
            patch(
                "app.domains.geo.intelligence.suggestions._load_canal_geometries",
                return_value=[{"id": 1, "geometry": {"type": "LineString", "coordinates": [[-63.02, -32.02], [-63.01, -32.01]]}}],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._load_proxy_hydric_scores",
                return_value={"z1": 58.0},
            ) as proxy_mock,
            patch(
                "app.domains.geo.intelligence.calculations.detect_coverage_gaps",
                return_value=[
                    {
                        "zone_id": "z1",
                        "geometry": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "severity": "alto",
                        "hci_score": 58.0,
                    }
                ],
            ),
        ):
            seeds = _build_gap_seed_candidates(db, zones, max_candidates=3)

        proxy_mock.assert_called_once()
        assert len(seeds) == 1
        assert seeds[0]["candidate_type"] == "gap_to_network"
        assert seeds[0]["priority_score"] == 58.0
        assert "gap alto" in seeds[0]["reason"]

    def test_auto_analysis_falls_back_to_flow_acc_hotspots_before_distance_only(self):
        from app.domains.geo.routing_auto_analysis import auto_analyze_corridors

        db = MagicMock()
        routed_payload = {
            "summary": {
                "mode": "raster",
                "profile": "hidraulico",
                "total_distance_m": 880.0,
                "edges": 1,
                "corridor_width_m": 50,
                "cost_breakdown": {"avg_profile_factor": 1.0},
            },
            "centerline": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-63.0, -32.0], [-63.01, -32.01]]}, "properties": {}}],
            },
            "corridor": None,
            "alternatives": [],
        }

        with (
            patch(
                "app.domains.geo.routing_auto_analysis.load_auto_analysis_zones",
                return_value=[
                    {
                        "id": "z1",
                        "nombre": "Zona 1",
                        "cuenca": "A",
                        "priority_score": 0.0,
                        "hydric_score": 0.0,
                        "flood_score": 0.0,
                        "risk_level": "desconocido",
                        "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                        "distance_to_network_m": 500.0,
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.generate_auto_corridor_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_suggestion_seed_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_gap_seed_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_flow_acc_hotspot_candidates",
                return_value=[
                    {
                        "candidate_id": "z1::flowacc::network",
                        "candidate_type": "flowacc_hotspot_to_network",
                        "source_zone_id": "z1",
                        "source_zone_name": "Zona 1",
                        "target_zone_id": "network",
                        "target_zone_name": "Red existente",
                        "from_lon": -63.0,
                        "from_lat": -32.0,
                        "to_lon": -63.01,
                        "to_lat": -32.01,
                        "zone_pair_distance_deg": 0.01,
                        "network_distance_m": 500.0,
                        "priority_score": 71.0,
                        "reason": "Descargar hotspot de escorrentía en Zona 1 hacia la red existente más cercana (flow_acc=8200)",
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.corridor_routing",
                return_value=routed_payload,
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._centerline_overlap_metrics",
                return_value={"existing_network_overlap_m": 10.0, "overlap_ratio": 0.05},
            ),
        ):
            result = auto_analyze_corridors(
                db,
                scope_type="consorcio",
                scope_id=None,
                mode="raster",
                profile="hidraulico",
                max_candidates=3,
            )

        assert result["summary"]["returned_candidates"] >= 1
        assert result["candidates"][0]["candidate_type"] == "flowacc_hotspot_to_network"
        assert "hotspot de escorrentía" in result["candidates"][0]["ranking_breakdown"]["explanation"]

    def test_auto_analysis_does_not_mix_distance_fillers_when_hydraulic_candidates_exist(self):
        from app.domains.geo.routing_auto_analysis import auto_analyze_corridors

        db = MagicMock()
        routed_payload = {
            "summary": {
                "mode": "raster",
                "profile": "hidraulico",
                "total_distance_m": 700.0,
                "edges": 1,
                "corridor_width_m": 50,
                "cost_breakdown": {"avg_profile_factor": 1.0},
            },
            "centerline": {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-63.0, -32.0], [-63.01, -32.01]]}, "properties": {}}],
            },
            "corridor": None,
            "alternatives": [],
        }

        with (
            patch(
                "app.domains.geo.routing_auto_analysis.load_auto_analysis_zones",
                return_value=[
                    {
                        "id": "z1",
                        "nombre": "Zona 1",
                        "cuenca": "A",
                        "priority_score": 0.0,
                        "hydric_score": 0.0,
                        "flood_score": 0.0,
                        "risk_level": "desconocido",
                        "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                        "distance_to_network_m": 500.0,
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.generate_auto_corridor_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_suggestion_seed_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_gap_seed_candidates",
                return_value=[],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_flow_acc_hotspot_candidates",
                return_value=[
                    {
                        "candidate_id": "z1::flowacc::network",
                        "candidate_type": "flowacc_hotspot_to_network",
                        "source_zone_id": "z1",
                        "source_zone_name": "Zona 1",
                        "target_zone_id": "network",
                        "target_zone_name": "Red existente",
                        "from_lon": -63.0,
                        "from_lat": -32.0,
                        "to_lon": -63.01,
                        "to_lat": -32.01,
                        "zone_pair_distance_deg": 0.01,
                        "network_distance_m": 500.0,
                        "priority_score": 71.0,
                        "reason": "Descargar hotspot de escorrentía en Zona 1 hacia la red existente más cercana (flow_acc=8200)",
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._build_distance_fallback_candidates",
                return_value=[
                    {
                        "candidate_id": "z1::distance::network",
                        "candidate_type": "distance_to_network",
                        "source_zone_id": "z1",
                        "source_zone_name": "Zona 1",
                        "target_zone_id": "network",
                        "target_zone_name": "Red existente",
                        "from_lon": -63.0,
                        "from_lat": -32.0,
                        "to_lon": -63.01,
                        "to_lat": -32.01,
                        "zone_pair_distance_deg": 0.01,
                        "network_distance_m": 500.0,
                        "priority_score": 60.0,
                        "reason": "Descargar Zona 1 hacia la red existente más cercana por aislamiento territorial (500 m)",
                    }
                ],
            ) as distance_mock,
            patch(
                "app.domains.geo.routing_auto_analysis.corridor_routing",
                return_value=routed_payload,
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._centerline_overlap_metrics",
                return_value={"existing_network_overlap_m": 10.0, "overlap_ratio": 0.05},
            ),
        ):
            result = auto_analyze_corridors(
                db,
                scope_type="consorcio",
                scope_id=None,
                mode="raster",
                profile="hidraulico",
                max_candidates=5,
            )

        distance_mock.assert_not_called()
        assert all(candidate["candidate_type"] != "distance_to_network" for candidate in result["candidates"])

    def test_auto_analysis_excludes_routes_that_overlap_existing_network_too_much(self):
        from app.domains.geo.routing_auto_analysis import auto_analyze_corridors

        db = MagicMock()
        routed_payload = {
            "summary": {
                "mode": "raster",
                "profile": "balanceado",
                "total_distance_m": 1200.0,
                "edges": 1,
                "corridor_width_m": 50,
                "cost_breakdown": {},
            },
            "centerline": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-63.0, -32.0], [-63.02, -32.02]],
                        },
                        "properties": {},
                    }
                ],
            },
            "corridor": None,
            "alternatives": [],
        }

        with (
            patch(
                "app.domains.geo.routing_auto_analysis.load_auto_analysis_zones",
                return_value=[
                    {
                        "id": "z1",
                        "nombre": "Zona 1",
                        "cuenca": "A",
                        "priority_score": 90.0,
                        "hydric_score": 90.0,
                        "flood_score": 80.0,
                        "risk_level": "critico",
                        "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.005, -32.002]},
                        "distance_to_network_m": 220.0,
                    },
                    {
                        "id": "z2",
                        "nombre": "Zona 2",
                        "cuenca": "A",
                        "priority_score": 80.0,
                        "hydric_score": 75.0,
                        "flood_score": 70.0,
                        "risk_level": "alto",
                        "point": {"type": "Point", "coordinates": [-63.02, -32.02]},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.021, -32.021]},
                        "distance_to_network_m": 260.0,
                    },
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.corridor_routing",
                return_value=routed_payload,
            ),
            patch(
                "app.domains.geo.routing_auto_analysis._centerline_overlap_metrics",
                return_value={"existing_network_overlap_m": 1000.0, "overlap_ratio": 0.92},
            ),
        ):
            result = auto_analyze_corridors(
                db,
                scope_type="consorcio",
                scope_id=None,
                mode="raster",
                profile="balanceado",
                max_candidates=5,
            )

        assert result["summary"]["generated_candidates"] >= 1
        assert result["summary"]["returned_candidates"] == 0
        assert result["candidates"] == []

    def test_auto_analysis_downgrades_not_found_raster_candidates_to_unroutable(self):
        from app.core.exceptions import NotFoundError
        from app.domains.geo.routing_auto_analysis import auto_analyze_corridors

        db = MagicMock()

        with (
            patch(
                "app.domains.geo.routing_auto_analysis.load_auto_analysis_zones",
                return_value=[
                    {
                        "id": "z1",
                        "nombre": "Zona 1",
                        "cuenca": "A",
                        "priority_score": 55.0,
                        "hydric_score": 55.0,
                        "flood_score": 40.0,
                        "risk_level": "alto",
                        "point": {"type": "Point", "coordinates": [-63.0, -32.0]},
                        "nearest_network_point": {"type": "Point", "coordinates": [-63.01, -32.01]},
                        "distance_to_network_m": 300.0,
                    }
                ],
            ),
            patch(
                "app.domains.geo.routing_auto_analysis.corridor_routing",
                side_effect=NotFoundError("No raster corridor path could be traced between the selected points"),
            ),
        ):
            result = auto_analyze_corridors(
                db,
                scope_type="consorcio",
                scope_id=None,
                mode="raster",
                profile="hidraulico",
                max_candidates=3,
            )

        assert result["summary"]["generated_candidates"] >= 1
        assert result["summary"]["returned_candidates"] >= 1
        assert result["summary"]["routed_candidates"] == 0
        assert result["summary"]["unroutable_candidates"] >= 1
        assert result["candidates"][0]["status"] == "unroutable"
        assert result["candidates"][0]["ranking_breakdown"]["explanation"] == (
            "No se encontró una ruta útil sobre el ámbito seleccionado."
        )

    def test_endpoint_delegates_to_auto_analysis_service(self):
        from app.domains.geo.router import (
            AutoCorridorAnalysisRequest,
            calculate_auto_corridor_analysis,
        )

        body = AutoCorridorAnalysisRequest(
            scope_type="cuenca",
            scope_id="Cuenca Norte",
            mode="raster",
            profile="hidraulico",
            max_candidates=4,
            weight_slope=0.2,
            weight_hydric=0.6,
            weight_property=0.2,
            weight_landcover=0.1,
        )

        expected = {
            "analysis_id": str(uuid.uuid4()),
            "summary": {"returned_candidates": 2},
            "candidates": [],
        }

        with patch(
            "app.domains.geo.router_auto_analysis.auto_analyze_corridors",
            return_value=expected,
        ) as analysis_mock:
            result = calculate_auto_corridor_analysis(
                body,
                MagicMock(),
                _user=MagicMock(),
            )

        assert result == expected
        analysis_mock.assert_called_once()
        assert analysis_mock.call_args.kwargs["scope_type"] == "cuenca"
        assert analysis_mock.call_args.kwargs["mode"] == "raster"
        assert analysis_mock.call_args.kwargs["weight_overrides"]["hydric"] == 0.6
        assert analysis_mock.call_args.kwargs["weight_overrides"]["landcover"] == 0.1

    def test_point_scope_passes_coordinates_to_auto_analysis_service(self):
        from app.domains.geo.router import (
            AutoCorridorAnalysisRequest,
            calculate_auto_corridor_analysis,
        )

        body = AutoCorridorAnalysisRequest(
            scope_type="punto",
            point_lon=-63.12,
            point_lat=-32.18,
            mode="raster",
            profile="balanceado",
            max_candidates=3,
        )

        with patch(
            "app.domains.geo.router_auto_analysis.auto_analyze_corridors",
            return_value={"analysis_id": "x", "summary": {}, "candidates": []},
        ) as analysis_mock:
            calculate_auto_corridor_analysis(
                body,
                MagicMock(),
                _user=MagicMock(),
            )

        assert analysis_mock.call_args.kwargs["scope_type"] == "punto"
        assert analysis_mock.call_args.kwargs["point_lon"] == -63.12
        assert analysis_mock.call_args.kwargs["point_lat"] == -32.18
