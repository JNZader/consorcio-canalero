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


def _resultado_sintetico(
    *,
    exactitud: float | None = None,
    op_legal: int = 0,
    mixto_legal: int = 0,
) -> routing.ResultadoRouterLOOCV:
    """A held-out matrix with the exact figures a bar test needs.

    Built from counts rather than from a run, because the bar is being asserted
    here and not the router: a test that has to steer 49 embeddings into an
    accuracy of exactly 0.69 asserts mostly its own fixture. `n = 100` makes
    every ratio exact in two decimals, so `0.70` is `0.70` and not `0.7000001`.

    Errors that belong to neither named cell are `legal -> operational`: a
    redirect of a legal question, which is the cheap failure by design.
    """
    total = 100
    nombradas = [(routing.CLASE_OPERATIONAL, routing.CLASE_LEGAL)] * op_legal
    nombradas += [(routing.CLASE_MIXTO, routing.CLASE_LEGAL)] * mixto_legal
    aciertos = total - len(nombradas) if exactitud is None else round(exactitud * total)
    resto = total - aciertos - len(nombradas)
    assert resto >= 0, "the requested figures do not fit in 100 items"

    pares = (
        [(routing.CLASE_LEGAL, routing.CLASE_LEGAL)] * aciertos
        + nombradas
        + [(routing.CLASE_LEGAL, routing.CLASE_OPERATIONAL)] * resto
    )
    matriz = routing.matriz_desde(pares)
    return routing.ResultadoRouterLOOCV(
        n=total,
        parametros_shipped=routing.PARAMETROS_SIN_CALIBRAR,
        centroides_shipped={},
        folds=(),
        matriz=matriz,
        matriz_same_sample=matriz,
    )


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

    def test_la_superficie_operacional_por_defecto_es_la_ratificada(self):
        """S-1 — RATIFIED by the owner on 2026-08-24 (tasks.md 4.1).

        `/tramites` was raised as an implementation decision (`routing spec:31`
        requires a named surface; design.md G1 does not say which one when the
        subject family is unresolved) and the owner answered it as a decision:
        `/tramites` is the most general of the four, so it is the one an
        operator lands on carrying the fewest wrong assumptions about what their
        own question was about.

        Pinned as a literal rather than as `== SUPERFICIE_TRAMITES`: the alias
        would follow the constant wherever a refactor moved it, and what was
        ratified is the destination, not the name of the variable.
        """
        assert routing.SUPERFICIE_OPERACIONAL_POR_DEFECTO == "/tramites"
        assert routing.SUPERFICIE_OPERACIONAL_POR_DEFECTO in routing.SUPERFICIES

        # And it is really the fallback: a bare padrón-shaped name fires the
        # marker with no family attached, so nothing else can supply a surface.
        decision = routing.clasificar(
            "Necesito los datos de Marcelo Gutiérrez",
            embedder=EmbedderFalso(),
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )
        assert decision.clase == "operational"
        assert decision.motivo == routing.MOTIVO_REGLA
        assert decision.superficie == "/tramites"


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
        # By question text, NOT by position. Both rows take `decidida_en` from
        # the same `now()` inside one transaction, so `listar_decisiones_ruta`
        # breaks the tie on a random UUID and index 0 was whichever id happened
        # to sort first — this test failed 3 runs in 6 before the fix, and the
        # thing it was failing about was its own fixture.
        vieja = next(f for f in repository.listar_decisiones_ruta(db) if f.pregunta == "vieja")
        vieja.decidida_en = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=91)
        db.flush()

        borradas = repository.purgar_decisiones_ruta(db)
        db.flush()
        assert borradas == 1
        assert [f.pregunta for f in repository.listar_decisiones_ruta(db)] == ["nueva"]

    def test_la_purga_respeta_el_borde_exacto(self, db):
        """A row at EXACTLY the window edge survives (`<`, not `<=`).

        The previous version of this test placed the row 30 seconds INSIDE the
        window and asserted it survived — which is true under `<` and equally
        true under `<=`, so the flip it claimed to guard was never guarded. It
        could not have been: with the clock read inside the purge, a row written
        at `now - 90d` is already strictly older by the time the query runs.

        So the clock is an argument now. `ahora` is frozen, the row is placed at
        `ahora - 90d` to the microsecond, and BOTH sides of the boundary are
        asserted: the edge survives, one microsecond past it does not. Flip the
        comparator and the first assertion fails.
        """
        import datetime as dt

        from app.domains.conocimiento import repository

        ahora = dt.datetime(2026, 8, 24, 12, 0, 0, tzinfo=dt.timezone.utc)
        borde = ahora - dt.timedelta(days=routing.RETENCION_DECISIONES_DIAS)

        repository.registrar_decision_ruta(db, self._decision("justo en el borde"))
        db.flush()
        fila = repository.listar_decisiones_ruta(db)[0]
        fila.decidida_en = borde
        db.flush()

        assert repository.purgar_decisiones_ruta(db, ahora=ahora) == 0, (
            "a row AT the edge is not older than the window — the ratified side "
            "of the boundary is `<`, so the edge survives"
        )

        # One microsecond older is over the edge, and the same call deletes it.
        fila.decidida_en = borde - dt.timedelta(microseconds=1)
        db.flush()
        assert repository.purgar_decisiones_ruta(db, ahora=ahora) == 1

    def test_la_purga_rechaza_un_reloj_sin_zona(self, db):
        """`decidida_en` is TIMESTAMPTZ. A naive `ahora` would be read against
        the server's local offset and shift the whole retention window."""
        import datetime as dt

        from app.domains.conocimiento import repository

        with pytest.raises(ValueError, match="aware"):
            repository.purgar_decisiones_ruta(db, ahora=dt.datetime(2026, 8, 24, 12, 0, 0))


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

    def test_una_barra_sin_ratificar_reporta_y_no_dictamina(self):
        """The state SURVIVES the ratification (2026-08-24).

        The owner fixed THIS bar; the next one — a new labeled set, a re-derived
        threshold — starts unratified again, and a mechanism that only ever
        holds one value is a mechanism nobody can re-enter. So the unratified
        path is still asserted to measure, print, and refuse a verdict.
        """
        from app.domains.conocimiento.eval import router as eval_router

        embedder = EmbedderFalso()
        resultado = eval_router.correr_eval_router(embedder, pasos=3)
        evaluacion = routing.evaluar_barra(resultado, routing.BarraRouter(ratificada=False))

        assert evaluacion.estado == routing.ESTADO_BARRA_NO_RATIFICADA
        assert evaluacion.veredicto is None, (
            "a verdict against an unratified bar is a bar somebody invented"
        )
        assert evaluacion.componentes_fallidos == (), "nothing was judged, so nothing failed"
        assert evaluacion.exactitud is not None, "it must still MEASURE"

        bloque = "\n".join(eval_router.bloque_router(resultado, embedder, evaluacion))
        assert "operational -> legal" in bloque
        assert "barra_no_ratificada" in bloque
        assert eval_router.ETIQUETA_UPPER_BOUND in bloque
        assert "PASA" not in bloque and "NO PASA" not in bloque

    def test_la_barra_ratificada_es_la_que_el_owner_fijo(self):
        """RATIFIED 2026-08-24 (tasks.md 0.3), pinned as three literals.

        The numbers were fixed AFTER measuring on the ratified n=49 set, which
        is the whole discipline decision 0.3 protected. Pinning them here makes
        a later edit a change to a ratified value rather than a tuning knob.
        """
        barra = routing.BARRA_RATIFICADA
        assert barra.ratificada is True
        assert barra.exactitud_minima == 0.70
        assert barra.operational_a_legal_max == 0
        assert barra.mixto_a_legal_max == 2
        assert routing.BarraRouter() == barra, "the default IS the ratified bar"

    @pytest.mark.parametrize(
        "matriz_pares, pasa, motivo",
        [
            # accuracy: the exact edge passes, one item below it does not.
            (("exactitud", 0.70), True, "0.70 exact is ON the bar, and the bar is >="),
            (("exactitud", 0.69), False, "0.69 is below 0.70"),
            # `operational -> legal` is a HARD cell: one is already too many.
            (("op_legal", 0), True, "zero is the ratified value"),
            (("op_legal", 1), False, "one fabricated debt figure is not a rounding error"),
            # `mixto -> legal` is the measured 2, ratified AT the measurement.
            (("mixto_legal", 2), True, "2 of 13 is what was measured and ratified"),
            (("mixto_legal", 3), False, "3 is over the ratified ceiling"),
        ],
    )
    def test_cada_componente_de_la_barra_decide_en_su_borde_exacto(
        self, matriz_pares, pasa, motivo
    ):
        """Both directions, per component. A bar asserted only from the passing
        side is a bar that would still pass with the comparison inverted."""
        componente, valor = matriz_pares
        resultado = _resultado_sintetico(**{componente: valor})
        evaluacion = routing.evaluar_barra(resultado)

        assert evaluacion.estado == routing.ESTADO_BARRA_EVALUADA
        assert evaluacion.veredicto is pasa, motivo
        assert bool(evaluacion.componentes_fallidos) is (not pasa)

    def test_una_muestra_vacia_no_pasa_la_barra(self):
        """`exactitud is None` is the absence of a measurement, and an absent
        measurement must never read as a clean one."""
        vacio = routing.ResultadoRouterLOOCV(
            n=0,
            parametros_shipped=routing.PARAMETROS_SIN_CALIBRAR,
            centroides_shipped={},
            folds=(),
            matriz=routing.matriz_desde([]),
            matriz_same_sample=routing.matriz_desde([]),
        )
        evaluacion = routing.evaluar_barra(vacio)
        assert evaluacion.veredicto is False
        assert any("n/a" in fallo for fallo in evaluacion.componentes_fallidos)

    def test_el_json_lleva_la_etiqueta_de_upper_bound(self):
        """A same-sample figure that travels without its label is a held-out
        figure to whoever reads the JSON next."""
        from app.domains.conocimiento.eval import router as eval_router

        resultado = eval_router.correr_eval_router(EmbedderFalso(), pasos=3)
        datos = eval_router.a_json(resultado)
        assert datos["same_sample_label"] == eval_router.ETIQUETA_UPPER_BOUND
        assert len(datos["folds"]) == datos["n"] == 49

        # The bar is ratified, so the JSON carries a real verdict and the three
        # figures it was computed from — a verdict nobody can re-derive from the
        # same document is a verdict nobody can check.
        assert datos["barra"]["estado"] == routing.ESTADO_BARRA_EVALUADA
        assert datos["barra"]["ratificada"] is True
        assert datos["barra"]["veredicto"] in (True, False)
        assert datos["mixto_a_legal"] == resultado.matriz.mixto_a_legal
        assert datos["operational_a_legal"] == resultado.matriz.operational_a_legal

        # And an unratified bar still travels as `None`, not as a False.
        sin_ratificar = eval_router.a_json(
            resultado, routing.evaluar_barra(resultado, routing.BarraRouter(ratificada=False))
        )
        assert sin_ratificar["barra"]["veredicto"] is None
        assert sin_ratificar["barra"]["estado"] == routing.ESTADO_BARRA_NO_RATIFICADA

    def test_loocv_no_deja_que_el_item_retenido_arme_su_propio_centroide(self):
        """Refitting only the parameters leaks the held-out item through the
        very direction it is scored against."""
        from app.domains.conocimiento.eval import router as eval_router

        items = eval_router.cargar_router_set()
        senales = routing.senales_desde(items, EmbedderFalso())
        completo = routing.centroides_desde(senales)
        sin_uno = routing.centroides_desde(senales[1:])
        assert completo.como_mapa() != sin_uno.como_mapa()

    def test_la_matriz_held_out_cambia_si_el_item_retenido_arma_su_centroide(self):
        """The guardian for the one-token mutation the test above survives.

        `centroides_desde(senales) != centroides_desde(senales[1:])` compares a
        helper against itself; swapping `centroides_fold` for
        `centroides_shipped` inside `calibrar_loocv` leaves it — and the other
        49 tests — perfectly green while the held-out matrix silently becomes a
        training fit. So this asserts the OUTPUT of the real function on a set
        built to make the leak visible.

        The geometry, stated rather than hoped (`e1` legal, `e2` operational,
        `e3` geospatial): `X` is labeled `operational` and points at
        `(0, 0.6, 0.8)` — nearer the geospatial axis than the operational one.
        With `X` inside the operational centroid, that centroid tilts toward it
        and `X` scores 0.809 against itself-plus-friends versus 0.800 against
        geospatial, so the leak predicts `operational`. Fitted WITHOUT `X`, the
        operational centroid is `e2` exactly, `X` scores 0.6 against it and 0.8
        against geospatial, and the honest answer is a miss.

        The pair `{operational, geoespacial}` is deliberately not a `mixto`
        signature (design.md:165-168), so no parameter choice can reach this
        item: what the fold changes is the centroid and nothing else.
        """
        retenido = "X-operational-cerca-de-geo"

        def senal(ident: str, clase: str, vector: tuple[float, float, float]):
            return routing.SenalRuta(
                id=ident,
                pregunta=f"pregunta {ident}",
                clase_esperada=clase,
                borde=False,
                # Explicitly None: a stage-1 hit short-circuits `predecir` and
                # would make the centroids irrelevant to this item.
                clase_regla=None,
                vector=vector,
            )

        senales = (
            senal("L-1", "legal", (1.0, 0.0, 0.0)),
            senal("L-2", "legal", (1.0, 0.0, 0.0)),
            senal("L-3", "legal", (1.0, 0.0, 0.0)),
            senal("O-1", "operational", (0.0, 1.0, 0.0)),
            senal("O-2", "operational", (0.0, 1.0, 0.0)),
            senal(retenido, "operational", (0.0, 0.6, 0.8)),
            senal("G-1", "geoespacial", (0.0, 0.0, 1.0)),
            senal("G-2", "geoespacial", (0.0, 0.0, 1.0)),
            senal("G-3", "geoespacial", (0.0, 0.0, 1.0)),
        )

        resultado = routing.calibrar_loocv(senales, pasos=7)
        fold = next(f for f in resultado.folds if f.id == retenido)

        assert fold.clase_predicha == "geoespacial", (
            "the held-out item was classified against a centroid it helped build: "
            "`calibrar_loocv` must rebuild the CENTROIDS per fold, not only the "
            "parameters"
        )
        assert resultado.matriz.celda("operational", "geoespacial") == 1
        assert resultado.matriz.celda("operational", "operational") == 2

        # The same-sample matrix is the leak, measured on purpose: it gets the
        # item right, and that gap between 8/9 and 9/9 is exactly what the
        # `upper bound` label warns a reader about.
        assert resultado.matriz_same_sample.celda("operational", "operational") == 3
        assert resultado.matriz.exactitud == pytest.approx(8 / 9)
        assert resultado.matriz_same_sample.exactitud == pytest.approx(1.0)

    def test_una_regla_de_etapa_uno_decide_sin_tocar_el_sidecar(self):
        """S-3 — the stage-1 short-circuit, pinned by call count.

        `EmbedderCaido` already proves a rule survives a DOWN sidecar. It does
        not prove the sidecar was never CALLED: an implementation that embedded
        first and then let the rule win would fail that test only because the
        double happens to raise. The spy counts, so zero is zero.
        """
        espia = EmbedderFalso()
        decision = routing.clasificar(
            "¿cuánto debe Juan Pérez?",
            embedder=espia,
            centroides=_centroides_de_ejes(),
            parametros=routing.PARAMETROS_SIN_CALIBRAR,
        )

        assert decision.motivo == routing.MOTIVO_REGLA
        assert espia.llamadas == [], "stage 1 decided; nothing had to be embedded"
        assert decision.qvec is None and decision.puntajes == {}

        # Same property on the calibration path: `predecir` must not consult the
        # centroids for an item stage 1 already decided.
        class CentroidesQueGritan(routing.Centroides):
            def puntajes(self, qvec):  # pragma: no cover - must never run
                raise AssertionError("a rule-decided item asked the centroids for a score")

        senal = routing.SenalRuta(
            id="R-1",
            pregunta="¿cuánto debe Juan Pérez?",
            clase_esperada="operational",
            borde=False,
            clase_regla="operational",
            vector=(1.0, 0.0, 0.0),
        )
        gritones = CentroidesQueGritan({clase: tuple(v) for clase, v in EJE.items()})
        assert routing.predecir(senal, gritones, routing.PARAMETROS_SIN_CALIBRAR) == "operational"

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
