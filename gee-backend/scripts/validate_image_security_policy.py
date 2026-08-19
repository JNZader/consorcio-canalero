#!/usr/bin/env python3
"""Validate exact, temporary image-vulnerability debt against raw Trivy JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ISSUE = "https://github.com/JNZader/consorcio-canalero/issues/9"
OWNER = "JNZader"
SOURCE_REPOSITORY = "https://github.com/JNZader/consorcio-canalero"
TRIVY_VERSION = "0.70.0"
TRIVY_REPORT_SCHEMA = 2
PLATFORM = "linux/amd64"
# Prorrogas al sunset absoluto — registro consolidado.
#
# Prorroga CRITICAL 2026-07-30 y prorroga HIGH 2026-08-04. El registro
# anterior nombraba solo 2 CVE CRITICAL; la deuda congelada real son 18
# filas (13 HIGH + 5 CRITICAL) sobre 13 CVE distintos, y AMBOS techos se
# corren al mismo sunset absoluto ya existente. Re-evaluacion completa
# 2026-08-04 (build fresco --no-cache + Trivy 0.70.0 + Docker Hub API +
# tracker de seguridad de Debian): las 24 filas persisten identicas, NINGUNA
# tiene FixedVersion, el digest pineado de python:3.11.15-slim-trixie sigue
# siendo el corriente (no existe 3.11.16+) y el apt de la base no ofrece
# candidatos nuevos.
#
# Evidencia del tracker de Debian — los 13 CVE estan "vulnerable" en trixie
# sin version arreglada disponible:
#   HIGH
#     CVE-2026-53615  util-linux (9 filas)  RESUELTO via trixie-security
#                                           (2.41.5-0+deb13u1): las 9 filas se
#                                           quitaron del baseline por el hotfix
#                                           que hace --only-upgrade de esos 9
#                                           paquetes en el stage de produccion.
#     CVE-2026-14456  openssl/libssl3t64/   [trixie] sin version arreglada;
#                    openssl-provider-legacy (3 filas) alta recien revelada por
#                                           la DB v2 del mismo dia en el re-scan
#                                           CI 2026-08-18 (Trivy 0.70.0); se
#                                           congela como fix_deferred con
#                                           snapshot honesto (PR #193).
#     CVE-2025-69720  ncurses (4 filas)     [trixie] no-dsa (minor issue)
#     CVE-2026-48962  perl                  fixed solo en unstable 5.40.1-8
#     CVE-2026-57432  perl                  fixed solo en unstable 5.40.1-8
#     CVE-2026-42497  perl                  [trixie] postponed (minor issue)
#     CVE-2026-9538   perl                  [trixie] postponed (minor issue)
#     CVE-2026-41992  gzip                  [trixie] no-dsa (minor issue)
#     CVE-2026-54369  acl                   [trixie] no-dsa (llega por point
#                                           release, no backport individual)
#   CRITICAL
#     CVE-2026-13221  perl                  unstable unfixed, bug #1142037
#     CVE-2026-42496  perl                  [trixie] postponed (minor issue)
#     CVE-2026-57433  perl                  fixed solo en unstable 5.40.1-8
#     CVE-2026-8376   perl                  [trixie] no-dsa (point release)
#     CVE-2026-6653   libxml2               [trixie] no-dsa (minor issue).
#                                           libxml2 NO viene de la imagen base:
#                                           entra por libosmesa6 -> libllvm19,
#                                           que instala nuestro Dockerfile para
#                                           el render headless VTK/PyVista.
#
# Concentracion (baseline 2026-08-18, 18 filas): perl 8 + ncurses 4 +
# openssl 3 (CVE-2026-14456) = 15 de 18; util-linux 0% (resuelto en stage prod).
# perl-base es dependencia esencial de dpkg y util-linux/ncurses son sistema
# base: nada de eso es removible, y la app no usa perl. La palanca externa
# restante es un point release de Debian (13.7) que podria bajar hasta 5 HIGH
# y 1 CRITICAL (perl 5.40.1-8 + acl); hay que vigilarlo antes del sunset.
#
# El sunset absoluto 2026-08-21 fuerza la re-revision total: ``_enforce_time``
# evalua el sunset ANTES que los deadlines por severidad, asi que ese dia la
# politica falla aunque los techos por severidad sigan vigentes; y el chequeo
# de techos rechaza cualquier deadline del JSON mayor al sunset hard-codeado.
# HONESTIDAD (R1-001): ese sunset es una CONSTANTE de este archivo, no un
# mecanismo — moverla es una edicion de una linea, como lo fueron las dos
# prorrogas registradas arriba. Lo que la vuelve costosa es el test que la
# PINEA (``test_deadline_ceilings_are_the_documented_dates``): extenderla exige
# tocar codigo Y test en un commit revisado, con una justificacion nueva en
# este bloque. Ese es el contrato real; "imposible de extender" no existe.
DEADLINE_CEILINGS = {
    "CRITICAL": "2026-08-21T00:00:00Z",
    "HIGH": "2026-08-21T00:00:00Z",
    "absolute_sunset": "2026-08-21T00:00:00Z",
}
ROLE_BINDINGS = {
    "backend": {
        "dockerfile": "gee-backend/Dockerfile",
        "base_image": (
            "python:3.11.15-slim-trixie@"
            "sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93"
        ),
        "allowed_repositories": [
            "local/consorcio-backend",
            "ghcr.io/jnzader/consorcio-canalero/backend",
        ],
    },
    "geo-worker": {
        "dockerfile": "gee-backend/Dockerfile.geo",
        "base_image": (
            "ghcr.io/osgeo/gdal:ubuntu-small-3.13.1@"
            "sha256:66e200e63c7c2fd2534830caaf5a2dcbd0511680ab12a70f85886cc8330fa469"
        ),
        "allowed_repositories": [
            "local/consorcio-geo-worker",
            "ghcr.io/jnzader/consorcio-canalero/geo-worker",
        ],
    },
}
FINDING_FIELDS = (
    "target",
    "class",
    "type",
    "cve",
    "pkg_id",
    "purl",
    "installed",
    "severity",
    "status",
    "fixed",
)
POLICY_FINDING_FIELDS = {
    "target",
    "class",
    "type",
    "cve",
    "pkg_id",
    "purl",
    "installed",
    "severity",
    "status",
    "fixed",
    "count",
}
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
RFC3339_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T"
    r"(?P<time>\d{2}:\d{2}:\d{2})"
    r"(?P<fraction>\.\d+)?"
    r"(?P<zone>Z|[+-]\d{2}:\d{2})$"
)
CANONICAL_IMAGE_TARGET = "<image>"
FindingKey = tuple[str, ...]


class PolicyError(ValueError):
    """A fail-closed policy or report validation error."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PolicyError(f"{label} must be a list")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{label} must be a nonempty string")
    return value


def _digest(value: Any, label: str) -> str:
    digest = _string(value, label)
    if SHA256_RE.fullmatch(digest) is None:
        raise PolicyError(f"{label} must be a lowercase sha256 digest")
    return digest


def _repository_digest(value: Any, label: str) -> str:
    reference = _string(value, label)
    repository, separator, digest = reference.rpartition("@")
    if not separator or not repository:
        raise PolicyError(f"{label} must be a repository@sha256 digest reference")
    _digest(digest, f"{label} digest")
    return reference


def _rfc3339(value: Any, label: str) -> tuple[datetime, str]:
    raw = _string(value, label)
    match = RFC3339_RE.fullmatch(raw)
    if match is None:
        raise PolicyError(f"{label} must be a timezone-aware RFC3339 timestamp")
    zone = "+00:00" if match.group("zone") == "Z" else match.group("zone")
    fraction = match.group("fraction") or ""
    try:
        parsed = datetime.fromisoformat(
            f"{match.group('date')}T{match.group('time')}{fraction}{zone}"
        )
    except ValueError as exc:
        raise PolicyError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PolicyError(f"{label} must include an explicit timezone")
    utc = parsed.astimezone(timezone.utc)
    normalized = f"{utc:%Y-%m-%dT%H:%M:%S}{fraction}Z"
    return utc, normalized


def _timestamp(value: Any, label: str) -> datetime:
    return _rfc3339(value, label)[0]


def _normalized_timestamp(value: Any, label: str) -> str:
    return _rfc3339(value, label)[1]


def _repository(image_ref: str) -> str:
    without_digest = image_ref.split("@", 1)[0]
    last_slash = without_digest.rfind("/")
    last_colon = without_digest.rfind(":")
    if last_colon > last_slash:
        return without_digest[:last_colon]
    return without_digest


def _normalize_target(target: str, artifact_name: str) -> str:
    if target == artifact_name:
        return CANONICAL_IMAGE_TARGET
    if not target.startswith(artifact_name):
        return target
    suffix = target[len(artifact_name) :]
    if re.fullmatch(r" \([^()\r\n]+\)", suffix) is None:
        return target
    return CANONICAL_IMAGE_TARGET + suffix


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PolicyError(f"{label} cannot be read: {exc}") from exc
    if not raw.strip():
        raise PolicyError(f"{label} is empty and untrusted")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PolicyError(f"{label} is malformed JSON: {exc}") from exc
    return _object(value, label), raw


def _external_dockerfile_bases(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise PolicyError(f"base binding Dockerfile cannot be read: {exc}") from exc

    aliases: set[str] = set()
    bases: list[str] = []
    for line in lines:
        match = re.match(r"^\s*FROM\s+(?P<body>.+?)\s*$", line, flags=re.IGNORECASE)
        if match is None:
            continue
        parts = match.group("body").split()
        while parts and parts[0].startswith("--"):
            parts.pop(0)
        if not parts:
            raise PolicyError(f"base binding has malformed FROM in {path}")
        source = parts[0]
        if source not in aliases:
            bases.append(source)
        if len(parts) >= 3 and parts[-2].lower() == "as":
            aliases.add(parts[-1])

    if not bases:
        raise PolicyError(f"base binding found no external FROM in {path}")
    return bases


def _validate_static_policy(
    policy: dict[str, Any],
    role: str,
    repo_root: Path,
    *,
    require_active: bool,
) -> dict[str, Any]:
    if policy.get("schema_version") != SCHEMA_VERSION:
        raise PolicyError(f"policy schema_version must be {SCHEMA_VERSION}")
    if not isinstance(policy.get("active"), bool):
        raise PolicyError("policy active flag must be boolean")
    if require_active and policy["active"] is not True:
        raise PolicyError("policy is not active; Stage2B baseline activation is required")
    if policy.get("issue") != ISSUE:
        raise PolicyError("policy issue binding mismatch")
    if policy.get("owner") != OWNER:
        raise PolicyError("policy owner binding mismatch")
    if policy.get("renewal_allowed") is not False:
        raise PolicyError("policy renewal is forbidden")

    scanner = _object(policy.get("scanner"), "policy scanner")
    if scanner != {
        "name": "trivy",
        "version": TRIVY_VERSION,
        "report_schema_version": TRIVY_REPORT_SCHEMA,
    }:
        raise PolicyError("policy scanner binding mismatch")
    if policy.get("platform") != PLATFORM:
        raise PolicyError("policy platform binding mismatch")
    if policy.get("source_repository") != SOURCE_REPOSITORY:
        raise PolicyError("policy source binding mismatch")

    deadlines = _object(policy.get("deadlines"), "policy deadlines")
    for name, ceiling_raw in DEADLINE_CEILINGS.items():
        deadline = _timestamp(deadlines.get(name), f"policy deadline {name}")
        ceiling = _timestamp(ceiling_raw, f"hard-coded deadline ceiling {name}")
        if deadline > ceiling:
            raise PolicyError(f"policy deadline {name} exceeds hard-coded ceiling")

    images = _object(policy.get("images"), "policy images")
    if set(images) != set(ROLE_BINDINGS):
        raise PolicyError("policy images must contain only backend and geo-worker")
    image = _object(images.get(role), f"policy image {role}")
    expected = ROLE_BINDINGS[role]
    for field in ("dockerfile", "base_image", "allowed_repositories"):
        if image.get(field) != expected[field]:
            raise PolicyError(f"policy {role} {field} binding mismatch")

    dockerfile = repo_root / expected["dockerfile"]
    bases = _external_dockerfile_bases(dockerfile)
    if any(base != expected["base_image"] for base in bases):
        raise PolicyError(
            f"base binding mismatch for {role}: expected only {expected['base_image']}, got {bases}"
        )

    if require_active:
        for image_role in ROLE_BINDINGS:
            active_image = _object(images.get(image_role), f"policy image {image_role}")
            _validate_activation_provenance(active_image, image_role)
            _policy_counter(active_image, image_role)
    return image


def _validate_activation_provenance(image: dict[str, Any], role: str) -> None:
    provenance = _object(
        image.get("baseline_generated_from"),
        f"policy {role} baseline_generated_from",
    )
    required_fields = {
        "source_revision",
        "image_ref",
        "image_id",
        "platform_manifest_digest",
        "config_digest",
        "report_sha256",
        "scanned_at",
        "platform",
        "base_image",
        "scanner",
    }
    allowed_fields = required_fields | {"manifest_digest"}
    missing = sorted(required_fields - set(provenance))
    extra = sorted(set(provenance) - allowed_fields)
    if missing or extra:
        raise PolicyError(
            f"policy {role} provenance fields mismatch; missing={missing}, extra={extra}"
        )

    revision = _string(provenance.get("source_revision"), f"policy {role} source_revision")
    if REVISION_RE.fullmatch(revision) is None:
        raise PolicyError(f"policy {role} source_revision must be a 40-character git SHA")
    image_ref = _string(provenance.get("image_ref"), f"policy {role} image_ref")
    if _repository(image_ref) not in ROLE_BINDINGS[role]["allowed_repositories"]:
        raise PolicyError(f"policy {role} image provenance repository is not allowed")
    _digest(provenance.get("image_id"), f"policy {role} observed daemon image identity")
    _digest(
        provenance.get("platform_manifest_digest"),
        f"policy {role} platform manifest digest",
    )
    _digest(provenance.get("config_digest"), f"policy {role} config digest")
    if "manifest_digest" in provenance:
        _digest(provenance.get("manifest_digest"), f"policy {role} manifest digest")
    _digest(provenance.get("report_sha256"), f"policy {role} report_sha256")
    scanned_at = _timestamp(provenance.get("scanned_at"), f"policy {role} scanned_at")
    if provenance.get("platform") != PLATFORM:
        raise PolicyError(f"policy {role} provenance platform binding mismatch")
    if provenance.get("base_image") != ROLE_BINDINGS[role]["base_image"]:
        raise PolicyError(f"policy {role} provenance base image binding mismatch")

    scanner = _object(provenance.get("scanner"), f"policy {role} provenance scanner")
    if set(scanner) != {"name", "version", "report_schema_version", "vulnerability_db"}:
        raise PolicyError(f"policy {role} provenance scanner fields mismatch")
    if scanner.get("name") != "trivy" or scanner.get("version") != TRIVY_VERSION:
        raise PolicyError(f"policy {role} provenance scanner binding mismatch")
    if scanner.get("report_schema_version") != TRIVY_REPORT_SCHEMA:
        raise PolicyError(f"policy {role} provenance report schema mismatch")
    database = _object(
        scanner.get("vulnerability_db"),
        f"policy {role} provenance vulnerability DB",
    )
    if set(database) != {"version", "updated_at", "downloaded_at", "next_update"}:
        raise PolicyError(f"policy {role} vulnerability DB fields mismatch")
    database_version = database.get("version")
    if isinstance(database_version, bool) or not isinstance(database_version, int):
        raise PolicyError(f"policy {role} vulnerability DB version must be an integer")
    if database_version < 1:
        raise PolicyError(f"policy {role} vulnerability DB version must be positive")
    updated_at = _timestamp(database.get("updated_at"), f"policy {role} DB updated_at")
    downloaded_at = _timestamp(
        database.get("downloaded_at"),
        f"policy {role} DB downloaded_at",
    )
    next_update = _timestamp(database.get("next_update"), f"policy {role} DB next_update")
    if not updated_at <= downloaded_at <= scanned_at < next_update:
        raise PolicyError(f"policy {role} vulnerability DB was not fresh at scan time")


def _snapshot_scanner_provenance(
    metadata: dict[str, Any],
    *,
    scanned_at: datetime,
) -> dict[str, Any]:
    if set(metadata) != {"Version", "VulnerabilityDB"}:
        raise PolicyError("scanner metadata fields mismatch")
    if metadata.get("Version") != TRIVY_VERSION:
        raise PolicyError("scanner metadata version mismatch")
    database = _object(metadata.get("VulnerabilityDB"), "scanner vulnerability DB metadata")
    if set(database) != {"Version", "UpdatedAt", "DownloadedAt", "NextUpdate"}:
        raise PolicyError("scanner vulnerability DB metadata fields mismatch")
    database_version = database.get("Version")
    if isinstance(database_version, bool) or not isinstance(database_version, int):
        raise PolicyError("scanner vulnerability DB version must be an integer")
    if database_version < 1:
        raise PolicyError("scanner vulnerability DB version must be positive")
    updated_at = _timestamp(database.get("UpdatedAt"), "scanner DB UpdatedAt")
    downloaded_at = _timestamp(database.get("DownloadedAt"), "scanner DB DownloadedAt")
    next_update = _timestamp(database.get("NextUpdate"), "scanner DB NextUpdate")
    if not updated_at <= downloaded_at <= scanned_at < next_update:
        raise PolicyError("scanner vulnerability DB was not fresh at scan time")
    return {
        "name": "trivy",
        "version": TRIVY_VERSION,
        "report_schema_version": TRIVY_REPORT_SCHEMA,
        "vulnerability_db": {
            "version": database_version,
            "updated_at": _normalized_timestamp(database["UpdatedAt"], "scanner DB UpdatedAt"),
            "downloaded_at": _normalized_timestamp(
                database["DownloadedAt"],
                "scanner DB DownloadedAt",
            ),
            "next_update": _normalized_timestamp(
                database["NextUpdate"],
                "scanner DB NextUpdate",
            ),
        },
    }


def _report_counter(
    report: dict[str, Any],
    *,
    expected_image_ref: str,
    expected_image_id: str,
    expected_manifest_digest: str | None,
    expected_source_revision: str,
    expected_source_repository: str,
    role: str,
) -> Counter[FindingKey]:
    if report.get("SchemaVersion") != TRIVY_REPORT_SCHEMA:
        raise PolicyError("report schema mismatch")
    if report.get("ArtifactType") != "container_image":
        raise PolicyError("report is not a container image report")
    for field in ("CreatedAt", "ArtifactID", "ReportID"):
        _string(report.get(field), f"report {field}")
    _timestamp(report["CreatedAt"], "report CreatedAt")
    artifact_name = _string(report.get("ArtifactName"), "report ArtifactName")

    scanner = _object(report.get("Trivy"), "report scanner metadata")
    if scanner.get("Version") != TRIVY_VERSION:
        raise PolicyError("report scanner version mismatch")

    metadata = _object(report.get("Metadata"), "report metadata")
    expected_image_id = _digest(expected_image_id, "expected daemon image identity")
    if metadata.get("ImageID") != expected_image_id:
        raise PolicyError("report daemon image identity binding mismatch")
    if artifact_name != expected_image_ref:
        raise PolicyError("report image reference binding mismatch")
    if metadata.get("Reference") != expected_image_ref:
        raise PolicyError("report metadata image reference binding mismatch")

    repository = _repository(expected_image_ref)
    if repository not in ROLE_BINDINGS[role]["allowed_repositories"]:
        raise PolicyError("expected image repository is not allowed by policy")
    repo_tags = _list(metadata.get("RepoTags"), "report RepoTags")
    if expected_image_ref not in repo_tags:
        raise PolicyError("report image tag binding mismatch")
    repo_digests_value = metadata.get("RepoDigests")
    if repo_digests_value is None:
        repo_digests_value = []
    repo_digests = [
        _repository_digest(value, f"report RepoDigests[{index}]")
        for index, value in enumerate(_list(repo_digests_value, "report RepoDigests"))
    ]
    if expected_manifest_digest is not None:
        manifest_digest = _digest(
            expected_manifest_digest,
            "expected manifest digest",
        )
        if f"{repository}@{manifest_digest}" not in repo_digests:
            raise PolicyError("report manifest digest binding mismatch")

    if expected_source_repository != SOURCE_REPOSITORY:
        raise PolicyError("expected source repository does not match hard-coded source")
    if REVISION_RE.fullmatch(expected_source_revision) is None:
        raise PolicyError("expected source revision must be a 40-character git SHA")

    image_config = _object(metadata.get("ImageConfig"), "report image config metadata")
    platform = f"{image_config.get('os')}/{image_config.get('architecture')}"
    if platform != PLATFORM:
        raise PolicyError(f"report platform binding mismatch: {platform}")
    config = _object(image_config.get("config"), "report image config")
    labels = _object(config.get("Labels"), "report OCI labels")
    if labels.get("org.opencontainers.image.source") != expected_source_repository:
        raise PolicyError("report source repository label mismatch")
    if labels.get("org.opencontainers.image.revision") != expected_source_revision:
        raise PolicyError("report source revision label mismatch")

    if report.get("ExperimentalModifiedFindings"):
        raise PolicyError("report contains suppressed or modified findings")
    results = _list(report.get("Results"), "report Results")
    if not results:
        raise PolicyError("report Results is empty and untrusted")

    findings: Counter[FindingKey] = Counter()
    for result_index, raw_result in enumerate(results):
        result = _object(raw_result, f"report Results[{result_index}]")
        target = _normalize_target(
            _string(result.get("Target"), f"report Results[{result_index}].Target"),
            artifact_name,
        )
        finding_class = _string(
            result.get("Class"),
            f"report Results[{result_index}].Class",
        )
        finding_type = _string(result.get("Type"), f"report Results[{result_index}].Type")
        for unsupported in ("Misconfigurations", "Secrets", "Licenses"):
            if result.get(unsupported):
                raise PolicyError(f"report contains unexpected {unsupported}")

        vulnerabilities = result.get("Vulnerabilities", [])
        if vulnerabilities is None:
            vulnerabilities = []
        vulnerabilities = _list(
            vulnerabilities,
            f"report Results[{result_index}].Vulnerabilities",
        )
        for vulnerability_index, raw_vulnerability in enumerate(vulnerabilities):
            label = f"report vulnerability {result_index}:{vulnerability_index}"
            vulnerability = _object(raw_vulnerability, label)
            purl = _string(
                _object(vulnerability.get("PkgIdentifier"), f"{label} PkgIdentifier").get("PURL"),
                f"{label} PURL",
            )
            if "FixedVersion" not in vulnerability:
                fixed = ""
            else:
                fixed = vulnerability["FixedVersion"]
                if not isinstance(fixed, str):
                    raise PolicyError(f"{label} FixedVersion must be a string")
            status = _string(vulnerability.get("Status"), f"{label} status")
            if fixed.strip() or status.lower() == "fixed":
                raise PolicyError(f"{label} has a fixed version or fixed status")
            severity = _string(vulnerability.get("Severity"), f"{label} severity").upper()
            if severity not in {"CRITICAL", "HIGH"}:
                raise PolicyError(f"{label} has unsupported severity {severity}")

            key = (
                target,
                finding_class,
                finding_type,
                _string(vulnerability.get("VulnerabilityID"), f"{label} CVE"),
                _string(vulnerability.get("PkgID"), f"{label} PkgID"),
                purl,
                _string(vulnerability.get("InstalledVersion"), f"{label} installed"),
                severity,
                status,
                fixed,
            )
            findings[key] += 1
    return findings


def _entry_key(entry: dict[str, Any], label: str) -> FindingKey:
    if set(entry) != POLICY_FINDING_FIELDS:
        missing = sorted(POLICY_FINDING_FIELDS - set(entry))
        extra = sorted(set(entry) - POLICY_FINDING_FIELDS)
        raise PolicyError(f"{label} fields mismatch; missing={missing}, extra={extra}")
    fixed = entry.get("fixed")
    if not isinstance(fixed, str):
        raise PolicyError(f"{label} fixed must be a string")
    status = _string(entry.get("status"), f"{label} status")
    if fixed.strip() or status.lower() == "fixed":
        raise PolicyError(f"{label} cannot freeze a fixed finding")
    severity = _string(entry.get("severity"), f"{label} severity").upper()
    if severity not in {"CRITICAL", "HIGH"}:
        raise PolicyError(f"{label} has unsupported severity")
    return (
        _string(entry.get("target"), f"{label} target"),
        _string(entry.get("class"), f"{label} class"),
        _string(entry.get("type"), f"{label} type"),
        _string(entry.get("cve"), f"{label} CVE"),
        _string(entry.get("pkg_id"), f"{label} PkgID"),
        _string(entry.get("purl"), f"{label} PURL"),
        _string(entry.get("installed"), f"{label} installed"),
        severity,
        status,
        fixed,
    )


def _policy_counter(image: dict[str, Any], role: str) -> Counter[FindingKey]:
    entries = _list(image.get("findings"), f"policy {role} findings")
    counter: Counter[FindingKey] = Counter()
    for index, raw_entry in enumerate(entries):
        label = f"policy {role} finding[{index}]"
        entry = _object(raw_entry, label)
        key = _entry_key(entry, label)
        if key in counter:
            raise PolicyError(f"policy {role} has duplicate finding rows")
        count = entry.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise PolicyError(f"{label} count must be a positive integer")
        counter[key] = count
    if role == "geo-worker" and counter:
        raise PolicyError("geo-worker policy must have an empty finding set")
    return counter


def _format_counter(counter: Counter[FindingKey]) -> str:
    samples = []
    for key, count in sorted(counter.items()):
        values = dict(zip(FINDING_FIELDS, key, strict=True))
        samples.append(f"{values['cve']}:{values['pkg_id']}:{count}")
    return ", ".join(samples[:10])


def _counter_entries(counter: Counter[FindingKey]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key, count in sorted(counter.items()):
        values = dict(zip(FINDING_FIELDS, key, strict=True))
        entries.append(
            {
                "target": values["target"],
                "class": values["class"],
                "type": values["type"],
                "cve": values["cve"],
                "pkg_id": values["pkg_id"],
                "purl": values["purl"],
                "installed": values["installed"],
                "severity": values["severity"],
                "status": values["status"],
                "fixed": values["fixed"],
                "count": count,
            }
        )
    return entries


def _enforce_time(
    policy: dict[str, Any],
    expected: Counter[FindingKey],
    now: datetime,
) -> None:
    deadlines = _object(policy["deadlines"], "policy deadlines")
    sunset = _timestamp(deadlines["absolute_sunset"], "policy absolute sunset")
    if now >= sunset:
        raise PolicyError("policy absolute sunset has expired")
    for severity in ("CRITICAL", "HIGH"):
        if not any(key[7] == severity for key in expected):
            continue
        expiry = _timestamp(deadlines[severity], f"policy {severity} deadline")
        if now >= expiry:
            raise PolicyError(f"policy {severity} finding deadline has expired")


def validate(
    *,
    policy: dict[str, Any],
    report: dict[str, Any],
    role: str,
    repo_root: Path,
    expected_image_ref: str,
    expected_image_id: str,
    expected_source_revision: str,
    expected_source_repository: str,
    now: datetime,
    expected_manifest_digest: str | None = None,
) -> int:
    image = _validate_static_policy(policy, role, repo_root, require_active=True)
    actual = _report_counter(
        report,
        expected_image_ref=expected_image_ref,
        expected_image_id=expected_image_id,
        expected_manifest_digest=expected_manifest_digest,
        expected_source_revision=expected_source_revision,
        expected_source_repository=expected_source_repository,
        role=role,
    )
    expected = _policy_counter(image, role)
    _enforce_time(policy, expected, now)
    if role == "geo-worker" and actual:
        raise PolicyError("geo-worker report must have an empty finding set")

    unexpected = actual - expected
    missing = expected - actual
    if unexpected or missing:
        raise PolicyError(
            "finding multiset mismatch; "
            f"unexpected=[{_format_counter(unexpected)}]; "
            f"missing=[{_format_counter(missing)}]"
        )
    return sum(actual.values())


def snapshot(
    *,
    policy: dict[str, Any],
    report: dict[str, Any],
    report_raw: bytes,
    role: str,
    repo_root: Path,
    expected_image_ref: str,
    expected_image_id: str,
    expected_source_revision: str,
    expected_source_repository: str,
    scanner_metadata: dict[str, Any],
    platform_manifest_digest: str,
    image_config_digest: str,
    expected_manifest_digest: str | None = None,
) -> dict[str, Any]:
    _validate_static_policy(policy, role, repo_root, require_active=False)
    actual = _report_counter(
        report,
        expected_image_ref=expected_image_ref,
        expected_image_id=expected_image_id,
        expected_manifest_digest=expected_manifest_digest,
        expected_source_revision=expected_source_revision,
        expected_source_repository=expected_source_repository,
        role=role,
    )
    if role == "geo-worker" and actual:
        raise PolicyError("geo-worker report must have an empty finding set")
    scanned_at = _timestamp(report["CreatedAt"], "report CreatedAt")
    provenance = {
        "source_revision": expected_source_revision,
        "image_ref": expected_image_ref,
        "image_id": _digest(expected_image_id, "expected daemon image identity"),
        "platform_manifest_digest": _digest(
            platform_manifest_digest,
            "observed platform manifest digest",
        ),
        "config_digest": _digest(image_config_digest, "observed image config digest"),
        "report_sha256": "sha256:" + hashlib.sha256(report_raw).hexdigest(),
        "scanned_at": _normalized_timestamp(report["CreatedAt"], "report CreatedAt"),
        "platform": PLATFORM,
        "base_image": ROLE_BINDINGS[role]["base_image"],
        "scanner": _snapshot_scanner_provenance(
            scanner_metadata,
            scanned_at=scanned_at,
        ),
    }
    if expected_manifest_digest is not None:
        provenance["manifest_digest"] = expected_manifest_digest
    return {
        "baseline_generated_from": provenance,
        "findings": _counter_entries(actual),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "snapshot"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--policy", type=Path, required=True)
        subparser.add_argument("--report", type=Path, required=True)
        subparser.add_argument("--image-role", choices=sorted(ROLE_BINDINGS), required=True)
        subparser.add_argument("--expected-image-ref", required=True)
        subparser.add_argument(
            "--expected-image-id",
            required=True,
            help=("opaque Docker daemon/Trivy image identity (not a config or manifest digest)"),
        )
        subparser.add_argument(
            "--expected-manifest-digest",
            help="optional authoritative registry manifest digest",
        )
        subparser.add_argument("--expected-source-revision", required=True)
        subparser.add_argument("--expected-source-repository", required=True)
        subparser.add_argument("--repo-root", type=Path, default=Path.cwd())
        subparser.add_argument("--now")
        if command == "snapshot":
            subparser.add_argument("--scanner-metadata", type=Path, required=True)
            subparser.add_argument("--platform-manifest-digest", required=True)
            subparser.add_argument("--image-config-digest", required=True)
            subparser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        policy, _ = _read_json(args.policy, "policy")
        report, report_raw = _read_json(args.report, "report")
        now = _timestamp(args.now, "current time") if args.now else datetime.now(timezone.utc)
        common = {
            "policy": policy,
            "report": report,
            "role": args.image_role,
            "repo_root": args.repo_root.resolve(),
            "expected_image_ref": args.expected_image_ref,
            "expected_image_id": args.expected_image_id,
            "expected_manifest_digest": args.expected_manifest_digest,
            "expected_source_revision": args.expected_source_revision,
            "expected_source_repository": args.expected_source_repository,
        }
        if args.command == "validate":
            count = validate(**common, now=now)
            print(f"image security policy valid for {args.image_role}: {count} findings")
            return 0

        scanner_metadata, _ = _read_json(args.scanner_metadata, "scanner metadata")
        output = snapshot(
            **common,
            report_raw=report_raw,
            scanner_metadata=scanner_metadata,
            platform_manifest_digest=args.platform_manifest_digest,
            image_config_digest=args.image_config_digest,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote normalized {args.image_role} snapshot to {args.output}")
        return 0
    except (OSError, PolicyError) as exc:
        print(f"image security policy rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
