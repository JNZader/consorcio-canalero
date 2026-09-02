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
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.conocimiento.embedding import (
    Embedder,
    RevisionNoResoluble,
    canonicalizar_revision,
)
from app.domains.conocimiento.expectations import CorpusExpectations, load_expectations
from app.domains.conocimiento.fusion import RRF_K, reciprocal_rank_fusion
from app.domains.conocimiento.gates import GateReport, run_all_gates
from app.domains.conocimiento.parser import Unidad, parse_document
from app.domains.conocimiento.recuperacion.bm25 import (
    PROFUNDIDAD_CANDIDATOS,
    lexemas_de_consulta,
    obtener_indice,
)
from app.domains.conocimiento.recuperacion.expansion import expandir_consulta_recuperacion
from app.domains.conocimiento.recuperacion.reranker import Candidato, Reranker, ordenar_por_ce
from app.domains.conocimiento.repository import (
    # Deliberate re-export (the redundant alias is how ruff is told so). The eval
    # package may not import `repository` (design.md D4) and still has to print
    # WHICH operator produced the lexical leg it is reporting on — an ablation
    # whose operator is not disclosed is a measurement of something the reader
    # cannot name (ledger RAG4-001).
    CLASIFICACIONES_ENVIABLES,
    FTS_OPERADOR as FTS_OPERADOR,
    LEG_LIMIT,
    IngestionAbort,
    LegHit,
    ProcedenciaEmbeddings,
    claves_sin_embedding,
    fts_search,
    hydrate_citations,
    leer_procedencia,
    require_vector_support,
    textos_indexados,
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

#: `fts`, `vector` and `hybrid` are the published V0 ablation and stay exactly as
#: they were — they are the baseline `bm25_ce` is measured AGAINST, and an
#: ablation whose baseline arm no longer runs is a claim rather than a
#: comparison. `bm25_ce` is the ratified serving configuration `B50`
#: (`design.md:1125-1139`): real BM25 candidates, cross-encoder ranking, no
#: vector leg anywhere in it.
MODOS = ("fts", "vector", "hybrid", "bm25_ce")

#: The modes that fuse two legs by RRF. `bm25_ce` is deliberately not one of
#: them: it has a single candidate leg and a ranker, and there is nothing to
#: fuse.
MODOS_RRF = ("fts", "vector", "hybrid")


#: The value both sides collapse to under the deterministic-embedder exemption.
#: A sentinel rather than a `revision is None` short-circuit so the comparison
#: stays ONE tuple check: an exemption written as an early `return` is an
#: exemption that a later field added to the tuple silently skips.
_REVISION_SINTETICA = "<sintetica>"


class EmbedderRequerido(RuntimeError):
    """A vector-using mode was requested without an embedder to build the query.

    Deliberately NOT a silent downgrade to `fts`. A caller who asked for the
    vector leg and got a lexical answer would have no way to tell.
    """


class EmbeddingsNoCargadas(RuntimeError):
    """The snapshot has no vectors at all, so the vector leg has nothing to search.

    A sibling of `VectorSupportUnavailable`, one level up: that one means "this
    DATABASE cannot run a vector query", this one means "this SNAPSHOT was never
    embedded". Both are refusals rather than empty results for the same reason —
    an empty hit list is a legitimate answer to a query that matched nothing, and
    a corpus that was never embedded must never be mistaken for one.
    """


class EmbedderMismatch(RuntimeError):
    """The query embedder is not the one that produced the stored vectors.

    Cosine distance between vectors from two different models is arithmetic, not
    similarity: it computes, it ranks, and it means nothing. The failure has no
    symptom at the query surface — the leg returns 50 confident hits either way
    — so it can only be caught by comparing identities, which is why
    `rag_corpus` records the model that wrote the column (migration
    `conocimiento_004`, ledger RAG3-001).

    The check is symmetric on purpose. Refusing only the synthetic-rows/real-
    embedder direction would leave the mirror image — a deterministic smoke
    embedder queried against real BGE-M3 vectors — silently producing a ranked
    list of pure noise, which is the same fabricated-measurement failure with
    the operands swapped.
    """


def _leg_map(hits: Sequence[LegHit]) -> dict[str, LegHit]:
    return {hit.citation_key: hit for hit in hits}


def procedencia_embeddings(db: Session, corpus_sha: str) -> ProcedenciaEmbeddings | None:
    """What produced this snapshot's vectors, read from `rag_corpus`.

    A thin pass-through, and it exists for a structural reason rather than a
    stylistic one: the eval package may not import `repository` (design.md D4),
    because a module that can reach the repository can reach `vector_search` and
    thereby skip the two provenance refusals that make a published measurement
    honest. The report needs this data — it pins the model the corpus was
    embedded with — so the service layer exposes it and the boundary holds.
    """
    return leer_procedencia(db, corpus_sha)


def claves_sin_vector(db: Session, corpus_sha: str) -> frozenset[str]:
    """Which units the vector leg cannot reach at all, for the eval to disclose.

    Same structural reason as `procedencia_embeddings`: the eval package may not
    import `repository` (design.md D4), and it needs this set to tell "the vector
    leg ranked badly" apart from "the vector leg had nothing to rank". Those are
    different findings and only one of them is about retrieval quality.

    **The capability check runs FIRST, and it is not a formality** (ledger
    RJDA-103). This reads the dev-only `embedding` column, which does not exist
    on the CI image, and the harness calls it BEFORE the first `recuperar` — so
    on a vector-less database the old ordering surfaced a raw psycopg
    `ProgrammingError: column "embedding" does not exist` instead of the
    `VectorSupportUnavailable` written to explain exactly this, and it did so
    from inside the caller's session, aborting the transaction on the way out.
    Telling callers in a docstring to check first was not a guard; this is.
    """
    require_vector_support(db)
    return claves_sin_embedding(db, corpus_sha)


#: The serving gate's SQL, in the same raw-SQL join shape `eval/privacy.py:49-58`
#: already uses, so "what leaves the machine" reads the same in both places. Raw
#: rather than the ORM for exactly that reason: this query must be readable end
#: to end by someone auditing the privacy boundary.
_UNIDADES_ENVIABLES_SQL = text(
    """
    SELECT u.citation_key
    FROM rag_unidad u
    JOIN rag_documento d
      ON d.corpus_sha = u.corpus_sha AND d.documento_id = u.documento_id
    WHERE u.corpus_sha = :corpus_sha
      AND u.citation_key = ANY(:claves)
      AND d.clasificacion = ANY(:enviables)
    """
)


def assert_unidades_publicas(db: Session, corpus_sha: str, claves: Sequence[str]) -> frozenset[str]:
    """Return the SHIPPABLE SUBSET of `claves` — it never raises on exclusion.

    Per-unit exclusion, not snapshot refusal, and the difference is deliberate.
    `eval/privacy.py`'s `assert_public_domain` refuses the WHOLE snapshot if a
    single document is non-public, which is right for a *baseline*: a baseline
    computed over a filtered corpus would be compared against a corpus it was not
    computed over. A served answer has no such symmetry requirement — it is
    grounded in whatever units it actually cites — so dropping the units that may
    not travel is the correct behaviour here, and refusing the request would not
    be.

    The admitted set is `CLASIFICACIONES_ENVIABLES`, imported rather than
    re-spelled: "shippable" has exactly ONE definition in this codebase, shared
    with the ingest rule. `assert_public_domain` deliberately does not use it.

    The name is kept from the ratified amendment even though the function now
    admits `institucional` too, because that is the name the amendment uses and
    renaming it here would make the design document and the code disagree about
    which gate is which.

    Downstream contract (G2b): the generation payload is the retrieved list
    filtered to this subset, in retrieved order, nothing back-filled to restore
    `k`; an empty payload is abstención and never reaches the provider; and every
    later check binds to the payload, so an excluded unit's citation key is an
    INVENTED key, not a permitted one.
    """
    if not claves:
        return frozenset()
    filas = db.execute(
        _UNIDADES_ENVIABLES_SQL,
        {
            "corpus_sha": corpus_sha,
            "claves": list(claves),
            "enviables": sorted(CLASIFICACIONES_ENVIABLES),
        },
    ).scalars()
    return frozenset(filas)


def verificar_embedder(db: Session, corpus_sha: str, embedder: Embedder) -> None:
    """Refuse a vector query whose embedder did not produce this snapshot's vectors.

    Runs BEFORE either leg, so a mismatch costs nothing and, more importantly,
    cannot half-answer: a `hybrid` call that ran FTS and then refused would leave
    the caller holding a lexical result set for a question they asked to be
    fused.
    """
    procedencia = leer_procedencia(db, corpus_sha)
    if procedencia is None:
        raise EmbeddingsNoCargadas(
            f"snapshot {corpus_sha} is not in rag_corpus. There is nothing to "
            "retrieve from, let alone to embed against."
        )
    if not procedencia.cargado:
        raise EmbeddingsNoCargadas(
            f"snapshot {corpus_sha} has no embeddings loaded (rag_corpus."
            "embedding_modelo IS NULL) — it was ingested but never embedded. The "
            "vector leg would silently contribute nothing and the fused result "
            "would be FTS wearing a hybrid label. Run scripts/rag_embed_batch.py "
            "and scripts/rag_load_vectors.py, or ask for modo='fts'."
        )
    # Both revisions are canonicalized to their resolved commit hash BEFORE the
    # comparison, and a value that does not resolve is refused rather than
    # string-compared (`design.md:73-84`). Doing it here, on both operands, is
    # what keeps the guard from firing on two processes running the same weights
    # — a false positive whose symptom at the query surface is identical to the
    # true positive's, which is the worst possible shape for a guard.
    try:
        revision_almacenada = canonicalizar_revision(procedencia.revision_hf)
    except RevisionNoResoluble as no_resoluble:
        raise EmbedderMismatch(
            f"snapshot {corpus_sha} records embedding_revision_hf="
            f"{procedencia.revision_hf!r}, which is not a resolved commit hash. "
            "That is unknown provenance, not a match: two different commits can "
            "share a tag. Re-load a manifest that carries the resolved revision."
        ) from no_resoluble
    try:
        revision_del_embedder = canonicalizar_revision(embedder.revision)
    except RevisionNoResoluble as no_resoluble:
        raise EmbedderMismatch(
            f"the query embedder reports revision {embedder.revision!r}, which is "
            "not a resolved commit hash. Load it from a resolved revision — the "
            "sidecar reports what transformers recorded on the config, never the "
            "symbolic pin it was started from."
        ) from no_resoluble

    # NULL is UNKNOWN, not a wildcard. Rows loaded before the sidecar existed
    # hold `revision_hf IS NULL`, and treating that as "matches anything" would
    # restore the hole this check closes. The ONE exemption is the deterministic
    # fake, whose `revision` is `None` by construction (`embedding.py:304`) and
    # whose artifacts stamp `revision_hf: null` — and it is keyed on the
    # embedder's own `sintetico` flag rather than on the NULLs themselves, so a
    # REAL embedder reporting no revision is still unknown provenance
    # (`design.md:99-105`).
    if revision_almacenada is None and revision_del_embedder is None and embedder.sintetico:
        revision_almacenada = revision_del_embedder = _REVISION_SINTETICA
    elif revision_almacenada is None or revision_del_embedder is None:
        # Every operand is named, the model included: this branch also catches
        # the synthetic-rows/real-embedder pair, and a message that mentioned
        # only the revisions would report a model mismatch as a NULL problem.
        raise EmbedderMismatch(
            f"snapshot {corpus_sha} holds vectors produced by "
            f"{procedencia.modelo!r} at revision {procedencia.revision_hf!r}, and "
            f"the query embedder is {embedder.model_id!r} at revision "
            f"{embedder.revision!r}. A NULL revision on a real embedder is unknown "
            "provenance, not a wildcard: two BGE-M3 revisions report the same "
            "model_id and produce different vectors, so 'matches anything' is the "
            "hole this check exists to close. Re-load a manifest that carries the "
            "resolved revision (scripts/rag_embed_batch.py + rag_load_vectors.py)."
        )

    # One tuple check rather than two ifs, so a field cannot later be added to
    # one side only (`design.md:94-97`).
    if (procedencia.modelo, revision_almacenada) != (embedder.model_id, revision_del_embedder):
        raise EmbedderMismatch(
            f"snapshot {corpus_sha} holds vectors produced by "
            f"{procedencia.modelo!r} at revision {procedencia.revision_hf!r} "
            f"(sintetico={procedencia.sintetico}), but the query embedder is "
            f"{embedder.model_id!r} at revision {embedder.revision!r}. Distances "
            "across two different models — or two revisions of one model — are "
            "arithmetic without meaning: the leg would return a confident, fully "
            "attributed, entirely fabricated ranking. A NULL recorded revision is "
            "unknown provenance and is refused for the same reason."
        )


class RerankerRequerido(RuntimeError):
    """`modo="bm25_ce"` was asked for without a ranker to run it.

    A sibling of `EmbedderRequerido` and a refusal for the same reason: returning
    the BM25 order under the `bm25_ce` label would publish the candidate leg as
    if it were the ratified configuration. BM25 alone is candidate GENERATION; it
    was never measured as a ranking.
    """


class CorpusNoServible(RuntimeError):
    """The active snapshot must not be served from, and the reason is named.

    Today that means SYNTHETIC embeddings (task 7.6, `design.md:751-752`): the
    diagnostic endpoint reports `sintetico`, and serving refuses OUTRIGHT rather
    than answering a legal question from vectors nobody trained. The eval harness
    has the same guard on the publish side (`report._gate_sintetico`); this is
    the serving side of it, and the two exist for the same reason — a stand-in
    that is only reported, never refused, gets read as a measurement.
    """


class UmbralAbstencionNoCorresponde(CorpusNoServible):
    """The shipped abstention threshold was calibrated for a different base.

    A subclass of `CorpusNoServible` rather than a new category, because the
    consequence is identical and already wired: the worker turns it into
    `no_disponible` naming the exception, and the synchronous surface answers
    `base_de_conocimiento_no_lista`. Both say "this deployment is not ready",
    which is what an abstention threshold belonging to another corpus means —
    as opposed to "the corpus has nothing applicable", which is the one thing it
    must never be confused with.
    """


def verificar_umbral_abstencion(db: Session, corpus_sha: str) -> None:
    """Task 9.6 — serving reads the threshold artifact and refuses on mismatch.

    Read per retrieval and against LOADED state, for the same reason the three
    enablement facts are: re-deriving the threshold is a deploy, never a code
    change, and a check that ran once at import would keep serving against a
    stale number for as long as the process lived.

    A `no_derivado` artifact passes silently. That is not laxity: there is no
    number, so nothing can be served against the wrong one, and whether the
    surface may be enabled at all with no ratified abstention bar is owner
    decision 0.1 — a flag, not this function.
    """
    from app.domains.conocimiento.eval.umbral_abstencion import (
        UmbralAbstencionDivergente,
        cargar_umbral,
        verificar_identidad,
    )

    procedencia = procedencia_embeddings(db, corpus_sha)
    try:
        verificar_identidad(
            cargar_umbral(),
            corpus_sha=corpus_sha,
            embedding_modelo=procedencia.modelo if procedencia else None,
            embedding_revision_hf=procedencia.revision_hf if procedencia else None,
        )
    except UmbralAbstencionDivergente as exc:
        raise UmbralAbstencionNoCorresponde(str(exc)) from exc


def _recuperar_bm25_ce(
    db: Session,
    corpus_sha: str,
    pregunta: str,
    *,
    k: int,
    reranker: Reranker,
    profundidad: int,
) -> ResultadoRecuperacion:
    """The ratified `B50` path: BM25 top-50 over norma units, then the CE.

    Three properties are contracts rather than implementation details:

    * **no vector column is read**, at all — the vector leg is out of candidate
      generation (`design.md:1129-1131`) and the stored corpus vectors have no
      serving consumer on this path;
    * **the order is the cross-encoder's alone** — the BM25 score selected the
      pool and is carried for disclosure, never blended (`design.md:1136-1138`);
    * **no per-document cap** — REJECTED at ratification because it lifts hit@5
      to 0.793 while collapsing vigencia-correctness to 0.333
      (`design.md:1138-1139`).

    A copy of the question may be expanded before both legs (`expansion.py`):
    the original `pregunta` is what the result discloses and what the
    generator sees. The fused ablation arms never take this path.
    """
    pregunta_recuperacion = expandir_consulta_recuperacion(pregunta)
    indice = obtener_indice(db, corpus_sha)
    lexemas = lexemas_de_consulta(db, pregunta_recuperacion)
    candidatos = indice.buscar(lexemas, limite=profundidad)

    textos = textos_indexados(db, corpus_sha, [hit.citation_key for hit in candidatos])
    faltantes = [hit.citation_key for hit in candidatos if hit.citation_key not in textos]
    if faltantes:
        # Same failure the fused path names on hydration: a key the index holds
        # and the table does not means the snapshot moved under the query.
        raise IngestionAbort(
            f"{', '.join(faltantes)} are in the BM25 index of snapshot {corpus_sha} "
            "but have no row. The snapshot changed mid-query."
        )

    ordenados = ordenar_por_ce(
        reranker,
        pregunta_recuperacion,
        [
            Candidato(citation_key=hit.citation_key, texto_indexado=textos[hit.citation_key])
            for hit in candidatos
        ],
    )[:k]

    por_bm25 = _leg_map(candidatos)
    provenance = hydrate_citations(db, corpus_sha, [clave for clave, _ in ordenados])

    hits: list[CitaRecuperada] = []
    for citation_key, score_ce in ordenados:
        fila = provenance.get(citation_key)
        if fila is None:
            raise IngestionAbort(
                f"{citation_key} ranked in snapshot {corpus_sha} but has no row. "
                "The snapshot changed mid-query."
            )
        en_bm25 = por_bm25[citation_key]
        hits.append(
            CitaRecuperada(
                **fila,
                score_ce=score_ce,
                rango_bm25=en_bm25.rango,
                valor_bm25=en_bm25.valor,
            )
        )

    return ResultadoRecuperacion(
        corpus_sha=corpus_sha,
        pregunta=pregunta,
        modo="bm25_ce",
        k=k,
        hits=hits,
        n_bm25=len(candidatos),
        reranker_modelo=reranker.model_id,
        reranker_sintetico=reranker.sintetico,
    )


def recuperar(
    db: Session,
    corpus_sha: str,
    pregunta: str,
    *,
    modo: str = "hybrid",
    k: int = 10,
    embedder: Embedder | None = None,
    qvec: Sequence[float] | None = None,
    reranker: Reranker | None = None,
    limite_leg: int = LEG_LIMIT,
    rrf_k: int = RRF_K,
    profundidad_candidatos: int = PROFUNDIDAD_CANDIDATOS,
) -> ResultadoRecuperacion:
    """Run the requested legs and return fully attributed citations.

    Two shapes live behind one entry point. `fts`, `vector` and `hybrid` are the
    published V0 ablation: independent legs, RRF fusion, unchanged. `bm25_ce` is
    the ratified serving configuration and does not fuse at all — BM25 selects
    fifty norma candidates and the cross-encoder orders them (`_recuperar_bm25_ce`).
    The fused path below is NOT dead code kept for sentiment: it is the baseline
    the ratified configuration's numbers are quoted against.

    Determinism is a property of the whole chain and every link carries part of
    it: each leg sorts by `citation_key` as its secondary key, fusion sorts by
    `(-score, citation_key)`, and hydration preserves the fused order rather than
    the database's. Same question and same snapshot in, byte-identical ranked
    list out — which is what makes a gold-set number mean anything.

    The vector leg RAISES `VectorSupportUnavailable` where it cannot run. There
    is no fallback here and there must not be one: a `hybrid` run that quietly
    became `fts` would publish a comparison it never made. For the same reason it
    raises `EmbeddingsNoCargadas` on a snapshot that was never embedded and
    `EmbedderMismatch` when the query embedder is not the one that wrote the
    column: both are ways for the vector leg to contribute nothing, or nonsense,
    while the result still looks fused.

    `qvec` lets a caller that already embedded this question hand the vector in
    rather than pay a second sidecar hop for the same text under the same model
    (`design.md:145-160`). It bypasses no guard: `require_vector_support` and
    `verificar_embedder` still run, and `embedder` is still required for the
    vector modes, because the identity `verificar_embedder` compares lives on the
    embedder and not on the vector. Handing in a `qvec` computed by a DIFFERENT
    embedder than the one passed is a caller bug this guard structurally cannot
    see; the one call site that does this builds both from the same adapter.
    """
    if modo not in MODOS:
        raise ValueError(f"unknown modo {modo!r} (expected one of {MODOS})")

    if modo == "bm25_ce":
        if qvec is not None:
            # Accepting and ignoring it would be worse than refusing: the caller
            # would believe a vector reached the ranking, and `bm25_ce` reads no
            # vector column at all (`design.md:1129-1131`). The router computes
            # one query vector for its own stage 2; handing it here is a wiring
            # mistake, and a silent one has no symptom.
            raise ValueError(
                "modo='bm25_ce' has no vector leg, so a caller-supplied qvec "
                "would be silently discarded. Pass it only to 'vector'/'hybrid'."
            )
        if reranker is None:
            raise RerankerRequerido(
                "modo='bm25_ce' needs a reranker: BM25 selects the candidate pool "
                "and the cross-encoder is what ranks it. Returning the BM25 order "
                "alone would publish candidate generation as if it were the "
                "ratified B50 configuration."
            )
        return _recuperar_bm25_ce(
            db,
            corpus_sha,
            pregunta,
            k=k,
            reranker=reranker,
            profundidad=profundidad_candidatos,
        )

    if modo in ("vector", "hybrid") and embedder is None:
        raise EmbedderRequerido(
            f"modo={modo!r} needs an embedder to turn the question into a query "
            "vector. Falling back to FTS would answer a different question than "
            "the one asked."
        )

    if modo in ("vector", "hybrid"):
        assert embedder is not None  # guarded above; keeps mypy honest
        # Capability first, then content. A vector-less database cannot answer at
        # all, and saying so is more useful than reporting which model its (non-
        # existent) column was built with.
        require_vector_support(db)
        verificar_embedder(db, corpus_sha, embedder)

    hits_fts: list[LegHit] = []
    hits_vector: list[LegHit] = []

    if modo in ("fts", "hybrid"):
        hits_fts = fts_search(db, corpus_sha, pregunta, limite=limite_leg)
    if modo in ("vector", "hybrid"):
        assert embedder is not None  # guarded above; keeps mypy honest
        # One question, one embedding. The router's stage 2 and this leg need the
        # SAME vector of the SAME text under the SAME model; embedding twice
        # costs a second sidecar hop on the critical path and, worse, creates a
        # state where the router classified one vector and retrieval searched
        # another (`design.md:145-160`). `qvec` is a shortcut past the second
        # ENCODE and past nothing else — `require_vector_support` and
        # `verificar_embedder` already ran above, unconditionally, because the
        # identity they compare lives on the embedder and not on the vector.
        vector_de_consulta = qvec if qvec is not None else embedder.encode([pregunta])[0]
        hits_vector = vector_search(db, corpus_sha, vector_de_consulta, limite=limite_leg)

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
