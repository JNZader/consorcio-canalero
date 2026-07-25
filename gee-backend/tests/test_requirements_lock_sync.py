"""Guard: the resolved lockfiles must satisfy the declared manifests.

Builds and CI install from ``requirements.lock`` / ``requirements-dev.lock``,
NOT from the ``requirements*.txt`` manifests. That split creates a silent
drift channel:

* Dependabot's pip ecosystem does not understand plain ``.lock`` files, so its
  bumps land in ``requirements.txt`` and the lock stays behind — a green PR
  that changes nothing about what actually ships.
* ``trivy fs`` does not parse ``requirements.lock`` either (verified: the same
  vulnerable pin is reported from ``requirements.txt`` and skipped from the
  lock), so the manifest-level scan cannot catch a hand-edited lock.
* The security exclusions live in the manifest (``fastapi!=0.137.0,!=0.137.1``,
  ``PyJWT>=2.11.0,<3.0.0``…) and are asserted by the CI contract tests against
  that manifest — nothing tied them to the file that is installed.

These tests close the loop offline: no network, no uv, no resolver. They only
assert that every direct requirement is present in the lock and that its pinned
version satisfies the declared specifier. Regenerate with the commands in the
``requirements.txt`` header when this fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _parse_manifest(path: Path) -> dict[str, Requirement]:
    """Direct requirements declared by a ``requirements*.txt`` manifest."""
    requirements: dict[str, Requirement] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        requirement = Requirement(line)
        requirements[canonicalize_name(requirement.name)] = requirement
    return requirements


def _parse_lock(path: Path) -> dict[str, Version]:
    """Pinned versions in a hash-pinned lockfile (``name==version \\``)."""
    pins: dict[str, Version] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip().rstrip("\\").strip()
        if not line or line.startswith("-") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        # Skip hash continuation lines and any extras/markers noise.
        if not name or name.startswith("--"):
            continue
        pins[canonicalize_name(Requirement(line).name)] = Version(version.split(";")[0].strip())
    return pins


LOCK_PAIRS = [
    pytest.param(["requirements.txt"], "requirements.lock", id="runtime"),
    pytest.param(
        ["requirements.txt", "requirements-dev.txt"],
        "requirements-dev.lock",
        id="runtime+dev",
    ),
]


@pytest.mark.parametrize(("manifests", "lockfile"), LOCK_PAIRS)
def test_lock_covers_every_direct_requirement(manifests: list[str], lockfile: str) -> None:
    pins = _parse_lock(BACKEND_ROOT / lockfile)
    missing = []
    for manifest in manifests:
        for name in _parse_manifest(BACKEND_ROOT / manifest):
            if name not in pins:
                missing.append(f"{name} (declared in {manifest})")
    assert not missing, (
        f"{lockfile} is missing direct requirements: {sorted(missing)}. "
        "Regenerate the lockfiles — see the header of requirements.txt."
    )


@pytest.mark.parametrize(("manifests", "lockfile"), LOCK_PAIRS)
def test_lock_pins_satisfy_declared_specifiers(manifests: list[str], lockfile: str) -> None:
    """A pin outside its declared range means the lock lost a security bound."""
    pins = _parse_lock(BACKEND_ROOT / lockfile)
    violations = []
    for manifest in manifests:
        for name, requirement in _parse_manifest(BACKEND_ROOT / manifest).items():
            pinned = pins.get(name)
            if pinned is None:
                continue
            if not requirement.specifier.contains(pinned, prereleases=True):
                violations.append(f"{name}=={pinned} violates '{requirement}' ({manifest})")
    assert not violations, (
        f"{lockfile} pins violate the declared specifiers: {violations}. "
        "These specifiers carry security exclusions (e.g. fastapi!=0.137.0) — "
        "regenerate the lockfiles instead of editing them by hand."
    )


def test_lockfiles_are_hash_pinned() -> None:
    """``pip install --require-hashes`` must stay possible for both locks."""
    for lockfile in ("requirements.lock", "requirements-dev.lock"):
        content = (BACKEND_ROOT / lockfile).read_text()
        assert "--hash=sha256:" in content, f"{lockfile} lost its hashes"
