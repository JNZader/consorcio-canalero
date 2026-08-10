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
from app.domains.conocimiento.service import LEG_LIMIT, ProcedenciaEmbeddings

NO_REGISTRADO = "no registrado en la base"
ETIQUETA_SMOKE = "SMOKE RUN — NOT AN EVAL"


class EvalSinteticoNoEsEval(RuntimeError):
    """The snapshot holds synthetic vectors, so this cannot be published as an eval."""


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


def _gate_sintetico(procedencia: ProcedenciaEmbeddings | None, permitir: bool) -> bool:
    """Returns whether this is a smoke run. Raises when it is one and is not allowed."""
    sintetico = bool(procedencia is not None and procedencia.sintetico)
    if sintetico and not permitir:
        snapshot = procedencia.corpus_sha if procedencia else "?"
        modelo = procedencia.modelo if procedencia else None
        raise EvalSinteticoNoEsEval(
            f"snapshot {snapshot} was loaded with "
            f"SYNTHETIC vectors (embedding_modelo={modelo!r}, embedding_sintetico=true). "
            "Refusing to render an eval report: every table would be shaped like a "
            "measurement and none of it would be one. Load real vectors "
            "(scripts/rag_embed_batch.py + scripts/rag_load_vectors.py), or pass "
            "permitir_sintetico=True / --allow-synthetic to get a clearly-labelled "
            "SMOKE RUN that carries no verdict."
        )
    return sintetico


def _fmt(valor: float | None, decimales: int = 3) -> str:
    """`n/d` for a metric with no denominator. Never `0.000`, which is a result."""
    if valor is None:
        return "n/d"
    return f"{valor:.{decimales}f}"


def _tabla_metricas(corrida: ResultadoModo, go_no_go) -> list[str]:
    lineas = [
        "| métrica | valor | barra | fuente | ¿pasa? |",
        "|---|---:|---:|---|---|",
    ]
    for barra in go_no_go.barras:
        comparador = "=" if barra.comparador == "==" else "≥"
        lineas.append(
            f"| {barra.nombre} | {_fmt(barra.valor)} | {comparador} {barra.minimo:.2f} "
            f"| {barra.fuente} | {'sí' if barra.pasa else 'NO'} |"
        )
    return lineas


def _bloque_metodologia(corrida: ResultadoModo) -> list[str]:
    resumen = resumen_metodologico(corrida)
    return [
        "**Metodología (divulgación obligatoria — design.md D6)**",
        "",
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


def _bloque_cobertura(corrida: ResultadoModo) -> list[str]:
    cobertura = corrida.cobertura
    lineas = [
        "**Cobertura de las piernas**",
        "",
        f"- preguntas corridas: {cobertura.n_preguntas}",
        f"- sin candidatos FTS: {cobertura.sin_candidatos_fts} "
        f"({cobertura.fraccion_sin_candidatos_fts:.1%})",
        f"- sin candidatos vector: {cobertura.sin_candidatos_vector} "
        f"({cobertura.fraccion_sin_candidatos_vector:.1%})",
    ]
    if cobertura.leg_fts_degradada:
        lineas += [
            "",
            "> ⚠️ **LEG DEGRADADA (FTS)** — la mayoría de las preguntas no obtuvo "
            "ningún candidato léxico. `websearch_to_tsquery` arma una CONJUNCIÓN, "
            "así que una pregunta coloquial compila a una decena de lexemas unidos "
            "por `&` y no hay artículo que los contenga a todos (ledger RAG4-001). "
            "Las métricas de este modo describen esa propiedad de la consulta, no "
            "la calidad del índice.",
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
            "ninguna pregunta, así que este bloque NO es una fusión: es la otra "
            "pierna sola, con etiqueta de híbrido.",
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


def renderizar_markdown(
    resultado: ResultadoEval,
    procedencia: ProcedenciaEmbeddings | None,
    *,
    generado_en: dt.datetime,
    device_consulta: str,
    permitir_sintetico: bool = False,
) -> str:
    """Render the report. Pure: same arguments in, byte-identical string out."""
    sintetico = _gate_sintetico(procedencia, permitir_sintetico)
    gold = resultado.gold
    precondicion = gold.precondicion()

    lineas: list[str] = []
    if sintetico:
        lineas += [
            f"# {ETIQUETA_SMOKE} — consorcio-rag",
            "",
            "> Este documento **no es una evaluación**. El snapshot fue cargado con "
            "vectores sintéticos (`embedding_sintetico = true`), producidos por un "
            "embebedor determinístico de prueba. Los rankings de abajo son ruido con "
            "forma de medición. No hay veredicto y no puede haberlo.",
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
    ]
    if not precondicion.evaluable:
        lineas.append("")
        for motivo in precondicion.motivos:
            lineas.append(f"  - {motivo}")
    lineas.append("")

    for modo in resultado.modos:
        corrida = resultado.por_modo[modo]
        go_no_go = decidir_go_no_go(corrida, gold)
        veredicto = "NO EVALUABLE" if sintetico else go_no_go.veredicto
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
        lineas += ["", "**Por pregunta**", "", *_tabla_preguntas(corrida), ""]

    return "\n".join(lineas) + "\n"


def _a_json(
    resultado: ResultadoEval,
    procedencia: ProcedenciaEmbeddings | None,
    *,
    generado_en: dt.datetime,
    device_consulta: str,
    sintetico: bool,
) -> dict[str, Any]:
    versiones = runtime_versions()
    modos: dict[str, Any] = {}
    for modo in resultado.modos:
        corrida = resultado.por_modo[modo]
        go_no_go = decidir_go_no_go(corrida, resultado.gold)
        modos[modo] = {
            "k": corrida.k,
            "metricas": {
                "n_respondibles": corrida.metricas.n_respondibles,
                "hit_rate_at_5": corrida.metricas.hit_rate_at_5,
                "mrr": corrida.metricas.mrr,
                "citation_precision": corrida.metricas.citation_precision,
                "separacion_norma_secundaria": corrida.metricas.separacion_norma_secundaria,
                "vigencia_correctness": corrida.metricas.vigencia_correctness,
                "n_vigencia": corrida.metricas.n_vigencia,
            },
            "metodologia": resumen_metodologico(corrida),
            "cobertura": {
                "n_preguntas": corrida.cobertura.n_preguntas,
                "sin_candidatos_fts": corrida.cobertura.sin_candidatos_fts,
                "sin_candidatos_vector": corrida.cobertura.sin_candidatos_vector,
                "leg_fts_degradada": corrida.cobertura.leg_fts_degradada,
                "leg_vector_degradada": corrida.cobertura.leg_vector_degradada,
                "hibrido_degenerado": corrida.hibrido_degenerado,
            },
            "go_no_go": {
                "veredicto": "NO EVALUABLE" if sintetico else go_no_go.veredicto,
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
        "sintetico": sintetico,
        "minimo_respondibles": MINIMO_RESPONDIBLES,
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
) -> ReporteEscrito:
    """Write the markdown and its machine-readable twin, side by side.

    The synthetic gate runs BEFORE the directory is created, so a refused run
    leaves nothing behind — a half-written `docs/rag/` entry is exactly the
    artifact somebody finds later and reads as a result.
    """
    sintetico = _gate_sintetico(procedencia, permitir_sintetico)
    markdown = renderizar_markdown(
        resultado,
        procedencia,
        generado_en=generado_en,
        device_consulta=device_consulta,
        permitir_sintetico=permitir_sintetico,
    )
    datos = _a_json(
        resultado,
        procedencia,
        generado_en=generado_en,
        device_consulta=device_consulta,
        sintetico=sintetico,
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
