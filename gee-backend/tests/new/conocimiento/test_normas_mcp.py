# ruff: noqa: F811, F401
# The three-way equivalence test drives the same assembled app and fakes the
# mailbox tests use, so those fixtures are imported by name from their module.
"""Unit 4 — `scripts/rag_normas_mcp.py`: the MCP mirror, exactly three tools.

The server is built with the OFFICIAL SDK (`requirements-mcp.txt`, pinned), never
hand-rolled JSON-RPC. That dependency is deliberately outside the app venv and the
app image, so the tests that need it are skipped where it is absent and the ones
that do not (the tool names, the missing-install exit code) always run.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from pathlib import Path

import pytest

from scripts import rag_normas, rag_normas_mcp

from .test_normas_kernel import OTRO_SHA, SHA, barra_superada, seed, seed_otro_sha
from .test_qa_surface import BASE, _como, app_client, limitador, sonda
from .test_rag_eval_cli import _NullEngine, _SesionPrestada

CONSULTA = "canal de riego"

requiere_mcp = pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("mcp") is None,
    reason="the `mcp` SDK is not installed here (requirements-mcp.txt, separate venv)",
)


def _correr(corrutina):
    return asyncio.run(corrutina)


def _abrir(db):
    """A session opener that hands the test's session out and never closes it."""

    @contextlib.contextmanager
    def abrir():
        yield db

    return abrir


@pytest.fixture
def servidor(db):
    return rag_normas_mcp.build_server(_abrir(db))


class TestSinElSDK:
    """These run in the plain app venv: nothing here may import `mcp`."""

    def test_las_herramientas_son_las_tres_del_nucleo(self):
        assert rag_normas_mcp.TOOLS == ("buscar", "leer", "chequear")
        assert rag_normas_mcp.TOOLS == rag_normas.SUBCOMANDOS

    def test_el_modulo_se_importa_sin_el_sdk(self, monkeypatch):
        """Importing must not require `mcp`: only RUNNING the server does."""
        monkeypatch.setitem(sys.modules, "mcp", None)
        import importlib

        importlib.reload(rag_normas_mcp)

    def test_una_instalacion_ausente_sale_2_con_instrucciones(self, monkeypatch, capsys):
        monkeypatch.setitem(sys.modules, "mcp", None)
        monkeypatch.setattr(
            rag_normas_mcp,
            "create_engine",
            lambda url: (_ for _ in ()).throw(AssertionError("opened the database")),
        )
        codigo = rag_normas_mcp.main(["--database-url", "postgresql://unused/unused"])
        assert codigo == rag_normas_mcp.SALIDA_SIN_DEPENDENCIA == 2
        error = capsys.readouterr().err
        assert "requirements-mcp.txt" in error
        assert "venv-mcp" in error
        assert "scripts/rag_normas.py" in error  # the CLI works without the SDK

    def test_el_chequeo_de_la_dependencia_va_antes_que_la_base(self, monkeypatch, capsys):
        monkeypatch.setitem(sys.modules, "mcp", None)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert rag_normas_mcp.main([]) == 2
        assert "requirements-mcp.txt" in capsys.readouterr().err

    def test_no_escribe_su_propio_json_rpc(self):
        fuente = Path(rag_normas_mcp.__file__).read_text(encoding="utf-8")
        assert "jsonrpc" not in fuente.lower()
        assert "json-rpc" not in fuente.lower()

    def test_el_pin_es_exacto_y_vive_fuera_de_la_imagen(self):
        raiz = Path(rag_normas_mcp.__file__).resolve().parent.parent
        lineas = [
            linea.strip()
            for linea in (raiz / "requirements-mcp.txt").read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.lstrip().startswith("#")
        ]
        assert len(lineas) == 1
        nombre, _, version = lineas[0].partition("==")
        assert nombre == "mcp"
        assert version and all(parte.isdigit() for parte in version.split("."))
        # Not in the app's own requirements, which is what the image installs.
        app = (raiz / "requirements.txt").read_text(encoding="utf-8").lower()
        assert "mcp" not in {
            linea.split("==")[0].split(">=")[0].strip() for linea in app.splitlines()
        }


@requiere_mcp
class TestLasTresHerramientas:
    def test_lista_exactamente_buscar_leer_chequear(self, servidor):
        herramientas = _correr(servidor.list_tools())
        assert sorted(h.name for h in herramientas) == sorted(["buscar", "leer", "chequear"])
        assert len(herramientas) == 3

    def test_no_hay_redactar(self, servidor):
        nombres = {h.name for h in _correr(servidor.list_tools())}
        assert "redactar" not in nombres

    def test_buscar_no_tiene_parametro_de_modo(self, servidor):
        buscar = next(h for h in _correr(servidor.list_tools()) if h.name == "buscar")
        assert set(buscar.input_schema["properties"]) == {"consulta", "k"}

    def test_leer_y_chequear_tienen_los_parametros_del_nucleo(self, servidor):
        por_nombre = {h.name: h for h in _correr(servidor.list_tools())}
        assert set(por_nombre["leer"].input_schema["properties"]) == {"citation_key"}
        assert set(por_nombre["chequear"].input_schema["properties"]) == {
            "citation_key",
            "span",
            "vigencia",
            "sha",
        }

    def test_cada_herramienta_declara_que_no_escribe(self, servidor):
        for herramienta in _correr(servidor.list_tools()):
            assert herramienta.annotations is not None
            assert herramienta.annotations.read_only_hint is True


@requiere_mcp
class TestLlamadas:
    def _llamar(self, servidor, nombre, **argumentos):
        return _correr(servidor.call_tool(nombre, argumentos))

    def test_buscar_devuelve_el_mismo_resultado_que_el_nucleo(self, db, servidor):
        from app.domains.conocimiento import normas, service

        seed(db)
        resultado = self._llamar(servidor, "buscar", consulta=CONSULTA)
        esperado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU).model_dump(mode="json")
        assert resultado.structured_content == esperado
        assert resultado.is_error is False

    def test_buscar_sin_barra_va_por_clave_y_sin_rango(self, db, servidor):
        seed(db)
        cuerpo = self._llamar(servidor, "buscar", consulta=CONSULTA).structured_content
        claves = [u["citation_key"] for u in cuerpo["unidades"]]
        assert claves == sorted(claves)
        assert cuerpo["orden_presentado"] is False
        assert "rango" not in json.dumps(cuerpo)

    def test_buscar_con_barra_superada_lleva_rango(self, db, servidor, barra_superada):
        seed(db)
        cuerpo = self._llamar(servidor, "buscar", consulta=CONSULTA).structured_content
        assert cuerpo["orden_presentado"] is True
        assert [u["rango"] for u in cuerpo["unidades"]] == list(
            range(1, len(cuerpo["unidades"]) + 1)
        )

    def test_buscar_vacio_es_exito_con_sin_unidades(self, db, servidor):
        seed(db)
        cuerpo = self._llamar(servidor, "buscar", consulta="zzzz qqqq").structured_content
        assert cuerpo["sin_unidades"] is True
        assert "abstenc" not in json.dumps(cuerpo).lower()

    @pytest.mark.parametrize("argumentos", [{"consulta": "   "}, {"consulta": CONSULTA, "k": 51}])
    def test_buscar_rechaza_lo_que_rechaza_la_ruta(self, db, servidor, argumentos):
        from mcp.server.mcpserver.exceptions import ToolError

        seed(db)
        with pytest.raises(ToolError):
            self._llamar(servidor, "buscar", **argumentos)

    def test_buscar_sin_corpus_activo_es_un_error_de_herramienta(self, servidor):
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError, match="no active corpus"):
            self._llamar(servidor, "buscar", consulta=CONSULTA)

    def test_leer_devuelve_el_texto_exacto(self, db, servidor):
        seed(db)
        unidad = self._llamar(servidor, "leer", citation_key="9750#1").structured_content
        assert unidad["texto"] == "El consorcio administra el canal de riego."
        assert unidad["corpus_sha"] == SHA

    def test_leer_una_clave_desconocida_es_error_y_no_devuelve_texto(self, db, servidor):
        from mcp.server.mcpserver.exceptions import ToolError

        seed(db)
        seed_otro_sha(db)
        for clave in ("NO-EXISTE#9", "SOLO-OTRO#1"):
            with pytest.raises(ToolError) as error:
                self._llamar(servidor, "leer", citation_key=clave)
            assert "Texto del otro snapshot" not in str(error.value)

    def test_chequear_pasa_y_rechaza_nombrando_la_condicion(self, db, servidor):
        seed(db)
        bien = self._llamar(
            servidor,
            "chequear",
            citation_key="9750#1",
            span="administra",
            vigencia="vigente",
            sha=SHA,
        ).structured_content
        assert bien["pasa"] is True

        for cambios, condicion in (
            ({"sha": OTRO_SHA}, "sha"),
            ({"citation_key": "NO-EXISTE#9"}, "clave"),
            ({"span": "no esta"}, "span"),
            ({"vigencia": "derogada"}, "vigencia"),
        ):
            argumentos = {
                "citation_key": "9750#1",
                "span": "administra",
                "vigencia": "vigente",
                "sha": SHA,
                **cambios,
            }
            resultado = self._llamar(servidor, "chequear", **argumentos)
            # A failing verdict is an ANSWER, not a tool error: the caller reads it.
            assert resultado.is_error is False
            assert resultado.structured_content["pasa"] is False
            assert resultado.structured_content["condicion_fallida"] == condicion


@requiere_mcp
class TestLasTresSuperficiesDevuelvenLoMismo:
    @pytest.mark.parametrize("con_barra", [False, True], ids=["sin-orden", "con-orden"])
    def test_ruta_cli_y_mcp(
        self, app_client, db_session_factory, monkeypatch, capsys, request, con_barra
    ):
        from app.config import settings

        if con_barra:
            request.getfixturevalue("barra_superada")
        monkeypatch.setattr(settings, "conocimiento_normas_enabled", True)
        sesion = db_session_factory()
        try:
            seed(sesion)
            sesion.commit()
        finally:
            sesion.close()

        app, cliente = app_client
        _como(app, "admin")
        ruta = cliente.post(f"{BASE}/normas/buscar", json={"consulta": CONSULTA})
        assert ruta.status_code == 200

        monkeypatch.setattr(rag_normas, "create_engine", lambda url: _NullEngine())
        monkeypatch.setattr(rag_normas, "Session", _SesionPrestada(db_session_factory()))
        assert (
            rag_normas.main(["buscar", CONSULTA, "--database-url", "postgresql://unused/unused"])
            == 0
        )
        cli = json.loads(capsys.readouterr().out)

        mcp = _correr(
            rag_normas_mcp.build_server(_abrir(db_session_factory())).call_tool(
                "buscar", {"consulta": CONSULTA}
            )
        ).structured_content

        assert ruta.json() == cli == mcp
        assert mcp["orden_presentado"] is con_barra
