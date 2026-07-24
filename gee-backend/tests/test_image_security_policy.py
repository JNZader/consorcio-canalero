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
BACKEND_DAEMON_IMAGE_ID = "sha256:" + ("1" * 64)
BACKEND_REGISTRY_MANIFEST_DIGEST = "sha256:" + ("6" * 64)
BACKEND_PLATFORM_MANIFEST_DIGEST = "sha256:" + ("7" * 64)
BACKEND_CONFIG_DIGEST = "sha256:" + ("8" * 64)
GEO_REF = "local/consorcio-geo-worker:test"
GEO_DAEMON_IMAGE_ID = "sha256:" + ("5" * 64)
GEO_PLATFORM_MANIFEST_DIGEST = "sha256:" + ("9" * 64)
GEO_CONFIG_DIGEST = "sha256:" + ("0" * 64)
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


def _retag_report(report: dict[str, Any], image_ref: str) -> None:
    old_ref = report["ArtifactName"]
    report["ArtifactName"] = image_ref
    report["Metadata"]["Reference"] = image_ref
    report["Metadata"]["RepoTags"] = [
        image_ref if tag == old_ref else tag for tag in report["Metadata"]["RepoTags"]
    ]
    for result in report["Results"]:
        target = result.get("Target")
        if isinstance(target, str) and (target == old_ref or target.startswith(f"{old_ref} ")):
            result["Target"] = image_ref + target[len(old_ref) :]


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
        "count": 1,
    }


def _scanner_metadata() -> dict[str, Any]:
    return {
        "Version": "0.70.0",
        "VulnerabilityDB": {
            "Version": 2,
            "UpdatedAt": "2026-07-22T23:00:00Z",
            "DownloadedAt": "2026-07-22T23:30:00Z",
            "NextUpdate": "2026-07-24T00:00:00Z",
        },
    }


def _provenance(image_ref: str, image_id: str, role: str) -> dict[str, Any]:
    platform_manifest_digest = (
        BACKEND_PLATFORM_MANIFEST_DIGEST if role == "backend" else GEO_PLATFORM_MANIFEST_DIGEST
    )
    config_digest = BACKEND_CONFIG_DIGEST if role == "backend" else GEO_CONFIG_DIGEST
    base_image = BACKEND_BASE if role == "backend" else GEO_BASE
    return {
        "source_revision": SOURCE_REVISION,
        "image_ref": image_ref,
        "image_id": image_id,
        "platform_manifest_digest": platform_manifest_digest,
        "config_digest": config_digest,
        "report_sha256": "sha256:" + ("f" * 64),
        "scanned_at": "2026-07-23T00:00:00Z",
        "platform": "linux/amd64",
        "base_image": base_image,
        "scanner": {
            "name": "trivy",
            "version": "0.70.0",
            "report_schema_version": 2,
            "vulnerability_db": {
                "version": 2,
                "updated_at": "2026-07-22T23:00:00Z",
                "downloaded_at": "2026-07-22T23:30:00Z",
                "next_update": "2026-07-24T00:00:00Z",
            },
        },
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
                    "ghcr.io/jnzader/consorcio-canalero/backend",
                ],
                "baseline_generated_from": _provenance(
                    BACKEND_REF,
                    BACKEND_DAEMON_IMAGE_ID,
                    "backend",
                ),
                "findings": [_finding()],
            },
            "geo-worker": {
                "dockerfile": "gee-backend/Dockerfile.geo",
                "base_image": GEO_BASE,
                "allowed_repositories": [
                    "local/consorcio-geo-worker",
                    "ghcr.io/jnzader/consorcio-canalero/geo-worker",
                ],
                "baseline_generated_from": _provenance(
                    GEO_REF,
                    GEO_DAEMON_IMAGE_ID,
                    "geo-worker",
                ),
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
    expected_id = expected_id or (
        BACKEND_DAEMON_IMAGE_ID if role == "backend" else GEO_DAEMON_IMAGE_ID
    )
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
        scanner_metadata_path = _write_json(
            tmp_path / "trivy-version.json",
            _scanner_metadata(),
        )
        platform_manifest_digest = (
            BACKEND_PLATFORM_MANIFEST_DIGEST if role == "backend" else GEO_PLATFORM_MANIFEST_DIGEST
        )
        config_digest = BACKEND_CONFIG_DIGEST if role == "backend" else GEO_CONFIG_DIGEST
        command_line += [
            "--scanner-metadata",
            str(scanner_metadata_path),
            "--platform-manifest-digest",
            platform_manifest_digest,
            "--image-config-digest",
            config_digest,
            "--output",
            str(tmp_path / "snapshot.json"),
        ]
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


def test_repository_policy_is_active_with_exact_stage2b2_observations() -> None:
    policy = json.loads(REPO_POLICY.read_text(encoding="utf-8"))
    backend = policy["images"]["backend"]
    geo = policy["images"]["geo-worker"]
    backend_provenance = backend["baseline_generated_from"]
    geo_provenance = geo["baseline_generated_from"]

    assert policy["active"] is True
    assert "activation_blocker" not in policy
    assert backend["allowed_repositories"] == [
        "local/consorcio-backend",
        "ghcr.io/jnzader/consorcio-canalero/backend",
    ]
    assert geo["allowed_repositories"] == [
        "local/consorcio-geo-worker",
        "ghcr.io/jnzader/consorcio-canalero/geo-worker",
    ]
    assert len(backend["findings"]) == 30
    assert sum(finding["count"] for finding in backend["findings"]) == 30
    assert {finding["count"] for finding in backend["findings"]} == {1}
    assert {finding["target"] for finding in backend["findings"]} == {"<image> (debian 13.6)"}
    assert sum(finding["severity"] == "HIGH" for finding in backend["findings"]) == 25
    assert sum(finding["severity"] == "CRITICAL" for finding in backend["findings"]) == 5
    assert sum(finding["status"] == "affected" for finding in backend["findings"]) == 27
    assert sum(finding["status"] == "fix_deferred" for finding in backend["findings"]) == 3
    assert all(finding["fixed"] == "" for finding in backend["findings"])
    assert all("layer" not in finding for finding in backend["findings"])
    assert geo["findings"] == []
    assert backend_provenance["report_sha256"] == (
        "sha256:eda0e61b19adcf2978774fbee2d9414f409ea10aa595c7fb0198d30f8716d4a8"
    )
    assert geo_provenance["report_sha256"] == (
        "sha256:21eedc171a92b12f338aa9f714fc15fd701a0f2f35aed3997fa1bf711d09db51"
    )
    assert backend_provenance["source_revision"] == ("96cf15d0f36577c2500d2708dc5c1b899035177f")
    assert geo_provenance["source_revision"] == backend_provenance["source_revision"]
    assert backend_provenance["platform"] == "linux/amd64"
    assert geo_provenance["platform"] == "linux/amd64"
    assert backend_provenance["base_image"] == BACKEND_BASE
    assert geo_provenance["base_image"] == GEO_BASE
    assert backend_provenance["scanner"]["version"] == "0.70.0"
    assert geo_provenance["scanner"]["version"] == "0.70.0"
    assert backend_provenance["scanner"]["vulnerability_db"]["version"] == 2
    assert geo_provenance["scanner"]["vulnerability_db"]["version"] == 2


def test_valid_exact_backend_and_empty_geo_reports_pass(tmp_path: Path) -> None:
    backend = _run(tmp_path / "backend")
    geo = _run(tmp_path / "geo", role="geo-worker")

    assert backend.returncode == 0, backend.stderr
    assert geo.returncode == 0, geo.stderr


@pytest.mark.parametrize("repo_digests", ["absent", None, []])
@pytest.mark.parametrize(
    ("role", "fixture"),
    [
        ("backend", "trivy-backend-one-finding.json"),
        ("geo-worker", "trivy-geo-empty.json"),
    ],
)
def test_loaded_local_reports_do_not_require_registry_repo_digests(
    tmp_path: Path,
    role: str,
    fixture: str,
    repo_digests: str | list[Any] | None,
) -> None:
    report = _load_fixture(fixture)
    if repo_digests == "absent":
        report["Metadata"].pop("RepoDigests")
    else:
        report["Metadata"]["RepoDigests"] = repo_digests

    result = _run(tmp_path, role=role, report=report)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("repo_digests", [False, 0, "", {}])
def test_non_null_non_list_repo_digests_are_rejected(
    tmp_path: Path,
    repo_digests: Any,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["Metadata"]["RepoDigests"] = repo_digests

    _assert_rejected(_run(tmp_path, report=report), "RepoDigests must be a list")


def test_runtime_daemon_image_identity_is_not_statically_bound_to_provenance(
    tmp_path: Path,
) -> None:
    policy = _active_policy()
    policy["images"]["backend"]["baseline_generated_from"]["image_id"] = "sha256:" + ("2" * 64)

    result = _run(tmp_path, policy=policy)

    assert result.returncode == 0, result.stderr


def test_omitted_fixed_version_is_canonicalized_to_empty_string(tmp_path: Path) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["Results"][0]["Vulnerabilities"][0].pop("FixedVersion")

    result = _run(tmp_path, report=report)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("value", [None, 0, False, [], {}])
def test_present_non_string_fixed_version_is_rejected(
    tmp_path: Path,
    value: Any,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["Results"][0]["Vulnerabilities"][0]["FixedVersion"] = value

    _assert_rejected(_run(tmp_path, report=report), "FixedVersion must be a string")


def test_optional_manifest_digest_is_bound_separately_from_daemon_image_identity(
    tmp_path: Path,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    repository = BACKEND_REF.rsplit(":", 1)[0]
    report["Metadata"]["RepoDigests"] = [f"{repository}@{BACKEND_REGISTRY_MANIFEST_DIGEST}"]

    accepted = _run(
        tmp_path / "accepted",
        report=report,
        expected_manifest_digest=BACKEND_REGISTRY_MANIFEST_DIGEST,
    )
    assert accepted.returncode == 0, accepted.stderr

    missing_manifest = copy.deepcopy(report)
    missing_manifest["Metadata"]["RepoDigests"] = []
    _assert_rejected(
        _run(
            tmp_path / "missing-manifest",
            report=missing_manifest,
            expected_manifest_digest=BACKEND_REGISTRY_MANIFEST_DIGEST,
        ),
        "manifest digest",
    )

    daemon_identity_only = copy.deepcopy(report)
    daemon_identity_only["Metadata"]["RepoDigests"] = [f"{repository}@{BACKEND_DAEMON_IMAGE_ID}"]
    _assert_rejected(
        _run(
            tmp_path / "daemon-identity-is-not-manifest",
            report=daemon_identity_only,
            expected_manifest_digest=BACKEND_REGISTRY_MANIFEST_DIGEST,
        ),
        "manifest digest",
    )

    malformed = copy.deepcopy(report)
    malformed["Metadata"]["RepoDigests"] = [42]
    _assert_rejected(
        _run(tmp_path / "malformed-repo-digest", report=malformed),
        "RepoDigests",
    )


@pytest.mark.parametrize("repo_digests", ["absent", None, []])
def test_expected_manifest_digest_rejects_missing_local_repo_digest(
    tmp_path: Path,
    repo_digests: str | list[Any] | None,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    if repo_digests == "absent":
        report["Metadata"].pop("RepoDigests")
    else:
        report["Metadata"]["RepoDigests"] = repo_digests

    _assert_rejected(
        _run(
            tmp_path,
            report=report,
            expected_manifest_digest=BACKEND_REGISTRY_MANIFEST_DIGEST,
        ),
        "manifest digest binding mismatch",
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
            lambda report: report["Results"][0]["Vulnerabilities"][0].pop("Status"),
            "status",
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
    "layer_value",
    [
        "absent",
        None,
        "not-an-object",
        {},
        {"Digest": 42, "DiffID": ["not-a-digest"]},
        {
            "Digest": "sha256:" + ("a" * 64),
            "DiffID": "sha256:" + ("b" * 64),
        },
    ],
)
def test_layer_metadata_is_ignored_for_frozen_debt_identity(
    tmp_path: Path,
    layer_value: Any,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    vulnerability = report["Results"][0]["Vulnerabilities"][0]
    if layer_value == "absent":
        vulnerability.pop("Layer")
    else:
        vulnerability["Layer"] = layer_value

    result = _run(tmp_path, report=report)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "mutate",
    [
        lambda finding: finding.__setitem__("VulnerabilityID", "CVE-2026-99999"),
        lambda finding: finding.__setitem__("PkgID", "libother@1.0.0"),
        lambda finding: finding["PkgIdentifier"].__setitem__(
            "PURL", "pkg:deb/debian/libother@1.0.0?arch=amd64"
        ),
        lambda finding: finding.__setitem__("InstalledVersion", "9.9.9"),
        lambda finding: finding.__setitem__("Severity", "CRITICAL"),
        lambda finding: finding.__setitem__("Status", "fix_deferred"),
        lambda finding: finding.__setitem__("FixedVersion", "1.0.1"),
    ],
)
def test_security_identity_mutations_are_rejected(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], Any],
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    mutate(report["Results"][0]["Vulnerabilities"][0])

    assert _run(tmp_path, report=report).returncode == 1


@pytest.mark.parametrize("mutation", ["remove", "duplicate"])
def test_report_finding_multiplicity_mutations_are_rejected(
    tmp_path: Path,
    mutation: str,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    vulnerabilities = report["Results"][0]["Vulnerabilities"]
    if mutation == "remove":
        vulnerabilities.clear()
    else:
        vulnerabilities.append(copy.deepcopy(vulnerabilities[0]))

    _assert_rejected(_run(tmp_path, report=report), "multiset mismatch")


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


@pytest.mark.parametrize(
    ("report_target", "policy_target"),
    [
        (BACKEND_REF, "<image>"),
        (f"{BACKEND_REF} (debian 13.6)", "<image> (debian 13.6)"),
    ],
)
def test_image_target_normalizes_only_the_artifact_name_and_distro_suffix(
    tmp_path: Path,
    report_target: str,
    policy_target: str,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["Results"][0]["Target"] = report_target
    policy = _active_policy()
    policy["images"]["backend"]["findings"][0]["target"] = policy_target

    result = _run(tmp_path, policy=policy, report=report)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "target",
    [
        f"{BACKEND_REF}-sidecar (debian 13.6)",
        f"{BACKEND_REF}/usr/lib",
        f"{BACKEND_REF} (debian 13.6)/usr/lib",
        "Python",
    ],
)
def test_image_target_normalization_preserves_unrelated_targets(
    tmp_path: Path,
    target: str,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["Results"][0]["Target"] = target
    policy = _active_policy()
    policy["images"]["backend"]["findings"][0]["target"] = target

    result = _run(tmp_path, policy=policy, report=report)

    assert result.returncode == 0, result.stderr


def test_layer_metadata_does_not_change_canonical_snapshot(tmp_path: Path) -> None:
    policy = _active_policy()
    policy["active"] = False
    policy["images"]["backend"]["findings"] = {"unactivated": True}
    original = _load_fixture("trivy-backend-one-finding.json")
    changed = copy.deepcopy(original)
    changed["Results"][0]["Vulnerabilities"][0]["Layer"] = {
        "Digest": "not-a-digest",
        "DiffID": ["not-a-diff-id"],
    }

    without_layer = copy.deepcopy(original)
    without_layer["Results"][0]["Vulnerabilities"][0].pop("Layer")
    first = _run(tmp_path / "first", policy=policy, report=without_layer, command="snapshot")
    second = _run(tmp_path / "second", policy=policy, report=changed, command="snapshot")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_snapshot = json.loads((tmp_path / "first/snapshot.json").read_text(encoding="utf-8"))
    second_snapshot = json.loads((tmp_path / "second/snapshot.json").read_text(encoding="utf-8"))
    assert first_snapshot["findings"] == second_snapshot["findings"]
    assert "layer" not in first_snapshot["findings"][0]


def test_different_image_tags_produce_the_same_canonical_snapshot(
    tmp_path: Path,
) -> None:
    policy = _active_policy()
    policy["active"] = False
    policy["images"]["backend"]["findings"] = {"unactivated": True}
    first_report = _load_fixture("trivy-backend-one-finding.json")
    first_report["Results"][0]["Target"] = f"{BACKEND_REF} (debian 13.6)"
    second_ref = "local/consorcio-backend:other-build"
    second_report = copy.deepcopy(first_report)
    _retag_report(second_report, second_ref)

    first = _run(
        tmp_path / "first",
        policy=policy,
        report=first_report,
        command="snapshot",
    )
    second = _run(
        tmp_path / "second",
        policy=policy,
        report=second_report,
        expected_ref=second_ref,
        command="snapshot",
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_snapshot = json.loads((tmp_path / "first/snapshot.json").read_text(encoding="utf-8"))
    second_snapshot = json.loads((tmp_path / "second/snapshot.json").read_text(encoding="utf-8"))
    assert first_snapshot["findings"] == second_snapshot["findings"]
    assert first_snapshot["findings"][0]["target"] == "<image> (debian 13.6)"


def test_timezone_aware_created_at_is_normalized_to_utc(tmp_path: Path) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["CreatedAt"] = "2026-07-23T03:00:00+03:00"
    policy = _active_policy()
    policy["active"] = False
    policy["images"]["backend"]["findings"] = {"unactivated": True}

    validation = _run(tmp_path / "validate", report=report)
    snapshot = _run(
        tmp_path / "snapshot",
        policy=policy,
        report=report,
        command="snapshot",
    )

    assert validation.returncode == 0, validation.stderr
    assert snapshot.returncode == 0, snapshot.stderr
    normalized = json.loads((tmp_path / "snapshot/snapshot.json").read_text(encoding="utf-8"))
    assert normalized["baseline_generated_from"]["scanned_at"] == ("2026-07-23T00:00:00Z")


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-07-23T00:00:00",
        "2026-07-23 00:00:00Z",
        "not-a-timestamp",
    ],
)
def test_naive_or_malformed_created_at_is_rejected(
    tmp_path: Path,
    created_at: str,
) -> None:
    report = _load_fixture("trivy-backend-one-finding.json")
    report["CreatedAt"] = created_at

    _assert_rejected(_run(tmp_path, report=report), "CreatedAt")


def test_cli_describes_image_id_as_opaque_daemon_identity() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "opaque Docker daemon/Trivy image identity" in result.stdout
    assert "configuration image ID" not in result.stdout


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


def test_scanner_platform_source_image_and_base_bindings_fail_closed(
    tmp_path: Path,
) -> None:
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
            BACKEND_DAEMON_IMAGE_ID,
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
    report["Metadata"]["RepoDigests"] = [f"{repository}@{BACKEND_REGISTRY_MANIFEST_DIGEST}"]
    report["Results"][0]["Vulnerabilities"].append(
        copy.deepcopy(report["Results"][0]["Vulnerabilities"][0])
    )
    result = _run(
        tmp_path,
        policy=policy,
        report=report,
        expected_manifest_digest=BACKEND_REGISTRY_MANIFEST_DIGEST,
        command="snapshot",
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["findings"][0]["count"] == 2
    provenance = snapshot["baseline_generated_from"]
    assert provenance["image_id"] == BACKEND_DAEMON_IMAGE_ID
    assert provenance["manifest_digest"] == BACKEND_REGISTRY_MANIFEST_DIGEST
    assert provenance["platform_manifest_digest"] == BACKEND_PLATFORM_MANIFEST_DIGEST
    assert provenance["config_digest"] == BACKEND_CONFIG_DIGEST
    assert provenance["platform"] == "linux/amd64"
    assert provenance["base_image"] == BACKEND_BASE
    assert provenance["scanner"] == {
        "name": "trivy",
        "version": "0.70.0",
        "report_schema_version": 2,
        "vulnerability_db": {
            "version": 2,
            "updated_at": "2026-07-22T23:00:00Z",
            "downloaded_at": "2026-07-22T23:30:00Z",
            "next_update": "2026-07-24T00:00:00Z",
        },
    }
    report_bytes = (tmp_path / "report.json").read_bytes()
    assert snapshot["baseline_generated_from"]["report_sha256"] == (
        "sha256:" + hashlib.sha256(report_bytes).hexdigest()
    )
