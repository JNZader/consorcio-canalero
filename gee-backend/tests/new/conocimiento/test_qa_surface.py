"""The V1 HTTP surface: auth, the enablement AND, the mailbox, the diagnostic (U7).

This file REPLACES `test_rag_no_router.py`, and the replacement is the same work
unit on purpose (task 7.4). V0's test asserted an ABSENCE — no `router.py`,
nothing under `app/api/v2/` naming the domain, no mounted route reaching
retrieval — because an unmounted router is dead code a contributor wires up by
accident and the thing it would expose is a legal-retrieval endpoint with no auth
story. Deleting that guard alone would leave the absence unasserted and the
presence untested at the same time; V1 removes it by shipping the contract it was
waiting for.

Nothing here touches the network. The sidecar probe and the provider adapter are
both replaced through the seams the production wiring uses.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.domains.conocimiento import buzon, router as conocimiento_router
from app.domains.conocimiento.embed_sidecar import SidecarNoDisponible

BASE = "/api/v2/conocimiento"
PREGUNTAS = f"{BASE}/preguntas"


class SondaFalsa:
    """A `/ready` probe with a scripted answer and no socket."""

    def __init__(self, fallo: SidecarNoDisponible | None = None) -> None:
        self.fallo = fallo
        self.consultas = 0

    def exigir_listo(self, **_kwargs) -> None:
        self.consultas += 1
        if self.fallo is not None:
            raise self.fallo

    def invalidar(self) -> None:  # pragma: no cover - shape only
        pass


class LimitadorFalso:
    """A rate limiter with no Redis and no clock.

    Replaced rather than exercised for real: `DistributedRateLimiter` reaches for
    `settings.redis_url` and, with no Redis on the box, spends its connect
    timeout on every single request before falling back to its in-memory window.
    That turns an auth test suite into a several-minute one and measures the
    fallback, not the route.
    """

    def __init__(self, permite: bool = True) -> None:
        self.permite = permite
        self.claves: list[str] = []

    async def check(self, clave: str):
        self.claves.append(clave)
        return (self.permite, 0, 30)


@pytest.fixture
def sonda() -> SondaFalsa:
    return SondaFalsa()


@pytest.fixture
def limitador() -> LimitadorFalso:
    return LimitadorFalso()


@pytest.fixture
def app_client(db_session_factory, sonda, limitador, monkeypatch, tmp_path):
    """The REAL assembled app, with only the DB, the probe and the store replaced.

    The route table is exercised through TestClient rather than walked, per the
    module-identity pathology documented in `test_ficha_router_contract.py`.
    """
    from app.config import settings as ajustes
    from app.db.session import get_db
    from app.main import app

    # The DEPLOYMENT-WIDE middleware limiter is stood down for this module, and
    # the reason is a real interaction rather than convenience: it is a process
    # singleton with a 100-request window keyed on the client IP, every
    # TestClient in the suite shares that IP, and its in-memory fallback window
    # does not reset between modules. This file makes ~50 requests, which is
    # enough to spend the shared budget and fail whatever HTTP module happens to
    # run next — a failure with no relationship to the code that caused it. What
    # this module tests is the conocimiento route's OWN limiter, which is
    # injected above and asserted directly.
    monkeypatch.setattr(ajustes, "rate_limit_disabled", True)

    def _get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[conocimiento_router.get_sonda_sidecar] = lambda: sonda
    app.dependency_overrides[conocimiento_router.get_conocimiento_rate_limiter] = lambda: limitador
    # A fresh in-process counter per test: the quota is a module singleton and a
    # leaked count would make an unrelated test fail with "quota exhausted".
    from app.domains.conocimiento.costos import AlmacenEnMemoria

    almacen = AlmacenEnMemoria()
    app.dependency_overrides[conocimiento_router.get_almacen_cuota] = lambda: almacen

    from fastapi.testclient import TestClient

    cliente = TestClient(app, raise_server_exceptions=False)
    cliente.headers.update({"Host": "localhost"})
    yield app, cliente
    app.dependency_overrides.clear()


@pytest.fixture
def habilitado(monkeypatch, tmp_path):
    """Every ANDed enablement fact TRUE, so the tests below can turn one off.

    The terms record is written to a temp file and pointed at through
    `cargar_terminos`'s seam — never by editing the checked-in one, whose
    `verificado: false` is itself an asserted fact (`test_el_registro_que_esta_
    hoy_en_el_repo_no_habilita_el_flag`).
    """
    import yaml

    from app.config import settings
    from app.domains.conocimiento import proveedores

    registro = tmp_path / "terminos.yaml"
    registro.write_text(
        yaml.safe_dump(
            {
                "verificado": True,
                "modelo_id": settings.conocimiento_modelo,
                "pool": settings.conocimiento_pool,
                "no_entrenamiento": True,
                "retencion_dias": 30,
                "verificado_el": "2026-08-24",
                "verificado_por": "owner",
                "fuente_url": "https://example.test/terms",
                "sha256_terminos": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        conocimiento_router, "cargar_terminos", lambda: proveedores.cargar_terminos(registro)
    )
    monkeypatch.setattr(settings, "conocimiento_qa_enabled", True)
    monkeypatch.setattr(settings, "conocimiento_proveedor_api_key", "clave-de-prueba")
    monkeypatch.setattr(settings, "conocimiento_quota_diaria_usuario", 5)
    return settings


def _como(app, rol: str, user_id=None):
    from app.auth.dependencies import current_active_user
    from app.auth.models import UserRole

    app.dependency_overrides[current_active_user] = lambda: SimpleNamespace(
        id=user_id or uuid.uuid4(), role=UserRole(rol), is_active=True, is_superuser=False
    )


def _usuario(db_session_factory) -> uuid.UUID:
    from app.auth.models import User, UserRole

    sesion = db_session_factory()
    try:
        usuario = User(
            email=f"cd-{uuid.uuid4().hex[:10]}@test.com",
            hashed_password="fakehash",
            nombre="Comisión",
            apellido="Directiva",
            role=UserRole.ADMIN,
        )
        sesion.add(usuario)
        sesion.commit()
        return usuario.id
    finally:
        sesion.close()


# ---------------------------------------------------------------------------
# Task 7.4 — the auth contract the deleted absence-test was waiting for
# ---------------------------------------------------------------------------


class TestAuth:
    def test_anonimo_es_401(self, app_client, habilitado):
        _app, cliente = app_client
        assert cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"}).status_code == 401
        assert cliente.get(PREGUNTAS).status_code == 401
        assert cliente.get(f"{BASE}/estado").status_code == 401

    @pytest.mark.parametrize("rol", ["operador", "ciudadano"])
    def test_operador_y_ciudadano_son_403(self, app_client, habilitado, rol):
        """`require_admin` is V1's APPROXIMATION of the Comisión Directiva role.

        The real role is follow-up F3. What must hold today is that nobody below
        admin reaches a surface that spends money and sends a question out of the
        box.
        """
        app, cliente = app_client
        _como(app, rol)
        assert cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"}).status_code == 403
        assert cliente.get(PREGUNTAS).status_code == 403
        assert cliente.get(f"{BASE}/estado").status_code == 403

    @pytest.mark.parametrize("rol", ["operador", "ciudadano"])
    def test_el_detalle_de_UN_item_tambien_es_403(
        self, app_client, habilitado, db_session_factory, rol
    ):
        """The by-id route carries the verbatim question a CD member asked.

        It was the one route in the family with no auth test of its own, and the
        one whose response body is a person's question rather than a list of
        their own. The id is real so the assertion cannot pass on a 404.
        """
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": "pregunta privada"}).json()
        _como(app, rol)
        assert cliente.get(f"{PREGUNTAS}/{creado['id']}").status_code == 403

    def test_el_detalle_de_UN_item_es_401_para_un_anonimo(
        self, app_client, habilitado, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": "pregunta privada"}).json()
        from app.auth.dependencies import current_active_user

        app.dependency_overrides.pop(current_active_user, None)
        assert cliente.get(f"{PREGUNTAS}/{creado['id']}").status_code == 401

    def test_con_el_flag_apagado_hasta_un_admin_recibe_503(self, app_client):
        """The kill switch, and its default. No flag set anywhere is OFF."""
        app, cliente = app_client
        _como(app, "admin")
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        assert resp.status_code == 503
        assert resp.json()["detail"]["error"] == "funcionalidad_no_disponible"

    def test_el_flag_se_evalua_ANTES_que_el_auth_no_expone_la_superficie(self, app_client):
        """With the surface off, an anonymous caller learns nothing about it."""
        _app, cliente = app_client
        assert cliente.post(PREGUNTAS, json={"pregunta": "x"}).status_code == 503


# ---------------------------------------------------------------------------
# Task 7.2 — THE THREE ANDED FACTS, each with its own named cause
# ---------------------------------------------------------------------------


class TestLaHabilitacionEsUnAND:
    def _causa(self, cliente) -> tuple[int, dict]:
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley 9750?"})
        return resp.status_code, resp.json().get("detail", {})

    def test_terminos_sin_verificar_refusan_con_su_causa(self, app_client, habilitado, monkeypatch):
        """THE gap U6 left: the terms gate had no caller on the serving path.

        Without this dependency, flipping `conocimiento_qa_enabled` would have
        served questions against a record marked `verificado: false` — and the
        only thing enforcing A2's "if those terms cannot be verified, the flag is
        NOT enabled" would have been somebody remembering.
        """
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        codigo, detalle = self._causa(cliente)
        assert codigo == 503
        assert detalle["error"] == "base_de_conocimiento_no_lista"
        assert detalle["causa"] == "terminos_no_verificados"

    def test_el_registro_QUE_ESTA_HOY_EN_EL_REPO_no_habilita_la_superficie(
        self, app_client, monkeypatch
    ):
        """End to end, against the real checked-in record. It ships unverified,
        so the surface refuses today — which is the honest state until the owner
        performs `docs/rag/proveedor-terminos.md`."""
        from app.config import settings

        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(settings, "conocimiento_qa_enabled", True)
        monkeypatch.setattr(settings, "conocimiento_proveedor_api_key", "clave")
        codigo, detalle = self._causa(cliente)
        assert codigo == 503
        assert detalle["causa"] == "terminos_no_verificados"

    def test_la_credencial_ausente_refusa_con_su_causa_y_no_con_un_500(
        self, app_client, habilitado, monkeypatch
    ):
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        codigo, detalle = self._causa(cliente)
        assert codigo == 503
        assert detalle["causa"] == "credencial_ausente"

    def test_el_sidecar_caido_refusa_con_su_causa(self, app_client, habilitado, sonda):
        app, cliente = app_client
        _como(app, "admin")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "container down")
        codigo, detalle = self._causa(cliente)
        assert codigo == 503
        assert detalle["causa"] == "embedder_no_listo"

    def test_el_orden_es_TERMINOS_primero(self, app_client, habilitado, monkeypatch, sonda):
        """With all three false, the cause named is the terms record.

        Order is not cosmetic: the terms gate is the only one of the three that
        governs whether the law text and a CD member's verbatim question may
        LEAVE THE BOX at all.
        """
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "down")
        _codigo, detalle = self._causa(cliente)
        assert detalle["causa"] == "terminos_no_verificados"

    def test_la_sonda_del_sidecar_NO_se_consulta_con_terminos_rotos(
        self, app_client, habilitado, monkeypatch, sonda
    ):
        """Short-circuit, so a refused deployment does not poll a container."""
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        self._causa(cliente)
        assert sonda.consultas == 0


class TestLasLecturasNoTomanElAND:
    """W5: reading a stored answer needs no embedder, credential or terms.

    Nothing leaves the box and nothing is computed. Gating the reads on the full
    AND made the bandeja — and the `demorado` badge that explains the silence —
    disappear at exactly the moment something was wrong, which is when a CD
    member most needs to look at it.
    """

    @pytest.fixture
    def _con_todo_roto(self, habilitado, monkeypatch, sonda):
        """Flag ON, every other enablement fact FALSE."""
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "container down")
        return habilitado

    def test_el_listado_se_lee_con_el_sidecar_caido(
        self, app_client, habilitado, db_session_factory, monkeypatch, sonda
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        assert cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"}).status_code == 202
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "container down")
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        listado = cliente.get(PREGUNTAS)
        assert listado.status_code == 200
        assert [item["pregunta"] for item in listado.json()] == ["¿qué dice la ley?"]

    def test_el_detalle_se_lee_con_el_sidecar_caido(
        self, app_client, habilitado, db_session_factory, monkeypatch, sonda
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"}).json()
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "container down")
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        detalle = cliente.get(f"{PREGUNTAS}/{creado['id']}")
        assert detalle.status_code == 200
        assert detalle.json()["estado"] == "pendiente"

    def test_el_SUBMIT_sigue_exigiendo_el_AND_completo(
        self, app_client, _con_todo_roto, db_session_factory
    ):
        """The other direction, and the one that matters: submitting is what
        spends a quota slot and sends the question out of the box."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        assert resp.status_code == 503
        assert resp.json()["detail"]["causa"] == "terminos_no_verificados"

    def test_las_lecturas_SIGUEN_detras_del_kill_switch(self, app_client, db_session_factory):
        """Exempt from the AND is not exempt from the flag: a deployment that
        never turned the surface on exposes none of it."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        assert cliente.get(PREGUNTAS).status_code == 503
        assert cliente.get(f"{PREGUNTAS}/{uuid.uuid4()}").status_code == 503

    def test_las_lecturas_NO_consultan_la_sonda(
        self, app_client, habilitado, db_session_factory, sonda
    ):
        """Not just tolerated — not asked at all. A readiness probe on a read is
        a network call added to an operation that needs no network."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        antes = sonda.consultas
        cliente.get(PREGUNTAS)
        assert sonda.consultas == antes


class TestElLimiteDelListado:
    """W6: `limite` reaches `LIMIT`, so it is validated rather than trusted."""

    @pytest.mark.parametrize("valor", [-1, 0, 201])
    def test_un_limite_fuera_de_rango_es_422_y_no_un_500(
        self, app_client, habilitado, db_session_factory, valor
    ):
        """A negative `LIMIT` is a `ProgrammingError` rendered as a 500, which
        reports a broken deployment for a caller's typo."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        assert cliente.get(PREGUNTAS, params={"limite": valor}).status_code == 422

    def test_el_tope_exacto_se_acepta(self, app_client, habilitado, db_session_factory):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        tope = conocimiento_router.LIMITE_MAXIMO
        assert cliente.get(PREGUNTAS, params={"limite": tope}).status_code == 200
        assert cliente.get(PREGUNTAS, params={"limite": 1}).status_code == 200


class TestLaSondaNoConvierteUnaConfigRotaEn500:
    """S4: a malformed `conocimiento_embed_url` is a config fault, not a 500.

    Most bad values already land as `embedder_inalcanzable` through the sidecar
    adapter, and that is asserted here too so the fix cannot be read as covering
    more than it does. Two families escape it because they are not
    `httpx.HTTPError`, which is the only family the adapter translates: an
    unclosed IPv6 bracket raises inside `httpx.Client(...)` itself, and an
    invalid IDNA host raises `UnicodeError` at request time. Both were a 500 on
    a readiness gate, which sends the operator to look for a dead container
    instead of at the env var they mistyped.
    """

    def _refusal(self, monkeypatch, url):
        from app.config import settings
        from app.domains.conocimiento.embed_sidecar import SidecarNoDisponible as Refusal

        monkeypatch.setattr(settings, "conocimiento_embed_url", url)
        monkeypatch.setattr(settings, "conocimiento_embed_timeout_s", 0.5)
        sonda = conocimiento_router.SondaSidecar(ttl_s=0.0)
        with pytest.raises(Refusal) as capturado:
            sonda.exigir_listo()
        return capturado.value

    @pytest.mark.parametrize("url", ["http://[::1", "http://xn--", "http://" + "a" * 300 + ".test"])
    def test_una_url_que_NINGUNA_capa_nombraba_es_embedder_no_listo(self, monkeypatch, url):
        assert self._refusal(monkeypatch, url).causa == conocimiento_router.CAUSA_EMBEDDER

    @pytest.mark.parametrize("url", ["ftp://embed:8002", "no-es-una-url", ""])
    def test_las_que_YA_estaban_cubiertas_siguen_siendo_del_adaptador(self, monkeypatch, url):
        """Unchanged on purpose: an unset or unroutable URL is the adapter's
        named refusal and stays that way."""
        assert self._refusal(monkeypatch, url).causa in {
            "embedder_inalcanzable",
            conocimiento_router.CAUSA_EMBEDDER,
        }


# ---------------------------------------------------------------------------
# Task 7.1 — submit -> id -> status, and the listing
# ---------------------------------------------------------------------------


class TestElBuzon:
    def test_el_submit_devuelve_id_y_pendiente_y_NUNCA_una_respuesta(
        self, app_client, habilitado, db_session_factory
    ):
        """A3's whole restructuring: the submit call cannot answer."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley 9750?"})
        assert resp.status_code == 202
        cuerpo = resp.json()
        assert cuerpo["estado"] == "pendiente"
        uuid.UUID(cuerpo["id"])
        assert "respuesta" not in cuerpo and "citas" not in cuerpo

    def test_el_estado_de_un_item_se_consulta_por_id(
        self, app_client, habilitado, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley 9750?"}).json()
        item = cliente.get(f"{PREGUNTAS}/{creado['id']}")
        assert item.status_code == 200
        assert item.json()["estado"] == "pendiente"
        assert item.json()["pregunta"] == "¿qué dice la ley 9750?"
        assert item.json()["respuesta"] is None

    def test_el_item_de_otro_admin_es_404_y_no_403(
        self, app_client, habilitado, db_session_factory
    ):
        """A 403 confirms the id exists, and the row holds the verbatim question
        a specific person asked."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": "pregunta privada"}).json()
        _como(app, "admin", _usuario(db_session_factory))
        assert cliente.get(f"{PREGUNTAS}/{creado['id']}").status_code == 404

    def test_el_listado_solo_muestra_lo_propio(self, app_client, habilitado, db_session_factory):
        app, cliente = app_client
        mio = _usuario(db_session_factory)
        _como(app, "admin", mio)
        cliente.post(PREGUNTAS, json={"pregunta": "mía"})
        _como(app, "admin", _usuario(db_session_factory))
        cliente.post(PREGUNTAS, json={"pregunta": "ajena"})
        _como(app, "admin", mio)
        preguntas = [item["pregunta"] for item in cliente.get(PREGUNTAS).json()]
        assert preguntas == ["mía"]

    def test_una_pregunta_vacia_es_422_y_no_ocupa_la_cola(
        self, app_client, habilitado, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        resp = cliente.post(PREGUNTAS, json={"pregunta": "   "})
        assert resp.status_code == 422

    def test_la_cuota_sin_configurar_REFUSA(
        self, app_client, habilitado, monkeypatch, db_session_factory
    ):
        """Blocked on the cost re-derivation (A6), and unset refuses rather than
        serving an unbounded number of billed questions."""
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        monkeypatch.setattr(habilitado, "conocimiento_quota_diaria_usuario", 0)
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        assert resp.status_code == 503
        assert resp.json()["detail"]["causa"] == "CuotaNoConfigurada"

    def test_la_cuota_diaria_se_agota(
        self, app_client, habilitado, monkeypatch, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        monkeypatch.setattr(habilitado, "conocimiento_quota_diaria_usuario", 2)
        for _ in range(2):
            assert cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice?"}).status_code == 202
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice?"})
        assert resp.status_code == 503
        assert resp.json()["detail"]["causa"] == "CuotaAgotada"

    def test_el_limitador_keyea_por_USUARIO_y_no_por_IP(
        self, app_client, habilitado, limitador, db_session_factory
    ):
        """Behind a proxy `request.client.host` collapses every admin into one
        bucket, so the ficha's `_client_ip` keying is the wrong precedent for an
        authenticated route."""
        app, cliente = app_client
        usuario = _usuario(db_session_factory)
        _como(app, "admin", usuario)
        cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        assert limitador.claves == [f"user:{usuario}"]

    def test_pasado_el_limite_es_429_y_no_encola(
        self, app_client, habilitado, limitador, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        limitador.permite = False
        resp = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        assert resp.status_code == 429
        assert cliente.get(PREGUNTAS).json() == []

    def test_un_cuerpo_gigante_se_rechaza_ANTES_de_parsearlo(
        self, app_client, habilitado, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        from app.config import settings

        gordo = "x" * (settings.conocimiento_max_body_bytes + 1024)
        resp = cliente.post(PREGUNTAS, json={"pregunta": gordo})
        assert resp.status_code == 413
        assert resp.json()["detail"]["error"] == "cuerpo_excedido"

    def test_un_cuerpo_CHUNKED_sin_content_length_tambien_se_corta(
        self, app_client, habilitado, db_session_factory
    ):
        """The guard that a declared `Content-Length` cannot cover.

        This is the case that made the body parameter untenable: FastAPI reads a
        DECLARED body before it solves route dependencies, so with `cuerpo:
        PreguntaEntrada` in the signature the whole chunked stream would already
        be in memory by the time the limit was consulted. "413 before parsing"
        has to be true of the request nobody announced the size of, or it is only
        true of the polite ones.
        """
        from app.config import settings

        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))

        def _trozos():
            enviado = 0
            while enviado <= settings.conocimiento_max_body_bytes:
                enviado += 4096
                yield b"x" * 4096

        resp = cliente.post(
            PREGUNTAS,
            content=_trozos(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413
        assert resp.json()["detail"]["error"] == "cuerpo_excedido"

    def test_un_json_invalido_es_422_y_no_un_500(self, app_client, habilitado, db_session_factory):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        resp = cliente.post(
            PREGUNTAS, content=b"{no json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "cuerpo_invalido"


# ---------------------------------------------------------------------------
# Task 7.3 + 7.6 — the diagnostic, and where a down worker becomes visible
# ---------------------------------------------------------------------------


class TestDiagnostico:
    def test_reporta_la_cola_y_no_solo_la_procedencia(
        self, app_client, habilitado, db_session_factory
    ):
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"})
        cuerpo = cliente.get(f"{BASE}/estado").json()
        assert cuerpo["profundidad_cola"] >= 1
        assert cuerpo["mas_antiguo_pendiente"] is not None
        assert cuerpo["ultima_corrida_worker"] is None
        assert cuerpo["worker_demorado"] is False

    def test_un_pendiente_viejo_marca_al_worker_como_demorado(
        self, app_client, habilitado, db_session_factory, monkeypatch
    ):
        """A3's honesty obligation: "pendiente" is only honest while it is true.

        Under the queue model there is no per-question `503
        reranker_no_disponible` any more, so this is the ONLY place a
        permanently-down worker is visible.
        """
        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": "¿qué dice la ley?"}).json()
        sesion = db_session_factory()
        try:
            sesion.execute(
                text(
                    "UPDATE rag_consulta SET creada_en = now() - interval '2 days' WHERE id = :id"
                ),
                {"id": uuid.UUID(creado["id"])},
            )
            sesion.commit()
        finally:
            sesion.close()

        assert cliente.get(f"{BASE}/estado").json()["worker_demorado"] is True
        assert cliente.get(f"{PREGUNTAS}/{creado['id']}").json()["demorado"] is True

    def test_sigue_respondiendo_con_el_sidecar_CAIDO(self, app_client, habilitado, sonda):
        """A diagnostic that refuses when the thing it diagnoses is broken is not
        a diagnostic. It REPORTS the three facts instead of enforcing them."""
        app, cliente = app_client
        _como(app, "admin")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "container down")
        resp = cliente.get(f"{BASE}/estado")
        assert resp.status_code == 200
        assert resp.json()["embedder_listo"] is False
        assert "embedder_no_listo" in resp.json()["causa_no_listo"]

    def test_la_causa_sigue_el_MISMO_orden_que_el_gate(
        self, app_client, habilitado, monkeypatch, sonda
    ):
        """W2: terms -> credential -> embedder, exactly as the 503 refuses.

        With all three false the diagnostic used to name the SIDECAR while the
        503 the operator was actually getting named the TERMS record, sending
        them to restart a container over a policy file. The three booleans are
        still all reported; this pins which one the single `causa` line quotes.
        """
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(conocimiento_router, "cargar_terminos", lambda: None)
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "down")
        cuerpo = cliente.get(f"{BASE}/estado").json()
        assert cuerpo["causa_no_listo"].startswith("terminos_no_verificados")
        assert (cuerpo["terminos_verificados"], cuerpo["credencial_presente"]) == (False, False)
        assert cuerpo["embedder_listo"] is False

    def test_con_los_terminos_ok_la_causa_es_la_CREDENCIAL_y_no_el_sidecar(
        self, app_client, habilitado, monkeypatch, sonda
    ):
        """The rung that actually moved: the credential is checked BEFORE the
        embedder in the gate, and now here too."""
        app, cliente = app_client
        _como(app, "admin")
        monkeypatch.setattr(habilitado, "conocimiento_proveedor_api_key", "")
        sonda.fallo = SidecarNoDisponible("embedder_no_listo", "down")
        assert (
            cliente.get(f"{BASE}/estado").json()["causa_no_listo"].startswith("credencial_ausente")
        )

    def test_reporta_embeddings_sinteticos(self, app_client, habilitado, db_session_factory):
        app, cliente = app_client
        _como(app, "admin")
        sesion = db_session_factory()
        try:
            sesion.execute(
                text(
                    "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                    "articulos_declarados, activo, embedding_modelo, embedding_sintetico) "
                    "VALUES (:sha, 'u', '2', 1, true, 'stub', true)"
                ),
                {"sha": "c" * 40},
            )
            sesion.commit()
        finally:
            sesion.close()
        cuerpo = cliente.get(f"{BASE}/estado").json()
        assert cuerpo["embedding_sintetico"] is True


# ---------------------------------------------------------------------------
# Task 7.5 (RED) — the question must reach exactly ONE outbound payload
# ---------------------------------------------------------------------------


class TestLaPreguntaNoSeEscapa:
    """Threat: the question text leaving the box.

    Amended by A3 to span submit -> queue -> worker: the QUEUED item's stored
    question must not reach any outbound payload except the worker's single
    generation call. Everything else on the path — routing, the embedder, the
    decision record — is inside the deployment.
    """

    def test_el_registro_de_ruta_devuelve_la_pregunta_VERBATIM(self, db):
        """The record has to answer the only question it was built to answer: "a
        CD member reports an operational question was answered instead of
        redirected". A digest satisfies none of that."""
        from app.domains.conocimiento import repository, routing

        pregunta = "¿Cómo tramito la baja del padrón, che?"
        decision = routing.DecisionRuta(
            pregunta=pregunta,
            clase="operational",
            superficie="/tramites",
            motivo="regla",
            margen=None,
            umbral_vigente=None,
        )
        ident = repository.registrar_decision_ruta(db, decision)
        (guardada,) = db.execute(
            text("SELECT pregunta FROM rag_decision_ruta WHERE id = :id"), {"id": ident}
        ).one()
        assert guardada == pregunta

    def test_la_pregunta_encolada_aparece_en_UN_solo_payload_saliente(self, db, monkeypatch):
        """Submit -> queue -> worker, with every seam instrumented.

        The embedder and the reranker are LOCAL (the sidecar is a container on
        the deployment's own network; the cross-encoder is the owner's GPU), so
        seeing the question there is not an escape. The provider adapter is the
        one seam that crosses the boundary, and it must see the question exactly
        once per generation.
        """
        import httpx

        from app.domains.conocimiento import service, trabajador
        from app.domains.conocimiento.proveedores import conectar_puente
        from tests.new.conocimiento.test_trabajador import (
            PARAMETROS,
            EmbedderFalso,
            RerankerFalso,
            _resultado_con_un_hit,
            centroides_hacia,
            seed,
            terminos_ok,
        )

        pregunta = "¿Qué obligaciones impone la ley 9750 al consorcista?"
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta=pregunta)
        monkeypatch.setattr(service, "recuperar", lambda *a, **k: _resultado_con_un_hit())

        salientes: list[bytes] = []

        def _transporte(peticion: httpx.Request) -> httpx.Response:
            salientes.append(peticion.content)
            return httpx.Response(
                200,
                json={"text": "Corresponde [ley-9750#art1].", "stop_reason": "stop"},
            )

        def _crear(presupuesto):
            return conectar_puente(
                "http://gateway.test",
                modelo="m",
                pool="p",
                api_key="k",
                timeout_s=5.0,
                presupuesto=presupuesto,
                transporte=httpx.MockTransport(_transporte),
            )

        item = trabajador.procesar_uno(
            db,
            corpus_sha=seed.__globals__["SHA"],
            embedder=EmbedderFalso(),
            centroides=centroides_hacia("legal"),
            parametros=PARAMETROS,
            reranker=RerankerFalso(),
            crear_generador=_crear,
            verificar_terminos_fn=terminos_ok,
        )

        assert item.estado == "respuesta"
        # The pre-claim wiring probe builds an adapter and closes it without
        # sending anything, so the outbound count below still measures ONE call.
        con_la_pregunta = [cuerpo for cuerpo in salientes if pregunta.encode("utf-8") in cuerpo]
        assert len(salientes) == 1, "more than one outbound call left the box"
        assert len(con_la_pregunta) == 1, (
            "the question must appear in EXACTLY one outbound payload — the generation call"
        )


# ---------------------------------------------------------------------------
# W4 — `mixto`, end to end: submit -> queue -> worker -> read
# ---------------------------------------------------------------------------


class TestMixtoDeExtremoAExtremo:
    """Routing spec scenarios #6 and #7, over the real submit/read surface.

    `mixto` is the one class whose contract spans BOTH legs of the response, and
    it was the only worker path with no end-to-end coverage: the `parcial`
    variable in `trabajador.procesar_uno` was set on every branch and asserted on
    none, so `parcial = None` was a live mutant — every test would still have
    passed with the redirect silently dropped. That is exactly the failure the
    spec names ("MUST NOT drop the redirect because a legal answer was
    produced"), and dropping it has no symptom on the page: the answer looks
    complete and the operational half of the question simply vanishes.

    Both scenarios go through `POST /preguntas` and are read back through
    `GET /preguntas/{id}`, so the redirect has to survive the worker AND the
    serialization the panel reads.
    """

    @pytest.fixture
    def _mixto(self, app_client, habilitado, db_session_factory, monkeypatch):
        """Submit the spec's `mixto` question and return a runner for the worker."""
        from app.domains.conocimiento import service, trabajador
        from tests.new.conocimiento import test_trabajador as fixtures

        app, cliente = app_client
        _como(app, "admin", _usuario(db_session_factory))
        creado = cliente.post(PREGUNTAS, json={"pregunta": fixtures.PREGUNTA_MIXTA}).json()
        assert creado["estado"] == "pendiente"

        def _procesar(resultado, guion):
            sesion = db_session_factory()
            try:
                fixtures.seed(sesion)
                fixtures.seed_privado(sesion)
                monkeypatch.setattr(service, "recuperar", lambda *a, **k: resultado())
                trabajador.procesar_uno(
                    sesion,
                    corpus_sha=fixtures.SHA,
                    embedder=fixtures.EmbedderFalso(),
                    centroides=fixtures.centroides_mixto(),
                    parametros=fixtures.PARAMETROS,
                    reranker=fixtures.RerankerFalso(),
                    crear_generador=lambda _p: fixtures.GeneradorFalso(guion),
                    verificar_terminos_fn=fixtures.terminos_ok,
                )
                sesion.commit()
            finally:
                sesion.close()
            return cliente.get(f"{PREGUNTAS}/{creado['id']}").json()

        return _procesar

    def test_la_pata_legal_se_responde_y_el_redirect_SIGUE_ahi(self, _mixto):
        """Spec scenario #6. The mutant this kills is `parcial = None`.

        A `mixto` answer with the redirect dropped is indistinguishable from a
        complete answer, and the operational half of the question — "cuánto debo
        yo" — disappears with no trace anywhere in the response.
        """
        from app.domains.conocimiento.generacion import SalidaProveedor
        from tests.new.conocimiento.test_trabajador import _resultado_con_un_hit

        item = _mixto(
            _resultado_con_un_hit,
            SalidaProveedor(texto="Corresponde [ley-9750#art1].", truncado=False),
        )
        assert item["estado"] == "respuesta"
        assert item["respuesta"]["citas"][0]["citation_key"] == "ley-9750#art1"

        parcial = item["respuesta"]["redireccion_parcial"]
        assert parcial is not None, "the redirect was dropped because a legal answer existed"
        assert parcial["superficie"] == "/finanzas"
        # The answer text makes no claim about the caller's balance: the debt leg
        # is a redirect, and the legal leg only ever cites the corpus.
        assert item["respuesta"]["respuesta"] == "Corresponde [ley-9750#art1]."

    def test_la_pata_legal_ABSTIENE_y_el_redirect_SIGUE_ahi(self, _mixto):
        """Spec scenario #7, and the harder half of the same contract.

        `estado` is the LEGAL leg and `redireccion_parcial` is orthogonal to it,
        which is the whole reason the schema has two fields: a single
        mutually-exclusive tag could not hold `abstencion` and a redirect at
        once. Here the only retrieved unit is `privado`, so the payload is empty
        after exclusion and no provider is called at all — and the operational
        redirect must survive that.
        """
        from tests.new.conocimiento.test_trabajador import _resultado_solo_privado

        item = _mixto(
            _resultado_solo_privado,
            AssertionError("an empty payload must never reach the provider"),
        )
        assert item["estado"] == "abstencion"
        assert item["respuesta"]["motivo"] == "exclusion_por_clasificacion"
        # The excluded KEY travels; the text and the provenance of a unit that
        # may not leave the box do not.
        assert item["respuesta"]["citas"] == []

        parcial = item["respuesta"]["redireccion_parcial"]
        assert parcial is not None, "the redirect must survive the legal part abstaining"
        assert parcial["superficie"] == "/finanzas"
