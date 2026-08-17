"""Publication policy of ``GET /api/v2/geo/layers/public`` (no auth).

The endpoint is the ONLY gate deciding which DEM-pipeline layers an
anonymous visitor can discover. Production publishes ``dem_raw``,
``terrain_class`` (clasificación del terreno, pedido del consorcio
2026-07-30) and the ``flood_risk`` / ``drainage_need`` composites
(overlays de riesgo/drenaje del mapa de la ficha, 2026-08-01); every
other terrain product stays behind login.

These tests pin that policy with the review flag explicitly OFF, so a
developer with ``PUBLIC_MAP_LAYER_EVAL`` exported in their shell still
exercises the production branch.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fastapi import FastAPI

from app.db.session import get_db
from app.domains.geo.models import FormatoGeoLayer, FuenteGeoLayer, GeoLayer

# Register every model module in ``Base.metadata`` WITHOUT importing
# ``app.main``. pytest imports test modules at COLLECTION time, and pulling
# the full app graph there (sentry / GEE / matplotlib side effects) poisoned
# the VTK offscreen renderer further down the run: segfault 3/3 en CI
# (2026-07-30), mientras develop —donde nadie importa app.main en
# coleccion— pasaba. Espejo del bloque de registro de
# ``app/db/migrations/env.py``; sin el, correr este archivo SOLO deja FKs
# colgando (p. ej. ``flood_labels.zona_id`` -> ``zonas_operativas``).
import app.auth.models  # noqa: F401, E402
import app.domains.capas.models  # noqa: F401, E402
import app.domains.denuncias.models  # noqa: F401, E402
import app.domains.finanzas.models  # noqa: F401, E402
import app.domains.geo.intelligence.models  # noqa: F401, E402
import app.domains.monitoring.models  # noqa: F401, E402
import app.domains.padron.models  # noqa: F401, E402
import app.domains.reuniones.models  # noqa: F401, E402
import app.domains.settings.models  # noqa: F401, E402
import app.domains.tramites.models  # noqa: F401, E402
import app.shared.celery_outbox  # noqa: F401, E402

# SOLO router_core — NO el aggregate ``app.domains.geo.router``: el agregado
# arrastra shapely (libgeos, nativa) en tiempo de coleccion de pytest, y esa
# carga temprana desestabilizaba los tests del renderer VTK offscreen mas
# adelante en la suite (segfault intermitente SOLO en CI). Verificado:
# importar router_core no carga ninguna libreria nativa pesada.
from app.domains.geo.router_core import router as core_router  # noqa: E402

ENDPOINT = "/api/v2/geo/layers/public"


def _build_minimal_app() -> FastAPI:
    """FastAPI minima con SOLO el router geo montado en su prefijo real.

    Evita ``app.main`` (middleware TrustedHost, sentry, lifespan) — el
    endpoint bajo test no depende de nada de eso.
    """
    minimal = FastAPI()
    minimal.include_router(core_router, prefix="/api/v2/geo")
    return minimal


@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient wired to the rolled-back test session, eval flag OFF."""
    monkeypatch.delenv("PUBLIC_MAP_LAYER_EVAL", raising=False)

    minimal = _build_minimal_app()
    minimal.dependency_overrides[get_db] = lambda: db
    yield TestClient(minimal)


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


def test_public_layers_expose_published_production_set(
    client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"limit": 100})
    assert resp.status_code == 200, resp.text
    # Igualdad EXACTA: si manana alguien amplia PUBLIC_PRODUCTION_LAYER_TYPES,
    # este assert falla y obliga a decidirlo a conciencia en el test, no de
    # rebote. flood_risk/drainage_need se sumaron al set publico (overlays de
    # riesgo/drenaje de la ficha, 2026-08-01); precip_normal se suma para el
    # visor multi-riesgo (2026-08-17).
    assert _tipos(resp) == {"dem_raw", "terrain_class", "flood_risk", "drainage_need", "precip_normal"}


def test_public_layers_hide_non_published_types(client: TestClient, seeded_layers: None) -> None:
    resp = client.get(ENDPOINT, params={"limit": 100})
    assert resp.status_code == 200, resp.text
    tipos = _tipos(resp)
    # flood_risk/drainage_need YA NO son privados (publicados 2026-08-01); el
    # resto de los productos intermedios del pipeline sigue detras de login.
    privados = {
        "hand",
        "twi",
        "flow_acc",
        "flow_dir",
        "slope",
        "aspect",
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


@pytest.mark.parametrize("tipo", ["flood_risk", "drainage_need"])
def test_public_layers_tipo_filter_narrows_to_composite(
    tipo: str, client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"tipo": tipo})
    assert resp.status_code == 200, resp.text
    assert _tipos(resp) == {tipo}


def test_public_layers_foreign_fuente_returns_empty_page(
    client: TestClient, seeded_layers: None
) -> None:
    resp = client.get(ENDPOINT, params={"fuente": "gee"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


def test_public_layers_require_no_authentication(client: TestClient) -> None:
    resp = client.get(ENDPOINT)
    assert resp.status_code == 200, "public layer catalog must stay anonymous-readable"
