"""Publication policy of ``GET /api/v2/geo/layers/public`` (no auth).

The endpoint is the ONLY gate deciding which DEM-pipeline layers an
anonymous visitor can discover. Production publishes ``dem_raw`` plus
``terrain_class`` (clasificación del terreno, pedido del consorcio
2026-07-30); every other terrain product stays behind login.

These tests pin that policy with the review flag explicitly OFF, so a
developer with ``PUBLIC_MAP_LAYER_EVAL`` exported in their shell still
exercises the production branch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer

# Importing the app at module scope registers EVERY model module in
# ``Base.metadata`` before the session-scoped ``create_all`` runs. Without it,
# running this file on its own leaves cross-domain foreign keys dangling
# (e.g. ``flood_labels.zona_id`` -> ``zonas_operativas``).
from app.main import app  # noqa: E402  (import order is load-bearing)

ENDPOINT = "/api/v2/geo/layers/public"


@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient wired to the rolled-back test session, eval flag OFF."""
    monkeypatch.delenv("PUBLIC_MAP_LAYER_EVAL", raising=False)

    app.dependency_overrides[get_db] = lambda: db
    tc = TestClient(app)
    # ``localhost`` is a trusted host in dev (derived from CORS_ORIGINS);
    # the default ``testserver`` would be rejected before routing.
    tc.headers.update({"Host": "localhost"})
    yield tc
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded_layers(db: Session) -> None:
    """One DEM-pipeline layer per tile-capable tipo.

    Seeds the FULL tile-capable set (not just a sample) so the equality
    assertion below fails if ANY extra tipo is ever added to the public
    production allowlist — this test is the only safety net over an
    anonymous publication policy.
    """
    from app.domains.geo.router_core import PUBLIC_TILE_CAPABLE_TYPES

    for tipo in sorted(PUBLIC_TILE_CAPABLE_TYPES):
        db.add(
            GeoLayer(
                nombre=f"{tipo}_test",
                tipo=tipo,
                fuente=FuenteGeoLayer.DEM_PIPELINE.value,
                archivo_path=f"/tmp/{tipo}.tif",
                formato=FormatoGeoLayer.GEOTIFF.value,
            )
        )
    db.flush()


def _tipos(response) -> set[str]:
    return {item["tipo"] for item in response.json()["items"]}


def test_public_layers_expose_dem_raw_and_terrain_class(
    client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"limit": 100})
    assert resp.status_code == 200, resp.text
    # Igualdad EXACTA: si manana alguien amplia PUBLIC_PRODUCTION_LAYER_TYPES
    # (p. ej. mete flood_risk), este assert falla y obliga a decidirlo a
    # conciencia en el test, no de rebote.
    assert _tipos(resp) == {"dem_raw", "terrain_class"}


def test_public_layers_hide_non_published_types(client: TestClient, seeded_layers: None) -> None:
    resp = client.get(ENDPOINT, params={"limit": 100})
    assert resp.status_code == 200, resp.text
    tipos = _tipos(resp)
    privados = {
        "hand",
        "twi",
        "flow_acc",
        "flow_dir",
        "slope",
        "aspect",
        "flood_risk",
        "drainage_need",
    }
    assert not (tipos & privados), f"tipos privados expuestos: {tipos & privados}"


def test_public_layers_tipo_filter_rejects_private_type(
    client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"tipo": "hand"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []
    assert resp.json()["total"] == 0


def test_public_layers_tipo_filter_narrows_to_terrain_class(
    client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"tipo": "terrain_class"})
    assert resp.status_code == 200, resp.text
    assert _tipos(resp) == {"terrain_class"}


def test_public_layers_foreign_fuente_returns_empty_page(
    client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"fuente": "gee"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


def test_public_layers_require_no_authentication(client: TestClient) -> None:
    resp = client.get(ENDPOINT)
    assert resp.status_code == 200, "public layer catalog must stay anonymous-readable"
