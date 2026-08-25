"""Answer-level eval: mechanical metrics automated, faithfulness graded by the owner.

Tasks 9.1–9.4, `design.md` G7 (:822-909) and the generation spec's
`Answer-Level Eval Metrics With Ratified Thresholds` requirement.

This module is a GRADING HARNESS. It does not produce answers and it must not:
the answers come from the pinned provider (or, for the 9.6b bench, from a real
SLM on the owner's GPU worker), through the runbook, and the owner grades them.
What lives here is the artifact format, its loading, its refusals, and the
arithmetic over what the artifact holds.

Four properties are load-bearing, and each is a refusal rather than a convention.

**1. The invented-citation universe is the POST-EXCLUSION payload, not the
retrieved page** *(bounded correction, 2026-08-23; `design.md:832-839`)*. The
enforcement that actually runs binds membership to the payload
(`generacion.verificar`), and scoring against the retrieved page measures a
different function — one that errs in the dangerous direction, since a key
belonging to a retrieved-but-EXCLUDED unit would score as correct here and be
rejected in production. So the payload is recomputed from the database with the
same `service.assert_unidades_publicas` call the request path uses, and the
recorded payload is checked against it.

**2. A reclassification re-triggers the measurement even with `corpus_sha`
unmoved** *(`design.md:853-857`)*. The corpus is byte-identical; the payloads are
not. So the artifact pins `(corpus_sha, expected_clasificacion_sha256)` and
`verificar_payload` refuses when the re-derived shippable set diverges from the
recorded one — which is the same fact reaching us through the data instead of
through the header.

**3. Grades are pinned to what produced them** *(9.3, `design.md:884-890`)*. A
faithfulness label is a judgment about a specific answer produced by a specific
prompt, a specific model and a specific corpus. Re-using it after any of the
three moves is scoring the old system's output as the new one's, so
`verificar_pines` compares all three, names BOTH operands, and says the fix is a
re-grade — never a re-scoring.

**4. `n >= 30` counts ANSWERS, and the claim count travels beside it**
*(`design.md:864-868`)*. An answer carries several claims, so "n = 30" read as
claims would be six or seven answers wearing a bigger number. `n_respuestas`,
`n_afirmaciones` and the per-answer claim distribution are all published.

And the one thing this module will not do: it does not decide the faithfulness
bar. `invented-citation = 0.00`, `uncited-claim = 0.00` and the end-to-end
abstention pair are SPEC'd (generation spec, `Answer-Level Eval Metrics`) and are
scored here. `fully-supported >= 0.95` is a PROPOSAL awaiting owner ratification,
so it prints next to the figures under `barra_no_ratificada` and issues no
verdict — the same discipline `eval/router.py` uses for its own bar.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from sqlalchemy.orm import Session

from app.domains.conocimiento import generacion

RUTA_ANSWER_SET = Path(__file__).with_name("answer_set.yaml")
RUTA_EXPECTED_CLASIFICACION = Path(__file__).with_name("expected_clasificacion.yaml")

#: The owner grades every claim into exactly one of these. `parcial` is a real
#: outcome and not a hedge: at n≈30 with a single grader, forcing partial support
#: into either neighbour is what turns one judgment call into a threshold crossing.
GRADOS = ("sostenida", "parcial", "contradicha")

#: Ratified 2026-08-23 (decision 0.6): the answer set is `n >= 30` ANSWERS.
N_MINIMO_RESPUESTAS = 30

#: Intra-rater re-grade sample: 10% of the graded claims, with a HARD FLOOR of 15
#: (`design.md:877-882`). The floor is the point — at 30 answers × 3 claims a bare
#: 10% is 9 claims, and an agreement figure over 9 items moves 0.11 per
#: disagreement. If 10% exceeds 15, 10% wins.
FRACCION_REGRADO = 0.10
PISO_REGRADO = 15

#: The three bars the generation spec makes MANDATORY and this module scores.
BARRA_CITA_INVENTADA = 0.00
BARRA_AFIRMACION_SIN_CITA = 0.00
BARRA_ABSTENCION_RECALL = 1.00
BARRA_ABSTENCION_PRECISION = 0.80

#: PROPOSED, not ratified (`design.md:892-895`). Printed beside the figures; never
#: turned into a pass or a fail here.
PROPUESTA_SOSTENIDA = 0.95
PROPUESTA_CONTRADICHA = 0.00

ESTADO_BARRA_NO_RATIFICADA = "barra_no_ratificada"
ESTADO_NO_EVALUABLE = "not-evaluable"

#: `estado_servido` values that mean the surface served NO answer. Read off the
#: generation state machine rather than re-listed by hand, so a new terminal state
#: cannot silently start counting as an answer.
ESTADOS_SIN_RESPUESTA = frozenset(
    {
        generacion.ESTADO_ABSTENCION,
        generacion.ESTADO_REDIRECCION,
        generacion.ESTADO_GENERACION_FALLIDA,
        generacion.ESTADO_NO_DISPONIBLE,
    }
)

#: The one state that abstains BECAUSE the corpus had nothing applicable, as
#: opposed to a dependency failure. Only this one is an abstention DECISION; the
#: others are outages and are excluded from the pair, because counting an outage
#: as a correct abstention would let a dead provider score 1.00 recall.
ESTADO_ABSTENCION = generacion.ESTADO_ABSTENCION


class ConjuntoRespuestasNoRatificado(RuntimeError):
    """The answer set is not owner-ratified, so nothing is scored from it.

    Same refusal as `eval/router.py::cargar_router_set`, for the same reason:
    everything downstream of loading produces numbers, and numbers from an
    unreviewed set are indistinguishable on the page from numbers from a
    reviewed one. The generation spec makes this explicit — "the owner MUST
    ratify the answer set before any threshold is scored".
    """


class ConjuntoRespuestasInvalido(RuntimeError):
    """The artifact does not satisfy its own schema."""


class PinRespuestasDivergente(RuntimeError):
    """The grades were produced under a different prompt, model or corpus.

    Names both operands and says the fix is a RE-GRADE. Re-scoring the old
    labels against the new system is the exact move this refusal exists to stop:
    it would publish a faithfulness figure for text the new prompt never wrote.
    """


class PayloadDivergente(RuntimeError):
    """The recorded post-exclusion payload is not the one the gate produces today.

    The corpus bytes have not moved — `corpus_sha` still matches — but the
    classification has, so the payloads have. Every invented-citation score in
    this artifact was computed against a universe that no longer exists.
    """


class RespuestasSinteticas(RuntimeError):
    """The answers came from a stand-in generator, so they are not an eval.

    The exact sibling of `report._gate_sintetico` and of
    `generacion.assert_generador_publicable`: a `GeneradorDeterministico` writes
    text shaped like an answer, with citation keys and framings that pass every
    mechanical check by construction, and a faithfulness rate computed over it
    measures the fixture.
    """


@dataclass(frozen=True)
class Afirmacion:
    """One graded claim: what it says, what it cites, and how the owner graded it."""

    id: str
    texto: str
    clave: str
    grado: str


@dataclass(frozen=True)
class RespuestaGraduada:
    """One served answer, its recorded context, and its graded claims.

    `claves_recuperadas` and `claves_payload` are both recorded because their
    DIFFERENCE is the privacy gate's contribution, and the design requires that
    contribution to be visible rather than folded into the abstention rate.
    """

    id: str
    pregunta: str | None
    pregunta_ref: str | None
    texto: str
    claves_recuperadas: tuple[str, ...]
    claves_payload: tuple[str, ...]
    estado_servido: str
    #: The gold label: SHOULD this question have been abstained on?
    debe_abstenerse: bool
    afirmaciones: tuple[Afirmacion, ...]
    #: Claim id -> second-pass grade. Blind to the first pass and at least a day
    #: later (`design.md:870-875`); this module cannot verify either condition and
    #: does not pretend to — it reports the sample size next to the agreement.
    regrado: Mapping[str, str]

    @property
    def abstuvo(self) -> bool:
        """Did the SURFACE serve no answer? Measured post-exclusion, on the outcome."""
        return self.estado_servido in ESTADOS_SIN_RESPUESTA

    @property
    def abstencion_por_exclusion(self) -> bool:
        """Did the privacy gate empty a non-empty retrieved page?

        The design asks for this explicitly: "the reader is entitled to see how
        much of the abstention rate the privacy gate is producing".
        """
        return bool(self.claves_recuperadas) and not self.claves_payload


@dataclass(frozen=True)
class ConjuntoRespuestas:
    version: int
    estado: str
    prompt_version: int
    provider_model_pin: str
    corpus_sha: str
    expected_clasificacion_sha256: str
    generador_sintetico: bool | None
    respuestas: tuple[RespuestaGraduada, ...]

    @property
    def n_respuestas(self) -> int:
        return len(self.respuestas)

    @property
    def n_afirmaciones(self) -> int:
        return sum(len(r.afirmaciones) for r in self.respuestas)

    @property
    def distribucion_afirmaciones(self) -> dict[int, int]:
        """claims-per-answer -> how many answers have that many.

        Published because "n = 30 answers, 94 claims" and "n = 30 answers, 65 of
        them from one" are different facts and only one of them supports a rate.
        """
        histograma: dict[int, int] = {}
        for respuesta in self.respuestas:
            cuantas = len(respuesta.afirmaciones)
            histograma[cuantas] = histograma.get(cuantas, 0) + 1
        return histograma


def sha256_de(path: Path) -> str:
    """The artifact's own bytes, hashed. Not a re-derivation of its contents.

    The pin has to move when the FILE moves, including for an edit that a parser
    would normalise away: a widened allowlist written as a reordered list is
    still a widened allowlist.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _afirmaciones_de(crudo: Mapping[str, Any], respuesta_id: str) -> tuple[Afirmacion, ...]:
    vistas: set[str] = set()
    salida: list[Afirmacion] = []
    for entrada in crudo.get("afirmaciones") or []:
        id = str(entrada["id"])
        if id in vistas:
            raise ConjuntoRespuestasInvalido(
                f"{respuesta_id}: duplicate claim id {id!r} — a grade that cannot be "
                "traced back to one claim cannot be re-graded either"
            )
        vistas.add(id)
        grado = str(entrada["grado"])
        if grado not in GRADOS:
            raise ConjuntoRespuestasInvalido(
                f"{respuesta_id}/{id}: grado {grado!r} is not one of {GRADOS}. A "
                "vocabulary this module does not know is a label nobody can count."
            )
        salida.append(
            Afirmacion(
                id=id,
                texto=str(entrada.get("texto", "")),
                clave=str(entrada.get("clave", "")),
                grado=grado,
            )
        )
    return tuple(salida)


def cargar_conjunto_respuestas(ruta: Path | None = None) -> ConjuntoRespuestas:
    """Parse the graded artifact, or REFUSE when it is not owner-ratified."""
    ruta = ruta or RUTA_ANSWER_SET
    return cargar_desde_mapping(yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}, ruta.name)


def cargar_desde_mapping(datos: Mapping[str, Any], origen: str) -> ConjuntoRespuestas:
    """The parser itself, over an already-decoded mapping.

    Split out from the file reader so an in-memory arm (the SLM bench's two
    inline arms) is validated by exactly these rules without a round trip
    through the filesystem. That round trip mattered: `RespuestaGraduada.texto`
    and `pregunta` are the verbatim question and answer text, and threat 7.5 is
    about precisely that text leaving the box — writing it to a world-readable
    `/tmp` file to re-parse it is the box leaking to make a copy of itself.
    """
    estado = str(datos.get("estado", ""))
    if not estado.startswith("RATIFICADO"):
        raise ConjuntoRespuestasNoRatificado(
            f"{origen} reports estado={estado!r}. Answer-level thresholds are "
            "not-evaluable until the owner ratifies the set (generation spec, "
            "`Answer-Level Eval Metrics With Ratified Thresholds`). The answers "
            "themselves are produced by the GPU worker through the runbook; this "
            "harness grades and scores them, it never writes them."
        )

    respuestas: list[RespuestaGraduada] = []
    vistas: set[str] = set()
    for crudo in datos.get("respuestas") or []:
        id = str(crudo["id"])
        if id in vistas:
            raise ConjuntoRespuestasInvalido(f"duplicate answer id {id!r}")
        vistas.add(id)

        recuperadas = tuple(str(c) for c in crudo.get("claves_recuperadas") or ())
        payload = tuple(str(c) for c in crudo.get("claves_payload") or ())
        if not set(payload).issubset(set(recuperadas)):
            raise ConjuntoRespuestasInvalido(
                f"{id}: `claves_payload` is not a subset of `claves_recuperadas`. "
                "The payload is the retrieved page FILTERED; a key in it that was "
                "never retrieved did not come from this request."
            )

        estado_servido = str(crudo.get("estado_servido", ""))
        if (
            estado_servido == generacion.ESTADO_RESPUESTA
            and not str(crudo.get("texto", "")).strip()
        ):
            raise ConjuntoRespuestasInvalido(
                f"{id}: estado_servido={estado_servido!r} with empty text. Every "
                "mechanical check passes vacuously on empty text, so an empty "
                "answer recorded as served would score a perfect row."
            )

        respuestas.append(
            RespuestaGraduada(
                id=id,
                pregunta=None if crudo.get("pregunta") is None else str(crudo["pregunta"]),
                pregunta_ref=(
                    None if crudo.get("pregunta_ref") is None else str(crudo["pregunta_ref"])
                ),
                texto=str(crudo.get("texto", "")),
                claves_recuperadas=recuperadas,
                claves_payload=payload,
                estado_servido=estado_servido,
                debe_abstenerse=bool(crudo.get("debe_abstenerse", False)),
                afirmaciones=_afirmaciones_de(crudo, id),
                regrado={str(k): str(v) for k, v in (crudo.get("regrado") or {}).items()},
            )
        )

    return ConjuntoRespuestas(
        version=int(datos.get("version", 1)),
        estado=estado,
        prompt_version=int(datos.get("prompt_version", 0)),
        provider_model_pin=str(datos.get("provider_model_pin", "")),
        corpus_sha=str(datos.get("corpus_sha", "")),
        expected_clasificacion_sha256=str(datos.get("expected_clasificacion_sha256", "")),
        generador_sintetico=(
            None if datos.get("generador_sintetico") is None else bool(datos["generador_sintetico"])
        ),
        respuestas=tuple(respuestas),
    )


def verificar_pines(
    conjunto: ConjuntoRespuestas,
    *,
    prompt_version: int,
    provider_model_pin: str,
    corpus_sha: str,
) -> None:
    """Task 9.3 — refuse on divergence, naming both operands.

    A pure comparison, meant to run at the CLI edge BEFORE the database is opened
    or a report directory is created, following `verificar_corpus_sha`'s exact
    precedent (`harness.py`). The message says the fix is a re-grade, because it
    is: re-scoring the existing labels against the new system would attribute to
    the new prompt a judgment made about the old one's text.
    """
    divergencias = [
        (nombre, esperado, medido)
        for nombre, esperado, medido in (
            ("prompt_version", conjunto.prompt_version, prompt_version),
            ("provider_model_pin", conjunto.provider_model_pin, provider_model_pin),
            ("corpus_sha", conjunto.corpus_sha, corpus_sha),
        )
        if esperado != medido
    ]
    if not divergencias:
        return
    detalle = "; ".join(
        f"{nombre}: el artefacto está pineado a {esperado!r} y esta corrida es {medido!r}"
        for nombre, esperado, medido in divergencias
    )
    raise PinRespuestasDivergente(
        f"las cifras graduadas no corresponden a este sistema — {detalle}. "
        "La corrección es RE-GRADUAR contra la salida nueva, nunca re-puntuar "
        "las etiquetas viejas: una etiqueta de fidelidad es un juicio sobre un "
        "texto concreto, y ese texto ya no es el que el sistema produce."
    )


def verificar_payload(db: Session, conjunto: ConjuntoRespuestas) -> None:
    """Task 9.4 — recompute the shippable set and refuse on divergence.

    The universe is recomputed with the SAME call the request path makes
    (`service.assert_unidades_publicas`), not with a copy of its rule. This is
    what catches a reclassification that left `corpus_sha` unmoved: the bytes are
    identical and the payloads are not, so pinning `corpus_sha` alone would let a
    widened allowlist reuse figures measured under a narrower one.
    """
    from app.domains.conocimiento.service import assert_unidades_publicas

    for respuesta in conjunto.respuestas:
        if not respuesta.claves_recuperadas:
            continue
        enviables = assert_unidades_publicas(
            db, conjunto.corpus_sha, list(respuesta.claves_recuperadas)
        )
        registrado = frozenset(respuesta.claves_payload)
        if enviables != registrado:
            raise PayloadDivergente(
                f"{respuesta.id}: el payload registrado es {sorted(registrado)} y la "
                f"clasificación vigente produce {sorted(enviables)} sobre el mismo "
                f"snapshot {conjunto.corpus_sha}. El corpus no se movió; la "
                "clasificación sí, así que el universo contra el que se puntuó "
                "`cita inventada` ya no existe. Re-corré el answer set y re-graduá "
                "(design.md:853-857)."
            )


def assert_publicable(conjunto: ConjuntoRespuestas) -> None:
    """No figures from a stand-in generator, and none from a set with no runs.

    Both halves matter. A `GeneradorDeterministico` writes text engineered to
    satisfy every mechanical check, so its invented-citation rate is 0.00 by
    construction and means nothing. An EMPTY set is the state this repository
    ships in — the answers come from the GPU worker through the runbook — and
    publishing 0/0 as a rate would report "no failures found" for a measurement
    that never ran.

    A set that never DECLARES which of the two it is refuses as well. `null` is
    not `false`: an artifact with answers and no declaration would be published
    on the assumption that a real generator wrote them, which is the one thing
    this gate exists not to assume.
    """
    if conjunto.generador_sintetico is None:
        raise RespuestasSinteticas(
            "el artefacto no declara `generador_sintetico`. Un `null` no es un "
            "`false`: dice que nadie registró qué escribió estas respuestas, y "
            "publicarlas asumiendo un generador real es exactamente la "
            "suposición que este chequeo existe para no hacer. Declaralo en el "
            "artefacto (`false` sólo cuando la corrida real existe)."
        )
    if conjunto.generador_sintetico:
        raise RespuestasSinteticas(
            "las respuestas de este artefacto las escribió un generador "
            "SINTÉTICO (`generador_sintetico: true`). Un stand-in produce texto "
            "hecho a medida de los chequeos mecánicos: su tasa de cita inventada "
            "es 0.00 por construcción. Corré el answer set contra el pin real "
            "desde el worker con GPU (runbook G9) y volvé a graduar."
        )
    if not conjunto.respuestas:
        raise RespuestasSinteticas(
            "el answer set no tiene ninguna respuesta corrida. 0 de 0 no es "
            "`0.00`: es una medición que no ocurrió, y publicarla como tasa "
            "reporta ausencia de fallas donde hay ausencia de datos."
        )


@dataclass(frozen=True)
class ParAbstencionE2E:
    """The END-TO-END pair: measured post-exclusion, on the SERVED outcome.

    Never merged into the retrieval-level LOOCV pair and never substituted by it
    (`design.md:841-852`). `AbstentionPolicy` decides on the retrieved set; the
    privacy exclusion runs AFTER it and can empty the payload, producing an
    abstention the policy never chose. Counting that where the policy sits would
    attribute the privacy gate's behaviour to the retriever.
    """

    n: int
    debian_abstenerse: int
    abstuvieron: int
    aciertos: int
    abstenciones_por_exclusion: int

    @property
    def recall(self) -> float | None:
        if not self.debian_abstenerse:
            return None
        return self.aciertos / self.debian_abstenerse

    @property
    def precision(self) -> float | None:
        if not self.abstuvieron:
            return None
        return self.aciertos / self.abstuvieron


def par_abstencion_e2e(conjunto: ConjuntoRespuestas) -> ParAbstencionE2E:
    """Recall and precision over the served outcomes.

    An exclusion-driven abstention is a TRUE abstention for recall (no answer was
    served) and counts AGAINST precision when the question was answerable — which
    is the honest accounting the design spells out, and the reason
    `abstenciones_por_exclusion` is reported beside the pair rather than inside it.
    """
    debian = sum(1 for r in conjunto.respuestas if r.debe_abstenerse)
    abstuvieron = sum(1 for r in conjunto.respuestas if r.abstuvo)
    aciertos = sum(1 for r in conjunto.respuestas if r.abstuvo and r.debe_abstenerse)
    return ParAbstencionE2E(
        n=conjunto.n_respuestas,
        debian_abstenerse=debian,
        abstuvieron=abstuvieron,
        aciertos=aciertos,
        abstenciones_por_exclusion=sum(
            1 for r in conjunto.respuestas if r.abstuvo and r.abstencion_por_exclusion
        ),
    )


def muestra_de_regrado(n_afirmaciones: int) -> int:
    """How many claims the intra-rater second pass must cover.

    `max(15, ceil(0.10 * n))`. The floor is the load-bearing half: 10% of 90
    claims is 9, and an agreement figure over 9 items moves 0.11 per
    disagreement — the same sample inflation this harness refuses elsewhere,
    wearing the opposite sign.
    """
    return max(PISO_REGRADO, math.ceil(FRACCION_REGRADO * n_afirmaciones))


@dataclass(frozen=True)
class MetricasRespuestas:
    """Every published answer-level figure, with the `n` each one rests on."""

    n_respuestas: int
    n_afirmaciones: int
    distribucion_afirmaciones: Mapping[int, int]
    n_claves_citadas: int
    n_claves_inventadas: int
    n_lineas_sustantivas: int
    n_lineas_sin_cita: int
    respuestas_con_cita_inventada: tuple[str, ...]
    n_sostenidas: int
    n_parciales: int
    n_contradichas: int
    n_regradadas: int
    n_regrado_requerido: int
    acuerdos_regrado: int
    par_e2e: ParAbstencionE2E
    motivos_no_evaluable: tuple[str, ...]

    @property
    def tasa_cita_inventada(self) -> float | None:
        if not self.n_claves_citadas:
            return None
        return self.n_claves_inventadas / self.n_claves_citadas

    @property
    def tasa_afirmacion_sin_cita(self) -> float | None:
        if not self.n_lineas_sustantivas:
            return None
        return self.n_lineas_sin_cita / self.n_lineas_sustantivas

    @property
    def tasa_sostenida(self) -> float | None:
        if not self.n_afirmaciones:
            return None
        return self.n_sostenidas / self.n_afirmaciones

    @property
    def tasa_contradicha(self) -> float | None:
        if not self.n_afirmaciones:
            return None
        return self.n_contradichas / self.n_afirmaciones

    @property
    def acuerdo_intra_evaluador(self) -> float | None:
        """`None` when the second pass is too thin to publish (`design.md:877-882`).

        Below the floor the figure is reported as `not-evaluable`, never as a
        number — the same discipline the retrieval spec uses below n = 20.
        """
        if self.n_afirmaciones < PISO_REGRADO:
            return None
        if self.n_regradadas < self.n_regrado_requerido:
            return None
        return self.acuerdos_regrado / self.n_regradadas

    @property
    def evaluable(self) -> bool:
        return not self.motivos_no_evaluable


def puntuar(conjunto: ConjuntoRespuestas) -> MetricasRespuestas:
    """The deterministic half of G7, scored against the recorded payload.

    Membership uses `generacion.claves_citadas` and the uncited-claim rule uses
    `generacion.lineas_sustantivas` — the SAME functions the pre-serve check
    runs. A second implementation of "what counts as a claim" would publish a
    rate for a function production does not have.
    """
    citadas_total = 0
    inventadas_total = 0
    con_inventada: list[str] = []
    lineas_total = 0
    sin_cita_total = 0
    sostenidas = parciales = contradichas = 0
    regradadas = acuerdos = 0

    for respuesta in conjunto.respuestas:
        payload = frozenset(respuesta.claves_payload)
        citadas = generacion.claves_citadas(respuesta.texto)
        inventadas = citadas - payload
        citadas_total += len(citadas)
        inventadas_total += len(inventadas)
        if inventadas:
            con_inventada.append(respuesta.id)

        lineas_total += len(generacion.lineas_sustantivas(respuesta.texto))
        sin_cita_total += len(generacion.afirmaciones_sin_cita(respuesta.texto))

        por_id = {a.id: a for a in respuesta.afirmaciones}
        for afirmacion in respuesta.afirmaciones:
            if afirmacion.grado == "sostenida":
                sostenidas += 1
            elif afirmacion.grado == "parcial":
                parciales += 1
            else:
                contradichas += 1
        for id_afirmacion, grado in respuesta.regrado.items():
            original = por_id.get(id_afirmacion)
            if original is None:
                raise ConjuntoRespuestasInvalido(
                    f"{respuesta.id}: el re-grado nombra la afirmación "
                    f"{id_afirmacion!r}, que no existe en esta respuesta"
                )
            regradadas += 1
            acuerdos += int(original.grado == grado)

    motivos: list[str] = []
    if conjunto.n_respuestas < N_MINIMO_RESPUESTAS:
        motivos.append(
            f"n_respuestas = {conjunto.n_respuestas} < {N_MINIMO_RESPUESTAS}: el "
            "conjunto ratificado se mide en RESPUESTAS, no en afirmaciones "
            "(decisión 0.6, `design.md:864-868`)."
        )
    requerido = muestra_de_regrado(conjunto.n_afirmaciones)
    if conjunto.n_afirmaciones < PISO_REGRADO:
        motivos.append(
            f"n_afirmaciones = {conjunto.n_afirmaciones} < {PISO_REGRADO}: el "
            "acuerdo intra-evaluador se reporta `not-evaluable`, nunca como número."
        )
    elif regradadas < requerido:
        motivos.append(
            f"re-grado = {regradadas} de {requerido} requeridas "
            f"(max({PISO_REGRADO}, {FRACCION_REGRADO:.0%} de "
            f"{conjunto.n_afirmaciones})): el acuerdo intra-evaluador queda "
            "`not-evaluable`."
        )

    return MetricasRespuestas(
        n_respuestas=conjunto.n_respuestas,
        n_afirmaciones=conjunto.n_afirmaciones,
        distribucion_afirmaciones=conjunto.distribucion_afirmaciones,
        n_claves_citadas=citadas_total,
        n_claves_inventadas=inventadas_total,
        n_lineas_sustantivas=lineas_total,
        n_lineas_sin_cita=sin_cita_total,
        respuestas_con_cita_inventada=tuple(con_inventada),
        n_sostenidas=sostenidas,
        n_parciales=parciales,
        n_contradichas=contradichas,
        n_regradadas=regradadas,
        n_regrado_requerido=requerido,
        acuerdos_regrado=acuerdos,
        par_e2e=par_abstencion_e2e(conjunto),
        motivos_no_evaluable=tuple(motivos),
    )


@dataclass(frozen=True)
class BarraRespuestas:
    nombre: str
    valor: float | None
    limite: float
    comparador: str
    fuente: str
    ratificada: bool = True

    @property
    def pasa(self) -> bool | None:
        """`None` when the bar is not ratified or the figure does not exist.

        Three states, never two: a bar nobody ratified and a bar with no
        measurement both have to be distinguishable from a bar that failed.
        """
        if not self.ratificada or self.valor is None:
            return None
        if self.comparador == "<=":
            return self.valor <= self.limite
        if self.comparador == "==":
            return self.valor == self.limite
        return self.valor >= self.limite


def barras(metricas: MetricasRespuestas) -> tuple[BarraRespuestas, ...]:
    """The spec'd bars, scored — and the proposed one, printed without a verdict."""
    par = metricas.par_e2e
    return (
        BarraRespuestas(
            "invented-citation rate",
            metricas.tasa_cita_inventada,
            BARRA_CITA_INVENTADA,
            "<=",
            "payload post-exclusión (misma llamada que el request)",
        ),
        BarraRespuestas(
            "uncited-claim rate",
            metricas.tasa_afirmacion_sin_cita,
            BARRA_AFIRMACION_SIN_CITA,
            "<=",
            "líneas sustantivas (misma regla que el chequeo pre-serve)",
        ),
        BarraRespuestas(
            "abstención e2e recall",
            par.recall,
            BARRA_ABSTENCION_RECALL,
            "==",
            "salida SERVIDA, post-exclusión",
        ),
        BarraRespuestas(
            "abstención e2e precision",
            par.precision,
            BARRA_ABSTENCION_PRECISION,
            ">=",
            "salida SERVIDA, post-exclusión",
        ),
        BarraRespuestas(
            "fully-supported claim rate",
            metricas.tasa_sostenida,
            PROPUESTA_SOSTENIDA,
            ">=",
            "graduado por el owner",
            ratificada=False,
        ),
        BarraRespuestas(
            "claims contradicted by their cited unit",
            metricas.tasa_contradicha,
            PROPUESTA_CONTRADICHA,
            "<=",
            "graduado por el owner",
            ratificada=False,
        ),
    )


# ---------------------------------------------------------------------------
# The seam the report renders through
# ---------------------------------------------------------------------------


MOTIVO_NO_CORRIDO = (
    "El bloque de métricas por respuesta no se puntuó en esta corrida: no se pasó "
    "`--answer-set`. Las respuestas las produce el worker con GPU (runbook G9); "
    "este arnés las gradúa y las puntúa, nunca las escribe."
)


@dataclass(frozen=True)
class EntradaRespuestas:
    """A scored answer set, or the stated reason there is none.

    One argument instead of three, exactly like `eval/router.py::EntradaRouter`:
    the metrics without the pins they were computed under are figures nobody can
    audit, so bundling them makes the illegal combination unconstructible.
    """

    conjunto: ConjuntoRespuestas | None = None
    metricas: MetricasRespuestas | None = None
    motivo_no_evaluable: str | None = None

    def __post_init__(self) -> None:
        if (self.conjunto is None) != (self.metricas is None):
            raise ConjuntoRespuestasInvalido(
                "un conjunto y sus métricas viajan juntos: unas métricas sin sus "
                "pines no se pueden auditar, y un conjunto sin métricas no dice nada."
            )
        if self.conjunto is None and not self.motivo_no_evaluable:
            raise ConjuntoRespuestasInvalido(
                "una entrada sin resultado tiene que nombrar por qué: "
                "`not-evaluable` sin razón es indistinguible de una sección que "
                "alguien se olvidó de llenar."
            )

    @classmethod
    def no_evaluable(cls, motivo: str) -> "EntradaRespuestas":
        return cls(motivo_no_evaluable=motivo)


def _fmt(valor: float | None, decimales: int = 3) -> str:
    return "n/d" if valor is None else f"{valor:.{decimales}f}"


def pasa_publicable(barra: BarraRespuestas, *, evaluable: bool) -> bool | None:
    """`barra.pasa`, but `None` while the SET itself is not evaluable.

    The bar arithmetic is fine on three answers — every citation is in its
    payload, so `invented-citation rate` is `0.000` and clears a `<= 0.00`
    bar. What is not fine is printing that as a pass: it is a rate over a
    sample the ratified minimum (`decisión 0.6`) already rejected, and a `sí`
    in a table is the single most quotable cell in this report. The retrieval
    harness applies exactly this rule below n = 20 (`GoNoGo.veredicto`), and a
    reader must not be able to lift the answer-level row out of the caveat
    printed under it.
    """
    return None if not evaluable else barra.pasa


def _veredicto(barra: BarraRespuestas, *, evaluable: bool) -> str:
    if not barra.ratificada:
        return ESTADO_BARRA_NO_RATIFICADA
    if pasa_publicable(barra, evaluable=evaluable) is None:
        return ESTADO_NO_EVALUABLE
    return "sí" if barra.pasa else "NO"


def bloque_no_evaluable(motivo: str) -> list[str]:
    return [
        "## Métricas por respuesta (answer-level)",
        "",
        f"**`{ESTADO_NO_EVALUABLE}`** — las métricas por respuesta NO se puntuaron.",
        "",
        motivo,
    ]


def bloque_para(entrada: EntradaRespuestas | None) -> list[str]:
    """The answer-level section of the report, always present, never invented."""
    if entrada is None:
        return bloque_no_evaluable(MOTIVO_NO_CORRIDO)
    if entrada.conjunto is None or entrada.metricas is None:
        return bloque_no_evaluable(entrada.motivo_no_evaluable or MOTIVO_NO_CORRIDO)

    conjunto, metricas = entrada.conjunto, entrada.metricas
    par = metricas.par_e2e
    lineas = [
        "## Métricas por respuesta (answer-level)",
        "",
        f"- estado del conjunto: {conjunto.estado}",
        f"- pines: prompt_version `{conjunto.prompt_version}` · modelo "
        f"`{conjunto.provider_model_pin}` · corpus_sha `{conjunto.corpus_sha}` · "
        f"expected_clasificacion sha256 `{conjunto.expected_clasificacion_sha256}`",
        f"- **n_respuestas = {metricas.n_respuestas}** (mínimo ratificado "
        f"{N_MINIMO_RESPUESTAS}) · **n_afirmaciones = {metricas.n_afirmaciones}**",
        "- distribución de afirmaciones por respuesta: "
        + (
            ", ".join(
                f"{cuantas}→{respuestas}"
                for cuantas, respuestas in sorted(metricas.distribucion_afirmaciones.items())
            )
            or "—"
        ),
        "",
        "> `n` cuenta **respuestas**, no afirmaciones: una respuesta lleva varias "
        "afirmaciones, así que 30 leído como afirmaciones serían seis o siete "
        "respuestas con un número más grande encima. La distribución está arriba "
        "para que se vea si la tasa se apoya en treinta respuestas independientes "
        "o en una sola muy larga.",
        "",
        "| métrica | valor | barra | fuente | n | ¿pasa? |",
        "|---|---:|---:|---|---:|---|",
    ]
    denominadores = {
        "invented-citation rate": metricas.n_claves_citadas,
        "uncited-claim rate": metricas.n_lineas_sustantivas,
        "abstención e2e recall": par.debian_abstenerse,
        "abstención e2e precision": par.abstuvieron,
        "fully-supported claim rate": metricas.n_afirmaciones,
        "claims contradicted by their cited unit": metricas.n_afirmaciones,
    }
    for barra in barras(metricas):
        comparador = {"<=": "≤", ">=": "≥", "==": "="}[barra.comparador]
        lineas.append(
            f"| {barra.nombre} | {_fmt(barra.valor)} | {comparador} {barra.limite:.2f} "
            f"| {barra.fuente} | {denominadores[barra.nombre]} "
            f"| {_veredicto(barra, evaluable=metricas.evaluable)} |"
        )

    lineas += [
        "",
        "### Abstención end-to-end (post-exclusión)",
        "",
        f"- respuestas: {par.n} · debían abstenerse: {par.debian_abstenerse} · "
        f"se abstuvieron: {par.abstuvieron} · aciertos: {par.aciertos}",
        f"- **abstenciones producidas por la exclusión de privacidad: "
        f"{par.abstenciones_por_exclusion}**",
        "",
        "> Esta fila es **propia** y no se fusiona con el par LOOCV de "
        "recuperación. `AbstentionPolicy` decide sobre el conjunto RECUPERADO; la "
        "exclusión de privacidad corre después y puede vaciar el payload, "
        "produciendo una abstención que la política nunca eligió. Una abstención "
        "por exclusión es una abstención VERDADERA para el recall (no se sirvió "
        "nada) y cuenta EN CONTRA de la precisión si el corpus sí tenía una norma "
        "aplicable en una unidad excluida: el lector tiene derecho a ver cuánto de "
        "la tasa de abstención lo produce la compuerta de privacidad.",
        "",
        "### Acuerdo intra-evaluador",
        "",
        f"- afirmaciones re-graduadas: {metricas.n_regradadas} de "
        f"{metricas.n_regrado_requerido} requeridas "
        f"(max({PISO_REGRADO}, {FRACCION_REGRADO:.0%} de {metricas.n_afirmaciones}))",
        f"- acuerdo: {_fmt(metricas.acuerdo_intra_evaluador)}",
        "",
        "> Hay un solo evaluador (el owner), así que el acuerdo INTER-evaluador no "
        "existe; lo que sí es obtenible es el intra-evaluador, en una segunda "
        "pasada ciega a las etiquetas de la primera y al menos un día después. Una "
        "fidelidad de 0.97 al lado de un acuerdo de 0.80 es un hecho distinto de "
        "la misma cifra al lado de 0.98.",
        "",
        f"> **`{ESTADO_BARRA_NO_RATIFICADA}`** para las dos últimas filas de la "
        "tabla: `fully-supported >= 0.95` y `contradichas = 0.00` son PROPUESTAS "
        "esperando ratificación del owner (`design.md:892-895`), y nada acá "
        "convierte una barra sin ratificar en un pase ni en una falla. Las tres "
        "primeras sí están en el spec de generación y sí se puntúan.",
    ]
    if metricas.motivos_no_evaluable:
        lineas += [
            "",
            f"> El conjunto NO es evaluable, así que las barras ratificadas de la "
            f"tabla salen `{ESTADO_NO_EVALUABLE}` y no `sí`/`NO`. Los VALORES "
            "siguen impresos porque son aritmética real sobre lo que hay; lo que "
            "no puede emitirse es el veredicto, que es la celda que se cita sola.",
            "",
            "**Motivos de `not-evaluable`:**",
            "",
        ]
        lineas += [f"- {motivo}" for motivo in metricas.motivos_no_evaluable]
    if metricas.respuestas_con_cita_inventada:
        lineas += [
            "",
            "**Respuestas con al menos una clave inventada** (una sola bloquea el "
            "serving, spec de generación): "
            + ", ".join(f"`{id}`" for id in metricas.respuestas_con_cita_inventada),
        ]
    return lineas


def json_para(entrada: EntradaRespuestas | None) -> dict[str, Any]:
    """The machine-readable twin. Same refusal, same labels."""
    if entrada is None:
        return {"evaluado": False, "motivo": MOTIVO_NO_CORRIDO}
    if entrada.conjunto is None or entrada.metricas is None:
        return {"evaluado": False, "motivo": entrada.motivo_no_evaluable or MOTIVO_NO_CORRIDO}

    conjunto, metricas = entrada.conjunto, entrada.metricas
    par = metricas.par_e2e
    return {
        "evaluado": True,
        "estado": conjunto.estado,
        "pines": {
            "prompt_version": conjunto.prompt_version,
            "provider_model_pin": conjunto.provider_model_pin,
            "corpus_sha": conjunto.corpus_sha,
            "expected_clasificacion_sha256": conjunto.expected_clasificacion_sha256,
        },
        "n_respuestas": metricas.n_respuestas,
        "n_afirmaciones": metricas.n_afirmaciones,
        "minimo_respuestas": N_MINIMO_RESPUESTAS,
        "distribucion_afirmaciones": {
            str(k): v for k, v in sorted(metricas.distribucion_afirmaciones.items())
        },
        "tasa_cita_inventada": metricas.tasa_cita_inventada,
        "n_claves_citadas": metricas.n_claves_citadas,
        "n_claves_inventadas": metricas.n_claves_inventadas,
        "respuestas_con_cita_inventada": list(metricas.respuestas_con_cita_inventada),
        "tasa_afirmacion_sin_cita": metricas.tasa_afirmacion_sin_cita,
        "n_lineas_sustantivas": metricas.n_lineas_sustantivas,
        "n_lineas_sin_cita": metricas.n_lineas_sin_cita,
        "tasa_sostenida": metricas.tasa_sostenida,
        "tasa_contradicha": metricas.tasa_contradicha,
        "n_sostenidas": metricas.n_sostenidas,
        "n_parciales": metricas.n_parciales,
        "n_contradichas": metricas.n_contradichas,
        "acuerdo_intra_evaluador": metricas.acuerdo_intra_evaluador,
        "n_regradadas": metricas.n_regradadas,
        "n_regrado_requerido": metricas.n_regrado_requerido,
        # Its OWN key, never merged into the retrieval-level pair.
        "abstencion_e2e": {
            "n": par.n,
            "debian_abstenerse": par.debian_abstenerse,
            "abstuvieron": par.abstuvieron,
            "aciertos": par.aciertos,
            "abstenciones_por_exclusion": par.abstenciones_por_exclusion,
            "recall": par.recall,
            "precision": par.precision,
            "medida_en": "salida servida, post-exclusión",
        },
        "evaluable": metricas.evaluable,
        "motivos_no_evaluable": list(metricas.motivos_no_evaluable),
        "barras": [
            {
                "nombre": barra.nombre,
                "valor": barra.valor,
                "limite": barra.limite,
                "comparador": barra.comparador,
                "fuente": barra.fuente,
                "ratificada": barra.ratificada,
                "pasa": pasa_publicable(barra, evaluable=metricas.evaluable),
            }
            for barra in barras(metricas)
        ],
    }


def cargar_y_puntuar(
    db: Session,
    *,
    ruta: Path | None = None,
    prompt_version: int,
    provider_model_pin: str,
    corpus_sha: str,
) -> EntradaRespuestas:
    """Load, check every pin, refuse a synthetic run, then score.

    Ordering is the property, and it mirrors `rag_eval.py`'s: the pure string
    comparisons run before the database is touched, and the database check runs
    before any arithmetic. A run refused at the pins costs nothing.
    """
    conjunto = cargar_conjunto_respuestas(ruta)
    verificar_pines(
        conjunto,
        prompt_version=prompt_version,
        provider_model_pin=provider_model_pin,
        corpus_sha=corpus_sha,
    )
    assert_publicable(conjunto)
    verificar_payload(db, conjunto)
    return EntradaRespuestas(conjunto=conjunto, metricas=puntuar(conjunto))


def ids_por_estado(respuestas: Sequence[RespuestaGraduada]) -> dict[str, list[str]]:
    """Traceability helper: which answer ids ended in each served state."""
    agrupado: dict[str, list[str]] = {}
    for respuesta in respuestas:
        agrupado.setdefault(respuesta.estado_servido, []).append(respuesta.id)
    return agrupado
