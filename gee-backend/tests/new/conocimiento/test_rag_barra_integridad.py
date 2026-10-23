"""Integrity binding of `eval/barra_sin_gpu.yaml` (audit finding RAG-2).

Before this seal, the three serving predicates (`exigir_superada`,
`exigir_no_superada_honesta`, `superada_para`) validated the artifact's OWN
fields only: the estado word, the modo, the corpus_sha, the figures against
constants. Nothing bound the checked-in file to a measured run, so an
internally-consistent hand edit — `estado: superada` plus figures above every
constant plus the served corpus_sha — loaded cleanly, passed
`rag_ingest --exigir-barra` and flipped serving to rank order on fabricated
numbers. The mirrored edit fabricated an honest-looking `no_superada` for
`--produccion-sin-orden`.

`integridad_sha256` closes that copy window: a digest over the load-bearing
fields (`CAMPOS_INTEGRIDAD`), stamped by the generation path (`derivar_desde`
-> `volcar`, the block `scripts/rag_eval.py` prints) and re-verified by
`cargar_barra`, the single choke point every predicate loads through. Honesty
stance copied from the `regla_sha256` precedent
(`repository.regla_clasificacion_sha256`): the hash is unkeyed, so it is NOT
cryptographic proof that a figure was measured — it raises the bar to "the
edit must also forge the digest, and both lines then sit in the review diff of
the commit that flips serving".

The RED-CHECK tests feed a generation-stamped, then field-tampered artifact to
the loader: on the unfixed loader such an artifact loaded fine (that IS the
finding), so the `pytest.raises(BarraInvalida)` assertions there were red
witnesses before the fix and are green now.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from types import SimpleNamespace

import pytest
import yaml

from app.domains.conocimiento.eval import barra_sin_gpu
from app.domains.conocimiento.service import ProcedenciaEmbeddings

from .test_normas_kernel import OTRO_SHA, SHA

ARM = "bm25_sin_ce"
GENERADO = dt.datetime(2026, 10, 23, 12, 0, tzinfo=dt.timezone.utc)


def _procedencia():
    return ProcedenciaEmbeddings(
        corpus_sha=SHA,
        modelo="BAAI/bge-m3",
        revision_hf="a" * 40,
        sintetico=False,
        artifact_sha256="b" * 64,
        loaded_at=GENERADO,
    )


def _corrida(*, hit: float | None = 0.75):
    """A scored run reduced to what `derivar_desde` reads (mirrors test_normas_eval)."""
    return SimpleNamespace(
        modo=ARM,
        metricas=SimpleNamespace(
            n_respondibles=34,
            hit_rate_at_5=hit,
            separacion_norma_secundaria=1.0,
            vigencia_correctness=1.0,
        ),
        perdidas_de_migracion=(),
    )


def _gold_evaluable():
    from .test_rag_eval_harness import gold_item, gold_set

    return gold_set(
        *[gold_item(f"g-{i:02d}", "canal de riego", "answerable", ("9750#1",)) for i in range(20)],
        corpus_sha=SHA,
    )


def _artefacto_superado(tmp_path, *, hit: float = 0.75):
    """The generation path end to end: derive, dump, write, return the path.

    The written file is born sealed because `volcar` stamps the digest — that
    is the contract under test, so the base artifact always comes from
    `derivar_desde`/`volcar`, never from a hand-typed dict.
    """
    barra = barra_sin_gpu.derivar_desde(_corrida(hit=hit), _procedencia(), _gold_evaluable())
    ruta = tmp_path / "barra.yaml"
    ruta.write_text(barra_sin_gpu.a_yaml(barra), encoding="utf-8")
    return ruta, barra


def _volcar_yaml_en(tmp_path, datos, nombre="barra.yaml"):
    ruta = tmp_path / nombre
    ruta.write_text(yaml.safe_dump(datos, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return ruta


class TestElSelloCubreLosCamposQueDeciden:
    """RED-CHECK: every load-bearing field is inside the digest.

    Each case tampers ONE covered field after the generation path stamped the
    digest, exactly like the consistent hand edit of finding RAG-2. On the
    unfixed loader every one of these artifacts loaded fine; the assertions
    were the red witnesses.
    """

    @pytest.mark.parametrize(
        ("campo", "valor"),
        [
            ("estado", "no_superada"),
            ("modo", "bm25_ce"),
            ("corpus_sha", OTRO_SHA),
            ("n_respondibles", 35),
            ("hit_rate_at_5", 0.99),
            ("separacion_norma_secundaria", 0.5),
            ("vigencia_correcta", 0.5),
        ],
    )
    def test_un_campo_tocado_con_sello_viejo_es_invalido(self, tmp_path, campo, valor):
        ruta, _ = _artefacto_superado(tmp_path)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        datos[campo] = valor  # the edit; the digest line stays what volcar stamped
        _volcar_yaml_en(tmp_path, datos)

        with pytest.raises(barra_sin_gpu.BarraInvalida, match="integridad"):
            barra_sin_gpu.cargar_barra(ruta)

    def test_el_canon_es_exactamente_campos_integridad(self, tmp_path):
        """The exclusion list is explicit: metodologia/motivo are prose no predicate reads."""
        ruta, barra = _artefacto_superado(tmp_path)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        assert barra_sin_gpu.CAMPOS_INTEGRIDAD == (
            "estado",
            "modo",
            "corpus_sha",
            "n_respondibles",
            "hit_rate_at_5",
            "separacion_norma_secundaria",
            "vigencia_correcta",
        )
        # Prose is outside the seal: rewording metodologia keeps the artifact loadable.
        datos["metodologia"] = "reworded prose, same measurement"
        _volcar_yaml_en(tmp_path, datos)
        cargado = barra_sin_gpu.cargar_barra(ruta)
        assert cargado.metodologia == "reworded prose, same measurement"
        assert dataclasses.replace(cargado, metodologia=barra.metodologia) == barra


class TestLaFabricacionConsistenteYaNoCarga:
    """RED-CHECK for both serving directions of finding RAG-2.

    Pre-fix, a generation-stamped artifact whose estado+figures were then
    hand-edited into internal consistency loaded cleanly AND passed the
    predicate it was aimed at. Each direction gets its own tamper.
    """

    def test_superada_fabricada_sobre_una_falla_real(self, tmp_path):
        # Measured reality: 22/34, a failed bar. The edit: estado+hit flipped.
        ruta, _ = _artefacto_superado(tmp_path, hit=22 / 34)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        assert datos["estado"] == "no_superada"
        datos["estado"] = "superada"
        datos["hit_rate_at_5"] = 0.75
        _volcar_yaml_en(tmp_path, datos)

        with pytest.raises(barra_sin_gpu.BarraInvalida, match="integridad"):
            barra_sin_gpu.cargar_barra(ruta)
        # Fail-safe holds: a broken artifact never unlocks rank order.
        assert barra_sin_gpu.superada_para(SHA, ruta) is False

    def test_no_superada_fabricada_sobre_un_exito_real(self, tmp_path):
        # Measured reality: 0.75, a cleared bar. The edit: a manufactured failure.
        ruta, _ = _artefacto_superado(tmp_path, hit=0.75)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        assert datos["estado"] == "superada"
        datos["estado"] = "no_superada"
        datos["hit_rate_at_5"] = 22 / 34
        _volcar_yaml_en(tmp_path, datos)

        with pytest.raises(barra_sin_gpu.BarraInvalida, match="integridad"):
            barra_sin_gpu.cargar_barra(ruta)


class TestElSelloMismo:
    def test_un_sello_tocado_es_invalido(self, tmp_path):
        ruta, _ = _artefacto_superado(tmp_path)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        datos["integridad_sha256"] = "0" * 64
        _volcar_yaml_en(tmp_path, datos)

        with pytest.raises(barra_sin_gpu.BarraInvalida, match="integridad"):
            barra_sin_gpu.cargar_barra(ruta)

    def test_un_artefacto_sin_sello_es_invalido(self, tmp_path):
        """Deleting the seal line is not a bypass: no seal, no load."""
        ruta, _ = _artefacto_superado(tmp_path)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        del datos["integridad_sha256"]
        _volcar_yaml_en(tmp_path, datos)

        with pytest.raises(barra_sin_gpu.BarraInvalida, match="integridad_sha256"):
            barra_sin_gpu.cargar_barra(ruta)
        assert barra_sin_gpu.superada_para(SHA, ruta) is False


class TestElCaminoDeGeneracionSellaYCarga:
    """The generation path stamps the digest with the same function the loader verifies."""

    def test_un_artefacto_derivado_carga_con_su_propio_sello(self, tmp_path):
        ruta, barra = _artefacto_superado(tmp_path)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))

        assert "integridad_sha256" in datos
        assert datos["integridad_sha256"] == barra_sin_gpu.integridad_sha256(barra)
        assert barra_sin_gpu.cargar_barra(ruta) == barra
        assert barra_sin_gpu.superada_para(SHA, ruta) is True
        assert barra_sin_gpu.superada_para(OTRO_SHA, ruta) is False

    def test_un_no_medido_tambien_lleva_sello_y_carga(self, tmp_path):
        barra = barra_sin_gpu.derivar_desde(
            _corrida(), _procedencia(), _gold_evaluable(), permitir_sintetico=True
        )
        assert barra.estado == "no_medido"
        ruta = _volcar_yaml_en(tmp_path, barra_sin_gpu.volcar(barra))
        assert barra_sin_gpu.cargar_barra(ruta) == barra

    def test_sellar_re_estampa_un_volcado_editado(self, tmp_path):
        """One function re-seals an edited dump — the honest way to adjust a dumped block."""
        ruta, _ = _artefacto_superado(tmp_path)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        datos["metodologia"] = "prosa ajustada"
        datos = barra_sin_gpu.sellar(datos)
        _volcar_yaml_en(tmp_path, datos)
        assert barra_sin_gpu.cargar_barra(ruta).metodologia == "prosa ajustada"

    def test_el_artefacto_enviado_lleva_un_sello_valido(self):
        """The checked-in yaml must re-verify against its own loaded fields."""
        raw = yaml.safe_load(barra_sin_gpu.RUTA_BARRA.read_text(encoding="utf-8"))
        assert raw["integridad_sha256"], "barra_sin_gpu.yaml ships without the integrity seal"
        artefacto = barra_sin_gpu.cargar_barra()
        assert raw["integridad_sha256"] == barra_sin_gpu.integridad_sha256(artefacto)
