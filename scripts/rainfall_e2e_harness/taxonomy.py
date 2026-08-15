"""Failure classification, redaction, and manifest (RMEH-009/012-B).

Relies on ``FailureClass``, ``RunIdentity`` and ``ResourceLease`` from the
safety layer; kept separate so the taxonomy/matrix logic is reviewable without
the safety internals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Mapping

from scripts.rainfall_e2e_harness.safety import (
    FailureClass,
    ResourceLease,
    RunIdentity,
)


def classify_request_failure(*, pre_click_integrity_ok: bool, click_occurred: bool) -> FailureClass:
    """Exclusive: pre-click camera/projection/occlusion/tile failure is BROWSER
    integrity; a passed integrity gate + a single real click that then fails on
    request/identity/continuity is PRODUCT assertion."""
    if not pre_click_integrity_ok:
        return FailureClass.BROWSER_INTEGRITY_FAILURE
    if not click_occurred:
        return FailureClass.BROWSER_INTEGRITY_FAILURE
    return FailureClass.PRODUCT_ASSERTION_FAILURE


_SECRET_KEY = re.compile(r"(?i)(password|secret|token|nonce|api_?key)")
_KV_SECRET = re.compile(r"(?i)(\w*(?:password|secret|token|nonce|api_?key)\w*)=\S+")
_BEARER = re.compile(r"(?i)Authorization:\s*Bearer\s+\S+")
_COOKIE = re.compile(r"(?i)Cookie:\s*[^\s\"]+")


def redact_text(text: str) -> str:
    text = _BEARER.sub("Authorization: Bearer ***", text)
    text = _COOKIE.sub("Cookie: ***", text)
    text = _KV_SECRET.sub(lambda m: f"{m.group(1)}=***", text)
    return text


def redact_command(command: list[str], env: Mapping[str, str] | None = None) -> dict[str, object]:
    redacted_env = {
        key: ("***" if _SECRET_KEY.search(key) else value) for key, value in (env or {}).items()
    }
    return {"command": list(command), "env": redacted_env}


@dataclass
class SceneManifest:
    identity: RunIdentity
    lease: ResourceLease
    repo_sha: str = ""
    evidence_sha256: str = ""
    failure_class: FailureClass = FailureClass.PASSED
    counts: Mapping[str, int] = field(default_factory=dict)
    selection_records: list[object] = field(default_factory=list)
    cleanup_result: str = ""
    diagnostics: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.identity.run_id,
                "lease_id": self.lease.lease_id,
                "compose_project": self.lease.project_name,
                "repo_sha": self.repo_sha,
                "evidence_sha256": self.evidence_sha256,
                "failure_class": self.failure_class.value,
                "counts": dict(self.counts),
                "selection_records": list(self.selection_records),
                "cleanup_result": self.cleanup_result,
                "diagnostics": self.diagnostics,
            },
            sort_keys=True,
        )


def manifest_failure(
    *,
    identity: RunIdentity,
    lease: ResourceLease,
    failure_class: FailureClass,
    diagnostics: str,
) -> SceneManifest:
    return SceneManifest(
        identity=identity, lease=lease, failure_class=failure_class, diagnostics=diagnostics
    )


def homepage_browse_failure(
    *, identity: RunIdentity, lease: ResourceLease, diagnostics: str
) -> SceneManifest:
    return SceneManifest(
        identity=identity,
        lease=lease,
        failure_class=FailureClass.BROWSER_INTEGRITY_FAILURE,
        diagnostics=diagnostics,
    )
