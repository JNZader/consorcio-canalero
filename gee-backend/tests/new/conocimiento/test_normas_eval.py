"""Unit 2 — the measured no-GPU arm: harness wiring, bar derivation, report, CLIs.

Nothing here runs the real 57-item gold set or touches a serving database. Every
gold item is a short synthetic question over a seeded mini-snapshot, and no
private gold-question text appears in this file.
"""

from __future__ import annotations

import datetime as dt
import json
from types import SimpleNamespace

import pytest
import yaml

from app.domains.conocimiento.eval import barra_sin_gpu, harness, report
from app.domains.conocimiento.recuperacion.bm25 import limpiar_cache_indices
from app.domains.conocimiento.recuperacion.reranker import RerankerDeterministico
from app.domains.conocimiento.service import ProcedenciaEmbeddings
from scripts import rag_eval, rag_ingest

from .test_normas_kernel import OTRO_SHA, SHA, seed
from .test_rag_eval_cli import MOMENTO, _NullEngine, cli, marcar  # noqa: F401 (cli is a fixture)
from .test_rag_eval_harness import SHA as SHA_HARNESS
from .test_rag_eval_harness import gold_item, gold_set

ARM = "bm25_sin_ce"
GENERADO = dt.datetime(2026, 10, 22, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def indice_limpio():
    limpiar_cache_indices()
    yield
    limpiar_cache_indices()


def _gold(*items):
    return gold_set(*items, corpus_sha=SHA)


def _gold_evaluable():
    """Twenty owner-validated answerable items: the harness precondition."""
    return _gold(
        *[gold_item(f"g-{i:02d}", "canal de riego", "answerable", ("9750#1",)) for i in range(20)]
    )


def _procedencia(*, sintetico: bool = False, sha: str = SHA):
    return ProcedenciaEmbeddings(
        corpus_sha=sha,
        modelo="BAAI/bge-m3",
        revision_hf=None if sintetico else "a" * 40,
        sintetico=sintetico,
        artifact_sha256="b" * 64,
        loaded_at=GENERADO,
    )


def _corrida(
    *,
    modo: str = ARM,
    hit: float | None = 0.75,
    separacion: float | None = 1.0,
    vigencia: float | None = 1.0,
    perdidas: tuple = (),
):
    """A scored run reduced to what `derivar_desde` reads."""
    return SimpleNamespace(
        modo=modo,
        metricas=SimpleNamespace(
            n_respondibles=34,
            hit_rate_at_5=hit,
            separacion_norma_secundaria=separacion,
            vigencia_correctness=vigencia,
        ),
        perdidas_de_migracion=perdidas,
    )


# ---------------------------------------------------------------------------
# 2.2 — the harness knows the arm
# ---------------------------------------------------------------------------


class TestElArnesConoceElBrazo:
    def test_sus_piernas_son_bm25(self):
        assert harness.LEGS_POR_MODO[ARM] == ("bm25",)

    def test_no_tiene_senal_de_abstencion_ratificada(self):
        assert ARM in harness.MODOS_SIN_SENAL_RATIFICADA
        assert "bm25_ce" in harness.MODOS_SIN_SENAL_RATIFICADA

    def test_corre_sin_reranker_ni_embedder(self, db):
        seed(db)
        corrida = harness.correr_modo(db, SHA, _gold_evaluable(), modo=ARM)
        assert corrida.modo == ARM
        assert corrida.ranker_modelo is None
        assert corrida.ranker_sintetico is None
        assert corrida.cobertura.legs_corridas == ("bm25",)
        assert corrida.senales == ()

    def test_un_reranker_del_llamador_no_llega_al_brazo(self, db):
        """`evaluar` threads ONE reranker to every mode; the no-GPU arm must drop it."""
        seed(db)
        resultado = harness.evaluar(
            db,
            SHA,
            _gold_evaluable(),
            modos=("bm25_ce", ARM),
            reranker=RerankerDeterministico(),
        )
        assert resultado.por_modo["bm25_ce"].ranker_sintetico is True
        assert resultado.por_modo[ARM].ranker_modelo is None
        assert resultado.por_modo[ARM].modo == ARM

    def test_el_brazo_nunca_se_etiqueta_bm25_ce(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        assert set(resultado.por_modo) == {ARM}
        assert all(corrida.modo != "bm25_ce" for corrida in resultado.por_modo.values())

    def test_su_fila_de_abstencion_es_no_evaluable(self, db):
        seed(db)
        corrida = harness.correr_modo(db, SHA, _gold_evaluable(), modo=ARM)
        decision = harness.decidir_go_no_go(corrida, _gold_evaluable())
        assert decision.veredicto == "NO EVALUABLE"
        assert "abstention recall" in decision.barras_no_evaluables

    def test_un_modo_sin_gpu_no_cambia_la_barra_de_hit_rate(self):
        assert harness.BARRA_HIT_RATE == 0.72
        assert harness.BARRA_SEPARACION == 1.0
        assert harness.BARRA_VIGENCIA == 1.0


class TestPerdidasDeMigracion:
    """The gold keys are re-validated BEFORE hit@5, and migration misses count apart."""

    def _gold(self):
        return _gold(
            gold_item("B-OK", "administra el canal", "answerable", ("9750#1",)),
            gold_item("B-M", "canal de riego", "answerable", ("9750#99",)),
            gold_item("B-R", "zzzz", "answerable", ("9750#2",)),
        )

    def test_una_clave_ausente_se_cuenta_aparte_de_un_fallo_de_recuperacion(self, db):
        seed(db)
        corrida = harness.correr_modo(db, SHA, self._gold(), modo=ARM)
        assert corrida.perdidas_de_migracion == (("B-M", ("9750#99",)),)
        assert corrida.n_perdidas_de_migracion == 1
        assert corrida.fallas_de_recuperacion == ("B-R",)

    def test_un_item_con_todas_sus_claves_no_es_perdida(self, db):
        seed(db)
        corrida = harness.correr_modo(db, SHA, self._gold(), modo=ARM)
        assert "B-OK" not in {id for id, _ in corrida.perdidas_de_migracion}
        assert "B-OK" not in corrida.fallas_de_recuperacion

    def test_toda_corrida_informa_las_perdidas_no_solo_el_brazo_sin_gpu(self, db):
        seed(db)
        corrida = harness.correr_modo(
            db, SHA, self._gold(), modo="bm25_ce", reranker=RerankerDeterministico()
        )
        assert corrida.perdidas_de_migracion == (("B-M", ("9750#99",)),)

    def test_una_clave_ausente_entre_varias_tambien_cuenta(self, db):
        seed(db)
        gold = _gold(gold_item("B-P", "canal de riego", "answerable", ("9750#1", "9750#99")))
        corrida = harness.correr_modo(db, SHA, gold, modo=ARM)
        assert corrida.perdidas_de_migracion == (("B-P", ("9750#99",)),)


# ---------------------------------------------------------------------------
# 2.2 — derivar_desde
# ---------------------------------------------------------------------------


class TestDerivarDesde:
    def test_una_corrida_limpia_deriva_superada(self):
        barra = barra_sin_gpu.derivar_desde(_corrida(), _procedencia(), _gold_evaluable())
        assert barra.estado == "superada"
        assert barra.modo == ARM
        assert barra.corpus_sha == SHA
        assert barra.hit_rate_at_5 == 0.75
        assert barra.separacion_norma_secundaria == 1.0
        assert barra.vigencia_correcta == 1.0
        assert barra.n_respondibles == 34
        assert barra.metodologia
        barra_sin_gpu.exigir_superada(barra, SHA)

    def test_por_debajo_de_la_barra_deriva_no_superada_con_las_cifras(self):
        barra = barra_sin_gpu.derivar_desde(_corrida(hit=0.71), _procedencia(), _gold_evaluable())
        assert barra.estado == "no_superada"
        assert barra.hit_rate_at_5 == 0.71
        with pytest.raises(barra_sin_gpu.BarraNoSuperada):
            barra_sin_gpu.exigir_superada(barra, SHA)

    @pytest.mark.parametrize(
        "cambios",
        [{"separacion": 0.5}, {"vigencia": 0.5}],
    )
    def test_una_separacion_por_debajo_de_uno_no_supera(self, cambios):
        barra = barra_sin_gpu.derivar_desde(_corrida(**cambios), _procedencia(), _gold_evaluable())
        assert barra.estado == "no_superada"

    def test_rechaza_un_snapshot_sintetico(self):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(), _procedencia(sintetico=True), _gold_evaluable()
        )
        assert barra.estado == "no_medido"
        assert "sint" in barra.motivo.lower()
        assert barra.corpus_sha is None and barra.hit_rate_at_5 is None

    def test_rechaza_una_corrida_allow_synthetic(self):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(), _procedencia(), _gold_evaluable(), permitir_sintetico=True
        )
        assert barra.estado == "no_medido"
        assert "sint" in barra.motivo.lower()

    def test_un_gold_fijado_a_otro_snapshot_no_decide_la_barra(self):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(), _procedencia(sha=OTRO_SHA), _gold_evaluable()
        )
        assert barra.estado == "no_medido"
        assert "gold" in barra.motivo.lower()

    def test_sin_procedencia_no_hay_medicion(self):
        barra = barra_sin_gpu.derivar_desde(_corrida(), None, _gold_evaluable())
        assert barra.estado == "no_medido"

    def test_el_brazo_cuda_no_puede_dar_la_barra_del_brazo_sin_gpu(self):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(modo="bm25_ce"), _procedencia(), _gold_evaluable()
        )
        assert barra.estado == "no_medido"
        assert barra.modo == ARM
        assert "bm25_ce" in barra.motivo

    def test_una_perdida_de_migracion_deja_la_barra_sin_decidir(self):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(perdidas=(("B-M", ("9750#99",)),)), _procedencia(), _gold_evaluable()
        )
        assert barra.estado == "no_medido"
        assert "migra" in barra.motivo.lower()

    def test_un_gold_no_evaluable_deja_la_barra_sin_decidir(self):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(), _procedencia(), _gold(gold_item("g-1", "canal", "answerable", ("9750#1",)))
        )
        assert barra.estado == "no_medido"

    @pytest.mark.parametrize("campo", ["hit", "separacion", "vigencia"])
    def test_una_cifra_sin_denominador_no_se_decide(self, campo):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(**{campo: None}), _procedencia(), _gold_evaluable()
        )
        assert barra.estado == "no_medido"

    def test_el_volcado_se_puede_volver_a_cargar(self, tmp_path):
        barra = barra_sin_gpu.derivar_desde(_corrida(), _procedencia(), _gold_evaluable())
        ruta = tmp_path / "barra.yaml"
        ruta.write_text(yaml.safe_dump(barra_sin_gpu.volcar(barra)), encoding="utf-8")
        assert barra_sin_gpu.cargar_barra(ruta) == barra
        assert barra_sin_gpu.superada_para(SHA, ruta) is True
        assert barra_sin_gpu.superada_para(OTRO_SHA, ruta) is False


# ---------------------------------------------------------------------------
# 2.2 — the report
# ---------------------------------------------------------------------------


class TestElReporte:
    def test_el_brazo_gateado_no_cambia(self):
        assert report.MODO_GATEADO == "bm25_ce"

    def test_sin_el_brazo_el_bloque_lo_dice(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=("fts",))
        bloque = "\n".join(report.bloque_barra_sin_gpu(resultado, _procedencia()))
        assert "no se corrió" in bloque
        assert "not-evaluable" in bloque

    def test_el_bloque_nombra_el_brazo_en_cada_cifra_y_no_usa_31_34(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        bloque = report.bloque_barra_sin_gpu(resultado, _procedencia())
        filas = [linea for linea in bloque if linea.startswith("| `bm25_sin_ce`")]
        assert len(filas) == 3, bloque
        texto = "\n".join(bloque)
        assert "31/34" not in texto
        assert "0.72" in texto

    def test_con_los_dos_brazos_las_cifras_son_las_del_brazo_sin_gpu(self, db):
        seed(db)
        resultado = harness.evaluar(
            db,
            SHA,
            _gold_evaluable(),
            modos=("bm25_ce", ARM),
            reranker=RerankerDeterministico(),
        )
        bloque = report.bloque_barra_sin_gpu(resultado, _procedencia())
        propias = resultado.por_modo[ARM].metricas
        fila_hit = next(linea for linea in bloque if "hit@5" in linea and linea.startswith("| `"))
        assert fila_hit.startswith("| `bm25_sin_ce`")
        assert f"| {propias.hit_rate_at_5:.3f} |" in fila_hit

    def test_una_corrida_chica_deja_la_barra_no_medida_y_dice_por_que(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        bloque = report.bloque_barra_sin_gpu(resultado, _procedencia(sintetico=True))
        texto = "\n".join(bloque)
        assert "no_medido" in texto
        assert "sint" in texto.lower()

    def test_el_bloque_siembra_el_yaml_cuando_la_barra_se_decide(self, db, monkeypatch):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        decidida = barra_sin_gpu.derivar_desde(_corrida(), _procedencia(), _gold_evaluable())
        monkeypatch.setattr(barra_sin_gpu, "derivar_desde", lambda *a, **k: decidida)
        bloque = "\n".join(report.bloque_barra_sin_gpu(resultado, _procedencia()))
        assert "estado: superada" in bloque
        assert f"corpus_sha: {SHA}" in bloque
        assert "barra_sin_gpu.yaml" in bloque

    def test_el_bloque_no_siembra_nada_si_la_barra_no_se_decide(self, db, monkeypatch):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        sin_medir = barra_sin_gpu.derivar_desde(_corrida(), None, _gold_evaluable())
        monkeypatch.setattr(barra_sin_gpu, "derivar_desde", lambda *a, **k: sin_medir)
        bloque = "\n".join(report.bloque_barra_sin_gpu(resultado, _procedencia()))
        assert "estado: superada" not in bloque
        assert "estado: no_superada" not in bloque
        assert "no_medido" in bloque

    def test_el_json_lleva_la_barra_siempre(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=("fts",))
        datos = report._a_json(
            resultado,
            _procedencia(),
            generado_en=GENERADO,
            device_consulta="cpu",
            sintetico=False,
        )
        assert datos["barra_sin_gpu"]["evaluado"] is False
        assert datos["barra_sin_gpu"]["modo"] == ARM

    def test_el_json_del_brazo_lleva_estado_y_cifras(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        datos = report._a_json(
            resultado,
            _procedencia(),
            generado_en=GENERADO,
            device_consulta="cpu",
            sintetico=False,
        )
        barra = datos["barra_sin_gpu"]
        assert barra["evaluado"] is True
        assert barra["modo"] == ARM
        assert barra["estado"] in ("superada", "no_superada", "no_medido")
        assert set(barra["medido"]) == {
            "hit_rate_at_5",
            "separacion_norma_secundaria",
            "vigencia_correcta",
        }
        assert datos["modos"][ARM]["ranker"] == {"modelo": None, "sintetico": None}

    def test_el_markdown_completo_incluye_el_bloque(self, db):
        seed(db)
        resultado = harness.evaluar(db, SHA, _gold_evaluable(), modos=(ARM,))
        md = report.renderizar_markdown(
            resultado, _procedencia(), generado_en=GENERADO, device_consulta="cpu"
        )
        assert "## Barra del brazo `bm25_sin_ce`" in md
        assert f"## Modo `{ARM}`" in md


# ---------------------------------------------------------------------------
# 2.3 — rag_eval.py and rag_ingest.py
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_eval(request, monkeypatch):
    """`rag_eval.main` over the harness mini-snapshot, with every builder armed to refuse."""
    base = request.getfixturevalue("cli")

    def prohibido(nombre, **_):
        raise AssertionError(f"the no-GPU arm built {nombre!r}; it needs neither")

    monkeypatch.setattr(rag_eval, "_reranker", prohibido)
    monkeypatch.setattr(rag_eval, "_embedder", lambda nombre, **k: prohibido(nombre))
    return base


class TestRagEval:
    def test_el_brazo_es_un_modo_aceptado(self):
        args = rag_eval.build_parser().parse_args(["--corpus-sha", SHA, "--modo", ARM])
        assert args.modo == [ARM]

    def test_el_default_sigue_siendo_la_ablacion_de_tres(self):
        args = rag_eval.build_parser().parse_args(["--corpus-sha", SHA])
        assert args.modo is None

    def test_corre_sin_construir_reranker_ni_embedder_y_escribe_el_bloque(
        self, cli_eval, tmp_path, capsys
    ):
        marcar(cli_eval, sintetico=False)
        codigo = rag_eval.main(
            [
                "--corpus-sha",
                SHA_HARNESS,
                "--database-url",
                "postgresql://unused/unused",
                "--modo",
                ARM,
                "--destino",
                str(tmp_path),
                "--generado-en",
                MOMENTO,
            ]
        )
        assert codigo == 0
        md = next(tmp_path.glob("retrieval-eval-*.md")).read_text(encoding="utf-8")
        assert "## Barra del brazo `bm25_sin_ce`" in md
        datos = json.loads(next(tmp_path.glob("*.results.json")).read_text(encoding="utf-8"))
        assert datos["barra_sin_gpu"]["modo"] == ARM
        assert datos["barra_sin_gpu"]["estado"] == "no_medido"
        assert ARM in capsys.readouterr().out


class TestExigirBarra:
    """`rag_ingest --exigir-barra` refuses unless the artifact is `superada` for that SHA."""

    ARGS = ["--corpus-path", "/nonexistent", "--database-url", "postgresql://unused/unused"]

    def _espia(self, monkeypatch):
        llamadas: list[str] = []

        def ingest_falso(*a, **k):
            llamadas.append("ingest")
            raise AssertionError("ingest ran although the bar gate refused")

        monkeypatch.setattr(rag_ingest, "ingest", ingest_falso)
        monkeypatch.setattr(rag_ingest, "create_engine", lambda url: _NullEngine())
        return llamadas

    def test_el_flag_existe_y_no_es_el_default(self):
        parser = rag_ingest.build_parser()
        assert parser.parse_args([*self.ARGS, "--corpus-sha", SHA]).exigir_barra is False
        assert (
            parser.parse_args([*self.ARGS, "--corpus-sha", SHA, "--exigir-barra"]).exigir_barra
            is True
        )

    def test_el_artefacto_enviado_no_superada_rechaza_antes_de_ingerir(self, monkeypatch, capsys):
        llamadas = self._espia(monkeypatch)
        codigo = rag_ingest.main([*self.ARGS, "--corpus-sha", SHA, "--exigir-barra"])
        assert codigo == 1
        assert llamadas == []
        assert "nothing was written" in capsys.readouterr().err

    def test_rechaza_un_sha_que_no_es_el_de_la_barra(self, monkeypatch, tmp_path, capsys):
        llamadas = self._espia(monkeypatch)
        ruta = tmp_path / "barra.yaml"
        ruta.write_text(
            yaml.safe_dump(
                barra_sin_gpu.volcar(
                    barra_sin_gpu.derivar_desde(_corrida(), _procedencia(), _gold_evaluable())
                )
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(barra_sin_gpu, "RUTA_BARRA", ruta)
        codigo = rag_ingest.main([*self.ARGS, "--corpus-sha", OTRO_SHA, "--exigir-barra"])
        assert codigo == 1
        assert llamadas == []
        assert "corpus_sha" in capsys.readouterr().err

    def test_con_la_barra_superada_para_ese_sha_ingesta(self, monkeypatch, tmp_path):
        ruta = tmp_path / "barra.yaml"
        ruta.write_text(
            yaml.safe_dump(
                barra_sin_gpu.volcar(
                    barra_sin_gpu.derivar_desde(_corrida(), _procedencia(), _gold_evaluable())
                )
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(barra_sin_gpu, "RUTA_BARRA", ruta)
        monkeypatch.setattr(rag_ingest, "create_engine", lambda url: _NullEngine())
        llamadas: list[str] = []

        class _Sesion:
            def __init__(self, *_):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def begin(self):
                return self

            def rollback(self):
                pass

        def ingest_falso(*a, **k):
            llamadas.append("ingest")
            return SimpleNamespace(
                corpus_sha=SHA,
                gates=SimpleNamespace(
                    documentos=0, articulos_total=0, no_articulos_total=0, over_ceiling=[]
                ),
                unidades_escritas=0,
                unidades_eliminadas=0,
                committed=True,
                procedencia_olvidada=False,
                verificacion_fallida=False,
            )

        monkeypatch.setattr(rag_ingest, "ingest", ingest_falso)
        monkeypatch.setattr(rag_ingest, "Session", _Sesion)
        codigo = rag_ingest.main([*self.ARGS, "--corpus-sha", SHA, "--exigir-barra"])
        assert codigo == 0
        assert llamadas == ["ingest"]

    def test_tambien_rige_con_dry_run(self, monkeypatch, capsys):
        llamadas = self._espia(monkeypatch)
        codigo = rag_ingest.main([*self.ARGS, "--corpus-sha", SHA, "--exigir-barra", "--dry-run"])
        assert codigo == 1
        assert llamadas == []
        assert "nothing was written" in capsys.readouterr().err

    def test_sin_el_flag_el_comportamiento_no_cambia(self, monkeypatch, capsys):
        """The gate is opt-in: omitting it must not read the artifact at all."""
        monkeypatch.setattr(
            barra_sin_gpu,
            "cargar_barra",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("read the bar without the flag")),
        )
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setattr(
            rag_ingest,
            "ingest",
            lambda *a, **k: (_ for _ in ()).throw(rag_ingest.repository.IngestionAbort("stop")),
        )
        codigo = rag_ingest.main(
            ["--corpus-path", "/nonexistent", "--corpus-sha", SHA, "--dry-run"]
        )
        assert codigo == 1
        assert "INGESTION ABORTED" in capsys.readouterr().err

    def test_el_default_es_laboratorio(self):
        parser = rag_ingest.build_parser()
        assert parser.parse_args([*self.ARGS, "--corpus-sha", SHA]).entorno == "laboratorio"

    def test_produccion_sin_exigir_barra_no_abre_nada(self, monkeypatch, capsys):
        """Production is not a database URL. Forgetting the bar must refuse before ingest."""
        llamadas = self._espia(monkeypatch)
        codigo = rag_ingest.main([*self.ARGS, "--corpus-sha", SHA, "--entorno", "produccion"])
        assert codigo == 1
        assert llamadas == []
        error = capsys.readouterr().err
        assert "produccion" in error
        assert "exigir-barra" in error

    def test_laboratorio_sigue_pudiendo_ingerir_sin_la_barra(self, monkeypatch):
        llamadas: list[str] = []

        class _Sesion:
            def __init__(self, *_):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def begin(self):
                return self

            def rollback(self):
                pass

        def ingest_falso(*_a, **_k):
            llamadas.append("ingest")
            return SimpleNamespace(
                corpus_sha=SHA,
                gates=SimpleNamespace(
                    documentos=0, articulos_total=0, no_articulos_total=0, over_ceiling=[]
                ),
                unidades_escritas=0,
                unidades_eliminadas=0,
                committed=True,
                procedencia_olvidada=False,
                verificacion_fallida=False,
            )

        monkeypatch.setattr(rag_ingest, "create_engine", lambda url: _NullEngine())
        monkeypatch.setattr(rag_ingest, "ingest", ingest_falso)
        monkeypatch.setattr(rag_ingest, "Session", _Sesion)
        codigo = rag_ingest.main([*self.ARGS, "--corpus-sha", SHA, "--entorno", "laboratorio"])
        assert codigo == 0
        assert llamadas == ["ingest"]
