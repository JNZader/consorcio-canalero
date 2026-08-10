"""Corpus loading + gate orchestration for ingestion, and the retrieval path.

The ingestion half is pure with respect to the database: it reads a checkout,
parses it, and runs the gates. `scripts/rag_ingest.py` owns the transaction and
is the only thing that writes.

The retrieval half (`recuperar`) is the one code path all three ablation modes
share — `fts`, `vector` and `hybrid` differ only in which legs run, never in how
results are fused, ordered or attributed. Three code paths would be three
opportunities for the modes to stop being comparable, which is the one thing an
ablation cannot survive.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml
from sqlalchemy.orm import Session

from app.domains.conocimiento.embedding import Embedder
from app.domains.conocimiento.expectations import CorpusExpectations, load_expectations
from app.domains.conocimiento.fusion import RRF_K, reciprocal_rank_fusion
from app.domains.conocimiento.gates import GateReport, run_all_gates
from app.domains.conocimiento.parser import Unidad, parse_document
from app.domains.conocimiento.repository import (
    LEG_LIMIT,
    IngestionAbort,
    LegHit,
    fts_search,
    hydrate_citations,
    vector_search,
)
from app.domains.conocimiento.schemas import CitaRecuperada, ResultadoRecuperacion


class CorpusPinMismatch(IngestionAbort):
    """The checkout's HEAD is not the declared SHA, or the tree is dirty."""


@dataclass(frozen=True)
class LoadedDocument:
    documento_id: str
    archivo: str
    text: str
    frontmatter: dict[str, Any]
    unidades: tuple[Unidad, ...]


@dataclass(frozen=True)
class LoadedCorpus:
    corpus_sha: str
    documentos: tuple[LoadedDocument, ...]
    expectations: CorpusExpectations
    #: The checkout this was read from. Carried so the file inventory gate can
    #: compare the declared document list against what is actually on disk.
    corpus_path: Path

    @property
    def sources(self) -> dict[str, str]:
        return {doc.documento_id: doc.text for doc in self.documentos}

    @property
    def parsed(self) -> dict[str, tuple[Unidad, ...]]:
        return {doc.documento_id: doc.unidades for doc in self.documentos}


def _git(corpus_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(corpus_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise CorpusPinMismatch(
            f"`git {' '.join(args)}` failed in {corpus_path}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def verify_corpus_pin(corpus_path: Path, declared_sha: str) -> str:
    """Resolve the checkout's HEAD and refuse anything but a clean, pinned tree.

    Both halves matter. The SHA check is what makes a snapshot reproducible; the
    dirty-tree check is what keeps `ON CONFLICT DO UPDATE` honest, since a
    modified working tree could rewrite a committed snapshot's content while its
    `corpus_sha` stayed the same, leaving no trace (design.md D2).
    """
    if not (corpus_path / ".git").exists():
        raise CorpusPinMismatch(f"{corpus_path} is not a git checkout")

    head = _git(corpus_path, "rev-parse", "HEAD")
    if head != declared_sha:
        raise CorpusPinMismatch(
            f"declared --corpus-sha {declared_sha} but {corpus_path} is at {head}. "
            "Ingestion aborts before writing any row."
        )
    dirty = _git(corpus_path, "status", "--porcelain")
    if dirty:
        raise CorpusPinMismatch(
            f"{corpus_path} has uncommitted changes; refusing to ingest a dirty "
            f"tree as snapshot {declared_sha}:\n{dirty}"
        )
    return head


def split_frontmatter(text: str, archivo: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        raise IngestionAbort(f"{archivo}: no YAML frontmatter block")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise IngestionAbort(f"{archivo}: unterminated YAML frontmatter block")
    return yaml.safe_load(text[4 : end + 1]) or {}


def load_corpus(
    corpus_path: Path,
    expectations: CorpusExpectations | None = None,
) -> LoadedCorpus:
    """Read + parse every declared document. No DB, no gates yet."""
    expectations = expectations or load_expectations()
    documentos: list[LoadedDocument] = []

    for documento_id, policy in expectations.documentos.items():
        path = corpus_path / policy.archivo
        if not path.is_file():
            raise IngestionAbort(f"{policy.archivo} declared in expectations but missing")
        text = path.read_text(encoding="utf-8")
        frontmatter = split_frontmatter(text, policy.archivo)
        documentos.append(
            LoadedDocument(
                documento_id=documento_id,
                archivo=policy.archivo,
                text=text,
                frontmatter=frontmatter,
                unidades=tuple(parse_document(text, frontmatter, policy)),
            )
        )

    return LoadedCorpus(
        corpus_sha=expectations.corpus_sha,
        documentos=tuple(documentos),
        expectations=expectations,
        corpus_path=corpus_path,
    )


def gate_corpus(corpus: LoadedCorpus, strict_token_ceiling: bool = False) -> GateReport:
    return run_all_gates(
        corpus.parsed,
        corpus.sources,
        corpus.expectations,
        strict_token_ceiling=strict_token_ceiling,
        corpus_path=corpus.corpus_path,
    )


def texto_sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Retrieval — one code path, three modes (design.md D4)
# ---------------------------------------------------------------------------

MODOS = ("fts", "vector", "hybrid")


class EmbedderRequerido(RuntimeError):
    """A vector-using mode was requested without an embedder to build the query.

    Deliberately NOT a silent downgrade to `fts`. A caller who asked for the
    vector leg and got a lexical answer would have no way to tell.
    """


def _leg_map(hits: Sequence[LegHit]) -> dict[str, LegHit]:
    return {hit.citation_key: hit for hit in hits}


def recuperar(
    db: Session,
    corpus_sha: str,
    pregunta: str,
    *,
    modo: str = "hybrid",
    k: int = 10,
    embedder: Embedder | None = None,
    limite_leg: int = LEG_LIMIT,
    rrf_k: int = RRF_K,
) -> ResultadoRecuperacion:
    """Run the requested legs, fuse by RRF, return fully attributed citations.

    Determinism is a property of the whole chain and every link carries part of
    it: each leg sorts by `citation_key` as its secondary key, fusion sorts by
    `(-score, citation_key)`, and hydration preserves the fused order rather than
    the database's. Same question and same snapshot in, byte-identical ranked
    list out — which is what makes a gold-set number mean anything.

    The vector leg RAISES `VectorSupportUnavailable` where it cannot run. There
    is no fallback here and there must not be one: a `hybrid` run that quietly
    became `fts` would publish a comparison it never made.
    """
    if modo not in MODOS:
        raise ValueError(f"unknown modo {modo!r} (expected one of {MODOS})")
    if modo in ("vector", "hybrid") and embedder is None:
        raise EmbedderRequerido(
            f"modo={modo!r} needs an embedder to turn the question into a query "
            "vector. Falling back to FTS would answer a different question than "
            "the one asked."
        )

    hits_fts: list[LegHit] = []
    hits_vector: list[LegHit] = []

    if modo in ("fts", "hybrid"):
        hits_fts = fts_search(db, corpus_sha, pregunta, limite=limite_leg)
    if modo in ("vector", "hybrid"):
        assert embedder is not None  # guarded above; keeps mypy honest
        (qvec,) = embedder.encode([pregunta])
        hits_vector = vector_search(db, corpus_sha, qvec, limite=limite_leg)

    fusionado = reciprocal_rank_fusion(
        [[hit.citation_key for hit in hits_fts], [hit.citation_key for hit in hits_vector]],
        k=rrf_k,
    )[:k]

    por_fts = _leg_map(hits_fts)
    por_vector = _leg_map(hits_vector)
    provenance = hydrate_citations(db, corpus_sha, [clave for clave, _ in fusionado])

    hits: list[CitaRecuperada] = []
    for citation_key, score in fusionado:
        fila = provenance.get(citation_key)
        if fila is None:
            # A key that ranked but cannot be hydrated means the snapshot changed
            # under the query. Skipping it silently would return a ranked list
            # shorter than its own scores claim.
            raise IngestionAbort(
                f"{citation_key} ranked in snapshot {corpus_sha} but has no row. "
                "The snapshot changed mid-query."
            )
        en_fts = por_fts.get(citation_key)
        en_vector = por_vector.get(citation_key)
        hits.append(
            CitaRecuperada(
                **fila,
                score_rrf=score,
                rango_fts=None if en_fts is None else en_fts.rango,
                valor_fts=None if en_fts is None else en_fts.valor,
                rango_vector=None if en_vector is None else en_vector.rango,
                distancia_vector=None if en_vector is None else en_vector.valor,
            )
        )

    return ResultadoRecuperacion(
        corpus_sha=corpus_sha,
        pregunta=pregunta,
        modo=modo,
        k=k,
        hits=hits,
        n_fts=len(hits_fts),
        n_vector=len(hits_vector),
    )
