"""Loader for `corpus_expectations.yaml` — the checked-in ingestion contract.

The YAML carries **two** inventories (design.md D2, "Gates"):

1. the article one — per-document expected `tipo_chunk='articulo'` counts plus
   the per-class subtotals (1358 + 6 + 19 + 0 = 1383);
2. the non-article one — the per-document expected `tipo_chunk` + citation key
   of every section the MANIFEST marks as *content but not articulado*.

Both halves are load-bearing. Counting non-article chunks toward 1383 breaks
the gate; not counting them **at all** is how Ley 10679's `## Vigencia de los
fondos` quietly never gets ingested and the system answers "el FDA venció en
2023" with a byte-exact citation.

It also carries each document's citation-key policy. That policy cannot be
derived from the frontmatter: `numero` is free text and reads, for example,
`3780 Serie C (1965) — aprueba Resolución DPH N° 1225 (1954)`. The MANIFEST
declares the keys instead (`9750#3`, `3780-C-65#punto-4`,
`res-aprhi-004-2026#art1`), so they are pinned here rather than re-derived.
"""

from __future__ import annotations

from dataclasses import dataclass
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
class DocumentPolicy:
    """Per-document ingestion contract: key shape plus both expected inventories."""

    documento_id: str
    archivo: str
    tipo: str
    es_secundaria: bool
    key_prefix: str
    key_style: str
    articulos: int
    no_articulos: tuple[NonArticleUnit, ...]

    def non_article_for(self, heading: str) -> NonArticleUnit | None:
        for unit in self.no_articulos:
            if unit.heading == heading:
                return unit
        return None


@dataclass(frozen=True)
class CorpusExpectations:
    corpus_sha: str
    manifest_version: int
    articulos_declarados: int
    subtotales_articulo: dict[str, int]
    no_articulos_declarados: int
    documentos: dict[str, DocumentPolicy]

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

    documentos: dict[str, DocumentPolicy] = {}
    for documento_id, entry in raw["documentos"].items():
        if entry["key_style"] not in KEY_STYLES:
            raise ValueError(
                f"{documento_id}: unknown key_style {entry['key_style']!r} "
                f"(expected one of {KEY_STYLES})"
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
        )

    return CorpusExpectations(
        corpus_sha=raw["corpus_sha"],
        manifest_version=raw["manifest_version"],
        articulos_declarados=raw["articulos_declarados"],
        subtotales_articulo=dict(raw["subtotales_articulo"]),
        no_articulos_declarados=raw["no_articulos_declarados"],
        documentos=documentos,
    )
