"""Task 9.6 — the shipped abstention threshold, its header and its refusal.

The threshold that decides whether the surface answers or abstains is a config
value SEEDED FROM THE EVAL, carrying `(corpus_sha, embedding_modelo,
embedding_revision_hf, n, metodologia)`. Serving reads it and refuses with
`base_de_conocimiento_no_lista` on mismatch, on the same discipline as
`verificar_corpus_sha`.

The artifact ships with NO number, and that is task 9.5 showing through: owner
decision 0.1 is open, the serving arm carries no ratified abstention signal, and
a number here would set the enablement gate to a value nobody chose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from app.domains.conocimiento import service
from app.domains.conocimiento.eval import umbral_abstencion as ua
from app.domains.conocimiento.eval.umbral_abstencion import (
    ESTADO_DERIVADO,
    ESTADO_NO_DERIVADO,
    UmbralAbstencionDivergente,
    UmbralAbstencionInvalido,
    cargar_umbral,
    verificar_identidad,
)
from app.domains.conocimiento.repository import registrar_procedencia

SHA = "c" * 40


def escribir(tmp_path: Path, datos: dict) -> Path:
    ruta = tmp_path / "umbral_abstencion.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return ruta


def derivado(**cambios) -> dict:
    base = {
        "estado": ESTADO_DERIVADO,
        "corpus_sha": SHA,
        "embedding_modelo": "BAAI/bge-m3",
        "embedding_revision_hf": "a" * 40,
        "n": 52,
        "metodologia": "LOOCV sobre hybrid",
        "umbral": 0.0163,
        "motivo": "",
    }
    base.update(cambios)
    return base


class TestElArtefactoQueSeCommitea:
    def test_ship_sin_numero_porque_la_decision_0_1_sigue_abierta(self):
        """`estado: no_derivado`, `umbral: null` — and the reason written down.

        Task 9.5 is blocked and the serving arm has no ratified signal. A number
        here would be the gate set to whatever the sweep returned, wearing the
        clothes of a decision.
        """
        artefacto = cargar_umbral()
        assert artefacto.estado == ESTADO_NO_DERIVADO
        assert artefacto.umbral is None
        assert "0.1" in artefacto.motivo
        assert "0.489" in artefacto.motivo, "the measured figure travels with the refusal"

    def test_el_encabezado_esta_completo_aunque_este_vacio(self):
        """Every key the design names is present, holding `null`.

        A key that only appears once it has a value is a key nobody notices is
        missing — and the header is what makes the number auditable.
        """
        datos = yaml.safe_load(ua.RUTA_UMBRAL.read_text(encoding="utf-8"))
        for campo in (
            "corpus_sha",
            "embedding_modelo",
            "embedding_revision_hf",
            "n",
            "metodologia",
            "umbral",
        ):
            assert campo in datos

    def test_pedirle_el_numero_a_un_artefacto_no_derivado_refusa(self):
        with pytest.raises(UmbralAbstencionInvalido) as fallo:
            cargar_umbral().exigir_umbral()
        assert "no_derivado" in str(fallo.value)


class TestEsquema:
    def test_un_derivado_sin_pines_es_invalido(self, tmp_path):
        """The vacuous-pass hole, closed.

        A derived threshold with `corpus_sha: null` compares equal to a snapshot
        whose provenance is also absent, so it would pass the identity check and
        be served against an unknown corpus.
        """
        ruta = escribir(tmp_path, derivado(corpus_sha=None))
        with pytest.raises(UmbralAbstencionInvalido) as fallo:
            cargar_umbral(ruta)
        assert "corpus_sha" in str(fallo.value)

    def test_un_no_derivado_con_numero_es_invalido(self, tmp_path):
        """Nobody ratified it and it is sitting there for somebody to read."""
        ruta = escribir(tmp_path, {"estado": ESTADO_NO_DERIVADO, "umbral": 0.5})
        with pytest.raises(UmbralAbstencionInvalido) as fallo:
            cargar_umbral(ruta)
        assert "peor de los dos mundos" in str(fallo.value)

    def test_un_estado_desconocido_es_invalido(self, tmp_path):
        ruta = escribir(tmp_path, {"estado": "casi"})
        with pytest.raises(UmbralAbstencionInvalido):
            cargar_umbral(ruta)


class TestIdentidad:
    def test_los_tres_pines_coincidentes_no_levantan_nada(self, tmp_path):
        artefacto = cargar_umbral(escribir(tmp_path, derivado()))
        verificar_identidad(
            artefacto,
            corpus_sha=SHA,
            embedding_modelo="BAAI/bge-m3",
            embedding_revision_hf="a" * 40,
        )

    @pytest.mark.parametrize(
        "kwargs,esperado",
        [
            ({"corpus_sha": "9" * 40}, "corpus_sha"),
            ({"embedding_modelo": "intfloat/multilingual-e5-large"}, "embedding_modelo"),
            ({"embedding_revision_hf": "b" * 40}, "embedding_revision_hf"),
        ],
    )
    def test_cualquier_divergencia_refusa(self, tmp_path, kwargs, esperado):
        """The HF revision counts too: two revisions are two vector spaces.

        `EmbedderMismatch` compares the same pair for the same reason. A cosine
        threshold is a statement about a space, so a threshold carried across a
        revision bump is a cut at a value that means something else there.
        """
        artefacto = cargar_umbral(escribir(tmp_path, derivado()))
        base = {
            "corpus_sha": SHA,
            "embedding_modelo": "BAAI/bge-m3",
            "embedding_revision_hf": "a" * 40,
        }
        with pytest.raises(UmbralAbstencionDivergente) as fallo:
            verificar_identidad(artefacto, **{**base, **kwargs})
        assert esperado in str(fallo.value)

    def test_un_no_derivado_nunca_es_un_mismatch(self, tmp_path):
        """No number means nothing can be served against the wrong one.

        Refusing here would take the surface down for a state that is task 9.5's
        (the flag), not this check's.
        """
        artefacto = cargar_umbral(escribir(tmp_path, {"estado": ESTADO_NO_DERIVADO}))
        verificar_identidad(
            artefacto,
            corpus_sha="lo-que-sea",
            embedding_modelo=None,
            embedding_revision_hf=None,
        )


class TestDerivarDesdeLaCorrida:
    """The artifact is SEEDED from the eval, never typed by hand."""

    class _LOOCV:
        n = 52
        umbral_shipped = 0.0163

    def _corrida(self, *, modo="hybrid", ratificada=True):
        class Corrida:
            pass

        corrida = Corrida()
        corrida.modo = modo
        corrida.senal_ratificada = ratificada
        corrida.fuente_senal = "RRF fusionado"
        corrida.loocv = self._LOOCV()
        return corrida

    class _Procedencia:
        corpus_sha = SHA
        modelo = "BAAI/bge-m3"
        revision_hf = "a" * 40
        sintetico = False

    def test_una_corrida_real_produce_el_artefacto_completo(self):
        artefacto = ua.derivar_desde(self._corrida(), self._Procedencia())
        assert artefacto.estado == ESTADO_DERIVADO
        assert artefacto.umbral == 0.0163
        assert artefacto.n == 52
        assert "LOOCV" in artefacto.metodologia
        assert artefacto.exigir_umbral() == 0.0163

    def test_un_modo_sin_senal_ratificada_no_deriva_nada(self):
        """`bm25_ce` — the arm that is actually served, and the whole of 9.5.

        Deriving a threshold from an unratified signal would leave the gate at
        whatever the system already does, presented as a decision.
        """
        artefacto = ua.derivar_desde(
            self._corrida(modo="bm25_ce", ratificada=False), self._Procedencia()
        )
        assert artefacto.estado == ESTADO_NO_DERIVADO
        assert artefacto.umbral is None
        assert "0.1" in artefacto.motivo

    def test_un_snapshot_sintetico_no_deriva_nada(self):
        class Sintetica(self._Procedencia):
            sintetico = True

        artefacto = ua.derivar_desde(self._corrida(), Sintetica())
        assert artefacto.estado == ESTADO_NO_DERIVADO
        assert "ruido de hash" in artefacto.motivo

    def test_el_volcado_conserva_el_orden_del_encabezado(self):
        volcado = ua.volcar(ua.derivar_desde(self._corrida(), self._Procedencia()))
        assert list(volcado)[:6] == [
            "estado",
            "corpus_sha",
            "embedding_modelo",
            "embedding_revision_hf",
            "n",
            "metodologia",
        ]


class TestElServingLoLee:
    """The refusal reaching the path that answers a real question."""

    def seed(self, db) -> None:
        db.execute(
            text(
                "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, true)"
            ),
            {"sha": SHA},
        )
        registrar_procedencia(
            db,
            SHA,
            modelo="BAAI/bge-m3",
            revision_hf="a" * 40,
            sintetico=False,
            artifact_sha256="b" * 64,
        )
        db.flush()

    def test_con_el_artefacto_shipped_no_derivado_el_serving_no_refusa(self, db):
        """Today's state: no threshold, so no mismatch, so no refusal."""
        self.seed(db)
        service.verificar_umbral_abstencion(db, SHA)

    def test_un_umbral_de_otro_corpus_es_corpus_no_servible(self, db, tmp_path, monkeypatch):
        """The refusal the task names, arriving where it can stop an answer.

        `UmbralAbstencionNoCorresponde` is a `CorpusNoServible`, so the worker
        already turns it into `no_disponible` naming the exception and the
        synchronous surface into `base_de_conocimiento_no_lista`. Both say "this
        deployment is not ready" — never "the corpus has nothing applicable".
        """
        self.seed(db)
        ajeno = escribir(tmp_path, derivado(corpus_sha="9" * 40))
        monkeypatch.setattr(ua, "RUTA_UMBRAL", ajeno)
        with pytest.raises(service.UmbralAbstencionNoCorresponde) as fallo:
            service.verificar_umbral_abstencion(db, SHA)
        assert issubclass(type(fallo.value), service.CorpusNoServible)
        assert "corpus_sha" in str(fallo.value)

    def test_un_umbral_de_otro_espacio_vectorial_tambien_refusa(self, db, tmp_path, monkeypatch):
        self.seed(db)
        ajeno = escribir(tmp_path, derivado(embedding_revision_hf="b" * 40))
        monkeypatch.setattr(ua, "RUTA_UMBRAL", ajeno)
        with pytest.raises(service.UmbralAbstencionNoCorresponde):
            service.verificar_umbral_abstencion(db, SHA)
