"""Loader for `corpus_expectations.yaml` — the checked-in ingestion contract.

The YAML carries **three** inventories (design.md D2, "Gates"):

1. the article one — per-document expected `tipo_chunk='articulo'` counts plus
   the per-class subtotals (1358 + 6 + 19 + 0 = 1383);
2. the non-article one — the per-document expected `tipo_chunk` + citation key
   of every section the MANIFEST marks as *content but not articulado*;
3. the **exclusion** one — every remaining `#`/`##` heading, each tagged with a
   declared exclusion class. Inventories 1 and 2 say what MUST be indexed;
   inventory 3 is what makes the first two exhaustive.

All three are load-bearing. Counting non-article chunks toward 1383 breaks the
gate; not counting them **at all** is how Ley 10679's `## Vigencia de los
fondos` quietly never gets ingested and the system answers "el FDA venció en
2023" with a byte-exact citation. And leaving a heading out of all three is how
Res. APRHI 3/2026's ANEXO I — the 25 afectaciones its own art. 1° declares to
"integrar el presente instrumento legal" — was absent from the index with every
count gate green (ledger RAG2-001). A section that is in none of the three
inventories is now a gate failure, not a silence.

It also carries each document's citation-key policy. That policy cannot be
derived from the frontmatter: `numero` is free text and reads, for example,
`3780 Serie C (1965) — aprueba Resolución DPH N° 1225 (1954)`. The MANIFEST
declares the keys instead (`9750#3`, `3780-C-65#punto-4`,
`res-aprhi-004-2026#art1`), so they are pinned here rather than re-derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

EXPECTATIONS_PATH = Path(__file__).parent / "corpus_expectations.yaml"

#: Key shapes declared by the MANIFEST, one per document.
#:   ``numero``   -> ``9750#3``, ``5589#193bis``, ``5350#13quater``
#:   ``articulo`` -> ``res-aprhi-004-2026#art1``, ``10demayo#res189-2014#art1``
#:   ``punto``    -> ``3780-C-65#punto-4``, ``srh-2013#punto-1``
KEY_STYLES = ("numero", "articulo", "punto")


@dataclass(frozen=True)
class NonArticleUnit:
    """One section the MANIFEST indexes as content but not as articulado."""

    heading: str
    tipo_chunk: str
    citation_key: str


@dataclass(frozen=True)
class ExcludedHeading:
    """One heading deliberately left out of the index, and why.

    `clase` keys into the corpus-level `clases_excluidas` map, which carries the
    prose reason once instead of repeating it across ~250 entries. That keeps
    every exclusion greppable by class ("show me everything excluded as
    `contenido-no-declarado`") — the review affordance a free-text `motivo` per
    entry loses as soon as two people phrase the same reason differently.
    """

    heading: str
    clase: str


@dataclass(frozen=True)
class DocumentPolicy:
    """Per-document ingestion contract: key shape plus all three inventories."""

    documento_id: str
    archivo: str
    tipo: str
    es_secundaria: bool
    key_prefix: str
    key_style: str
    articulos: int
    no_articulos: tuple[NonArticleUnit, ...]
    excluidos: tuple[ExcludedHeading, ...] = ()

    def non_article_for(self, heading: str) -> NonArticleUnit | None:
        for unit in self.no_articulos:
            if unit.heading == heading:
                return unit
        return None

    def is_excluded(self, heading: str) -> bool:
        return any(item.heading == heading for item in self.excluidos)


@dataclass(frozen=True)
class CorpusExpectations:
    corpus_sha: str
    manifest_version: int
    articulos_declarados: int
    subtotales_articulo: dict[str, int]
    no_articulos_declarados: int
    documentos: dict[str, DocumentPolicy]
    #: Exclusion class -> the one-line reason every heading tagged with it shares.
    clases_excluidas: dict[str, str] = field(default_factory=dict)
    #: Files in the corpus checkout that are deliberately not documents
    #: (MANIFEST/README-class). Anything else unlisted is a gate failure.
    archivos_no_documento: frozenset[str] = frozenset()

    def policy_for(self, documento_id: str) -> DocumentPolicy:
        try:
            return self.documentos[documento_id]
        except KeyError:
            raise KeyError(
                f"{documento_id!r} is not declared in corpus_expectations.yaml. "
                "Every document needs a pinned citation-key policy and expected "
                "counts before it can be ingested."
            ) from None


@lru_cache(maxsize=1)
def load_expectations(path: Path | None = None) -> CorpusExpectations:
    raw = yaml.safe_load((path or EXPECTATIONS_PATH).read_text(encoding="utf-8"))
    clases_excluidas = dict(raw.get("clases_excluidas", {}))

    documentos: dict[str, DocumentPolicy] = {}
    for documento_id, entry in raw["documentos"].items():
        if entry["key_style"] not in KEY_STYLES:
            raise ValueError(
                f"{documento_id}: unknown key_style {entry['key_style']!r} "
                f"(expected one of {KEY_STYLES})"
            )
        for item in entry.get("excluidos", ()):
            # An exclusion whose class is not declared is an exclusion with no
            # stated reason — exactly what this inventory exists to prevent.
            if item["clase"] not in clases_excluidas:
                raise ValueError(
                    f"{documento_id}: heading {item['heading']!r} is excluded under "
                    f"undeclared class {item['clase']!r}. Add it to "
                    "`clases_excluidas` with its reason before excluding anything "
                    "under it."
                )
        documentos[documento_id] = DocumentPolicy(
            documento_id=documento_id,
            archivo=entry["archivo"],
            tipo=entry["tipo"],
            es_secundaria=entry["es_secundaria"],
            key_prefix=entry["key_prefix"],
            key_style=entry["key_style"],
            articulos=entry["articulos"],
            no_articulos=tuple(
                NonArticleUnit(
                    heading=item["heading"],
                    tipo_chunk=item["tipo_chunk"],
                    citation_key=item["citation_key"],
                )
                for item in entry["no_articulos"]
            ),
            excluidos=tuple(
                ExcludedHeading(heading=item["heading"], clase=item["clase"])
                for item in entry.get("excluidos", ())
            ),
        )

    return CorpusExpectations(
        corpus_sha=raw["corpus_sha"],
        manifest_version=raw["manifest_version"],
        articulos_declarados=raw["articulos_declarados"],
        subtotales_articulo=dict(raw["subtotales_articulo"]),
        no_articulos_declarados=raw["no_articulos_declarados"],
        documentos=documentos,
        clases_excluidas=clases_excluidas,
        archivos_no_documento=frozenset(raw.get("archivos_no_documento", ())),
    )


# ---------------------------------------------------------------------------
# `eval/expected_clasificacion.yaml` — the checked-in privacy expectation
# ---------------------------------------------------------------------------
#
# It lives under `eval/` (design.md's file table) but is loaded from HERE, not
# from the eval package: the eval package may not import `repository`
# (design.md D4) and the diff this artifact exists for is a diff against the
# ingest rule. `expectations.py` already owns the checked-in contracts and
# imports nothing from `repository`, so the loader belongs here and the
# comparison happens in the caller.

EXPECTED_CLASIFICACION_PATH = Path(__file__).parent / "eval" / "expected_clasificacion.yaml"


class ClasificacionShaMismatch(RuntimeError):
    """The artifact is pinned to a different corpus revision than the snapshot."""


@dataclass(frozen=True)
class ExpectedClasificacion:
    """One document's expected class and the evidence string it derives from."""

    documento_id: str
    tipo: str
    es_secundaria: bool
    clasificacion: str
    evidencia: str


@dataclass(frozen=True)
class ExpectedClasificaciones:
    corpus_sha: str
    #: `repository.regla_clasificacion_sha256()` at generation time. A rule
    #: change that does not regenerate this artifact fails the unit diff, which
    #: is the point: 11 of 35 documents have checked-in fixtures, so a widening
    #: that only touches the other 24 would otherwise be invisible in CI.
    regla_sha256: str
    documentos: dict[str, ExpectedClasificacion]

    def por_clase(self, clase: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                doc_id for doc_id, item in self.documentos.items() if item.clasificacion == clase
            )
        )


@lru_cache(maxsize=1)
def load_expected_clasificacion(path: Path | None = None) -> ExpectedClasificaciones:
    raw = yaml.safe_load((path or EXPECTED_CLASIFICACION_PATH).read_text(encoding="utf-8"))
    documentos = {
        entry["documento_id"]: ExpectedClasificacion(
            documento_id=entry["documento_id"],
            tipo=entry["tipo"],
            es_secundaria=bool(entry["es_secundaria"]),
            clasificacion=entry["clasificacion"],
            evidencia=entry["evidencia"],
        )
        for entry in raw["documentos"]
    }
    return ExpectedClasificaciones(
        corpus_sha=str(raw["corpus_sha"]),
        regla_sha256=str(raw["regla_sha256"]),
        documentos=documentos,
    )


def verificar_corpus_sha_clasificacion(expected: ExpectedClasificaciones, corpus_sha: str) -> None:
    """Refuse an artifact pinned to a different corpus revision than the snapshot.

    Same discipline as `harness.verificar_corpus_sha`, and for the same reason
    scaled up: a `fuente_url` list is corpus content, so an expectation written
    against one revision says nothing about another. Compared against the wrong
    snapshot, a document that was promoted by a URL added later is
    indistinguishable from a rule regression.
    """
    if expected.corpus_sha != corpus_sha:
        raise ClasificacionShaMismatch(
            f"expected_clasificacion.yaml is pinned to corpus_sha "
            f"{expected.corpus_sha} but the snapshot being checked is "
            f"{corpus_sha}. Every expected class was derived from the first "
            "revision's frontmatter; diffed against the second, a promotion that "
            "a later URL caused is indistinguishable from a rule regression. "
            "Regenerate the artifact against the snapshot you mean to check."
        )
