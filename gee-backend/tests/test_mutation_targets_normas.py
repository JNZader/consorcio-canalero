"""DB-free tests for the norms mutation targets.

The shared cosmic-ray job runs its test command once per mutant and forbids a
database. ``tests/new/conocimiento/test_normas_*.py`` open Postgres, so they
cannot be that command. These tests mock the repository and the retrieval call
and hit both sides of the fail-closed branches in ``normas.py``, ``editor.py``
and ``eval/barra_sin_gpu.py``.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.domains.conocimiento import editor, normas, repository, service
from app.domains.conocimiento.eval import barra_sin_gpu
from app.domains.conocimiento.schemas import CitaRecuperada, ResultadoRecuperacion

SHA = "a" * 40
OTRO = "b" * 40
AHORA = datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc)


def _activo(sha: str = SHA) -> repository.CorpusActivo:
    return repository.CorpusActivo(corpus_sha=sha, ingested_at=AHORA)


def _fila(**cambios: object) -> dict[str, object]:
    fila: dict[str, object] = {
        "citation_key": "8803#1",
        "documento_id": "ley-8803",
        "tipo_chunk": "articulo",
        "texto": "TODA persona tiene derecho",
        "tipo": "ley",
        "es_secundaria": False,
        "jurisdiccion": "cordoba",
        "estado_vigencia": "VIGENTE",
        "clasificacion": "publico",
        "source_file": "ley-8803-acceso-informacion-cordoba.md",
        "source_offset": 0,
    }
    fila.update(cambios)
    return fila


def _parchear_lectura(monkeypatch: pytest.MonkeyPatch, fila: dict[str, object] | None) -> None:
    monkeypatch.setattr(normas.repository, "leer_corpus_activo", lambda _db: _activo())
    monkeypatch.setattr(normas.repository, "leer_unidad", lambda _db, _sha, _clave: fila)


def _chequear(span: str = "TODA persona", vigencia: str | None = "VIGENTE", sha: str = SHA):
    return normas.chequear(MagicMock(), "8803#1", span, vigencia, sha)


class TestChequear:
    def test_pasa_solo_cuando_las_cuatro_condiciones_se_cumplen(self, monkeypatch) -> None:
        _parchear_lectura(monkeypatch, _fila())
        veredicto = _chequear()
        assert veredicto.pasa is True
        assert veredicto.clasificacion == "publico"
        assert veredicto.condicion_fallida is None

    def test_sin_corpus_activo_falla_en_sha_y_no_lee_una_unidad(self, monkeypatch) -> None:
        monkeypatch.setattr(normas.repository, "leer_corpus_activo", lambda _db: None)
        monkeypatch.setattr(
            normas.repository,
            "leer_unidad",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("leyó una unidad")),
        )
        veredicto = _chequear()
        assert veredicto.pasa is False
        assert veredicto.condicion_fallida == "sha"

    def test_un_sha_viejo_falla_antes_de_la_clave(self, monkeypatch) -> None:
        monkeypatch.setattr(normas.repository, "leer_corpus_activo", lambda _db: _activo(OTRO))
        monkeypatch.setattr(
            normas.repository,
            "leer_unidad",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("leyó una unidad")),
        )
        veredicto = _chequear()
        assert veredicto.condicion_fallida == "sha"
        assert SHA in veredicto.detalle

    def test_la_clave_ausente_nombra_clave(self, monkeypatch) -> None:
        _parchear_lectura(monkeypatch, None)
        assert _chequear().condicion_fallida == "clave"

    def test_el_span_vacio_no_es_una_cita(self, monkeypatch) -> None:
        _parchear_lectura(monkeypatch, _fila())
        veredicto = _chequear(span="")
        assert veredicto.condicion_fallida == "span"
        assert veredicto.clasificacion == "publico"

    def test_el_span_tiene_que_ser_subcadena_literal(self, monkeypatch) -> None:
        _parchear_lectura(monkeypatch, _fila())
        assert _chequear(span="toda persona").condicion_fallida == "span"
        assert _chequear(span="TODA persona").pasa is True

    def test_la_vigencia_tiene_que_ser_igual(self, monkeypatch) -> None:
        _parchear_lectura(monkeypatch, _fila())
        veredicto = _chequear(vigencia="DEROGADA")
        assert veredicto.condicion_fallida == "vigencia"
        assert "DEROGADA" in veredicto.detalle


def _hit(clave: str, rango: int) -> CitaRecuperada:
    return CitaRecuperada(
        citation_key=clave,
        documento_id="ley-8803",
        tipo_chunk="articulo",
        texto="texto",
        tipo="ley",
        es_secundaria=False,
        jurisdiccion="cordoba",
        clasificacion="publico",
        source_file="ley.md",
        source_offset=0,
        rango_bm25=rango,
        valor_bm25=3.5,
        score_rrf=0.2,
        score_ce=1.1,
    )


def _buscar(monkeypatch: pytest.MonkeyPatch, hits: list[CitaRecuperada], *, modo: str, barra: bool):
    monkeypatch.setattr(normas.repository, "leer_corpus_activo", lambda _db: _activo())
    monkeypatch.setattr(normas.barra_sin_gpu, "superada_para", lambda _sha, ruta=None: barra)

    def recuperar(*_a, **_k):
        return ResultadoRecuperacion(corpus_sha=SHA, pregunta="q", modo=modo, k=10, hits=hits)

    monkeypatch.setattr(normas.service, "recuperar", recuperar)
    return normas.buscar(MagicMock(), "q", modo=modo)


class TestBuscar:
    def test_sin_corpus_no_recupera(self, monkeypatch) -> None:
        monkeypatch.setattr(normas.repository, "leer_corpus_activo", lambda _db: None)
        monkeypatch.setattr(
            normas.service,
            "recuperar",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("recuperó")),
        )
        with pytest.raises(normas.SinCorpusActivo):
            normas.buscar(MagicMock(), "q", modo=service.MODO_SIN_GPU)

    def test_sin_barra_ordena_por_clave_y_no_muestra_puntaje(self, monkeypatch) -> None:
        resultado = _buscar(
            monkeypatch, [_hit("b", 1), _hit("a", 2)], modo=service.MODO_SIN_GPU, barra=False
        )
        assert [u.citation_key for u in resultado.unidades] == ["a", "b"]
        assert resultado.sin_unidades is False
        assert resultado.orden_presentado is False
        volcado = resultado.model_dump()
        assert "rango" not in str(volcado)
        assert "valor_bm25" not in str(volcado)
        assert "score_ce" not in str(volcado)

    def test_con_barra_el_orden_es_el_de_bm25_y_el_puntaje_no_sale(self, monkeypatch) -> None:
        resultado = _buscar(
            monkeypatch, [_hit("b", 2), _hit("a", 1)], modo=service.MODO_SIN_GPU, barra=True
        )
        assert [(u.citation_key, u.rango) for u in resultado.unidades] == [("a", 1), ("b", 2)]
        assert resultado.sin_unidades is False
        assert resultado.orden_presentado is True
        volcado = resultado.model_dump()
        assert "valor_bm25" not in str(volcado)
        assert "score_rrf" not in str(volcado)

    def test_vacio_es_sin_unidades_aunque_la_barra_este_superada(self, monkeypatch) -> None:
        resultado = _buscar(monkeypatch, [], modo=service.MODO_SIN_GPU, barra=True)
        assert resultado.unidades == []
        assert resultado.sin_unidades is True

    def test_otro_modo_no_se_ordena_aunque_la_barra_diga_que_si(self, monkeypatch) -> None:
        resultado = _buscar(monkeypatch, [_hit("b", 1), _hit("a", 2)], modo="bm25_ce", barra=True)
        assert [u.citation_key for u in resultado.unidades] == ["a", "b"]
        assert "rango" not in str(resultado.model_dump())

    def test_leer_devuelve_la_unidad_o_rechaza_la_clave(self, monkeypatch) -> None:
        _parchear_lectura(monkeypatch, _fila())
        leida = normas.leer(MagicMock(), "8803#1")
        assert leida.texto == "TODA persona tiene derecho"
        assert leida.corpus_sha == SHA
        _parchear_lectura(monkeypatch, None)
        with pytest.raises(normas.UnidadNoEncontrada):
            normas.leer(MagicMock(), "8803#1")


def _barra(**cambios: object) -> barra_sin_gpu.BarraSinGpu:
    base: dict[str, object] = {
        "estado": barra_sin_gpu.ESTADO_SUPERADA,
        "modo": service.MODO_SIN_GPU,
        "corpus_sha": SHA,
        "n_respondibles": 10,
        "hit_rate_at_5": 0.72,
        "separacion_norma_secundaria": 1.0,
        "vigencia_correcta": 1.0,
        "metodologia": "medida en laboratorio",
        "motivo": "",
    }
    base.update(cambios)
    return barra_sin_gpu.BarraSinGpu(**base)  # type: ignore[arg-type]


class TestBarra:
    def test_las_figuras_en_el_piso_alcanzan(self) -> None:
        barra_sin_gpu.exigir_superada(_barra(), SHA)

    def test_cada_figura_por_debajo_rechaza(self) -> None:
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(_barra(estado="no_superada"), SHA)
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(_barra(modo="bm25_ce"), SHA)
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(_barra(corpus_sha=OTRO), SHA)
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(_barra(hit_rate_at_5=0.719), SHA)
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(_barra(separacion_norma_secundaria=0.99), SHA)
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(_barra(vigencia_correcta=None), SHA)

    def test_superada_para_falla_cerrado(self, monkeypatch) -> None:
        monkeypatch.setattr(barra_sin_gpu, "cargar_barra", lambda ruta=None: _barra())
        assert barra_sin_gpu.superada_para(SHA) is True
        monkeypatch.setattr(
            barra_sin_gpu, "cargar_barra", lambda ruta=None: _barra(hit_rate_at_5=0.5)
        )
        assert barra_sin_gpu.superada_para(SHA) is False

    def test_derivar_rechaza_lo_que_no_puede_decidir_la_barra(self) -> None:
        proc = SimpleNamespace(sintetico=False, corpus_sha=SHA)
        gold = SimpleNamespace(
            corpus_sha=SHA,
            precondicion=lambda: SimpleNamespace(evaluable=True, motivos=[]),
        )
        metricas = SimpleNamespace(
            hit_rate_at_5=0.72,
            separacion_norma_secundaria=1.0,
            vigencia_correctness=1.0,
            n_respondibles=10,
        )
        corrida = SimpleNamespace(
            modo=service.MODO_SIN_GPU, perdidas_de_migracion=[], metricas=metricas
        )

        assert barra_sin_gpu.derivar_desde(corrida, None, gold).estado == "no_medido"
        assert (
            barra_sin_gpu.derivar_desde(
                corrida, SimpleNamespace(sintetico=True, corpus_sha=SHA), gold
            ).estado
            == "no_medido"
        )
        assert (
            barra_sin_gpu.derivar_desde(corrida, proc, gold, permitir_sintetico=True).estado
            == "no_medido"
        )
        ajena = SimpleNamespace(modo="bm25_ce", perdidas_de_migracion=[], metricas=metricas)
        assert barra_sin_gpu.derivar_desde(ajena, proc, gold).estado == "no_medido"
        otro_gold = SimpleNamespace(
            corpus_sha=OTRO,
            precondicion=lambda: SimpleNamespace(evaluable=True, motivos=[]),
        )
        assert barra_sin_gpu.derivar_desde(corrida, proc, otro_gold).estado == "no_medido"

        decidida = barra_sin_gpu.derivar_desde(corrida, proc, gold)
        assert decidida.estado == "superada"
        assert decidida.corpus_sha == SHA

        corta = SimpleNamespace(
            modo=service.MODO_SIN_GPU,
            perdidas_de_migracion=[],
            metricas=SimpleNamespace(
                hit_rate_at_5=0.719,
                separacion_norma_secundaria=1.0,
                vigencia_correctness=1.0,
                n_respondibles=10,
            ),
        )
        assert barra_sin_gpu.derivar_desde(corta, proc, gold).estado == "no_superada"


class TestBarraSinOrden:
    """`exigir_no_superada_honesta`: one assertion per refusal branch, plus the boundaries."""

    def test_la_falla_honesta_pasa(self) -> None:
        honesta = _barra(estado="no_superada", hit_rate_at_5=0.6470588235294118)
        assert barra_sin_gpu.exigir_no_superada_honesta(honesta, SHA) is None

    def test_cada_rechazo_nombra_su_causa(self) -> None:
        rechazada = barra_sin_gpu.BarraSinOrdenRechazada
        with pytest.raises(rechazada, match="--exigir-barra"):
            barra_sin_gpu.exigir_no_superada_honesta(_barra(), SHA)
        with pytest.raises(rechazada, match="no failed measurement"):
            barra_sin_gpu.exigir_no_superada_honesta(_barra(estado="no_medido"), SHA)
        with pytest.raises(rechazada, match="never for another arm"):
            barra_sin_gpu.exigir_no_superada_honesta(
                _barra(estado="no_superada", hit_rate_at_5=0.5, modo="bm25_ce"), SHA
            )
        with pytest.raises(rechazada, match="snapshot being ingested"):
            barra_sin_gpu.exigir_no_superada_honesta(
                _barra(estado="no_superada", hit_rate_at_5=0.5), OTRO
            )
        with pytest.raises(rechazada, match="missing figure"):
            barra_sin_gpu.exigir_no_superada_honesta(
                _barra(estado="no_superada", hit_rate_at_5=None), SHA
            )
        with pytest.raises(rechazada, match="inconsistent"):
            barra_sin_gpu.exigir_no_superada_honesta(_barra(estado="no_superada"), SHA)

    @pytest.mark.parametrize(
        "campo",
        ["hit_rate_at_5", "separacion_norma_secundaria", "vigencia_correcta"],
    )
    def test_una_cifra_ausente_rechaza_aunque_las_otras_fallen(self, campo: str) -> None:
        # Every figure fails (0.1) except the one under test, which is absent.
        cifras = {
            "hit_rate_at_5": 0.1,
            "separacion_norma_secundaria": 0.1,
            "vigencia_correcta": 0.1,
            campo: None,
        }
        artefacto = _barra(estado="no_superada", **cifras)
        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="missing figure"):
            barra_sin_gpu.exigir_no_superada_honesta(artefacto, SHA)

    @pytest.mark.parametrize(
        ("campo", "debajo"),
        [
            ("hit_rate_at_5", 0.719),
            ("separacion_norma_secundaria", 0.999),
            ("vigencia_correcta", 0.999),
        ],
    )
    def test_justo_debajo_de_su_constante_cuenta_como_falla(
        self, campo: str, debajo: float
    ) -> None:
        artefacto = _barra(estado="no_superada", **{campo: debajo})
        assert barra_sin_gpu.exigir_no_superada_honesta(artefacto, SHA) is None

    def test_exactamente_en_las_constantes_no_cuenta_como_falla(self) -> None:
        # 0.72, 1.0 and 1.0 sit exactly on the constants: none of them is failing.
        en_la_barra = _barra(
            estado="no_superada",
            hit_rate_at_5=0.72,
            separacion_norma_secundaria=1.0,
            vigencia_correcta=1.0,
        )
        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="inconsistent"):
            barra_sin_gpu.exigir_no_superada_honesta(en_la_barra, SHA)

    def test_el_camino_sin_orden_no_desbloquea_el_orden(self, monkeypatch) -> None:
        honesta = _barra(estado="no_superada", hit_rate_at_5=0.6470588235294118)
        monkeypatch.setattr(barra_sin_gpu, "cargar_barra", lambda ruta=None: honesta)
        assert barra_sin_gpu.superada_para(SHA) is False


def _catalogo() -> editor.Catalogo:
    slot = editor.SlotLegal("ley", "8803#1", "TODA persona", "VIGENTE", SHA, "art. 1")
    pedido = editor.Pedido("1", "titulo", {}, "texto {{legal:ley}}", "")
    return editor.Catalogo(SHA, {"ley-8803": "VIGENTE"}, {"ley": slot}, {"1": pedido})


class TestEditor:
    def test_el_lint_deja_pasar_un_token_y_frena_una_cita_suelta(self) -> None:
        assert editor.lint_texto_libre("pedido {{id:expediente}}") == []
        assert editor.lint_texto_libre("ver art. 6") == ["art. 6"]
        assert "Ley 8803" in editor.lint_texto_libre("conforme a la Ley 8803")[0]

    def test_pedido_8_y_obra_no_llegan_al_nucleo(self, monkeypatch) -> None:
        monkeypatch.setattr(
            editor.normas,
            "chequear",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("chequeó")),
        )
        with pytest.raises(editor.PedidoNoSoportado):
            editor.exportar(MagicMock(), "8", _catalogo())
        with pytest.raises(editor.PedidoNoSoportado):
            editor.exportar(MagicMock(), "nota-de-obra", _catalogo())

    def test_una_cita_fallida_no_compone_el_documento(self, monkeypatch) -> None:
        compuesto: list[str] = []
        monkeypatch.setattr(
            editor,
            "componer",
            lambda *_a, **_k: compuesto.append("si") or "BORRADOR",
        )
        monkeypatch.setattr(
            editor.normas,
            "chequear",
            lambda *_a, **_k: SimpleNamespace(
                pasa=False, clasificacion="publico", condicion_fallida="span"
            ),
        )
        with pytest.raises(editor.ExportacionRechazada) as error:
            editor.exportar(MagicMock(), "1", _catalogo())
        assert error.value.slot == "ley"
        assert error.value.causa == "span"
        assert compuesto == []

    def test_una_unidad_privada_tampoco_sale(self, monkeypatch) -> None:
        monkeypatch.setattr(
            editor.normas,
            "chequear",
            lambda *_a, **_k: SimpleNamespace(
                pasa=True, clasificacion="privado", condicion_fallida=None
            ),
        )
        with pytest.raises(editor.ExportacionRechazada) as error:
            editor.exportar(MagicMock(), "1", _catalogo())
        assert error.value.causa == "privado"

    def test_exportar_devuelve_el_texto_cuando_el_chequeo_pasa(self, monkeypatch) -> None:
        monkeypatch.setattr(editor, "componer", lambda *_a, **_k: "BORRADOR")
        monkeypatch.setattr(
            editor.normas,
            "chequear",
            lambda *_a, **_k: SimpleNamespace(
                pasa=True, clasificacion="publico", condicion_fallida=None
            ),
        )
        assert editor.exportar(MagicMock(), "1", _catalogo()) == "BORRADOR"

    def test_el_catalogo_real_compone_los_ocho_borradores(self) -> None:
        catalogo = editor.cargar()
        assert tuple(catalogo.pedidos) == editor.PEDIDOS_SOPORTADOS
        assert "8" not in catalogo.pedidos
        for pedido_id in editor.PEDIDOS_SOPORTADOS:
            assert editor.componer(pedido_id, catalogo).strip()
