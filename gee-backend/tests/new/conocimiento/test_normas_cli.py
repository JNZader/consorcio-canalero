# ruff: noqa: F811, F401
# The route/CLI equivalence test drives the same assembled app and fakes the
# mailbox tests use, so those fixtures are imported by name from their module.
"""Unit 4 — `scripts/rag_normas.py`: three subcommands over the same kernel.

The CLI is `normas.buscar/leer/chequear` with argparse in front. Every test seeds
the kernel's mini-snapshot and hands `main()` the fixture's session, the same
pattern `scripts/rag_eval.py` is tested with: real SQL, no committed rows.
"""

from __future__ import annotations

import json

import pytest

from app.domains.conocimiento.recuperacion.reranker import (
    RerankerDeterministico,
    RerankerNoDisponible,
)
from scripts import rag_normas

from .test_normas_kernel import OTRO_SHA, SHA, barra_superada, seed, seed_otro_sha
from .test_qa_surface import BASE, _como, app_client, limitador, sonda
from .test_rag_eval_cli import _NullEngine, _SesionPrestada

CONSULTA = "canal de riego"
URL = ["--database-url", "postgresql://unused/unused"]


@pytest.fixture
def cli_normas(db, monkeypatch):
    """`rag_normas.main` over the fixture's session, with the reranker armed to refuse."""
    monkeypatch.setattr(rag_normas, "create_engine", lambda url: _NullEngine())
    monkeypatch.setattr(rag_normas, "Session", _SesionPrestada(db))

    def prohibido(*_a, **_k):
        raise AssertionError("the no-GPU arm built a reranker; it needs none")

    monkeypatch.setattr(rag_normas, "_reranker", prohibido)
    return db


def _correr(capsys, *argv):
    codigo = rag_normas.main([*argv, *URL])
    salida = capsys.readouterr()
    return codigo, salida.out, salida.err


class TestLosTresSubcomandos:
    def test_son_exactamente_buscar_leer_chequear(self):
        assert rag_normas.SUBCOMANDOS == ("buscar", "leer", "chequear")

    def test_no_hay_redactar_ni_otro_subcomando(self, capsys):
        with pytest.raises(SystemExit) as salida:
            rag_normas.main(["redactar", "algo", *URL])
        assert salida.value.code == 2
        assert "redactar" in capsys.readouterr().err

    def test_sin_subcomando_es_uso_incorrecto(self, capsys):
        with pytest.raises(SystemExit) as salida:
            rag_normas.main([])
        assert salida.value.code == 2

    def test_sin_url_de_base_sale_2(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert rag_normas.main(["buscar", CONSULTA]) == 2
        assert "--database-url" in capsys.readouterr().err


class TestBuscar:
    def test_por_defecto_es_el_brazo_sin_gpu_y_va_ordenado_por_clave(self, cli_normas, capsys):
        seed(cli_normas)
        codigo, salida, _ = _correr(capsys, "buscar", CONSULTA)
        assert codigo == 0
        cuerpo = json.loads(salida)
        assert cuerpo["modo"] == "bm25_sin_ce"
        assert cuerpo["corpus_sha"] == SHA
        claves = [unidad["citation_key"] for unidad in cuerpo["unidades"]]
        assert claves and claves == sorted(claves)
        assert cuerpo["orden_presentado"] is False
        for prohibido in ("rango", "score", "valor_bm25", "distancia", "orden_modo"):
            assert prohibido not in salida.lower(), prohibido

    def test_con_barra_superada_lleva_rango(self, cli_normas, barra_superada, capsys):
        seed(cli_normas)
        codigo, salida, _ = _correr(capsys, "buscar", CONSULTA)
        assert codigo == 0
        cuerpo = json.loads(salida)
        assert cuerpo["orden_presentado"] is True
        assert [u["rango"] for u in cuerpo["unidades"]] == list(
            range(1, len(cuerpo["unidades"]) + 1)
        )

    def test_un_resultado_vacio_es_exito_con_sin_unidades(self, cli_normas, capsys):
        seed(cli_normas)
        codigo, salida, _ = _correr(capsys, "buscar", "zzzz qqqq")
        assert codigo == 0
        cuerpo = json.loads(salida)
        assert cuerpo["sin_unidades"] is True
        assert cuerpo["unidades"] == []
        assert "abstenc" not in salida.lower()

    def test_k_acota_la_salida(self, cli_normas, capsys):
        seed(cli_normas)
        _, salida, _ = _correr(capsys, "buscar", CONSULTA, "--k", "2")
        assert len(json.loads(salida)["unidades"]) == 2

    @pytest.mark.parametrize("k", ["0", "51", "-1"])
    def test_un_k_fuera_de_rango_sale_2(self, cli_normas, capsys, k):
        seed(cli_normas)
        codigo, salida, error = _correr(capsys, "buscar", CONSULTA, "--k", k)
        assert codigo == 2
        assert salida == ""

    def test_una_consulta_en_blanco_sale_2(self, cli_normas, capsys):
        seed(cli_normas)
        codigo, salida, _ = _correr(capsys, "buscar", "   ")
        assert codigo == 2
        assert salida == ""

    def test_sin_corpus_activo_sale_1_y_no_imprime_unidades(self, cli_normas, capsys):
        codigo, salida, error = _correr(capsys, "buscar", CONSULTA)
        assert codigo == 1
        assert salida == ""
        assert "no active corpus" in error

    def test_un_corpus_inactivo_no_cuenta(self, cli_normas, capsys):
        seed(cli_normas, activo=False)
        codigo, salida, _ = _correr(capsys, "buscar", CONSULTA)
        assert codigo == 1
        assert salida == ""


class TestBuscarConElBrazoGateado:
    def test_construye_el_reranker_solo_si_se_pide_bm25_ce(self, cli_normas, monkeypatch, capsys):
        seed(cli_normas)
        construidos: list[str] = []

        def reranker(nombre, *, device):
            construidos.append(device)
            return RerankerDeterministico()

        monkeypatch.setattr(rag_normas, "_reranker", reranker)
        codigo, salida, _ = _correr(capsys, "buscar", CONSULTA, "--modo", "bm25_ce")
        assert codigo == 0
        assert construidos == ["cuda"]
        assert json.loads(salida)["modo"] == "bm25_ce"

    def test_bm25_ce_nunca_hereda_el_orden_de_la_barra_del_otro_brazo(
        self, cli_normas, barra_superada, monkeypatch, capsys
    ):
        seed(cli_normas)
        monkeypatch.setattr(
            rag_normas, "_reranker", lambda nombre, *, device: RerankerDeterministico()
        )
        _, salida, _ = _correr(capsys, "buscar", CONSULTA, "--modo", "bm25_ce")
        cuerpo = json.loads(salida)
        assert cuerpo["orden_presentado"] is False
        claves = [u["citation_key"] for u in cuerpo["unidades"]]
        assert claves == sorted(claves)
        assert "rango" not in salida

    def test_sin_cross_encoder_sale_2_con_el_motivo_y_sin_salida(
        self, cli_normas, monkeypatch, capsys
    ):
        seed(cli_normas)

        def sin_gpu(nombre, *, device):
            raise RerankerNoDisponible("no CUDA device is available")

        monkeypatch.setattr(rag_normas, "_reranker", sin_gpu)
        codigo, salida, error = _correr(capsys, "buscar", CONSULTA, "--modo", "bm25_ce")
        assert codigo == 2
        assert salida == ""
        assert "no CUDA device" in error
        assert "--modo bm25_sin_ce" in error

    def test_un_modo_que_no_existe_sale_2(self, cli_normas, capsys):
        with pytest.raises(SystemExit) as salida:
            rag_normas.main(["buscar", CONSULTA, "--modo", "vector", *URL])
        assert salida.value.code == 2


class TestLeer:
    def test_devuelve_la_unidad_exacta_y_su_procedencia(self, cli_normas, capsys):
        seed(cli_normas)
        codigo, salida, _ = _correr(capsys, "leer", "9750#1")
        assert codigo == 0
        unidad = json.loads(salida)
        assert unidad["citation_key"] == "9750#1"
        assert unidad["texto"] == "El consorcio administra el canal de riego."
        assert unidad["corpus_sha"] == SHA
        assert unidad["clasificacion"]

    def test_una_clave_desconocida_sale_1_sin_texto(self, cli_normas, capsys):
        seed(cli_normas)
        codigo, salida, error = _correr(capsys, "leer", "NO-EXISTE#9")
        assert codigo == 1
        assert salida == ""
        assert "NO-EXISTE#9" in error

    def test_una_clave_de_otro_snapshot_se_rechaza(self, cli_normas, capsys):
        seed(cli_normas)
        seed_otro_sha(cli_normas)
        codigo, salida, _ = _correr(capsys, "leer", "SOLO-OTRO#1")
        assert codigo == 1
        assert "Texto del otro snapshot" not in salida

    def test_sin_corpus_activo_sale_1(self, cli_normas, capsys):
        codigo, salida, error = _correr(capsys, "leer", "9750#1")
        assert codigo == 1
        assert salida == ""


class TestChequear:
    def _chequear(self, capsys, *, clave="9750#1", span="administra", vigencia="vigente", sha=SHA):
        argv = ["chequear", clave, "--span", span, "--sha", sha]
        if vigencia is not None:
            argv += ["--vigencia", vigencia]
        return _correr(capsys, *argv)

    def test_pasa_con_las_cuatro_condiciones(self, cli_normas, capsys):
        seed(cli_normas)
        codigo, salida, _ = self._chequear(capsys)
        assert codigo == 0
        veredicto = json.loads(salida)
        assert veredicto["pasa"] is True
        assert veredicto["condicion_fallida"] is None

    @pytest.mark.parametrize(
        ("cambios", "condicion"),
        [
            ({"sha": OTRO_SHA}, "sha"),
            ({"clave": "NO-EXISTE#9"}, "clave"),
            ({"span": "texto que no esta"}, "span"),
            ({"span": ""}, "span"),
            ({"vigencia": "derogada"}, "vigencia"),
        ],
    )
    def test_cada_rechazo_sale_1_y_nombra_la_condicion(
        self, cli_normas, capsys, cambios, condicion
    ):
        seed(cli_normas)
        codigo, salida, _ = self._chequear(capsys, **cambios)
        assert codigo == 1
        veredicto = json.loads(salida)
        assert veredicto["pasa"] is False
        assert veredicto["condicion_fallida"] == condicion
        assert condicion in veredicto["detalle"]


class TestLaCLIEsElMismoNucleoQueLaRuta:
    def _sembrar(self, db_session_factory):
        sesion = db_session_factory()
        try:
            seed(sesion)
            sesion.commit()
        finally:
            sesion.close()

    @pytest.mark.parametrize("con_barra", [False, True], ids=["sin-orden", "con-orden"])
    def test_misma_consulta_mismas_unidades_y_mismos_campos(
        self, app_client, db_session_factory, monkeypatch, capsys, request, con_barra
    ):
        from app.config import settings

        if con_barra:
            request.getfixturevalue("barra_superada")
        monkeypatch.setattr(settings, "conocimiento_normas_enabled", True)
        self._sembrar(db_session_factory)

        app, cliente = app_client
        _como(app, "admin")
        ruta = cliente.post(f"{BASE}/normas/buscar", json={"consulta": CONSULTA})
        assert ruta.status_code == 200

        monkeypatch.setattr(rag_normas, "create_engine", lambda url: _NullEngine())
        monkeypatch.setattr(rag_normas, "Session", _SesionPrestada(db_session_factory()))
        codigo, salida, _ = _correr(capsys, "buscar", CONSULTA)
        assert codigo == 0

        assert json.loads(salida) == ruta.json()
        assert json.loads(salida)["orden_presentado"] is con_barra
