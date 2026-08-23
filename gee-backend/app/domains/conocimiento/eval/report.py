"""The V0 deliverable: a markdown eval report plus its machine-readable twin.

Three properties are load-bearing, and each one is a refusal rather than a
convention:

1. **A synthetic snapshot cannot render as an eval.** `DeterministicEmbedder`
   exists so the pipeline can be exercised without a 2.2 GB model, and a report
   produced over hash noise would be shaped exactly like a real one — same
   tables, same verdict line, same authority. RAG3-001 closed that at the load
   and query layers; this closes it at the layer that publishes. The only way
   past is an explicit flag, and what comes out then is titled SMOKE RUN, named
   `retrieval-eval-SINTETICO-…` so it cannot be mistaken inside `docs/rag/`, and
   carries no verdict at all.

2. **Provenance is read from the DATABASE, not from a sidecar.** The dump path
   is `vectors-{sha8}.copy`, so a second batch over the same corpus revision
   overwrites both the artifact and the sidecar that described it. `rag_corpus`'s
   five `conocimiento_004` columns are the only copy that survives, and they are
   what this report prints.

3. **Time is an argument.** Nothing here reads a clock — a test asserts that over
   the module's own AST. Same database plus same gold set produces a
   byte-identical document apart from the header it was handed.

**Point 1 has two halves, and only one of them used to exist.** RAG3-001 was
written when every mode was ordered by RRF over a vector leg, so "was this
fabricated?" had exactly one answer: `embedding_sintetico`. `bm25_ce` reads no
vector column at all and its order is the cross-encoder's alone, so a
`DeterministicReranker` fabricates the entire ranking while the snapshot's
embedding provenance stays perfectly real. The gate now refuses on either
source, with the same treatment: no verdict, `SINTETICO-` in the filename.

**What the database cannot tell us, and is therefore not printed as if it could
(ledger RAG4-002).** D6 asks the report to pin torch version and device "for both
legs". `conocimiento_004` records model, HF revision, `sintetico`, the artifact
sha256 and a timestamp — not the batch's torch build and not its device. Those
live only in the sidecar, which point 2 just explained is not durable. So the
corpus-side row says `no registrado en la base` and names the artifact sha256 as
the pointer to the sidecar that has it. Printing THIS process's torch and device
next to the corpus leg would be the actual falsehood: those vectors came off a
CUDA box this process has never seen.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domains.conocimiento.embedding import runtime_versions
from app.domains.conocimiento.eval.harness import (
    MINIMO_RESPONDIBLES,
    ResultadoEval,
    ResultadoModo,
    decidir_go_no_go,
    resumen_metodologico,
)
from app.domains.conocimiento.fusion import RRF_K
from app.domains.conocimiento.service import FTS_OPERADOR, LEG_LIMIT, ProcedenciaEmbeddings

NO_REGISTRADO = "no registrado en la base"
ETIQUETA_SMOKE = "SMOKE RUN — NOT AN EVAL"


class EvalSinteticoNoEsEval(RuntimeError):
    """Something in this run was produced by a stand-in, so it is not an eval.

    Either the snapshot's vectors or a mode's RANKER. The two are independent
    sources of the same failure and both carry the same consequence, which is why
    they share one exception rather than being told apart at the call site.
    """


@dataclass(frozen=True)
class ReporteEscrito:
    markdown: Path
    json: Path


def nombre_de_archivo(corpus_sha: str, generado_en: dt.datetime, *, sintetico: bool) -> str:
    """`retrieval-eval-{sha8}-{YYYY-MM-DD}.md`, with a loud infix when synthetic.

    The infix is in the FILENAME and not only in the body because `docs/rag/`
    will eventually hold several of these, and the thing a person reads first is
    the file list.
    """
    marca = "SINTETICO-" if sintetico else ""
    return f"retrieval-eval-{marca}{corpus_sha[:8]}-{generado_en.date().isoformat()}.md"


def _rankers_sinteticos(resultado: ResultadoEval | None) -> tuple[str, ...]:
    """The modes of this run whose ORDER came from a stand-in ranker, sorted.

    The second half of the RAG3-001 refusal, and it was missing. Under `bm25_ce`
    the retrieval order is the cross-encoder's alone, so a `DeterministicReranker`
    substitutes for the model exactly as `DeterministicEmbedder` substitutes for
    BGE-M3 — and the report it produces has the same tables, the same bars and
    the same verdict line over an order that is hash noise. Gating only on
    `ProcedenciaEmbeddings` let that through on the one arm that has no embedding
    provenance to gate at all: `bm25_ce` reads no vector column, so its
    `procedencia.sintetico` says nothing about what ranked it.
    """
    if resultado is None:
        return ()
    return tuple(
        sorted(
            modo for modo, corrida in resultado.por_modo.items() if corrida.ranker_sintetico is True
        )
    )


def _gate_sintetico(
    procedencia: ProcedenciaEmbeddings | None,
    permitir: bool,
    *,
    resultado: ResultadoEval | None = None,
) -> bool:
    """Returns whether this is a smoke run. Raises when it is one and is not allowed.

    Two independent sources of fabrication, one gate and one treatment: synthetic
    EMBEDDINGS (the snapshot was loaded by a deterministic stand-in) and a
    synthetic RANKER (the order came from one). Either alone makes the document a
    smoke run — no verdict, `SINTETICO-` in the filename — because a table cannot
    be half a measurement.
    """
    embeddings_sinteticos = bool(procedencia is not None and procedencia.sintetico)
    modos_sinteticos = _rankers_sinteticos(resultado)
    sintetico = embeddings_sinteticos or bool(modos_sinteticos)
    if not sintetico or permitir:
        return sintetico

    motivos: list[str] = []
    if embeddings_sinteticos:
        snapshot = procedencia.corpus_sha if procedencia else "?"
        modelo = procedencia.modelo if procedencia else None
        motivos.append(
            f"snapshot {snapshot} was loaded with SYNTHETIC vectors "
            f"(embedding_modelo={modelo!r}, embedding_sintetico=true)"
        )
    if modos_sinteticos:
        rankers = sorted(
            {
                resultado.por_modo[modo].ranker_modelo or "?"
                for modo in modos_sinteticos
                if resultado is not None
            }
        )
        motivos.append(
            f"mode(s) {', '.join(modos_sinteticos)} were ranked by a SYNTHETIC "
            f"stand-in ({', '.join(rankers)}) rather than by "
            "BAAI/bge-reranker-v2-m3"
        )
    raise EvalSinteticoNoEsEval(
        "; ".join(motivos) + ". "
        "Refusing to render an eval report: every table would be shaped like a "
        "measurement and none of it would be one. Load real vectors "
        "(scripts/rag_embed_batch.py + scripts/rag_load_vectors.py) and rank with "
        "the pinned cross-encoder, or pass permitir_sintetico=True / "
        "--allow-synthetic to get a clearly-labelled SMOKE RUN that carries no "
        "verdict."
    )


def _fmt(valor: float | None, decimales: int = 3) -> str:
    """`n/d` for a metric with no denominator. Never `0.000`, which is a result."""
    if valor is None:
        return "n/d"
    return f"{valor:.{decimales}f}"


#: Metrics whose denominator is narrower than `n_respondibles`. A mean over a
#: subset and a mean over the whole answerable set are different claims, so the
#: table states the `n` beside the value rather than letting them look alike.
_DENOMINADOR_PROPIO = {
    "norma-vs-secundaria": "n_separacion",
    "vigencia-correctness": "n_vigencia",
    "citation-precision": "n_citation_precision",
}


def _tabla_metricas(corrida: ResultadoModo, go_no_go) -> list[str]:
    lineas = [
        "| métrica | valor | barra | fuente | n | ¿pasa? |",
        "|---|---:|---:|---|---:|---|",
    ]
    for barra in go_no_go.barras:
        comparador = "=" if barra.comparador == "==" else "≥"
        atributo = _DENOMINADOR_PROPIO.get(barra.nombre)
        if atributo is not None:
            n = str(getattr(corrida.metricas, atributo))
        elif barra.fuente == "LOOCV held-out":
            n = str(corrida.loocv.n)
        else:
            n = str(corrida.metricas.n_respondibles)
        lineas.append(
            f"| {barra.nombre} | {_fmt(barra.valor)} | {comparador} {barra.minimo:.2f} "
            f"| {barra.fuente} | {n} | {'sí' if barra.pasa else 'NO'} |"
        )
    return lineas


def _bloque_metodologia(corrida: ResultadoModo) -> list[str]:
    resumen = resumen_metodologico(corrida)
    lineas = [
        "**Metodología (divulgación obligatoria — design.md D6)**",
        "",
        f"- Señal de abstención: {resumen['senal']}",
        f"- Regla de selección: {resumen['regla_de_seleccion']}",
        f"- Validación: {resumen['validacion']} (leave-one-out)",
        f"- n = {resumen['n']}",
        f"- Umbral shipped (ajustado sobre el conjunto completo): "
        f"{resumen['umbral_shipped']:.6f}"
        + (" — por FALLBACK" if resumen["umbral_shipped_fallback"] else ""),
        f"- Par que decide el go/no-go (**LOOCV held-out**): "
        f"recall {_fmt(resumen['held_out_recall'])} · precision {_fmt(resumen['held_out_precision'])}",
        f"- Par de la misma muestra: recall {_fmt(resumen['same_sample_recall'])} · "
        f"precision {_fmt(resumen['same_sample_precision'])} "
        f"— **{resumen['etiqueta_same_sample']}**, no decide nada",
        f"- folds con fallback: {resumen['folds_con_fallback']} de {resumen['n']} "
        f"({resumen['fraccion_fallback']:.1%}) — un fallback frecuente es en sí mismo "
        "una señal de no-go",
    ]
    if resumen["senal_constante"]:
        lineas += [
            "",
            "> ⚠️ **SEÑAL CONSTANTE** — todas las preguntas produjeron el mismo "
            "valor, así que la grilla tiene un solo candidato y el barrido de "
            "umbrales no barrió nada: el resultado quedó fijado antes de mirar los "
            "datos. Las cifras de abstención de este modo no son una medición.",
        ]
    return lineas


def _no_corrio(cobertura, leg: str) -> str:
    """Annotate a count that is 100 % only because the leg was never asked to run.

    Without it the `fts` block reads "sin candidatos vector: 52 (100.0%)", which
    is true and says nothing — and a reader who has learned that the coverage
    block states the obvious stops reading the one line that carries RAG4-001.
    """
    return "" if leg in cobertura.legs_corridas else "  — esta pierna no corre en este modo"


def _bloque_cobertura(corrida: ResultadoModo) -> list[str]:
    cobertura = corrida.cobertura
    lineas = [
        "**Cobertura de las piernas**",
        "",
        f"- operador de la pierna léxica: {FTS_OPERADOR}",
        f"- piernas que corrieron en este modo: {', '.join(cobertura.legs_corridas) or '—'}",
        f"- preguntas corridas: {cobertura.n_preguntas}",
        f"- sin candidatos FTS: {cobertura.sin_candidatos_fts} "
        f"({cobertura.fraccion_sin_candidatos_fts:.1%}){_no_corrio(cobertura, 'fts')}",
        f"- sin candidatos vector: {cobertura.sin_candidatos_vector} "
        f"({cobertura.fraccion_sin_candidatos_vector:.1%}){_no_corrio(cobertura, 'vector')}",
    ]
    if cobertura.leg_fts_degradada:
        lineas += [
            "",
            "> ⚠️ **LEG DEGRADADA (FTS)** — la mayoría de las preguntas no obtuvo "
            "ningún candidato léxico. Con el operador CONJUNTIVO original esto era "
            "el estado normal y no decía nada del índice (ledger RAG4-001); con la "
            "disyunción vigente significa que las preguntas y los artículos no "
            "comparten ni un lexema, que es una brecha de vocabulario real. En "
            "cualquiera de los dos casos las métricas de este modo describen la "
            "consulta antes que la calidad del índice.",
        ]
    if cobertura.leg_vector_degradada:
        lineas += [
            "",
            "> ⚠️ **LEG DEGRADADA (vector)** — la mayoría de las preguntas no obtuvo "
            "candidatos vectoriales.",
        ]
    if corrida.hibrido_degenerado:
        lineas += [
            "",
            "> ⚠️ **HÍBRIDO DEGENERADO** — una de las dos piernas no aportó nada en "
            "la mayoría de las preguntas, así que este bloque NO es una fusión: es "
            "mayormente la otra pierna sola, con etiqueta de híbrido.",
        ]
    return lineas


#: Bounded rendering of a key set in the markdown block, per the RAG3-003
#: convention already used by `rag_load_vectors._muestra`. The exempt set is
#: "every unit of the snapshot with no vector", which is three units under
#: BGE-M3's window and can be an order of magnitude more under E5's 512 — an
#: unbounded bullet list would bury the two numbers the block exists to state.
#: Only the MARKDOWN is capped: the JSON twin keeps the complete list, because
#: truncating a machine-readable field is data loss rather than legibility.
MAX_CLAVES_EN_BLOQUE = 10


def _bullets_acotados(valores: tuple[str, ...], *, code: bool) -> list[str]:
    """`- x` … `- … (+N more)` — the first ten, then an honest count of the rest."""
    visibles = valores[:MAX_CLAVES_EN_BLOQUE]
    lineas = [f"  - `{v}`" if code else f"  - {v}" for v in visibles]
    resto = len(valores) - len(visibles)
    if resto:
        lineas.append(f"  - … (+{resto} more)")
    return lineas


def _bloque_exencion(corrida: ResultadoModo) -> list[str]:
    """Disclose the over-ceiling exemption, in every mode, including "none".

    Printed even when nothing is exempt, and that is the point: a block that only
    appears when it changed a number is a block a reader learns to expect to be
    absent, so its absence stops being informative. Here absence and "0 items"
    are different facts — `fts` and `hybrid` never exempt anything by design,
    `vector` may exempt and happen not to — and both are stated.

    **The ceiling is named, not numbered** (ledger RJDB-101 ≡ RJDA-106). It is a
    property of the embedder that produced the batch — 8192 tokens for BGE-M3,
    512 for multilingual-e5-large — and nothing durable records it: the
    `conocimiento_004` provenance columns keep model, HF revision, `sintetico`,
    artifact sha256 and a timestamp, and the token ceiling lives only in the
    sidecar that RAG3-001 established is not durable. Printing `8192` under an
    E5 batch would be a fabricated number in the one block whose whole job is to
    explain why some units have no vector; deriving it from the model id would
    be a second source of truth that a `--max-length` override makes a lie. So
    the block says which ceiling it means and leaves the number to whoever can
    actually read it.
    """
    exencion = corrida.exencion
    if not exencion.aplica:
        return [
            "**Exención por ceiling de embedding**",
            "",
            "- no aplica en este modo: la pierna léxica alcanza las unidades sin "
            "vector, así que ningún ítem sale del denominador.",
        ]

    lineas = [
        "**Exención por ceiling de embedding**",
        "",
        f"- unidades del snapshot SIN vector: {len(exencion.claves)}",
    ]
    lineas += _bullets_acotados(exencion.claves, code=True)
    lineas += [
        f"- ítems del gold cuyas citas esperadas están TODAS sin vector: "
        f"{exencion.n_preguntas_exentas}",
    ]
    lineas += _bullets_acotados(exencion.preguntas, code=False)
    lineas += [
        "",
        "> Estas unidades superan el techo de tokens del modelo del batch (una "
        "propiedad del embedder, no una constante del sistema: la ventana de "
        "BGE-M3 y la de multilingual-e5-large difieren en un factor de 16). Por "
        "decisión de diseño (design.md D3) se ingieren ENTERAS, **nunca se "
        "truncan**, siguen siendo recuperables por FTS y no se embeben: son "
        "**FTS-only by design**. En un modo de una sola pierna vectorial no hay "
        "ranking posible para ellas, así que los ítems de arriba salen del "
        "denominador de `citation-precision` (columna `n`) en lugar de puntuar "
        "0.00 contra una barra dura de `= 1.00`. En `fts` y `hybrid` se puntúan "
        "normalmente, y esa diferencia entre modos es un resultado de la "
        "ablación, no ruido.",
    ]
    return lineas


def _tabla_preguntas(corrida: ResultadoModo) -> list[str]:
    lineas = [
        "| id | clase | esperadas | devueltas (top-5) | score top-1 | fts | vec |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for detalle in corrida.detalles:
        esperadas = ", ".join(f"`{c}`" for c in detalle.citas_esperadas) or "—"
        devueltas = ", ".join(f"`{c}`" for c in detalle.claves_devueltas[:5]) or "—"
        lineas.append(
            f"| {detalle.id} | {detalle.clase} | {esperadas} | {devueltas} "
            f"| {detalle.score_top1:.6f} | {detalle.n_fts} | {detalle.n_vector} |"
        )
    return lineas


def _bloque_procedencia(
    procedencia: ProcedenciaEmbeddings | None,
    corpus_sha: str,
    device_consulta: str,
) -> list[str]:
    versiones = runtime_versions()
    if procedencia is None:
        estado = f"snapshot `{corpus_sha}` no está en `rag_corpus`"
        modelo = revision = artifact = cargado = NO_REGISTRADO
    elif not procedencia.cargado:
        estado = "ingerido pero **nunca embebido** (`embedding_modelo IS NULL`)"
        modelo = revision = artifact = cargado = "—"
    else:
        estado = "vectores cargados"
        modelo = f"`{procedencia.modelo}`"
        revision = f"`{procedencia.revision_hf}`" if procedencia.revision_hf else NO_REGISTRADO
        artifact = f"`{procedencia.artifact_sha256}`"
        cargado = procedencia.loaded_at.isoformat() if procedencia.loaded_at else NO_REGISTRADO

    return [
        "## Procedencia (leída de `rag_corpus`, no de un sidecar)",
        "",
        f"- corpus_sha: `{corpus_sha}`",
        f"- estado: {estado}",
        f"- modelo de embeddings: {modelo}",
        f"- revisión HF: {revision}",
        f"- sha256 del artefacto: {artifact}",
        f"- embeddings cargados en: {cargado}",
        f"- sintético: {'**sí**' if procedencia and procedencia.sintetico else 'no'}",
        "",
        "| leg | torch | transformers | device |",
        "|---|---|---|---|",
        f"| corpus (batch GPU) | {NO_REGISTRADO} | {NO_REGISTRADO} | {NO_REGISTRADO} |",
        f"| consulta (este proceso) | {versiones.get('torch') or '—'} "
        f"| {versiones.get('transformers') or '—'} | {device_consulta} |",
        "",
        "> La fila del corpus dice `no registrado en la base` a propósito: la "
        "migración `conocimiento_004` graba modelo, revisión, `sintetico`, sha256 "
        "del artefacto y timestamp — **no** la versión de torch ni el device del "
        "batch. Esos viven sólo en el sidecar, que un segundo batch sobre la misma "
        "revisión del corpus sobrescribe. Imprimir acá los valores de ESTE proceso "
        "sería atribuirle a los vectores del corpus un entorno que nunca los "
        "produjo (ledger RAG4-002); el sha256 de arriba es el puntero al sidecar "
        "que sí los tiene.",
        "",
        f"- RRF k = {RRF_K} · LEG_LIMIT = {LEG_LIMIT}",
    ]


#: Ops O.4 resolved the latency criterion as "measure locally for V0, LABELLED;
#: on-box measurement deferred to the V1 gate". So the label travels with the
#: number and the report never decides it — `scripts/rag_query_latency.py`
#: stamps `etiqueta` (LOCAL / ESTIMATE) and this block prints what it was given.
ETIQUETA_LATENCIA_DESCONOCIDA = "SIN ETIQUETA"


def _bloque_latencia(latencia: dict[str, Any] | None) -> list[str]:
    """The ratified latency criterion, or an explicit statement that it is absent.

    D3 asks whether a CPU-only box can turn a question into a query vector fast
    enough to serve. `scripts/rag_query_latency.py` answers it and wrote its
    answer to a file nothing read, so the criterion existed and the deliverable
    never carried it (ledger RJDA-006). The report now reads that file.

    It is READ, never measured here: this module may not touch a clock (the
    determinism claim is asserted over its AST), and a latency figure taken
    while rendering a report would measure the report. Absent, the block says
    so and names the command — silence would let a reader assume the criterion
    was met by a report that never looked.
    """
    if latencia is None:
        return [
            "## Latencia de embebido de consulta",
            "",
            "- **no medida en esta corrida.** El criterio de latencia (design.md "
            "D3) no está evaluado en este documento.",
            "- Para medirlo: `venv-rag/bin/python scripts/rag_query_latency.py "
            "--gold-set app/domains/conocimiento/eval/gold_set.yaml --device cpu "
            "--threads 2 --json artifacts/rag/latencia.json`, y volvé a correr "
            "`rag_eval.py --latencia artifacts/rag/latencia.json`.",
        ]

    etiqueta = str(latencia.get("etiqueta") or ETIQUETA_LATENCIA_DESCONOCIDA)
    lineas = [
        "## Latencia de embebido de consulta",
        "",
        f"- **etiqueta: {etiqueta}** — Ops O.4: cualquier medición que no sea "
        "sobre la máquina destino (CX33, 2 vCPU compartidas, sin GPU) es un "
        "**ESTIMATE**, y la medición on-box queda diferida a la compuerta de V1.",
        f"- modelo: `{latencia.get('modelo')}`",
        f"- device: {latencia.get('device')} · cpu_count: {latencia.get('cpu_count')} "
        f"· torch threads: {latencia.get('torch_threads')}",
        f"- muestras: {latencia.get('n')} "
        f"({latencia.get('preguntas')} preguntas × {latencia.get('repeticiones')} "
        f"repeticiones, {latencia.get('calentamientos')} de calentamiento)",
        f"- **p50 {_fmt(latencia.get('p50_ms'), 1)} ms · "
        f"p95 {_fmt(latencia.get('p95_ms'), 1)} ms** "
        f"(min {_fmt(latencia.get('min_ms'), 1)} · max {_fmt(latencia.get('max_ms'), 1)})",
        "",
        "> Una latencia sin cantidad de núcleos, threads y device no es una "
        "medición sino un rumor, así que las condiciones van al lado del número. "
        "Se mide **una consulta por vez**, que es la forma que tendría un "
        "request; medir en lote reportaría throughput y respondería otra pregunta.",
    ]
    if latencia.get("sintetico"):
        lineas += [
            "",
            "> ⚠️ **ESTE NÚMERO NO ES DEL MODELO.** Fue medido con el embebedor "
            "determinístico, así que mide el arnés: no hay tokenizer real ni "
            "forward pass. No sirve para decidir la compuerta de serving.",
        ]
    return lineas


def renderizar_markdown(
    resultado: ResultadoEval,
    procedencia: ProcedenciaEmbeddings | None,
    *,
    generado_en: dt.datetime,
    device_consulta: str,
    permitir_sintetico: bool = False,
    latencia: dict[str, Any] | None = None,
) -> str:
    """Render the report. Pure: same arguments in, byte-identical string out."""
    sintetico = _gate_sintetico(procedencia, permitir_sintetico, resultado=resultado)
    modos_sinteticos = _rankers_sinteticos(resultado)
    gold = resultado.gold
    precondicion = gold.precondicion()

    lineas: list[str] = []
    if sintetico:
        lineas += [
            f"# {ETIQUETA_SMOKE} — consorcio-rag",
            "",
            "> Este documento **no es una evaluación**. Los rankings de abajo son "
            "ruido con forma de medición. No hay veredicto y no puede haberlo.",
            "",
        ]
        if procedencia is not None and procedencia.sintetico:
            lineas += [
                "> - El snapshot fue cargado con vectores sintéticos "
                "(`embedding_sintetico = true`), producidos por un embebedor "
                "determinístico de prueba.",
                "",
            ]
        if modos_sinteticos:
            lineas += [
                f"> - El orden de {', '.join(f'`{m}`' for m in modos_sinteticos)} lo "
                "produjo un ranker SINTÉTICO, no `BAAI/bge-reranker-v2-m3`. En "
                "`bm25_ce` el orden es el del cross-encoder y nada más, así que un "
                "stand-in determinístico no degrada el ranking: lo reemplaza entero.",
                "",
            ]
    else:
        lineas += ["# Evaluación de recuperación — consorcio-rag V0", ""]

    lineas += [
        f"Generado: {generado_en.isoformat()}",
        "",
        *_bloque_procedencia(procedencia, resultado.corpus_sha, device_consulta),
        "",
        "## Gold set",
        "",
        f"- ítems: {len(gold.items)} (respondibles {gold.n_respondibles} · "
        f"abstención {gold.n_unanswerable})",
        f"- ratificado: {gold.ratificado}",
        f"- corpus_sha del gold set: `{gold.corpus_sha}`",
        f"- evaluable: {'sí' if precondicion.evaluable else 'NO'}",
        "",
        *_bloque_latencia(latencia),
    ]
    if not precondicion.evaluable:
        lineas.append("")
        for motivo in precondicion.motivos:
            lineas.append(f"  - {motivo}")
    lineas.append("")

    for modo in resultado.modos:
        corrida = resultado.por_modo[modo]
        go_no_go = decidir_go_no_go(corrida, gold)
        veredicto = "NO EVALUABLE" if sintetico else go_no_go.veredicto_con_alcance
        lineas += [
            f"## Modo `{modo}`",
            "",
            f"**Veredicto: {veredicto}**",
            "",
        ]
        if not go_no_go.evaluable:
            for motivo in go_no_go.motivos_no_evaluable:
                lineas.append(f"- {motivo}")
            lineas.append("")
        lineas += _tabla_metricas(corrida, go_no_go)
        lineas += ["", *_bloque_metodologia(corrida)]
        lineas += ["", *_bloque_cobertura(corrida)]
        lineas += ["", *_bloque_exencion(corrida)]
        lineas += ["", "**Por pregunta**", "", *_tabla_preguntas(corrida), ""]

    return "\n".join(lineas) + "\n"


def _a_json(
    resultado: ResultadoEval,
    procedencia: ProcedenciaEmbeddings | None,
    *,
    generado_en: dt.datetime,
    device_consulta: str,
    sintetico: bool,
    latencia: dict[str, Any] | None = None,
) -> dict[str, Any]:
    versiones = runtime_versions()
    modos: dict[str, Any] = {}
    for modo in resultado.modos:
        corrida = resultado.por_modo[modo]
        go_no_go = decidir_go_no_go(corrida, resultado.gold)
        modos[modo] = {
            "k": corrida.k,
            # `None` for the RRF ablation, which orders by fusion and has no
            # ranker. Published so a machine reader can tell a measured order
            # from a stand-in one without parsing the Spanish smoke banner.
            "ranker": {
                "modelo": corrida.ranker_modelo,
                "sintetico": corrida.ranker_sintetico,
            },
            "metricas": {
                "n_respondibles": corrida.metricas.n_respondibles,
                "hit_rate_at_5": corrida.metricas.hit_rate_at_5,
                # Re-ratified 2026-08-23: hit@10 is scored as its own bar, so it
                # is published as its own figure. A bar whose number does not
                # appear in the JSON is a verdict nobody can re-derive.
                "hit_rate_at_10": corrida.metricas.hit_rate_at_10,
                "mrr": corrida.metricas.mrr,
                "citation_precision": corrida.metricas.citation_precision,
                "n_citation_precision": corrida.metricas.n_citation_precision,
                "separacion_norma_secundaria": corrida.metricas.separacion_norma_secundaria,
                "n_separacion": corrida.metricas.n_separacion,
                "vigencia_correctness": corrida.metricas.vigencia_correctness,
                "n_vigencia": corrida.metricas.n_vigencia,
            },
            "exencion_over_ceiling": {
                "aplica": corrida.exencion.aplica,
                "motivo": (
                    "unidades sobre el techo de tokens del modelo del batch "
                    "(propiedad del embedder, no una constante del sistema): "
                    "ingeridas enteras, recuperables por FTS, nunca embebidas "
                    "(FTS-only by design, design.md D3)"
                ),
                "claves_sin_vector": list(corrida.exencion.claves),
                "preguntas_exentas": list(corrida.exencion.preguntas),
                "n_preguntas_exentas": corrida.exencion.n_preguntas_exentas,
                "metrica_afectada": "citation-precision",
            },
            "metodologia": resumen_metodologico(corrida),
            "cobertura": {
                "operador_fts": FTS_OPERADOR,
                "legs_corridas": list(corrida.cobertura.legs_corridas),
                "n_preguntas": corrida.cobertura.n_preguntas,
                "sin_candidatos_fts": corrida.cobertura.sin_candidatos_fts,
                "sin_candidatos_vector": corrida.cobertura.sin_candidatos_vector,
                "leg_fts_degradada": corrida.cobertura.leg_fts_degradada,
                "leg_vector_degradada": corrida.cobertura.leg_vector_degradada,
                "hibrido_degenerado": corrida.hibrido_degenerado,
            },
            "go_no_go": {
                "veredicto": "NO EVALUABLE" if sintetico else go_no_go.veredicto,
                "veredicto_con_alcance": (
                    "NO EVALUABLE" if sintetico else go_no_go.veredicto_con_alcance
                ),
                # A machine reader must be able to tell a bare GO from one whose
                # scope is a single leg WITHOUT parsing the Spanish sentence.
                "veredicto_calificado": go_no_go.veredicto_calificado and not sintetico,
                "legs_degradadas": list(go_no_go.legs_degradadas),
                "evaluable": go_no_go.evaluable and not sintetico,
                "motivos_no_evaluable": list(go_no_go.motivos_no_evaluable),
                "barras": [
                    {
                        "nombre": barra.nombre,
                        "valor": barra.valor,
                        "minimo": barra.minimo,
                        "comparador": barra.comparador,
                        "fuente": barra.fuente,
                        "pasa": barra.pasa,
                    }
                    for barra in go_no_go.barras
                ],
            },
            "preguntas": [
                {
                    "id": detalle.id,
                    "clase": detalle.clase,
                    "citas_esperadas": list(detalle.citas_esperadas),
                    "claves_devueltas": list(detalle.claves_devueltas),
                    "score_top1": detalle.score_top1,
                    "margen": detalle.margen,
                    "n_fts": detalle.n_fts,
                    "n_vector": detalle.n_vector,
                }
                for detalle in corrida.detalles
            ],
        }

    return {
        "generado_en": generado_en.isoformat(),
        "corpus_sha": resultado.corpus_sha,
        # The gold set's OWN pin, next to the snapshot's, so a reader of the JSON
        # alone can see they agree. `verificar_corpus_sha` refuses at the CLI when
        # they do not; this is the record that the check had something to compare
        # (ledger RAG4-003).
        "gold_corpus_sha": resultado.gold.corpus_sha,
        "sintetico": sintetico,
        # `None` and not an empty object: "the criterion was not evaluated" and
        # "it was evaluated and came back empty" are different facts, and a
        # machine reader must not have to guess which one a `{}` means.
        "latencia": latencia,
        "minimo_respondibles": MINIMO_RESPONDIBLES,
        "operador_fts": FTS_OPERADOR,
        "rrf_k": RRF_K,
        "leg_limit": LEG_LIMIT,
        "procedencia": {
            "modelo": procedencia.modelo if procedencia else None,
            "revision_hf": procedencia.revision_hf if procedencia else None,
            "sintetico": procedencia.sintetico if procedencia else None,
            "artifact_sha256": procedencia.artifact_sha256 if procedencia else None,
            "embeddings_loaded_at": (
                procedencia.loaded_at.isoformat() if procedencia and procedencia.loaded_at else None
            ),
            "torch_corpus": None,
            "device_corpus": None,
            "torch_consulta": versiones.get("torch"),
            "transformers_consulta": versiones.get("transformers"),
            "device_consulta": device_consulta,
        },
        "gold_set": {
            "n": len(resultado.gold.items),
            "n_respondibles": resultado.gold.n_respondibles,
            "n_unanswerable": resultado.gold.n_unanswerable,
            "ratificado": resultado.gold.ratificado,
            "no_resueltas": list(resultado.gold.no_resueltas),
            "evaluable": resultado.gold.precondicion().evaluable,
        },
        "modos": modos,
    }


def escribir_reporte(
    resultado: ResultadoEval,
    procedencia: ProcedenciaEmbeddings | None,
    *,
    destino: Path,
    generado_en: dt.datetime,
    device_consulta: str,
    permitir_sintetico: bool = False,
    latencia: dict[str, Any] | None = None,
) -> ReporteEscrito:
    """Write the markdown and its machine-readable twin, side by side.

    The synthetic gate runs BEFORE the directory is created, so a refused run
    leaves nothing behind — a half-written `docs/rag/` entry is exactly the
    artifact somebody finds later and reads as a result.
    """
    sintetico = _gate_sintetico(procedencia, permitir_sintetico, resultado=resultado)
    markdown = renderizar_markdown(
        resultado,
        procedencia,
        generado_en=generado_en,
        device_consulta=device_consulta,
        permitir_sintetico=permitir_sintetico,
        latencia=latencia,
    )
    datos = _a_json(
        resultado,
        procedencia,
        generado_en=generado_en,
        device_consulta=device_consulta,
        sintetico=sintetico,
        latencia=latencia,
    )

    destino.mkdir(parents=True, exist_ok=True)
    nombre = nombre_de_archivo(resultado.corpus_sha, generado_en, sintetico=sintetico)
    ruta_md = destino / nombre
    ruta_json = destino / f"{nombre[:-3]}.results.json"
    ruta_md.write_text(markdown, encoding="utf-8")
    ruta_json.write_text(
        json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ReporteEscrito(markdown=ruta_md, json=ruta_json)
