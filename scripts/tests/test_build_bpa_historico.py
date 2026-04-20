"""Tests for Phase 7 writer — ``build_bpa_historico_features``.

The ETL emits a NEW GeoJSON layer ``bpa_historico.geojson`` covering every
parcel that has ever been in the BPA program (``años_bpa >= 1``). Features
carry geometry from catastro, plus a thin property set driving the gradient
fill on the frontend map.

Invariants anchored here:
1. Only parcels with ``años_bpa >= 1`` appear.
2. Feature geometry is sourced from the matching catastro feature.
3. Each feature's properties include ``nro_cuenta``, ``años_bpa``,
   ``años_lista``, ``n_explotacion_ultima``, ``bpa_activa_2025``.
4. ``n_explotacion_ultima`` is the 2025 name when present, else the most
   recent year's name from the historical series.
5. Parcels lacking a catastro geometry are silently dropped (not an error).
"""

from __future__ import annotations

from scripts.etl_pilar_verde.writers import build_bpa_historico_features


def _catastro_feature(cuenta: str, *, coords: tuple[float, float] = (-62.5, -32.5)) -> dict:
    lon, lat = coords
    return {
        "type": "Feature",
        "properties": {"Nro_Cuenta": cuenta},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [lon, lat],
                    [lon + 0.01, lat],
                    [lon + 0.01, lat + 0.01],
                    [lon, lat + 0.01],
                    [lon, lat],
                ]
            ],
        },
    }


def _parcel(
    cuenta: str,
    *,
    anios: int,
    lista: list[str],
    has_2025: bool = False,
    historico: dict[str, str] | None = None,
    n_explotacion_2025: str | None = None,
) -> dict:
    bpa_2025 = (
        {"n_explotacion": n_explotacion_2025 or "El Tala", "activa": True}
        if has_2025
        else None
    )
    return {
        "nro_cuenta": cuenta,
        "bpa_2025": bpa_2025,
        "bpa_historico": historico or {},
        "años_bpa": anios,
        "años_lista": lista,
    }


class TestBuildBpaHistoricoFeatures:
    def test_only_parcels_with_history_appear(self):
        catastro = [
            _catastro_feature("A"),
            _catastro_feature("B"),
            _catastro_feature("C"),
        ]
        parcels = [
            _parcel("A", anios=0, lista=[]),
            _parcel("B", anios=1, lista=["2025"], has_2025=True),
            _parcel("C", anios=3, lista=["2019", "2020", "2024"], historico={"2019": "x", "2020": "x", "2024": "x"}),
        ]
        collection = build_bpa_historico_features(parcels, catastro)
        assert collection["type"] == "FeatureCollection"
        cuentas = {f["properties"]["nro_cuenta"] for f in collection["features"]}
        assert cuentas == {"B", "C"}

    def test_feature_properties_shape(self):
        catastro = [_catastro_feature("A")]
        parcels = [
            _parcel(
                "A",
                anios=3,
                lista=["2019", "2020", "2025"],
                has_2025=True,
                historico={"2019": "La Sentina", "2020": "La Sentina"},
                n_explotacion_2025="La Sentina 2025",
            )
        ]
        collection = build_bpa_historico_features(parcels, catastro)
        props = collection["features"][0]["properties"]
        assert props == {
            "nro_cuenta": "A",
            "años_bpa": 3,
            "años_lista": ["2019", "2020", "2025"],
            "n_explotacion_ultima": "La Sentina 2025",
            "bpa_activa_2025": True,
        }

    def test_n_explotacion_ultima_falls_back_to_last_historical_year(self):
        catastro = [_catastro_feature("A")]
        parcels = [
            _parcel(
                "A",
                anios=2,
                lista=["2019", "2024"],
                has_2025=False,
                historico={"2019": "Old Name", "2024": "New Name"},
            )
        ]
        collection = build_bpa_historico_features(parcels, catastro)
        props = collection["features"][0]["properties"]
        assert props["n_explotacion_ultima"] == "New Name"
        assert props["bpa_activa_2025"] is False

    def test_parcels_missing_catastro_geometry_are_dropped(self):
        catastro = [_catastro_feature("A")]
        parcels = [
            _parcel("A", anios=1, lista=["2025"], has_2025=True),
            _parcel("B_NO_CAT", anios=2, lista=["2019", "2020"], historico={"2019": "x", "2020": "x"}),
        ]
        collection = build_bpa_historico_features(parcels, catastro)
        cuentas = {f["properties"]["nro_cuenta"] for f in collection["features"]}
        assert cuentas == {"A"}

    def test_geometry_matches_catastro_feature(self):
        catastro = [_catastro_feature("A", coords=(-62.7, -32.3))]
        parcels = [_parcel("A", anios=1, lista=["2025"], has_2025=True)]
        collection = build_bpa_historico_features(parcels, catastro)
        geom = collection["features"][0]["geometry"]
        assert geom["type"] == "Polygon"
        # First coordinate must come from the catastro feature.
        assert geom["coordinates"][0][0] == [-62.7, -32.3]
