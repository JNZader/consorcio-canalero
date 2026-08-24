"""The mailbox worker: every named refusal in the chain lands as an ITEM STATE (U7).

This file exists for one claim: `procesar_uno` never lets a named refusal escape
as a traceback. A worker that dies on a refusal it could have recorded turns a
diagnosable state into a log line AND leaves the item `pendiente` forever with no
explanation — A3's honesty obligation inverted.

The chain has four sources of named refusals and each gets a row here: the
sidecar (routing), retrieval, the cost ceilings, and the provider. The item
budget gets its own, because U6 shipped a `PresupuestoAgotado` that escaped the
one function supposed to own every terminal state.

No network: the embedder, the reranker and the generator are all fakes injected
through the seams the production wiring already uses.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.conocimiento import buzon, routing, service, trabajador
from app.domains.conocimiento.embed_sidecar import SidecarNoDisponible
from app.domains.conocimiento.generacion import (
    GeneracionNoDisponible,
    PresupuestoAgotado,
    SalidaProveedor,
)
from app.domains.conocimiento.models import RagDecisionRuta

SHA = "b" * 40


def seed(db) -> None:
    """One public snapshot with one citable unit. Real Postgres."""
    db.execute(
        text(
            "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
            "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, true)"
        ),
        {"sha": SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
            "jurisdiccion, estado_vigencia, clasificacion) VALUES "
            "(:sha, 'ley-9750', 'ley-provincial', false, 'provincial', 'vigente', 'publico')"
        ),
        {"sha": SHA},
    )
    db.execute(
        text(
            "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
            "texto, texto_indexado, source_file, source_offset) VALUES "
            "(:sha, 'ley-9750#art1', 'ley-9750', 'articulo', :t, :t, 'f.md', 0)"
        ),
        {"sha": SHA, "t": "El consorcio administra la red de canales."},
    )
    db.flush()


class EmbedderFalso:
    model_id = "falso"
    revision = None
    dims = 3
    token_ceiling = 512

    def __init__(self, vector=(1.0, 0.0, 0.0), falla: Exception | None = None) -> None:
        self._vector = tuple(vector)
        self._falla = falla

    def count_tokens(self, texto: str) -> int:  # pragma: no cover - query seam
        raise NotImplementedError

    def encode(self, textos):
        if self._falla is not None:
            raise self._falla
        return [list(self._vector) for _ in textos]


class RerankerFalso:
    model_id = "falso-ce"
    sintetico = False

    def puntuar(self, pregunta, textos):  # pragma: no cover - shape only
        return [1.0 for _ in textos]


class RerankerFalsoSintetico(RerankerFalso):
    model_id = "deterministico"
    sintetico = True


class GeneradorFalso:
    """A `Generador` context manager that replays one scripted outcome."""

    sintetico = False
    model_id = "falso"

    def __init__(self, guion) -> None:
        self._guion = guion
        self.cerrado = False

    def generar(self, prompt: str, *, max_tokens: int):
        if isinstance(self._guion, BaseException):
            raise self._guion
        return self._guion

    def close(self) -> None:
        self.cerrado = True

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def centroides_hacia(clase: str) -> routing.Centroides:
    """Centroids whose top score is `clase` by construction."""
    base = {
        routing.CLASE_LEGAL: (1.0, 0.0, 0.0),
        routing.CLASE_OPERATIONAL: (0.0, 1.0, 0.0),
        routing.CLASE_GEOESPACIAL: (0.0, 0.0, 1.0),
    }
    ganador = base.pop(clase)
    return routing.Centroides({clase: ganador, **base})


PARAMETROS = routing.ParametrosRuta(umbral=0.1, banda=0.05, piso=0.5)


def correr(
    db,
    *,
    embedder=None,
    centroides=None,
    reranker=None,
    generador=None,
    item_deadline_s: float = 60.0,
    monkeypatch=None,
    recuperar_falla: Exception | None = None,
):
    if recuperar_falla is not None:

        def _explota(*_a, **_k):
            raise recuperar_falla

        monkeypatch.setattr(service, "recuperar", _explota)

    gen = (
        generador
        if generador is not None
        else GeneradorFalso(SalidaProveedor(texto="Corresponde [ley-9750#art1].", truncado=False))
    )
    return trabajador.procesar_uno(
        db,
        corpus_sha=SHA,
        embedder=embedder or EmbedderFalso(),
        centroides=centroides or centroides_hacia(routing.CLASE_LEGAL),
        parametros=PARAMETROS,
        reranker=reranker or RerankerFalso(),
        crear_generador=lambda _presupuesto: gen,
        item_deadline_s=item_deadline_s,
    )


class TestColaVacia:
    def test_sin_pendientes_no_hace_nada(self, db):
        assert (
            trabajador.procesar_uno(
                db,
                corpus_sha=SHA,
                embedder=EmbedderFalso(),
                centroides=centroides_hacia(routing.CLASE_LEGAL),
                parametros=PARAMETROS,
                reranker=RerankerFalso(),
                crear_generador=lambda _p: GeneradorFalso(None),
            )
            is None
        )


class TestRerankerSintetico:
    def test_un_ranker_de_relleno_se_rechaza_ANTES_de_tocar_la_cola(self, db):
        """Fail-closed: no CPU fallback, no smaller model, no stand-in.

        And refused BEFORE the claim, so the refusal cannot consume an item: a
        wiring fault must not be recorded as "your question could not be
        answered".
        """
        item = buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley?")
        with pytest.raises(trabajador.RerankerSintetico):
            correr(db, reranker=RerankerFalsoSintetico())
        db.refresh(item)
        assert item.estado == "pendiente"


class TestRedireccionPura:
    def test_una_pregunta_operativa_termina_en_redireccion_sin_tocar_al_proveedor(self, db):
        """No GPU, no provider, terminal at routing time."""
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="cómo pago la cuota de este año")
        generador = GeneradorFalso(AssertionError("the provider must not be called"))
        item = correr(
            db, centroides=centroides_hacia(routing.CLASE_OPERATIONAL), generador=generador
        )
        assert item.estado == "redireccion"
        assert item.respuesta["redireccion"]["superficie"] in routing.SUPERFICIES
        assert item.respuesta["respuesta"] is None
        assert item.respuesta["citas"] == []

    def test_la_decision_de_ruta_queda_registrada_y_ligada_al_item(self, db):
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="cómo pago la cuota de este año")
        item = correr(db, centroides=centroides_hacia(routing.CLASE_OPERATIONAL))
        assert item.decision_ruta_id is not None
        registro = db.get(RagDecisionRuta, item.decision_ruta_id)
        # U4's record and U7's item are joined here and nowhere else.
        assert registro.pregunta == "cómo pago la cuota de este año"


class TestRefusalesQueAterrizanComoEstado:
    def test_el_sidecar_caido_es_no_disponible_y_no_una_excepcion(self, db):
        seed(db)
        item_creado = buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        item = correr(
            db,
            embedder=EmbedderFalso(
                falla=SidecarNoDisponible("embedder_no_listo", "container down")
            ),
        )
        assert item.id == item_creado.id
        assert item.estado == "no_disponible"
        assert "embedder_no_listo" in item.respuesta["motivo"]
        # No classification happened, so there is nothing honest to redirect to.
        assert item.respuesta["redireccion_parcial"] is None
        assert item.decision_ruta_id is None

    @pytest.mark.parametrize(
        "falla",
        [
            service.EmbeddingsNoCargadas("never embedded"),
            service.EmbedderMismatch("another model wrote the column"),
            service.RerankerRequerido("no ranker"),
        ],
    )
    def test_los_refusales_de_recuperacion_son_no_disponible_nunca_abstencion(
        self, db, monkeypatch, falla
    ):
        """An abstention would tell a CD member the corpus has nothing for them,
        which is a false statement about the law."""
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        item = correr(db, monkeypatch=monkeypatch, recuperar_falla=falla)
        assert item.estado == "no_disponible"
        assert type(falla).__name__ in item.respuesta["motivo"]

    def test_un_snapshot_con_embeddings_sinteticos_no_se_sirve(self, db):
        """Task 7.6: serving refuses OUTRIGHT when `sintetico` is true."""
        seed(db)
        db.execute(
            text(
                "UPDATE rag_corpus SET embedding_modelo = 'stub', embedding_sintetico = true "
                "WHERE corpus_sha = :sha"
            ),
            {"sha": SHA},
        )
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        item = correr(db)
        assert item.estado == "no_disponible"
        assert "CorpusNoServible" in item.respuesta["motivo"]

    def test_el_techo_de_gasto_es_no_disponible_del_item(self, db, monkeypatch):
        """`MedidorDeGasto` refuses BEFORE an attempt is issued, which is outside
        anything `generar_respuesta` wraps — so it needs this catch."""
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        monkeypatch.setattr(
            service,
            "recuperar",
            lambda *a, **k: _resultado_con_un_hit(),
        )
        item = correr(
            db,
            generador=GeneradorFalso(GeneracionNoDisponible("TechoDeGasto: window spent")),
        )
        assert item.estado == "no_disponible"
        assert "TechoDeGasto" in item.respuesta["motivo"]

    def test_el_presupuesto_del_item_agotado_es_generacion_fallida(self, db, monkeypatch):
        """NOT `no_disponible`: the box was available, the item just did not
        finish, and "not available" would send an operator to inspect a healthy
        dependency."""
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        monkeypatch.setattr(service, "recuperar", lambda *a, **k: _resultado_con_un_hit())
        item = correr(db, generador=GeneradorFalso(PresupuestoAgotado("60.0s spent")))
        assert item.estado == "generacion_fallida"
        assert "presupuesto_item_agotado" in item.respuesta["motivo"]

    def test_un_presupuesto_ya_vencido_falla_el_item_ANTES_de_recuperar(self, db, monkeypatch):
        """The budget bounds the ITEM, not the generator: an item that spent its
        whole budget before retrieval has still spent it."""
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        llamadas: list[int] = []
        monkeypatch.setattr(
            service, "recuperar", lambda *a, **k: llamadas.append(1) or _resultado_con_un_hit()
        )
        item = correr(db, item_deadline_s=-1.0)
        assert item.estado == "generacion_fallida"
        assert "presupuesto_item_agotado" in item.respuesta["motivo"]
        assert llamadas == [], "retrieval ran on an item whose budget was already spent"


class TestCaminoFeliz:
    def test_una_respuesta_certificada_aterriza_con_sus_citas(self, db, monkeypatch):
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        monkeypatch.setattr(service, "recuperar", lambda *a, **k: _resultado_con_un_hit())
        item = correr(db)
        assert item.estado == "respuesta"
        assert item.respuesta["citas"][0]["citation_key"] == "ley-9750#art1"
        assert item.procesada_en is not None

    def test_el_adaptador_del_proveedor_se_cierra_siempre(self, db, monkeypatch):
        """One adapter per item, closed per item: an unclosed pool per item is a
        descriptor leak that shows up as a worker that stops answering."""
        seed(db)
        buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        monkeypatch.setattr(service, "recuperar", lambda *a, **k: _resultado_con_un_hit())
        generador = GeneradorFalso(GeneracionNoDisponible("caído"))
        correr(db, generador=generador)
        assert generador.cerrado


class TestElItemNoSeOrfana:
    def test_una_excepcion_SIN_NOMBRE_no_se_traga_y_deja_el_item_pendiente(self, db, monkeypatch):
        """A `KeyError` here is a bug. Swallowing it into `no_disponible` would
        report an outage the operator would go looking for in a healthy
        dependency. It propagates, the transaction rolls back, and the item is
        still `pendiente` — the state it never left.
        """
        seed(db)
        item = buzon.encolar(db, usuario_id=None, pregunta="¿qué dice la ley 9750?")
        monkeypatch.setattr(
            service, "recuperar", lambda *a, **k: (_ for _ in ()).throw(KeyError("bug"))
        )
        with pytest.raises(KeyError):
            correr(db)
        # The claimed row was never moved: no terminal state, no payload, no
        # timestamp. The caller's rollback then releases the lock and the item is
        # claimable again — which is the whole reason there is no reaper here.
        assert item.estado == "pendiente"
        assert item.respuesta is None
        assert item.procesada_en is None


def _resultado_con_un_hit():
    from app.domains.conocimiento.schemas import CitaRecuperada, ResultadoRecuperacion

    return ResultadoRecuperacion(
        corpus_sha=SHA,
        pregunta="¿qué dice la ley 9750?",
        modo="bm25_ce",
        k=10,
        hits=[
            CitaRecuperada(
                citation_key="ley-9750#art1",
                documento_id="ley-9750",
                tipo_chunk="articulo",
                texto="El consorcio administra la red de canales.",
                tipo="ley-provincial",
                es_secundaria=False,
                jurisdiccion="provincial",
                estado_vigencia="vigente",
                source_file="f.md",
                source_offset=0,
            )
        ],
        reranker_modelo="falso-ce",
        reranker_sintetico=False,
    )
