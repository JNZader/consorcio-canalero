"""Which drainage variant the crossing run reads, and when it may substitute.

"Fail if ``natural_flow_acc_{area_id}`` is missing" would make Fase A
permanently unavailable for every area with no canals — a large share of them,
and precisely the areas where a road's natural flow is the ONLY hydrological
story there is. The pipeline does not register the natural layers there because
it has nothing new to register: ``hay_variante_natural = filled_hydro != filled``
(``tasks_dem_support.py:265-270``), and in that branch ``flow_dir_{area_id}`` /
``flow_acc_{area_id}`` are **byte-identical** to what the natural variant would
have been — same input file object, same computation.

So the fallback exists, but it is licensed by a **checked fact** about that
area's pipeline run, never by the mere absence of a file. These tests pin all
four outcomes, and the resolution is by EXACT NAME rather than "first layer of
tipo X" — three layers share ``tipo = FLOW_ACC`` (``flow_acc_``,
``natural_flow_acc_``, ``escenario_flow_acc_``), so the existing
``.first()``-over-an-unordered-query idiom at ``intelligence/tasks.py:204-217``
cannot state which variant it read.

A fake repository, not the database: what is under test is the decision, and a
decision is easier to corner with four hand-built layer sets than with four
seeded schemas.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domains.geo.intelligence.cruces_camino_support import (
    VarianteNoDisponible,
    resolver_variante_drenaje,
)

AREA = "zona_principal"


class FakeRepo:
    """Just enough repository to answer the two questions the resolver asks."""

    def __init__(self, layers: dict[str, str], dem_resultados: list[dict] | None = None):
        self._layers = layers
        self._dem_resultados = dem_resultados if dem_resultados is not None else [{}]
        self.nombres_consultados: list[str] = []

    def get_layer_by_nombre(self, _db, nombre: str):
        self.nombres_consultados.append(nombre)
        path = self._layers.get(nombre)
        return SimpleNamespace(nombre=nombre, archivo_path=path) if path else None

    def get_dem_resultados(self, _db, _area_id: str) -> list[dict]:
        """Newest first — the DEM runs' ``resultado`` payloads for this area."""
        return list(self._dem_resultados)

    def get_layers(self, *_args, **_kwargs):  # pragma: no cover - must never be reached
        raise AssertionError(
            "resolution must be BY NAME — 'first layer of tipo X' cannot state "
            "which drainage variant it read"
        )


def _dem_run(*, burned: bool) -> dict:
    """A DEM job ``resultado`` with and without a burn on record.

    ``burned_dem`` / ``filled_hydro_dem`` land in ``outputs`` only inside the
    burn branch (``tasks_dem_support.py:109-143``), so their presence IS the
    record of a burn and their absence is the record of none.
    """
    outputs = {"filled_dem": "/data/dem_filled.tif", "flow_acc": "/data/flow_acc.tif"}
    if burned:
        outputs["burned_dem"] = "/data/dem_burned.tif"
        outputs["filled_hydro_dem"] = "/data/dem_filled_hydro.tif"
    return outputs


class TestNaturalPairPresent:
    def test_the_natural_pair_is_used_when_it_resolves(self):
        repo = FakeRepo(
            {
                f"natural_flow_dir_{AREA}": "/data/natural_flow_dir.tif",
                f"natural_flow_acc_{AREA}": "/data/natural_flow_acc.tif",
                f"flow_dir_{AREA}": "/data/flow_dir.tif",
                f"flow_acc_{AREA}": "/data/flow_acc.tif",
            }
        )

        resolved = resolver_variante_drenaje(None, repo, area_id=AREA)

        assert resolved.flow_dir_path == "/data/natural_flow_dir.tif"
        assert resolved.flow_acc_path == "/data/natural_flow_acc.tif"
        assert resolved.variante == "natural"

    def test_resolution_is_by_exact_name(self):
        repo = FakeRepo(
            {
                f"natural_flow_dir_{AREA}": "/data/natural_flow_dir.tif",
                f"natural_flow_acc_{AREA}": "/data/natural_flow_acc.tif",
            }
        )

        resolver_variante_drenaje(None, repo, area_id=AREA)

        assert f"natural_flow_dir_{AREA}" in repo.nombres_consultados
        assert f"natural_flow_acc_{AREA}" in repo.nombres_consultados

    def test_the_escenario_variant_is_never_reachable(self):
        """No path silently reads a SIMULATION of canals nobody has built."""
        repo = FakeRepo(
            {
                f"escenario_flow_dir_{AREA}": "/data/escenario_flow_dir.tif",
                f"escenario_flow_acc_{AREA}": "/data/escenario_flow_acc.tif",
            },
            dem_resultados=[_dem_run(burned=False)],
        )

        with pytest.raises(VarianteNoDisponible):
            resolver_variante_drenaje(None, repo, area_id=AREA)

        assert not any("escenario" in n for n in repo.nombres_consultados)


class TestVerifiedNoBurnFallback:
    def test_both_absent_with_a_verified_no_burn_falls_back_and_records_it(self):
        repo = FakeRepo(
            {
                f"flow_dir_{AREA}": "/data/flow_dir.tif",
                f"flow_acc_{AREA}": "/data/flow_acc.tif",
            },
            dem_resultados=[_dem_run(burned=False)],
        )

        resolved = resolver_variante_drenaje(None, repo, area_id=AREA)

        assert resolved.flow_dir_path == "/data/flow_dir.tif"
        assert resolved.flow_acc_path == "/data/flow_acc.tif"
        assert resolved.variante == "relevado_equivale_natural", (
            "the substitution must be RECORDED — an equivalence established from "
            "the recorded absence of burning, not a silent swap"
        )

    def test_a_burn_on_record_makes_the_fallback_a_refusal(self):
        repo = FakeRepo(
            {
                f"flow_dir_{AREA}": "/data/flow_dir.tif",
                f"flow_acc_{AREA}": "/data/flow_acc.tif",
            },
            dem_resultados=[_dem_run(burned=True)],
        )

        with pytest.raises(VarianteNoDisponible) as exc:
            resolver_variante_drenaje(None, repo, area_id=AREA)

        assert f"natural_flow_acc_{AREA}" in str(exc.value), (
            "the refusal must NAME the missing layer"
        )

    def test_the_most_recent_dem_run_decides(self):
        """An area burned once and re-run without canals is no longer burned."""
        repo = FakeRepo(
            {
                f"flow_dir_{AREA}": "/data/flow_dir.tif",
                f"flow_acc_{AREA}": "/data/flow_acc.tif",
            },
            dem_resultados=[_dem_run(burned=False), _dem_run(burned=True)],
        )

        resolved = resolver_variante_drenaje(None, repo, area_id=AREA)

        assert resolved.variante == "relevado_equivale_natural"

    def test_no_dem_run_at_all_is_a_refusal_not_a_fallback(self):
        """Absence of evidence is not evidence of no burn."""
        repo = FakeRepo(
            {
                f"flow_dir_{AREA}": "/data/flow_dir.tif",
                f"flow_acc_{AREA}": "/data/flow_acc.tif",
            },
            dem_resultados=[],
        )

        with pytest.raises(VarianteNoDisponible):
            resolver_variante_drenaje(None, repo, area_id=AREA)


class TestHalfPairIsAlwaysARefusal:
    @pytest.mark.parametrize("present", ["natural_flow_dir", "natural_flow_acc"])
    def test_exactly_one_of_the_natural_pair_raises(self, present: str):
        """Half a pair is a broken pipeline run, not a licence to substitute."""
        repo = FakeRepo(
            {
                f"{present}_{AREA}": "/data/half.tif",
                f"flow_dir_{AREA}": "/data/flow_dir.tif",
                f"flow_acc_{AREA}": "/data/flow_acc.tif",
            },
            dem_resultados=[_dem_run(burned=False)],
        )

        with pytest.raises(VarianteNoDisponible) as exc:
            resolver_variante_drenaje(None, repo, area_id=AREA)

        assert "natural_flow" in str(exc.value)

    @pytest.mark.parametrize("present", ["flow_dir", "flow_acc"])
    def test_exactly_one_of_the_operational_pair_raises(self, present: str):
        repo = FakeRepo(
            {f"{present}_{AREA}": "/data/half.tif"},
            dem_resultados=[_dem_run(burned=False)],
        )

        with pytest.raises(VarianteNoDisponible):
            resolver_variante_drenaje(None, repo, area_id=AREA)


class TestRefusalDoesNotGateCanalCrossings:
    """A hard refusal aborts the ``flujo_natural`` derivation ONLY.

    Canal crossings have no raster dependency at all — a canal that crosses a
    road crosses it whether or not a DEM exists — so an area with a broken DEM
    still gets its culvert candidates. The exception carries that instruction
    rather than leaving each caller to remember it.
    """

    def test_the_refusal_is_typed_so_the_caller_can_continue_with_canals(self):
        repo = FakeRepo({}, dem_resultados=[_dem_run(burned=True)])

        with pytest.raises(VarianteNoDisponible) as exc:
            resolver_variante_drenaje(None, repo, area_id=AREA)

        assert exc.value.area_id == AREA
        assert exc.value.capa_faltante
