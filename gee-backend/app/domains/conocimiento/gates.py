"""Ingestion gates — hard aborts, not warnings (design.md D2, "Gates").

Seven gates run before the ingestion transaction commits. Any failure aborts, so
a partial or drifted snapshot never becomes the active one:

1. **Per-document AND total article count.** A total-only check is exactly how a
   compensating pair of over- and under-capture passes unnoticed.
2. **Non-article inventory**, asserted with the same per-document strictness and
   never folded into the 1383. Both halves are load-bearing.
3. **Verbatim substring** — every `texto` is byte-exact in its source file.
4. **Citation-key uniqueness**, including the D-9 collision pairs.
5. **Token ceiling** — a unit over the embedding model's 8192-token context is
   recorded and reported (and aborts under `--strict-token-ceiling`) instead of
   being silently truncated at embedding time.
6. **Heading coverage** — every `#`/`##` heading is captured, declared, or
   explicitly excluded. Gates 1 and 2 only check what the YAML *claims*; a
   section nobody claimed is invisible to both.
7. **Corpus file inventory** — every `.md` in the checkout is a declared
   document or an explicitly declared non-document.

Gates 1-5 verify the declared inventory. Gates 6 and 7 are what make that
inventory *exhaustive*, and they exist because both holes were real: Res. APRHI
3/2026's ANEXO I and II were in no inventory and therefore in no index, with
every count gate green (ledger RAG2-001); and a corpus `.md` never listed under
`documentos` is not ingested and raises no error anywhere (its sibling).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from app.domains.conocimiento.expectations import CorpusExpectations, DocumentPolicy
from app.domains.conocimiento.parser import H1_RE, H2_RE, Unidad, body_offset

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


def heading_coverage_gate(
    parsed: Mapping[str, Sequence[Unidad]],
    sources: Mapping[str, str],
    expectations: CorpusExpectations,
    report: GateReport,
) -> None:
    """Every `#`/`##` heading must be captured, declared, or explicitly excluded.

    The count gates are only as exhaustive as the YAML they check against: they
    compare produced units to *declared* units, so a section declared nowhere is
    invisible to both. Res. APRHI 3/2026's `# ANEXO I` — the planilla of 25
    afectaciones its own art. 1° declares to "integrar el presente instrumento
    legal", content that exists in no other document — sat outside the index
    with all five original gates green (ledger RAG2-001).

    A heading passes on exactly three grounds, and the third is the point:

    * it falls inside a captured unit's span (an article, or a sub-heading of
      one — a `##` inside a level-1 anexo is *part of* that unit, not a
      separate one);
    * it is declared in `no_articulos` (missing production is then the
      non-article inventory gate's failure to report, not this one's);
    * it is listed in the document's `excluidos`, under a class declared in
      `clases_excluidas`.

    Anything else fails. Adding a heading to `excluidos` is cheap — that is
    deliberate. The cost this gate imposes is not effort, it is *having to say
    so*, which is precisely what nobody did for the anexos.
    """
    for documento_id, policy in expectations.documentos.items():
        source = sources.get(documento_id)
        if source is None:
            # Already reported by the article count gate; nothing to scan.
            continue

        unidades = parsed.get(documento_id, ())
        spans = [(u.source_offset, u.source_offset + len(u.texto)) for u in unidades]
        start_of_body = body_offset(source)

        for regex in (H1_RE, H2_RE):
            for match in regex.finditer(source, start_of_body):
                offset = match.start()
                heading = match.group("titulo").strip()
                if any(begin <= offset < end for begin, end in spans):
                    continue
                if policy.non_article_for(heading) is not None:
                    continue
                if policy.is_excluded(heading):
                    continue
                report.failures.append(
                    f"{documento_id}: heading {heading!r} (offset {offset}) is in no "
                    "inventory — it is not inside a captured unit, not declared in "
                    "no_articulos, and not listed in excluidos. Index it or declare "
                    "why it is excluded; silence is what made RAG2-001 invisible."
                )


def corpus_file_inventory_gate(
    corpus_path: Path,
    expectations: CorpusExpectations,
    report: GateReport,
) -> None:
    """Every `.md` in the checkout is a declared document or a declared non-document.

    `load_corpus` iterates the YAML's documents and reads each one, so a corpus
    file that nobody listed is never opened, never parsed, never counted and
    never reported: it is simply absent, and every gate stays green. That is the
    same failure shape as RAG2-001 one level up — the inventory is only
    exhaustive if something compares it against reality.
    """
    if not corpus_path.is_dir():
        report.failures.append(f"corpus path {corpus_path} is not a directory")
        return

    declared = {policy.archivo for policy in expectations.documentos.values()}
    for path in sorted(corpus_path.glob("*.md")):
        if path.name in declared or path.name in expectations.archivos_no_documento:
            continue
        report.failures.append(
            f"{path.name} is present in the corpus checkout but declared neither "
            "in `documentos` nor in `archivos_no_documento`. An unlisted file is "
            "never ingested and never reported."
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
    corpus_path: Path | None = None,
) -> GateReport:
    """Run every gate and return the accumulated report.

    Gates do NOT short-circuit: one run reports every problem at once, because
    fixing a corpus one abort at a time is how a five-minute check becomes an
    afternoon.

    `corpus_path` is optional only because the unit-level gate tests build a
    parse in memory with no checkout behind it. Real ingestion always passes it
    — `gate_corpus` takes it from the `LoadedCorpus` — so the file inventory
    gate is never skipped on the path that writes rows.
    """
    report = GateReport(documentos=len(parsed))
    article_count_gate(parsed, expectations, report)
    non_article_inventory_gate(parsed, expectations, report)
    heading_coverage_gate(parsed, sources, expectations, report)
    verbatim_substring_gate(parsed, sources, report)
    citation_key_uniqueness_gate(parsed, report)
    token_ceiling_gate(parsed, report, token_counter, strict=strict_token_ceiling)
    if corpus_path is not None:
        corpus_file_inventory_gate(corpus_path, expectations, report)
    return report


def policy_for(expectations: CorpusExpectations, documento_id: str) -> DocumentPolicy:
    return expectations.policy_for(documento_id)
