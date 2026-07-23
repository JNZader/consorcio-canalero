"""Fail-closed contracts for frozen production image vulnerability debt."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "gee-backend/scripts/validate_image_security_policy.py"
REPO_POLICY = REPO_ROOT / "gee-backend/security/frozen-image-debt.json"
FIXTURES = Path(__file__).parent / "fixtures/image_security"
SOURCE_REPOSITORY = "https://github.com/JNZader/consorcio-canalero"
SOURCE_REVISION = "a" * 40
BACKEND_REF = "local/consorcio-backend:test"
BACKEND_ID = "sha256:" + ("1" * 64)
BACKEND_MANIFEST_DIGEST = "sha256:" + ("7" * 64)
GEO_REF = "local/consorcio-geo-worker:test"
GEO_ID = "sha256:" + ("5" * 64)
BACKEND_BASE = (
    "python:3.11.15-slim-trixie@"
    "sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93"
)
GEO_BASE = (
    "ghcr.io/osgeo/gdal:ubuntu-small-3.13.1@"
    "sha256:66e200e63c7c2fd2534830caaf5a2dcbd0511680ab12a70f85886cc8330fa469"
)


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _finding() -> dict[str, Any]:
    return {
        "target": "Debian GNU/Linux 13 (trixie)",
        "class": "os-pkgs",
        "type": "debian",
        "cve": "CVE-2026-10001",
        "pkg_id": "libexample@1.0.0",
        "purl": "pkg:deb/debian/libexample@1.0.0?arch=amd64",
        "installed": "1.0.0",
        "severity": "HIGH",
        "status": "affected",
        "fixed": "",
        "layer": {
            "digest": "sha256:" + ("3" * 64),
            "diff_id": "sha256:" + ("4" * 64),
        },
        "count": 1,
    }


def _provenance(image_ref: str, image_id: str) -> dict[str, str]:
    return {
        "source_revision": SOURCE_REVISION,
        "image_ref": image_ref,
        "image_id": image_id,
        "report_sha256": "sha256:" + ("f" * 64),
        "scanned_at": "2026-07-23T00:00:00Z",
    }


def _active_policy() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "active": True,
        "issue": "https://github.com/JNZader/consorcio-canalero/issues/9",
        "owner": "JNZader",
        "renewal_allowed": False,
        "scanner": {
            "name": "trivy",
            "version": "0.70.0",
            "report_schema_version": 2,
        },
        "platform": "linux/amd64",
        "source_repository": SOURCE_REPOSITORY,
        "deadlines": {
            "CRITICAL": "2026-07-29T00:00:00Z",
            "HIGH": "2026-08-05T00:00:00Z",
            "absolute_sunset": "2026-08-21T00:00:00Z",
        },
        "images": {
            "backend": {
                "dockerfile": "gee-backend/Dockerfile",
                "base_image": BACKEND_BASE,
                "allowed_repositories": [
                    "local/consorcio-backend",
                    "ghcr.io/JNZader/consorcio-canalero/backend",
                ],
                "baseline_generated_from": _provenance(BACKEND_REF, BACKEND_ID),
                "findings": [_finding()],
            },
            "geo-worker": {
                "dockerfile": "gee-backend/Dockerfile.geo",
                "base_image": GEO_BASE,
                "allowed_repositories": [
                    "local/consorcio-geo-worker",
                    "ghcr.io/JNZader/consorcio-canalero/geo-worker",
                ],
                "baseline_generated_from": _provenance(GEO_REF, GEO_ID),
                "findings": [],
            },
        },
    }


def _write_dockerfiles(root: Path) -> None:
    backend = root / "gee-backend/Dockerfile"
    geo = root / "gee-backend/Dockerfile.geo"
    backend.parent.mkdir(parents=True, exist_ok=True)
    backend.write_text(
        f"FROM {BACKEND_BASE} AS build\n"
        "FROM build AS development\n"
        f"FROM {BACKEND_BASE} AS production\n",
        encoding="utf-8",
    )
    geo.write_text(f"FROM {GEO_BASE}\n", encoding="utf-8")


def _run(
    tmp_path: Path,
    *,
    role: str = "backend",
    policy: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    expected_ref: str | None = None,
    expected_id: str | None = None,
    expected_manifest_digest: str | None = None,
    now: str = "2026-07-23T00:00:00Z",
    command: str = "validate",
) -> subprocess.CompletedProcess[str]:
    _write_dockerfiles(tmp_path)
    policy_path = _write_json(tmp_path / "policy.json", policy or _active_policy())
    if report is None:
        fixture = "trivy-backend-one-finding.json" if role == "backend" else "trivy-geo-empty.json"
        report = _load_fixture(fixture)
    report_path = _write_json(tmp_path / "report.json", report)
    expected_ref = expected_ref or (BACKEND_REF if role == "backend" else GEO_REF)
    expected_id = expected_id or (BACKEND_ID if role == "backend" else GEO_ID)
    command_line = [
        sys.executable,
        str(SCRIPT),
        command,
        "--policy",
        str(policy_path),
        "--report",
        str(report_path),
        "--image-role",
        role,
        "--expected-image-ref",
        expected_ref,
        "--expected-image-id",
        expected_id,
        "--expected-source-revision",
        SOURCE_REVISION,
        "--expected-source-repository",
        SOURCE_REPOSITORY,
        "--repo-root",
        str(tmp_path),
        "--now",
        now,
    ]
    if expected_manifest_digest is not None:
        command_line += ["--expected-manifest-digest", expected_manifest_digest]
    if command == "snapshot":
        command_line += ["--output", str(tmp_path / "snapshot.json")]
    return subprocess.run(
        command_line,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_rejected(result: subprocess.CompletedProcess[str], fragment: str) -> None:
    assert result.returncode == 1, result.stdout
    assert fragment.lower() in result.stderr.lower()


def test_repository_policy_is_machine_unactivated_until_stage2b() -> None:
    policy = json.loads(REPO_POLICY.read_text(encoding="utf-8"))

    assert policy["active"] is False
    assert not isinstance(policy["images"]["backend"]["findings"], list)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "validate",
            "--policy",
            str(REPO_POLICY),
            "--report",
            str(FIXTURES / "trivy-backend-one-finding.json"),
            "--image-role",
            "backend",
            "--expected-image-ref",
            BACKEND_REF,
            "--expected-image-id",
            BACKEND_ID,
            "--expected-source-revision",
            SOURCE_REVISION,
            "--expected-source-repository",
            SOURCE_REPOSITORY,
            "--repo-root",
            str(REPO_ROOT),
            "--now",
            "2026-07-23T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    _assert_rejected(result, "not active")


def test_valid_exact_backend_and_empty_geo_reports_pass(tmp_path: Path) -> None:
    backend = _run(tmp_path / "backend")
    geo = _run(tmp_path / "geo", role="geo-worker")

    assert backend.returncode == 0, backend.stderr
    assert geo.returncode == 0, geo.stderr


def test_loaded_local_reports_do_not_require_registry_repo_digests(tmp_path: Path) -> None:
    backend_report = _load_fixture("trivy-backend-one-finding.json")
    geo_report = _load_fixture("trivy-geo-empty.json")

    assert backend_report["Metadata"]["RepoDigests"] == []
    assert geo_report["Metadata"]["RepoDigests"] == []
    assert _run(tmp_path / "backend", report=backend_report).returncode == 0
    assert _run(tmp_path / "geo", role="geo-worker", report=geo_report).returncode == 0


def test_optional_manifest_digest_is_bound_separately_from_config_id(
    tmp_path: Path,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    repository = BACKEND_REF.rsplit(":", 1)[0]
    report["Metadata"]["RepoDigests"] = [f"{repository}@{BACKEND_MANIFEST_DIGEST}"]

    accepted = _run(
        tmp_path / "accepted",
        report=report,
        expected_manifest_digest=BACKEND_MANIFEST_DIGEST,
    )
    assert accepted.returncode == 0, accepted.stderr

    missing_manifest = copy.deepcopy(report)
    missing_manifest["Metadata"]["RepoDigests"] = []
    _assert_rejected(
        _run(
            tmp_path / "missing-manifest",
            report=missing_manifest,
            expected_manifest_digest=BACKEND_MANIFEST_DIGEST,
        ),
        "manifest digest",
    )

    config_digest_only = copy.deepcopy(report)
    config_digest_only["Metadata"]["RepoDigests"] = [f"{repository}@{BACKEND_ID}"]
    _assert_rejected(
        _run(
            tmp_path / "config-is-not-manifest",
            report=config_digest_only,
            expected_manifest_digest=BACKEND_MANIFEST_DIGEST,
        ),
        "manifest digest",
    )

    malformed = copy.deepcopy(report)
    malformed["Metadata"]["RepoDigests"] = [42]
    _assert_rejected(
        _run(tmp_path / "malformed-repo-digest", report=malformed),
        "RepoDigests",
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda report: report["Results"][0]["Vulnerabilities"][0]["PkgIdentifier"].__setitem__(
                "PURL", ""
            ),
            "purl",
        ),
        (
            lambda report: report["Results"][0]["Vulnerabilities"][0].pop("Layer"),
            "layer",
        ),
        (lambda report: report.pop("Metadata"), "metadata"),
    ],
)
def test_missing_required_report_metadata_fails(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], Any],
    message: str,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    mutate(report)

    _assert_rejected(_run(tmp_path, report=report), message)


@pytest.mark.parametrize(
    ("field", "value"),
    [("FixedVersion", "1.0.1"), ("Status", "fixed")],
)
def test_fixed_findings_can_never_be_frozen(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["Results"][0]["Vulnerabilities"][0][field] = value

    _assert_rejected(_run(tmp_path, report=report), "fixed")


def test_exact_counter_rejects_new_decreased_changed_and_duplicate_counts(
    tmp_path: Path,
) -> None:
    base_policy = _active_policy()
    base_report = _load_fixture("trivy-backend-one-finding.json")

    new_report = copy.deepcopy(base_report)
    extra = copy.deepcopy(new_report["Results"][0]["Vulnerabilities"][0])
    extra["VulnerabilityID"] = "CVE-2026-10002"
    new_report["Results"][0]["Vulnerabilities"].append(extra)
    _assert_rejected(_run(tmp_path / "new", report=new_report), "unexpected")

    decreased = copy.deepcopy(base_policy)
    decreased["images"]["backend"]["findings"][0]["count"] = 2
    _assert_rejected(_run(tmp_path / "decreased", policy=decreased), "missing")

    changed = copy.deepcopy(base_policy)
    changed["images"]["backend"]["findings"][0]["installed"] = "0.9.0"
    _assert_rejected(_run(tmp_path / "changed", policy=changed), "mismatch")

    duplicate = copy.deepcopy(base_policy)
    duplicate["images"]["backend"]["findings"].append(
        copy.deepcopy(duplicate["images"]["backend"]["findings"][0])
    )
    _assert_rejected(_run(tmp_path / "duplicate", policy=duplicate), "duplicate")


@pytest.mark.parametrize(
    ("mutate_policy", "now", "message"),
    [
        (
            lambda policy: policy["deadlines"].__setitem__("HIGH", "2026-08-06T00:00:00Z"),
            "2026-07-23T00:00:00Z",
            "ceiling",
        ),
        (
            lambda policy: None,
            "2026-08-05T00:00:00Z",
            "expired",
        ),
        (
            lambda policy: None,
            "2026-08-21T00:00:00Z",
            "sunset",
        ),
    ],
)
def test_deadline_ceilings_expiry_and_absolute_sunset_fail(
    tmp_path: Path,
    mutate_policy: Callable[[dict[str, Any]], Any],
    now: str,
    message: str,
) -> None:
    policy = _active_policy()
    mutate_policy(policy)

    _assert_rejected(_run(tmp_path, policy=policy, now=now), message)


def test_scanner_platform_source_image_and_base_bindings_fail_closed(tmp_path: Path) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")

    wrong_scanner = copy.deepcopy(report)
    wrong_scanner["Trivy"]["Version"] = "0.69.0"
    _assert_rejected(_run(tmp_path / "scanner", report=wrong_scanner), "scanner")

    wrong_platform = copy.deepcopy(report)
    wrong_platform["Metadata"]["ImageConfig"]["architecture"] = "arm64"
    _assert_rejected(_run(tmp_path / "platform", report=wrong_platform), "platform")

    wrong_source = copy.deepcopy(report)
    labels = wrong_source["Metadata"]["ImageConfig"]["config"]["Labels"]
    labels["org.opencontainers.image.source"] = "https://example.invalid/repo"
    _assert_rejected(_run(tmp_path / "source", report=wrong_source), "source")

    _assert_rejected(
        _run(tmp_path / "image-ref", expected_ref="local/consorcio-backend:other"),
        "image",
    )
    _assert_rejected(
        _run(tmp_path / "image-id", expected_id="sha256:" + ("9" * 64)),
        "image",
    )

    base_root = tmp_path / "base"
    _write_dockerfiles(base_root)
    (base_root / "gee-backend/Dockerfile").write_text(
        "FROM python:latest AS production\n", encoding="utf-8"
    )
    policy_path = _write_json(base_root / "policy.json", _active_policy())
    report_path = _write_json(base_root / "report.json", report)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "validate",
            "--policy",
            str(policy_path),
            "--report",
            str(report_path),
            "--image-role",
            "backend",
            "--expected-image-ref",
            BACKEND_REF,
            "--expected-image-id",
            BACKEND_ID,
            "--expected-source-revision",
            SOURCE_REVISION,
            "--expected-source-repository",
            SOURCE_REPOSITORY,
            "--repo-root",
            str(base_root),
            "--now",
            "2026-07-23T00:00:00Z",
        ],
        cwd=base_root,
        text=True,
        capture_output=True,
        check=False,
    )
    _assert_rejected(result, "base")


@pytest.mark.parametrize(
    "report",
    [{}, {"SchemaVersion": 2, "Results": []}],
)
def test_malformed_or_empty_untrusted_reports_fail(
    tmp_path: Path,
    report: dict[str, Any],
) -> None:
    _assert_rejected(_run(tmp_path, report=report), "report")


def test_geo_worker_rejects_any_finding(tmp_path: Path) -> None:
    report = _load_fixture("trivy-geo-empty.json")
    result = copy.deepcopy(_load_fixture("trivy-backend-one-finding.json")["Results"][0])
    report["Results"].append(result)

    _assert_rejected(_run(tmp_path, role="geo-worker", report=report), "geo-worker")


def test_snapshot_outputs_sorted_counter_and_report_provenance(tmp_path: Path) -> None:
    policy = _active_policy()
    policy["active"] = False
    policy["images"]["backend"]["findings"] = {"unactivated": True}
    report = _load_fixture("trivy-backend-one-finding.json")
    repository = BACKEND_REF.rsplit(":", 1)[0]
    report["Metadata"]["RepoDigests"] = [f"{repository}@{BACKEND_MANIFEST_DIGEST}"]
    report["Results"][0]["Vulnerabilities"].append(
        copy.deepcopy(report["Results"][0]["Vulnerabilities"][0])
    )
    result = _run(
        tmp_path,
        policy=policy,
        report=report,
        expected_manifest_digest=BACKEND_MANIFEST_DIGEST,
        command="snapshot",
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["findings"][0]["count"] == 2
    assert snapshot["baseline_generated_from"]["image_id"] == BACKEND_ID
    assert snapshot["baseline_generated_from"]["manifest_digest"] == BACKEND_MANIFEST_DIGEST
    report_bytes = (tmp_path / "report.json").read_bytes()
    assert snapshot["baseline_generated_from"]["report_sha256"] == (
        "sha256:" + hashlib.sha256(report_bytes).hexdigest()
    )
