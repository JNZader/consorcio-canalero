"""Candidate generation: textbook BM25 over the lexemes Postgres already stored.

**Why not `ts_rank_cd`.** It is the obvious thing and it is measurably worse:
0.655 hit@5 against BM25's 0.759 on the same pool depth, the same reranker and
the same gold set (`docs/rag/candidate-recall-campaign-2026-08-23.md:374-390`).
`ts_rank_cd` has no IDF term at all — it scores term *density* inside a document
and is blind to how rare the term is in the corpus, which is exactly the signal
that separates "the article about expropiación" from the 300 articles that
mention "el" and "de". This module is therefore not an optimisation of the FTS
leg; it replaces its scoring function while keeping its analyzer.

**The analyzer is not reimplemented, and that is load-bearing.** The postings
list is built from `rag_unidad.tsv` — the GENERATED column whose definition
lives in migration `conocimiento_001` — and the query is stemmed by asking
Postgres for `to_tsvector('spanish', <pregunta>)`. Document side and query side
therefore go through one Snowball dictionary of one Postgres version. A Python
stemmer here would be a second analyzer that drifts silently: `intervenir`
indexes as `interven`, and any implementation that stems it to anything else
matches zero of the 13 units that carry it, with no error anywhere.

**The `tsv` weights are carried, not discarded.** The generated column is
`setweight(epigrafe, 'A') || setweight(texto_indexado, 'B')`, so a lexeme in an
article's epigraph is worth `PESO_A` occurrences and one in its body is worth
one. This is what the measured configuration did; changing it changes the
measurement.

**Norma-only.** The index is built over `es_secundaria = false` units, and the
filter is load-bearing rather than tidy: with fuentes secundarias in the pool the
cross-encoder's norma-vs-secundaria separation collapses to 0.483
(`design.md:1135-1136`) — the reranker happily puts a consultant's report above
the law it summarises, which is the single failure this corpus exists to prevent.

Measured cost at the pinned corpus (1398 norma units): 0.14 s to build, ~2 MB
resident, ~0.5 ms per query.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.conocimiento.repository import LegHit

#: Textbook BM25 parameters. `k1` bounds term-frequency saturation, `b` the
#: length normalisation. These are the values the campaign measured; they are
#: constants of the ratified configuration, not knobs.
BM25_K1: float = 1.2
BM25_B: float = 0.75

#: Weight of a `tsv` position labelled 'A' (the epígrafe half of the generated
#: column). Everything else counts as one occurrence.
PESO_A: float = 2.0

#: Candidate pool depth. The ratified configuration is `B50`: fifty norma units,
#: reranked. Deeper pools were measured and did not help — the exhaustive ceiling
#: over all 1398 units scores 0.724, BELOW this, because a bounded pool is also a
#: precision filter (`design.md:1129-1131`).
PROFUNDIDAD_CANDIDATOS: int = 50

#: One `'lexema':posiciones` entry of a `tsvector`'s text rendering. A lexeme is
#: single-quoted and an embedded quote is doubled, so the body is "anything but a
#: quote, or a doubled quote". Positions are digits with optional weight labels.
_ENTRADA_TSV = re.compile(r"'((?:[^']|'')*)':([0-9A-D,]+)")


class IndiceVacio(RuntimeError):
    """The snapshot holds no searchable norma unit.

    A refusal rather than an empty index, for the same reason the vector leg
    refuses a snapshot that was never embedded: "nothing matched your question"
    and "this snapshot has nothing to match against" are different facts, and
    only one of them is about the question.
    """


def parse_tsv(raw: str | None) -> dict[str, float]:
    """`{lexema: frecuencia ponderada}` from a `tsvector`'s text rendering.

    Reads what Postgres wrote rather than re-tokenising the source text: this is
    the same lexeme set the GIN index holds and the same one `@@` would match.
    """
    salida: dict[str, float] = {}
    if not raw:
        return salida
    for lexema, posiciones in _ENTRADA_TSV.findall(raw):
        lexema = lexema.replace("''", "'")
        peso = 0.0
        for posicion in posiciones.split(","):
            peso += PESO_A if posicion.endswith("A") else 1.0
        salida[lexema] = salida.get(lexema, 0.0) + peso
    return salida


_UNIDADES_NORMA_SQL = text(
    """
    SELECT u.citation_key, CAST(u.tsv AS text)
    FROM rag_unidad u
    JOIN rag_documento d
      ON d.corpus_sha = u.corpus_sha AND d.documento_id = u.documento_id
    WHERE u.corpus_sha = :corpus_sha AND d.es_secundaria = false
    ORDER BY u.citation_key ASC
    """
)

_LEXEMAS_CONSULTA_SQL = text("SELECT CAST(to_tsvector('spanish', :pregunta) AS text)")


def lexemas_de_consulta(db: Session, pregunta: str) -> dict[str, float]:
    """Stem the question IN POSTGRES, with the same dictionary the column used.

    The frequencies come back for symmetry of parsing only: BM25's query side
    weights each distinct term once, which is what `IndiceBM25.buscar` does.
    """
    return parse_tsv(db.execute(_LEXEMAS_CONSULTA_SQL, {"pregunta": pregunta}).scalar_one())


@dataclass(frozen=True)
class IndiceBM25:
    """An in-process postings list over one snapshot's norma units.

    Immutable by construction: a snapshot is a snapshot, and an index that could
    be mutated in place would be a cache whose contents no longer name what they
    were built from.
    """

    corpus_sha: str
    #: Insertion-ordered by `citation_key`, which is what makes a tie in the
    #: score resolve deterministically.
    claves: tuple[str, ...]
    tf: Mapping[str, Mapping[str, float]]
    doclen: Mapping[str, float]
    avgdl: float
    idf: Mapping[str, float]

    @property
    def n_unidades(self) -> int:
        return len(self.claves)

    def buscar(
        self,
        lexemas: Mapping[str, float],
        limite: int = PROFUNDIDAD_CANDIDATOS,
    ) -> list[LegHit]:
        """Top-`limite` units by BM25, ranked and attributed like any other leg.

        A query lexeme absent from the corpus contributes nothing — it has no
        IDF, not an infinite one. A query that reduces to no known lexeme returns
        an empty list, which is a legitimate answer and stays distinguishable
        from a refusal.

        Each DISTINCT query lexeme counts once. Repeating a word in the question
        is emphasis a human hears; giving it double weight would let a phrasing
        tic outrank the corpus.

        `citation_key` is the secondary sort and it is not tidiness: this corpus
        holds 45 articles whose entire body is the words "Sin Reglamentar"
        (`MANIFEST.md:658-660`). They score identically, and at the `limite`
        boundary an arbitrary order would decide which of them is even seen.
        """
        puntajes: dict[str, float] = {}
        for lexema in lexemas:
            peso_idf = self.idf.get(lexema)
            if peso_idf is None:
                continue
            for clave in self.claves:
                frecuencia = self.tf[clave].get(lexema)
                if not frecuencia:
                    continue
                denominador = frecuencia + BM25_K1 * (
                    1.0 - BM25_B + BM25_B * self.doclen[clave] / self.avgdl
                )
                puntajes[clave] = puntajes.get(clave, 0.0) + peso_idf * (
                    frecuencia * (BM25_K1 + 1.0) / denominador
                )
        ordenados = sorted(puntajes.items(), key=lambda par: (-par[1], par[0]))[:limite]
        return [
            LegHit(citation_key=clave, rango=rango, valor=valor)
            for rango, (clave, valor) in enumerate(ordenados)
        ]


def construir_indice(db: Session, corpus_sha: str) -> IndiceBM25:
    """Read the snapshot's norma lexemes and derive the postings statistics.

    `N` and every document frequency are computed over the NORMA subset, not over
    the whole snapshot, because that subset is the collection actually being
    searched: an IDF computed over documents the query can never reach would
    describe a corpus this leg does not have.
    """
    filas = db.execute(_UNIDADES_NORMA_SQL, {"corpus_sha": corpus_sha}).all()
    if not filas:
        raise IndiceVacio(
            f"snapshot {corpus_sha} has no `es_secundaria = false` units, so there "
            "is nothing to build a candidate index over. An empty index would "
            "answer every question with an empty pool, which reads exactly like a "
            "question nothing matched."
        )

    claves = tuple(fila[0] for fila in filas)
    tf = {fila[0]: parse_tsv(fila[1]) for fila in filas}
    doclen = {clave: math.fsum(tf[clave].values()) for clave in claves}
    avgdl = math.fsum(doclen.values()) / len(claves)
    if avgdl <= 0.0:
        raise IndiceVacio(
            f"snapshot {corpus_sha} has {len(claves)} norma units and not one "
            "indexable lexeme among them. The length normalisation would divide "
            "by zero; refusing is the honest outcome."
        )

    df: Counter[str] = Counter()
    for clave in claves:
        for lexema in tf[clave]:
            df[lexema] += 1
    total = len(claves)
    idf = {lexema: math.log(1.0 + (total - n + 0.5) / (n + 0.5)) for lexema, n in df.items()}

    return IndiceBM25(
        corpus_sha=corpus_sha,
        claves=claves,
        tf=tf,
        doclen=doclen,
        avgdl=avgdl,
        idf=idf,
    )


#: One index per snapshot, per process. Keyed by `corpus_sha` alone because that
#: is what the snapshot IS — `rag_unidad` rows are immutable within a SHA except
#: through a re-ingest, which is a named, ordered runbook step and not something
#: that happens under a running query. `limpiar_cache_indices` exists for the
#: tests that seed several snapshots into one process and for a re-ingest that
#: reuses the same SHA.
_CACHE: dict[str, IndiceBM25] = {}


def obtener_indice(db: Session, corpus_sha: str, *, refrescar: bool = False) -> IndiceBM25:
    """The cached index for this snapshot, built on first use (measured 0.14 s)."""
    if refrescar:
        _CACHE.pop(corpus_sha, None)
    indice = _CACHE.get(corpus_sha)
    if indice is None:
        indice = construir_indice(db, corpus_sha)
        _CACHE[corpus_sha] = indice
    return indice


def limpiar_cache_indices() -> None:
    """Drop every cached index. Called by tests and after a re-ingest."""
    _CACHE.clear()
