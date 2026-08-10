"""Corpus loading + gate orchestration for ingestion.

Everything here is pure with respect to the database: it reads a checkout,
parses it, and runs the gates. `scripts/rag_ingest.py` owns the transaction and
is the only thing that writes.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domains.conocimiento.expectations import CorpusExpectations, load_expectations
from app.domains.conocimiento.gates import GateReport, run_all_gates
from app.domains.conocimiento.parser import Unidad, parse_document
from app.domains.conocimiento.repository import IngestionAbort


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
