"""Question routing: stage-1 lexicon, stage-2 centroid, `mixto`, refusals (U4).

Written RED-first against `openspec/changes/consorcio-conocimiento-semantico`:
the `knowledge-question-routing` spec supplies the acceptance criteria and
design.md G1 (:130-202) constrains the shape.

Three properties this file exists to pin down, because each one is a way the
router could look correct and be dangerous:

1. **An `operational` question makes zero retrieval calls.** Not "returns a
   redirect and also happens to have queried" — the spy counts calls, so a
   future refactor that classifies *after* retrieving fails here rather than in
   production, where the cost is a legal-corpus answer about a real person.
2. **`mixto` is reachable.** A bare `margen < umbral -> redirect` rule makes it
   unreachable by construction (design.md:162-170), and the symptom is not an
   error — it is a class that silently never fires.
3. **A down sidecar is never a classification.** `no_disponible`, never a
   redirect and never an abstention (design.md:198-202).

No test here asserts a numeric BAR. The bar is unratified (tasks.md 0.3,
design.md A4) and `evaluar_barra` is asserted to refuse a verdict rather than to
issue one.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

import pytest

from app.domains.conocimiento import routing
from app.domains.conocimiento.embed_sidecar import CAUSA_NO_LISTO, SidecarNoDisponible

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class EmbedderFalso:
    """Deterministic, synthetic, and LOUD about it (`sintetico = True`).

    Vectors are hash-derived, so nothing measured through this double is a
    quality claim about BGE-M3 — it exercises plumbing and arithmetic only. The
    tests that need *geometry* build their vectors explicitly instead
    (`EmbedderDirigido`), because hash noise has no class structure at all.
    """

    model_id = "test/fake-router"
    revision = None
    sintetico = True
    #: Three, matching `EJE` — a fake whose width disagrees with the centroids
    #: would exercise the dimension refusal instead of the routing rules.
    dims = 3
    token_ceiling = 8192

    def __init__(self) -> None:
        self.llamadas: list[tuple[str, ...]] = []

    def count_tokens(self, texto: str) -> int:  # pragma: no cover - not a query concern
        raise NotImplementedError

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        self.llamadas.append(tuple(textos))
        vectores = []
        for texto in textos:
            crudo = hashlib.sha256(texto.encode("utf-8")).digest()[: self.dims]
            valores = [byte / 255.0 - 0.5 for byte in crudo]
            norma = sum(v * v for v in valores) ** 0.5
            vectores.append([v / norma for v in valores])
        return vectores


class EmbedderDirigido(EmbedderFalso):
    """Returns the vector the test asked for, so geometry is stated not hoped."""

    def __init__(self, mapa: dict[str, Sequence[float]]) -> None:
        super().__init__()
        self._mapa = mapa
        self.dims = len(next(iter(mapa.values())))

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        self.llamadas.append(tuple(textos))
        return [[float(v) for v in self._mapa[texto]] for texto in textos]


class EmbedderCaido(EmbedderFalso):
    """The sidecar is down. Every `encode` is a named refusal."""

    def encode(self, textos: Sequence[str]) -> list[list[float]]:
        raise SidecarNoDisponible(CAUSA_NO_LISTO, "the model is still loading")


class EspiaRecuperacion:
    """Counts retrieval calls. Its whole job is to still be at zero.

    Installed OVER `service.recuperar`, not passed in as a parameter. A
    parameter the production caller never supplies proves nothing; replacing the
    real symbol means a future `routing.py` that reaches for retrieval — by any
    import path that resolves through the module — is caught here.
    """

    def __init__(self) -> None:
        self.llamadas = 0

    def __call__(self, *args, **kwargs):  # pragma: no cover - must never run
        self.llamadas += 1
        raise AssertionError("retrieval ran for a question that must never reach it")


@pytest.fixture
def espia_recuperacion(monkeypatch):
    from app.domains.conocimiento import service

    espia = EspiaRecuperacion()
    monkeypatch.setattr(service, "recuperar", espia)
    return espia


#: Three orthogonal axes, one per pure class. Cosine against these is then exact
#: arithmetic a reader can verify by hand rather than an opaque hash outcome.
EJE = {
    "legal": (1.0, 0.0, 0.0),
    "operational": (0.0, 1.0, 0.0),
    "geoespacial": (0.0, 0.0, 1.0),
}


def _centroides_de_ejes() -> routing.Centroides:
    return routing.Centroides({clase: tuple(vec) for clase, vec in EJE.items()})


# ---------------------------------------------------------------------------
# 4.1 — stage-1 deterministic lexicon
# ---------------------------------------------------------------------------


class TestEtapaUnoLexico:
    """`routing spec:22-27, 33-45` — markers that decide without a model."""

    @pytest.mark.parametrize(
        "pregunta, clase, superficie",
        [
            ("¿cuánto debe Juan Pérez?", "operational", "/finanzas"),
            ("¿cuál es el saldo de la cuota 2026?", "operational", "/finanzas"),
            ("¿en qué anda el trámite que presenté?", "operational", "/tramites"),
            ("¿me buscás el expediente 12/2026?", "operational", "/tramites"),
            ("quiero saber el estado de mi denuncia", "operational", "/denuncias"),
            ("¿por dónde pasa el canal N°5?", "geoespacial", "/mapa"),
            ("¿dónde queda la alcantarilla nueva?", "geoespacial", "/mapa"),
            ("¿qué hay en -31.4201, -62.0812?", "geoespacial", "/mapa"),
        ],
    )
    def test_marcador_decide_sin_modelo(self, pregunta, clase, superficie):
        embedder = EmbedderFalso()
        decision = routing.clasificar(
            pregunta,
            embedder=embedder,
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert decision.clase == clase
        assert decision.superficie == superficie
        assert decision.motivo == routing.MOTIVO_REGLA
        assert embedder.llamadas == [], (
            "a stage-1 decision must not embed: the sidecar hop is the expensive "
            "leg and a rule that already decided has nothing to ask it."
        )

    def test_un_marcador_legal_desactiva_la_etapa_uno(self):
        """A norm word next to a debt word is not a stage-1 redirect.

        This is the `mixto` doorway. `"cuota"` is a `/finanzas` marker, so a
        lexicon that fires on markers alone would redirect
        `routing spec:59` — the spec's own worked `mixto` example — and the class
        would be unreachable from the very question that defines it.
        """
        embedder = EmbedderFalso()
        decision = routing.clasificar(
            "¿qué dice la norma sobre la cuota y cuánto debo yo?",
            embedder=embedder,
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert decision.motivo != routing.MOTIVO_REGLA
        assert embedder.llamadas, "stage 2 must have run"

    def test_nombre_con_forma_de_padron_es_marcador_operativo(self):
        """`design.md:139` names it explicitly: a padrón-shaped person name."""
        assert routing.marcadores_etapa_uno("¿figura Juan Pérez en el padrón?")
        assert not routing.marcadores_etapa_uno(
            "¿qué establece la Ley Provincial de Aguas al respecto?"
        ), "a capitalized statute name is not a person"

    def test_el_lexico_es_insensible_a_tildes_y_mayusculas(self):
        """Real keyboards. Four items of the ratified set carry no accents."""
        sin_tilde = routing.clasificar(
            "cuanto DEBE Juan Perez",
            embedder=EmbedderFalso(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert sin_tilde.clase == "operational"
        assert sin_tilde.superficie == "/finanzas"

    def test_la_superficie_es_estable_entre_repeticiones(self):
        """`routing spec:47-51`."""
        pregunta = "¿cuánto debe Juan Pérez?"
        superficies = {
            routing.clasificar(
                pregunta,
                embedder=EmbedderFalso(),
                centroides=_centroides_de_ejes(),
                parametros=routing.PARAMETROS_SIN_CALIBRAR,
            ).superficie
            for _ in range(3)
        }
        assert superficies == {"/finanzas"}

    def test_toda_superficie_pertenece_al_conjunto_del_spec(self):
        """`routing spec:31` names four and only four."""
        assert set(routing.SUPERFICIES) == {"/tramites", "/finanzas", "/denuncias", "/mapa"}


# ---------------------------------------------------------------------------
# 4.2 — an operational question makes zero retrieval calls
# ---------------------------------------------------------------------------


class TestNadaDeRecuperacion:
    """`routing spec:13, 22-27` — the redirect is not "answer, then discard"."""

    def test_operational_no_hace_ni_una_llamada_de_recuperacion(self, espia_recuperacion):
        decision = routing.clasificar(
            "¿cuánto debe Juan Pérez?",
            embedder=EmbedderFalso(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert decision.clase == "operational"
        assert espia_recuperacion.llamadas == 0
        assert decision.superficie == "/finanzas"

    def test_geoespacial_tampoco(self, espia_recuperacion):
        decision = routing.clasificar(
            "¿por dónde pasa el canal N°5?",
            embedder=EmbedderFalso(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert decision.clase == "geoespacial"
        assert espia_recuperacion.llamadas == 0

    def test_una_pregunta_legal_tampoco_recupera_desde_el_router(self, espia_recuperacion):
        """Routing DECIDES; it does not retrieve. Wiring is U7's job."""
        decision = routing.clasificar(
            "¿qué procedimiento fija la norma para constituir un consorcio?",
            embedder=EmbedderDirigido(
                {"¿qué procedimiento fija la norma para constituir un consorcio?": (1.0, 0.0, 0.0)}
            ),
            centroides=_centroides_de_ejes(),
            parametros=routing.ParametrosRuta(0.20, 0.05, 0.30),
        )
        assert decision.clase == "legal"
        assert espia_recuperacion.llamadas == 0

    def test_la_decision_no_lleva_prosa_ni_citas(self):
        """`routing spec:38` — no answer, no figure, no citation."""
        decision = routing.clasificar(
            "¿cuánto debe Juan Pérez?",
            embedder=EmbedderFalso(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        campos = set(vars(decision))
        assert not campos & {"respuesta", "texto", "citas", "claves"}, (
            f"a routing decision carries no answer surface; found {campos}"
        )


# ---------------------------------------------------------------------------
# 4.3 — the `mixto` top-2 signature, and the doubt-redirect it is exempt from
# ---------------------------------------------------------------------------


class TestFirmaMixto:
    """`design.md:161-170`, `routing spec:53-70`."""

    def _decidir(self, vector, parametros=None, pregunta="pregunta de prueba"):
        return routing.clasificar(
            pregunta,
            embedder=EmbedderDirigido({pregunta: vector}),
            centroides=_centroides_de_ejes(),
            parametros=parametros or routing.ParametrosRuta(umbral=0.20, banda=0.10, piso=0.30),
        )

    def test_legal_mas_operational_dentro_de_banda_y_sobre_piso_es_mixto(self):
        # Equidistant from the legal and operational axes: margin 0, both
        # cosines 0.707 — inside the band and well clear of the floor. The
        # question is the spec's own worked example (routing spec:59), so the
        # partial redirect's surface is decided by the `cuota`/`debo` markers
        # rather than by the declared default.
        decision = self._decidir(
            (0.7071, 0.7071, 0.0),
            pregunta="¿qué dice la norma sobre la cuota y cuánto debo yo?",
        )
        assert decision.clase == "mixto"
        assert decision.motivo == routing.MOTIVO_MIXTO
        assert decision.superficie == "/finanzas"

    def test_mixto_sin_marcador_de_familia_cae_en_la_superficie_declarada(self):
        """routing spec:31 requires a surface even when the subject family is
        unresolved. The declared default is a redirect either way — never prose.
        """
        decision = self._decidir((0.7071, 0.7071, 0.0))
        assert decision.clase == "mixto"
        assert decision.superficie == routing.SUPERFICIE_OPERACIONAL_POR_DEFECTO
        assert decision.superficie in routing.SUPERFICIES

    def test_legal_mas_geoespacial_tambien_es_mixto(self):
        decision = self._decidir((0.7071, 0.0, 0.7071))
        assert decision.clase == "mixto"
        assert decision.superficie == "/mapa"

    def test_operational_mas_geoespacial_no_es_mixto(self):
        """`mixto` means *partly legal*. Without a legal leg there is nothing to
        answer, so the honest outcome is a plain redirect, not a split response.
        """
        decision = self._decidir((0.0, 0.7071, 0.7071))
        assert decision.clase != "mixto"
        assert decision.clase in ("operational", "geoespacial")

    def test_por_debajo_del_piso_no_es_mixto_aunque_el_margen_sea_chico(self):
        """Two weak, nearly equal scores are noise, not a mixed question.

        Note the third component: cosine ignores magnitude, so "weak" cannot be
        produced by a SHORT vector — `(0.05, 0.05, 0)` normalizes to the same
        0.707/0.707 as the canonical `mixto`. Weakness is a DIRECTION that
        points away from every class axis, which is what the large negative
        third component encodes here.
        """
        decision = self._decidir((0.2, 0.2, -0.9592), routing.ParametrosRuta(0.20, 0.10, 0.30))
        assert decision.puntajes["legal"] == pytest.approx(0.2, abs=1e-3)
        assert decision.clase != "mixto"
        assert decision.motivo == routing.MOTIVO_DUDA

    def test_la_magnitud_no_cambia_nada_la_direccion_lo_es_todo(self):
        """A scaled query must route identically: an un-normalized vector that
        moved the margin would make the floor depend on vector length."""
        largo = self._decidir((7.071, 7.071, 0.0))
        corto = self._decidir((0.07071, 0.07071, 0.0))
        assert largo.clase == corto.clase == "mixto"
        assert largo.margen == pytest.approx(corto.margen)

    def test_mixto_esta_exento_del_redirect_por_duda(self):
        """The whole point of :162-165: `mixto` margins are small BY DESIGN.

        Under a bare `margen < umbral -> redirect` rule this exact vector — the
        canonical `mixto` — becomes a redirect, and the class is unreachable.
        """
        parametros = routing.ParametrosRuta(umbral=0.90, banda=0.10, piso=0.30)
        decision = self._decidir((0.7071, 0.7071, 0.0), parametros)
        assert decision.margen is not None and decision.margen < parametros.umbral
        assert decision.clase == "mixto"

    def test_duda_que_no_tiene_la_forma_de_mixto_redirige(self):
        """`routing spec:72-81` — bias toward redirect under doubt."""
        parametros = routing.ParametrosRuta(umbral=0.50, banda=0.02, piso=0.30)
        decision = self._decidir((0.65, 0.60, 0.0), parametros)
        assert decision.motivo == routing.MOTIVO_DUDA
        assert decision.clase != "legal"
        assert decision.superficie in routing.SUPERFICIES

    def test_legal_confiado_pasa_a_recuperacion(self):
        parametros = routing.ParametrosRuta(umbral=0.20, banda=0.05, piso=0.30)
        decision = self._decidir((1.0, 0.0, 0.0), parametros)
        assert decision.clase == "legal"
        assert decision.motivo == routing.MOTIVO_CENTROIDE
        assert decision.superficie is None

    def test_una_pregunta_un_embedding(self):
        """`design.md:145-148`. Two vectors for one question is a state where
        the router classified one and retrieval searched another."""
        pregunta = "¿qué dice la norma sobre la cuota y cuánto debo yo?"
        embedder = EmbedderDirigido({pregunta: (0.7071, 0.7071, 0.0)})
        decision = routing.clasificar(
            pregunta,
            embedder=embedder,
            centroides=_centroides_de_ejes(),
            parametros=routing.ParametrosRuta(0.20, 0.10, 0.30),
        )
        assert embedder.llamadas == [(pregunta,)]
        assert decision.qvec == pytest.approx([0.7071, 0.7071, 0.0])


# ---------------------------------------------------------------------------
# 4.4 — a down sidecar is `no_disponible`, never a routing claim
# ---------------------------------------------------------------------------


class TestSidecarCaido:
    """`design.md:198-202`."""

    def test_sidecar_caido_propaga_la_negativa_nombrada(self):
        with pytest.raises(SidecarNoDisponible) as fallo:
            routing.clasificar(
                "¿qué procedimiento fija la norma para constituir un consorcio?",
                embedder=EmbedderCaido(),
                centroides=_centroides_de_ejes(),
                parametros=routing.PARAMETROS_SIN_CALIBRAR,
            )
        assert fallo.value.causa == CAUSA_NO_LISTO

    def test_no_degrada_a_redirect_ni_a_reglas(self):
        """A redirect is a CLASSIFICATION CLAIM. Making it because a container
        is down is a fabricated classification, not a graceful degradation."""
        with pytest.raises(SidecarNoDisponible):
            routing.clasificar(
                "¿qué dice el estatuto sobre las asambleas?",
                embedder=EmbedderCaido(),
                centroides=_centroides_de_ejes(),
                parametros=routing.PARAMETROS_SIN_CALIBRAR,
            )

    def test_una_pregunta_decidida_en_etapa_uno_no_necesita_el_sidecar(self):
        """Not a fallback: stage 1 never asked the sidecar anything."""
        decision = routing.clasificar(
            "¿cuánto debe Juan Pérez?",
            embedder=EmbedderCaido(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert decision.clase == "operational"
        assert decision.motivo == routing.MOTIVO_REGLA

    def test_un_embedder_sin_centroides_se_niega(self):
        """Centroids for a class that has no labeled items would be a zero
        vector, and cosine against zero is undefined — not 0.0."""
        with pytest.raises(routing.RouterNoCalibrado):
            routing.Centroides({"legal": (1.0, 0.0, 0.0)})


# ---------------------------------------------------------------------------
# 4.6 — the routing decision record
# ---------------------------------------------------------------------------


class TestRegistroDeDecisiones:
    """`design.md:188-196`, `routing spec:85, 94-98`.

    The record stores the question **verbatim**. A hash satisfies none of
    :94-98 — reconstructing a question from its hash is the thing hashes exist
    to prevent, and "a CD member reports that an operational question was
    answered" is unanswerable against a digest.

    That is not a privacy regression and does not touch the Privacy Boundary:
    the boundary governs what LEAVES the deployment, and this table is the box's
    own Postgres. The constraints that make it so are asserted here rather than
    assumed.
    """

    def _decision(self, pregunta="¿cuánto debe Juan Pérez?"):
        return routing.clasificar(
            pregunta,
            embedder=EmbedderFalso(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )

    def test_la_pregunta_se_guarda_textual(self, db):
        from app.domains.conocimiento import repository

        pregunta = "¿cuánto debe Juan Pérez?"
        fila_id = repository.registrar_decision_ruta(db, self._decision(pregunta))
        db.flush()

        guardadas = repository.listar_decisiones_ruta(db)
        assert [f.id for f in guardadas] == [fila_id]
        assert guardadas[0].pregunta == pregunta, "a hash satisfies none of routing spec:94-98"
        assert guardadas[0].clase == "operational"
        assert guardadas[0].superficie == "/finanzas"
        assert guardadas[0].motivo == routing.MOTIVO_REGLA

    def test_una_decision_de_etapa_dos_guarda_margen_y_umbral(self, db):
        from app.domains.conocimiento import repository

        pregunta = "¿qué dice la norma sobre la cuota y cuánto debo yo?"
        decision = routing.clasificar(
            pregunta,
            embedder=EmbedderDirigido({pregunta: (0.7071, 0.7071, 0.0)}),
            centroides=_centroides_de_ejes(),
            parametros=routing.ParametrosRuta(0.20, 0.10, 0.30),
        )
        repository.registrar_decision_ruta(db, decision)
        db.flush()

        fila = repository.listar_decisiones_ruta(db)[0]
        assert fila.clase == "mixto"
        assert fila.margen == pytest.approx(0.0, abs=1e-9)
        assert fila.umbral_vigente == pytest.approx(0.20)
        assert fila.decidida_en is not None

    def test_una_decision_por_regla_no_inventa_una_confianza(self, db):
        """`margen` and `umbral_vigente` stay NULL. A rule computed neither, and
        writing 0.0 there would put a confidence on a decision that has none."""
        from app.domains.conocimiento import repository

        repository.registrar_decision_ruta(db, self._decision())
        db.flush()

        fila = repository.listar_decisiones_ruta(db)[0]
        assert fila.margen is None
        assert fila.umbral_vigente is None

    def test_el_registro_no_guarda_el_vector_ni_ninguna_cita(self, db):
        """The record is `(pregunta, clase, margen, umbral_vigente, ts)` plus the
        surface and the motive. Not the embedding, not a retrieval payload."""
        from app.domains.conocimiento.models import RagDecisionRuta

        columnas = set(RagDecisionRuta.__table__.columns.keys())
        assert not columnas & {"qvec", "embedding", "vector", "puntajes", "citas", "respuesta"}, (
            f"the routing record grew an unrelated surface: {sorted(columnas)}"
        )

    def test_la_retencion_esta_acotada_y_es_la_ratificada(self, db):
        """90 days, RATIFIED (tasks.md 0.6 / design.md A5) — not `forever`."""
        import datetime as dt

        from app.domains.conocimiento import repository

        assert routing.RETENCION_DECISIONES_DIAS == 90

        repository.registrar_decision_ruta(db, self._decision("vieja"))
        repository.registrar_decision_ruta(db, self._decision("nueva"))
        db.flush()
        vieja = repository.listar_decisiones_ruta(db)[0]
        vieja.decidida_en = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=91)
        db.flush()

        borradas = repository.purgar_decisiones_ruta(db)
        db.flush()
        assert borradas == 1
        assert [f.pregunta for f in repository.listar_decisiones_ruta(db)] == ["nueva"]

    def test_la_purga_respeta_el_borde_exacto(self, db):
        """A row at exactly the window edge survives. The boundary is nailed
        down here so a future `<` / `<=` flip is a failure, not a data loss."""
        import datetime as dt

        from app.domains.conocimiento import repository

        repository.registrar_decision_ruta(db, self._decision("justo en el borde"))
        db.flush()
        fila = repository.listar_decisiones_ruta(db)[0]
        fila.decidida_en = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
            days=routing.RETENCION_DECISIONES_DIAS, seconds=-30
        )
        db.flush()

        assert repository.purgar_decisiones_ruta(db) == 0


# ---------------------------------------------------------------------------
# 4.6 — the migration, on a real Postgres
# ---------------------------------------------------------------------------

# Reuses `test_rag_migrations`'s throwaway-database fixture rather than
# re-implementing it. Importing the fixture binds it into this module's
# namespace, which is what makes it resolvable by name below.
from tests.new.conocimiento.test_rag_migrations import (  # noqa: E402
    ALEMBIC_INI_PATH,
    throwaway_db,  # noqa: F401
)

_HEAD_U4 = "conocimiento_006"


class TestMigracionDecisionRuta:
    """Real-PG. `Base.metadata.create_all()` proves the ORM agrees with itself;
    only the migration proves a deploy gets the same table."""

    def test_upgrade_crea_la_tabla_con_sus_checks(self, throwaway_db):  # noqa: F811
        from alembic import command
        from sqlalchemy import inspect, text

        cfg, engine = throwaway_db
        command.upgrade(cfg, _HEAD_U4)

        inspector = inspect(engine)
        assert "rag_decision_ruta" in inspector.get_table_names()
        columnas = {col["name"] for col in inspector.get_columns("rag_decision_ruta")}
        assert columnas == {
            "id",
            "pregunta",
            "clase",
            "superficie",
            "motivo",
            "margen",
            "umbral_vigente",
            "decidida_en",
        }, "the migration and models.py must declare the same shape"
        assert any(
            indice["name"] == "ix_rag_decision_ruta_decidida_en"
            for indice in inspector.get_indexes("rag_decision_ruta")
        ), "the retention purge scans by age; without the index it seq-scans the log"

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO rag_decision_ruta (id, pregunta, clase, superficie, motivo) "
                    "VALUES (gen_random_uuid(), 'una', 'legal', NULL, 'centroide')"
                )
            )
        with pytest.raises(Exception) as fallo:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO rag_decision_ruta (id, pregunta, clase, motivo) "
                        "VALUES (gen_random_uuid(), 'otra', 'inventada', 'centroide')"
                    )
                )
        assert "ck_rag_decision_ruta_clase" in str(fallo.value)

    def test_una_superficie_inventada_es_rechazada(self, throwaway_db):  # noqa: F811
        from alembic import command
        from sqlalchemy import text

        cfg, engine = throwaway_db
        command.upgrade(cfg, _HEAD_U4)

        with pytest.raises(Exception) as fallo:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO rag_decision_ruta (id, pregunta, clase, superficie, motivo) "
                        "VALUES (gen_random_uuid(), 'x', 'operational', '/padron', 'regla')"
                    )
                )
        assert "ck_rag_decision_ruta_superficie" in str(fallo.value)

    def test_el_arbol_sigue_con_una_sola_cabeza(self):
        """`conocimiento_006` chains onto the tip, not onto an already-parented
        revision. A fork is invisible to every test that names a revision."""
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI_PATH))).get_heads()
        assert list(heads) == [_HEAD_U4], f"expected a single head at {_HEAD_U4}, got {heads}"


# ---------------------------------------------------------------------------
# 4.7 — the ratified set, the confusion matrix, and the refusals
# ---------------------------------------------------------------------------


class TestEvalRouter:
    """`routing spec:87-104`, `design.md:172-186`."""

    def test_el_set_ratificado_carga_y_cumple_los_pisos(self):
        from app.domains.conocimiento.eval import router as eval_router

        items = eval_router.cargar_router_set()
        assert len(items) == 49
        por_clase = eval_router.ids_por_clase(items)
        assert {clase: len(ids) for clase, ids in por_clase.items()} == {
            "legal": 13,
            "operational": 12,
            "geoespacial": 11,
            "mixto": 13,
        }
        assert all(len(ids) >= eval_router.PISO_POR_CLASE for ids in por_clase.values()), (
            "design.md:181 — a floor of 10 per class is what makes the four-class "
            "matrix have cells rather than anecdotes"
        )

    def test_un_set_sin_ratificar_es_not_evaluable(self, tmp_path):
        """`routing spec:100-104`. It REFUSES; it does not score and warn."""
        import yaml as _yaml

        from app.domains.conocimiento.eval import router as eval_router

        borrador = tmp_path / "borrador.yaml"
        borrador.write_text(
            _yaml.safe_dump(
                {
                    "estado": "BORRADOR (pendiente de revision del owner)",
                    "preguntas": [
                        {"id": "X-1", "pregunta": "x", "clase_esperada": "legal"},
                    ],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        with pytest.raises(routing.SetRouterNoRatificado) as fallo:
            eval_router.cargar_router_set(borrador)
        assert "not-evaluable" in str(fallo.value)

        bloque = eval_router.bloque_no_evaluable(str(fallo.value))
        assert any("`not-evaluable`" in linea for linea in bloque)
        assert not any(
            caracter.isdigit() and "0." in linea for linea in bloque for caracter in linea
        ), "a refusal must not print a score next to the word not-evaluable"

    def test_un_set_ratificado_pero_flaco_tambien_se_rechaza(self, tmp_path):
        """Ratification is not a bypass of the sample-size floor. A file edited
        down to twelve items still parses, and would still print a matrix."""
        import yaml as _yaml

        from app.domains.conocimiento.eval import router as eval_router

        flaco = tmp_path / "flaco.yaml"
        flaco.write_text(
            _yaml.safe_dump(
                {
                    "estado": "RATIFICADO (owner)",
                    "preguntas": [
                        {"id": f"X-{i}", "pregunta": f"q{i}", "clase_esperada": "legal"}
                        for i in range(12)
                    ],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        with pytest.raises(routing.SetRouterNoRatificado):
            eval_router.cargar_router_set(flaco)

    def test_la_matriz_nombra_la_celda_peligrosa(self):
        """`routing spec:87-92` — reported EXPLICITLY, not derivable-in-principle."""
        matriz = routing.matriz_desde(
            [
                ("operational", "legal"),
                ("operational", "operational"),
                ("legal", "legal"),
                ("mixto", "mixto"),
                ("geoespacial", "geoespacial"),
            ]
        )
        assert matriz.operational_a_legal == 1
        assert matriz.fraccion_operational_a_legal == pytest.approx(0.5)
        assert matriz.exactitud == pytest.approx(0.8)

    def test_una_matriz_vacia_no_reporta_exactitud_perfecta_ni_cero(self):
        """`None`, not 1.0. No denominator means no measurement — the same
        convention `ParAbstencion.recall` uses and for the same reason."""
        vacia = routing.matriz_desde([])
        assert vacia.exactitud is None
        assert vacia.fraccion_operational_a_legal is None

    def test_la_barra_no_ratificada_reporta_y_no_dictamina(self):
        """The gate runs, prints, and refuses to say pass or fail."""
        from app.domains.conocimiento.eval import router as eval_router

        embedder = EmbedderFalso()
        resultado = eval_router.correr_eval_router(embedder, pasos=3)
        evaluacion = routing.evaluar_barra(resultado)

        assert evaluacion.estado == routing.ESTADO_BARRA_NO_RATIFICADA
        assert evaluacion.veredicto is None, (
            "a verdict against an unratified bar is a bar somebody invented"
        )
        assert evaluacion.barra.ratificada is False
        assert evaluacion.exactitud is not None, "it must still MEASURE"

        bloque = "\n".join(eval_router.bloque_router(resultado, embedder, evaluacion))
        assert "operational -> legal" in bloque
        assert "barra_no_ratificada" in bloque
        assert eval_router.ETIQUETA_UPPER_BOUND in bloque
        assert "PASA" not in bloque and "NO PASA" not in bloque

    def test_una_barra_ratificada_si_dictamina(self):
        """The mechanism is not decorative: flip `ratificada` and it decides."""
        from app.domains.conocimiento.eval import router as eval_router

        resultado = eval_router.correr_eval_router(EmbedderFalso(), pasos=3)
        holgada = routing.evaluar_barra(resultado, routing.BarraRouter(1.0, 0.0, ratificada=True))
        assert holgada.estado == routing.ESTADO_BARRA_EVALUADA
        assert holgada.veredicto is True

        imposible = routing.evaluar_barra(
            resultado, routing.BarraRouter(0.0, 1.01, ratificada=True)
        )
        assert imposible.veredicto is False

    def test_el_json_lleva_la_etiqueta_de_upper_bound(self):
        """A same-sample figure that travels without its label is a held-out
        figure to whoever reads the JSON next."""
        from app.domains.conocimiento.eval import router as eval_router

        datos = eval_router.a_json(eval_router.correr_eval_router(EmbedderFalso(), pasos=3))
        assert datos["same_sample_label"] == eval_router.ETIQUETA_UPPER_BOUND
        assert datos["barra"]["veredicto"] is None
        assert datos["barra"]["estado"] == routing.ESTADO_BARRA_NO_RATIFICADA
        assert len(datos["folds"]) == datos["n"] == 49

    def test_loocv_no_deja_que_el_item_retenido_arme_su_propio_centroide(self):
        """Refitting only the parameters leaks the held-out item through the
        very direction it is scored against."""
        from app.domains.conocimiento.eval import router as eval_router

        items = eval_router.cargar_router_set()
        senales = routing.senales_desde(items, EmbedderFalso())
        completo = routing.centroides_desde(senales)
        sin_uno = routing.centroides_desde(senales[1:])
        assert completo.como_mapa() != sin_uno.como_mapa()

    def test_mixto_no_tiene_centroide(self):
        """design.md:165-168 — it is recognized by its top-2 signature."""
        from app.domains.conocimiento.eval import router as eval_router

        senales = routing.senales_desde(eval_router.cargar_router_set(), EmbedderFalso())
        assert set(routing.centroides_desde(senales).como_mapa()) == {
            "legal",
            "operational",
            "geoespacial",
        }
        with pytest.raises(routing.RouterNoCalibrado):
            routing.Centroides({clase: EJE.get(clase, (1.0, 0.0, 0.0)) for clase in routing.CLASES})
