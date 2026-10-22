# ruff: noqa: F811, F401
# The fixtures below are IMPORTED from the sibling test modules so this file
# drives the same assembled app, probe and limiter fakes the mailbox tests use;
# pytest finds them by name, which is exactly what ruff reads as a redefinition.
"""Unit 3 — `POST /conocimiento/normas/buscar`: the gate, the body, the two shapes.

The surface is the kernel's `buscar` pinned to the no-GPU arm. Everything the
mailbox's enablement AND checks (terms record, provider credential, embedder
sidecar) is deliberately absent here, and several tests below prove the route
does not even ask.

Nothing touches the network. The sidecar probe is the scripted fake from
`test_qa_surface`, and the corpus is the kernel's seeded mini-snapshot.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.domains.conocimiento.embed_sidecar import SidecarNoDisponible

from .test_normas_kernel import OTRO_SHA, SHA, barra_superada, seed  # noqa: F401
from .test_qa_surface import (  # noqa: F401 (fixtures)
    BASE,
    PREGUNTAS,
    _como,
    app_client,
    limitador,
    sonda,
)

BUSCAR = f"{BASE}/normas/buscar"
CONSULTA = "canal de riego"


@pytest.fixture
def normas_on(monkeypatch):
    """The norms flag ON and nothing else: the QA flag stays at its default."""
    monkeypatch.setattr(settings, "conocimiento_normas_enabled", True)
    return settings


@pytest.fixture
def corpus(db_session_factory):
    sesion = db_session_factory()
    try:
        seed(sesion)
        sesion.commit()
    finally:
        sesion.close()


def _post(cliente, cuerpo=None, **kwargs):
    return cliente.post(BUSCAR, json={"consulta": CONSULTA} if cuerpo is None else cuerpo, **kwargs)


class TestElFlagYElOrdenDeLaPuerta:
    def test_el_default_es_503_hasta_para_un_admin(self, app_client, corpus):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente)
        assert respuesta.status_code == 503
        detalle = respuesta.json()["detail"]
        assert detalle["error"] == "funcionalidad_no_disponible"
        assert detalle["causa"] == "conocimiento_normas_enabled"

    def test_el_flag_nace_apagado(self):
        from app.config import Settings

        assert Settings.model_fields["conocimiento_normas_enabled"].default is False

    def test_el_flag_se_evalua_antes_que_el_auth(self, app_client, corpus):
        """With the surface off, an anonymous caller learns nothing about it."""
        _app, cliente = app_client
        assert _post(cliente).status_code == 503

    def test_con_qa_apagado_y_normas_encendido_las_normas_responden_y_el_buzon_no(
        self, app_client, normas_on, corpus
    ):
        app, cliente = app_client
        _como(app, "admin")
        assert settings.conocimiento_qa_enabled is False
        assert _post(cliente).status_code == 200
        buzon = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        assert buzon.status_code == 503
        assert buzon.json()["detail"]["causa"] == "conocimiento_qa_enabled"

    def test_con_qa_encendido_y_normas_apagado_las_normas_siguen_apagadas(
        self, app_client, monkeypatch, corpus
    ):
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(settings, "conocimiento_qa_enabled", True)
        respuesta = _post(cliente)
        assert respuesta.status_code == 503
        assert respuesta.json()["detail"]["causa"] == "conocimiento_normas_enabled"

    def test_anonimo_es_401(self, app_client, normas_on, corpus):
        _app, cliente = app_client
        assert _post(cliente).status_code == 401

    @pytest.mark.parametrize("rol", ["operador", "ciudadano"])
    def test_por_debajo_de_admin_es_403(self, app_client, normas_on, corpus, rol):
        app, cliente = app_client
        _como(app, rol)
        assert _post(cliente).status_code == 403

    def test_el_admin_va_antes_que_el_corpus(self, app_client, normas_on):
        """No corpus AND not an admin: the caller learns nothing about the corpus."""
        app, cliente = app_client
        _como(app, "operador")
        assert _post(cliente).status_code == 403

    def test_sin_corpus_activo_es_503_con_su_causa(self, app_client, normas_on):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente)
        assert respuesta.status_code == 503
        detalle = respuesta.json()["detail"]
        assert detalle["error"] == "base_de_conocimiento_no_lista"
        assert detalle["causa"] == "sin_corpus_activo"

    def test_un_corpus_inactivo_no_cuenta(self, app_client, normas_on, db_session_factory):
        app, cliente = app_client
        _como(app, "admin")
        sesion = db_session_factory()
        try:
            seed(sesion, activo=False)
            sesion.commit()
        finally:
            sesion.close()
        respuesta = _post(cliente)
        assert respuesta.status_code == 503
        assert respuesta.json()["detail"]["causa"] == "sin_corpus_activo"


class TestNoPideNadaDelBuzon:
    def test_ni_terminos_ni_credencial_ni_sidecar(
        self, app_client, normas_on, corpus, sonda, monkeypatch
    ):
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(settings, "conocimiento_proveedor_api_key", "")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "container down")
        respuesta = _post(cliente)
        assert respuesta.status_code == 200
        assert sonda.consultas == 0

    def test_no_gasta_cuota_ni_limitador_del_buzon(
        self, app_client, normas_on, corpus, limitador, monkeypatch
    ):
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(settings, "conocimiento_quota_diaria_usuario", 0)
        assert _post(cliente).status_code == 200
        assert limitador.claves == []


class TestLasDosFormas:
    def test_sin_barra_va_ordenada_por_clave_y_sin_rango(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente)
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        claves = [unidad["citation_key"] for unidad in cuerpo["unidades"]]
        assert claves
        assert claves == sorted(claves)
        assert cuerpo["orden_presentado"] is False
        assert cuerpo["modo"] == "bm25_sin_ce"
        assert cuerpo["corpus_sha"] == SHA
        assert cuerpo["nota_orden"]
        crudo = respuesta.text.lower()
        for prohibido in ("rango", "score", "valor_bm25", "distancia", "orden_modo"):
            assert prohibido not in crudo, prohibido

    def test_con_barra_superada_lleva_rango_y_el_modo_que_ordeno(
        self, app_client, normas_on, corpus, barra_superada
    ):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente)
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["orden_presentado"] is True
        assert cuerpo["orden_modo"] == "bm25_sin_ce"
        assert [unidad["rango"] for unidad in cuerpo["unidades"]] == list(
            range(1, len(cuerpo["unidades"]) + 1)
        )
        crudo = respuesta.text.lower()
        for prohibido in ("score", "valor_bm25", "distancia"):
            assert prohibido not in crudo, prohibido

    def test_una_barra_de_otro_sha_no_desbloquea_el_orden(
        self, app_client, normas_on, corpus, barra_superada
    ):
        barra_superada(corpus_sha=OTRO_SHA)
        app, cliente = app_client
        _como(app, "admin")
        cuerpo = _post(cliente).json()
        assert cuerpo["orden_presentado"] is False
        assert all("rango" not in unidad for unidad in cuerpo["unidades"])

    def test_cada_unidad_lleva_texto_y_procedencia(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        unidad = _post(cliente).json()["unidades"][0]
        assert set(unidad) >= {
            "citation_key",
            "documento_id",
            "texto",
            "tipo",
            "es_secundaria",
            "jurisdiccion",
            "estado_vigencia",
            "relevancia_consorcio",
        }


class TestResultadoVacio:
    def test_es_200_con_sin_unidades_y_sin_campo_de_abstencion(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente, {"consulta": "zzzz qqqq"})
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["sin_unidades"] is True
        assert cuerpo["unidades"] == []
        assert cuerpo["orden_presentado"] is False
        assert "abstenc" not in respuesta.text.lower()
        assert "abstain" not in respuesta.text.lower()

    def test_con_barra_superada_un_resultado_vacio_sigue_sin_orden(
        self, app_client, normas_on, corpus, barra_superada
    ):
        app, cliente = app_client
        _como(app, "admin")
        cuerpo = _post(cliente, {"consulta": "zzzz qqqq"}).json()
        assert cuerpo["sin_unidades"] is True
        assert cuerpo["orden_presentado"] is False


class TestElCuerpo:
    def test_un_parametro_modo_en_el_cuerpo_es_422(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        for modo in ("bm25_ce", "bm25_sin_ce", "fts"):
            respuesta = _post(cliente, {"consulta": CONSULTA, "modo": modo})
            assert respuesta.status_code == 422, modo
            assert respuesta.json()["detail"]["error"] == "cuerpo_invalido"

    def test_un_modo_en_la_query_string_se_ignora_y_no_elige_el_brazo(
        self, app_client, normas_on, corpus
    ):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = cliente.post(f"{BUSCAR}?modo=bm25_ce", json={"consulta": CONSULTA})
        assert respuesta.status_code == 200
        assert respuesta.json()["modo"] == "bm25_sin_ce"

    def test_el_esquema_publicado_no_tiene_modo(self, app_client):
        _app, cliente = app_client
        esquema = cliente.get("/openapi.json").json()
        operacion = esquema["paths"]["/api/v2/conocimiento/normas/buscar"]["post"]
        propiedades = operacion["requestBody"]["content"]["application/json"]["schema"][
            "properties"
        ]
        assert set(propiedades) == {"consulta", "k"}
        assert not [p for p in operacion.get("parameters", []) if p["name"] == "modo"]

    @pytest.mark.parametrize(
        "cuerpo",
        [
            {},
            {"consulta": ""},
            {"consulta": "   "},
            {"consulta": CONSULTA, "k": 0},
            {"consulta": CONSULTA, "k": 51},
            {"consulta": 7},
            {"consulta": "x" * 2001},
        ],
    )
    def test_un_cuerpo_invalido_es_422_y_no_un_500(self, app_client, normas_on, corpus, cuerpo):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente, cuerpo)
        assert respuesta.status_code == 422
        assert respuesta.json()["detail"]["error"] == "cuerpo_invalido"

    def test_un_json_invalido_es_422(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = cliente.post(
            BUSCAR, content=b"{no es json", headers={"content-type": "application/json"}
        )
        assert respuesta.status_code == 422

    def test_el_error_no_repite_el_cuerpo_rechazado(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        respuesta = _post(cliente, {"consulta": CONSULTA, "modo": "SECRETO-123"})
        assert "SECRETO-123" not in respuesta.text

    def test_k_acota_la_cantidad_de_unidades(self, app_client, normas_on, corpus):
        app, cliente = app_client
        _como(app, "admin")
        cuerpo = _post(cliente, {"consulta": CONSULTA, "k": 2}).json()
        assert len(cuerpo["unidades"]) == 2

    def test_un_cuerpo_gigante_se_rechaza_antes_de_parsearlo(
        self, app_client, normas_on, corpus, monkeypatch
    ):
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(settings, "conocimiento_max_body_bytes", 64)
        respuesta = _post(cliente, {"consulta": "x" * 500})
        assert respuesta.status_code == 413


def test_solo_las_rutas_de_normas_llegan_al_nucleo():
    """Retrieval is not a mailbox feature. One call site, two normas paths."""
    from pathlib import Path

    from app.domains.conocimiento import router as modulo

    texto = Path(modulo.__file__).read_text(encoding="utf-8")
    assert texto.count("normas.buscar(") == 1
    assert "service.recuperar(" not in texto
    assert texto.count("editor.exportar(") == 1
    caminos = sorted(
        getattr(ruta, "path", "")
        for ruta in modulo.router.routes
        if "/normas" in getattr(ruta, "path", "")
    )
    assert caminos == [
        "/conocimiento/normas/buscar",
        "/conocimiento/normas/pedidos/{pedido_id}/exportar",
    ]
