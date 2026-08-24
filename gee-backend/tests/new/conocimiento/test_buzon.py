"""The mailbox queue: enqueue, claim, terminal writes, staleness, retention (U7).

Real Postgres throughout. Two of the claims under test are properties of the
DATABASE and not of Python — the six-state CHECK and `FOR UPDATE SKIP LOCKED` —
and a SQLite-shaped test would report both as passing while enforcing neither.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domains.conocimiento import buzon, repository
from app.domains.conocimiento.models import RagConsulta
from app.domains.conocimiento.schemas import CitaRecuperada, Redireccion, RespuestaConocimiento


def _usuario(db) -> uuid.UUID:
    """A real `users` row — `rag_consulta.usuario_id` is a real FK.

    The FK is the point: without it a typo'd requester id would silently create
    an item nobody can ever list, which is a queued question that will be
    processed, billed and delivered to nobody.
    """
    from app.auth.models import User, UserRole

    usuario = User(
        email=f"cd-{uuid.uuid4().hex[:10]}@test.com",
        hashed_password="fakehash",
        nombre="Comisión",
        apellido="Directiva",
        role=UserRole.ADMIN,
    )
    db.add(usuario)
    db.flush()
    return usuario.id


def _cita(clave: str = "ley-9750#art1") -> CitaRecuperada:
    return CitaRecuperada(
        citation_key=clave,
        documento_id="ley-9750",
        texto="El consorcio administra la red.",
        epigrafe="Objeto",
        tipo_chunk="articulo",
        tipo="ley",
        fuente_url="https://example.test/ley-9750",
        estado_vigencia="vigente",
        es_secundaria=False,
        jurisdiccion="cordoba",
        source_file="ley-9750.md",
        source_offset=0,
    )


class TestEncolar:
    def test_un_item_nace_pendiente_sin_respuesta_y_sin_procesada_en(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="  ¿Qué dice la ley 9750?  ")
        assert item.estado == "pendiente"
        assert item.respuesta is None
        assert item.procesada_en is None
        # Stripped, not stored raw: the surface echoes this text back and a
        # question with leading whitespace is the same question.
        assert item.pregunta == "¿Qué dice la ley 9750?"

    def test_una_pregunta_vacia_se_rechaza_antes_de_ocupar_la_cola(self, db):
        for vacia in ("", "   ", "\n\t"):
            with pytest.raises(buzon.PreguntaInvalida):
                buzon.encolar(db, usuario_id=None, pregunta=vacia)

    def test_una_pregunta_sobre_el_techo_se_rechaza_y_NO_se_trunca(self, db):
        larga = "a" * (buzon.PREGUNTA_MAX_CHARS + 1)
        with pytest.raises(buzon.PreguntaInvalida) as exc:
            buzon.encolar(db, usuario_id=None, pregunta=larga)
        # The refusal is the point: a truncated legal question is a DIFFERENT
        # question, and the answer would be certified against text nobody wrote.
        assert "truncated" in str(exc.value)
        assert db.query(RagConsulta).count() == 0


class TestLaBaseRechazaEstadosIlegales:
    """The CHECKs, exercised against real Postgres. Mutation targets."""

    def test_un_estado_fuera_de_la_union_no_persiste(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE rag_consulta SET estado = 'casi_respuesta' WHERE id = :id"),
                {"id": item.id},
            )
        db.rollback()

    def test_un_terminal_sin_payload_no_persiste(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "UPDATE rag_consulta SET estado = 'abstencion', procesada_en = now() "
                    "WHERE id = :id"
                ),
                {"id": item.id},
            )
        db.rollback()

    def test_un_pendiente_con_payload_no_persiste(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE rag_consulta SET respuesta = '{}'::jsonb WHERE id = :id"),
                {"id": item.id},
            )
        db.rollback()

    def test_un_terminal_sin_procesada_en_no_persiste(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "UPDATE rag_consulta SET estado = 'abstencion', "
                    'respuesta = \'{"estado": "abstencion"}\'::jsonb WHERE id = :id'
                ),
                {"id": item.id},
            )
        db.rollback()


class TestPersistirResultado:
    def test_una_respuesta_aterriza_con_estado_payload_y_marca_de_tiempo(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        ahora = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=datetime.timezone.utc)
        buzon.persistir_resultado(
            db,
            item,
            RespuestaConocimiento(
                estado="respuesta",
                respuesta="Corresponde [ley-9750#art1].",
                citas=[_cita()],
            ),
            ahora=ahora,
        )
        db.refresh(item)
        assert item.estado == "respuesta"
        assert item.procesada_en == ahora
        assert item.respuesta["estado"] == "respuesta"
        assert item.respuesta["citas"][0]["citation_key"] == "ley-9750#art1"

    def test_un_worker_no_puede_escribir_pendiente_como_RESULTADO(self, db):
        """`pendiente` is the state an item is BORN in, never one a run decides."""
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        with pytest.raises(buzon.EstadoIncoherente):
            buzon.persistir_resultado(db, item, RespuestaConocimiento(estado="pendiente"))

    def test_un_item_ya_terminal_no_se_sobreescribe(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        buzon.persistir_resultado(db, item, RespuestaConocimiento(estado="abstencion"))
        with pytest.raises(buzon.EstadoIncoherente):
            buzon.persistir_resultado(db, item, RespuestaConocimiento(estado="generacion_fallida"))

    def test_una_redireccion_pura_lleva_su_superficie_hasta_el_payload(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="¿cómo pago la cuota?")
        buzon.persistir_resultado(
            db,
            item,
            RespuestaConocimiento(
                estado="redireccion",
                redireccion=Redireccion(superficie="/finanzas", motivo="regla"),
            ),
        )
        db.refresh(item)
        assert item.respuesta["redireccion"]["superficie"] == "/finanzas"
        # A pure redirect that names no surface is the refusal it exists to avoid.
        assert item.respuesta["redireccion_parcial"] is None


class TestReclamar:
    def test_reclama_el_mas_viejo_primero(self, db):
        primero = buzon.encolar(db, usuario_id=None, pregunta="primera")
        db.execute(
            text("UPDATE rag_consulta SET creada_en = now() - interval '1 hour' WHERE id = :id"),
            {"id": primero.id},
        )
        buzon.encolar(db, usuario_id=None, pregunta="segunda")
        db.expire_all()
        assert buzon.reclamar_pendiente(db).pregunta == "primera"

    def test_no_reclama_items_terminales(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        buzon.persistir_resultado(db, item, RespuestaConocimiento(estado="abstencion"))
        assert buzon.reclamar_pendiente(db) is None

    def test_el_item_reclamado_SIGUE_pendiente(self, db):
        """No intermediate state exists, so no worker death can orphan one.

        This is the whole difference from the `geo_jobs` claim, whose committed
        `RUNNING` needs `geo/reconciliation.py` to terminalize the rows a lost
        worker left behind. Here the claim is a row LOCK: an aborted transaction
        releases it and the item is exactly where it was.
        """
        item = buzon.encolar(db, usuario_id=None, pregunta="p")
        reclamado = buzon.reclamar_pendiente(db)
        assert reclamado.id == item.id
        assert reclamado.estado == "pendiente"

    def test_dos_trabajadores_no_toman_el_mismo_item(self, test_engine):
        """`SKIP LOCKED`, against real Postgres and two real connections.

        Committed rows and explicit cleanup: the shared `db` fixture is ONE
        transaction, and a lock cannot be observed from inside the transaction
        that holds it.

        `lock_timeout` on the second session is not decoration. Without `SKIP
        LOCKED` the second claim BLOCKS instead of failing, so a regression would
        hang this test — and a suite that hangs is a suite nobody can read a
        result from. With the timeout, dropping `SKIP LOCKED` raises inside two
        seconds and the assertion below is reachable either way.
        """
        from sqlalchemy.orm import Session

        marca = f"skip-locked-{uuid.uuid4().hex[:8]}"
        sembrador = Session(bind=test_engine)
        try:
            for _ in range(2):
                buzon.encolar(db=sembrador, usuario_id=None, pregunta=marca)
            sembrador.commit()

            a, b = Session(bind=test_engine), Session(bind=test_engine)
            try:
                primero = buzon.reclamar_pendiente(a)
                b.execute(text("SET LOCAL lock_timeout = '2s'"))
                segundo = buzon.reclamar_pendiente(b)
                assert primero is not None and segundo is not None
                assert primero.id != segundo.id, (
                    "two workers claimed the same item: SKIP LOCKED is not doing "
                    "its job and the question would be answered (and billed) twice"
                )
            finally:
                a.rollback()
                a.close()
                b.rollback()
                b.close()
        finally:
            sembrador.query(RagConsulta).filter(RagConsulta.pregunta == marca).delete()
            sembrador.commit()
            sembrador.close()


class TestAlcanceDelDueno:
    def test_un_item_de_otro_usuario_no_se_lee(self, db):
        mio, ajeno = _usuario(db), _usuario(db)
        item = buzon.encolar(db, usuario_id=ajeno, pregunta="pregunta ajena")
        assert buzon.obtener(db, item.id, usuario_id=mio) is None
        assert buzon.obtener(db, item.id, usuario_id=ajeno) is not None

    def test_el_listado_solo_devuelve_lo_propio(self, db):
        mio, ajeno = _usuario(db), _usuario(db)
        buzon.encolar(db, usuario_id=mio, pregunta="mía")
        buzon.encolar(db, usuario_id=ajeno, pregunta="ajena")
        preguntas = [fila.pregunta for fila in buzon.listar(db, usuario_id=mio)]
        assert preguntas == ["mía"]


class TestDiagnostico:
    def test_profundidad_cuenta_solo_pendientes(self, db):
        a = buzon.encolar(db, usuario_id=None, pregunta="a")
        buzon.encolar(db, usuario_id=None, pregunta="b")
        assert buzon.profundidad(db) == 2
        buzon.persistir_resultado(db, a, RespuestaConocimiento(estado="abstencion"))
        assert buzon.profundidad(db) == 1

    def test_ultima_corrida_es_none_hasta_que_algo_se_procesa(self, db):
        buzon.encolar(db, usuario_id=None, pregunta="a")
        assert buzon.ultima_corrida(db) is None

    def test_ultima_corrida_lee_el_procesado_mas_reciente(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="a")
        ahora = datetime.datetime(2026, 8, 24, 9, 30, tzinfo=datetime.timezone.utc)
        buzon.persistir_resultado(db, item, RespuestaConocimiento(estado="abstencion"), ahora=ahora)
        assert buzon.ultima_corrida(db) == ahora

    def test_mas_antiguo_pendiente_ignora_terminales(self, db):
        item = buzon.encolar(db, usuario_id=None, pregunta="a")
        buzon.persistir_resultado(db, item, RespuestaConocimiento(estado="abstencion"))
        assert buzon.mas_antiguo_pendiente(db) is None


class TestDemora:
    """A3: "Pendiente" is only honest while it is true."""

    def _item(self, edad_s: float, estado: str = "pendiente") -> RagConsulta:
        ahora = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=datetime.timezone.utc)
        return RagConsulta(
            pregunta="p",
            estado=estado,
            creada_en=ahora - datetime.timedelta(seconds=edad_s),
        )

    AHORA = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=datetime.timezone.utc)

    def test_un_pendiente_reciente_no_esta_demorado(self):
        assert not buzon.esta_demorado(self._item(10), ventana_s=900, ahora=self.AHORA)

    def test_un_pendiente_pasado_la_ventana_si(self):
        assert buzon.esta_demorado(self._item(901), ventana_s=900, ahora=self.AHORA)

    def test_el_borde_exacto_NO_esta_demorado(self):
        """Strictly greater, and the boundary is nailed down on the honest side."""
        assert not buzon.esta_demorado(self._item(900), ventana_s=900, ahora=self.AHORA)

    def test_un_terminal_nunca_esta_demorado(self):
        """A finished item is finished; a warning next to an answer that arrived
        would teach the reader to ignore the warning."""
        assert not buzon.esta_demorado(
            self._item(99999, estado="respuesta"), ventana_s=900, ahora=self.AHORA
        )

    def test_una_ventana_sin_configurar_no_marca_todo_como_demorado(self):
        assert not buzon.esta_demorado(self._item(99999), ventana_s=0, ahora=self.AHORA)


class TestRetencion:
    """The mailbox stores the verbatim question, so it carries the same window."""

    def test_purga_por_edad_de_SUBMISION_y_respeta_el_borde(self, db):
        ahora = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=datetime.timezone.utc)
        viejo = buzon.encolar(db, usuario_id=None, pregunta="vieja")
        borde = buzon.encolar(db, usuario_id=None, pregunta="borde")
        db.execute(
            text("UPDATE rag_consulta SET creada_en = :t WHERE id = :id"),
            {"t": ahora - datetime.timedelta(days=91), "id": viejo.id},
        )
        db.execute(
            text("UPDATE rag_consulta SET creada_en = :t WHERE id = :id"),
            {"t": ahora - datetime.timedelta(days=90), "id": borde.id},
        )
        db.expire_all()
        assert repository.purgar_consultas(db, ahora=ahora) == 1
        assert [f.pregunta for f in db.query(RagConsulta).all()] == ["borde"]

    def test_un_pendiente_viejo_TAMBIEN_se_purga(self, db):
        """Keyed on submission, not on processing: an item nobody ever processed
        is exactly the one whose question has been sitting around longest."""
        ahora = datetime.datetime(2026, 8, 24, 12, 0, tzinfo=datetime.timezone.utc)
        item = buzon.encolar(db, usuario_id=None, pregunta="nunca procesada")
        db.execute(
            text("UPDATE rag_consulta SET creada_en = :t WHERE id = :id"),
            {"t": ahora - datetime.timedelta(days=200), "id": item.id},
        )
        db.expire_all()
        assert repository.purgar_consultas(db, ahora=ahora) == 1

    def test_un_ahora_naive_se_rechaza(self, db):
        with pytest.raises(ValueError):
            repository.purgar_consultas(db, ahora=datetime.datetime(2026, 8, 24, 12, 0))


# ---------------------------------------------------------------------------
# The MIGRATION, on a throwaway real Postgres (U7)
# ---------------------------------------------------------------------------

# `Base.metadata.create_all()` proves the ORM agrees with itself. Only the
# migration proves a DEPLOY gets the same table, and the classes above assert the
# CHECKs against the create_all shape — so without this they would pass while the
# deployed database enforced nothing.
from tests.new.conocimiento.test_rag_migrations import throwaway_db  # noqa: E402, F401

_HEAD_U7 = "conocimiento_007"


class TestMigracionBuzon:
    def test_upgrade_crea_la_tabla_con_sus_checks_y_sus_indices(self, throwaway_db):  # noqa: F811
        from alembic import command
        from sqlalchemy import inspect

        cfg, engine = throwaway_db
        command.upgrade(cfg, _HEAD_U7)

        inspector = inspect(engine)
        assert "rag_consulta" in inspector.get_table_names()
        assert {col["name"] for col in inspector.get_columns("rag_consulta")} == {
            "id",
            "usuario_id",
            "pregunta",
            "estado",
            "decision_ruta_id",
            "respuesta",
            "creada_en",
            "procesada_en",
        }, "the migration and models.py must declare the same shape"

        indices = {indice["name"] for indice in inspector.get_indexes("rag_consulta")}
        assert "ix_rag_consulta_pendientes" in indices, (
            "the claim scan reads pending rows oldest-first on every worker tick; "
            "without the index it seq-scans the whole mailbox"
        )
        assert "ix_rag_consulta_usuario" in indices

    @pytest.mark.parametrize(
        ("sql", "restriccion"),
        [
            (
                "INSERT INTO rag_consulta (id, pregunta, estado) "
                "VALUES (gen_random_uuid(), 'p', 'casi_respuesta')",
                "ck_rag_consulta_estado",
            ),
            (
                "INSERT INTO rag_consulta (id, pregunta, estado, procesada_en) "
                "VALUES (gen_random_uuid(), 'p', 'abstencion', now())",
                "ck_rag_consulta_payload_iff_terminal",
            ),
            (
                "INSERT INTO rag_consulta (id, pregunta, estado, respuesta) "
                "VALUES (gen_random_uuid(), 'p', 'pendiente', '{}'::jsonb)",
                "ck_rag_consulta_payload_iff_terminal",
            ),
            (
                "INSERT INTO rag_consulta (id, pregunta, estado, respuesta) VALUES "
                "(gen_random_uuid(), 'p', 'abstencion', '{\"estado\":\"abstencion\"}'::jsonb)",
                "ck_rag_consulta_procesada_iff_terminal",
            ),
        ],
    )
    def test_la_base_DESPLEGADA_rechaza_los_estados_ilegales(
        self,
        throwaway_db,  # noqa: F811
        sql,
        restriccion,
    ):
        from alembic import command
        from sqlalchemy import text

        cfg, engine = throwaway_db
        command.upgrade(cfg, _HEAD_U7)

        with pytest.raises(Exception) as fallo:
            with engine.begin() as conn:
                conn.execute(text(sql))
        assert restriccion in str(fallo.value)

    def test_el_downgrade_deja_el_arbol_como_estaba(self, throwaway_db):  # noqa: F811
        from alembic import command
        from sqlalchemy import inspect

        cfg, engine = throwaway_db
        command.upgrade(cfg, _HEAD_U7)
        command.downgrade(cfg, "conocimiento_006")
        assert "rag_consulta" not in inspect(engine).get_table_names()
        # The routing record SURVIVES: the two tables are joined by a nullable FK
        # and dropping the mailbox must not take the decision log with it.
        assert "rag_decision_ruta" in inspect(engine).get_table_names()
