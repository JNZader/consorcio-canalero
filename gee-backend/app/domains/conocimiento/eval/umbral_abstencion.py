"""The shipped abstention threshold: seeded from the eval, pinned to its inputs.

Task 9.6, `design.md:897-904`.

**It is not a constant in code and not a number typed into an env file from
memory.** It is a config value *seeded from the eval artifact*, and the artifact
carries its own `(corpus_sha, embedding_modelo, embedding_revision_hf, n,
metodologia)` header so that a reader can tell what the number was calibrated
against without going to look for the run that produced it.

**Re-derivation is triggered by identity, not by a date.** Any change to
`corpus_sha`, or to the embedder identity — model **or** HF revision, the pair G0
compares — makes the shipped threshold a number calibrated for a different corpus
or a different vector space. Serving then refuses with
`base_de_conocimiento_no_lista` rather than answering against it, on the same
discipline as `verificar_corpus_sha` and for the same reason: the failure is
silent otherwise, and its symptom is an abstention rate that drifts without
anybody changing anything.

**What this module deliberately does NOT do: pick a bar.** Task 9.5 is BLOCKED on
owner decision 0.1, and the serving arm (`bm25_ce`) carries no ratified abstention
signal at all — the measured candidate, reranker confidence, scored WORSE than the
cosine one it would replace (LOOCV precision 0.489 at recall 1.000). So the shipped
artifact is `estado: no_derivado`, `umbral: null`, and `derivar_desde` REFUSES to
produce a threshold for a mode with no ratified signal rather than shipping
whatever the sweep happened to return. A file that carried a number here would
set the enablement gate to a value nobody chose, which is the exact failure the
`SenalAbstencionNoRatificada` refusal exists to prevent one layer up.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RUTA_UMBRAL = Path(__file__).with_name("umbral_abstencion.yaml")

ESTADO_DERIVADO = "derivado"
ESTADO_NO_DERIVADO = "no_derivado"


class UmbralAbstencionInvalido(RuntimeError):
    """The artifact does not satisfy its own header contract."""


class UmbralAbstencionDivergente(RuntimeError):
    """The shipped threshold was calibrated for a different corpus or vector space.

    Raised on `corpus_sha`, on `embedding_modelo` or on `embedding_revision_hf` —
    the last one included because two revisions of the same model id are two
    different vector spaces, and a cosine threshold is a statement about a space.
    Both operands are named, because "the threshold does not match" sends a
    person to read two files and naming the pair sends them to the one that moved.
    """


@dataclass(frozen=True)
class UmbralAbstencion:
    """The artifact, exactly as it is on disk."""

    estado: str
    corpus_sha: str | None
    embedding_modelo: str | None
    embedding_revision_hf: str | None
    n: int | None
    metodologia: str
    umbral: float | None
    motivo: str

    @property
    def derivado(self) -> bool:
        return self.estado == ESTADO_DERIVADO

    def exigir_umbral(self) -> float:
        """The threshold, or a refusal that says why there is none.

        Never a default. A caller that "just needs a number" is exactly the
        caller this artifact exists to stop, and handing back `0.0` would abstain
        on nothing while handing back `1.0` would abstain on everything — both
        are decisions about the gate, made here, by nobody.
        """
        if not self.derivado or self.umbral is None:
            raise UmbralAbstencionInvalido(
                f"el umbral de abstención está en estado {self.estado!r} y no hay "
                f"número que entregar. Motivo registrado: {self.motivo}"
            )
        return self.umbral


def cargar_umbral(ruta: Path | None = None) -> UmbralAbstencion:
    """Parse the artifact and check that a DERIVED one carries its whole header.

    A derived threshold with a missing pin is worse than no artifact: it would
    pass the identity check vacuously — `None == None` for a snapshot whose
    provenance is also absent — and serve a calibrated number against an unknown
    corpus.
    """
    ruta = ruta or RUTA_UMBRAL
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    estado = str(datos.get("estado", ESTADO_NO_DERIVADO))
    if estado not in (ESTADO_DERIVADO, ESTADO_NO_DERIVADO):
        raise UmbralAbstencionInvalido(
            f"{ruta.name}: estado {estado!r} desconocido "
            f"(esperado {ESTADO_DERIVADO!r} o {ESTADO_NO_DERIVADO!r})"
        )

    umbral = datos.get("umbral")
    artefacto = UmbralAbstencion(
        estado=estado,
        corpus_sha=None if datos.get("corpus_sha") is None else str(datos["corpus_sha"]),
        embedding_modelo=(
            None if datos.get("embedding_modelo") is None else str(datos["embedding_modelo"])
        ),
        embedding_revision_hf=(
            None
            if datos.get("embedding_revision_hf") is None
            else str(datos["embedding_revision_hf"])
        ),
        n=None if datos.get("n") is None else int(datos["n"]),
        metodologia=str(datos.get("metodologia", "")),
        umbral=None if umbral is None else float(umbral),
        motivo=str(datos.get("motivo", "")),
    )

    if artefacto.derivado:
        faltantes = [
            campo
            for campo in ("corpus_sha", "embedding_modelo", "n", "umbral", "metodologia")
            if not getattr(artefacto, campo)
        ]
        if faltantes:
            raise UmbralAbstencionInvalido(
                f"{ruta.name}: estado {ESTADO_DERIVADO!r} con el encabezado "
                f"incompleto ({', '.join(faltantes)}). Un umbral derivado SIN sus "
                "pines pasa la verificación de identidad de forma vacua y se sirve "
                "contra un corpus desconocido."
            )
    elif artefacto.umbral is not None:
        raise UmbralAbstencionInvalido(
            f"{ruta.name}: estado {ESTADO_NO_DERIVADO!r} con `umbral: "
            f"{artefacto.umbral}`. Un número guardado bajo 'no derivado' es el "
            "peor de los dos mundos: nadie lo ratificó y está ahí para que "
            "alguien lo lea."
        )
    return artefacto


def verificar_identidad(
    artefacto: UmbralAbstencion,
    *,
    corpus_sha: str,
    embedding_modelo: str | None,
    embedding_revision_hf: str | None,
) -> None:
    """Refuse when the shipped threshold does not belong to the active snapshot.

    A `no_derivado` artifact is NOT a mismatch and does not refuse here: there is
    no number, so nothing can be served against the wrong one. That state is
    task 9.5's territory (the enablement flag stays off) and not this check's.
    """
    if not artefacto.derivado:
        return

    divergencias = [
        (nombre, esperado, vigente)
        for nombre, esperado, vigente in (
            ("corpus_sha", artefacto.corpus_sha, corpus_sha),
            ("embedding_modelo", artefacto.embedding_modelo, embedding_modelo),
            ("embedding_revision_hf", artefacto.embedding_revision_hf, embedding_revision_hf),
        )
        if esperado != vigente
    ]
    if not divergencias:
        return

    detalle = "; ".join(
        f"{nombre}: el umbral se calibró con {esperado!r} y el snapshot activo es {vigente!r}"
        for nombre, esperado, vigente in divergencias
    )
    raise UmbralAbstencionDivergente(
        f"el umbral de abstención vigente no corresponde a esta base — {detalle}. "
        "Servir contra él sería aplicar un corte calibrado para otro corpus o para "
        "otro espacio vectorial: dos revisiones del mismo modelo son dos espacios "
        "distintos, y un umbral de coseno es una afirmación sobre un espacio. "
        "Re-derivá el umbral con `scripts/rag_eval.py` sobre este snapshot."
    )


def derivar_desde(corrida: Any, procedencia: Any) -> UmbralAbstencion:
    """Build the artifact from a scored run — or state why it cannot be derived.

    `corrida` is a `harness.ResultadoModo` and `procedencia` a
    `ProcedenciaEmbeddings`; both are typed loosely on purpose, because importing
    the harness here would make `service` -> `eval` -> `service` a cycle and this
    module is on the SERVING side of that boundary.

    Two refusals, both producing a `no_derivado` artifact with its reason rather
    than an exception: the caller is a report writer, and killing a whole eval
    because a threshold could not be derived would lose the measurement that
    explains why.
    """
    if not getattr(corrida, "senal_ratificada", True):
        return UmbralAbstencion(
            estado=ESTADO_NO_DERIVADO,
            corpus_sha=None,
            embedding_modelo=None,
            embedding_revision_hf=None,
            n=None,
            metodologia="",
            umbral=None,
            motivo=(
                f"el modo {corrida.modo!r} no tiene señal de abstención ratificada "
                "(decisión 0.1 del owner, ABIERTA). La señal candidata medida — "
                "confianza del reranker — resultó PEOR que la coseno que "
                "reemplazaría: precisión LOOCV 0.489 con recall 1.000. Derivar un "
                "umbral igual dejaría la compuerta en el valor que el sistema ya "
                "tiene, presentado como una decisión."
            ),
        )
    if procedencia is None or getattr(procedencia, "sintetico", False):
        return UmbralAbstencion(
            estado=ESTADO_NO_DERIVADO,
            corpus_sha=None,
            embedding_modelo=None,
            embedding_revision_hf=None,
            n=None,
            metodologia="",
            umbral=None,
            motivo=(
                "el snapshot no tiene procedencia real de embeddings. Un umbral "
                "calibrado sobre vectores sintéticos es un corte sobre ruido de "
                "hash con forma de decisión."
            ),
        )

    loocv = corrida.loocv
    return UmbralAbstencion(
        estado=ESTADO_DERIVADO,
        corpus_sha=procedencia.corpus_sha,
        embedding_modelo=procedencia.modelo,
        embedding_revision_hf=procedencia.revision_hf,
        n=loocv.n,
        metodologia=(
            f"LOOCV sobre el modo {corrida.modo!r}; señal: {corrida.fuente_senal}; "
            "regla: mayor precisión entre los umbrales que alcanzan recall 1.00, "
            "desempate por el umbral menor; grilla = los valores observados, sin "
            "agregar candidatos."
        ),
        umbral=loocv.umbral_shipped,
        motivo="",
    )


def volcar(artefacto: UmbralAbstencion) -> dict[str, Any]:
    """The artifact as a plain mapping, in the header order the design names."""
    return {
        "estado": artefacto.estado,
        "corpus_sha": artefacto.corpus_sha,
        "embedding_modelo": artefacto.embedding_modelo,
        "embedding_revision_hf": artefacto.embedding_revision_hf,
        "n": artefacto.n,
        "metodologia": artefacto.metodologia,
        "umbral": artefacto.umbral,
        "motivo": artefacto.motivo,
    }
