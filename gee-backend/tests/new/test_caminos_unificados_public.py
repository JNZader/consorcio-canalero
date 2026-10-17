"""The public caminos envelope is one feature per route."""

from __future__ import annotations

from app.domains.geo.caminos_unificados_public import assemble_public_caminos

COLORS = ["#111111", "#222222"]


def test_assemble_paints_one_feature_per_route_with_the_dominant_consorcio() -> None:
    collection = assemble_public_caminos(
        {
            "routes": [
                {
                    "id": 2,
                    "ruta": "T269-03",
                    "nombre": "Camino Provincial T269-03",
                    "tipo_generico": "Camino Provincial",
                    "red": "Terciaria",
                    "consorcios": "C.C. 269 - SAN MARCOS SUD",
                    "longitud_geodesica_km": 5.5,
                    "cantidad_tramos_fisicos": 2,
                    "ccn": "C.C. 269 - SAN MARCOS SUD",
                    "ccc": "269",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[-62.5, -32.5], [-62.5, -32.52]]],
                    },
                },
                {
                    "id": 1,
                    "ruta": "RP3",
                    "nombre": "Ruta Provincial 3",
                    "tipo_generico": "Ruta Provincial",
                    "red": "Secundaria",
                    "consorcios": "C.C. 027 - LEONES",
                    "longitud_geodesica_km": 10,
                    "cantidad_tramos_fisicos": 1,
                    "ccn": "C.C. 027 - LEONES",
                    "ccc": "",
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [[[-62.4, -32.5], [-62.4, -32.6]]],
                    },
                },
            ],
            "legend": [
                {"ccn": "C.C. 269 - SAN MARCOS SUD", "ccc": "269", "tramos": 2, "km": 5.5},
                {"ccn": "C.C. 027 - LEONES", "ccc": "", "tramos": 1, "km": 10},
            ],
        },
        COLORS,
    )

    assert [feature["properties"]["rtn"] for feature in collection["features"]] == [
        "T269-03",
        "RP3",
    ]
    t269 = collection["features"][0]["properties"]
    assert t269["ruta"] == "T269-03"
    assert t269["fna"] == "Camino Provincial T269-03"
    assert t269["cantidad_tramos_fisicos"] == 2
    assert t269["color"] == "#222222"
    assert collection["features"][0]["geometry"]["type"] == "MultiLineString"
    leones = collection["consorcios"][0]
    assert leones["nombre"] == "C.C. 027 - LEONES"
    assert leones["codigo"] == "C.C. 027 - LEONES"
    assert leones["tramos"] == 1
    assert collection["metadata"] == {
        "total_tramos": 2,
        "total_consorcios": 2,
        "total_km": 15.5,
    }


def test_assemble_drops_a_route_without_a_line_and_survives_an_empty_payload() -> None:
    collection = assemble_public_caminos(
        {
            "routes": [
                {"id": 1, "ruta": "X", "geometry": {"type": "Point", "coordinates": [0, 0]}},
                {"id": 2, "ruta": "Y", "geometry": None},
            ],
            "legend": None,
        },
        COLORS,
    )

    assert collection["features"] == []
    assert collection["metadata"]["total_tramos"] == 0
    assert assemble_public_caminos(None, COLORS)["type"] == "FeatureCollection"
