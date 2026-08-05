# Frozen image vulnerability debt

This directory contains the active, temporary, fail-closed image policy tracked by
[issue #9](https://github.com/JNZader/consorcio-canalero/issues/9).

Stage 2B2 generated the baseline from the preserved final images built at
`96cf15d0f36577c2500d2708dc5c1b899035177f` and their raw, unsuppressed Trivy 0.70.0 reports.
The backend exception is the exact normalized 24-row multiset (19 HIGH, 5 CRITICAL); the former
44-row PR17 set is invalid for this package closure. The Geo worker has an empty exception set, so
any HIGH or CRITICAL Geo finding fails.

The policy has no *automated* renewal mechanism — every extension is a one-line edit of a
hard-coded constant in a reviewed commit (it has happened twice; see below). Its ceilings are:

- CRITICAL: 2026-08-21T00:00:00Z
- HIGH: 2026-08-21T00:00:00Z
- absolute sunset: 2026-08-21T00:00:00Z

Both severity ceilings were moved to the already-existing absolute sunset (CRITICAL on
2026-07-30, HIGH on 2026-08-04) because every frozen finding is unfixable upstream: all 24
rows span 13 distinct CVEs that Debian's security tracker still marks `vulnerable` in trixie
with no fixed version, and none carries a `FixedVersion`. See the consolidated evidence block
in `scripts/validate_image_security_policy.py`. The sunset binds the policy *JSON*: the
validator checks it before the per-severity deadlines, and the ceiling check rejects any JSON
deadline past it. The sunset constant itself is pinned by
`test_deadline_ceilings_are_the_documented_dates`, so extending it takes a code-and-test change
in one reviewed commit with fresh justification — deliberate friction, not impossibility.

## Evidence and image identity

`baseline_generated_from.image_id` records the opaque daemon image identity returned by
`docker image inspect .Id` and emitted by Trivy as `Metadata.ImageID`. Depending on the Docker
image store, that value can identify an OCI index, manifest, or config; the validator never assumes
it is a configuration digest. `config_digest` and `platform_manifest_digest` record the separately
observed OCI config and selected `linux/amd64` manifest.

The baseline provenance also records the exact raw-report SHA-256, source revision, image
reference, pinned Dockerfile base, platform, scanner/report versions, scan time, and fresh
vulnerability-DB timestamps. Snapshot generation requires the Trivy JSON version sidecar plus the
independently observed platform-manifest and config digests. Active-policy validation fails closed
if any required provenance field is missing, malformed, stale at scan time, or inconsistent with
the pinned role bindings.

The recorded daemon identities are historical evidence, not static CI inputs. Every workflow build
derives its candidate identity dynamically and binds the raw report to that value, exact image
reference, platform, source/revision labels, Dockerfile base, and finding multiset.

`--expected-manifest-digest` remains optional and separate. Supply it only from an independent,
authoritative registry or deployment source. When supplied, the report must contain the matching
`repository@sha256:...` entry; absence or mismatch rejects the report. The validator never infers a
manifest or config digest from the daemon identity.

## Stable vulnerability identity

The frozen backend debt is an exact multiset keyed by target, class, type, CVE, package ID, PURL,
installed version, severity, status, and fixed-version availability. Counts remain exact: adding,
removing, or duplicating a finding rejects the scan. `Layer.Digest` and `Layer.DiffID` are explicitly
excluded because they describe volatile build-layer output, not vulnerability identity; Trivy may
omit them, and equivalent non-reproducible builds may change them without changing package debt.
Layer metadata is ignored in reports and is not stored in policy snapshots. No vulnerability,
package, fix, severity, status, provenance, or multiplicity check is relaxed.

## Stable finding targets

Trivy prefixes an OS target with the ephemeral scanned image reference. The validator normalizes
only a target equal to `Metadata.ArtifactName`, or that exact value followed solely by a
parenthesized distro suffix, to `<image>` while preserving the suffix. Python, filesystem, package,
and near-prefix targets remain verbatim, so target identity stays part of the exact tuple without
binding the debt set to a temporary tag.

## Daily rescan blocker

A scheduled workflow is intentionally not present yet. GITHUB_TOKEN can read GHCR, but the
repository has no authoritative source for the **currently deployed immutable backend and Geo
worker digest references**. Scanning `:latest` or a guessed commit tag would not prove deployed
state. Deployment configuration must expose both deployed `@sha256:` references as non-secret
repository variables (or an authenticated deployment inventory) before a daily job can bind and
scan them. No new registry secret is required or invented.
