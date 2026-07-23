# Frozen image vulnerability debt

This directory contains the temporary, fail-closed image policy tracked by
[issue #9](https://github.com/JNZader/consorcio-canalero/issues/9).

The frozen-image-debt.json file is deliberately **unactivated** in Stage 2A. It cannot validate
a backend image until Stage 2B builds the final consolidated source, scans it with Trivy 0.70.0,
and replaces the backend placeholder with the validator's exact normalized snapshot. Never copy
the former 44 findings: PR19 changed the final package closure.

The policy has no renewal mechanism. Its hard-coded ceilings are:

- CRITICAL: 2026-07-29T00:00:00Z
- HIGH: 2026-08-05T00:00:00Z
- absolute sunset: 2026-08-21T00:00:00Z

The Geo worker has no exception set; any HIGH or CRITICAL finding fails.

## Image identity

`baseline_generated_from.image_id` is the Docker configuration image ID returned by
`docker image inspect .Id`. It is not a registry manifest digest. A local
`buildx --load` candidate commonly has an empty `RepoDigests` list, so local validation binds
the report to that configuration ID, its exact image reference, platform, source/revision labels,
and finding multiset.

`--expected-manifest-digest` is optional and must only be supplied from an independent,
authoritative registry or deployment source. When supplied, the report must also contain the
matching `repository@sha256:...` entry. The validator never infers or substitutes a manifest
digest from the Docker configuration ID.

## Daily rescan blocker

A scheduled workflow is intentionally not present yet. GITHUB_TOKEN can read GHCR, but the
repository has no authoritative source for the **currently deployed immutable backend and Geo
worker digest references**. Scanning :latest or a guessed commit tag would not prove deployed
state. Stage 2B/GitHub configuration must expose both deployed @sha256: references as non-secret
repository variables (or an authenticated deployment inventory) before a daily job can bind and
scan them. No new registry secret is required or invented.
