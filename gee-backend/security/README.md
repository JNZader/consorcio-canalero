# Frozen image vulnerability debt

This directory contains the active, temporary, fail-closed image policy tracked by
[issue #9](https://github.com/JNZader/consorcio-canalero/issues/9).

Stage 2B2 generated the baseline from the preserved final images built at
`96cf15d0f36577c2500d2708dc5c1b899035177f` and their raw, unsuppressed Trivy 0.70.0 reports.
The backend exception is the exact normalized 56-row multiset (55 HIGH, 1 CRITICAL; 20 distinct
CVEs; no `FixedVersion` on any row) after the 2026-09-24 honest rescan that followed the Debian
13.7 hotfixes. The former 44-row PR17 set is invalid for this package closure. The Geo worker
has an empty exception set, so any HIGH or CRITICAL Geo finding fails.

The policy has no *automated* renewal mechanism — every extension is a one-line edit of a
hard-coded constant in a reviewed commit (it has happened four times; see below). Its ceilings are:

- CRITICAL: 2026-10-31T00:00:00Z
- HIGH: 2026-10-31T00:00:00Z
- absolute sunset: 2026-10-31T00:00:00Z

Both severity ceilings were first moved to the then-existing absolute sunset (CRITICAL on
2026-07-30, HIGH on 2026-08-04), on 2026-08-22 all three — the absolute sunset included, for
the first time — moved to 2026-09-18, and on 2026-09-24 all three moved to 2026-10-31. That
last extension is paired with real remediation: Debian 13.7 (2026-09-12) made `perl-base
5.40.1-6+deb13u1`, `gzip 1.13-1+deb13u1` and `libsqlite3-0 3.46.1-7+deb13u2` available to the
pinned base's apt, and trixie-security shipped `libpcre2-8-0 10.46-1~deb13u2`. The production
stage of `gee-backend/Dockerfile` now applies those four `--only-upgrade` hotfixes (same pattern
as openssl/util-linux; base digest untouched). The pcre2 one is mandatory: Trivy reports
CVE-2026-86145/-89157/-89161 *with* a `FixedVersion`, and this policy refuses to freeze anything
that has a fix. The baseline was regenerated from an honest Trivy 0.70.0 rescan of the resulting
image, so the rows that disappear (7 perl, 1 gzip, 2 sqlite) are the ones Trivy stops reporting —
nothing was removed by hand. The same rescan, with the vulnerability DB of 2026-09-24, also
revealed debt the August baseline did not know about and that has no apt candidate and no fix in
trixie (Debian tracker: `vulnerable` in trixie, fixed only in forky/sid): four util-linux CVEs
(CVE-2026-76642/-78408/-78409/-78410, 9 rows each), CVE-2026-16742 (`libsystemd0`/`libudev1`),
seven more `libxml2` HIGH rows and three more `libexpat1` HIGH rows. Still present from before:
CVE-2026-66046 (`libexpat1`), CVE-2026-6653 (`libxml2`, pulled in by `libosmesa6`),
CVE-2025-69720 (`ncurses`, 4 rows), CVE-2026-54369 (`libacl1`) and CVE-2026-9538 (`perl-base`,
postponed). Net: 18 → 56 rows. See the consolidated evidence block in
`scripts/validate_image_security_policy.py`.

Frontend Alpine `nginx`/`libxml2` debt is separate from this Debian baseline: hold
`nginx:1.30.4-alpine` until Alpine apk remediates **CVE-2026-6732** (Dependabot
#308/#330; see `consorcio-web/Dockerfile` runtime stage and `docs/ROADMAP.md`
backlog). Do not confuse trixie `libxml2` rows here with that frontend gate.

The sunset binds the policy *JSON*: the
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
