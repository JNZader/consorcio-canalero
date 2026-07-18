"""Cross-stack contracts consumed by the admin frontend tests."""

import json
from pathlib import Path

from app.domains.finanzas.models import CATEGORIAS_GASTO, CATEGORIAS_INGRESO
from app.domains.finanzas.router import router as finanzas_router
from app.domains.finanzas.schemas import GastoCreate, IngresoCreate
from app.domains.padron.router import router as padron_router
from app.domains.tramites.router import router as tramites_router
from app.domains.tramites.schemas import SeguimientoCreate, TramiteCreate, TramiteResponse


CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "consorcio-web"
    / "tests"
    / "fixtures"
    / "admin-api-contracts.json"
)


def _contracts() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _route_surface(router) -> set[tuple[str, str]]:
    return {(route.path, method) for route in router.routes for method in (route.methods or set())}


def test_finanzas_frontend_payloads_match_backend_schemas() -> None:
    contract = _contracts()["finanzas"]

    assert tuple(contract["gasto_categories"]) == CATEGORIAS_GASTO
    assert tuple(contract["ingreso_categories"]) == CATEGORIAS_INGRESO
    gasto = GastoCreate.model_validate(contract["gasto_create"]).model_dump(
        mode="json", exclude_none=True
    )
    ingreso = IngresoCreate.model_validate(contract["ingreso_create"]).model_dump(
        mode="json", exclude_none=True
    )
    assert {**gasto, "monto": float(gasto["monto"])} == contract["gasto_create"]
    assert {**ingreso, "monto": float(ingreso["monto"])} == contract["ingreso_create"]


def test_tramites_frontend_payloads_and_detail_match_backend_schemas() -> None:
    contract = _contracts()["tramites"]

    assert (
        TramiteCreate.model_validate(contract["create"]).model_dump(mode="json", exclude_none=True)
        == contract["create"]
    )
    assert (
        SeguimientoCreate.model_validate(contract["seguimiento_create"]).model_dump(mode="json")
        == contract["seguimiento_create"]
    )
    assert (
        TramiteResponse.model_validate(contract["detail"]).model_dump(mode="json")
        == contract["detail"]
    )


def test_admin_frontend_only_uses_routes_implemented_by_backend() -> None:
    assert ("/finanzas/comprobantes/upload", "POST") not in _route_surface(finanzas_router)
    assert ("/tramites/{tramite_id}/seguimiento", "POST") in _route_surface(tramites_router)
    assert not any("pagos" in path for path, _method in _route_surface(padron_router))
