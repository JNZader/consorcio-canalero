"""Fixtures for the conocimiento (RAG) ingestion tests.

Every fixture under `fixtures/` is a byte-exact slice of the real SHA-pinned
corpus (verbatim YAML frontmatter block + verbatim body line ranges), so
fixture-driven parser tests still exercise the corpus's real shapes without
baking `~/Escritorio/...` into the repository (design.md D2, "Corpus location").
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# The corpus revision every expectation in this suite is pinned to.
PINNED_CORPUS_SHA = "12043582bf8016288a7e8084e85a4b713a97af2f"


def load_fixture(name: str) -> tuple[str, dict[str, Any]]:
    """Return `(markdown_text, frontmatter)` for a checked-in corpus fragment."""
    text = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    end = text.find("\n---\n", 3)
    if not text.startswith("---\n") or end == -1:
        raise AssertionError(f"fixture {name} has no YAML frontmatter block")
    return text, yaml.safe_load(text[4 : end + 1]) or {}


@pytest.fixture
def fixture_loader():
    return load_fixture


def real_corpus_path() -> Path | None:
    """The real corpus checkout, or None when it is not available.

    Gate tests that assert the full 1383-unit inventory need the actual
    SHA-pinned checkout; CI has no access to the private corpus repository, so
    those tests skip there and run locally. The gates themselves are NOT
    optional — they are wired into `rag_ingest.py` and abort ingestion
    (design.md D2, "Gates").
    """
    raw = os.environ.get("RAG_CORPUS_PATH")
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if (path / "MANIFEST.md").is_file() else None


def requires_real_corpus(obj):
    """Mark a test as part of the corpus contract AND skip it without a corpus.

    The `corpus` marker is what makes the skipping *visible*: `make
    test-rag-corpus` selects exactly these tests and fails when any of them is
    skipped, so "the corpus suite passed" can never again mean "the corpus suite
    did not run". Plain `pytest tests/new/` (the CI shape) still skips them, by
    design and now on the record — CI genuinely cannot hold the private corpus
    (ledger RAG2-005).
    """
    obj = pytest.mark.corpus(obj)
    return pytest.mark.skipif(
        real_corpus_path() is None,
        reason="set RAG_CORPUS_PATH to a checkout of consorcio-corpus-legal at the pinned SHA",
    )(obj)
