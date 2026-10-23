"""Unit 1 — the mute kernel: the no-GPU arm, the bar loader, buscar/leer/chequear.

Every test seeds a tiny `rag_*` snapshot rather than touching the real corpus, and
no question text from the private gold set appears anywhere in this file.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.conocimiento import service
from app.domains.conocimiento.recuperacion.bm25 import limpiar_cache_indices
from app.domains.conocimiento.recuperacion.reranker import RerankerDeterministico

from .conftest import PINNED_CORPUS_SHA

SHA = "a" * 40
OTRO_SHA = "b" * 40


@pytest.fixture(autouse=True)
def indice_limpio():
    limpiar_cache_indices()
    yield
    limpiar_cache_indices()


def seed(db, *, sha: str = SHA, activo: bool = True) -> None:
    """Three documents: a live norma, a secondary report and a private memo."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 5, :activo)"
        ),
        {"sha": sha, "activo": activo},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, relevancia_consorcio, clasificacion) VALUES "
            "(:sha, :doc, :tipo, :sec, :jur, :vig, :rel, :clasif)"
        ),
        [
            {
                "sha": sha,
                "doc": "ley-9750",
                "tipo": "ley-provincial",
                "sec": False,
                "jur": "provincial",
                "vig": "vigente",
                "rel": "alta",
                "clasif": "publico",
            },
            {
                "sha": sha,
                "doc": "informe-x",
                "tipo": "informe-consultoria",
                "sec": True,
                "jur": "provincial",
                "vig": "vigente",
                "rel": "media",
                "clasif": "publico",
            },
            {
                "sha": sha,
                "doc": "ley-vieja",
                "tipo": "ley-provincial",
                "sec": False,
                "jur": "provincial",
                "vig": "derogada",
                "rel": "baja",
                "clasif": "publico",
            },
            {
                "sha": sha,
                "doc": "memo-privado",
                "tipo": "registro-administrativo",
                "sec": False,
                "jur": "provincial",
                "vig": "vigente",
                "rel": "alta",
                "clasif": "privado",
            },
        ],
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, :key, :doc, 'articulo', :texto, :texto, 'f.md', 0)"
        ),
        [
            {
                "sha": sha,
                "key": "9750#1",
                "doc": "ley-9750",
                "texto": "El consorcio administra el canal de riego.",
            },
            {
                "sha": sha,
                "key": "9750#2",
                "doc": "ley-9750",
                "texto": "La asamblea aprueba el presupuesto anual del canal.",
            },
            {
                "sha": sha,
                "key": "INF#1",
                "doc": "informe-x",
                "texto": "El informe describe el canal de riego y sus compuertas.",
            },
            {
                "sha": sha,
                "key": "VIEJA#1",
                "doc": "ley-vieja",
                "texto": "El canal de riego se rige por esta norma derogada.",
            },
            {
                "sha": sha,
                "key": "MEMO#1",
                "doc": "memo-privado",
                "texto": "Nota interna sobre el canal de riego.",
            },
        ],
    )
    db.flush()


class TestModoSinGpu:
    """1.1 — `bm25_sin_ce` runs with no reranker, and `bm25_ce` still refuses."""

    def test_el_id_es_exactamente_bm25_sin_ce(self):
        assert service.MODO_SIN_GPU == "bm25_sin_ce"

    def test_esta_en_modos_y_no_en_modos_rrf(self):
        assert service.MODO_SIN_GPU in service.MODOS
        assert service.MODO_SIN_GPU not in service.MODOS_RRF

    def test_no_reutiliza_ningun_id_existente(self):
        assert service.MODOS.count(service.MODO_SIN_GPU) == 1
        assert service.MODO_SIN_GPU not in ("fts", "vector", "hybrid", "bm25_ce", "bm25")

    def test_corre_sin_reranker(self, db):
        seed(db)
        resultado = service.recuperar(db, SHA, "canal de riego", modo=service.MODO_SIN_GPU, k=5)
        assert resultado.modo == "bm25_sin_ce"
        assert resultado.hits, "the arm must return units for a matching question"
        assert resultado.reranker_modelo is None
        assert resultado.reranker_sintetico is None

    def test_no_lleva_puntaje_de_cross_encoder(self, db):
        seed(db)
        resultado = service.recuperar(db, SHA, "canal de riego", modo=service.MODO_SIN_GPU)
        assert all(hit.score_ce is None for hit in resultado.hits)
        assert all(hit.rango_bm25 is not None for hit in resultado.hits)

    def test_un_reranker_lanza_value_error(self, db):
        seed(db)
        with pytest.raises(ValueError, match="reranker"):
            service.recuperar(
                db,
                SHA,
                "canal",
                modo=service.MODO_SIN_GPU,
                reranker=RerankerDeterministico(),
            )

    def test_un_qvec_lanza_value_error(self, db):
        seed(db)
        with pytest.raises(ValueError, match="qvec"):
            service.recuperar(db, SHA, "canal", modo=service.MODO_SIN_GPU, qvec=[0.1, 0.2])

    def test_bm25_ce_sin_reranker_sigue_rechazando(self, db):
        seed(db)
        with pytest.raises(service.RerankerRequerido):
            service.recuperar(db, SHA, "canal", modo="bm25_ce")

    def test_bm25_ce_con_reranker_sigue_igual(self, db):
        seed(db)
        resultado = service.recuperar(
            db, SHA, "canal de riego", modo="bm25_ce", reranker=RerankerDeterministico()
        )
        assert resultado.modo == "bm25_ce"
        assert all(hit.score_ce is not None for hit in resultado.hits)

    def test_mismo_pool_bm25_que_bm25_ce(self, db):
        """Same candidate generation: the two arms differ ONLY in the ranker."""
        seed(db)
        sin_ce = service.recuperar(db, SHA, "canal de riego", modo=service.MODO_SIN_GPU, k=10)
        con_ce = service.recuperar(
            db, SHA, "canal de riego", modo="bm25_ce", k=10, reranker=RerankerDeterministico()
        )
        assert {h.citation_key for h in sin_ce.hits} == {h.citation_key for h in con_ce.hits}
        assert sin_ce.n_bm25 == con_ce.n_bm25


# ---------------------------------------------------------------------------
# 1.3 — the bar artifact loader
# ---------------------------------------------------------------------------


def _barra(**cambios):
    """A `superada` artifact for `SHA`, with every figure exactly on the bar."""
    from app.domains.conocimiento.eval.barra_sin_gpu import BarraSinGpu

    base = {
        "estado": "superada",
        "modo": "bm25_sin_ce",
        "corpus_sha": SHA,
        "n_respondibles": 34,
        "hit_rate_at_5": 0.72,
        "separacion_norma_secundaria": 1.0,
        "vigencia_correcta": 1.0,
        "metodologia": "recorded from a lab run",
        "motivo": "",
    }
    base.update(cambios)
    return BarraSinGpu(**base)


class TestCargadorDeLaBarra:
    def test_el_artefacto_enviado_registra_la_medicion_no_superada(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        artefacto = barra_sin_gpu.cargar_barra()
        assert artefacto.estado == "no_superada"
        assert artefacto.modo == "bm25_sin_ce"
        assert artefacto.corpus_sha == PINNED_CORPUS_SHA
        assert artefacto.n_respondibles == 34
        assert artefacto.hit_rate_at_5 == pytest.approx(22 / 34)
        assert artefacto.separacion_norma_secundaria == 1.0
        assert artefacto.vigencia_correcta == 1.0
        assert barra_sin_gpu.superada_para(PINNED_CORPUS_SHA) is False

    def test_el_artefacto_enviado_no_se_puede_exigir(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match="estado"):
            barra_sin_gpu.exigir_superada(barra_sin_gpu.cargar_barra(), SHA)

    def test_superada_con_todo_en_la_barra_pasa(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        barra_sin_gpu.exigir_superada(_barra(), SHA)

    @pytest.mark.parametrize("estado", ["no_medido", "no_superada"])
    def test_rechaza_lo_que_no_esta_superada(self, estado):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match="estado"):
            barra_sin_gpu.exigir_superada(_barra(estado=estado), SHA)

    def test_rechaza_un_sha_distinto(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match="corpus_sha"):
            barra_sin_gpu.exigir_superada(_barra(), OTRO_SHA)

    def test_rechaza_hit_at_5_por_debajo_de_la_barra(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match="hit@5"):
            barra_sin_gpu.exigir_superada(_barra(hit_rate_at_5=0.71), SHA)

    def test_la_barra_de_hit_at_5_es_la_del_harness(self):
        from app.domains.conocimiento.eval import barra_sin_gpu
        from app.domains.conocimiento.eval.harness import BARRA_HIT_RATE

        assert BARRA_HIT_RATE == 0.72
        barra_sin_gpu.exigir_superada(_barra(hit_rate_at_5=BARRA_HIT_RATE), SHA)

    @pytest.mark.parametrize(
        ("campo", "patron"),
        [
            ("separacion_norma_secundaria", "norma-vs-secundaria"),
            ("vigencia_correcta", "vigencia"),
        ],
    )
    def test_rechaza_separacion_por_debajo_de_uno(self, campo, patron):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match=patron):
            barra_sin_gpu.exigir_superada(_barra(**{campo: 0.99}), SHA)

    def test_rechaza_una_cifra_ausente(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match="hit@5"):
            barra_sin_gpu.exigir_superada(_barra(hit_rate_at_5=None), SHA)

    def test_rechaza_un_modo_que_no_es_el_brazo_sin_gpu(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraNoSuperada, match="modo"):
            barra_sin_gpu.exigir_superada(_barra(modo="bm25_ce"), SHA)

    def test_cargar_lee_un_yaml_y_exigir_lo_acepta(self, tmp_path):
        import yaml

        from app.domains.conocimiento.eval import barra_sin_gpu

        ruta = tmp_path / "barra.yaml"
        ruta.write_text(
            yaml.safe_dump(
                {
                    "estado": "superada",
                    "modo": "bm25_sin_ce",
                    "corpus_sha": SHA,
                    "n_respondibles": 34,
                    "hit_rate_at_5": 0.75,
                    "separacion_norma_secundaria": 1.0,
                    "vigencia_correcta": 1.0,
                    "metodologia": "x",
                }
            ),
            encoding="utf-8",
        )
        barra_sin_gpu.exigir_superada(barra_sin_gpu.cargar_barra(ruta), SHA)
        assert barra_sin_gpu.superada_para(SHA, ruta) is True
        assert barra_sin_gpu.superada_para(OTRO_SHA, ruta) is False

    def test_superada_sin_sus_pines_es_invalida(self, tmp_path):
        import yaml

        from app.domains.conocimiento.eval import barra_sin_gpu

        ruta = tmp_path / "barra.yaml"
        ruta.write_text(yaml.safe_dump({"estado": "superada", "modo": "bm25_sin_ce"}))
        with pytest.raises(barra_sin_gpu.BarraInvalida, match="corpus_sha"):
            barra_sin_gpu.cargar_barra(ruta)
        # A broken artifact never unlocks rank order.
        assert barra_sin_gpu.superada_para(SHA, ruta) is False

    def test_no_medido_con_cifras_es_invalido(self, tmp_path):
        import yaml

        from app.domains.conocimiento.eval import barra_sin_gpu

        ruta = tmp_path / "barra.yaml"
        ruta.write_text(yaml.safe_dump({"estado": "no_medido", "hit_rate_at_5": 0.9}))
        with pytest.raises(barra_sin_gpu.BarraInvalida, match="no_medido"):
            barra_sin_gpu.cargar_barra(ruta)

    def test_estado_desconocido_es_invalido(self, tmp_path):
        import yaml

        from app.domains.conocimiento.eval import barra_sin_gpu

        ruta = tmp_path / "barra.yaml"
        ruta.write_text(yaml.safe_dump({"estado": "aprobada"}))
        with pytest.raises(barra_sin_gpu.BarraInvalida, match="aprobada"):
            barra_sin_gpu.cargar_barra(ruta)


def _no_superada(**cambios):
    """An honest failed bar for `SHA`: hit@5 at 22/34, both other figures at 1.00."""
    base = {"estado": "no_superada", "hit_rate_at_5": 22 / 34}
    base.update(cambios)
    return _barra(**base)


class TestExigirNoSuperadaHonesta:
    """The unranked production path accepts a failed bar and nothing else."""

    def test_una_no_superada_honesta_pasa(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        assert barra_sin_gpu.exigir_no_superada_honesta(_no_superada(), SHA) is None

    @pytest.mark.parametrize(
        "cambios",
        [
            {"hit_rate_at_5": 0.71},
            {"separacion_norma_secundaria": 0.99},
            {"vigencia_correcta": 0.99},
        ],
    )
    def test_alcanza_con_que_una_sola_cifra_falle(self, cambios):
        from app.domains.conocimiento.eval import barra_sin_gpu

        # `_barra` keeps the other two figures on the bar, so exactly one fails.
        artefacto = _barra(estado="no_superada", **cambios)
        assert barra_sin_gpu.exigir_no_superada_honesta(artefacto, SHA) is None

    def test_superada_se_rechaza_y_nombra_el_camino_ranqueado(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="--exigir-barra"):
            barra_sin_gpu.exigir_no_superada_honesta(_barra(), SHA)

    def test_superada_con_otro_modo_sigue_nombrando_el_camino_ranqueado(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="--exigir-barra"):
            barra_sin_gpu.exigir_no_superada_honesta(_barra(modo="bm25_ce"), SHA)

    def test_no_medido_se_rechaza(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="no_medido"):
            barra_sin_gpu.exigir_no_superada_honesta(_no_superada(estado="no_medido"), SHA)

    def test_otro_modo_se_rechaza(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="bm25_ce"):
            barra_sin_gpu.exigir_no_superada_honesta(_no_superada(modo="bm25_ce"), SHA)

    def test_otro_sha_se_rechaza(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="corpus_sha"):
            barra_sin_gpu.exigir_no_superada_honesta(_no_superada(), OTRO_SHA)

    @pytest.mark.parametrize(
        "campo",
        ["hit_rate_at_5", "separacion_norma_secundaria", "vigencia_correcta"],
    )
    def test_una_cifra_ausente_no_es_evidencia_de_fallo(self, campo):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match=campo):
            barra_sin_gpu.exigir_no_superada_honesta(_no_superada(**{campo: None}), SHA)

    def test_no_superada_con_todas_las_cifras_en_la_barra_es_inconsistente(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        with pytest.raises(barra_sin_gpu.BarraSinOrdenRechazada, match="inconsistent"):
            barra_sin_gpu.exigir_no_superada_honesta(_barra(estado="no_superada"), SHA)

    def test_la_excepcion_no_es_la_de_la_barra_no_superada(self):
        from app.domains.conocimiento.eval import barra_sin_gpu

        assert issubclass(barra_sin_gpu.BarraSinOrdenRechazada, RuntimeError)
        assert not issubclass(barra_sin_gpu.BarraSinOrdenRechazada, barra_sin_gpu.BarraNoSuperada)


# ---------------------------------------------------------------------------
# 1.5 — leer and chequear
# ---------------------------------------------------------------------------


@pytest.fixture
def normas():
    from app.domains.conocimiento import normas as modulo

    return modulo


def seed_otro_sha(db) -> None:
    """A second, INACTIVE snapshot that holds a key the active one lacks."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, false)"
        ),
        {"sha": OTRO_SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES "
            "(:sha, 'ley-9750', 'ley-provincial', false, 'provincial', 'vigente', 'publico')"
        ),
        {"sha": OTRO_SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, 'SOLO-OTRO#1', 'ley-9750', 'articulo', 'Texto del otro snapshot.', "
            "'Texto del otro snapshot.', 'g.md', 0)"
        ),
        {"sha": OTRO_SHA},
    )
    db.flush()


class TestLeer:
    def test_devuelve_el_texto_byte_exacto(self, db, normas):
        seed(db)
        crudo = "Art.\u00a01\u00ba  doble  espacio\ty tab\n\nsalto final "
        db.execute(
            text(
                "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                "texto, texto_indexado, source_file, source_offset) VALUES "
                "(:sha, 'ESP#1', 'ley-9750', 'articulo', :texto, 'otro', 'f.md', 7)"
            ),
            {"sha": SHA, "texto": crudo},
        )
        db.flush()
        unidad = normas.leer(db, "ESP#1")
        assert unidad.texto == crudo
        assert unidad.texto.encode("utf-8") == crudo.encode("utf-8")

    def test_lleva_clasificacion_y_procedencia(self, db, normas):
        seed(db)
        privada = normas.leer(db, "MEMO#1")
        publica = normas.leer(db, "9750#1")
        assert privada.clasificacion == "privado"
        assert publica.clasificacion == "publico"
        assert publica.corpus_sha == SHA
        assert publica.source_file == "f.md"
        assert publica.estado_vigencia == "vigente"
        assert publica.es_secundaria is False
        assert normas.leer(db, "INF#1").es_secundaria is True

    def test_clave_desconocida_se_rechaza_sin_devolver_texto(self, db, normas):
        seed(db)
        with pytest.raises(normas.UnidadNoEncontrada) as error:
            normas.leer(db, "NO-EXISTE#9")
        assert "NO-EXISTE#9" in str(error.value)

    def test_una_clave_de_otro_sha_no_se_lee(self, db, normas):
        seed(db)
        seed_otro_sha(db)
        with pytest.raises(normas.UnidadNoEncontrada):
            normas.leer(db, "SOLO-OTRO#1")

    def test_sin_corpus_activo_se_rechaza(self, db, normas):
        seed(db, activo=False)
        with pytest.raises(normas.SinCorpusActivo):
            normas.leer(db, "9750#1")


class TestChequear:
    def test_pasa_con_las_cuatro_condiciones(self, db, normas):
        seed(db)
        veredicto = normas.chequear(db, "9750#1", "administra el canal", "vigente", SHA)
        assert veredicto.pasa is True
        assert veredicto.condicion_fallida is None
        assert veredicto.clasificacion == "publico"

    def test_sha_no_activo_es_rechazo_no_advertencia(self, db, normas):
        seed(db)
        seed_otro_sha(db)
        veredicto = normas.chequear(db, "9750#1", "administra", "vigente", OTRO_SHA)
        assert veredicto.pasa is False
        assert veredicto.condicion_fallida == "sha"

    def test_sin_corpus_activo_el_sha_falla(self, db, normas):
        seed(db, activo=False)
        veredicto = normas.chequear(db, "9750#1", "administra", "vigente", SHA)
        assert (veredicto.pasa, veredicto.condicion_fallida) == (False, "sha")

    def test_clave_ausente_en_ese_sha(self, db, normas):
        seed(db)
        veredicto = normas.chequear(db, "NO-EXISTE#9", "administra", "vigente", SHA)
        assert (veredicto.pasa, veredicto.condicion_fallida) == (False, "clave")
        assert veredicto.clasificacion is None

    def test_clave_que_solo_existe_en_otro_sha(self, db, normas):
        seed(db)
        seed_otro_sha(db)
        veredicto = normas.chequear(db, "SOLO-OTRO#1", "otro snapshot", "vigente", SHA)
        assert (veredicto.pasa, veredicto.condicion_fallida) == (False, "clave")

    def test_span_de_otra_unidad(self, db, normas):
        """The span exists in 9750#2 but not in the cited 9750#1."""
        seed(db)
        veredicto = normas.chequear(db, "9750#1", "presupuesto anual", "vigente", SHA)
        assert (veredicto.pasa, veredicto.condicion_fallida) == (False, "span")
        assert veredicto.clasificacion == "publico"

    def test_span_vacio(self, db, normas):
        """`"" in texto` is True in Python, which is exactly why it is refused first."""
        seed(db)
        veredicto = normas.chequear(db, "9750#1", "", "vigente", SHA)
        assert (veredicto.pasa, veredicto.condicion_fallida) == (False, "span")

    def test_el_span_es_subcadena_literal_no_normalizada(self, db, normas):
        seed(db)
        # Same words, different case: not a substring, so it refuses.
        veredicto = normas.chequear(db, "9750#1", "ADMINISTRA EL CANAL", "vigente", SHA)
        assert veredicto.condicion_fallida == "span"

    def test_vigencia_distinta(self, db, normas):
        seed(db)
        veredicto = normas.chequear(db, "VIEJA#1", "norma derogada", "vigente", SHA)
        assert (veredicto.pasa, veredicto.condicion_fallida) == (False, "vigencia")
        assert normas.chequear(db, "VIEJA#1", "norma derogada", "derogada", SHA).pasa is True

    def test_el_orden_de_las_condiciones(self, db, normas):
        """SHA first, then key, then span, then vigencia: each refusal names ITS condition."""
        seed(db)
        seed_otro_sha(db)
        assert normas.chequear(db, "X#0", "", "mal", OTRO_SHA).condicion_fallida == "sha"
        assert normas.chequear(db, "X#0", "", "mal", SHA).condicion_fallida == "clave"
        assert normas.chequear(db, "9750#1", "", "mal", SHA).condicion_fallida == "span"
        assert normas.chequear(db, "9750#1", "administra", "mal", SHA).condicion_fallida == (
            "vigencia"
        )

    def test_el_rechazo_nombra_la_condicion(self, db, normas):
        seed(db)
        veredicto = normas.chequear(db, "9750#1", "administra", "mal", SHA)
        assert "vigencia" in veredicto.detalle

    def test_lleva_clasificacion_de_una_unidad_privada(self, db, normas):
        seed(db)
        veredicto = normas.chequear(db, "MEMO#1", "Nota interna", "vigente", SHA)
        assert veredicto.pasa is True
        assert veredicto.clasificacion == "privado"


# ---------------------------------------------------------------------------
# 1.6 — the order policy and the empty result
# ---------------------------------------------------------------------------

CONSULTA = "canal de riego"


@pytest.fixture
def barra_superada(tmp_path, monkeypatch):
    """Point the loader at a `superada` artifact for `SHA`."""
    import yaml

    from app.domains.conocimiento.eval import barra_sin_gpu

    def escribir(**cambios):
        datos = {
            "estado": "superada",
            "modo": "bm25_sin_ce",
            "corpus_sha": SHA,
            "n_respondibles": 34,
            "hit_rate_at_5": 0.75,
            "separacion_norma_secundaria": 1.0,
            "vigencia_correcta": 1.0,
            "metodologia": "test",
        }
        datos.update(cambios)
        ruta = tmp_path / "barra.yaml"
        ruta.write_text(yaml.safe_dump(datos), encoding="utf-8")
        monkeypatch.setattr(barra_sin_gpu, "RUTA_BARRA", ruta)

    escribir()
    return escribir


def _orden_bm25(db) -> list[str]:
    resultado = service.recuperar(db, SHA, CONSULTA, modo=service.MODO_SIN_GPU, k=10)
    return [hit.citation_key for hit in sorted(resultado.hits, key=lambda h: h.rango_bm25)]


class TestPoliticaDeOrden:
    def test_el_orden_bm25_difiere_del_orden_por_clave(self, db):
        """Guard on the fixture: both branches below are only distinguishable if this holds."""
        seed(db)
        assert _orden_bm25(db) != sorted(_orden_bm25(db))

    def test_sin_barra_ordena_por_clave_y_no_presenta_orden(self, db, normas):
        seed(db)
        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU)
        claves = [u.citation_key for u in resultado.unidades]
        assert claves == sorted(claves)
        assert set(claves) == set(_orden_bm25(db))
        assert resultado.orden_presentado is False
        assert resultado.nota_orden

    def test_sin_barra_no_hay_rango_ni_puntaje_en_ningun_nivel(self, db, normas):
        seed(db)
        datos = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU).model_dump(mode="json")
        crudo = str(datos).lower()
        for prohibido in ("rango", "score", "valor_bm25", "distancia", "orden_modo"):
            assert prohibido not in crudo, prohibido
        for unidad in datos["unidades"]:
            assert set(unidad) >= {
                "citation_key",
                "texto",
                "tipo",
                "es_secundaria",
                "estado_vigencia",
                "jurisdiccion",
                "relevancia_consorcio",
            }

    def test_con_barra_superada_ordena_por_rango_bm25(self, db, normas, barra_superada):
        seed(db)
        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU)
        assert [u.citation_key for u in resultado.unidades] == _orden_bm25(db)
        assert [u.rango for u in resultado.unidades] == list(range(1, len(resultado.unidades) + 1))
        assert resultado.orden_presentado is True
        assert resultado.orden_modo == "bm25_sin_ce"

    def test_con_barra_superada_tampoco_hay_puntajes(self, db, normas, barra_superada):
        seed(db)
        datos = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU).model_dump(mode="json")
        crudo = str(datos).lower()
        for prohibido in ("score", "valor_bm25", "distancia"):
            assert prohibido not in crudo, prohibido

    def test_barra_de_otro_sha_no_desbloquea_el_orden(self, db, normas, barra_superada):
        barra_superada(corpus_sha=OTRO_SHA)
        seed(db)
        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU)
        assert resultado.orden_presentado is False
        claves = [u.citation_key for u in resultado.unidades]
        assert claves == sorted(claves)

    @pytest.mark.parametrize(
        "cambios",
        [
            {"hit_rate_at_5": 0.71},
            {"separacion_norma_secundaria": 0.99},
            {"vigencia_correcta": 0.99},
            {"estado": "no_superada"},
        ],
    )
    def test_barra_que_no_se_cumple_no_desbloquea_el_orden(
        self, db, normas, barra_superada, cambios
    ):
        barra_superada(**cambios)
        seed(db)
        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU)
        assert resultado.orden_presentado is False

    def test_bm25_ce_nunca_hereda_el_orden_del_otro_brazo(self, db, normas, barra_superada):
        seed(db)
        resultado = normas.buscar(db, CONSULTA, modo="bm25_ce", reranker=RerankerDeterministico())
        assert resultado.modo == "bm25_ce"
        assert resultado.orden_presentado is False
        claves = [u.citation_key for u in resultado.unidades]
        assert claves == sorted(claves)

    def test_bm25_ce_sin_reranker_sigue_rechazando(self, db, normas):
        seed(db)
        with pytest.raises(service.RerankerRequerido):
            normas.buscar(db, CONSULTA, modo="bm25_ce")

    def test_la_respuesta_lleva_modo_y_procedencia(self, db, normas):
        seed(db)
        resultado = normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU)
        assert resultado.modo == "bm25_sin_ce"
        assert resultado.corpus_sha == SHA
        assert resultado.ingested_at is not None

    def test_vacio_marca_sin_unidades_y_no_habla_de_abstencion(self, db, normas, barra_superada):
        seed(db)
        resultado = normas.buscar(db, "zzzz", modo=service.MODO_SIN_GPU)
        assert resultado.unidades == []
        assert resultado.sin_unidades is True
        assert resultado.orden_presentado is False
        datos = resultado.model_dump(mode="json")
        assert "abstenc" not in str(datos).lower()
        assert "umbral" not in str(datos).lower()

    def test_con_resultados_sin_unidades_es_falso(self, db, normas):
        seed(db)
        assert normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU).sin_unidades is False

    def test_sin_corpus_activo_se_rechaza(self, db, normas):
        seed(db, activo=False)
        with pytest.raises(normas.SinCorpusActivo):
            normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU)

    def test_k_acota_las_unidades(self, db, normas):
        seed(db)
        assert len(normas.buscar(db, CONSULTA, modo=service.MODO_SIN_GPU, k=2).unidades) == 2


class TestNoHayRedactar:
    def test_el_kernel_no_define_redactar(self):
        from pathlib import Path

        from app.domains.conocimiento import normas

        assert not hasattr(normas, "redactar")
        assert "def redactar" not in Path(normas.__file__).read_text(encoding="utf-8")
