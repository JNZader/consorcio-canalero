"""Route-table + schema guards for the ficha territorial (PR A3a-i).

`spec geo-analysis-endpoint` › "No auth regression on sibling routes" (JD-A-010)
and › "Existing geo endpoints unaffected" (JDB-003).

**Why the route table is walked over a locally built app, never over
``app.main``**: pytest imports test modules at COLLECTION time, and pulling the
full app graph there (sentry / GEE / matplotlib side effects) poisoned the VTK
offscreen renderer later in the run — segfault 3/3 in CI (see
``test_geo_public_layers`` and ``test_suelos_etl``). In CI ``fastapi.routing`` ends up imported under TWO module identities, so an
``isinstance(route, APIRoute)`` walk over a locally-built app returns False for
every route and yields an EMPTY table — even though a ``TestClient`` on the same
app serves a 503 on the ficha route (proving the route object is really there).
That mismatch — behavioural 503 OK, structural walk empty — is the tell; it cost
five CI rounds chasing timing/scope/subprocess red herrings before the class
identity was the actual cause. The route walk therefore DUCK-TYPES (methods +
dependant + path) instead of ``isinstance``, and ``_app_de_ficha()`` is built
inside each test body (never ``app.main``, never a module-scoped fixture). Each
walk asserts the set is non-empty first, failing loudly instead of vacuously.

**Reality check recorded here (deviation from the spec wording).** The spec says
``analisis-zona`` will be "the ONLY ``/api/v2/geo`` route without an operator
dependency". It is not: seven pre-existing routes (public layer catalog, the
tile proxy, the basins/approved-zones read + PDF exports) are already
unauthenticated on ``develop``. Freezing that set is the guard that actually
bites — the test fails if a NEW route joins it or if a listed route is ever
tightened, and it is the only place that fact is written down.
"""

from __future__ import annotations

from typing import Any

import pytest

FICHA_PATH = "/api/v2/geo/analisis-zona"

# Callables that prove an authenticated caller is required. ``current_user_dependency``
# is fastapi-users' token resolver (used by ``require_admin`` / ``require_admin_or_operator``
# / ``require_authenticated``); ``_require_*`` are the geo router's lazy wrappers.
MARCADORES_AUTH = {
    "current_user_dependency",
    "_require_operator",
    "_require_admin",
    "_require_authenticated",
    "require_admin",
    "require_admin_or_operator",
    "require_authenticated",
}

# Frozen, reviewed set of routes that were ALREADY public before this change.
RUTAS_PUBLICAS_PREEXISTENTES = {
    ("GET", "/api/v2/geo/layers/public"),
    ("GET", "/api/v2/geo/layers/{layer_id}/tiles/{z}/{x}/{y}.png"),
    ("GET", "/api/v2/geo/basins"),
    ("GET", "/api/v2/geo/basins/approved-zones/current"),
    ("GET", "/api/v2/geo/basins/approved-zones/history"),
    ("GET", "/api/v2/geo/basins/approved-zones/current/export-pdf"),
    ("POST", "/api/v2/geo/basins/approved-zones/current/export-map-pdf"),
}

GUARDIAS_FICHA = {"enforce_ficha_rate_limit", "enforce_body_limit", "enforce_ficha_enabled"}


def _app_de_ficha(db: Any = None) -> Any:
    """Fresh app with ONLY the geo router mounted — never ``app.main`` (see module docstring).

    Mirrors the two installers ``app.main`` calls, because handlers and
    ``components.schemas`` belong to an app, not to a router.
    """
    from fastapi import FastAPI

    from app.db.session import get_db
    from app.domains.geo.ficha_errors import install_ficha_error_handler
    from app.domains.geo.router import router as geo_router
    from app.domains.geo.router_ficha import install_ficha_openapi_schemas

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    install_ficha_error_handler(app)
    install_ficha_openapi_schemas(app)
    if db is not None:
        app.dependency_overrides[get_db] = lambda: db
    return app


def _nombres_de_dependencias(dependant: Any, acumulado: set[str]) -> set[str]:
    for sub in dependant.dependencies:
        acumulado.add(getattr(sub.call, "__name__", type(sub.call).__name__))
        _nombres_de_dependencias(sub, acumulado)
    return acumulado


def _tabla_de_rutas() -> list[tuple[str, str, set[str]]]:
    """(metodo, path, nombres de dependencias) para cada ruta bajo /api/v2/geo.

    Construida in-process con `_app_de_ficha()`, DENTRO de una fixture de
    scope funcion — NO module-scope. Ese era el bug: una fixture module-scope
    corre en el setup temprano, y en el interprete de CI el `geo_router` todavia
    no tiene sus rutas en ese punto (aparecen vacias -> 0 rutas). Los tests de
    comportamiento de este mismo archivo montan `_app_de_ficha()` dentro del
    cuerpo (scope funcion) y pasan en CI; esta funcion usa el mismo momento.
    """
    # DUCK TYPING, no isinstance(ruta, APIRoute): en el interprete de CI
    # `fastapi.routing` termina importado con DOS identidades de modulo, asi
    # que el `APIRoute` que importa el test NO es la clase de las instancias del
    # app y el isinstance devuelve False para TODAS -> tabla vacia (0 rutas)
    # aunque el TestClient sirva 503 sobre la misma ruta. Ese fue el fantasma de
    # las 5 pasadas. Filtrar por atributos (methods+dependant+path) es inmune a
    # la identidad de clase.
    app = _app_de_ficha()
    tabla = [
        (metodo, ruta.path, _nombres_de_dependencias(ruta.dependant, set()))
        for ruta in app.routes
        if hasattr(ruta, "methods") and hasattr(ruta, "dependant") and hasattr(ruta, "path")
        for metodo in sorted(ruta.methods - {"HEAD", "OPTIONS"})
    ]
    assert len(tabla) > 20, (
        "la tabla de rutas geo salio vacia o mutilada — el test no puede probar nada"
    )
    return tabla


def test_la_ficha_esta_montada_y_es_publica():
    """spec › "Discriminated-union request body" — la ruta existe, es POST, sin auth.

    Behavioral: `_app_de_ficha()` se construye en el CUERPO (no en fixture) — es
    el momento en que los demas tests behavioral de este archivo reciben 200/503
    en CI, lo que prueba que la app in-body SI tiene las rutas. Un TestClient
    confirma montada (no 404), POST-only (GET -> 405) y publica (POST sin auth
    NO da 401/403; la ficha apagada por defecto da 503).
    """
    from fastapi.testclient import TestClient

    with TestClient(_app_de_ficha()) as cliente:
        assert cliente.get(FICHA_PATH).status_code == 405, "la ficha deberia ser POST-only"
        resp = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": "X"})
    assert resp.status_code != 404, f"{FICHA_PATH} no esta montada"
    assert resp.status_code not in (401, 403), "la ficha es publica; apareció un guard de auth"
    assert resp.status_code == 503, "apagada por defecto deberia dar 503 sin tocar auth"

    # Complemento estructural sobre la MISMA app in-body (no fixture): las
    # guardias obligatorias estan presentes y ninguna dependencia de auth.
    _, _, deps = next(fila for fila in _tabla_de_rutas() if fila[1] == FICHA_PATH)
    assert not (deps & MARCADORES_AUTH), (
        f"guard de auth inesperado: {sorted(deps & MARCADORES_AUTH)}"
    )
    assert GUARDIAS_FICHA <= deps, f"faltan guardias: {sorted(GUARDIAS_FICHA - deps)}"


def test_ninguna_ruta_geo_nueva_quedo_sin_auth():
    """spec › "No auth regression on sibling routes" (JD-A-010).

    Route walk sobre la app in-body (construida aca, no en fixture module-scope
    — ese fue el bug de CI: el geo_router aparecia vacio en el setup temprano).
    """
    tabla = _tabla_de_rutas()
    abiertas = {(metodo, path) for metodo, path, deps in tabla if not (deps & MARCADORES_AUTH)}
    esperadas = RUTAS_PUBLICAS_PREEXISTENTES | {("POST", FICHA_PATH)}

    nuevas = abiertas - esperadas
    assert not nuevas, f"rutas /api/v2/geo abiertas sin revisar: {sorted(nuevas)}"

    cerradas = esperadas - abiertas
    assert not cerradas, (
        f"estas rutas dejaron de ser publicas — actualiza la lista congelada: {sorted(cerradas)}"
    )


def test_el_limitador_de_la_ficha_no_toca_ninguna_otra_ruta():
    """spec › "Existing geo endpoints unaffected" (JDB-003).

    Las guardias de la ficha existen en exactamente una ruta. App in-body.
    La saturacion behavioral del limiter contra ``/zonal-stats`` es A3a-ii.
    """
    contaminadas = {
        (metodo, path)
        for metodo, path, deps in _tabla_de_rutas()
        if (deps & GUARDIAS_FICHA) and path != FICHA_PATH
    }
    assert not contaminadas, (
        f"las guardias de la ficha se colaron en rutas de operador: {sorted(contaminadas)}"
    )


def test_tipo_desconocido_es_rechazado_por_la_union():
    """spec › "Unknown tipo is rejected" — no geometry, no raster, no DB."""
    from pydantic import TypeAdapter, ValidationError

    from app.domains.geo.schemas_ficha import FichaRequest

    with pytest.raises(ValidationError):
        TypeAdapter(FichaRequest).validate_python({"tipo": "provincia", "nomenclatura": "X"})


def test_el_cap_de_vertices_corta_antes_de_cualquier_io():
    """spec › "Vertex cap rejected before raster read" — cheap schema validator."""
    from pydantic import TypeAdapter

    from app.config import settings
    from app.domains.geo.ficha_errors import FichaError
    from app.domains.geo.schemas_ficha import FichaRequest

    anillo = [[-62.0 + i * 1e-6, -32.0] for i in range(settings.ficha_max_vertices + 2)]
    anillo.append(anillo[0])

    with pytest.raises(FichaError) as excinfo:
        TypeAdapter(FichaRequest).validate_python(
            {"tipo": "poligono", "geometry": {"type": "Polygon", "coordinates": [anillo]}}
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.codigo == "cap_excedido"
    assert excinfo.value.extra["cap"] == "vertices"


# ── F1: un cliente que se desconecta no puede costar un 500 ni un ERROR ──────


def test_desconexion_a_mitad_del_cuerpo_no_escala_a_500_ni_a_error(caplog):
    """F1 › ``ClientDisconnect`` es una salida esperada, no una excepción no manejada.

    La guardia de cuerpo corre ANTES del limitador por diseño, así que dejar
    propagar ``ClientDisconnect`` daba un disparador gratis y sin throttling:
    ``generic_exception_handler`` loguea con ``logger.exception`` y manda un
    evento a Sentry. Se arma un ``Request`` cuyo ``receive`` devuelve
    ``http.disconnect`` — que es exactamente lo que hace Starlette cuando el
    peer corta — y se exige un ``FichaError`` 400, cero ERROR en el log.
    """
    import asyncio
    import logging

    from starlette.requests import Request

    from app.domains.geo.ficha_errors import FichaError
    from app.domains.geo.router_ficha import enforce_body_limit

    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "method": "POST",
        "path": FICHA_PATH,
        # Sin content-length: obliga a entrar al camino de streaming.
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
        "client": ("203.0.113.7", 51234),
    }

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(FichaError) as excinfo:
            asyncio.run(enforce_body_limit(Request(scope, receive)))

    assert excinfo.value.status_code == 400, "una desconexión no es un 500"
    assert excinfo.value.codigo == "cliente_desconectado"

    errores = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errores, f"la desconexión dejó registros de ERROR: {[r.message for r in errores]}"


# ── F2: la referencia auditable tiene que ser estable entre procesos ─────────


def test_la_huella_de_geometria_no_depende_del_orden_de_claves():
    """F2 › mismo polígono, distinto orden de claves ⇒ misma referencia."""
    from app.domains.geo.ficha_service import referencia_auditable
    from app.domains.geo.schemas_ficha import FichaPoligonoRequest

    anillo = [[-62.0, -32.0], [-62.0, -32.1], [-61.9, -32.1], [-62.0, -32.0]]

    uno = FichaPoligonoRequest(
        tipo="poligono", geometry={"type": "Polygon", "coordinates": [anillo]}
    )
    otro = FichaPoligonoRequest(
        tipo="poligono", geometry={"coordinates": [anillo], "type": "Polygon"}
    )

    assert referencia_auditable(uno) == referencia_auditable(otro)
    assert "geom:" in referencia_auditable(uno)


def test_la_huella_de_geometria_sobrevive_a_un_proceso_nuevo():
    """F2 › ``hash()`` estaba salado por PYTHONHASHSEED: dos procesos, dos refs.

    Se corre el mismo cálculo en un intérprete FRESCO con un seed distinto
    forzado. Con ``hash()`` esto fallaba; con SHA-256 sobre JSON canónico la
    referencia es la misma y las filas de auditoría del mismo polígono se
    pueden correlacionar entre reinicios y entre los 2 workers de uvicorn.
    """
    import os
    import subprocess
    import sys

    from app.domains.geo.ficha_service import _huella_geometria

    geometria = {
        "type": "Polygon",
        "coordinates": [[[-62.0, -32.0], [-62.0, -32.1], [-61.9, -32.1], [-62.0, -32.0]]],
    }
    esperado = _huella_geometria(geometria)

    guion = (
        "import json,sys;"
        "sys.path.insert(0, %r);"
        "from app.domains.geo.ficha_service import _huella_geometria;"
        "print(_huella_geometria(json.loads(sys.argv[1])))"
    ) % os.getcwd()

    entorno = {**os.environ, "PYTHONHASHSEED": "12345"}
    salida = subprocess.run(
        [sys.executable, "-c", guion, __import__("json").dumps(geometria)],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=120,
    )
    assert salida.returncode == 0, salida.stderr
    assert salida.stdout.strip().splitlines()[-1] == esperado


# ── F3: el requestBody se describe a mano; sus $ref son responsabilidad nuestra ──


def test_el_openapi_de_la_ficha_no_deja_referencias_colgadas():
    """F3 › cero ``$ref`` colgados en el requestBody — A4 lee este contrato.

    El cuerpo se valida dentro de una dependencia (para conservar los códigos
    §2.6), así que FastAPI nunca registra los modelos: los ``$defs`` que emite
    pydantic se perderían y los cuatro ``$ref`` — incluido el ``mapping`` del
    discriminador — apuntarían a la nada. Un generador de clientes falla o
    emite un cuerpo sin tipar.
    """
    doc = _app_de_ficha().openapi()
    esquemas = doc.get("components", {}).get("schemas", {})

    operacion = doc["paths"][FICHA_PATH]["post"]
    cuerpo = operacion["requestBody"]

    referencias: list[str] = []

    def recorrer(nodo: Any) -> None:
        if isinstance(nodo, dict):
            ref = nodo.get("$ref")
            if isinstance(ref, str):
                referencias.append(ref)
            # El ``mapping`` del discriminador son refs sin clave ``$ref``.
            mapping = nodo.get("discriminator", {})
            if isinstance(mapping, dict):
                referencias.extend(str(v) for v in mapping.get("mapping", {}).values())
            for valor in nodo.values():
                recorrer(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                recorrer(valor)

    recorrer(cuerpo)
    assert referencias, "el requestBody quedó sin refs — el test no probaría nada"

    colgadas = [
        ref
        for ref in referencias
        if not (ref.startswith("#/components/schemas/") and ref.split("/")[-1] in esquemas)
    ]
    assert not colgadas, f"referencias colgadas en el requestBody de la ficha: {colgadas}"


# ── F4: el placeholder no puede ser alcanzable en producción ────────────────


def test_la_ficha_apagada_no_es_un_amplificador_de_errores(caplog):
    """F4 + R4-005 › una feature apagada loguea WARNING, no ERROR.

    El gate contesta ANTES del limitador, así que si un 503 deliberado se
    registrara como ERROR cualquiera podría inflar el error budget de un
    deployment apagado con pedidos públicos — el mismo agujero que F1. El
    ``codigo`` sí tiene que estar en la línea, que es el punto de R4-005.
    """
    import asyncio
    import logging

    from app.domains.geo import ficha_errors

    with caplog.at_level(logging.DEBUG):
        asyncio.run(
            ficha_errors.ficha_error_handler(
                None, ficha_errors.funcionalidad_no_disponible("ficha territorial")
            )
        )

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "un 503 deliberado se registró como ERROR"
    )
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert avisos, "el rechazo no dejó ninguna línea"
    assert any("funcionalidad_no_disponible" in r.getMessage() for r in avisos), (
        "la línea no lleva el ``codigo`` — R4-005 pide poder distinguir causas"
    )


def test_una_falla_real_de_5xx_si_se_registra_como_error(caplog):
    """R4-005 › la contracara: ``raster_ilegible`` es una falla, no un estado elegido."""
    import asyncio
    import logging

    from app.domains.geo import ficha_errors

    with caplog.at_level(logging.DEBUG):
        asyncio.run(ficha_errors.ficha_error_handler(None, ficha_errors.raster_ilegible("suelos")))

    errores = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errores, "una falla de infraestructura quedó por debajo de ERROR"
    assert any("raster_ilegible" in r.getMessage() for r in errores)


def test_la_ficha_esta_apagada_por_defecto_y_no_deja_rastro(db, monkeypatch):
    """F4 › apagada ⇒ 503 antes de auditar y antes de tomar un slot.

    Mientras ``analizar_zona`` devuelva ``area_ha=0.0`` con todo
    ``sin_cobertura``, publicar eso sería publicar un placeholder como si fuera
    una medición. Se verifica el default apagado, el código estable, que NO se
    escriba fila de auditoría y que el semáforo quede intacto.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from app.config import settings
    from app.domains.geo import ficha_service
    from app.shared.audit_log import AuditLog

    assert settings.ficha_enabled is False, "la ficha debe venir APAGADA de fábrica"

    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)
    ficha_service.reset_ficha_slots()
    slots = ficha_service.get_ficha_slots()
    libres_antes = slots._value

    antes = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "zona.analisis")
    ).scalar_one()

    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(
            FICHA_PATH, json={"tipo": "parcela", "nomenclatura": "19-04-12-3456-7"}
        )

    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "funcionalidad_no_disponible"
    assert "detail" in cuerpo, "el contrato §2.6 es plano: {detail, codigo, …}"

    despues = db.execute(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "zona.analisis")
    ).scalar_one()
    assert despues == antes, "una ficha apagada escribió fila de auditoría"
    assert slots._value == libres_antes, "una ficha apagada consumió un slot de cómputo"


def test_con_la_ficha_encendida_el_pipeline_responde_el_placeholder(db, monkeypatch):
    """F4 › la contracara: encendida, la ruta sigue siendo la misma ruta.

    Prendiendo el flag se ejercita el pipeline completo (gate → cuerpo →
    limitador → schema → auditoría → semáforo) y se comprueba que el
    placeholder es explícito: ``sin_cobertura`` en los CUATRO datasets, nunca
    hectáreas inventadas ni un dataset omitido (R3-007).
    """
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "ficha_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_disabled", True, raising=False)

    with TestClient(_app_de_ficha(db)) as cliente:
        respuesta = cliente.post(
            FICHA_PATH,
            json={
                "tipo": "poligono",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-62.0, -32.0], [-62.0, -32.1], [-61.9, -32.1], [-62.0, -32.0]]
                    ],
                },
            },
        )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["area_ha"] == 0.0
    for dataset in ("suelos", "flood_risk", "drainage_need", "precipitacion_mensual"):
        assert cuerpo[dataset] is not None, f"{dataset} se omitió en vez de reportarse"
        assert cuerpo[dataset]["cobertura"] == "sin_cobertura"
        assert cuerpo[dataset]["cobertura_ratio"] == 0.0
