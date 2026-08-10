"""Ingestion gates — hard aborts, not warnings (design.md D2, "Gates").

Five gates run inside the ingestion transaction. Any failure aborts before a
commit, so a partial or drifted snapshot never becomes the active one:

1. **Per-document AND total article count.** A total-only check is exactly how a
   compensating pair of over- and under-capture passes unnoticed.
2. **Non-article inventory**, asserted with the same per-document strictness and
   never folded into the 1383. Both halves are load-bearing.
3. **Verbatim substring** — every `texto` is byte-exact in its source file.
4. **Citation-key uniqueness**, including the D-9 collision pairs.
5. **Token ceiling** — a unit over the embedding model's 8192-token context
   aborts instead of being silently truncated at embedding time.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from app.domains.conocimiento.expectations import CorpusExpectations, DocumentPolicy
from app.domains.conocimiento.parser import Unidad

#: BGE-M3 (XLM-R) context ceiling. The MANIFEST forbids splitting long articles,
#: so silent truncation is the only failure mode that could survive review.
TOKEN_CEILING = 8192

#: Bytes-per-token for Spanish legal prose under XLM-R, calibrated on the
#: design's own measured datum: Ley 10679's `## Vigencia de los fondos` is
#: ~19.4 kB and ≈6 k XLM-R tokens (design.md D2), i.e. ≈3.2 B/token. 3.0
#: under-states that slightly, so the estimate errs toward over-counting tokens
#: — a loud false positive rather than a silent pass.
#:
#: This is an ESTIMATE. `transformers`/BGE-M3 is an ingestion-extra dependency
#: that arrives with slice 3, so `scripts/rag_embed_batch.py` re-runs the same
#: ceiling with the REAL tokenizer at embed pre-flight, which is where design D3
#: puts the hard abort. Pass a real `token_counter` here to get the exact count.
CONSERVATIVE_BYTES_PER_TOKEN = 3.0


class GateFailure(RuntimeError):
    """A gate rejected the parsed corpus. Ingestion must not commit."""


@dataclass
class GateReport:
    """Accumulated gate outcomes. `ok` is False if anything failed."""

    failures: list[str] = field(default_factory=list)
    articulos_total: int = 0
    no_articulos_total: int = 0
    documentos: int = 0
    #: Units whose indexed text exceeds the embedding context ceiling, as
    #: `(citation_key, tokens)`. First-class and always reported — never
    #: silently dropped and never truncated. They are separate from `failures`
    #: because the ceiling is an EMBEDDING constraint: an over-ceiling unit is
    #: still perfectly retrievable by FTS, and blocking ingestion on it would
    #: break the FTS-only leg of the ablation that slices 1-2 are meant to keep
    #: independently useful. `--strict-token-ceiling` promotes them to failures.
    over_ceiling: list[tuple[str, int]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def raise_if_failed(self) -> None:
        if self.failures:
            raise GateFailure(
                f"{len(self.failures)} ingestion gate failure(s):\n  - "
                + "\n  - ".join(self.failures)
            )


def estimate_tokens(text: str) -> int:
    """Conservative token-count estimate used when no real tokenizer is loaded."""
    return int(len(text) / CONSERVATIVE_BYTES_PER_TOKEN) + 1


def article_count_gate(
    parsed: Mapping[str, Sequence[Unidad]],
    expectations: CorpusExpectations,
    report: GateReport,
) -> None:
    """Assert per-document AND total `tipo_chunk='articulo'` counts."""
    total = 0
    for documento_id, policy in expectations.documentos.items():
        unidades = parsed.get(documento_id)
        if unidades is None:
            report.failures.append(f"{documento_id}: declared in expectations but never parsed")
            continue
        actual = sum(1 for u in unidades if u.tipo_chunk == "articulo")
        total += actual
        if actual != policy.articulos:
            report.failures.append(
                f"{documento_id}: expected {policy.articulos} articulo units, got {actual}"
            )

    report.articulos_total = total
    if total != expectations.articulos_declarados:
        report.failures.append(
            f"corpus total: expected {expectations.articulos_declarados} articulo "
            f"units, got {total}"
        )


def non_article_inventory_gate(
    parsed: Mapping[str, Sequence[Unidad]],
    expectations: CorpusExpectations,
    report: GateReport,
) -> None:
    """Assert the non-article inventory per document, never folded into 1383."""
    total = 0
    for documento_id, policy in expectations.documentos.items():
        unidades = parsed.get(documento_id, ())
        actual = {u.citation_key: u.tipo_chunk for u in unidades if u.tipo_chunk != "articulo"}
        expected = {item.citation_key: item.tipo_chunk for item in policy.no_articulos}
        total += len(actual)

        for key, tipo_chunk in expected.items():
            if key not in actual:
                report.failures.append(
                    f"{documento_id}: expected non-article unit {key!r} "
                    f"({tipo_chunk}) was not produced"
                )
            elif actual[key] != tipo_chunk:
                report.failures.append(
                    f"{documento_id}: {key!r} expected tipo_chunk {tipo_chunk!r}, "
                    f"got {actual[key]!r}"
                )
        for key in actual:
            if key not in expected:
                report.failures.append(
                    f"{documento_id}: produced undeclared non-article unit {key!r}"
                )

    report.no_articulos_total = total
    if total != expectations.no_articulos_declarados:
        report.failures.append(
            f"corpus total: expected {expectations.no_articulos_declarados} "
            f"non-article units, got {total}"
        )


def verbatim_substring_gate(
    parsed: Mapping[str, Sequence[Unidad]],
    sources: Mapping[str, str],
    report: GateReport,
) -> None:
    """Every `texto` must be a byte-exact substring of its source file.

    Checked at the unit's declared offset, not with `in`: a substring that
    matches somewhere else would still make `source_offset` a lie, and the
    embedding/citation provenance rests on that offset.
    """
    for documento_id, unidades in parsed.items():
        source = sources[documento_id]
        for unidad in unidades:
            start = unidad.source_offset
            if source[start : start + len(unidad.texto)] != unidad.texto:
                report.failures.append(
                    f"{documento_id}: {unidad.citation_key!r} is not a byte-exact "
                    f"substring of its source at offset {start}"
                )


def citation_key_uniqueness_gate(
    parsed: Mapping[str, Sequence[Unidad]],
    report: GateReport,
) -> None:
    """Citation keys are unique across the whole snapshot (D-9 included)."""
    counts = Counter(u.citation_key for unidades in parsed.values() for u in unidades)
    for key, count in sorted(counts.items()):
        if count > 1:
            report.failures.append(f"duplicate citation_key {key!r} appears {count} times")


def token_ceiling_gate(
    parsed: Mapping[str, Sequence[Unidad]],
    report: GateReport,
    token_counter: Callable[[str], int] = estimate_tokens,
    strict: bool = False,
) -> None:
    """Record every unit whose indexed text exceeds the model's context ceiling.

    Nothing is ever truncated here — that is the whole point. The MANIFEST
    forbids splitting long articles, so an over-ceiling unit is a decision to
    surface (embed it degraded, or leave it FTS-only), never something to quietly
    cut to fit. With `strict=True` the run aborts instead.
    """
    for documento_id, unidades in parsed.items():
        for unidad in unidades:
            tokens = token_counter(unidad.texto_indexado)
            if tokens > TOKEN_CEILING:
                report.over_ceiling.append((unidad.citation_key, tokens))
                if strict:
                    report.failures.append(
                        f"{documento_id}: {unidad.citation_key!r} is ~{tokens} "
                        f"tokens, over the {TOKEN_CEILING} ceiling. Aborting "
                        "rather than letting the embedder truncate it silently."
                    )


def run_all_gates(
    parsed: Mapping[str, Sequence[Unidad]],
    sources: Mapping[str, str],
    expectations: CorpusExpectations,
    token_counter: Callable[[str], int] = estimate_tokens,
    strict_token_ceiling: bool = False,
) -> GateReport:
    """Run every gate and return the accumulated report.

    Gates do NOT short-circuit: one run reports every problem at once, because
    fixing a corpus one abort at a time is how a five-minute check becomes an
    afternoon.
    """
    report = GateReport(documentos=len(parsed))
    article_count_gate(parsed, expectations, report)
    non_article_inventory_gate(parsed, expectations, report)
    verbatim_substring_gate(parsed, sources, report)
    citation_key_uniqueness_gate(parsed, report)
    token_ceiling_gate(parsed, report, token_counter, strict=strict_token_ceiling)
    return report


def policy_for(expectations: CorpusExpectations, documento_id: str) -> DocumentPolicy:
    return expectations.policy_for(documento_id)
