"""The DEM candidate classifier — pure functions, no database, no Celery.

Design D5: densify the trace every **15 m** (half a GLO-30 cell), sample the DEM
at each vertex for the road profile, sample two flanking points at **±60 m** along
the local perpendicular for the terrain, and compare **medians**:

    median(road) − median(flank) ≥  T  → terraplen
    median(road) − median(flank) ≤ −T  → canal
    otherwise                          → neutro

``confianza_m`` stores the **signed** difference, so the magnitude and the
direction of the disagreement both survive into the row.

Medians rather than means is not a style preference: a single culvert or spoil
pile is a metre-scale outlier on a profile of tens of samples, and a mean lets it
move the verdict of the whole segment. One test below is exactly that scenario.

The last class is the source rule (Law 2): the classifier reads **``dem_filled``**
— the fill of the REAL DEM — and never ``dem_filled_hydro`` or ``dem_burned``,
which carry a −10 m fictional trench. A run whose newest DEM record offers only a
burned surface **raises**; it does not fall back.
"""

from __future__ import annotations

import pytest

from app.domains.geo.relevamiento.clasificador import (
    FLANCO_OFFSET_FALLBACK_M,
    PARAMETER_FALLBACKS,
    PARAMETER_KEYS,
    PASO_DENSIFICADO_M,
    UMBRAL_FALLBACK_M,
    DemFilledNoDisponible,
    clasificar_perfiles,
    densificar,
    puntos_flanco,
    resolver_dem_filled,
)

T = 1.0


def _linea_recta(largo_m: float):
    """A straight line along +x, in a metric CRS."""
    from shapely.geometry import LineString

    return LineString([(0.0, 0.0), (largo_m, 0.0)])


class TestTheMedianComparison:
    @pytest.mark.parametrize(
        "diferencia,esperado",
        [
            (2.5, "terraplen"),
            (1.0, "terraplen"),  # exactly at T — the band is closed above
            (0.99, "neutro"),
            (0.0, "neutro"),
            (-0.99, "neutro"),
            (-1.0, "canal"),  # exactly at −T — closed below too
            (-2.5, "canal"),
        ],
    )
    def test_the_bands_are_closed_at_T(self, diferencia: float, esperado: str):
        clasificacion, _ = clasificar_perfiles([100.0 + diferencia] * 5, [100.0] * 10, umbral_m=T)

        assert clasificacion == esperado

    def test_confianza_m_is_the_signed_difference(self):
        _, confianza = clasificar_perfiles([101.4] * 5, [100.0] * 10, umbral_m=T)
        assert confianza == pytest.approx(1.4)

        _, confianza = clasificar_perfiles([98.6] * 5, [100.0] * 10, umbral_m=T)
        assert confianza == pytest.approx(-1.4), (
            "the sign is what says WHICH WAY the segment differs — an absolute "
            "value would make terraplen and canal indistinguishable in the column"
        )

    def test_one_culvert_cannot_move_the_verdict(self):
        """The reason the comparison is on medians and not on means.

        A 20-sample flat road profile with one −40 m culvert reading has a mean
        that is two metres below the terrain and a median that is level with it.
        Under a mean, this segment would be classified ``canal`` on the strength
        of a single cell.
        """
        perfil_camino = [100.0] * 19 + [60.0]
        perfil_flanco = [100.0] * 40

        clasificacion, confianza = clasificar_perfiles(perfil_camino, perfil_flanco, umbral_m=T)

        assert clasificacion == "neutro"
        assert confianza == pytest.approx(0.0)

        media_camino = sum(perfil_camino) / len(perfil_camino)
        assert media_camino - 100.0 < -T, (
            "the fixture must be one a MEAN would misclassify, or this test proves nothing"
        )

    def test_one_spoil_pile_cannot_move_the_verdict_either(self):
        perfil_camino = [100.0] * 19 + [140.0]

        clasificacion, _ = clasificar_perfiles(perfil_camino, [100.0] * 40, umbral_m=T)

        assert clasificacion == "neutro"

    def test_a_segment_with_no_usable_samples_is_not_classified(self):
        """No samples is NOT ``neutro``: nothing was measured, so nothing is said."""
        with pytest.raises(ValueError):
            clasificar_perfiles([], [100.0] * 10, umbral_m=T)

        with pytest.raises(ValueError):
            clasificar_perfiles([100.0] * 10, [], umbral_m=T)


class TestTheSamplingGeometry:
    def test_the_trace_is_densified_every_15_m(self):
        assert PASO_DENSIFICADO_M == 15.0, "half a GLO-30 cell (design D5)"

        vertices = densificar(_linea_recta(100.0))

        distancias = [
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(vertices, vertices[1:])
        ]
        assert distancias, "a 100 m line must produce more than one vertex"
        assert max(distancias) <= PASO_DENSIFICADO_M + 1e-6

    def test_densifying_keeps_both_endpoints(self):
        vertices = densificar(_linea_recta(100.0))

        assert vertices[0] == pytest.approx((0.0, 0.0))
        assert vertices[-1] == pytest.approx((100.0, 0.0))

    def test_a_segment_shorter_than_one_step_still_yields_its_endpoints(self):
        vertices = densificar(_linea_recta(4.0))

        assert len(vertices) >= 2

    def test_flanks_are_sampled_at_the_local_perpendicular(self):
        """A road along +x has its flanks at ±offset on y, both sides sampled."""
        linea = _linea_recta(100.0)
        vertices = densificar(linea)

        flancos = puntos_flanco(vertices, offset_m=60.0)

        assert len(flancos) == len(vertices)
        for (izq, der), vertice in zip(flancos, vertices):
            assert izq[0] == pytest.approx(vertice[0])
            assert der[0] == pytest.approx(vertice[0])
            assert {round(izq[1], 6), round(der[1], 6)} == {60.0, -60.0}

    def test_the_flank_offset_is_60_m_by_default(self):
        assert FLANCO_OFFSET_FALLBACK_M == 60.0, "two GLO-30 cells (design D5)"

    def test_a_diagonal_road_gets_a_diagonal_perpendicular(self):
        from shapely.geometry import LineString

        vertices = densificar(LineString([(0.0, 0.0), (100.0, 100.0)]))

        (izq, der) = puntos_flanco(vertices, offset_m=60.0)[1]

        # Perpendicular to a 45° line: the offset splits equally over x and y.
        assert abs(izq[0] - der[0]) == pytest.approx(2 * 60.0 / (2**0.5), rel=1e-6)
        assert abs(izq[1] - der[1]) == pytest.approx(2 * 60.0 / (2**0.5), rel=1e-6)


class TestTheParametersLiveInSystemSettings:
    """Task 3.1: the same home Fase A's five parameters got, no divergence."""

    def test_both_parameters_are_settings_keys_under_analisis(self):
        assert PARAMETER_KEYS == {
            "umbral_m": "analisis/tramo_clasif_umbral_m",
            "flanco_offset_m": "analisis/tramo_clasif_flanco_offset_m",
        }

    def test_the_fallbacks_match_the_designed_seeds(self):
        assert PARAMETER_FALLBACKS == {"umbral_m": 1.0, "flanco_offset_m": 60.0}
        assert UMBRAL_FALLBACK_M == 1.0

    def test_the_seeded_settings_carry_exactly_those_keys(self):
        """The fallback is the "row is missing" answer, not a second home."""
        from app.domains.settings.service import _SEED_DEFAULTS

        semillas = {s["clave"]: s for s in _SEED_DEFAULTS}
        for nombre, clave in PARAMETER_KEYS.items():
            assert clave in semillas, f"{clave} must be seeded, not only defaulted in code"
            assert semillas[clave]["categoria"] == "analisis"
            assert float(semillas[clave]["valor"]) == PARAMETER_FALLBACKS[nombre]


class TestTheSourceRasterIsNeverABurnedOne:
    """Law 2 — a fictional −10 m trench never reaches a displayed product."""

    def test_the_newest_run_s_filled_dem_is_used(self):
        ruta = resolver_dem_filled(
            [
                {"filled_dem": "/data/geo/zona/output/dem_filled.tif"},
                {"filled_dem": "/data/geo/zona/output/dem_filled.tif"},
            ]
        )

        assert ruta.endswith("dem_filled.tif")

    @pytest.mark.parametrize(
        "ruta",
        [
            "/data/geo/zona/output/dem_filled_hydro.tif",
            "/data/geo/zona/output/dem_burned.tif",
            "/data/geo/zona/output/dem_filled_escenario.tif",
        ],
    )
    def test_a_burned_or_simulated_surface_raises_instead_of_being_read(self, ruta: str):
        with pytest.raises(DemFilledNoDisponible):
            resolver_dem_filled([{"filled_dem": ruta}])

    def test_a_run_that_recorded_no_filled_dem_raises(self):
        with pytest.raises(DemFilledNoDisponible):
            resolver_dem_filled([{"burned_dem": "/data/geo/zona/output/dem_burned.tif"}])

    def test_no_dem_run_at_all_raises(self):
        with pytest.raises(DemFilledNoDisponible):
            resolver_dem_filled([])

    def test_an_older_good_run_does_not_rescue_a_newer_bad_one(self):
        """Falling back to an older run would classify against stale terrain."""
        with pytest.raises(DemFilledNoDisponible):
            resolver_dem_filled(
                [
                    {"filled_dem": "/data/geo/zona/output/dem_filled_hydro.tif"},
                    {"filled_dem": "/data/geo/zona/output/dem_filled.tif"},
                ]
            )

    def test_the_module_names_no_burned_raster_as_a_readable_source(self):
        """The forbidden names appear only in the refusal list, never as a path."""
        from app.domains.geo.relevamiento import clasificador

        assert "dem_filled_hydro.tif" in clasificador.NOMBRES_PROHIBIDOS
        assert "dem_burned.tif" in clasificador.NOMBRES_PROHIBIDOS
        assert clasificador.NOMBRE_DEM_FILLED == "dem_filled.tif"
