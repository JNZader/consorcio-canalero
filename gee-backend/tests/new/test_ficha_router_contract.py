"""Route-table + schema guards for the ficha territorial (PR A3a-i).

`spec geo-analysis-endpoint` › "No auth regression on sibling routes" (JD-A-010)
and › "Existing geo endpoints unaffected" (JDB-003).

**Why these are PURE behavioural (TestClient) tests, no structural route walk**:
in the CI interpreter, building a FastAPI app and iterating ``app.routes`` yields
an EMPTY set even though a ``TestClient`` on the SAME app serves the route (503
observed on ``/analisis-zona`` while the walk saw 0 routes) — a module-identity
pathology that empties the shared ``geo_router`` between two ``_app_de_ficha()``
calls in the same test. It survived isinstance->duck-typing and subprocess and
function-scope rewrites across six CI rounds. TestClient is the only thing CI
builds reliably, so the contract (mounted, POST-only, public, guards isolated,
no auth regression on siblings) is proven by response codes, never by walking
the route table.

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


# Muestra de rutas de operador (auth obligatoria) sin parametros de path,
# para probar por comportamiento que el auth SIGUE puesto en las hermanas.
RUTAS_OPERADOR_MUESTRA = {
    ("GET", "/api/v2/geo/jobs"),
    ("GET", "/api/v2/geo/layers"),
}

# Publicas SIN parametros de path, chequeables directo (el tile proxy y los
# export-pdf llevan {params}/cuerpo; la muestra de 4 alcanza para probar la
# propiedad "publica = no 401").
RUTAS_PUBLICAS_SIN_PARAMS = {
    ("GET", "/api/v2/geo/layers/public"),
    ("GET", "/api/v2/geo/basins"),
    ("GET", "/api/v2/geo/basins/approved-zones/current"),
    ("GET", "/api/v2/geo/basins/approved-zones/history"),
}


def _pedir(cliente: Any, metodo: str, path: str) -> Any:
    return cliente.post(path, json={}) if metodo == "POST" else cliente.get(path)


def test_la_ficha_esta_montada_y_es_publica(db):
    """spec › "Discriminated-union request body" — la ruta existe, es POST, sin auth.

    Puramente behavioral (TestClient): CI arma bien las apps que sirven trafico
    pero NO el walk estructural de rutas (patologia de identidad de modulos que
    vacia el geo_router entre dos construcciones — 6 pasadas documentadas en el
    docstring del modulo). Un GET->405 prueba montada+POST-only; un POST sin
    auth->503 prueba publica (ningun guard de auth) y apagada-por-defecto.
    """
    from fastapi.testclient import TestClient

    with TestClient(_app_de_ficha(db)) as cliente:
        assert cliente.get(FICHA_PATH).status_code == 405, "la ficha deberia ser POST-only"
        resp = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": "X"})
    assert resp.status_code != 404, f"{FICHA_PATH} no esta montada"
    assert resp.status_code not in (401, 403), "la ficha es publica; apareció un guard de auth"
    assert resp.status_code == 503, "apagada por defecto deberia dar 503 sin tocar auth"


def test_publicas_no_piden_auth_y_operador_si(db):
    """spec › "No auth regression on sibling routes" (JD-A-010) — behavioral.

    Las rutas publicas (muestra sin params) NUNCA dan 401/403; las de operador
    SIEMPRE dan 401 sin token. Prueba que agregar la ficha publica no aflojo el
    auth de las hermanas y que la ficha misma es publica.
    """
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False: una hermana puede dar 500 (tabla ausente en
    # el schema de test); eso NO es un desafio de auth, que es lo unico que este
    # test mide. Un 500 vuelve como respuesta en vez de propagar.
    with TestClient(_app_de_ficha(db), raise_server_exceptions=False) as cliente:
        for metodo, path in RUTAS_PUBLICAS_SIN_PARAMS:
            r = _pedir(cliente, metodo, path)
            assert r.status_code not in (401, 403), (
                f"{metodo} {path} deberia ser publica, dio {r.status_code}"
            )

        rf = cliente.post(FICHA_PATH, json={"tipo": "parcela", "nomenclatura": "X"})
        assert rf.status_code not in (401, 403), "la ficha deberia ser publica"

        for metodo, path in RUTAS_OPERADOR_MUESTRA:
            r = _pedir(cliente, metodo, path)
            assert r.status_code == 401, (
                f"{metodo} {path} deberia requerir auth, dio {r.status_code}"
            )


def test_la_guardia_de_la_ficha_no_se_colo_en_rutas_hermanas(db):
    """spec › "Existing geo endpoints unaffected" (JDB-003) — behavioral.

    Con la ficha APAGADA por defecto, solo ``/analisis-zona`` da el 503
    ``funcionalidad_no_disponible``. Si ``enforce_ficha_enabled`` se hubiera
    colado en una ruta hermana, esa hermana devolveria el mismo 503; se prueba
    que las publicas hermanas responden normal (nunca ese 503).
    """
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False: una hermana puede dar 500 (tabla ausente en
    # el schema de test); eso NO es un desafio de auth, que es lo unico que este
    # test mide. Un 500 vuelve como respuesta en vez de propagar.
    with TestClient(_app_de_ficha(db), raise_server_exceptions=False) as cliente:
        for metodo, path in RUTAS_PUBLICAS_SIN_PARAMS:
            r = _pedir(cliente, metodo, path)
            colado = (
                r.status_code == 503 and r.json().get("codigo") == "funcionalidad_no_disponible"
            )
            assert not colado, f"la guardia de la ficha se colo en {metodo} {path}"


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
