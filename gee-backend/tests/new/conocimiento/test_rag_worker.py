"""The worker RUNNER: the loop, the shutdown and the refusals (U7, task 7.7).

`procesar_uno` shipped with no caller — no loop, no CLI, no scheduled task — so
`POST /preguntas` wrote `pendiente` rows nothing would ever pick up. This file
covers the loop that fixes that, and ONLY the loop: how an item is processed is
`test_trabajador.py`'s subject and is not re-asserted here.

Every seam is faked. There is no GPU, no sidecar, no gateway and no sleeping:
`Parada.dormir` is replaced by a recorder, so "the empty queue sleeps" is an
assertion about a call rather than about elapsed wall time.
"""

from __future__ import annotations

import signal
from types import SimpleNamespace

import pytest

from app.domains.conocimiento import trabajador
from app.domains.conocimiento.proveedores import ProveedorMalConfigurado, TerminosNoVerificados
from app.domains.conocimiento.recuperacion.reranker import RerankerNoDisponible
from scripts import rag_worker


class SesionFalsa:
    """A session that records the transaction verbs and nothing else."""

    def __init__(self) -> None:
        self.eventos: list[str] = []

    def commit(self) -> None:
        self.eventos.append("commit")

    def rollback(self) -> None:
        self.eventos.append("rollback")

    def close(self) -> None:
        self.eventos.append("close")


class Fabrica:
    """A `session_factory` that hands out a fresh recorder per call."""

    def __init__(self) -> None:
        self.sesiones: list[SesionFalsa] = []

    def __call__(self) -> SesionFalsa:
        self.sesiones.append(SesionFalsa())
        return self.sesiones[-1]


@pytest.fixture
def parada(monkeypatch) -> rag_worker.Parada:
    """A stop flag whose sleep is recorded instead of slept."""
    flag = rag_worker.Parada()
    siestas: list[float] = []

    def _dormir(segundos: float) -> None:
        siestas.append(segundos)

    monkeypatch.setattr(flag, "dormir", _dormir)
    flag.siestas = siestas  # type: ignore[attr-defined]
    return flag


def _item(estado: str = "respuesta") -> SimpleNamespace:
    return SimpleNamespace(id="00000000-0000-0000-0000-000000000001", estado=estado)


class TestUnaPasadaProcesa:
    def test_procesa_N_items_y_commitea_UNO_por_item(self, parada):
        """One transaction per item, committed per item.

        Per item and not per batch: `procesar_uno` deliberately does not commit,
        so a worker that dies mid-item releases its claim — and an item that
        DID finish must be durable even if the next one crashes the process.
        """
        fabrica = Fabrica()
        pendientes = [_item(), _item(), _item()]

        def _procesar(_sesion):
            return pendientes.pop(0) if pendientes else parada.pedir()

        assert rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=5.0) == 3
        assert len(fabrica.sesiones) == 4  # three items plus the pass that stopped
        assert [s.eventos for s in fabrica.sesiones[:3]] == [["commit", "close"]] * 3

    def test_max_items_frena_sin_una_pasada_extra(self, parada):
        """The supervised one-shot drain. It stops ON the Nth item, not after
        polling once more — a poll after the last item is a claim nobody wanted."""
        fabrica = Fabrica()
        llamadas: list[int] = []

        def _procesar(_sesion):
            llamadas.append(1)
            return _item()

        assert (
            rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=5.0, max_items=2) == 2
        )
        assert len(llamadas) == 2


class TestLaColaVaciaDuerme:
    def test_sin_items_duerme_el_intervalo_y_no_commitea(self, parada):
        """Nothing was claimed, so there is nothing to commit — and a commit here
        would be a write on every idle poll forever."""
        fabrica = Fabrica()
        vueltas = []

        def _procesar(_sesion):
            vueltas.append(1)
            if len(vueltas) >= 3:
                parada.pedir()
            return None

        assert rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=7.5) == 0
        assert parada.siestas == [7.5, 7.5, 7.5]
        assert all(s.eventos == ["rollback", "close"] for s in fabrica.sesiones)


class TestLaSenalCorta:
    def test_la_parada_se_lee_ENTRE_items_y_el_bucle_sale_limpio(self, parada):
        fabrica = Fabrica()
        procesados = []

        def _procesar(_sesion):
            procesados.append(1)
            parada.pedir(signal.SIGTERM)
            return _item()

        assert rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=5.0) == 1
        assert len(procesados) == 1
        assert parada.senal == signal.SIGTERM

    def test_una_parada_ya_pedida_no_reclama_NADA(self, parada):
        """A SIGTERM that arrives while the previous item was committing must not
        start another one."""
        fabrica = Fabrica()
        parada.pedir(signal.SIGINT)

        def _procesar(_sesion):  # pragma: no cover - must never run
            raise AssertionError("the loop claimed an item after being asked to stop")

        assert rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=5.0) == 0
        assert fabrica.sesiones == []

    def test_dormir_despierta_apenas_se_pide_la_parada(self):
        """The real `dormir`, not the recorder: a worker polling every 5 s must
        not take up to 5 s to notice a SIGTERM, which is what a bare
        `time.sleep` would do."""
        flag = rag_worker.Parada()
        flag.pedir(signal.SIGTERM)
        import time

        inicio = time.monotonic()
        flag.dormir(30.0)
        assert time.monotonic() - inicio < 1.0

    def test_el_handler_solo_marca_la_bandera(self, monkeypatch):
        """Registered, and setting the flag rather than raising: the item in
        flight owns its own transaction and aborting it from a signal handler
        would be a rollback in the middle of a `flush`."""
        flag = rag_worker.Parada()
        registrados: dict[int, object] = {}
        monkeypatch.setattr(
            signal, "signal", lambda numero, handler: registrados.__setitem__(numero, handler)
        )
        rag_worker.instalar_senales(flag)
        assert set(registrados) == {signal.SIGTERM, signal.SIGINT}
        registrados[signal.SIGTERM](signal.SIGTERM, None)
        assert flag.pedida() and flag.senal == signal.SIGTERM


class TestLosRefusalesDeDespliegueNoMatanAlWorker:
    """The items are fine; the deployment is not.

    Failing an item on any of these would tell a CD member their question could
    not be answered about a box that never tried — and the operator can fix the
    terms record or the credential without losing a single queued question.
    """

    @pytest.mark.parametrize(
        "refusal",
        [
            TerminosNoVerificados("the record is marked unverified"),
            ProveedorMalConfigurado("conocimiento_proveedor_api_key is empty"),
            RerankerNoDisponible("no CUDA device is available"),
            trabajador.RerankerSintetico("a synthetic ranker"),
        ],
    )
    def test_se_loguea_se_duerme_y_se_sigue_puliendo(self, parada, refusal, caplog):
        fabrica = Fabrica()
        vueltas = []

        def _procesar(_sesion):
            vueltas.append(1)
            if len(vueltas) >= 2:
                parada.pedir()
            raise refusal

        with caplog.at_level("ERROR"):
            assert rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=3.0) == 0
        assert len(vueltas) == 2, "the loop gave up on a refusal that was not the items' fault"
        assert parada.siestas == [3.0, 3.0]
        assert all(s.eventos == ["rollback", "close"] for s in fabrica.sesiones)
        assert type(refusal).__name__ in caplog.text

    def test_una_excepcion_SIN_NOMBRE_propaga_y_no_se_traga(self, parada):
        """A loop that swallows bugs is a worker that reports itself alive while
        processing nothing. The session is still rolled back on the way out, so
        the claimed item goes back to `pendiente` rather than being held by a
        poisoned transaction.
        """
        fabrica = Fabrica()

        def _procesar(_sesion):
            raise KeyError("bug")

        with pytest.raises(KeyError):
            rag_worker.bucle(fabrica, _procesar, parada=parada, intervalo_s=5.0)
        assert fabrica.sesiones[0].eventos == ["rollback", "close"]


class TestLaCLI:
    def test_sin_database_url_es_exit_2_y_no_un_traceback(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert rag_worker.main([]) == 2
        assert "--database-url" in capsys.readouterr().err

    def test_sin_reranker_NO_arranca_y_no_cae_a_CPU(self, monkeypatch, capsys):
        """The design authorises no CPU fallback and no smaller model: a 98.9 s
        rerank is an outage that answers, not a degraded mode."""
        monkeypatch.setattr(
            rag_worker,
            "construir_reranker",
            lambda: (_ for _ in ()).throw(RerankerNoDisponible("no CUDA device is available")),
        )
        assert rag_worker.main(["--database-url", "postgresql://x/y"]) == 1
        assert "WORKER NOT STARTED" in capsys.readouterr().err

    def test_sin_torch_es_exit_2_porque_es_el_interprete_equivocado(self, monkeypatch, capsys):
        """`venv` versus `venv-rag` is usage, not an outage — the operator has to
        change the command, not the box."""
        monkeypatch.setattr(
            rag_worker,
            "construir_reranker",
            lambda: (_ for _ in ()).throw(
                RerankerNoDisponible("torch/transformers are not installed in this environment")
            ),
        )
        assert rag_worker.main(["--database-url", "postgresql://x/y"]) == 2

    def test_los_terminos_SIN_VERIFICAR_frenan_el_arranque(self, monkeypatch, capsys):
        """The gate at boot, before a 2 GB reranker and 49 embeddings are spent
        on a route the owner has not authorised."""
        monkeypatch.setattr(rag_worker, "construir_reranker", lambda: object())
        monkeypatch.setattr(
            rag_worker.trabajador,
            "verificar_terminos_vigentes",
            lambda: (_ for _ in ()).throw(TerminosNoVerificados("unverified")),
        )
        monkeypatch.setattr(
            rag_worker,
            "conectar_sidecar",
            lambda *_a, **_k: _SidecarNulo(),
        )
        assert rag_worker.main(["--database-url", "postgresql://x/y"]) == 1
        assert "TerminosNoVerificados" in capsys.readouterr().err


class _SidecarNulo:
    model_id = "falso"

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


# ---------------------------------------------------------------------------
# The wedge scenario (audit RAG-5), against real Postgres and the real loop
# ---------------------------------------------------------------------------


class TestElItemVenenosoNoWedgeaLaCola:
    """RED→GREEN for RAG-5: an unnamed exception on the OLDEST item used to
    crash-loop the worker on that same item forever (`Restart=always` + a claim
    that writes no intermediate state). With the accountant wired into `bucle`,
    the third crash terminalizes the item and the NEXT claim moves the queue.

    Committed rows and explicit cleanup, like `test_buzon`'s SKIP LOCKED test:
    the accountant writes from a SEPARATE committed transaction, which the
    shared `db` fixture's never-committed outer transaction can never show it.
    """

    def _sembrar(self, test_engine, monkeypatch):
        """A unique snapshot + a poison item (oldest) + a healthy one."""
        import uuid as _uuid

        from sqlalchemy import text
        from sqlalchemy.orm import Session

        from app.domains.conocimiento import service
        from tests.new.conocimiento.test_trabajador import _resultado_con_un_hit

        marca = f"rag5-{_uuid.uuid4().hex[:8]}"
        sha = (_uuid.uuid4().hex + _uuid.uuid4().hex)[:40]
        sembrador = Session(bind=test_engine)
        try:
            sembrador.execute(
                text(
                    "INSERT INTO rag_corpus (corpus_sha, repo_url, manifest_version, "
                    "articulos_declarados, activo) VALUES (:sha, 'u', '2', 1, true)"
                ),
                {"sha": sha},
            )
            sembrador.execute(
                text(
                    "INSERT INTO rag_documento (corpus_sha, documento_id, tipo, es_secundaria, "
                    "jurisdiccion, estado_vigencia, clasificacion) VALUES "
                    "(:sha, 'ley-9750', 'ley-provincial', false, 'provincial', 'vigente', 'publico')"
                ),
                {"sha": sha},
            )
            sembrador.execute(
                text(
                    "INSERT INTO rag_unidad (corpus_sha, citation_key, documento_id, tipo_chunk, "
                    "texto, texto_indexado, source_file, source_offset) VALUES "
                    "(:sha, 'ley-9750#art1', 'ley-9750', 'articulo', :t, :t, 'f.md', 0)"
                ),
                {"sha": sha, "t": "El consorcio administra la red de canales."},
            )
            veneno, sana = f"{marca}-veneno", f"{marca}-sana"
            for pregunta in (veneno, sana):
                sembrador.execute(
                    text("INSERT INTO rag_consulta (id, pregunta) VALUES (gen_random_uuid(), :p)"),
                    {"p": pregunta},
                )
            sembrador.execute(
                text(
                    "UPDATE rag_consulta SET creada_en = now() - interval '1 hour' "
                    "WHERE pregunta = :p"
                ),
                {"p": veneno},
            )
            sembrador.commit()
        finally:
            sembrador.close()

        def _recuperar(_db, _sha, pregunta, **_kw):
            if "veneno" in pregunta:
                raise KeyError("bug")
            return _resultado_con_un_hit()

        monkeypatch.setattr(service, "recuperar", _recuperar)
        return marca, sha, veneno, sana

    def _limpiar(self, test_engine, marca: str, sha: str) -> None:
        from sqlalchemy import text
        from sqlalchemy.orm import Session

        sesion = Session(bind=test_engine)
        try:
            sesion.execute(
                text("DELETE FROM rag_consulta WHERE pregunta LIKE :patron"),
                {"patron": f"{marca}-%"},
            )
            sesion.execute(
                text("DELETE FROM rag_decision_ruta WHERE pregunta LIKE :patron"),
                {"patron": f"{marca}-%"},
            )
            sesion.execute(text("DELETE FROM rag_unidad WHERE corpus_sha = :sha"), {"sha": sha})
            sesion.execute(text("DELETE FROM rag_documento WHERE corpus_sha = :sha"), {"sha": sha})
            sesion.execute(text("DELETE FROM rag_corpus WHERE corpus_sha = :sha"), {"sha": sha})
            sesion.commit()
        finally:
            sesion.close()

    def test_la_tercera_caida_aparta_al_veneno_y_la_cola_avanza(
        self, test_engine, monkeypatch, caplog
    ):
        from sqlalchemy import text
        from sqlalchemy.orm import Session, sessionmaker

        from app.domains.conocimiento import buzon, routing, trabajador
        from app.domains.conocimiento.generacion import SalidaProveedor
        from tests.new.conocimiento.test_trabajador import (
            EmbedderFalso,
            GeneradorFalso,
            PARAMETROS,
            RerankerFalso,
            centroides_hacia,
            terminos_ok,
        )

        marca, sha, veneno, sana = self._sembrar(test_engine, monkeypatch)
        try:
            fabrica = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
            contador = rag_worker.ContadorDeCaidas(fabrica)
            parada = rag_worker.Parada()
            parada.dormir = lambda _s: None  # type: ignore[method-assign] — no sleeping
            generador = GeneradorFalso(
                SalidaProveedor(texto="Corresponde [ley-9750#art1].", truncado=False)
            )

            def _procesar(sesion):
                contador.nueva_vuelta()
                return trabajador.procesar_uno(
                    sesion,
                    corpus_sha=sha,
                    embedder=EmbedderFalso(),
                    centroides=centroides_hacia(routing.CLASE_LEGAL),
                    parametros=PARAMETROS,
                    reranker=RerankerFalso(),
                    crear_generador=lambda _p: generador,
                    verificar_terminos_fn=terminos_ok,
                    al_reclamar=contador.al_reclamar,
                )

            import logging

            with caplog.at_level(logging.ERROR, logger="conocimiento.worker"):
                # N crash/restart cycles: the bug propagates EVERY time — the
                # accountant caps the blast radius, it does not soften the crash.
                for ciclo in range(buzon.MAX_CAIDAS_WORKER):
                    with pytest.raises(KeyError, match="bug") as caida:
                        rag_worker.bucle(
                            fabrica,
                            _procesar,
                            parada=parada,
                            intervalo_s=0.01,
                            al_caer=contador.al_caer,
                        )
                    assert type(caida.value) is KeyError, (
                        f"ciclo {ciclo}: la caída dejó de propagar — los bugs son ruidosos"
                    )

                lector = Session(bind=test_engine)
                try:
                    fila = lector.execute(
                        text(
                            "SELECT estado, caidas_worker, respuesta FROM rag_consulta "
                            "WHERE pregunta = :p"
                        ),
                        {"p": veneno},
                    ).one()
                finally:
                    lector.close()
                assert fila.estado == "generacion_fallida", (
                    f"tras {buzon.MAX_CAIDAS_WORKER} caídas el veneno sigue "
                    f"{fila.estado!r}: el worker seguiría reclamándolo para siempre"
                )
                assert fila.caidas_worker == buzon.MAX_CAIDAS_WORKER
                motivo = fila.respuesta["motivo"]
                assert f"{buzon.MAX_CAIDAS_WORKER} caídas" in motivo
                assert "KeyError" in motivo

                # The terminalization itself is loud and names the item.
                assert "item_envenenado" in caplog.text

            # The restart systemd would perform: the queue must MOVE now.
            procesados = rag_worker.bucle(
                fabrica,
                _procesar,
                parada=parada,
                intervalo_s=0.01,
                max_items=1,
                al_caer=contador.al_caer,
            )
            assert procesados == 1, "el worker siguió reclamando al veneno apartado"

            lector = Session(bind=test_engine)
            try:
                sana_fila = lector.execute(
                    text("SELECT estado, caidas_worker FROM rag_consulta WHERE pregunta = :p"),
                    {"p": sana},
                ).one()
                pendientes = lector.execute(
                    text(
                        "SELECT count(*) FROM rag_consulta WHERE pregunta LIKE :patron "
                        "AND estado = 'pendiente'"
                    ),
                    {"patron": f"{marca}-%"},
                ).scalar_one()
                pendiente_libre = buzon.reclamar_pendiente(lector)
            finally:
                lector.rollback()
                lector.close()
            assert sana_fila.estado == "respuesta"
            assert sana_fila.caidas_worker == 0
            assert pendientes == 0 and pendiente_libre is None, (
                "quedó algo reclamable del lote: la cola no terminó de avanzar"
            )
        finally:
            self._limpiar(test_engine, marca, sha)
