"""The sentinel that makes the corpus contract's skipping honest.

Every content test in this package hides behind `requires_real_corpus`, and CI
never sets `RAG_CORPUS_PATH` — the corpus repository is private and V0 is
all-local by owner rule. So the 35-document check, the 1383/65 counts, the
vigencia canary, the verbatim gate, determinism, pruning and idempotency all
report **skipped, and the run is green**. That is the correct behaviour for CI
and a terrible property to leave unstated (ledger RAG2-005).

The honest fix is not to smuggle the corpus into CI. It is two things:

* `make test-rag-corpus` runs exactly the `corpus`-marked tests and fails when
  any of them is *skipped*, so a local run cannot silently cover nothing;
* the test below, which turns the one genuinely dangerous case — `RAG_CORPUS_PATH`
  is SET but wrong — from a silent skip into a failure.

That second case is the dangerous one because `real_corpus_path()` returns None
for a path that exists but is not a corpus, which is indistinguishable, at the
report level, from not having configured one at all. A developer who typos the
path, points at the wrong repository, or sits on a different revision would see
the whole content suite skip and read it as "nothing to do here".
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from .conftest import PINNED_CORPUS_SHA

_UNSET = (
    "RAG_CORPUS_PATH is not set. This is the CI shape and it is expected: CI "
    "covers the structural tests only, and the corpus contract runs locally via "
    "`make test-rag-corpus`."
)


@pytest.mark.corpus
def test_rag_corpus_path_when_set_points_at_the_pinned_checkout():
    """Set-but-wrong must FAIL. Only unset may skip."""
    raw = os.environ.get("RAG_CORPUS_PATH")
    if not raw:
        pytest.skip(_UNSET)

    path = Path(raw).expanduser()
    assert path.is_dir(), (
        f"RAG_CORPUS_PATH={raw!r} is set but is not a directory. Without this "
        "assertion the entire corpus contract would have skipped green."
    )
    assert (path / "MANIFEST.md").is_file(), (
        f"RAG_CORPUS_PATH={raw!r} is a directory but holds no MANIFEST.md, so it "
        "is not a checkout of consorcio-corpus-legal."
    )

    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert head.returncode == 0, (
        f"RAG_CORPUS_PATH={raw!r} is not a git checkout: {head.stderr.strip()}. "
        "The pin is what makes every count in this suite reproducible."
    )
    assert head.stdout.strip() == PINNED_CORPUS_SHA, (
        f"corpus checkout is at {head.stdout.strip()}, but this suite's "
        f"expectations are pinned to {PINNED_CORPUS_SHA}. Every count assertion "
        "below would be measuring a different corpus."
    )
