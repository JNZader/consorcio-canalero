"""Ranking: `bge-reranker-v2-m3` over the 50 candidates, and nothing else.

The port is a Protocol with two implementations and one rule that governs both:
**the ordering score is the cross-encoder logit ALONE**. Every measured attempt
to help it with lexical evidence made it worse, monotonically in the blend
weight: RRF between the CE order and the BM25 order costs −0.035/−0.069 hit@5,
and a multiplicative CE×lexical score costs −0.104/−0.207
(`design.md:1136-1138`). Lexical signal lives in candidate generation, where it
is measurably the best thing available, and it stops there.

**A per-document cap is REJECTED, and the reason is worth keeping.** Capping how
many units one document may contribute lifts hit@5 to 0.793 — the best number in
the entire campaign — while collapsing vigencia-correctness from 1.00 to 0.333
(`design.md:1138-1139`). What it buys in "the right document appears" it pays for
by evicting the article that says the norm is derogated, which turns a correct
citation into confidently-cited dead law. The bar it breaks is the one that
cannot be traded.

**Serving is fail-closed on the device.** Measured CPU latency for depth 50 is
98.9 s per query on an i7-12700K, and the deployment box is weaker than that
(`docs/rag/reranker-experiment-2026-08-23.md:357-371`), so `BGEReranker` refuses
rather than silently taking two minutes per question. Under the ratified async
mailbox model (`design.md` amendment A3) that refusal is not a user-facing 503:
a worker that cannot rerank simply does not process the queue, and items stay
`pendiente`. This module serves the retrieval FUNCTION; wiring it to a worker and
a queue is U6/U7's work, not this one's.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

#: Pinned model + revision. The revision is the resolved commit the campaign
#: measured; a symbolic `main` would let a silent upstream re-upload change every
#: published number without moving a line of this repository.
MODELO_RERANKER = "BAAI/bge-reranker-v2-m3"
REVISION_RERANKER = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"

#: Token ceiling per (question, unit) pair, as measured. Ten of the corpus's
#: units exceed it (max 58,619 chars) and are TRUNCATED rather than skipped —
#: a known, recorded cost, scheduled as follow-up F1 (re-chunking), not as a
#: silent behaviour of this module.
MAX_LENGTH = 1024

#: Pairs per forward pass. Configurable because it is a memory/throughput knob of
#: the serving host, and only that: batching cannot change a score.
BATCH_POR_DEFECTO = 32


@dataclass(frozen=True)
class Candidato:
    """One unit offered to the ranker, with the exact text that gets scored.

    `texto_indexado` — title + structural path + body — is what the campaign
    scored and therefore what must be scored here. The verbatim `texto` is what
    is SHOWN as a citation and is deliberately not what is ranked: stripping the
    epigraph before scoring would hide from the reranker the one field that says
    which article this is.
    """

    citation_key: str
    texto_indexado: str


@runtime_checkable
class Reranker(Protocol):
    """What the retrieval path needs from a ranker, and nothing more."""

    model_id: str
    revision: str | None
    #: True for a stand-in that computes numbers without a model. The eval and
    #: the serving surface refuse to publish or serve on a synthetic ranker, the
    #: same way they already refuse synthetic embeddings.
    sintetico: bool

    def puntuar(self, pregunta: str, textos: Sequence[str]) -> list[float]:
        """Cross-encoder score per text, higher is more relevant, same order in."""
        ...


class RerankerNoDisponible(RuntimeError):
    """The reranker cannot run here — and that is a refusal, never a fallback.

    No CPU fallback and no smaller model: the design authorises neither
    (`design.md:1132-1134`). A CPU run would not be a slow answer, it would be a
    98.9-second one per question, and a smaller reranker would be a different
    measurement wearing the ratified one's numbers.
    """


class BGEReranker:
    """The real port: fp16 `bge-reranker-v2-m3` on a CUDA device.

    Imports of `torch` and `transformers` are deliberately deferred to
    construction. Neither is in the backend's runtime closure — the box does not
    hold them and must not need them to import `app` — so a module-level import
    would make the whole conocimiento domain unimportable wherever the reranker
    is not installed, which is everywhere except the GPU worker.
    """

    sintetico = False

    def __init__(
        self,
        *,
        model_id: str = MODELO_RERANKER,
        revision: str = REVISION_RERANKER,
        batch: int = BATCH_POR_DEFECTO,
        max_length: int = MAX_LENGTH,
        device: str = "cuda",
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - depends on the host
            raise RerankerNoDisponible(
                "torch/transformers are not installed in this environment, so "
                f"{model_id} cannot be loaded. This is not a reason to rank with "
                "something else: the ratified numbers were measured on this model."
            ) from exc

        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RerankerNoDisponible(
                "no CUDA device is available. Measured CPU latency at depth 50 is "
                "98.9 s per query on an i7-12700K and the box is weaker, so a CPU "
                "fallback is not a degraded mode, it is an outage that answers. "
                "Under the async queue model the correct behaviour is to leave "
                "items `pendiente` until a GPU worker runs."
            )

        self.model_id = model_id
        self.revision: str | None = revision
        self._batch = batch
        self._max_length = max_length
        self._device = device
        self._torch = torch
        self._tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
        modelo = AutoModelForSequenceClassification.from_pretrained(model_id, revision=revision)
        self._modelo = modelo.eval().half().to(device)

    def puntuar(self, pregunta: str, textos: Sequence[str]) -> list[float]:
        logits: list[float] = []
        with self._torch.no_grad():
            for inicio in range(0, len(textos), self._batch):
                lote = list(textos[inicio : inicio + self._batch])
                enc = self._tok(
                    [pregunta] * len(lote),
                    lote,
                    padding=True,
                    truncation=True,
                    max_length=self._max_length,
                    return_tensors="pt",
                ).to(self._device)
                logits.extend(self._modelo(**enc).logits.view(-1).float().cpu().tolist())
        return logits


class RerankerDeterministico:
    """A stand-in that computes reproducible numbers without a model.

    It exists so the retrieval CONTRACT — pool composition, ordering, exclusion,
    determinism — can be tested where no GPU exists, which is CI and every
    developer machine. It says nothing about retrieval QUALITY and must never be
    used to produce a published figure: `sintetico` is True precisely so the eval
    and the serving gate can refuse it, exactly as they already refuse synthetic
    embeddings.

    The score is a hash of `(pregunta, texto)`, so it is stable across processes
    and across runs and is uncorrelated with relevance — which is the point: a
    test that passes because the fake happens to rank well would be testing the
    fake.
    """

    model_id = "deterministico"
    revision: str | None = None
    sintetico = True

    def puntuar(self, pregunta: str, textos: Sequence[str]) -> list[float]:
        salida: list[float] = []
        for texto in textos:
            digest = hashlib.sha256(f"{pregunta}\x00{texto}".encode("utf-8")).digest()
            (crudo,) = struct.unpack(">Q", digest[:8])
            salida.append(crudo / float(1 << 64))
        return salida


def ordenar_por_ce(
    reranker: Reranker,
    pregunta: str,
    candidatos: Sequence[Candidato],
) -> list[tuple[str, float]]:
    """Rank candidates by the cross-encoder score alone. No blend, no cap.

    The candidates' BM25 order is discarded here on purpose: it already did its
    job by selecting the pool, and carrying it into the ranking is the fusion the
    campaign measured as harmful. The only thing that survives from candidate
    generation is MEMBERSHIP.

    Ties break on `citation_key`, so the same question against the same snapshot
    produces a byte-identical order — the property that makes a gold-set number
    mean anything.
    """
    if not candidatos:
        return []
    puntajes = reranker.puntuar(pregunta, [candidato.texto_indexado for candidato in candidatos])
    if len(puntajes) != len(candidatos):
        raise RerankerNoDisponible(
            f"the reranker returned {len(puntajes)} scores for {len(candidatos)} "
            "candidates. A partial ranking silently drops units from the pool, "
            "which is indistinguishable at the surface from them ranking badly."
        )
    pares = [
        (candidato.citation_key, float(puntaje)) for candidato, puntaje in zip(candidatos, puntajes)
    ]
    return sorted(pares, key=lambda par: (-par[1], par[0]))
